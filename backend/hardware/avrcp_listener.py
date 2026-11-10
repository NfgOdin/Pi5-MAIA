"""
avrcp_listener.py - Bluetooth AVRCP Steering Wheel & Radio Button Listener for CarPi5
Watches Linux kernel input devices (/dev/input/event*) created by BlueZ AVRCP.
Dispatches Skip (Next), Previous, Play/Pause, and Volume buttons directly to CarPi5 UI actions.
"""

import os
import sys
import glob
import time
import struct
import select
import threading
from typing import Optional, Callable, Dict, Any

# Linux input event constants
EV_KEY = 0x01
KEY_VOLUMEUP = 115
KEY_VOLUMEDOWN = 114
KEY_MUTE = 113
KEY_NEXTSONG = 163
KEY_PLAYPAUSE = 164
KEY_PREVIOUSSONG = 165
KEY_STOPCD = 166
KEY_PLAYCD = 200
KEY_PAUSECD = 201

class AvrcpListener:
    def __init__(self, action_callback: Optional[Callable[[dict], None]] = None):
        self.action_callback = action_callback
        self.running = True
        self.connected = False
        self.current_device: Optional[str] = None
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "device": self.current_device
        }

    def find_avrcp_device(self) -> Optional[str]:
        """Finds any input device named '*AVRCP*' from /proc/bus/input/devices."""
        if not os.path.exists('/proc/bus/input/devices'):
            return None
        try:
            with open('/proc/bus/input/devices', 'r') as f:
                content = f.read()
            for section in content.split('\n\n'):
                if 'AVRCP' in section:
                    for line in section.splitlines():
                        if 'Handlers=' in line:
                            for part in line.split():
                                if part.startswith('event'):
                                    path = f"/dev/input/{part}"
                                    if os.path.exists(path):
                                        return path
        except Exception as e:
            print(f"[AVRCP] Error reading input devices: {e}")
        return None

    def _monitor_loop(self):
        print("[AVRCP] Background Steering Wheel & Radio Media Controller listener started.")
        if not sys.platform.startswith("linux"):
            self.connected = False
            self.current_device = None
            return

        while self.running:
            dev_path = self.find_avrcp_device()
            if not dev_path:
                self.connected = False
                self.current_device = None
                time.sleep(3)
                continue

            self.current_device = dev_path
            self.connected = True
            print(f"[AVRCP] Connected to car media controller: {dev_path}")

            try:
                # Open in non-blocking raw read mode
                with open(dev_path, 'rb') as f:
                    fd = f.fileno()
                    # 64-bit Linux input_event struct: 2x 8-byte ints (time), 2x uint16, 1x int32 = 24 bytes
                    event_size = struct.calcsize("qqHHI")
                    while self.running:
                        r, _, _ = select.select([fd], [], [], 2.0)
                        if not r:
                            # Verify device still exists
                            if not os.path.exists(dev_path):
                                break
                            continue

                        raw = f.read(event_size)
                        if not raw or len(raw) < event_size:
                            break

                        _, _, ev_type, ev_code, ev_value = struct.unpack("qqHHI", raw)

                        # EV_KEY: 1 = pressed, 0 = released, 2 = hold
                        if ev_type == EV_KEY and ev_value == 1:
                            self._handle_key(ev_code)

            except Exception as ex:
                print(f"[AVRCP] Device connection dropped ({ex}). Re-scanning in 3s...")
            finally:
                self.connected = False
                self.current_device = None
            time.sleep(3)

    def _handle_key(self, code: int):
        action = None
        if code == KEY_NEXTSONG:
            print("[AVRCP] >> Steering Wheel / Radio NEXT TRACK pressed!")
            action = {"type": "media", "action": "next"}
        elif code == KEY_PREVIOUSSONG:
            print("[AVRCP] << Steering Wheel / Radio PREVIOUS TRACK pressed!")
            action = {"type": "media", "action": "prev"}
        elif code in (KEY_PLAYPAUSE, KEY_PLAYCD, KEY_PAUSECD):
            print("[AVRCP] || Steering Wheel / Radio PLAY/PAUSE pressed!")
            action = {"type": "media", "action": "toggle"}
        elif code == KEY_VOLUMEUP:
            print("[AVRCP] + Steering Wheel / Radio VOLUME UP pressed!")
            action = {"type": "volume", "action": "up"}
        elif code == KEY_VOLUMEDOWN:
            print("[AVRCP] - Steering Wheel / Radio VOLUME DOWN pressed!")
            action = {"type": "volume", "action": "down"}
        elif code == KEY_MUTE:
            print("[AVRCP] X Steering Wheel / Radio MUTE pressed!")
            action = {"type": "volume", "action": "mute"}

        if action and self.action_callback:
            try:
                self.action_callback(action)
            except Exception as cb_err:
                print(f"[AVRCP] Callback error: {cb_err}")
