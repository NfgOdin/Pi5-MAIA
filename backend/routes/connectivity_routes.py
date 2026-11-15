"""HTTP route handlers for Wi-Fi, Bluetooth, and Pedal Commander connectivity."""

from typing import Any

from routes import read_json_body, send_json


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle Wi-Fi, Bluetooth, and Pedal Commander GET requests."""
    path = parsed.path

    if path == "/api/wifi/status":
        send_json(handler, state.wifi.get_status())
        return True
    if path == "/api/wifi/scan":
        send_json(handler, state.wifi.scan_networks())
        return True
    if path == "/api/wifi/saved":
        send_json(handler, state.wifi.get_saved())
        return True

    if path in ("/api/bluetooth/status", "/api/bluetooth/devices"):
        send_json(handler, state.bluetooth.get_status())
        return True
    if path == "/api/bluetooth/scan":
        send_json(handler, state.bluetooth.scan_devices())
        return True
    if path == "/api/bluetooth/paired":
        send_json(handler, state.bluetooth.get_paired())
        return True

    if path == "/api/pedal_commander/status":
        send_json(handler, state.pedal_commander.get_status())
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle Wi-Fi, Bluetooth, and Pedal Commander POST requests."""
    path = parsed.path
    handled_paths = {
        "/api/wifi/connect",
        "/api/wifi/forget",
        "/api/wifi/clear",
        "/api/wifi/always_on",
        "/api/bluetooth/connect",
        "/api/bluetooth/disconnect",
        "/api/bluetooth/remove",
        "/api/bluetooth/discoverable",
        "/api/pedal_commander/set",
        "/api/pedal_commander/pin",
    }
    if path not in handled_paths:
        return False

    req_data = read_json_body(handler)

    if path == "/api/wifi/connect":
        res = state.wifi.connect(
            req_data.get("ssid", ""),
            req_data.get("password", None),
            req_data.get("auto_connect", True),
        )
    elif path == "/api/wifi/forget":
        res = state.wifi.forget(req_data.get("ssid", ""))
    elif path == "/api/wifi/clear":
        res = state.wifi.clear_all()
    elif path == "/api/wifi/always_on":
        res = state.wifi.set_always_on(req_data.get("enabled", True))
    elif path == "/api/bluetooth/connect":
        res = state.bluetooth.connect_device(req_data.get("mac", ""))
    elif path == "/api/bluetooth/disconnect":
        res = state.bluetooth.disconnect_device(req_data.get("mac", ""))
    elif path == "/api/bluetooth/remove":
        res = state.bluetooth.remove_device(req_data.get("mac", ""))
    elif path == "/api/bluetooth/discoverable":
        res = state.bluetooth.set_discoverable(req_data.get("enable", True))
    elif path == "/api/pedal_commander/set":
        res = state.pedal_commander.set_curve(
            req_data.get("mode", "SPORT"),
            req_data.get("level", 0),
            pin=req_data.get("pin"),
        )
    else:  # /api/pedal_commander/pin
        pin = req_data.get("pin", "")
        if getattr(state, "pedal_commander", None):
            state.pedal_commander.set_pin(pin)
        res = {
            "status": "ok",
            "pin": pin,
            "message": "Authentication PIN transmitted to Pedal Commander",
        }

    send_json(handler, res)
    return True
