"""HTTP route handlers for telemetry mode, DTC diagnostics, drag staging, dyno, thermal, and lap timer."""

from typing import Any
from urllib.parse import parse_qs

from routes import read_json_body, send_json


def _active_dyno(state: Any) -> Any:
    return state.obd_reader.dyno if state.telemetry_mode == "REAL" else state.simulator.dyno


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle telemetry, DTC diagnostics, drag staging, and canyon performance GET requests."""
    path = parsed.path

    if path == "/api/dtc/lookup":
        code = parse_qs(parsed.query).get("code", [""])[0]
        send_json(handler, state.copilot.diagnostics.explain_code(code))
        return True

    if path == "/api/dtc/inject":
        code = parse_qs(parsed.query).get("code", ["P0299"])[0]
        state.simulator.inject_dtc(code)
        print(f"[API] Injected DTC: {code}")
        send_json(handler, {"status": "ok", "injected": code, "active": state.simulator.active_dtcs})
        return True

    if path == "/api/dtc/status":
        obd = getattr(state, "obd", None) or getattr(state, "obd_reader", None)
        is_connected = bool(getattr(obd, "connected", False)) if obd else False
        if is_connected:
            active_dtcs = list(getattr(obd, "active_dtcs", []))
        else:
            sim = getattr(state, "simulator", None)
            active_dtcs = list(getattr(sim, "active_dtcs", [])) if sim else []

        code_details = []
        copilot = getattr(state, "copilot", None)
        if copilot and hasattr(copilot, "diagnostics"):
            for code in active_dtcs:
                code_details.append(copilot.diagnostics.explain_code(code))

        last_f = getattr(state, "last_frame", {}) or {}
        freeze_frame = {
            "rpm": last_f.get("rpm", 850),
            "boost_psi": last_f.get("boost_psi", 0.0),
            "coolant_temp_f": last_f.get("coolant_temp_f", 195),
            "speed_mph": last_f.get("speed_mph", 0),
            "engine_load_pct": last_f.get("engine_load_pct", 24.5),
            "throttle_pct": last_f.get("pedal_pos_pct", 12.0),
        }
        send_json(
            handler,
            {
                "status": "ok",
                "connected": is_connected,
                "mil_active": len(active_dtcs) > 0,
                "active_dtcs": active_dtcs,
                "pending_dtcs": [],
                "code_details": code_details,
                "freeze_frame": freeze_frame,
                "readiness": {
                    "misfire": True,
                    "fuel_system": True,
                    "comprehensive": True,
                    "catalyst": True,
                    "evap": True,
                    "o2_sensor": True,
                    "o2_heater": True,
                    "egr_vvt": True,
                },
            },
        )
        return True

    if path == "/api/dtc/clear":
        for src in (getattr(state, "obd", None), getattr(state, "obd_reader", None), getattr(state, "simulator", None)):
            if src and hasattr(src, "clear_dtcs"):
                try:
                    src.clear_dtcs()
                except Exception:
                    pass
        state.copilot.announced_dtcs.clear()
        print("[API] Cleared all DTCs")
        send_json(handler, {"status": "ok", "cleared": True})
        return True

    if path == "/api/drag/stage":
        tree_type = parse_qs(parsed.query).get("tree_type", ["SPORTSMAN"])[0]
        gps = getattr(state, "gps", None)
        res = gps.arm_staging(tree_type) if gps else {"status": "ok", "state": "STAGED"}
        send_json(handler, res)
        return True

    if path == "/api/drag/reset":
        gps = getattr(state, "gps", None)
        res = gps.reset_dragy() if gps else {"status": "ok", "state": "IDLE"}
        send_json(handler, res)
        return True

    if path == "/api/telemetry/mode":
        send_json(
            handler,
            {
                "mode": state.telemetry_mode,
                "connected": state.obd_reader.connected if state.telemetry_mode == "REAL" else True,
                "status_message": (
                    state.obd_reader.status_message
                    if state.telemetry_mode == "REAL"
                    else "Running Fiat 1.4L MultiAir simulation engine."
                ),
            },
        )
        return True

    if path == "/api/telemetry/dyno":
        dyno = _active_dyno(state)
        send_json(
            handler,
            {
                "whp": dyno.current_whp,
                "wtq": dyno.current_wtq,
                "peak_whp": dyno.peak_whp,
                "peak_wtq": dyno.peak_wtq,
                "peak_whp_rpm": dyno.peak_whp_rpm,
                "peak_wtq_rpm": dyno.peak_wtq_rpm,
                "vehicle": "2013 Dodge Dart 1.4L Turbo MultiAir",
                "curb_weight_lbs": 3186,
            },
        )
        return True

    if path == "/api/telemetry/spool_health":
        dyno = _active_dyno(state)
        send_json(
            handler,
            {
                "turbo": "Garrett GT1446 Wastegate & Diverter System",
                "health_pct": dyno.wastegate_health_pct,
                "latest_gradient_psi_per_1000rpm": dyno.latest_spool_gradient,
                "baseline_healthy_gradient": 9.5,
                "status": (
                    "HEALTHY"
                    if dyno.wastegate_health_pct >= 80.0
                    else ("ATTENTION" if dyno.wastegate_health_pct >= 65.0 else "WARNING_LEAK_OR_SLOP")
                ),
                "recent_spool_runs": [
                    {
                        "start_rpm": r.start_rpm,
                        "peak_rpm": r.peak_rpm,
                        "boost_delta": round(r.peak_boost - r.start_boost, 1),
                        "gradient": r.gradient_psi_per_1000rpm,
                        "health": r.health_score,
                        "gear": r.gear,
                    }
                    for r in dyno.recent_spool_runs
                ],
            },
        )
        return True

    if path == "/api/telemetry/shift_quality":
        dyno = _active_dyno(state)
        avg_score = round(dyno.total_shift_score / max(1, dyno.total_shift_count), 1) if dyno.total_shift_count > 0 else 100.0
        send_json(
            handler,
            {
                "transmission": "Fiat C635 6-Speed Manual",
                "latest_score": dyno.latest_shift_score,
                "latest_classification": dyno.latest_shift_type,
                "latest_delta_rpm": dyno.latest_shift_delta,
                "avg_score": avg_score,
                "total_shifts": dyno.total_shift_count,
                "recent_shifts": [
                    {
                        "from_gear": s.from_gear,
                        "to_gear": s.to_gear,
                        "speed_mph": s.speed_mph,
                        "delta_rpm": s.delta_rpm,
                        "score": s.score,
                        "classification": s.classification,
                    }
                    for s in dyno.shift_history[-10:]
                ],
            },
        )
        return True

    if path == "/api/telemetry/multiair_health":
        dyno = _active_dyno(state)
        send_json(
            handler,
            {
                "system": "Magneti Marelli UniAir Electro-Hydraulic Actuator",
                "oil_spec": "SAE 5W-40 Synthetic API SN / ACEA C3",
                "estimated_oil_temp_f": round(dyno.estimated_oil_temp_f, 1),
                "status": dyno.multiair_status,
                "full_boost_authorized": dyno.multiair_status == "WARM_OPTIMAL",
                "safe_boost_limit_psi": 7.0 if dyno.multiair_status == "COLD_PROTECT" else 22.0,
            },
        )
        return True

    if path == "/api/telemetry/thermal":
        data = getattr(state, "latest_thermal_data", None)
        if not data and getattr(state, "thermal_model", None):
            spd = state.latest_frame.speed_mph if state.latest_frame else 0.0
            data = state.thermal_model.step(spd)
        send_json(handler, data or {"brakes": {}, "tires": {}})
        return True

    if path == "/api/telemetry/lap_timer":
        lt = getattr(state, "lap_timer", None)
        send_json(handler, lt.get_status() if lt else {})
        return True

    if path == "/api/telemetry/lap_timer/tracks":
        lt = getattr(state, "lap_timer", None)
        send_json(handler, {"status": "ok", "tracks": lt.get_tracks() if lt else []})
        return True

    if path == "/api/telemetry/headlights":
        frame = getattr(state, "latest_frame", None)
        hl = getattr(frame, "headlights_on", False) if frame else False
        lux = getattr(frame, "ambient_light_lux", 100.0) if frame else 100.0
        send_json(handler, {"status": "ok", "headlights_on": hl, "ambient_light_lux": lux})
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle telemetry mode, drag staging, and canyon lap timer POST requests."""
    path = parsed.path

    if path == "/api/telemetry/mode":
        req_data = read_json_body(handler)
        is_test = req_data.get("test_mode", False) or (req_data.get("mode", "").upper() == "TEST")
        state.telemetry_mode = "TEST" if is_test else "REAL"
        state.save_settings({"test_mode": is_test, "telemetry_mode": state.telemetry_mode})
        print(f"[TELEMETRY] Telemetry mode switched to: {state.telemetry_mode} (Test mode: {is_test})")
        send_json(
            handler,
            {
                "status": "ok",
                "mode": state.telemetry_mode,
                "test_mode": is_test,
                "connected": state.obd_reader.connected if state.telemetry_mode == "REAL" else True,
                "status_message": (
                    state.obd_reader.status_message
                    if state.telemetry_mode == "REAL"
                    else "Running Fiat 1.4L MultiAir simulation engine."
                ),
            },
        )
        return True

    if path == "/api/drag/stage":
        req_data = read_json_body(handler)
        tree_type = req_data.get("tree_type", "SPORTSMAN")
        gps = getattr(state, "gps", None)
        res = gps.arm_staging(tree_type) if gps else {"status": "ok", "state": "STAGED"}
        send_json(handler, res)
        return True

    if path == "/api/drag/reset":
        gps = getattr(state, "gps", None)
        res = gps.reset_dragy() if gps else {"status": "ok", "state": "IDLE"}
        send_json(handler, res)
        return True

    if path == "/api/telemetry/headlights":
        req_data = read_json_body(handler)
        new_hl = bool(req_data.get("headlights", True))
        sim = getattr(state, "simulator", None)
        if sim and hasattr(sim, "set_headlights"):
            sim.set_headlights(new_hl)
        send_json(handler, {"status": "ok", "headlights_on": new_hl})
        return True

    if not path.startswith("/api/telemetry/lap_timer/"):
        return False

    sub = path.replace("/api/telemetry/lap_timer/", "")
    req_data = read_json_body(handler)
    lt = getattr(state, "lap_timer", None)
    if lt:
        if sub == "arm":
            lt.arm()
        elif sub == "start":
            lt.start_manual()
        elif sub == "stop":
            lt.stop()
        elif sub == "reset":
            lt.reset()
        elif sub == "select":
            lt.set_track(req_data.get("track_id", "pinal_pass"))

    send_json(handler, {"status": "ok", "lap_timer": lt.get_status() if lt else {}})
    return True
