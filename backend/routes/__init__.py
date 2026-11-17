"""Shared HTTP response helpers and modular route dispatchers for CarPi5."""

from dataclasses import asdict, is_dataclass
import json
from typing import Any, Dict


def frame_to_dict(frame: Any) -> Dict[str, Any]:
    """Safely convert a telemetry dataclass frame (or dict/namespace) to a plain dict."""
    if not frame:
        return {}
    if is_dataclass(frame):
        return asdict(frame)
    if isinstance(frame, dict):
        return dict(frame)
    return dict(vars(frame))


def send_json(handler: Any, payload: Any, status: int = 200) -> None:
    """Send a CORS-enabled UTF-8 JSON HTTP response."""
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload).encode("utf-8"))


def emit_ai_speech(
    state: Any,
    text: str,
    source: str = "COPILOT",
    emotion: str = None,
    hud_message: str = None,
    speak: bool = True,
    priority: int = 1,
    client_id: str = None,
    event_type: str = None,
    action: str = None,
) -> Any:
    """Emit spoken companion output into history, SSE ai_event, and audio TTS safely."""
    import re
    import time

    if hasattr(state, "emit_ai_speech") and callable(state.emit_ai_speech):
        return state.emit_ai_speech(
            text,
            source=source,
            emotion=emotion,
            hud_message=hud_message,
            speak=speak,
            priority=priority,
            client_id=client_id,
            event_type=event_type,
            action=action,
        )

    raw = str(text or "").strip()
    if not raw:
        return None
    clean = re.sub(r"\[EMOTION:\s*[A-Za-z_]+\]", "", raw, flags=re.IGNORECASE)
    clean = re.sub(r"<emotion>[A-Za-z_]+</emotion>", "", clean, flags=re.IGNORECASE).strip()
    if not clean:
        return None
    if getattr(state, "llm", None) and hasattr(state.llm, "log_speech"):
        state.llm.log_speech(clean, source=source)
    ev = {
        "id": int(time.time() * 1000),
        "client_id": client_id,
        "type": event_type or str(source or "COPILOT").upper(),
        "source": str(source or "COPILOT").upper(),
        "emotion": emotion or "DEVOTED",
        "speech": clean,
        "hud_message": hud_message,
        "action": action,
        "timestamp": time.time(),
        "time_str": time.strftime("%I:%M %p"),
    }
    if hasattr(state, "latest_ai_event"):
        state.latest_ai_event = ev
    copilot = getattr(state, "copilot", None)
    voice_mode = getattr(copilot, "voice_mode", "COPILOT")
    if speak and voice_mode != "MUTED" and getattr(state, "audio", None) and hasattr(state.audio, "speak"):
        state.audio.speak(clean, priority=priority)
    return ev


def send_bytes(
    handler: Any,
    data: bytes,
    content_type: str,
    status: int = 200,
    cache_control: str = None,
    head_only: bool = False,
) -> None:
    """Send a binary HTTP response (with optional Cache-Control and HEAD support)."""
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    if cache_control:
        handler.send_header("Cache-Control", cache_control)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    if not head_only:
        handler.wfile.write(data)


def read_json_body(handler: Any) -> Dict[str, Any]:
    """Read and parse a JSON request body safely, returning `{}` on empty or malformed input."""
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length <= 0:
        return {}
    try:
        raw = handler.rfile.read(content_length).decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def dispatch_head(handler: Any, parsed: Any) -> bool:
    """Route modular HEAD requests; returns True if handled."""
    from routes.media_routes import handle_head as media_head
    from routes.navigation_routes import handle_head as nav_head

    return media_head(handler, parsed) or nav_head(handler, parsed)


def dispatch_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Route modular GET requests; returns True if handled."""
    from routes.ai_routes import handle_get as ai_get
    from routes.assets_dashcam_routes import handle_get as assets_get
    from routes.connectivity_routes import handle_get as conn_get
    from routes.hardware_routes import handle_get as hw_get
    from routes.maintenance_pip_routes import handle_get as maint_pip_get
    from routes.media_routes import handle_get as media_get
    from routes.navigation_routes import handle_get as nav_get
    from routes.settings_auth_routes import handle_get as settings_get
    from routes.storage_trips_routes import handle_get as storage_get
    from routes.system_routes import handle_get as sys_get
    from routes.telemetry_routes import handle_get as telemetry_get
    from routes.telephony_routes import handle_get as telephony_get

    for sub_handler in (
        telephony_get,
        nav_get,
        telemetry_get,
        media_get,
        conn_get,
        hw_get,
        storage_get,
        sys_get,
        ai_get,
        maint_pip_get,
        settings_get,
        assets_get,
    ):
        if sub_handler(handler, parsed, state):
            return True
    return False


def dispatch_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Route modular POST requests; returns True if handled."""
    from routes.ai_routes import handle_post as ai_post
    from routes.assets_dashcam_routes import handle_post as assets_post
    from routes.connectivity_routes import handle_post as conn_post
    from routes.hardware_routes import handle_post as hw_post
    from routes.maintenance_pip_routes import handle_post as maint_pip_post
    from routes.media_routes import handle_post as media_post
    from routes.navigation_routes import handle_post as nav_post
    from routes.settings_auth_routes import handle_post as settings_post
    from routes.storage_trips_routes import handle_post as storage_post
    from routes.system_routes import handle_post as sys_post
    from routes.telemetry_routes import handle_post as telemetry_post
    from routes.telephony_routes import handle_post as telephony_post

    for sub_handler in (
        telephony_post,
        nav_post,
        telemetry_post,
        media_post,
        conn_post,
        hw_post,
        storage_post,
        sys_post,
        ai_post,
        maint_pip_post,
        settings_post,
        assets_post,
    ):
        if sub_handler(handler, parsed, state):
            return True
    return False
