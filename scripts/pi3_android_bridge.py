#!/usr/bin/env python3
"""
scripts/pi3_android_bridge.py - Dual-Pi Android USB/ADB & Tether Gateway for Raspberry Pi 3

Runs on Pi 3 (default 0.0.0.0:8002, alongside Pi 3 dashcam stream on :8000) so Pi 5
can monitor USB tethering, read/send Android SMS, sync contacts, control calls, and
browse `/sdcard` phone storage over the direct Ethernet link (`10.0.0.1` <-> `10.0.0.2`).
"""

import argparse
import base64
import json
import posixpath
import re
import shlex
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

DEFAULT_PHONE_ROOT = "/sdcard"


def _run_cmd(args: List[str], timeout: float = 4.0) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)


def _run_adb(adb_args: List[str], timeout: float = 5.0) -> Tuple[int, str, str]:
    if not shutil.which("adb"):
        return 127, "", "adb binary not installed on Pi 3"
    return _run_cmd(["adb", *adb_args], timeout=timeout)


def _normalize_phone_path(raw_path: str) -> str:
    p = (raw_path or DEFAULT_PHONE_ROOT).strip().replace("\\", "/")
    if p.startswith("pi3://"):
        p = "/" + p[len("pi3://"):].lstrip("/")
    norm = posixpath.normpath(p)
    if norm == "/sdcard" or norm.startswith("/sdcard/"):
        return norm
    return DEFAULT_PHONE_ROOT


def _parse_content_query_rows(stdout: str) -> List[Dict[str, str]]:
    """Parse `adb shell content query` `Row: N key=val, ...` lines safely."""
    rows: List[Dict[str, str]] = []
    if not stdout:
        return rows
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue
        payload = re.sub(r"^Row:\s*\d+\s+", "", line)
        parts = re.split(r",\s+(?=[A-Za-z0-9_]+=)", payload)
        item: Dict[str, str] = {}
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                item[k.strip()] = "" if v.strip() == "NULL" else v.strip()
        if item:
            rows.append(item)
    return rows


def get_android_status() -> Dict[str, Any]:
    rc_adb, out_adb, err_adb = _run_adb(["devices", "-l"], timeout=2.5)
    adb_devices: List[Dict[str, str]] = []
    if rc_adb == 0:
        for line in out_adb.splitlines()[1:]:
            toks = line.strip().split()
            if len(toks) >= 2 and toks[1] == "device":
                model_m = re.search(r"model:([^\s]+)", line)
                adb_devices.append({"serial": toks[0], "model": model_m.group(1) if model_m else "Android USB"})

    # Check USB tether network interfaces (usb0 / rndis0 / enx*)
    tether_iface = None
    tether_ip = None
    rc_ip, out_ip, _ = _run_cmd(["ip", "-o", "-4", "addr", "show"], timeout=2.0)
    if rc_ip == 0:
        for line in out_ip.splitlines():
            m = re.match(r"^\d+:\s+(usb\d+|rndis\d+|enx[0-9a-fA-F]+)\s+inet\s+([0-9.]+)", line.strip())
            if m:
                tether_iface, tether_ip = m.group(1), m.group(2)
                break

    adb_connected = len(adb_devices) > 0
    battery_pct = None
    call_state = "IDLE"
    incoming_number = ""

    if adb_connected:
        rc_b, out_b, _ = _run_adb(["shell", "dumpsys", "battery"], timeout=3.0)
        if rc_b == 0:
            bm = re.search(r"level:\s*(\d+)", out_b)
            if bm:
                battery_pct = int(bm.group(1))
        rc_t, out_t, _ = _run_adb(["shell", "dumpsys", "telephony.registry"], timeout=3.0)
        if rc_t == 0:
            cm = re.search(r"mCallState=(\d+)", out_t)
            if cm:
                st = cm.group(1)
                call_state = {"0": "IDLE", "1": "RINGING_INBOUND", "2": "ACTIVE"}.get(st, "IDLE")
            nm = re.search(r"mCallIncomingNumber=([^\s,]+)", out_t)
            if nm and nm.group(1) not in ("", "null", "0"):
                incoming_number = nm.group(1)

    return {
        "status": "ok",
        "bridge_version": "1.0",
        "adb_installed": shutil.which("adb") is not None,
        "adb_connected": adb_connected,
        "adb_error": None if rc_adb == 0 else err_adb,
        "phone_model": adb_devices[0]["model"] if adb_devices else None,
        "tether_active": bool(tether_iface),
        "tether_iface": tether_iface,
        "tether_ip": tether_ip,
        "battery_pct": battery_pct,
        "call_state": call_state,
        "incoming_number": incoming_number,
    }


