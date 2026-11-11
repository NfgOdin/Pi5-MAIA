"""
lap_timer.py - Canyon Run & Track Day Sector Lap Timer for CarPi5
Provides millisecond-precise sector split timing, delta tracking, and in-character daughter coaching.
Curated routes:
- Pinal Mountain Scenic Byway (Globe, AZ - 3 sectors)
- Salt River Canyon Pass (US-60 - 4 sectors)
- Apache Trail / AZ-188 Roosevelt Lake Canyon (3 sectors)
- Wild Horse Pass / Firebird Road Course (3 sectors)
- Arizona Motorsports Park (AMP - 3 sectors)
"""

import math
import time
from typing import Dict, Any, List, Optional, Tuple

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

TRACK_PROFILES: Dict[str, Dict[str, Any]] = {
    "pinal_pass": {
        "id": "pinal_pass",
        "name": "Pinal Mountain Scenic Byway",
        "region": "Globe, AZ",
        "description": "Twisting pine forest elevation climb from Russell Rd to Pinal Peak",
        "distance_miles": 8.4,
        "gates": [
            {"name": "Start Line (Canyon Base)", "lat": 33.3800, "lon": -110.7900, "radius_m": 45.0},
            {"name": "Sector 1 (Mid-Ridge Switchbacks)", "lat": 33.3500, "lon": -110.8100, "radius_m": 45.0},
            {"name": "Sector 2 (Ponderosa Pine S-Turns)", "lat": 33.3200, "lon": -110.8300, "radius_m": 45.0},
            {"name": "Finish (Upper Pinal Summit)", "lat": 33.2800, "lon": -110.8800, "radius_m": 45.0}
        ],
        "default_par_lap_s": 420.0
    },
    "salt_river": {
        "id": "salt_river",
        "name": "Salt River Canyon Pass (US-60)",
        "region": "Gila / Navajo County, AZ",
        "description": "High-speed sweeping canyon descent to the Salt River Bridge",
        "distance_miles": 12.2,
        "gates": [
            {"name": "Start (Upper Rest Stop)", "lat": 33.4100, "lon": -110.7500, "radius_m": 50.0},
            {"name": "Sector 1 (North Rim Descent)", "lat": 33.4350, "lon": -110.7000, "radius_m": 50.0},
            {"name": "Sector 2 (River Bridge Apex)", "lat": 33.4800, "lon": -110.6000, "radius_m": 50.0},
            {"name": "Finish (South Climb Lookout)", "lat": 33.5500, "lon": -110.5200, "radius_m": 50.0}
        ],
        "default_par_lap_s": 580.0
    },
    "roosevelt": {
        "id": "roosevelt",
        "name": "Apache Trail / AZ-188 Roosevelt Pass",
        "region": "Roosevelt Lake, AZ",
        "description": "Scenic lake basin canyon twisties",
        "distance_miles": 9.5,
        "gates": [
            {"name": "Start (Dam Overlook)", "lat": 33.4050, "lon": -110.8250, "radius_m": 45.0},
            {"name": "Sector 1 (Lake Ridge Sweep)", "lat": 33.4600, "lon": -110.9000, "radius_m": 45.0},
            {"name": "Finish (Windy Point)", "lat": 33.5200, "lon": -110.9800, "radius_m": 45.0}
        ],
        "default_par_lap_s": 460.0
    },
    "firebird": {
        "id": "firebird",
        "name": "Wild Horse Pass / Firebird Road Course",
        "region": "Chandler, AZ",
        "description": "Technical 1.6-mile road course with high-speed chicane and hairpin",
        "distance_miles": 1.6,
        "gates": [
            {"name": "Start / Finish Straight", "lat": 33.2650, "lon": -111.9680, "radius_m": 30.0},
            {"name": "Sector 1 (Infield Esses)", "lat": 33.2680, "lon": -111.9720, "radius_m": 30.0},
            {"name": "Sector 2 (Carousel Hairpin)", "lat": 33.2620, "lon": -111.9740, "radius_m": 30.0},
            {"name": "Start / Finish Line", "lat": 33.2650, "lon": -111.9680, "radius_m": 30.0}
        ],
        "default_par_lap_s": 88.5
    }
}

