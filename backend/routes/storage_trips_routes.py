"""HTTP route handlers for filesystem exploration and black-box trip archive management."""

import os
from typing import Any
from urllib.parse import parse_qs

from fs_manager import (
    copy_item,
    create_directory,
    delete_item,
    detect_usb_drives,
    list_directory,
    read_text_file,
    write_text_file,
)
from routes import read_json_body, send_bytes, send_json


def _send_csv_download(handler: Any, logger_obj: Any, t_id: Any) -> None:
    csv_bytes, filename = logger_obj.get_trip_csv_bytes(t_id) if logger_obj else (None, "")
    if csv_bytes:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/csv; charset=utf-8")
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(csv_bytes)
    else:
        send_json(handler, {"error": "CSV telemetry not found"}, status=404)


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle filesystem and trip archive GET endpoints."""
    path = parsed.path

    if path in ("/api/fs/devices", "/api/storage/devices"):
        send_json(handler, detect_usb_drives())
        return True
    if path == "/api/fs/list":
        target = parse_qs(parsed.query).get("path", [""])[0]
        send_json(handler, list_directory(target))
        return True
    if path == "/api/fs/read":
        target = parse_qs(parsed.query).get("path", [""])[0]
        send_json(handler, read_text_file(target))
        return True

    trip_logger = getattr(state, "trip_logger", None)

    if path == "/api/trips/telemetry":
        t_id = int(parse_qs(parsed.query).get("id", [0])[0])
        pts = trip_logger.get_trip_telemetry(t_id) if (trip_logger and t_id) else []
        send_json(handler, pts)
        return True
    if path == "/api/trips/recent":
        send_json(handler, trip_logger.get_recent_trips())
        return True
    if path == "/api/trips/stats":
        send_json(handler, trip_logger.get_lifetime_stats())
        return True
    if path == "/api/trips/manifest":
        t_id_str = parse_qs(parsed.query).get("id", [None])[0]
        t_id = int(t_id_str) if t_id_str and t_id_str.isdigit() else None
        html_content = trip_logger.get_manifest_html(t_id) if trip_logger else None
        if html_content:
            send_bytes(handler, html_content.encode("utf-8"), "text/html; charset=utf-8")
        else:
            send_json(handler, {"error": "Trip manifest not found"}, status=404)
        return True
    if path in ("/api/trips/download", "/api/trips/zip"):
        qs = parse_qs(parsed.query)
        t_id_str = qs.get("id", [None])[0]
        fmt = qs.get("format", ["zip"])[0].lower()
        t_id = int(t_id_str) if t_id_str and t_id_str.isdigit() else None
        if fmt == "csv":
            _send_csv_download(handler, trip_logger, t_id)
            return True
        zip_path, filename = trip_logger.get_trip_zip_path(t_id) if trip_logger else (None, "")
        if zip_path and os.path.exists(zip_path):
            with open(zip_path, "rb") as zf:
                zip_bytes = zf.read()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/zip")
            handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            handler.send_header("Content-Length", str(len(zip_bytes)))
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            handler.wfile.write(zip_bytes)
        else:
            send_json(handler, {"error": "Trip ZIP archive not found"}, status=404)
        return True
    if path == "/api/trips/csv":
        t_id_str = parse_qs(parsed.query).get("id", [None])[0]
        t_id = int(t_id_str) if t_id_str and t_id_str.isdigit() else None
        _send_csv_download(handler, trip_logger, t_id)
        return True
    if path == "/api/trips/settings":
        send_json(handler, trip_logger.get_settings() if trip_logger else {})
        return True
    if path == "/api/trips/retention":
        send_json(handler, {"retention_days": trip_logger.retention_days})
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle filesystem and trip archive POST endpoints."""
    path = parsed.path
    handled_paths = {
        "/api/fs/write",
        "/api/fs/delete",
        "/api/fs/copy",
        "/api/fs/mkdir",
        "/api/trips/archive_now",
        "/api/trips/settings",
        "/api/trips/clear",
        "/api/trips/delete",
        "/api/trips/retention",
    }
    if path not in handled_paths:
        return False

    req_data = read_json_body(handler)

    if path == "/api/fs/write":
        send_json(handler, write_text_file(req_data.get("path", ""), req_data.get("content", "")))
        return True
    if path == "/api/fs/delete":
        send_json(handler, delete_item(req_data.get("path", "")))
        return True
    if path == "/api/fs/copy":
        send_json(handler, copy_item(req_data.get("src", ""), req_data.get("dst", "")))
        return True
    if path == "/api/fs/mkdir":
        send_json(handler, create_directory(req_data.get("parent_path", ""), req_data.get("folder_name", "New Folder")))
        return True

    trip_logger = getattr(state, "trip_logger", None)

    if path == "/api/trips/archive_now":
        recent = trip_logger.get_recent_trips(1)
        active_id = trip_logger.current_trip_id or (recent[0]["id"] if recent else None)
        if active_id:
            zip_path = trip_logger.export_and_zip_trip(active_id, is_interim=(active_id == trip_logger.current_trip_id))
            send_json(handler, {"status": "ok", "archive_path": zip_path, "trip_id": active_id})
        else:
            send_json(handler, {"status": "error", "message": "No trip to archive"}, status=400)
        return True
    if path == "/api/trips/settings":
        new_settings = trip_logger.update_settings(req_data) if trip_logger else {}
        send_json(handler, {"status": "ok", "settings": new_settings})
        return True
    if path == "/api/trips/clear":
        ok = trip_logger.clear_all_trips()
        send_json(handler, {"status": "ok" if ok else "error", "message": "All trip logs cleared"}, status=200 if ok else 500)
        return True
    if path == "/api/trips/delete":
        trip_id = req_data.get("id")
        ok = trip_logger.delete_trip(int(trip_id)) if trip_id else False
        send_json(handler, {"status": "ok" if ok else "error"}, status=200 if ok else 400)
        return True

    # /api/trips/retention
    days = req_data.get("retention_days", 0)
    saved_days = trip_logger.set_retention_days(int(days))
    send_json(handler, {"status": "ok", "retention_days": saved_days})
    return True
