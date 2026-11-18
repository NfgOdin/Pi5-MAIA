"""
sms_manager.py - Real Dual-Pi Android SMS Sync & Dispatch Manager for CarPi5

Routes outbound SMS and fetches Android SMS inbox/sent history via Pi 3 USB/ADB
(`scripts/pi3_android_bridge.py` on `10.0.0.2:8002`) with kinship announcements.
Never pretends an offline text was sent: records `"delivery_status": "sent" | "offline" | "error"`.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .phone_manager import Pi3AndroidBridgeClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SMS_STORAGE_PATH = PROJECT_ROOT / "storage" / "sms_threads.json"


class SMSManager:
    """Manages cockpit SMS threads, real Pi 3 bridge sync/dispatch, and kinship notifications."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, bridge_client: Optional[Pi3AndroidBridgeClient] = None, storage_file: Optional[Path] = None):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.storage_file = Path(storage_file) if storage_file else SMS_STORAGE_PATH
        self.bridge = bridge_client or Pi3AndroidBridgeClient.get_shared()
        self.lock = threading.Lock()
        self.threads: Dict[str, List[Dict[str, Any]]] = self._load()
        self._seen_bridge_ids = {
            msg.get("bridge_id")
            for msgs in self.threads.values()
            for msg in msgs
            if msg.get("bridge_id")
        }

        self.active_dictation_target = ""
        self.active_dictation_text = ""
        self.dictation_state = "IDLE"

        self._audio_player = None
        self._rag_engine = None
        self._kinship = None

    def set_dependencies(self, audio_player, rag_engine, kinship) -> None:
        self._audio_player = audio_player
        self._rag_engine = rag_engine
        self._kinship = kinship

    def _load(self) -> Dict[str, List[Dict[str, Any]]]:
        if self.storage_file.exists():
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self) -> None:
        with self.lock:
            try:
                self.storage_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.storage_file, "w", encoding="utf-8") as f:
                    json.dump(self.threads, f, indent=2)
            except Exception as e:
                print(f"[SMS] Save error: {e}")

    def sync_from_bridge(self, announce_new: bool = False) -> Dict[str, Any]:
        """Pull real SMS messages from the Pi 3 Android USB/ADB bridge."""
        res = self.bridge.get_sms()
        if res.get("status") != "ok":
            return {"status": "error", "synced": 0, "error": res.get("error", "Pi 3 SMS bridge offline")}

        added = 0
        for row in res.get("messages", []):
            bid = str(row.get("id") or "")
            if bid and bid in self._seen_bridge_ids:
                continue
            sender = row.get("address", "Unknown")
            body = row.get("body", "")
            direction = row.get("direction", "INBOUND")
            contact = self._kinship.resolve_contact(sender) if self._kinship else {"name": sender, "kinship": sender}
            msg_obj = {
                "id": f"sms_b_{bid or int(time.time() * 1000)}",
                "bridge_id": bid,
                "sender": sender if direction == "INBOUND" else "ME",
                "sender_name": contact.get("name", sender),
                "sender_kinship": contact.get("kinship", sender),
                "direction": direction,
                "text": body,
                "timestamp": (row.get("date_ms", 0) / 1000.0) if row.get("date_ms") else time.time(),
                "read": bool(row.get("read", True)),
                "delivery_status": "received" if direction == "INBOUND" else "sent",
            }
            with self.lock:
                self.threads.setdefault(sender, []).append(msg_obj)
            if bid:
                self._seen_bridge_ids.add(bid)
            added += 1
            if announce_new and direction == "INBOUND" and not row.get("read", True) and self._audio_player:
                self._audio_player.speak(f"{contact.get('kinship', sender)} texted: {body}", priority=1)

        if added:
            self._save()
        return {"status": "ok", "synced": added}

    def receive_sms(self, sender: str, text: str) -> Dict[str, Any]:
        clean_text = text.strip()
        contact = self._kinship.resolve_contact(sender) if self._kinship else {"name": sender, "kinship": sender}
        kinship = contact.get("kinship", sender)

        msg_obj = {
            "id": f"sms_{int(time.time() * 1000)}",
            "sender": sender,
            "sender_name": contact.get("name", sender),
            "sender_kinship": kinship,
            "direction": "INBOUND",
            "text": clean_text,
            "timestamp": time.time(),
            "read": False,
            "delivery_status": "received",
        }

        with self.lock:
            self.threads.setdefault(sender, []).append(msg_obj)
        self._save()

        if self._audio_player:
            self._audio_player.speak(f"{kinship} texted: '{clean_text}'. Would you like to reply?", priority=1)

        if self._rag_engine:
            self._rag_engine.add_episodic_memory(
                companion_summary=f"Text message from {kinship} ({contact.get('name', sender)}): '{clean_text}'",
                driver_quote=f"Text from {kinship}",
                emotion_tag="CARING",
                importance=6,
            )

        self.active_dictation_target = sender
        self.dictation_state = "AWAITING_REPLY"
        return msg_obj

    def send_sms(self, recipient: str, text: str) -> Dict[str, Any]:
        clean_text = text.strip()
        contact = self._kinship.resolve_contact(recipient) if self._kinship else {"name": recipient, "kinship": recipient}
        kinship = contact.get("kinship", recipient)

        bridge_res = self.bridge.send_sms(recipient, clean_text)
        actually_sent = bool(bridge_res.get("sent"))
        status_label = "sent" if actually_sent else ("offline" if bridge_res.get("status") == "offline" else "error")

        msg_obj = {
            "id": f"sms_{int(time.time() * 1000)}",
            "sender": "ME",
            "sender_name": "Driver",
            "sender_kinship": "Driver",
            "direction": "OUTBOUND",
            "text": clean_text,
            "timestamp": time.time(),
            "read": True,
            "sent": actually_sent,
            "delivery_status": status_label,
            "transport": bridge_res.get("transport", "offline"),
            "error": bridge_res.get("error"),
        }

        with self.lock:
            self.threads.setdefault(recipient, []).append(msg_obj)
        self._save()

        if self._audio_player:
            if actually_sent:
                self._audio_player.speak(f"Message to {kinship} has been sent.", priority=1)
            else:
                self._audio_player.speak(
                    f"Could not send text to {kinship}; phone bridge is offline or permission blocked.",
                    priority=1,
                )

        self.dictation_state = "IDLE"
        self.active_dictation_target = ""
        self.active_dictation_text = ""
        return msg_obj

    def get_threads(self) -> Dict[str, List[Dict[str, Any]]]:
        with self.lock:
            return dict(self.threads)

    def get_thread(self, contact_or_number: str) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.threads.get(contact_or_number, []))