class CanyonLapTimer:
    def __init__(self, track_id: str = "pinal_pass"):
        self.track_id = track_id
        self.profile = TRACK_PROFILES.get(track_id, TRACK_PROFILES["pinal_pass"])
        self.state = "IDLE"  # IDLE, ARMED, RUNNING, FINISHED
        self.lap_start_time = 0.0
        self.current_sector_idx = 0
        self.sector_split_times: List[float] = []
        self.sector_deltas: List[float] = []
        self.sector_top_speeds: List[float] = []
        self.sector_max_lat_g: List[float] = []

        self.current_lap_s = 0.0
        self.best_lap_s: Optional[float] = None
        self.best_sector_splits: List[float] = []

        self.last_gate_pass_ts = 0.0
        self.audio_player = None

    def set_audio_player(self, player):
        self.audio_player = player

    def set_track(self, track_id: str) -> bool:
        if track_id in TRACK_PROFILES:
            self.track_id = track_id
            self.profile = TRACK_PROFILES[track_id]
            self.reset()
            return True
        return False

    def get_tracks(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": k,
                "name": v["name"],
                "region": v["region"],
                "distance_miles": v["distance_miles"],
                "sectors": len(v["gates"]) - 1
            }
            for k, v in TRACK_PROFILES.items()
        ]

    def arm(self):
        self.state = "ARMED"
        self.current_sector_idx = 0
        self.sector_split_times = []
        self.sector_deltas = []
        self.sector_top_speeds = []
        self.sector_max_lat_g = []
        self.current_lap_s = 0.0

    def start_manual(self):
        self.state = "RUNNING"
        self.lap_start_time = time.time()
        self.current_sector_idx = 0
        self.sector_split_times = []
        self.sector_deltas = []
        self.sector_top_speeds = [0.0]
        self.sector_max_lat_g = [0.0]

    def stop(self):
        self.state = "FINISHED"

    def reset(self):
        self.state = "IDLE"
        self.lap_start_time = 0.0
        self.current_sector_idx = 0
        self.sector_split_times = []
        self.sector_deltas = []
        self.sector_top_speeds = []
        self.sector_max_lat_g = []
        self.current_lap_s = 0.0

    def step(self, lat: float, lon: float, speed_mph: float, lat_g: float) -> Dict[str, Any]:
        now = time.time()
        gates = self.profile["gates"]

        if self.state == "RUNNING":
            self.current_lap_s = round(now - self.lap_start_time, 2)
            # Track peak speed and peak lateral G in current active sector
            while len(self.sector_top_speeds) <= self.current_sector_idx:
                self.sector_top_speeds.append(0.0)
            while len(self.sector_max_lat_g) <= self.current_sector_idx:
                self.sector_max_lat_g.append(0.0)

            if speed_mph > self.sector_top_speeds[self.current_sector_idx]:
                self.sector_top_speeds[self.current_sector_idx] = round(speed_mph, 1)
            if abs(lat_g) > self.sector_max_lat_g[self.current_sector_idx]:
                self.sector_max_lat_g[self.current_sector_idx] = round(abs(lat_g), 2)

        # Evaluate gate triggers
        if self.state in ("ARMED", "RUNNING") and (now - self.last_gate_pass_ts > 10.0):
            target_gate_idx = 0 if self.state == "ARMED" else self.current_sector_idx + 1
            if target_gate_idx < len(gates):
                gate = gates[target_gate_idx]
                dist_m = haversine_m(lat, lon, gate["lat"], gate["lon"])

                if dist_m <= gate["radius_m"]:
                    self.last_gate_pass_ts = now
                    if self.state == "ARMED":
                        # Cross start gate!
                        self.state = "RUNNING"
                        self.lap_start_time = now
                        self.current_sector_idx = 0
                        self.sector_top_speeds = [speed_mph]
                        self.sector_max_lat_g = [abs(lat_g)]
                        self._speak(f"Timer started! Green flag on {self.profile['name']}!")
                    else:
                        # Sector split or Finish!
                        split_s = round(now - self.lap_start_time, 2)
                        self.sector_split_times.append(split_s)

                        # Delta against best lap
                        best_split = None
                        if self.best_sector_splits and target_gate_idx - 1 < len(self.best_sector_splits):
                            best_split = self.best_sector_splits[target_gate_idx - 1]
                            delta_s = round(split_s - best_split, 2)
                        else:
                            delta_s = 0.0
                        self.sector_deltas.append(delta_s)

                        # Check if this was the Finish Gate
                        if target_gate_idx == len(gates) - 1:
                            self.state = "FINISHED"
                            is_new_best = False
                            if self.best_lap_s is None or split_s < self.best_lap_s:
                                self.best_lap_s = split_s
                                self.best_sector_splits = list(self.sector_split_times)
                                is_new_best = True

                            m = int(split_s // 60)
                            s = split_s % 60
                            time_str = f"{m} minutes, {s:.1f} seconds" if m > 0 else f"{s:.1f} seconds"
                            if is_new_best:
                                self._speak(f"Checkered flag Dad! New personal best: {time_str}!")
                            else:
                                self._speak(f"Checkered flag Dad! Lap finished in {time_str}.")
                        else:
                            # Intermediate sector gate
                            sec_num = target_gate_idx
                            self.current_sector_idx = target_gate_idx
                            self.sector_top_speeds.append(speed_mph)
                            self.sector_max_lat_g.append(abs(lat_g))
                            if delta_s < 0:
                                self._speak(f"Sector {sec_num} green! You're {abs(delta_s):.1f} seconds up on best lap, Dad!")
                            else:
                                self._speak(f"Sector {sec_num} complete.")

        return self.get_status()

    def _speak(self, text: str):
        if self.audio_player and hasattr(self.audio_player, "speak_instant"):
            self.audio_player.speak_instant(text)

    def get_status(self) -> Dict[str, Any]:
        cur_m = int(self.current_lap_s // 60)
        cur_s = self.current_lap_s % 60
        formatted_current = f"{cur_m:02d}:{cur_s:05.2f}"

        formatted_best = "--:--.--"
        if self.best_lap_s is not None:
            best_m = int(self.best_lap_s // 60)
            best_s = self.best_lap_s % 60
            formatted_best = f"{best_m:02d}:{best_s:05.2f}"

        return {
            "track_id": self.track_id,
            "track_name": self.profile["name"],
            "region": self.profile["region"],
            "distance_miles": self.profile["distance_miles"],
            "state": self.state,
            "current_lap_s": self.current_lap_s,
            "formatted_current": formatted_current,
            "best_lap_s": self.best_lap_s,
            "formatted_best": formatted_best,
            "current_sector": self.current_sector_idx + 1,
            "total_sectors": len(self.profile["gates"]) - 1,
            "sector_splits": self.sector_split_times,
            "sector_deltas": self.sector_deltas,
            "sector_top_speeds": self.sector_top_speeds,
            "sector_max_lat_g": self.sector_max_lat_g
        }
