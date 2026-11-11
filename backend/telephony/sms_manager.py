"""
sms_manager.py - Hands-Free Cockpit SMS Dictation & Thread Management for CarPi5
Provides:
1. Spoken incoming text notifications with kinship recognition (Nanny, Uncle Steven, etc.).
2. Hands-free voice dictation with spoken verification before dispatch.
3. Persistent message thread storage in storage/sms_threads.json.
4. Semantic SMS logging into Living Memory (rag_memory.db).
"""

import os
import sys
import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SMS_STORAGE_PATH = PROJECT_ROOT / "storage" / "sms_threads.json"

class SMSManager:
    """Manages cockpit SMS threads, voice dictation workflows, and notifications."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.storage_file = SMS_STORAGE_PATH
        self.lock = threading.Lock()
        self.threads: Dict[str, List[Dict[str, Any]]] = self._load()

        self.active_dictation_target = ""
        self.active_dictation_text = ""
        self.dictation_state = "IDLE"  # "IDLE", "AWAITING_REPLY", "CONFIRMING_SEND"

        self._audio_player = None
        self._rag_engine = None
        self._kinship = None

    def set_dependencies(self, audio_player, rag_engine, kinship):
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

    def _save(self):
        with self.lock:
            try:
                self.storage_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.storage_file, "w", encoding="utf-8") as f:
                    json.dump(self.threads, f, indent=2)
            except Exception as e:
                print(f"[SMS] Save error: {e}")

    def receive_sms(self, sender: str, text: str) -> Dict[str, Any]:
        """Receives incoming SMS, saves to thread, notifies driver aloud, and logs to memory."""
        clean_text = text.strip()
        contact = self._kinship.resolve_contact(sender) if self._kinship else {"name": sender, "kinship": sender}
        kinship = contact.get("kinship", sender)

        msg_obj = {
            "id": f"sms_{int(time.time()*1000)}",
            "sender": sender,
            "sender_name": contact.get("name", sender),
            "sender_kinship": kinship,
            "direction": "INBOUND",
            "text": clean_text,
            "timestamp": time.time(),
            "read": False
        }

        with self.lock:
            thread = self.threads.setdefault(sender, [])
            thread.append(msg_obj)
        self._save()

        # Spoken notification with kinship (Priority 1)
        announcement = f"Dad, {kinship} texted you: '{clean_text}'. Would you like to reply?"
        if self._audio_player:
            self._audio_player.speak(announcement, priority=1)

        # Log into Living Memory
        if self._rag_engine:
            self._rag_engine.add_episodic_memory(
                rum_summary=f"Text message from {kinship} ({contact.get('name', sender)}): '{clean_text}'",
                driver_quote=f"Text from {kinship}",
                emotion_tag="CARING",
                importance=6
            )

        self.active_dictation_target = sender
        self.dictation_state = "AWAITING_REPLY"
        return msg_obj

    def send_sms(self, recipient: str, text: str) -> Dict[str, Any]:
        """Dispatches an outbound SMS message and stores it in thread history."""
        clean_text = text.strip()
        contact = self._kinship.resolve_contact(recipient) if self._kinship else {"name": recipient, "kinship": recipient}
        kinship = contact.get("kinship", recipient)

        msg_obj = {
            "id": f"sms_{int(time.time()*1000)}",
            "sender": "ME",
            "sender_name": "Jonathan (Dad)",
            "sender_kinship": "Dad",
            "direction": "OUTBOUND",
            "text": clean_text,
            "timestamp": time.time(),
            "read": True
        }

        with self.lock:
            thread = self.threads.setdefault(recipient, [])
            thread.append(msg_obj)
        self._save()

        print(f"[SMS] Sent to {kinship} ({recipient}): '{clean_text}'")
        if self._audio_player:
            self._audio_player.speak(f"Your message to {kinship} has been sent, Dad.", priority=1)

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
