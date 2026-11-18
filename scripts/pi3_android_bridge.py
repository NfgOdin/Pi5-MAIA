#!/usr/bin/env python3
"""
scripts/pi3_android_bridge.py - Dual-Pi Android USB/ADB & Tether Gateway for Raspberry Pi 3

Runs on Pi 3 (default 0.0.0.0:8002, alongside Pi 3 dashcam stream on :8000) so Pi 5
can monitor USB tethering, read/send Android SMS, sync contacts, control calls, and
browse `/sdcard` phone storage over the direct Ethernet link (`10.0.0.1` <-> `10.0.0.2`).
"""

import argparse
import base64
import getpass
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

DEFAULT_PHONE_ROOT = "/sdcard"
_ADB_LOCK = threading.Lock()
_STATUS_LOCK = threading.Lock()
_STATUS_CACHE: Dict[str, Any] = {
    "status": "ok",
    "bridge_version": "1.0",
    "adb_installed": False,
    "adb_connected": False,
    "adb_error": None,
    "phone_model": None,
    "tether_active": False,
    "tether_iface": None,
    "tether_ip": None,
    "battery_pct": None,
    "call_state": "IDLE",
    "incoming_number": "",
}


def _run_cmd(args: List[str], timeout: float = 8.0) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)


def _run_adb(adb_args: List[str], timeout: float = 10.0) -> Tuple[int, str, str]:
    if not shutil.which("adb"):
        return 127, "", "adb binary not installed on Pi 3"
    with _ADB_LOCK:
        rc, out, err = _run_cmd(["adb", *adb_args], timeout=timeout)
        if rc != 0 and any(tok in (out + err).lower() for tok in ("protocol fault", "daemon not running", "connection reset")):
            _run_cmd(["adb", "start-server"], timeout=5.0)
            rc, out, err = _run_cmd(["adb", *adb_args], timeout=timeout)
        return rc, out, err


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
        rc_dt, out_dt, _ = _run_adb(
            ["shell", "dumpsys battery | grep -m1 level; dumpsys telephony.registry | grep -m2 -E 'mCallState|mCallIncomingNumber'"],
            timeout=6.0,
        )
        if rc_dt == 0:
            bm = re.search(r"level:\s*(\d+)", out_dt)
            if bm:
                battery_pct = int(bm.group(1))
            cm = re.search(r"mCallState=(\d+)", out_dt)
            if cm:
                call_state = {"0": "IDLE", "1": "RINGING_INBOUND", "2": "ACTIVE"}.get(cm.group(1), "IDLE")
            nm = re.search(r"mCallIncomingNumber=([^\s,]+)", out_dt)
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


def _to_pi3_fs_uri(real_path: Path) -> str:
    resolved = str(real_path.resolve()).replace("\\", "/")
    home_str = str(Path.home().resolve()).replace("\\", "/")
    if resolved == home_str:
        return "pi3-fs://home"
    if resolved == "/":
        return "pi3-fs://root"
    return f"pi3-fs://root/{resolved.lstrip('/')}"


def _resolve_pi3_fs_path(raw_uri: str) -> Path:
    s = str(raw_uri or "pi3-fs://home").strip().replace("\\", "/")
    if s in ("pi3-fs://home", "pi3-fs://home/", "home", "~", ""):
        return Path.home().resolve()
    if s in ("pi3-fs://root", "pi3-fs://root/", "/"):
        return Path("/")
    if s.startswith("pi3-fs://home/"):
        rel = s[len("pi3-fs://home/"):].lstrip("/")
        return (Path.home() / rel).resolve()
    if s.startswith("pi3-fs://root/"):
        rel = s[len("pi3-fs://root/"):].lstrip("/")
        return Path("/" + rel).resolve()
    if s.startswith("pi3-fs://"):
        rel = s[len("pi3-fs://"):].lstrip("/")
        return Path("/" + rel).resolve()
    return Path(os.path.expanduser(s)).resolve()


def _format_size_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _guess_file_type(name: str, is_dir: bool) -> str:
    if is_dir:
        return "folder"
    ext = os.path.splitext(name)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
        return "image"
    if ext in (".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac"):
        return "music"
    if ext in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
        return "video"
    if ext in (".txt", ".json", ".py", ".log", ".ini", ".cfg", ".sh", ".md", ".conf", ".service"):
        return "text"
    return "file"


