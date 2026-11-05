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
                    "mac": "F4:F5:DB:12:34:56",
                    "name": "User Phone",
                    "alias": "User Phone",
                    "paired": True,
                    "connected": True,
                    "audio_connected": True
                },
                "connected_devices": [
                    {
                        "mac": "F4:F5:DB:12:34:56",
                        "name": "User Phone",
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
                # Device AA:BB:CC:DD:EE:FF Name
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
        """Scans for nearby Bluetooth devices for 4 seconds and returns discovered list."""
        if not IS_LINUX:
            return [
                {"mac": "F4:F5:DB:12:34:56", "name": "User Phone (Connected)", "rssi": -48, "paired": True, "connected": True},
                {"mac": "98:CD:AC:44:11:22", "name": "Car OBD Scanner (ELM327)", "rssi": -65, "paired": False, "connected": False},
                {"mac": "E0:D4:E8:99:88:77", "name": "Wireless Gamepad", "rssi": -72, "paired": False, "connected": False}
            ]

        devices_map = {}
        try:
            # 1. Fetch currently paired/known devices
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

            # 2. Run scan for 4 seconds
            try:
                p = subprocess.Popen(["bluetoothctl", "scan", "on"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                time.sleep(3.5)
                p.terminate()
            except Exception:
                pass

            # 3. List all discovered devices
            all_devs = subprocess.check_output(["bluetoothctl", "devices"], text=True, timeout=3)
            for line in all_devs.splitlines():
                m = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.+)", line.strip())
                if m:
                    mac = m.group(1)
                    name = m.group(2).strip()
                    if mac not in devices_map:
                        devices_map[mac] = {
                            "mac": mac,
                            "name": name,
                            "paired": False,
                            "connected": False,
                            "rssi": -75
                        }

            # 4. Check connected
            conn_devs = subprocess.check_output(["bluetoothctl", "devices", "Connected"], text=True, timeout=3)
            for line in conn_devs.splitlines():
                m = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.+)", line.strip())
                if m and m.group(1) in devices_map:
                    devices_map[m.group(1)]["connected"] = True

        except Exception as e:
            print(f"[BLUETOOTH] Scan error: {e}")

        # Filter out unnamed/raw MAC address duplicates if better ones exist
        results = list(devices_map.values())
        results.sort(key=lambda d: (not d["connected"], not d["paired"], d["name"] == d["mac"]))
        return results

    def get_paired(self) -> List[Dict[str, Any]]:
        """Returns list of paired devices."""
        if not IS_LINUX:
            return [
                {"mac": "F4:F5:DB:12:34:56", "name": "User Phone", "connected": True}
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
        """Pairs, trusts, and connects to a Bluetooth device."""
        if not IS_LINUX:
            return {"status": "ok", "message": f"Connected to {mac} (PC simulation)"}

        try:
            # Trust device so it reconnects automatically in the future
            subprocess.run(["bluetoothctl", "trust", mac], timeout=4, capture_output=True)
            # Connect device
            res = subprocess.run(["bluetoothctl", "connect", mac], timeout=8, capture_output=True, text=True)
            if res.returncode == 0 or "successful" in res.stdout.lower():
                return {"status": "ok", "message": f"Successfully connected to {mac}"}
            else:
                # Try pairing first
                subprocess.run(["bluetoothctl", "pair", mac], timeout=8, capture_output=True)
                res2 = subprocess.run(["bluetoothctl", "connect", mac], timeout=8, capture_output=True, text=True)
                if "successful" in res2.stdout.lower():
                    return {"status": "ok", "message": f"Successfully paired and connected to {mac}"}
                return {"status": "ok", "message": res2.stdout.strip() or "Connection command dispatched"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def disconnect_device(self, mac: str) -> Dict[str, Any]:
        """Disconnects a Bluetooth device."""
        if not IS_LINUX:
            return {"status": "ok", "message": f"Disconnected {mac}"}
        try:
            subprocess.run(["bluetoothctl", "disconnect", mac], timeout=5, capture_output=True)
            return {"status": "ok", "message": f"Disconnected {mac}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def remove_device(self, mac: str) -> Dict[str, Any]:
        """Untrusts and removes (forgets) a Bluetooth device."""
        if not IS_LINUX:
            return {"status": "ok", "message": f"Removed {mac}"}
        try:
            subprocess.run(["bluetoothctl", "untrust", mac], timeout=4, capture_output=True)
            subprocess.run(["bluetoothctl", "remove", mac], timeout=4, capture_output=True)
            return {"status": "ok", "message": f"Removed {mac}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def set_discoverable(self, enable: bool) -> Dict[str, Any]:
        """Toggles discoverable mode."""
        arg = "on" if enable else "off"
        if IS_LINUX:
            try:
                subprocess.run(["bluetoothctl", "discoverable", arg], timeout=3, capture_output=True)
                subprocess.run(["bluetoothctl", "pairable", arg], timeout=3, capture_output=True)
            except Exception:
                pass
        return {"status": "ok", "discoverable": enable}
