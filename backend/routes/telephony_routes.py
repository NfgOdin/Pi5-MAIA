"""HTTP route handlers for Phase 15 Cockpit Telephony, Kinship, and SMS."""

from typing import Any
from urllib.parse import parse_qs

from routes import read_json_body, send_json


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle telephony and SMS GET endpoints."""
    path = parsed.path
    phone = getattr(state, "phone", None)
    sms = getattr(state, "sms", None)

    if path == "/api/phone/status":
        status = phone.get_status() if phone else {"state": "IDLE", "connected": False}
        send_json(handler, {"status": "ok", "phone": status})
        return True

    if path == "/api/phone/contacts":
        contacts = phone.kinship.get_contacts() if phone else []
        send_json(handler, {"status": "ok", "contacts": contacts})
        return True

    if path == "/api/phone/history":
        hist = phone.history if phone else []
        send_json(handler, {"status": "ok", "history": hist})
        return True

    if path == "/api/sms/threads":
        threads = sms.get_threads() if sms else {}
        send_json(handler, {"status": "ok", "threads": threads})
        return True

    if path == "/api/sms/thread":
        q = parse_qs(parsed.query)
        num = q.get("number", [""])[0]
        thread = sms.get_thread(num) if (sms and num) else []
        send_json(handler, {"status": "ok", "thread": thread})
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle telephony and SMS POST endpoints."""
    path = parsed.path
    phone = getattr(state, "phone", None)
    sms = getattr(state, "sms", None)

    handled_paths = {
        "/api/phone/dial",
        "/api/phone/answer",
        "/api/phone/hangup",
        "/api/phone/screen",
        "/api/phone/mute",
        "/api/phone/incoming",
        "/api/phone/screening_transcript",
        "/api/phone/contacts",
        "/api/phone/contacts/delete",
        "/api/phone/sync",
        "/api/sms/send",
        "/api/sms/incoming",
    }
    if path not in handled_paths:
        return False

    req_data = read_json_body(handler)
    res_payload = {"status": "ok"}

    if path == "/api/phone/dial":
        num = req_data.get("number", "").strip()
        dialed = phone.dial(num) if phone else False
        res_payload["dialed"] = dialed
        if not dialed and phone:
            res_payload["error"] = getattr(phone, "last_error", "Phone transport offline")
    elif path == "/api/phone/answer":
        answered = phone.answer_call() if phone else False
        res_payload["answered"] = answered
        if not answered and phone:
            res_payload["error"] = getattr(phone, "last_error", "Phone transport offline")
    elif path == "/api/phone/hangup":
        res_payload["ended"] = phone.end_call() if phone else False
    elif path == "/api/phone/screen":
        res_payload["screening"] = phone.start_call_screening() if phone else False
    elif path == "/api/phone/mute":
        res_payload["is_muted"] = phone.toggle_mute() if phone else False
    elif path == "/api/phone/sync":
        c_sync = phone.sync_contacts_from_bridge() if (phone and hasattr(phone, "sync_contacts_from_bridge")) else {"status": "offline", "added": 0}
        s_sync = sms.sync_from_bridge() if (sms and hasattr(sms, "sync_from_bridge")) else {"status": "offline", "synced": 0}
        res_payload["contacts_sync"] = c_sync
        res_payload["sms_sync"] = s_sync
    elif path == "/api/phone/incoming":
        num = req_data.get("number", "Unknown").strip()
        if phone:
            phone.trigger_incoming_call(num)
        res_payload["triggered"] = num
    elif path == "/api/phone/screening_transcript":
        txt = req_data.get("text", "").strip()
        if phone:
            phone.update_screening_transcript(txt)
        res_payload["updated"] = txt
    elif path == "/api/phone/contacts":
        contact = req_data.get("contact", {})
        res_payload["contact"] = phone.kinship.add_or_update_contact(contact) if phone else {}
    elif path == "/api/phone/contacts/delete":
        cid = req_data.get("id", "").strip()
        res_payload["deleted"] = phone.kinship.delete_contact(cid) if phone else False
    elif path == "/api/sms/send":
        rec = req_data.get("recipient", "").strip()
        txt = req_data.get("text", "").strip()
        res_payload["message"] = sms.send_sms(rec, txt) if sms else {}
    elif path == "/api/sms/incoming":
        snd = req_data.get("sender", "Unknown").strip()
        txt = req_data.get("text", "").strip()
        res_payload["message"] = sms.receive_sms(snd, txt) if sms else {}

    send_json(handler, res_payload)
    return True