def list_sms(limit: int = 30) -> Dict[str, Any]:
    rc, out, err = _run_adb(
        ["shell", "content", "query", "--uri", "content://sms", "--projection", "_id:address:body:date:type:read"],
        timeout=6.0,
    )
    if rc != 0:
        return {"status": "error", "messages": [], "error": err or "Failed reading Android SMS via ADB"}
    raw_rows = _parse_content_query_rows(out)
    messages = []
    for r in raw_rows[:limit]:
        mtype = str(r.get("type", "1"))
        messages.append({
            "id": r.get("_id", ""),
            "address": r.get("address", "Unknown"),
            "body": r.get("body", ""),
            "date_ms": int(r["date"]) if r.get("date", "").isdigit() else 0,
            "direction": "INBOUND" if mtype == "1" else "OUTBOUND",
            "read": r.get("read", "1") == "1",
        })
    return {"status": "ok", "messages": messages}


def send_sms(recipient: str, text: str) -> Dict[str, Any]:
    clean_num = "".join(ch for ch in (recipient or "") if ch.isdigit() or ch == "+")
    clean_txt = (text or "").strip()
    if not clean_num or not clean_txt:
        return {"status": "error", "sent": False, "error": "Recipient and non-empty message text required."}

    # Priority 1: KDE Connect CLI if paired cleanly on Pi 3
    if shutil.which("kdeconnect-cli"):
        rc_k, out_k, _ = _run_cmd(["kdeconnect-cli", "--list-available", "--id-only"], timeout=2.5)
        dev_id = next((ln.strip() for ln in out_k.splitlines() if ln.strip()), "") if rc_k == 0 else ""
        if dev_id:
            rc_s, _so, err_s = _run_cmd(
                ["kdeconnect-cli", "-d", dev_id, "--send-sms", clean_txt, "--destination", clean_num],
                timeout=6.0,
            )
            if rc_s == 0:
                return {"status": "ok", "sent": True, "transport": "kdeconnect"}
            return {"status": "error", "sent": False, "transport": "kdeconnect", "error": err_s or "KDE Connect SMS failed"}

    # Priority 2: ADB isms service invocation (checks explicit failure/SecurityException cleanly)
    rc, out, err = _run_adb(
        [
            "shell",
            "service",
            "call",
            "isms",
            "5",
            "i32",
            "0",
            "s16",
            "com.android.mms.service",
            "s16",
            "null",
            "s16",
            clean_num,
            "s16",
            "null",
            "s16",
            clean_txt,
            "s16",
            "null",
            "s16",
            "null",
            "i32",
            "1",
            "i64",
            "0",
        ],
        timeout=6.0,
    )
    combined = f"{out}\n{err}"
    if rc == 0 and "Parcel(" in out and "Exception" not in combined and "Error" not in combined:
        return {"status": "ok", "sent": True, "transport": "adb_isms"}
    return {
        "status": "error",
        "sent": False,
        "transport": "adb_isms",
        "error": (err or out or "Android refused non-privileged ADB SMS dispatch; pair KDE Connect for full SMS send."),
    }


def list_contacts() -> Dict[str, Any]:
    rc, out, err = _run_adb(
        ["shell", "content", "query", "--uri", "content://com.android.contacts/data/phones", "--projection", "display_name:data1"],
        timeout=6.0,
    )
    if rc != 0:
        return {"status": "error", "contacts": [], "error": err or "Contacts query failed"}
    seen = set()
    contacts = []
    for r in _parse_content_query_rows(out):
        name = r.get("display_name", "").strip()
        phone = r.get("data1", "").strip()
        if name and phone and (name, phone) not in seen:
            seen.add((name, phone))
            contacts.append({"name": name, "phone": phone})
    return {"status": "ok", "contacts": contacts}


