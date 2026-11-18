"""
phone_manager.py - Real Dual-Pi Telephony (BlueZ/oFono HFP + Pi 3 Android USB/ADB Bridge)

Supports:
1. Pi 5 BlueZ / PipeWire / oFono Hands-Free Profile (HFP) call audio & D-Bus modem control.
2. Pi 3 (`10.0.0.2:8002`) Android USB/ADB + KDE Connect Ethernet bridge (calls, SMS, contacts, `/sdcard` mount).
3. Family Kinship mapping (`config/family_kinship.json`) & RAG call memory logging.
4. Faithful hardware reporting: never fakes `connected: True` or successful dialing when unplugged/unpaired.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "family_kinship.json"
HISTORY_PATH = PROJECT_ROOT / "storage" / "call_history.json"

CALL_STATE_IDLE = "IDLE"
CALL_STATE_RINGING_INBOUND = "RINGING_INBOUND"
CALL_STATE_DIALING_OUTBOUND = "DIALING_OUTBOUND"
CALL_STATE_ACTIVE = "ACTIVE"
CALL_STATE_SCREENING = "SCREENING"


class Pi3AndroidBridgeClient:
    """Ethernet HTTP client talking to `scripts/pi3_android_bridge.py` (`10.0.0.2:8002`)."""

    _shared_instance = None
    _shared_lock = threading.Lock()

    @classmethod
    def get_shared(cls) -> "Pi3AndroidBridgeClient":
        with cls._shared_lock:
            if cls._shared_instance is None:
                cls._shared_instance = cls()
            return cls._shared_instance

    def __init__(self, base_url: Optional[str] = None, probe_ttl_sec: float = 12.0):
        self.explicit_url = base_url or os.environ.get("CARPI5_PI3_BRIDGE_URL", "").strip() or None
        self.candidates = [self.explicit_url] if self.explicit_url else [
            "http://10.0.0.2:8002",
            "http://carpi3.local:8002",
            "http://192.168.0.141:8002",
        ]
        self.active_url: Optional[str] = self.explicit_url
        self.probe_ttl_sec = probe_ttl_sec
        self._last_probe_ts = 0.0
        self._cached_status: Dict[str, Any] = {
            "online": False,
            "adb_connected": False,
            "tether_active": False,
            "phone_model": None,
            "battery_pct": None,
            "call_state": "IDLE",
        }
        self._lock = threading.Lock()

    def _http_json(
        self,
        url: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 3.0,
    ) -> Optional[Dict[str, Any]]:
        try:
            data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
            headers = {"User-Agent": "CarPi5-Pi3Bridge/1.0"}
            if data_bytes is not None:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.status < 300:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        return None

    def probe_status(self, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            if not force and (now - self._last_probe_ts) < self.probe_ttl_sec:
                return dict(self._cached_status)

        urls = [self.explicit_url] if self.explicit_url else (
            [self.active_url] + [c for c in self.candidates if c != self.active_url]
            if self.active_url else list(self.candidates)
        )
        found_url = None
        status_data = None
        for u in urls:
            if not u:
                continue
            res = self._http_json(f"{u.rstrip('/')}/status", method="GET", timeout=1.2)
            if isinstance(res, dict) and res.get("status") == "ok":
                found_url = u.rstrip("/")
                status_data = res
                break

        with self._lock:
            self._last_probe_ts = time.time()
            if found_url and status_data:
                self.active_url = found_url
                self._cached_status = {
                    "online": True,
                    "url": found_url,
                    "adb_connected": bool(status_data.get("adb_connected", False)),
                    "tether_active": bool(status_data.get("tether_active", False)),
                    "tether_iface": status_data.get("tether_iface"),
                    "phone_model": status_data.get("phone_model"),
                    "battery_pct": status_data.get("battery_pct"),
                    "call_state": status_data.get("call_state", "IDLE"),
                    "incoming_number": status_data.get("incoming_number", ""),
                }
            else:
                self._cached_status = {
                    "online": False,
                    "url": None,
                    "adb_connected": False,
                    "tether_active": False,
                    "tether_iface": None,
                    "phone_model": None,
                    "battery_pct": None,
                    "call_state": "IDLE",
                    "incoming_number": "",
                }
            return dict(self._cached_status)

    def _call(self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        st = self.probe_status(force=(self.active_url is None))
        if not st.get("online"):
            st = self.probe_status(force=True)
        if not st.get("online") or not st.get("url"):
            return {"status": "offline", "error": "Pi 3 Android USB bridge offline (10.0.0.2:8002 unreachable)"}
        res = self._http_json(f"{st['url']}{path}", method=method, payload=payload, timeout=5.0)
        if res is None:
            return {"status": "error", "error": f"Pi 3 bridge request failed ({path})"}
        return res

    def dial(self, number: str) -> Dict[str, Any]:
        return self._call("/call/dial", method="POST", payload={"number": number})

    def answer(self) -> Dict[str, Any]:
        return self._call("/call/answer", method="POST", payload={})

    def hangup(self) -> Dict[str, Any]:
        return self._call("/call/hangup", method="POST", payload={})

    def get_sms(self) -> Dict[str, Any]:
        return self._call("/sms/list", method="GET")

    def send_sms(self, recipient: str, text: str) -> Dict[str, Any]:
        return self._call("/sms/send", method="POST", payload={"recipient": recipient, "text": text})

    def get_contacts(self) -> Dict[str, Any]:
        return self._call("/contacts", method="GET")

    def list_files(self, phone_path: str = "/sdcard") -> Dict[str, Any]:
        q = urllib.parse.urlencode({"path": phone_path})
        return self._call(f"/fs/list?{q}", method="GET")

    def read_file(self, phone_path: str) -> Dict[str, Any]:
        q = urllib.parse.urlencode({"path": phone_path})
        return self._call(f"/fs/read?{q}", method="GET")

    def get_host_devices(self) -> List[Dict[str, Any]]:
        res = self._call("/host/devices", method="GET")
        if isinstance(res, dict) and isinstance(res.get("devices"), list):
            return res["devices"]
        return []

    def list_host_files(self, host_path: str = "pi3-fs://home") -> Dict[str, Any]:
        q = urllib.parse.urlencode({"path": host_path})
        return self._call(f"/host/list?{q}", method="GET")

    def read_host_file(self, host_path: str) -> Dict[str, Any]:
        q = urllib.parse.urlencode({"path": host_path})
        return self._call(f"/host/read?{q}", method="GET")


class KinshipManager:
    """Manages daughter-centric family kinship titles, contacts, and speech announcements."""

    def __init__(self, config_file: Path = CONFIG_PATH):
        self.config_file = config_file
        self.lock = threading.Lock()
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[KINSHIP] Config load error: {e}")
        return {
            "kinship_rules": {"mom": "Nanny", "dad": "Papa", "brother": "Uncle", "sister": "Aunt"},
            "contacts": [],
            "call_screening_prompt": "Hi! You've reached Jonathan's Dodge Dart. He's driving right now, who is this?",
            "screening_enabled": True,
        }

    def save(self) -> None:
        with self.lock:
            try:
                self.config_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2)
            except Exception as e:
                print(f"[KINSHIP] Save error: {e}")

    def get_contacts(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.data.get("contacts", []))

    def resolve_contact(self, query: str) -> Dict[str, Any]:
        clean_q = re.sub(r"[^\w]", "", (query or "").lower())
        with self.lock:
            for c in self.data.get("contacts", []):
                clean_phone = re.sub(r"[^\w]", "", c.get("phone", "").lower())
                clean_name = re.sub(r"[^\w]", "", c.get("name", "").lower())
                clean_kinship = re.sub(r"[^\w]", "", c.get("kinship", "").lower())
                if clean_q and (
                    (clean_phone and (clean_q in clean_phone or clean_phone in clean_q))
                    or clean_q == clean_name
                    or clean_q == clean_kinship
                ):
                    return c
        return {
            "id": f"unknown_{int(time.time())}",
            "name": query if not (query or "").isdigit() else f"Caller {query}",
            "kinship": query,
            "relationship": "Unknown Caller",
            "phone": query,
            "avatar_icon": "📞",
            "direct_announce": False,
            "vip": False,
        }

    def format_announcement(self, caller_id: str) -> str:
        contact = self.resolve_contact(caller_id)
        kinship = contact.get("kinship", "")
        if contact.get("direct_announce") and kinship:
            return f"Dad, {kinship} is calling!"
        return f"Incoming call from {caller_id}."

    def add_or_update_contact(self, contact: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            contacts = self.data.setdefault("contacts", [])
            cid = contact.get("id") or f"c_{int(time.time())}"
            contact["id"] = cid
            existing_idx = next((i for i, c in enumerate(contacts) if c.get("id") == cid), -1)
            if existing_idx >= 0:
                contacts[existing_idx] = contact
            else:
                contacts.append(contact)
        self.save()
        return contact

    def merge_synced_contacts(self, synced: List[Dict[str, str]]) -> int:
        added = 0
        with self.lock:
            contacts = self.data.setdefault("contacts", [])
            existing_nums = {re.sub(r"[^\d]", "", c.get("phone", ""))[-10:] for c in contacts if c.get("phone")}
            for item in synced:
                num = str(item.get("phone", "")).strip()
                norm = re.sub(r"[^\d]", "", num)[-10:]
                name = str(item.get("name", "")).strip()
                if not norm or norm in existing_nums or not name:
                    continue
                existing_nums.add(norm)
                contacts.append({
                    "id": f"sync_{norm}",
                    "name": name,
                    "kinship": name,
                    "relationship": "Phone Contact",
                    "phone": num,
                    "avatar_icon": "👤",
                    "direct_announce": False,
                    "vip": False,
                })
                added += 1
        if added:
            self.save()
        return added

    def delete_contact(self, contact_id: str) -> bool:
        with self.lock:
            contacts = self.data.get("contacts", [])
            initial_len = len(contacts)
            self.data["contacts"] = [c for c in contacts if c.get("id") != contact_id]
            changed = len(self.data["contacts"]) < initial_len
        if changed:
            self.save()
        return changed


class BluetoothHFPProvider:
    """Real Linux BlueZ / oFono / PipeWire HFP provider with truthful offline reporting."""

    def __init__(self, bridge_client: Optional[Pi3AndroidBridgeClient] = None):
        self.device_name: Optional[str] = None
        self.device_address: Optional[str] = None
        self.connected: bool = False
        self.ofono_ready: bool = False
        self.modem_path: Optional[str] = None
        self.bridge = bridge_client or Pi3AndroidBridgeClient.get_shared()
        self.refresh_connection()

    def refresh_connection(self) -> None:
        if not sys.platform.startswith("linux"):
            self.connected = False
            self.device_name = None
            self.device_address = None
            self.ofono_ready = False
            self.modem_path = None
            return

        dev_name = None
        dev_mac = None
        has_bt_audio = False

        if shutil.which("pactl"):
            try:
                res = subprocess.run(["pactl", "list", "cards", "short"], capture_output=True, text=True, timeout=1.5)
                if "bluez_card" in (res.stdout or ""):
                    has_bt_audio = True
            except Exception:
                pass

        if shutil.which("bluetoothctl"):
            try:
                res = subprocess.run(["bluetoothctl", "devices", "Connected"], capture_output=True, text=True, timeout=1.5)
                for line in (res.stdout or "").splitlines():
                    m = re.match(r"^Device\s+([0-9A-Fa-f:]{17})\s+(.+)$", line.strip())
                    if m:
                        dev_mac, dev_name = m.group(1).upper(), m.group(2).strip()
                        break
            except Exception:
                pass

        ofono_modem = None
        if shutil.which("dbus-send"):
            try:
                res = subprocess.run(
                    [
                        "dbus-send", "--system", "--print-reply",
                        "--dest=org.ofono", "/", "org.ofono.Manager.GetModems",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                )
                if res.returncode == 0:
                    m = re.search(r'object path\s+"(/hfp/[^"]+)"', res.stdout or "")
                    if m:
                        ofono_modem = m.group(1)
            except Exception:
                pass

        self.ofono_ready = bool(ofono_modem)
        self.modem_path = ofono_modem
        self.connected = bool(has_bt_audio or ofono_modem)
        self.device_name = dev_name if self.connected else None
        self.device_address = dev_mac if self.connected else None

    def _ofono_call(self, interface: str, method: str, *args: str) -> bool:
        if not self.ofono_ready or not self.modem_path or not shutil.which("dbus-send"):
            return False
        try:
            res = subprocess.run(
                [
                    "dbus-send", "--system", "--print-reply",
                    "--dest=org.ofono", self.modem_path, f"{interface}.{method}", *args,
                ],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            return res.returncode == 0
        except Exception:
            return False

    def dial(self, number: str) -> Tuple[bool, str, Optional[str]]:
        self.refresh_connection()
        if self._ofono_call("org.ofono.VoiceCallManager", "Dial", f"string:{number}", "string:default"):
            return True, "bt_ofono_hfp", None

        res = self.bridge.dial(number)
        if res.get("dialed"):
            return True, "pi3_android_adb", None

        return False, "offline", res.get("error") or "No Bluetooth oFono HFP modem or Pi 3 Android USB device connected."

    def answer(self) -> Tuple[bool, str, Optional[str]]:
        self.refresh_connection()
        if self.ofono_ready and shutil.which("dbus-send"):
            # Active ringing calls live under <modem_path>/voicecall*
            res = subprocess.run(
                ["dbus-send", "--system", "--print-reply", "--dest=org.ofono", self.modem_path or "/", "org.ofono.VoiceCallManager.GetCalls"],
                capture_output=True, text=True, timeout=2.0,
            )
            m = re.search(r'object path\s+"([^"]*voicecall\d+)"', res.stdout or "") if res.returncode == 0 else None
            if m:
                ans = subprocess.run(
                    ["dbus-send", "--system", "--print-reply", "--dest=org.ofono", m.group(1), "org.ofono.VoiceCall.Answer"],
                    capture_output=True, text=True, timeout=2.5,
                )
                if ans.returncode == 0:
                    return True, "bt_ofono_hfp", None

        res = self.bridge.answer()
        if res.get("answered"):
            return True, "pi3_android_adb", None
        return False, "offline", res.get("error") or "No active call transport (BT oFono HFP / Pi 3 ADB) connected."

    def hangup(self) -> Tuple[bool, str, Optional[str]]:
        if self._ofono_call("org.ofono.VoiceCallManager", "HangupAll"):
            return True, "bt_ofono_hfp", None
        res = self.bridge.hangup()
        if res.get("ended"):
            return True, "pi3_android_adb", None
        return False, "offline", res.get("error") or "No phone call transport connected."

    def mute(self, muted: bool) -> bool:
        if not sys.platform.startswith("linux"):
            return False
        if shutil.which("wpctl"):
            try:
                val = "1" if muted else "0"
                return subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", val], timeout=1.5).returncode == 0
            except Exception:
                pass
        return False


class PhoneManager:
    """Central Cockpit Telephony Manager combining Pi 5 BlueZ HFP + Pi 3 Android USB Bridge."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        bridge_client: Optional[Pi3AndroidBridgeClient] = None,
        kinship_file: Optional[Path] = None,
        history_file: Optional[Path] = None,
    ):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.bridge = bridge_client or Pi3AndroidBridgeClient.get_shared()
        self.kinship = KinshipManager(config_file=Path(kinship_file) if kinship_file else CONFIG_PATH)
        self.bt_provider = BluetoothHFPProvider(bridge_client=self.bridge)

        self.call_state = CALL_STATE_IDLE
        self.active_caller_number = ""
        self.active_caller_name = ""
        self.active_caller_kinship = ""
        self.call_start_time = 0.0
        self.is_muted = False
        self.live_screening_transcript = ""
        self.screening_notes = ""
        self.last_error: Optional[str] = None
        self.active_transport: str = "offline"

        self.history_file = Path(history_file) if history_file else HISTORY_PATH
        self.history: List[Dict[str, Any]] = self._load_history()

        self._audio_player = None
        self._rag_engine = None

    def set_audio_player(self, player) -> None:
        self._audio_player = player

    def set_rag_engine(self, rag) -> None:
        self._rag_engine = rag

    def _load_history(self) -> List[Dict[str, Any]]:
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self) -> None:
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history[-100:], f, indent=2)
        except Exception as e:
            print(f"[PHONE] Save history error: {e}")

    def get_status(self) -> Dict[str, Any]:
        self.bt_provider.refresh_connection()
        b_st = self.bridge.probe_status(force=False)
        bt_conn = bool(self.bt_provider.connected)
        adb_conn = bool(b_st.get("online") and b_st.get("adb_connected"))
        any_conn = bt_conn or adb_conn

        device_name = self.bt_provider.device_name or b_st.get("phone_model") or "No Phone Paired"
        elapsed = int(time.time() - self.call_start_time) if (self.call_state == CALL_STATE_ACTIVE and self.call_start_time > 0) else 0
        return {
            "state": self.call_state,
            "connected": any_conn,
            "bt_hfp_connected": bt_conn,
            "ofono_ready": self.bt_provider.ofono_ready,
            "pi3_bridge_online": bool(b_st.get("online")),
            "android_usb_connected": adb_conn,
            "tether_active": bool(b_st.get("tether_active")),
            "phone_battery_pct": b_st.get("battery_pct"),
            "device_name": device_name,
            "active_transport": self.active_transport,
            "last_error": self.last_error,
            "caller_number": self.active_caller_number,
            "caller_name": self.active_caller_name,
            "caller_kinship": self.active_caller_kinship,
            "duration_sec": elapsed,
            "is_muted": self.is_muted,
            "live_screening_transcript": self.live_screening_transcript,
            "recent_calls": self.history[-10:],
            "contacts": self.kinship.get_contacts(),
        }

    def sync_contacts_from_bridge(self) -> Dict[str, Any]:
        res = self.bridge.get_contacts()
        if res.get("status") != "ok":
            return {"status": "error", "added": 0, "error": res.get("error", "Pi 3 Android bridge unavailable")}
        added = self.kinship.merge_synced_contacts(res.get("contacts", []))
        return {"status": "ok", "added": added, "total": len(self.kinship.get_contacts())}

    def clear_all_phone_data(self) -> Dict[str, int]:
        """Erase call history, saved contacts, and live screening buffers cleanly."""
        calls_cleared = len(self.history)
        contacts_cleared = len(self.kinship.get_contacts())
        self.history = []
        self._save_history()
        with self.kinship.lock:
            self.kinship.data["contacts"] = []
        self.kinship.save()
        self.live_screening_transcript = ""
        self.screening_notes = ""
        return {"calls_cleared": calls_cleared, "contacts_cleared": contacts_cleared}

    def trigger_incoming_call(self, caller_number: str) -> None:
        contact = self.kinship.resolve_contact(caller_number)
        self.call_state = CALL_STATE_RINGING_INBOUND
        self.active_caller_number = caller_number
        self.active_caller_name = contact.get("name", caller_number)
        self.active_caller_kinship = contact.get("kinship", caller_number)
        self.live_screening_transcript = ""
        self.screening_notes = ""

        announcement = self.kinship.format_announcement(caller_number)
        if self._audio_player:
            self._audio_player.speak(announcement, priority=0)

    def answer_call(self) -> bool:
        if self.call_state not in (CALL_STATE_RINGING_INBOUND, CALL_STATE_SCREENING):
            return False
        ok, transport, err = self.bt_provider.answer()
        self.active_transport = transport
        self.last_error = err
        if not ok:
            return False
        self.call_state = CALL_STATE_ACTIVE
        self.call_start_time = time.time()
        return True

    def start_call_screening(self) -> bool:
        if self.call_state != CALL_STATE_RINGING_INBOUND:
            return False
        self.call_state = CALL_STATE_SCREENING
        self.live_screening_transcript = "Waiting for caller speech..."
        prompt = self.kinship.data.get(
            "call_screening_prompt",
            "Hi! You've reached Jonathan's Dodge Dart. He's driving right now, who is calling?",
        )
        if self._audio_player:
            self._audio_player.speak(prompt, priority=0)
        return True

    def update_screening_transcript(self, text: str) -> None:
        self.live_screening_transcript = text

    def end_call(self) -> bool:
        if self.call_state == CALL_STATE_IDLE:
            return False

        duration = int(time.time() - self.call_start_time) if (self.call_state == CALL_STATE_ACTIVE and self.call_start_time > 0) else 0
        call_record = {
            "id": f"call_{int(time.time())}",
            "number": self.active_caller_number,
            "name": self.active_caller_name,
            "kinship": self.active_caller_kinship,
            "timestamp": time.time(),
            "duration_sec": duration,
            "was_screened": bool(self.screening_notes or self.live_screening_transcript),
            "notes": self.screening_notes or self.live_screening_transcript,
        }
        self.history.append(call_record)
        self._save_history()

        if self._rag_engine and (duration > 15 or call_record["was_screened"]):
            summary = f"Call with {self.active_caller_kinship} ({self.active_caller_name}) lasting {duration}s."
            if call_record["notes"]:
                summary += f" Screened message: {call_record['notes']}"
            self._rag_engine.add_episodic_memory(
                companion_summary=summary,
                driver_quote=f"Call with {self.active_caller_kinship}",
                emotion_tag="CARING",
                importance=7,
            )

        self.bt_provider.hangup()
        self.call_state = CALL_STATE_IDLE
        self.active_caller_number = ""
        self.active_caller_name = ""
        self.active_caller_kinship = ""
        self.call_start_time = 0.0
        self.is_muted = False
        self.live_screening_transcript = ""
        return True

    def dial(self, query: str) -> bool:
        contact = self.kinship.resolve_contact(query)
        target_number = contact.get("phone", query)
        ok, transport, err = self.bt_provider.dial(target_number)
        self.active_transport = transport
        self.last_error = err
        if not ok:
            if self._audio_player:
                self._audio_player.speak("Cannot place call right now: no Bluetooth HFP or Pi 3 USB phone is connected.", priority=1)
            return False

        self.call_state = CALL_STATE_DIALING_OUTBOUND
        self.active_caller_number = target_number
        self.active_caller_name = contact.get("name", query)
        self.active_caller_kinship = contact.get("kinship", query)
        self.call_start_time = time.time()

        kinship = contact.get("kinship", "")
        if self._audio_player:
            self._audio_player.speak(f"Calling {kinship or target_number} now.", priority=1)
        return True

    def toggle_mute(self) -> bool:
        self.is_muted = not self.is_muted
        self.bt_provider.mute(self.is_muted)
        return self.is_muted
