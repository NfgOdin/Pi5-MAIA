"""
bluetooth_manager.py - Bluetooth Device & Audio Connection Manager for CarPi5
Interfaces with bluez (bluetoothctl) and pipewire audio.
Supports scanning, pairing, trusting, connecting, disconnecting, and auto-reconnect.
"""

import os
import re
import json
import time
import platform
import subprocess
from typing import Dict, Any, List, Optional

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "bluetooth_saved.json")
IS_LINUX = platform.system().lower() == "linux"

class BluetoothManager:
    def __init__(self):
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        default_config = {
            "pairable": True,
            "discoverable": True,
            "saved_devices": []
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    default_config.update(data)
            except Exception as e:
                print(f"[BLUETOOTH] Error loading {CONFIG_FILE}: {e}")
        return default_config

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"[BLUETOOTH] Error saving {CONFIG_FILE}: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns controller status, discoverable state, and currently connected devices."""
        status = {
            "powered": False,
            "pairable": True,
            "discoverable": True,
            "controller_name": "CarPi",
            "controller_mac": "",
            "connected_device": None,
            "connected_devices": []
        }

        if not IS_LINUX:
            return {
                "powered": True,
                "pairable": True,
                "discoverable": True,
                "controller_name": "CarPi (PC Sim)",
                "controller_mac": "00:1A:7D:DA:71:13",
                "connected_device": {
                    "mac": "0C:C0:C0:09:7D:45",
                    "name": "Uconnect",
                    "alias": "Uconnect",
                    "paired": True,
                    "connected": True,
                    "audio_connected": True
                },
                "connected_devices": [
                    {
                        "mac": "0C:C0:C0:09:7D:45",
                        "name": "Uconnect",
                        "paired": True,
                        "connected": True
                    }
                ]
            }

        try:
            out = subprocess.check_output(["bluetoothctl", "show"], text=True, timeout=3)
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("Controller"):
                    parts = line.split()
                    if len(parts) >= 2:
                        status["controller_mac"] = parts[1]
                elif line.startswith("Name:"):
                    status["controller_name"] = line.split(":", 1)[1].strip()
                elif line.startswith("Powered:"):
                    status["powered"] = "yes" in line.lower()
                elif line.startswith("Pairable:"):
                    status["pairable"] = "yes" in line.lower()
                elif line.startswith("Discoverable:"):
                    status["discoverable"] = "yes" in line.lower()

            # Check connected devices
            dev_out = subprocess.check_output(["bluetoothctl", "devices", "Connected"], text=True, timeout=3)
            connected = []
            for dline in dev_out.splitlines():
                dline = dline.strip()
                m = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.+)", dline)
                if m:
                    connected.append({
                        "mac": m.group(1),
                        "name": m.group(2).strip(),
                        "connected": True,
                        "paired": True
                    })

            status["connected_devices"] = connected
            if connected:
                status["connected_device"] = connected[0]

        except Exception as e:
            print(f"[BLUETOOTH] Status error: {e}")

        return status

    def scan_devices(self) -> List[Dict[str, Any]]:
        """
        Runs bluetoothctl active scan for 5 seconds and parses all discovered devices,
        exactly like Odin's _bluetooth_scan_thread.
        """
        if not IS_LINUX:
            return [
                {"mac": "0C:C0:C0:09:7D:45", "name": "Uconnect (Dodge Dart)", "rssi": -45, "paired": False, "connected": False},
                {"mac": "18:62:E4:46:73:8B", "name": "PDLCommander", "rssi": -65, "paired": False, "connected": False},
                {"mac": "F4:F5:DB:12:34:56", "name": "User Phone", "rssi": -55, "paired": True, "connected": True}
            ]

        devices_map = {}
        try:
            # 1. Fetch currently paired devices
            try:
                paired_out = subprocess.check_output(["bluetoothctl", "devices", "Paired"], text=True, timeout=3)
                for line in paired_out.splitlines():
                    m = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.+)", line.strip())
                    if m:
                        devices_map[m.group(1)] = {
                            "mac": m.group(1),
                            "name": m.group(2).strip(),
                            "paired": True,
                            "connected": False,
                            "rssi": -60
                        }
            except Exception:
                pass

            # 2. Trigger active scan (exact Odin command: bluetoothctl --timeout 5 scan on)
            try:
                subprocess.run("bluetoothctl --timeout 5 scan on", shell=True, capture_output=True, text=True, timeout=8)
            except Exception as se:
                print(f"[BLUETOOTH] Scan subprocess error: {se}")

            # 3. Retrieve all devices found (exact Odin command: bluetoothctl devices)
            try:
                result = subprocess.run("bluetoothctl devices", shell=True, capture_output=True, text=True, timeout=3)
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        parts = line.split(" ", 2)
                        if len(parts) >= 3 and parts[0] == "Device":
                            mac = parts[1]
                            name = parts[2].strip()
                            if mac not in devices_map:
                                devices_map[mac] = {
                                    "mac": mac,
                                    "name": name,
                                    "paired": False,
                                    "connected": False,
                                    "rssi": -70
                                }
                            else:
                                devices_map[mac]["name"] = name
            except Exception as de:
                print(f"[BLUETOOTH] Devices fetch error: {de}")

            # 4. Check connected
            try:
                conn_out = subprocess.check_output(["bluetoothctl", "devices", "Connected"], text=True, timeout=3)
                for line in conn_out.splitlines():
                    m = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.+)", line.strip())
                    if m and m.group(1) in devices_map:
                        devices_map[m.group(1)]["connected"] = True
            except Exception:
                pass

        except Exception as e:
            print(f"[BLUETOOTH] Overall scan error: {e}")

        results = list(devices_map.values())
        results.sort(key=lambda d: (not d["connected"], not d["paired"], d["name"] == d["mac"]))
        return results

    def get_paired(self) -> List[Dict[str, Any]]:
        """Returns list of paired devices."""
        if not IS_LINUX:
            return [
                {"mac": "0C:C0:C0:09:7D:45", "name": "Uconnect", "connected": False}
            ]

        paired = []
        try:
            out = subprocess.check_output(["bluetoothctl", "devices", "Paired"], text=True, timeout=3)
            conn_out = subprocess.check_output(["bluetoothctl", "devices", "Connected"], text=True, timeout=3)
            for line in out.splitlines():
                m = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.+)", line.strip())
                if m:
                    mac = m.group(1)
                    is_conn = mac in conn_out
                    paired.append({
                        "mac": mac,
                        "name": m.group(2).strip(),
                        "connected": is_conn
                    })
        except Exception as e:
            print(f"[BLUETOOTH] Paired error: {e}")
        return paired

    def connect_device(self, mac: str) -> Dict[str, Any]:
        """
        Pairs, trusts, and connects to a Bluetooth device (Odin implementation: pair -> trust -> connect).
        """
        if not IS_LINUX:
            return {"status": "ok", "message": f"Connected to {mac} (PC simulation)"}

        try:
            # 1. Pair
            pair_cmd = f"bluetoothctl pair {mac}"
            p_res = subprocess.run(pair_cmd, shell=True, capture_output=True, text=True, timeout=15)
            
            # 2. Trust
            trust_cmd = f"bluetoothctl trust {mac}"
            subprocess.run(trust_cmd, shell=True, capture_output=True, text=True, timeout=5)

            # 3. Connect (Audio Sink / Headset / Car Uconnect profile)
            conn_cmd = f"bluetoothctl connect {mac}"
            c_res = subprocess.run(conn_cmd, shell=True, capture_output=True, text=True, timeout=12)

            if c_res.returncode == 0 or "successful" in c_res.stdout.lower() or "successful" in p_res.stdout.lower():
                return {"status": "ok", "message": f"Successfully paired and connected to {mac}!"}
            else:
                out = (c_res.stdout or "") + (p_res.stdout or "") + (c_res.stderr or "")
                return {"status": "ok", "message": out.strip() or f"Dispatched connection to {mac}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def disconnect_device(self, mac: str) -> Dict[str, Any]:
        """Disconnects a Bluetooth device."""
        if not IS_LINUX:
            return {"status": "ok", "message": f"Disconnected {mac}"}
        try:
            subprocess.run(f"bluetoothctl disconnect {mac}", shell=True, timeout=5, capture_output=True)
            return {"status": "ok", "message": f"Disconnected {mac}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def remove_device(self, mac: str) -> Dict[str, Any]:
        """Untrusts and removes (forgets) a Bluetooth device."""
        if not IS_LINUX:
            return {"status": "ok", "message": f"Removed {mac}"}
        try:
            subprocess.run(f"bluetoothctl untrust {mac}", shell=True, timeout=4, capture_output=True)
            subprocess.run(f"bluetoothctl remove {mac}", shell=True, timeout=4, capture_output=True)
            return {"status": "ok", "message": f"Removed {mac}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def set_discoverable(self, enable: bool) -> Dict[str, Any]:
        """Toggles discoverable mode."""
        arg = "on" if enable else "off"
        if IS_LINUX:
            try:
                subprocess.run(f"bluetoothctl discoverable {arg}", shell=True, timeout=3, capture_output=True)
                subprocess.run(f"bluetoothctl pairable {arg}", shell=True, timeout=3, capture_output=True)
            except Exception:
                pass
        return {"status": "ok", "discoverable": enable}
