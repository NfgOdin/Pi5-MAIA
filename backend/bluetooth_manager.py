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
import threading
from typing import Dict, Any, List, Optional

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "bluetooth_saved.json")
IS_LINUX = platform.system().lower() == "linux"

class BluetoothManager:
    def __init__(self):
        self.config = self.load_config()
        if "auto_route_audio" not in self.config:
            self.config["auto_route_audio"] = True
            self.save_config()
        self._start_audio_monitor_thread()

    def _start_audio_monitor_thread(self):
        t = threading.Thread(target=self._audio_monitor_loop, daemon=True)
        t.start()

    def _audio_monitor_loop(self):
        while True:
            try:
                if self.config.get("auto_route_audio", True):
                    self.auto_route_audio()
            except Exception:
                pass
            time.sleep(4.0)

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
                time.sleep(1.2)
                self.auto_route_audio()
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

    def get_audio_devices(self) -> Dict[str, Any]:
        """
        Parses PipeWire / WirePlumber audio devices via `wpctl status`.
        Returns available Sinks, Sources, Bluetooth Device IDs, and the currently active default sink.
        """
        if not IS_LINUX:
            return {
                "sinks": [
                    {"id": 56, "name": "Built-in Audio Digital Stereo (HDMI)", "is_default": False, "volume": 1.40, "is_bluetooth": False},
                    {"id": 93, "name": "Uconnect", "is_default": True, "volume": 1.00, "is_bluetooth": True}
                ],
                "sources": [
                    {"id": 95, "name": "Uconnect", "is_default": False, "volume": 1.40, "is_bluetooth": True}
                ],
                "active_sink_id": 93,
                "bt_device_id": 84,
                "auto_route": self.config.get("auto_route_audio", True)
            }

        sinks = []
        sources = []
        active_sink_id = None
        active_source_id = None
        bt_device_id = None
        current_section = None

        env = os.environ.copy()
        env['XDG_RUNTIME_DIR'] = '/run/user/1000'

        try:
            res = subprocess.run(['wpctl', 'status'], capture_output=True, text=True, env=env, timeout=3)
            out = res.stdout
            for line in out.splitlines():
                clean = re.sub(r'^[\u2500-\u257F\s]+', '', line).strip()
                if 'Devices:' in clean:
                    current_section = 'devices'
                    continue
                elif 'Sinks:' in clean:
                    current_section = 'sinks'
                    continue
                elif 'Sources:' in clean:
                    current_section = 'sources'
                    continue
                elif 'Sink endpoints:' in clean or 'Filters:' in clean or 'Streams:' in clean or 'Video' in clean:
                    current_section = None
                    continue

                if current_section == 'devices':
                    m = re.search(r'(\d+)\.\s+(.+?)\s+\[bluez5\]', clean)
                    if m:
                        bt_device_id = int(m.group(1))
                elif current_section == 'sinks':
                    m = re.search(r'(\*?)\s*(\d+)\.\s+(.+?)\s+\[vol:\s*([\d\.]+)\]', clean)
                    if m:
                        is_def = bool(m.group(1))
                        s_id = int(m.group(2))
                        name = m.group(3).strip()
                        vol = float(m.group(4))
                        is_bt = 'uconnect' in name.lower() or 'bluez' in name.lower()
                        sinks.append({
                            'id': s_id,
                            'name': name,
                            'is_default': is_def,
                            'volume': vol,
                            'is_bluetooth': is_bt
                        })
                        if is_def:
                            active_sink_id = s_id
                elif current_section == 'sources':
                    m = re.search(r'(\*?)\s*(\d+)\.\s+(.+?)\s+\[vol:\s*([\d\.]+)\]', clean)
                    if m:
                        is_def = bool(m.group(1))
                        s_id = int(m.group(2))
                        name = m.group(3).strip()
                        vol = float(m.group(4))
                        is_bt = 'uconnect' in name.lower() or 'bluez' in name.lower()
                        sources.append({
                            'id': s_id,
                            'name': name,
                            'is_default': is_def,
                            'volume': vol,
                            'is_bluetooth': is_bt
                        })
                        if is_def:
                            active_source_id = s_id
        except Exception as e:
            print(f"[BLUETOOTH AUDIO] Error querying wpctl: {e}")

        return {
            "sinks": sinks,
            "sources": sources,
            "active_sink_id": active_sink_id,
            "active_source_id": active_source_id,
            "bt_device_id": bt_device_id,
            "auto_route": self.config.get("auto_route_audio", True)
        }

    def set_audio_sink(self, sink_id_or_type: Any) -> Dict[str, Any]:
        """Sets the active audio output sink (e.g. sink_id int, or 'bluetooth', 'hdmi')."""
        if not IS_LINUX:
            return {"status": "ok", "message": f"Set audio output to {sink_id_or_type} (PC simulation)"}

        env = os.environ.copy()
        env['XDG_RUNTIME_DIR'] = '/run/user/1000'

        devs = self.get_audio_devices()
        target_id = None
        is_bt_target = False

        if isinstance(sink_id_or_type, int) or (isinstance(sink_id_or_type, str) and str(sink_id_or_type).isdigit()):
            target_id = int(sink_id_or_type)
            for s in devs.get("sinks", []):
                if s["id"] == target_id and s["is_bluetooth"]:
                    is_bt_target = True
                    break
        elif str(sink_id_or_type).lower() in ("bluetooth", "uconnect", "car"):
            is_bt_target = True
            for s in devs.get("sinks", []):
                if s["is_bluetooth"]:
                    target_id = s["id"]
                    break
        elif str(sink_id_or_type).lower() in ("hdmi", "display", "builtin"):
            for s in devs.get("sinks", []):
                if not s["is_bluetooth"]:
                    target_id = s["id"]
                    break

        if target_id is not None:
            try:
                # If target is Bluetooth (Uconnect), ensure profile 131073 (A2DP High Fidelity Stereo) is locked
                bt_dev_id = devs.get("bt_device_id")
                if is_bt_target and bt_dev_id:
                    subprocess.run(['wpctl', 'set-profile', str(bt_dev_id), '131073'], env=env, timeout=3)

                subprocess.run(['wpctl', 'set-default', str(target_id)], env=env, timeout=3)
                subprocess.run(['wpctl', 'set-volume', str(target_id), '1.0'], env=env, timeout=3)
                return {"status": "ok", "sink_id": target_id, "message": f"Audio routed to sink {target_id}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "error", "message": f"Could not find sink matching '{sink_id_or_type}'"}

    def set_audio_source(self, source_id_or_type: Any) -> Dict[str, Any]:
        """Sets the active audio microphone input source via WirePlumber/wpctl."""
        if not IS_LINUX:
            return {"status": "ok", "message": f"Set audio input microphone to {source_id_or_type} (PC simulation)"}

        env = os.environ.copy()
        env['XDG_RUNTIME_DIR'] = '/run/user/1000'

        devs = self.get_audio_devices()
        target_id = None

        if isinstance(source_id_or_type, int) or (isinstance(source_id_or_type, str) and str(source_id_or_type).isdigit()):
            target_id = int(source_id_or_type)
        else:
            for s in devs.get("sources", []):
                if str(source_id_or_type).lower() in s["name"].lower():
                    target_id = s["id"]
                    break

        if target_id is not None:
            try:
                cmd = ['wpctl', 'set-default', str(target_id)]
                subprocess.run(cmd, env=env, timeout=2)
                print(f"[AUDIO ROUTING] Set default microphone source to wpctl ID: {target_id}")
                return {"status": "ok", "active_source_id": target_id}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "error", "message": f"Could not find source matching '{source_id_or_type}'"}


    def set_auto_route(self, enabled: bool) -> Dict[str, Any]:
        self.config["auto_route_audio"] = bool(enabled)
        self.save_config()
        if enabled:
            self.auto_route_audio()
        return {"status": "ok", "auto_route": self.config["auto_route_audio"]}

    def auto_route_audio(self) -> Dict[str, Any]:
        """
        Auto-switches audio output to Bluetooth (e.g. Uconnect) in pristine A2DP stereo if connected;
        otherwise routes to HDMI. Does NOT switch mic to Uconnect so Bluetooth is never degraded to 8kHz CVSD telephone mode.
        """
        devs = self.get_audio_devices()
        bt_sink = None
        hdmi_sink = None
        for s in devs.get("sinks", []):
            if s["is_bluetooth"]:
                bt_sink = s
            else:
                hdmi_sink = s

        bt_dev_id = devs.get("bt_device_id")
        env = os.environ.copy()
        env['XDG_RUNTIME_DIR'] = '/run/user/1000'

        if bt_sink:
            if not bt_sink.get("is_default"):
                print(f"[BLUETOOTH AUDIO] Auto-routing audio to Bluetooth car sink: {bt_sink['name']} (ID {bt_sink['id']})")
                if IS_LINUX:
                    try:
                        # Lock high fidelity A2DP profile
                        if bt_dev_id:
                            subprocess.run(['wpctl', 'set-profile', str(bt_dev_id), '131073'], env=env, timeout=3)
                        subprocess.run(['wpctl', 'set-default', str(bt_sink['id'])], env=env, timeout=3)
                        subprocess.run(['wpctl', 'set-volume', str(bt_sink['id']), '1.0'], env=env, timeout=3)
                    except Exception as e:
                        print(f"[BLUETOOTH AUDIO] Routing error: {e}")
            return {"status": "ok", "mode": "bluetooth", "sink": bt_sink}
        elif hdmi_sink:
            if not hdmi_sink.get("is_default"):
                print(f"[BLUETOOTH AUDIO] Bluetooth sink not found. Falling back to HDMI: {hdmi_sink['name']}")
                if IS_LINUX:
                    try:
                        subprocess.run(['wpctl', 'set-default', str(hdmi_sink['id'])], env=env, timeout=3)
                    except Exception:
                        pass
            return {"status": "ok", "mode": "hdmi", "sink": hdmi_sink}

        return {"status": "ok", "mode": "none"}
