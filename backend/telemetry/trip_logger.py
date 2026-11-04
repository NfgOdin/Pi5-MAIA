"""
trip_logger.py - SQLite Persistent Driving & Vehicle Diagnostics Database
Records:
- Driving Sessions / Trips (start/end timestamp, duration, distance, peak boost, max speed, average speed, max RPM, temperatures, fuel economy, DTC incidents, boost pulls, 0-60 launches)
- High-resolution sensor snapshots during full-throttle boost pulls
- Permanent DTC incident history
- Configurable retention policy (auto-delete after X days) & manual clear all with confirmation
"""

import os
import sqlite3
import time
import json
import threading
from typing import Dict, List, Any, Optional


class TripLogger:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "vehicle_data.db")
        self.current_trip_id: Optional[int] = None
        self.trip_start_time = time.time()
        self.last_sample_time = time.time()
        self.max_boost = 0.0
        self.max_speed = 0.0
        self.max_rpm = 0.0
        self.peak_coolant = 0.0
        self.peak_iat = 0.0
        self.distance_miles = 0.0
        self.speed_samples: List[float] = []
        self.rpm_samples: List[float] = []
        self.mpg_samples: List[float] = []
        self.dtc_incidents: List[str] = []
        self.boost_pulls_count = 0
        self.was_in_pull = False
        self.best_zero_to_sixty: Optional[float] = None
        self.retention_days = 0  # 0 = keep forever / disabled
        self.last_purge_time = 0.0
        self.lock = threading.RLock()

        self._init_db()
        self._load_settings()
        self.purge_old_trips()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Main Trips Table
            c.execute("""
                CREATE TABLE IF NOT EXISTS trips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_min REAL DEFAULT 0.0,
                    distance_miles REAL DEFAULT 0.0,
                    max_speed_mph REAL DEFAULT 0.0,
                    avg_speed_mph REAL DEFAULT 0.0,
                    max_boost_psi REAL DEFAULT 0.0,
                    max_rpm REAL DEFAULT 0.0,
                    avg_rpm REAL DEFAULT 0.0,
                    peak_coolant_f REAL DEFAULT 0.0,
                    peak_iat_f REAL DEFAULT 0.0,
                    avg_mpg REAL DEFAULT 0.0,
                    fuel_used_gal REAL DEFAULT 0.0,
                    dtc_count INTEGER DEFAULT 0,
                    dtc_list TEXT DEFAULT '[]',
                    boost_pulls_count INTEGER DEFAULT 0,
                    best_zero_to_sixty REAL
                )
            """)

            # High-resolution Sensor Pulls
            c.execute("""
                CREATE TABLE IF NOT EXISTS sensor_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trip_id INTEGER,
                    timestamp REAL,
                    speed_mph REAL,
                    boost_psi REAL,
                    rpm INTEGER,
                    coolant_temp_f REAL,
                    throttle_pct REAL,
                    FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
                )
            """)

            # Key-Value Settings Table (for retention policy, etc.)
            c.execute("""
                CREATE TABLE IF NOT EXISTS trip_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Migration: Ensure all new columns exist on pre-existing databases
            existing_cols = [row[1] for row in c.execute("PRAGMA table_info(trips)").fetchall()]
            new_columns = [
                ("distance_miles", "REAL DEFAULT 0.0"),
                ("avg_speed_mph", "REAL DEFAULT 0.0"),
                ("max_rpm", "REAL DEFAULT 0.0"),
                ("avg_rpm", "REAL DEFAULT 0.0"),
                ("peak_coolant_f", "REAL DEFAULT 0.0"),
                ("peak_iat_f", "REAL DEFAULT 0.0"),
                ("fuel_used_gal", "REAL DEFAULT 0.0"),
                ("dtc_list", "TEXT DEFAULT '[]'"),
                ("boost_pulls_count", "INTEGER DEFAULT 0"),
                ("best_zero_to_sixty", "REAL")
            ]
            for col_name, col_def in new_columns:
                if col_name not in existing_cols:
                    try:
                        c.execute(f"ALTER TABLE trips ADD COLUMN {col_name} {col_def}")
                    except Exception as e:
                        print(f"[TRIP_LOG] Migration note for {col_name}: {e}")

            conn.commit()

        # Start initial driving session
        self.start_trip()

    def _load_settings(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT value FROM trip_settings WHERE key = 'retention_days'")
                row = c.fetchone()
                if row:
                    self.retention_days = int(row[0])
        except Exception as e:
            print(f"[TRIP_LOG] Error reading settings: {e}")

    def set_retention_days(self, days: int) -> int:
        with self.lock:
            self.retention_days = max(0, int(days))
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO trip_settings (key, value) VALUES ('retention_days', ?)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """, (str(self.retention_days),))
                    conn.commit()
            except Exception as e:
                print(f"[TRIP_LOG] Error saving retention setting: {e}")
        self.purge_old_trips()
        return self.retention_days

    def purge_old_trips(self) -> int:
        """Purges trips older than retention_days. If retention_days <= 0, no trips are auto-deleted."""
        if self.retention_days <= 0:
            return 0
        purged_count = 0
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                # Find trips older than N days (excluding the active trip)
                c.execute("""
                    SELECT id FROM trips 
                    WHERE id != ? AND datetime(start_time) < datetime('now', '-' || ? || ' days')
                """, (self.current_trip_id or -1, self.retention_days))
                old_ids = [r[0] for r in c.fetchall()]
                if old_ids:
                    id_placeholders = ",".join("?" * len(old_ids))
                    c.execute(f"DELETE FROM sensor_logs WHERE trip_id IN ({id_placeholders})", old_ids)
                    c.execute(f"DELETE FROM trips WHERE id IN ({id_placeholders})", old_ids)
                    purged_count = len(old_ids)
                    conn.commit()
                    print(f"[TRIP_LOG] Auto-purged {purged_count} trips older than {self.retention_days} days.")
        except Exception as e:
            print(f"[TRIP_LOG] Error purging old trips: {e}")
        return purged_count

    def clear_all_trips(self) -> bool:
        """Permanently deletes all historical trip records and resets session stats."""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM sensor_logs")
                    c.execute("DELETE FROM trips")
                    try:
                        c.execute("DELETE FROM sqlite_sequence WHERE name IN ('trips', 'sensor_logs')")
                    except Exception:
                        pass
                    conn.commit()
                print("[TRIP_LOG] All trip logs cleared by user.")
                # Immediately start a clean new trip
                self.start_trip()
                return True
            except Exception as e:
                print(f"[TRIP_LOG] Error clearing trips: {e}")
                return False

    def delete_trip(self, trip_id: int) -> bool:
        """Deletes a single specific trip by ID."""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM sensor_logs WHERE trip_id = ?", (trip_id,))
                    c.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
                    conn.commit()
                return True
            except Exception as e:
                print(f"[TRIP_LOG] Error deleting trip {trip_id}: {e}")
                return False

    def start_trip(self):
        with self.lock:
            self.trip_start_time = time.time()
            self.last_sample_time = time.time()
            self.max_boost = 0.0
            self.max_speed = 0.0
            self.max_rpm = 0.0
            self.peak_coolant = 0.0
            self.peak_iat = 0.0
            self.distance_miles = 0.0
            self.speed_samples.clear()
            self.rpm_samples.clear()
            self.mpg_samples.clear()
            self.dtc_incidents.clear()
            self.boost_pulls_count = 0
            self.was_in_pull = False
            self.best_zero_to_sixty = None

            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO trips (
                            start_time, max_speed_mph, avg_speed_mph, max_boost_psi, 
                            max_rpm, avg_rpm, peak_coolant_f, peak_iat_f, avg_mpg, 
                            distance_miles, fuel_used_gal, dtc_count, dtc_list, boost_pulls_count
                        )
                        VALUES (?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, '[]', 0)
                    """, (time.strftime("%Y-%m-%d %H:%M:%S"),))
                    self.current_trip_id = c.lastrowid
                    conn.commit()
            except Exception as e:
                print(f"[TRIP_LOG] Error starting trip: {e}")

    def log_telemetry_sample(self, telem: Dict[str, Any]):
        """Called periodically from daemon telemetry loop (approx 1Hz)."""
        if not telem or not self.current_trip_id:
            return

        now = time.time()
        dt_sec = max(0.05, min(5.0, now - self.last_sample_time))
        self.last_sample_time = now

        speed = float(telem.get("speed_mph") or 0.0)
        boost = float(telem.get("boost_psi") or 0.0)
        rpm = float(telem.get("rpm") or 0.0)
        coolant = float(telem.get("coolant_temp_f") or 0.0)
        iat = float(telem.get("intake_temp_f") or 0.0)
        throttle = float(telem.get("throttle_pct") or 0.0)
        mpg = float(telem.get("fuel_mpg_instant") or 0.0)
        dtcs = telem.get("active_dtcs") or []
        z60 = telem.get("zero_to_sixty_time")

        with self.lock:
            # Distance integration (speed * hours)
            if speed > 0.5:
                self.distance_miles += speed * (dt_sec / 3600.0)

            # Maxima
            if speed > self.max_speed:
                self.max_speed = speed
            if boost > self.max_boost:
                self.max_boost = boost
            if rpm > self.max_rpm:
                self.max_rpm = rpm
            if coolant > self.peak_coolant:
                self.peak_coolant = coolant
            if iat > self.peak_iat:
                self.peak_iat = iat

            # Samples
            if speed > 0.5:
                self.speed_samples.append(speed)
                if len(self.speed_samples) > 600:
                    self.speed_samples.pop(0)

            if rpm > 400:
                self.rpm_samples.append(rpm)
                if len(self.rpm_samples) > 600:
                    self.rpm_samples.pop(0)

            if mpg > 0:
                self.mpg_samples.append(mpg)
                if len(self.mpg_samples) > 600:
                    self.mpg_samples.pop(0)

            # Boost pulls count
            is_pull = (boost >= 5.0 or throttle >= 80.0)
            if is_pull and not self.was_in_pull:
                self.boost_pulls_count += 1
            self.was_in_pull = is_pull

            # 0-60 Tracker
            if z60 and isinstance(z60, (int, float)) and z60 > 1.5:
                if self.best_zero_to_sixty is None or z60 < self.best_zero_to_sixty:
                    self.best_zero_to_sixty = round(float(z60), 2)

            # DTC tracking
            for d in dtcs:
                if d and d not in self.dtc_incidents:
                    self.dtc_incidents.append(str(d))

            # Averages
            duration_min = round((now - self.trip_start_time) / 60.0, 1)
            avg_speed = round(sum(self.speed_samples) / len(self.speed_samples), 1) if self.speed_samples else round(self.max_speed, 1)
            avg_rpm = round(sum(self.rpm_samples) / len(self.rpm_samples), 0) if self.rpm_samples else round(self.max_rpm, 0)
            avg_mpg = round(sum(self.mpg_samples) / len(self.mpg_samples), 1) if self.mpg_samples else 28.5
            fuel_used_gal = round(self.distance_miles / max(5.0, avg_mpg), 2)

            # Update DB
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute("""
                        UPDATE trips
                        SET end_time = ?,
                            duration_min = ?,
                            distance_miles = ?,
                            max_speed_mph = ?,
                            avg_speed_mph = ?,
                            max_boost_psi = ?,
                            max_rpm = ?,
                            avg_rpm = ?,
                            peak_coolant_f = ?,
                            peak_iat_f = ?,
                            avg_mpg = ?,
                            fuel_used_gal = ?,
                            dtc_count = ?,
                            dtc_list = ?,
                            boost_pulls_count = ?,
                            best_zero_to_sixty = ?
                        WHERE id = ?
                    """, (
                        time.strftime("%Y-%m-%d %H:%M:%S"),
                        duration_min,
                        round(self.distance_miles, 2),
                        round(self.max_speed, 1),
                        avg_speed,
                        round(self.max_boost, 1),
                        round(self.max_rpm, 0),
                        avg_rpm,
                        round(self.peak_coolant, 1),
                        round(self.peak_iat, 1),
                        avg_mpg,
                        fuel_used_gal,
                        len(self.dtc_incidents),
                        json.dumps(self.dtc_incidents),
                        self.boost_pulls_count,
                        self.best_zero_to_sixty,
                        self.current_trip_id
                    ))
                    conn.commit()
            except Exception as e:
                print(f"[TRIP_LOG] Error updating trip: {e}")

        # Periodic retention check (once every 10 minutes)
        if now - self.last_purge_time > 600:
            self.last_purge_time = now
            self.purge_old_trips()

    def get_recent_trips(self, limit: int = 30) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT * FROM trips ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = c.fetchall()
            trips = []
            for r in rows:
                d = dict(r)
                # Parse dtc_list safely
                if isinstance(d.get("dtc_list"), str):
                    try:
                        d["dtc_list"] = json.loads(d["dtc_list"])
                    except Exception:
                        d["dtc_list"] = []
                trips.append(d)
            return trips

    def get_lifetime_stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT 
                    COUNT(*), 
                    MAX(max_boost_psi), 
                    MAX(max_speed_mph), 
                    AVG(avg_mpg), 
                    SUM(duration_min),
                    SUM(distance_miles),
                    SUM(boost_pulls_count),
                    MIN(best_zero_to_sixty),
                    MAX(max_rpm)
                FROM trips
            """)
            count, peak_boost, top_speed, avg_mpg, total_dur, total_dist, total_pulls, best_060, max_rpm = c.fetchone()
            return {
                "total_trips": count or 0,
                "peak_boost_ever": round(peak_boost or 0.0, 1),
                "top_speed_ever": round(top_speed or 0.0, 1),
                "lifetime_avg_mpg": round(avg_mpg or 0.0, 1),
                "total_drive_hours": round((total_dur or 0.0) / 60.0, 1),
                "total_distance_miles": round(total_dist or 0.0, 1),
                "total_boost_pulls": total_pulls or 0,
                "best_zero_to_sixty_ever": round(best_060, 2) if best_060 is not None else None,
                "max_rpm_ever": round(max_rpm or 0.0, 0),
                "retention_days": self.retention_days
            }
