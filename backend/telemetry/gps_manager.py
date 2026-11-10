"""
gps_manager.py - Real-time NMEA GPS Manager for CarPi5
Reads hardware UART (/dev/ttyAMA10 or /dev/serial0) at 9600 baud.
Parses GGA, RMC, VTG, and GSV sentences.
Calculates Dragy performance metrics (0-60, 60ft, 1/8mi, 1/4mi) and elevation grade.
Thread-safe.
"""

import sys
import os
import subprocess
import time
import math
import threading
from typing import Dict, Any, Optional

try:
    import serial
except ImportError:
    serial = None


class GpsManager:
    def __init__(self, port: str = "/dev/ttyAMA10", baud: int = 9600):
        self.port = port
        self.baud = baud
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        
        self.data: Dict[str, Any] = {
            "connected": False,
            "fix": False,
            "fix_quality": 0,
            "sats": 0,
            "sats_in_view": 0,
            "lat": 0.0,
            "lon": 0.0,
            "speed_mph": 0.0,
            "speed_knots": 0.0,
            "heading": 0.0,
            "heading_cardinal": "N",
            "altitude_m": 0.0,
            "altitude_ft": 0.0,
            "road_grade_pct": 0.0,
            "last_update": 0.0
        }
        
        # Dragy / Performance Timer Engine
        self._last_time_sync = 0.0
        self.dragy: Dict[str, Any] = {
            "state": "IDLE",  # IDLE, STAGED, ACCELERATING, FINISHED
            "time_0_60": None,
            "time_60ft": None,
            "time_1_8mi": None,
            "speed_1_8mi": None,
            "time_1_4mi": None,
            "speed_1_4mi": None,
            "current_run_time": 0.0,
            "peak_g": 0.0,
            "history": []
        }
        
        self._last_alt = 0.0
        self._last_dist = 0.0
        self._run_start_time = 0.0
        self._run_dist_feet = 0.0
        self._last_speed_mph = 0.0
        self._last_speed_time = 0.0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, name="GpsManagerThread", daemon=True)
        self.thread.start()
        print(f"[GPS] Background manager started on {self.port} @ {self.baud} baud.")

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _get_cardinal(self, heading: float) -> str:
        dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        idx = int((heading + 22.5) / 45.0) % 8
        return dirs[idx]

    def _parse_coord(self, raw: str, direction: str, is_lon: bool = False) -> Optional[float]:
        if not raw or not direction:
            return None
        try:
            deg_digits = 3 if is_lon else 2
            deg = float(raw[:deg_digits])
            minutes = float(raw[deg_digits:])
            coord = round(deg + (minutes / 60.0), 6)
            if direction in ['S', 'W']:
                coord = -coord
            return coord
        except Exception:
            return None

    def _update_dragy(self, speed_mph: float, now: float):
        dt = now - self._last_speed_time if self._last_speed_time > 0 else 0.1
        if dt <= 0:
            dt = 0.1
        
        # Approximate feet traveled in dt: (mph * 5280 / 3600) * dt = mph * 1.46667 * dt
        feet_step = ((speed_mph + self._last_speed_mph) / 2.0) * 1.46667 * dt
        
        # Calculate instantaneous G-force: a = dv / dt (in mph/s). 1G ~= 21.937 mph/s
        dv_dt = (speed_mph - self._last_speed_mph) / dt if dt > 0 else 0.0
        inst_g = max(0.0, round(dv_dt / 21.937, 2))
        
        self._last_speed_mph = speed_mph
        self._last_speed_time = now

        if self.dragy["state"] in ["IDLE", "FINISHED"]:
            if speed_mph < 0.8:
                self.dragy["state"] = "STAGED"
                self.dragy["current_run_time"] = 0.0
                self._run_dist_feet = 0.0
                self.dragy["peak_g"] = 0.0
        elif self.dragy["state"] == "STAGED":
            if speed_mph >= 1.0:
                self.dragy["state"] = "ACCELERATING"
                self._run_start_time = now
                self._run_dist_feet = 0.0
                self.dragy["time_0_60"] = None
                self.dragy["time_60ft"] = None
                self.dragy["time_1_8mi"] = None
                self.dragy["speed_1_8mi"] = None
                self.dragy["time_1_4mi"] = None
                self.dragy["speed_1_4mi"] = None
                self.dragy["peak_g"] = inst_g
        elif self.dragy["state"] == "ACCELERATING":
            elapsed = round(now - self._run_start_time, 2)
            self.dragy["current_run_time"] = elapsed
            self._run_dist_feet += feet_step
            self.dragy["peak_g"] = max(self.dragy["peak_g"], inst_g)

            # 60ft
            if self._run_dist_feet >= 60.0 and self.dragy["time_60ft"] is None:
                self.dragy["time_60ft"] = elapsed

            # 0-60 MPH
            if speed_mph >= 60.0 and self.dragy["time_0_60"] is None:
                self.dragy["time_0_60"] = elapsed

            # 1/8 Mile = 660 ft
            if self._run_dist_feet >= 660.0 and self.dragy["time_1_8mi"] is None:
                self.dragy["time_1_8mi"] = elapsed
                self.dragy["speed_1_8mi"] = round(speed_mph, 1)

            # 1/4 Mile = 1320 ft
            if self._run_dist_feet >= 1320.0 and self.dragy["time_1_4mi"] is None:
                self.dragy["time_1_4mi"] = elapsed
                self.dragy["speed_1_4mi"] = round(speed_mph, 1)
                self.dragy["state"] = "FINISHED"
                run_record = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "0_60": self.dragy["time_0_60"],
                    "60ft": self.dragy["time_60ft"],
                    "1_8mi_time": self.dragy["time_1_8mi"],
                    "1_8mi_mph": self.dragy["speed_1_8mi"],
                    "1_4mi_time": self.dragy["time_1_4mi"],
                    "1_4mi_mph": self.dragy["speed_1_4mi"],
                    "peak_g": self.dragy["peak_g"]
                }
                self.dragy["history"].insert(0, run_record)
                if len(self.dragy["history"]) > 10:
                    self.dragy["history"].pop()

            # Abort if stopped
            if speed_mph < 0.5 and elapsed > 2.0:
                self.dragy["state"] = "STAGED"

    @staticmethod
    def _safe_float(val: str, default: float = 0.0) -> float:
        if not val:
            return default
        try:
            f = float(val)
            return f if math.isfinite(f) else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_int(val: str, default: int = 0) -> int:
        if not val:
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    def _reset_disconnected_state(self):
        """Reset GPS telemetry to pure resting hardware state when disconnected (AGENTS.md Rule 2)."""
        self.data["connected"] = False
        self.data["fix"] = False
        self.data["fix_quality"] = 0
        self.data["sats"] = 0
        self.data["sats_in_view"] = 0
        self.data["speed_mph"] = 0.0
        self.data["speed_knots"] = 0.0
        self.data["road_grade_pct"] = 0.0

    def _read_loop(self):
        while self.running:
            if not serial:
                with self.lock:
                    self._reset_disconnected_state()
                time.sleep(2.0)
                continue
            ser = None
            try:
                ser = serial.Serial(self.port, self.baud, timeout=1.0)
                print(f"[GPS] Opened UART port: {self.port} (awaiting valid NMEA stream)")
                last_nmea_rx = time.time()

                while self.running:
                    line_bytes = ser.readline()
                    now = time.time()
                    if not line_bytes:
                        if now - last_nmea_rx > 5.0:
                            with self.lock:
                                self._reset_disconnected_state()
                        continue
                    line = line_bytes.decode('latin1', errors='replace').strip()
                    if not line.startswith('$'):
                        if now - last_nmea_rx > 5.0:
                            with self.lock:
                                self._reset_disconnected_state()
                        continue

                    parts = line.split('*')[0].split(',')
                    tag = parts[0][1:]
                    last_nmea_rx = now

                    with self.lock:
                        self.data["connected"] = True
                        self.data["last_update"] = now

                        # GGA
                        if tag.endswith('GGA') and len(parts) > 9:
                            lat = self._parse_coord(parts[2], parts[3], False)
                            lon = self._parse_coord(parts[4], parts[5], True)
                            fix_q = self._safe_int(parts[6], 0)
                            sats = self._safe_int(parts[7], 0)
                            alt_m = self._safe_float(parts[9], 0.0)

                            if fix_q > 0 and self._last_alt != 0.0:
                                horiz_m = (self._run_dist_feet - self._last_dist) * 0.3048
                                if horiz_m >= 5.0:
                                    grade = ((alt_m - self._last_alt) / horiz_m) * 100.0
                                    self.data["road_grade_pct"] = round(max(-35.0, min(35.0, grade)), 1)
                                    self._last_alt = alt_m
                                    self._last_dist = self._run_dist_feet
                            elif fix_q > 0 and self._last_alt == 0.0:
                                self._last_alt = alt_m
                                self._last_dist = self._run_dist_feet

                            self.data["fix"] = fix_q > 0
                            self.data["fix_quality"] = fix_q
                            self.data["sats"] = sats
                            self.data["altitude_m"] = round(alt_m, 1)
                            self.data["altitude_ft"] = round(alt_m * 3.28084, 1)
                            if lat is not None:
                                self.data["lat"] = lat
                            if lon is not None:
                                self.data["lon"] = lon

                        # ZDA - Time & Date: $GNZDA,hhmmss.ss,dd,mm,yyyy,xx,xx*hh
                        elif tag.endswith('ZDA') and len(parts) > 4:
                            utc_time = parts[1]
                            day = parts[2]
                            month = parts[3]
                            year = parts[4]
                            if utc_time and day and month and year and (now - self._last_time_sync > 300.0):
                                try:
                                    # Format: YYYY-MM-DD HH:MM:SS
                                    hh = utc_time[:2]
                                    mm = utc_time[2:4]
                                    ss = utc_time[4:6]
                                    dt_str = f"{year}-{month}-{day} {hh}:{mm}:{ss}"
                                    if sys.platform.startswith("linux"):
                                        subprocess.run(["sudo", "date", "-u", "-s", dt_str], timeout=2)
                                        print(f"[GPS] Synchronized system clock to satellite UTC: {dt_str}")
                                        self._last_time_sync = now
                                except Exception:
                                    pass

                        elif tag.endswith('RMC') and len(parts) > 8:
                            status = parts[2]
                            lat = self._parse_coord(parts[3], parts[4], False)
                            lon = self._parse_coord(parts[5], parts[6], True)
                            knots = self._safe_float(parts[7], 0.0)
                            heading = self._safe_float(parts[8], 0.0)
                            speed_mph = round(knots * 1.15078, 1) if status == 'A' else 0.0

                            self.data["fix"] = status == 'A'
                            self.data["speed_knots"] = knots if status == 'A' else 0.0
                            self.data["speed_mph"] = speed_mph
                            self.data["heading"] = round(heading, 1)
                            self.data["heading_cardinal"] = self._get_cardinal(heading)
                            if lat is not None:
                                self.data["lat"] = lat
                            if lon is not None:
                                self.data["lon"] = lon

                            self._update_dragy(speed_mph, now)

                        # VTG
                        elif tag.endswith('VTG') and len(parts) > 7:
                            kph = self._safe_float(parts[7], 0.0)
                            self.data["speed_mph"] = round(kph * 0.621371, 1) if self.data["fix"] else 0.0
                            self._update_dragy(self.data["speed_mph"], now)

                        # GSV
                        elif tag.endswith('GSV') and len(parts) > 3:
                            sats_view = self._safe_int(parts[3], 0)
                            self.data["sats_in_view"] = max(self.data["sats_in_view"], sats_view)

            except Exception:
                with self.lock:
                    self._reset_disconnected_state()
                time.sleep(2.0)
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass

    def get_telemetry(self) -> Dict[str, Any]:
        with self.lock:
            return {
                **self.data,
                "dragy": dict(self.dragy)
            }


if __name__ == "__main__":
    gm = GpsManager(port="/dev/ttyAMA10", baud=9600)
    gm.start()
    try:
        for _ in range(5):
            time.sleep(1)
            print("GPS Telemetry:", gm.get_telemetry())
    finally:
        gm.stop()
