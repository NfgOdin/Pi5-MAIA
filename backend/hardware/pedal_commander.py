"""
pedal_commander.py - Bluetooth Low Energy (BLE) Controller for Pedal Commander
Connects to Pedal Commander via BlueZ D-Bus (GATT Service 0xFFE0 / Char 0xFFE1).
Controls throttle maps (ECO, CITY, SPORT, SPORT+) and sensitivity (-4 to +4).
"""

import sys
import time
import threading
from typing import Dict, Any, Optional

MAC_ADDRESS = "18:62:E4:46:73:8B"
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
DBUS_CHAR_PATH = "/org/bluez/hci0/dev_18_62_E4_46_73_8B/service0010/char0011"

MODES = {
    "ECO": 0,
    "CITY": 1,
    "SPORT": 2,
    "SPORT+": 3,
    "SPORT_PLUS": 3
}

class PedalCommanderController:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.current_mode = "SPORT"
        self.current_level = 2
        self.is_connected = False
        self.last_ack = ""
        self._bus = None
        self._char_iface = None

        if sys.platform.startswith("linux"):
            threading.Thread(target=self._init_dbus, daemon=True).start()

    def _init_dbus(self):
        try:
            import dbus
            self._bus = dbus.SystemBus()
            try:
                char_obj = self._bus.get_object("org.bluez", DBUS_CHAR_PATH)
                self._char_iface = dbus.Interface(char_obj, "org.bluez.GattCharacteristic1")
                self.is_connected = True
                print("[PEDAL COMMANDER] Connected to BLE GATT Characteristic 0xFFE1.")
            except Exception as e:
                print(f"[PEDAL COMMANDER] Initial char resolve note: {e}")
        except Exception as ex:
            print(f"[PEDAL COMMANDER] D-Bus init error: {ex}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "mac": MAC_ADDRESS,
            "connected": self.is_connected,
            "mode": self.current_mode,
            "level": self.current_level,
            "last_ack": self.last_ack
        }

    def set_curve(self, mode: str, level: int) -> Dict[str, Any]:
        norm_mode = mode.upper().replace("PLUS", "+")
        if norm_mode not in MODES:
            return {"status": "error", "message": f"Invalid mode '{mode}'. Choose ECO, CITY, SPORT, SPORT+"}

        clamped_level = max(-4, min(4, int(level)))
        self.current_mode = norm_mode
        self.current_level = clamped_level

        mode_idx = MODES[norm_mode]
        # Map -4..+4 to 0..8
        sens_idx = clamped_level + 4

        sent = False
        if sys.platform.startswith("linux") and self._char_iface:
            try:
                import dbus
                # Construct packet combinations to ensure support across firmware revisions:
                # 1. Binary packet: Header 0xAA, mode, sensitivity, checksum, Tail 0x55
                chk = (0xAA + mode_idx + sens_idx) & 0xFF
                bin_packet = dbus.Array([dbus.Byte(0xAA), dbus.Byte(mode_idx), dbus.Byte(sens_idx), dbus.Byte(chk), dbus.Byte(0x55)], signature=dbus.Signature('y'))
                self._char_iface.WriteValue(bin_packet, {"type": "command"})
                
                # 2. Text command frame: PC:<mode>:<level>\r\n
                txt = f"PC:{norm_mode}:{clamped_level}\r\n".encode("utf-8")
                txt_packet = dbus.Array([dbus.Byte(b) for b in txt], signature=dbus.Signature('y'))
                self._char_iface.WriteValue(txt_packet, {"type": "command"})

                sent = True
                self.last_ack = f"Sent {norm_mode} ({clamped_level:+d})"
                print(f"[PEDAL COMMANDER] Transmitted mode {norm_mode} lvl {clamped_level:+d} to BLE UART!")
            except Exception as e:
                print(f"[PEDAL COMMANDER] WriteValue error: {e}")
                self.last_ack = f"Error: {e}"

        return {
            "status": "ok" if sent else "simulated",
            "mode": self.current_mode,
            "level": self.current_level,
            "sent": sent,
            "message": f"Pedal curve updated to {norm_mode} {clamped_level:+d}"
        }
