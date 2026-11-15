"""HTTP route handlers for Pi hardware diagnostics, Pi 3 co-processor, GPIO, display, and gestures."""

import json
import time
import urllib.request
from typing import Any

from routes import read_json_body, send_json


def _probe_pi3_dashcam(state: Any) -> dict:
    pi3_host = getattr(state, "pi3_dashcam_host", None) or "http://10.0.0.2:8000"
    candidates = [pi3_host, "http://10.0.0.2:8000", "http://192.168.0.141:8000", "http://carpi3.local:8000"]
    seen = set()
    clean_candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    for cand in clean_candidates:
        try:
            req = urllib.request.Request(f"{cand}/api/status", headers={"User-Agent": "CarPi5-SBC-Studio"})
            with urllib.request.urlopen(req, timeout=0.8) as r:
                if r.status == 200:
                    raw = json.loads(r.read().decode("utf-8"))
                    state.pi3_dashcam_host = cand
                    return {
                        "connected": True,
                        "status": "ONLINE",
                        "host": cand,
                        "model": raw.get("model", "Raspberry Pi 3 Model B"),
                        "hardware": raw.get("hardware", {}),
                        "disk": raw.get("disk", {}),
                        "recording": raw.get("recording", False),
                        "source": raw.get("source", "N/A"),
                        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
        except Exception:
            continue

    return {
        "connected": False,
        "status": "OFFLINE",
        "host": None,
        "model": "Raspberry Pi 3 Model B (Dashcam)",
        "message": "Pi 3 Co-Processor not reachable on direct Ethernet (10.0.0.2) or Wi-Fi (192.168.0.141). Check dual-link cable.",
        "hardware": {
            "temp_c": None,
            "temp_f": None,
            "cpu_pct": None,
            "load_1m": None,
            "ram_used_mb": None,
            "ram_total_mb": None,
            "ram_pct": None,
            "system_uptime": "--",
        },
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle hardware, GPIO, display brightness, and gesture GET requests."""
    path = parsed.path

    if path == "/api/system/health":
        send_json(handler, state.sys_monitor.get_system_health())
        return True
    if path in ("/api/system/detailed_specs", "/api/hardware/specs"):
        send_json(handler, state.sys_monitor.get_detailed_hardware_specs())
        return True
    if path == "/api/system/pi3_hardware":
        send_json(handler, _probe_pi3_dashcam(state))
        return True
    if path == "/api/system/fan":
        send_json(handler, {"enabled": False, "status": "disabled"})
        return True
    if path == "/api/system/brightness":
        send_json(handler, {"brightness": state.sys_monitor.current_brightness})
        return True
    if path == "/api/gesture/status":
        send_json(handler, state.gesture_ctrl.get_status())
        return True
    if path == "/api/gpio/pins":
        send_json(handler, state.gpio.get_pins_status())
        return True
    if path == "/api/gpio/relays":
        send_json(handler, state.gpio.get_relays_status())
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle display brightness, fan, gesture trigger, and GPIO POST requests."""
    path = parsed.path
    handled_paths = {
        "/api/system/brightness",
        "/api/system/fan",
        "/api/gesture/trigger",
        "/api/gpio/toggle",
        "/api/gpio/set",
        "/api/gpio/pwm",
        "/api/gpio/pulse",
        "/api/gpio/morse",
    }
    if path not in handled_paths:
        return False

    req_data = read_json_body(handler)

    if path == "/api/system/brightness":
        val = req_data.get("brightness", 100)
        state.sys_monitor.set_brightness(val)
        send_json(handler, {"status": "ok", "brightness": state.sys_monitor.current_brightness})
        return True

    if path == "/api/system/fan":
        send_json(handler, {"status": "disabled", "message": "Fan controller disabled"})
        return True

    if path == "/api/gesture/trigger":
        gesture = req_data.get("gesture", "SWIPE_RIGHT")
        with state.lock:
            state.latest_ui_action = {"type": "gesture", "gesture": gesture, "confidence": 1.0}
        send_json(handler, {"status": "ok", "gesture": gesture})
        return True

    if path == "/api/gpio/toggle":
        bcm = req_data.get("bcm", 17)
        state.gpio.toggle_pin(bcm)
        send_json(
            handler,
            {
                "status": "ok",
                "bcm": bcm,
                "pins": state.gpio.get_pins_status(),
                "relays": state.gpio.get_relays_status(),
            },
        )
        return True

    if path == "/api/gpio/set":
        bcm = req_data.get("bcm", 17)
        pin_state = req_data.get("state", False)
        state.gpio.set_pin(bcm, pin_state)
        send_json(handler, {"status": "ok", "bcm": bcm, "state": pin_state})
        return True

    if path == "/api/gpio/pwm":
        bcm = req_data.get("bcm", 18)
        duty = req_data.get("duty_cycle", 0.5)
        state.gpio.set_pwm(bcm, duty)
        send_json(handler, {"status": "ok", "bcm": bcm, "duty_cycle": duty})
        return True

    if path == "/api/gpio/pulse":
        bcm = req_data.get("bcm", 18)
        dur = req_data.get("duration", 0.5)
        state.gpio.pulse_pin(bcm, dur)
        send_json(handler, {"status": "ok", "pulsed": bcm, "duration": dur})
        return True

    # /api/gpio/morse
    bcm = req_data.get("bcm", 18)
    msg = req_data.get("message", "SOS")
    state.gpio.transmit_morse(bcm, msg)
    send_json(handler, {"status": "ok", "morse": msg, "bcm": bcm})
    return True