def get_host_devices() -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    home_dir = Path.home().resolve()
    try:
        total_b, _used_b, free_b = shutil.disk_usage(home_dir)
        devices.append({
            "id": "loc_pi3_home",
            "name": "Pi 3 Home (~)",
            "label": "PI 3 HOME",
            "path": "pi3-fs://home",
            "mount_point": "pi3-fs://home",
            "icon": "🥧",
            "free_gb": round(free_b / (1024**3), 1),
            "total_gb": round(total_b / (1024**3), 1),
            "is_removable": False,
            "host": "pi3",
            "status": "READY",
        })
    except Exception:
        pass

    try:
        current_user = getpass.getuser()
        search_dirs = [Path("/media"), Path("/mnt")]
        if (Path("/media") / current_user).is_dir():
            search_dirs.append(Path("/media") / current_user)
        seen = set()
        for parent in search_dirs:
            if not parent.exists():
                continue
            for entry in parent.iterdir():
                if not entry.is_dir() or entry.name in ("pi", "root", current_user):
                    continue
                res = str(entry.resolve())
                if res in seen:
                    continue
                seen.add(res)
                try:
                    total_b, _used_b, free_b = shutil.disk_usage(entry)
                    uri = f"pi3-fs://root/{res.lstrip('/')}"
                    devices.append({
                        "id": f"pi3_usb_{entry.name}",
                        "name": f"Pi 3 USB ({entry.name})",
                        "label": f"PI3 USB ({entry.name.upper()})",
                        "path": uri,
                        "mount_point": uri,
                        "icon": "💾",
                        "free_gb": round(free_b / (1024**3), 1),
                        "total_gb": round(total_b / (1024**3), 1),
                        "is_removable": True,
                        "host": "pi3",
                        "status": "MOUNTED",
                    })
                except Exception:
                    pass
    except Exception:
        pass

    try:
        total_b, _used_b, free_b = shutil.disk_usage(Path("/"))
        devices.append({
            "id": "loc_pi3_root",
            "name": "Pi 3 System Root (/)",
            "label": "PI 3 ROOT (/)",
            "path": "pi3-fs://root",
            "mount_point": "pi3-fs://root",
            "icon": "⚙️",
            "free_gb": round(free_b / (1024**3), 1),
            "total_gb": round(total_b / (1024**3), 1),
            "is_removable": False,
            "host": "pi3",
            "status": "SYSTEM",
        })
    except Exception:
        pass

    return devices


def list_host_dir(raw_uri: str) -> Dict[str, Any]:
    target = _resolve_pi3_fs_path(raw_uri)
    if not target.exists() or not target.is_dir():
        target = Path.home().resolve()
    items: List[Dict[str, Any]] = []
    error_msg = None
    try:
        entries = list(target.iterdir())
        for entry in sorted(entries, key=lambda e: (not e.is_dir(), e.name.lower())):
            try:
                is_dir = entry.is_dir()
                st = entry.stat()
                size = st.st_size if not is_dir else 0
                mtime = st.st_mtime
                items.append({
                    "name": entry.name,
                    "path": f"pi3-fs://root/{str(entry.resolve()).lstrip('/')}",
                    "is_dir": is_dir,
                    "ext": entry.suffix.lower() if not is_dir else "",
                    "size_bytes": size,
                    "size_str": _format_size_bytes(size) if not is_dir else "",
                    "type": _guess_file_type(entry.name, is_dir),
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)) if mtime else "",
                    "timestamp": mtime,
                })
            except Exception:
                continue
    except Exception as exc:
        error_msg = str(exc)

    cur_uri = _to_pi3_fs_uri(target)
    parent_uri = _to_pi3_fs_uri(target.parent) if target.parent != target else None
    crumbs = [{"name": "🥧 Pi 3 (/)", "path": "pi3-fs://root"}]
    rel_segs = [seg for seg in str(target.resolve()).split("/") if seg]
    acc = ""
    for seg in rel_segs:
        acc += "/" + seg
        crumbs.append({"name": seg, "path": f"pi3-fs://root/{acc.lstrip('/')}"})

    return {
        "status": "ok" if not error_msg else "error",
        "error": error_msg,
        "path": cur_uri,
        "current_path": cur_uri,
        "parent_path": parent_uri,
        "breadcrumbs": crumbs,
        "items": items,
        "count": len(items),
    }


def read_host_file(raw_uri: str, max_bytes: int = 500000) -> Dict[str, Any]:
    target = _resolve_pi3_fs_path(raw_uri)
    if not target.exists() or target.is_dir():
        return {"status": "error", "message": "File not found on Pi 3"}
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_bytes)
        return {"status": "ok", "path": _to_pi3_fs_uri(target), "name": target.name, "content": content}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


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
            with _STATUS_LOCK:
                snap = dict(_STATUS_CACHE)
            self._send_json(snap)
        elif parsed.path == "/sms/list":
            self._send_json(list_sms())
        elif parsed.path == "/contacts":
            self._send_json(list_contacts())
        elif parsed.path == "/fs/list":
            self._send_json(list_phone_dir(qs.get("path", [DEFAULT_PHONE_ROOT])[0]))
        elif parsed.path == "/fs/read":
            self._send_json(read_phone_file(qs.get("path", [DEFAULT_PHONE_ROOT])[0]))
        elif parsed.path == "/host/devices":
            self._send_json({"status": "ok", "devices": get_host_devices()})
        elif parsed.path == "/host/list":
            self._send_json(list_host_dir(qs.get("path", ["pi3-fs://home"])[0]))
        elif parsed.path == "/host/read":
            self._send_json(read_host_file(qs.get("path", ["pi3-fs://home"])[0]))
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


def _status_monitor_loop() -> None:
    if shutil.which("adb"):
        _run_adb(["start-server"], timeout=6.0)
    while True:
        try:
            fresh = get_android_status()
            with _STATUS_LOCK:
                _STATUS_CACHE.clear()
                _STATUS_CACHE.update(fresh)
        except Exception:
            pass
        time.sleep(3.5)


def main() -> int:
    parser = argparse.ArgumentParser(description="CarPi3 Android USB/ADB & Filesystem Bridge")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    try:
        with _STATUS_LOCK:
            _STATUS_CACHE.update(get_android_status())
    except Exception:
        pass
    threading.Thread(target=_status_monitor_loop, daemon=True).start()
    srv = ThreadingHTTPServer((args.host, args.port), Pi3BridgeHandler)
    print(f"[PI3-BRIDGE] Android USB/ADB Bridge listening on {args.host}:{args.port}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
