"""Shared HTTP response helpers and modular route dispatchers for CarPi5."""

import json
from typing import Any, Dict


def send_json(handler: Any, payload: Any, status: int = 200) -> None:
    """Send a CORS-enabled UTF-8 JSON HTTP response."""
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload).encode("utf-8"))


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
    from routes.navigation_routes import handle_head as nav_head

    return nav_head(handler, parsed)


def dispatch_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Route modular GET requests; returns True if handled."""
    from routes.media_routes import handle_get as media_get
    from routes.navigation_routes import handle_get as nav_get
    from routes.telemetry_routes import handle_get as telemetry_get
    from routes.telephony_routes import handle_get as telephony_get

    for sub_handler in (telephony_get, nav_get, telemetry_get, media_get):
        if sub_handler(handler, parsed, state):
            return True
    return False


def dispatch_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Route modular POST requests; returns True if handled."""
    from routes.media_routes import handle_post as media_post
    from routes.navigation_routes import handle_post as nav_post
    from routes.telemetry_routes import handle_post as telemetry_post
    from routes.telephony_routes import handle_post as telephony_post

    for sub_handler in (telephony_post, nav_post, telemetry_post, media_post):
        if sub_handler(handler, parsed, state):
            return True
    return False
