"""

wifi_manager.py - Automotive Wi-Fi & Hotspot Manager for Dodge Dart CarPi5

Supports Raspberry Pi 5 (NetworkManager nmcli) and Windows (netsh) dev host.

Provides scanning, connection, auto-reconnect / always-on mode, and saved network management.

"""



import os

import re

import json

import time

import platform

import subprocess

from typing import Dict, Any, List, Optional



CONFIG_FILE = os.path.join(os.path.dirname(__file__), "wifi_saved.json")

IS_LINUX = platform.system().lower() == "linux"



class WifiManager:

    def __init__(self):

        self.config = self.load_config()



    def load_config(self) -> Dict[str, Any]:

        default_config = {

            "always_on": True,

            "saved_networks": [

                {

                    "ssid": "CarPi-Hotspot",

                    "auto_connect": True,

                    "last_connected": "Primary Phone Hotspot",

                    "security": "WPA2-Personal"

                }

            ]

        }

        if os.path.exists(CONFIG_FILE):

            try:

                with open(CONFIG_FILE, "r") as f:

                    data = json.load(f)

                    default_config.update(data)

            except Exception as e:

                print(f"[WIFI] Error loading wifi_saved.json: {e}")

        return default_config



    def save_config(self):

        try:

            with open(CONFIG_FILE, "w") as f:

                json.dump(self.config, f, indent=2)

        except Exception as e:

            print(f"[WIFI] Error saving wifi_saved.json: {e}")



    def get_status(self) -> Dict[str, Any]:

        """Returns the current Wi-Fi interface status, connected SSID, and IP address."""

        connected_ssid = None

        signal_percent = 0

        band = "5 GHz"

        ip_addr = "127.0.0.1"



        if IS_LINUX:

            try:

                # nmcli active connection check

                out = subprocess.check_output(

                    ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],

                    text=True, timeout=3

                )

                for line in out.splitlines():

                    parts = line.split(":")

                    if len(parts) >= 2 and "wireless" in parts[1]:

                        connected_ssid = parts[0]

                        break



                # Get IP and signal

                if connected_ssid:

                    try:

                        dev_out = subprocess.check_output(

                            ["nmcli", "-t", "-f", "IN-USE,SIGNAL,SSID", "dev", "wifi"],

                            text=True, timeout=3

                        )

                        for dline in dev_out.splitlines():

                            if dline.startswith("*"):

                                dparts = dline.split(":")

                                if len(dparts) >= 2 and dparts[1].isdigit():

                                    signal_percent = int(dparts[1])

                                    break

                    except Exception:

                        signal_percent = 85



                    # Use hostname -I for reliable in-car IP

                    try:

                        ip_out = subprocess.check_output(["hostname", "-I"], text=True, timeout=2).strip()

                        if ip_out:

                            ip_addr = ip_out.split()[0]

                    except Exception:

                        pass

            except Exception as e:

                pass

        else:

            # Windows fallback using netsh

            try:

                out = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], text=True, timeout=3)

                m_state = re.search(r"State\s*:\s*(\w+)", out)

                if m_state and m_state.group(1).lower() == "connected":

                    m_ssid = re.search(r"SSID\s*:\s*([^\r\n]+)", out)

                    m_sig = re.search(r"Signal\s*:\s*(\d+)%", out)

                    m_band = re.search(r"Band\s*:\s*([^\r\n]+)", out)

                    if m_ssid:

                        connected_ssid = m_ssid.group(1).strip()

                    if m_sig:

                        signal_percent = int(m_sig.group(1))

                    if m_band:

                        band = m_band.group(1).strip()

                    ip_addr = "192.168.1.105"

            except Exception:

                pass



        saved_ssids = [n["ssid"] for n in self.config.get("saved_networks", [])]



        return {

            "is_enabled": True,

            "connected": connected_ssid is not None,

            "ssid": connected_ssid or "Disconnected",

            "signal_percent": signal_percent if connected_ssid else 0,

            "band": band,

            "ip_address": ip_addr if connected_ssid else "No IP Assigned",

            "always_on": self.config.get("always_on", True),

            "total_saved": len(saved_ssids),

            "is_saved": connected_ssid in saved_ssids if connected_ssid else False

        }



    def scan_networks(self) -> List[Dict[str, Any]]:

        """Scans for visible Wi-Fi access points and phone hotspots."""

        networks = []

        seen_ssids = set()

        status = self.get_status()

        current_ssid = status.get("ssid") if status.get("connected") else None

        saved_dict = {n["ssid"]: n for n in self.config.get("saved_networks", [])}



        if IS_LINUX:

            try:

                # Trigger a scan

                subprocess.run(["nmcli", "dev", "wifi", "rescan"], timeout=4, capture_output=True)

                out = subprocess.check_output(

                    ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "dev", "wifi", "list"],

                    text=True, timeout=4

                )

                for line in out.splitlines():

                    parts = line.split(":")

                    if len(parts) >= 3 and parts[0].strip():

                        ssid = parts[0].strip()

                        if ssid in seen_ssids:

                            continue

                        seen_ssids.add(ssid)

                        sig = int(parts[1]) if parts[1].isdigit() else 50

                        sec = parts[2].strip() or "Open"

                        in_use = (len(parts) >= 4 and parts[3].strip() == "*") or (ssid == current_ssid)

                        networks.append({

                            "ssid": ssid,

                            "signal": sig,

                            "security": sec,

                            "connected": in_use,

                            "is_saved": ssid in saved_dict,

                            "auto_connect": saved_dict.get(ssid, {}).get("auto_connect", False)

                        })

            except Exception as e:

                print(f"[WIFI] Linux nmcli scan error: {e}")



        if not networks and not IS_LINUX:

            # Windows netsh scan

            try:

                out = subprocess.check_output(["netsh", "wlan", "show", "networks"], text=True, timeout=4)

                current_block_ssid = None

                for line in out.splitlines():

                    m_ssid = re.search(r"SSID\s+\d+\s+:\s*(.*)", line)

                    if m_ssid:

                        current_block_ssid = m_ssid.group(1).strip()

                    m_auth = re.search(r"Authentication\s+:\s*(.*)", line)

                    if m_auth and current_block_ssid:

                        if current_block_ssid not in seen_ssids and current_block_ssid:

                            seen_ssids.add(current_block_ssid)

                            is_conn = (current_block_ssid == current_ssid)

                            networks.append({

                                "ssid": current_block_ssid,

                                "signal": 85 if is_conn else 70,

                                "security": m_auth.group(1).strip(),

                                "connected": is_conn,

                                "is_saved": current_block_ssid in saved_dict,

                                "auto_connect": saved_dict.get(current_block_ssid, {}).get("auto_connect", False)

                            })

                        current_block_ssid = None

            except Exception as e:

                print(f"[WIFI] Windows netsh scan error: {e}")



        # Add any saved networks (like phone hotspot or garage) if not in range so the user can manage them

        for s_ssid, s_info in saved_dict.items():

            if s_ssid not in seen_ssids:

                networks.append({

                    "ssid": s_ssid,

                    "signal": 0,

                    "security": s_info.get("security", "WPA2-Personal"),

                    "connected": False,

                    "is_saved": True,

                    "auto_connect": s_info.get("auto_connect", True),

                    "out_of_range": True

                })



        # Sort: connected first, then in-range signal, then saved

        networks.sort(key=lambda x: (x.get("connected", False), x.get("signal", 0)), reverse=True)

        return networks



    def connect(self, ssid: str, password: Optional[str] = None, auto_connect: bool = True) -> Dict[str, Any]:

        """Connects to a Wi-Fi network and records it in remembered networks."""

        ssid = ssid.strip()

        if not ssid:

            return {"error": "Invalid SSID"}



        print(f"[WIFI] Connecting to '{ssid}' (Auto-connect={auto_connect})...")



        success = True

        err_msg = ""



        if IS_LINUX:

            try:

                # Always remove any stale or corrupted connection profile for this SSID first so NetworkManager creates a clean profile

                subprocess.run(["nmcli", "connection", "delete", ssid], capture_output=True, text=True, timeout=5)



                cmd = ["nmcli", "dev", "wifi", "connect", ssid]

                if password:

                    cmd.extend(["password", password])

                res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)

                if res.returncode != 0:

                    success = False

                    err_raw = (res.stderr or res.stdout or "").strip()

                    # Clean up failed profile so it doesn't leave broken state behind

                    subprocess.run(["nmcli", "connection", "delete", ssid], capture_output=True, text=True, timeout=5)

                    if "Secrets were required" in err_raw or "psk" in err_raw.lower():

                        err_msg = f"Failed connecting to '{ssid}': Incorrect Wi-Fi password."

                    else:

                        err_msg = f"Failed connecting to '{ssid}': {err_raw}"

                else:

                    if auto_connect:

                        subprocess.run(["nmcli", "connection", "modify", ssid, "connection.autoconnect", "yes"], timeout=3)

            except Exception as e:

                success = False

                err_msg = str(e)

        else:

            # On Windows dev machine, simulate connection and save credentials

            time.sleep(0.5)

            success = True



        if success:

            # Add or update in saved networks

            saved = self.config.setdefault("saved_networks", [])

            existing = next((item for item in saved if item["ssid"] == ssid), None)

            if existing:

                existing["auto_connect"] = auto_connect

                existing["last_connected"] = time.strftime("%Y-%m-%d %I:%M %p")

            else:

                saved.append({

                    "ssid": ssid,

                    "auto_connect": auto_connect,

                    "last_connected": time.strftime("%Y-%m-%d %I:%M %p"),

                    "security": "WPA2-Personal" if password else "Open"

                })

            self.save_config()

            return {"status": "ok", "ssid": ssid, "message": f"Successfully connected to {ssid}"}

        else:

            return {"error": f"Failed connecting to {ssid}: {err_msg}"}



    def get_saved(self) -> List[Dict[str, Any]]:

        """Returns the list of remembered networks and hotspots."""

        return self.config.get("saved_networks", [])



    def forget(self, ssid: str) -> Dict[str, Any]:

        """Forgets / deletes a saved network profile."""

        ssid = ssid.strip()

        if IS_LINUX:

            try:

                subprocess.run(["nmcli", "connection", "delete", ssid], capture_output=True, timeout=5)

            except Exception:

                pass

        else:

            try:

                subprocess.run(["netsh", "wlan", "delete", "profile", f"name={ssid}"], capture_output=True, timeout=5)

            except Exception:

                pass



        saved = self.config.get("saved_networks", [])

        self.config["saved_networks"] = [n for n in saved if n["ssid"] != ssid]

        self.save_config()

        return {"status": "ok", "ssid": ssid, "message": f"Forgot network {ssid}"}



    def clear_all(self) -> Dict[str, Any]:

        """Clears all remembered networks and hotspots."""

        saved = self.config.get("saved_networks", [])

        for n in saved:

            ssid = n.get("ssid", "")

            if IS_LINUX:

                try:

                    subprocess.run(["nmcli", "connection", "delete", ssid], capture_output=True, timeout=3)

                except Exception:

                    pass

            else:

                try:

                    subprocess.run(["netsh", "wlan", "delete", "profile", f"name={ssid}"], capture_output=True, timeout=3)

                except Exception:

                    pass



        self.config["saved_networks"] = []

        self.save_config()

        return {"status": "ok", "message": "All saved networks cleared."}



    def set_always_on(self, enabled: bool) -> Dict[str, Any]:

        """Toggles Wi-Fi Always-On / Auto-Connect mode."""

        self.config["always_on"] = bool(enabled)

        self.save_config()

        if IS_LINUX and enabled:

            try:

                subprocess.run(["nmcli", "radio", "wifi", "on"], capture_output=True, timeout=3)

            except Exception:

                pass

        return {"status": "ok", "always_on": self.config["always_on"]}

