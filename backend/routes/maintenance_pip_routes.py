"""HTTP route handlers for MultiAir maintenance schedule and Pip Drosophila connectome."""

from typing import Any

from routes import emit_ai_speech, frame_to_dict, read_json_body, send_json


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle maintenance status and Pip connectome state GET endpoints."""
    path = parsed.path

    if path == "/api/maintenance/status":
        status_data = state.rag.get_maintenance_status() if getattr(state, "rag", None) else {"error": "rag_unavailable"}
        send_json(handler, status_data)
        return True

    if path == "/api/pip/state":
        frame = state.latest_frame
        circ = state.llm.get_circadian_state()
        pip_info = state.pip.step(0.0, frame, is_night=circ["is_night"])
        send_json(
            handler,
            {
                "connectome": "Princeton FlyWire 2024 Adult Drosophila",
                "neurons": 139255,
                "synapses": 54500000,
                "pip_state": pip_info,
            },
        )
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle maintenance service logging, odometer updates, and Pip stimulation POST endpoints."""
    path = parsed.path

    if path == "/api/maintenance/record":
        req_data = read_json_body(handler)
        key = req_data.get("item_key")
        mileage = int(req_data.get("mileage", 0))
        notes = req_data.get("notes", "")
        ok = state.rag.record_service(key, mileage, notes) if getattr(state, "rag", None) else False
        send_json(
            handler,
            {"status": "ok" if ok else "error", "item_key": key, "mileage": mileage},
            status=200 if ok else 400,
        )
        return True

    if path == "/api/maintenance/odometer":
        req_data = read_json_body(handler)
        odo = int(req_data.get("odometer", 0))
        if getattr(state, "rag", None) and odo > 0:
            state.rag.set_odometer(odo)
        send_json(handler, {"status": "ok", "odometer": odo})
        return True

    if path == "/api/pip/feed":
        pre_state = frame_to_dict(state.pip.get_state()) if hasattr(state.pip, "get_state") else {}
        state.pip.stimulate_sugar_water()
        if getattr(state, "llm", None) and hasattr(state.llm, "get_pip_reaction"):
            reaction = state.llm.get_pip_reaction("feed", pip_state=pre_state)
        else:
            reaction = {
                "speech": "Here you go, Pip! Yummy sugar water droplets!",
                "emotion": "HAPPY_PROUD",
                "action": "action_cheer.bvh",
                "hud_message": "🪰 FED PIP SUGAR WATER",
            }
        speech_text = reaction.get("speech", "Here you go, Pip! Yummy sugar water droplets!")
        hud_msg = reaction.get("hud_message", "🪰 FED PIP SUGAR WATER")
        emotion = reaction.get("emotion", "HAPPY_PROUD")
        anim = reaction.get("action", "action_cheer.bvh")
        emit_ai_speech(
            state,
            speech_text,
            source="PIP_FEED",
            emotion=emotion,
            hud_message=hud_msg,
            speak=True,
            priority=1,
            event_type="PIP_FEED",
            action=anim,
        )
        state.latest_ui_action = {
            "type": "PIP_FEED",
            "speech": speech_text,
            "action": anim,
            "emotion": emotion,
            "hud_message": hud_msg,
        }
        send_json(handler, {"status": "ok", "action": "SUGAR_WATER_FED", "speech": speech_text})
        return True

    if path == "/api/pip/scare":
        pre_state = frame_to_dict(state.pip.get_state()) if hasattr(state.pip, "get_state") else {}
        state.pip.stimulate_scare(force=1.0)
        reaction = (
            state.llm.get_pip_reaction("scare", pip_state=pre_state)
            if (getattr(state, "llm", None) and hasattr(state.llm, "get_pip_reaction"))
            else None
        )
        if reaction and reaction.get("speech"):
            emit_ai_speech(
                state,
                reaction["speech"],
                source="PIP_SCARE",
                emotion=reaction.get("emotion", "SURPRISED"),
                hud_message=reaction.get("hud_message", "🪰 PIP GIANT FIBER ESCAPE"),
                speak=True,
                priority=2,
                event_type="PIP_SCARE",
            )
        send_json(handler, {"status": "ok", "action": "GIANT_FIBER_ESCAPE_TRIGGERED"})
        return True

    return False