def list_phone_dir(raw_path: str) -> Dict[str, Any]:
    norm = _normalize_phone_path(raw_path)
    q_path = shlex.quote(norm.rstrip("/") + "/")
    rc, out, err = _run_adb(["shell", f"ls -la {q_path}"], timeout=5.0)
    if rc != 0:
        return {"status": "error", "error": err or f"Unable to browse {norm}", "path": f"pi3://{norm.lstrip('/')}", "items": []}

    items: List[Dict[str, Any]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("total "):
            continue
        # Parse toybox/Android `ls -la`: perms links user group size date time name
        m = re.match(r"^([drwxlstST-]+)\s+\d+\s+\S+\s+\S+\s+(\d+)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(.+)$", line)
        if not m:
            continue
        perms, size_str, mod_str, name = m.groups()
        if name in (".", ".."):
            continue
        is_dir = perms.startswith("d")
        full_posix = posixpath.join(norm, name)
        ext = posixpath.splitext(name)[1].lower() if not is_dir else ""
        items.append({
            "name": name,
            "path": f"pi3://{full_posix.lstrip('/')}",
            "is_dir": is_dir,
            "ext": ext,
            "size_bytes": int(size_str) if not is_dir else 0,
            "size_str": f"{int(size_str)} B" if not is_dir else "",
            "type": "folder" if is_dir else ("image" if ext in (".jpg", ".jpeg", ".png", ".webp") else ("music" if ext in (".mp3", ".m4a", ".flac", ".wav") else "file")),
            "modified": mod_str,
        })
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    parent_posix = posixpath.dirname(norm) if norm != DEFAULT_PHONE_ROOT else None
    return {
        "status": "ok",
        "path": f"pi3://{norm.lstrip('/')}",
        "current_path": f"pi3://{norm.lstrip('/')}",
        "parent_path": f"pi3://{parent_posix.lstrip('/')}" if parent_posix else None,
        "items": items,
        "count": len(items),
    }


def read_phone_file(raw_path: str, max_bytes: int = 500000) -> Dict[str, Any]:
    norm = _normalize_phone_path(raw_path)
    q_path = shlex.quote(norm)
    if not shutil.which("adb"):
        return {"status": "error", "message": "adb not available on Pi 3"}
    try:
        proc = subprocess.run(["adb", "exec-out", f"head -c {int(max_bytes)} {q_path}"], capture_output=True, timeout=6.0)
        if proc.returncode != 0:
            return {"status": "error", "message": proc.stderr.decode("utf-8", errors="replace")}
        raw = proc.stdout
        try:
            text = raw.decode("utf-8")
            return {"status": "ok", "path": f"pi3://{norm.lstrip('/')}", "name": posixpath.basename(norm), "content": text}
        except UnicodeDecodeError:
            return {"status": "ok", "path": f"pi3://{norm.lstrip('/')}", "name": posixpath.basename(norm), "base64": base64.b64encode(raw).decode("ascii")}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class Pi3BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, obj: Dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/status":
            self._send_json(get_android_status())
        elif parsed.path == "/sms/list":
            self._send_json(list_sms())
        elif parsed.path == "/contacts":
            self._send_json(list_contacts())
        elif parsed.path == "/fs/list":
            self._send_json(list_phone_dir(qs.get("path", [DEFAULT_PHONE_ROOT])[0]))
        elif parsed.path == "/fs/read":
            self._send_json(read_phone_file(qs.get("path", [DEFAULT_PHONE_ROOT])[0]))
        else:
            self._send_json({"status": "error", "error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = self._read_json()
        if parsed.path == "/sms/send":
            self._send_json(send_sms(body.get("recipient", ""), body.get("text", "")))
        elif parsed.path == "/call/dial":
            num = "".join(ch for ch in str(body.get("number", "")) if ch.isdigit() or ch == "+")
            rc, _o, err = _run_adb(["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{num}"])
            self._send_json({"status": "ok" if rc == 0 else "error", "dialed": rc == 0, "error": None if rc == 0 else err})
        elif parsed.path == "/call/answer":
            rc, _o, err = _run_adb(["shell", "input", "keyevent", "KEYCODE_HEADSETHOOK"])
            self._send_json({"status": "ok" if rc == 0 else "error", "answered": rc == 0, "error": None if rc == 0 else err})
        elif parsed.path == "/call/hangup":
            rc, _o, err = _run_adb(["shell", "input", "keyevent", "KEYCODE_ENDCALL"])
            self._send_json({"status": "ok" if rc == 0 else "error", "ended": rc == 0, "error": None if rc == 0 else err})
        else:
            self._send_json({"status": "error", "error": "Not found"}, status=404)


def main() -> int:
    parser = argparse.ArgumentParser(description="CarPi3 Android USB/ADB & Filesystem Bridge")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Pi3BridgeHandler)
    print(f"[PI3-BRIDGE] Android USB/ADB Bridge listening on {args.host}:{args.port}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
