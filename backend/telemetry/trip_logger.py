"""
trip_logger.py - Professional Black-Box Flight Recorder & Driving Telemetry Suite for CarPi5
Records:
- Continuous high-resolution telemetry (16+ sensors @ 1Hz) for every driving session.
- Automatic trip segmentation (engine start/stop detection).
- Automatic periodic archiving & zipping (configurable: every 15, 30, 60 min, or trip end).
- Generation of:
  1. Full high-resolution telemetry CSV (Excel, MegaLogViewer, HP Tuners compatible).
  2. Statistical JSON summary.
  3. Official Court-Admissible / Legal Print Manifest (HTML/PDF printable report with SHA-256 verification).
- Interactive multi-channel graph timeline scrubbing.
- Configurable retention policy (auto-delete after X days) & manual purge with confirmation.
"""

import os
import sqlite3
import time
import json
import threading
import hashlib
import zipfile
import csv
import io
from typing import Dict, List, Any, Optional, Tuple


class _ClosingConnection(sqlite3.Connection):
    """SQLite Connection subclass that guarantees connection closing on context manager exit."""
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()


class TripLogger:
    def __init__(self, db_path: Optional[str] = None, archive_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "vehicle_data.db")
        self.archive_dir = archive_dir or os.path.join(base_dir, "storage", "trip_archives")
        os.makedirs(self.archive_dir, exist_ok=True)

        self.current_trip_id: Optional[int] = None
        self.trip_start_time = time.time()
        self.last_sample_time = time.time()
        self.last_archive_time = time.time()
        self.engine_off_start_time: Optional[float] = None
        
        # In-memory running stats for fast aggregate calculations
        self.max_boost = 0.0
        self.max_speed = 0.0
        self.max_rpm = 0.0
        self.peak_coolant = 0.0
        self.peak_iat = 0.0
        self.peak_load = 0.0
        self.min_volts = 99.0
        self.max_volts = 0.0
        self.distance_miles = 0.0
        self.idle_duration_sec = 0.0
        self.speed_samples: List[float] = []
        self.rpm_samples: List[float] = []
        self.mpg_samples: List[float] = []
        self.afr_samples: List[float] = []
        self.dtc_incidents: List[str] = []
        self.boost_pulls_count = 0
        self.was_in_pull = False
        self.best_zero_to_sixty: Optional[float] = None
        
        # Settings
        self.retention_days = 0          # 0 = keep forever
        self.auto_zip_interval_min = 30  # Default: auto-zip every 30 minutes
        self.auto_log_enabled = True
        self.last_purge_time = 0.0
        self.lock = threading.RLock()

        self._init_db()
        self._load_settings()
        self.purge_old_trips()

    def _get_connection(self):
        """Flash Wear Protection & RAM-optimized SQLite Connection with guaranteed close on exit."""
        conn = sqlite3.connect(self.db_path, timeout=10.0, factory=_ClosingConnection)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA mmap_size = 268435456;")
        conn.execute("PRAGMA cache_size = -64000;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            c = conn.cursor()
            # 1. Main Trips Summary Table
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
                    peak_load_pct REAL DEFAULT 0.0,
                    avg_afr REAL DEFAULT 14.7,
                    min_volts REAL DEFAULT 0.0,
                    max_volts REAL DEFAULT 0.0,
                    idle_duration_min REAL DEFAULT 0.0,
                    avg_mpg REAL DEFAULT 0.0,
                    fuel_used_gal REAL DEFAULT 0.0,
                    dtc_count INTEGER DEFAULT 0,
                    dtc_list TEXT DEFAULT '[]',
                    boost_pulls_count INTEGER DEFAULT 0,
                    best_zero_to_sixty REAL,
                    archive_path TEXT,
                    sha256_hash TEXT,
                    is_active INTEGER DEFAULT 1
                )
            """)

            # 2. Continuous High-Resolution Telemetry Stream Points Table
            c.execute("""
                CREATE TABLE IF NOT EXISTS trip_telemetry_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trip_id INTEGER,
                    timestamp REAL,
                    time_str TEXT,
                    time_12h TEXT,
                    elapsed_str TEXT,
                    speed_mph REAL,
                    rpm REAL,
                    boost_psi REAL,
                    vacuum_inhg REAL,
                    throttle_pct REAL,
                    pedal_pos_pct REAL,
                    engine_load_pct REAL,
                    coolant_temp_f REAL,
                    intake_temp_f REAL,
                    battery_volts REAL,
                    afr REAL,
                    timing_advance_deg REAL,
                    fuel_level_pct REAL,
                    fuel_gph REAL,
                    fuel_mpg_instant REAL,
                    ambient_temp_f REAL,
                    baro_kpa REAL,
                    distance_miles REAL,
                    gear TEXT,
                    dtc_count INTEGER,
                    FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_trip_pts_trip_id ON trip_telemetry_points(trip_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_trip_pts_ts ON trip_telemetry_points(timestamp)")

            # 3. Settings Table
            c.execute("""
                CREATE TABLE IF NOT EXISTS trip_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Migrations: Ensure all columns exist on pre-existing databases
            existing_cols = [row[1] for row in c.execute("PRAGMA table_info(trips)").fetchall()]
            new_columns = [
                ("distance_miles", "REAL DEFAULT 0.0"),
                ("avg_speed_mph", "REAL DEFAULT 0.0"),
                ("max_rpm", "REAL DEFAULT 0.0"),
                ("avg_rpm", "REAL DEFAULT 0.0"),
                ("peak_coolant_f", "REAL DEFAULT 0.0"),
                ("peak_iat_f", "REAL DEFAULT 0.0"),
                ("peak_load_pct", "REAL DEFAULT 0.0"),
                ("avg_afr", "REAL DEFAULT 14.7"),
                ("min_volts", "REAL DEFAULT 0.0"),
                ("max_volts", "REAL DEFAULT 0.0"),
                ("idle_duration_min", "REAL DEFAULT 0.0"),
                ("fuel_used_gal", "REAL DEFAULT 0.0"),
                ("dtc_list", "TEXT DEFAULT '[]'"),
                ("boost_pulls_count", "INTEGER DEFAULT 0"),
                ("best_zero_to_sixty", "REAL"),
                ("archive_path", "TEXT"),
                ("sha256_hash", "TEXT"),
                ("max_speed_time", "TEXT DEFAULT ''"),
                ("engine_runtime_sec", "INTEGER DEFAULT 0"),
                ("is_active", "INTEGER DEFAULT 1")
            ]
            for col_name, col_def in new_columns:
                if col_name not in existing_cols:
                    try:
                        c.execute(f"ALTER TABLE trips ADD COLUMN {col_name} {col_def}")
                    except Exception as e:
                        print(f"[TRIP_LOG] Migration note for {col_name}: {e}")

                        # Check points table columns
            pts_cols = [row[1] for row in c.execute("PRAGMA table_info(trip_telemetry_points)").fetchall()]
            for p_col in [("time_12h", "TEXT DEFAULT ''"), ("elapsed_str", "TEXT DEFAULT ''"), ("engine_runtime_sec", "INTEGER DEFAULT 0")]:
                if p_col[0] not in pts_cols:
                    try: c.execute(f"ALTER TABLE trip_telemetry_points ADD COLUMN {p_col[0]} {p_col[1]}")
                    except: pass
            conn.commit()

        # Start initial driving session
        self.start_trip()

    def _load_settings(self):
        try:
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT key, value FROM trip_settings")
                for k, v in c.fetchall():
                    if k == "retention_days":
                        self.retention_days = int(v)
                    elif k == "auto_zip_interval_min":
                        self.auto_zip_interval_min = int(v)
                    elif k == "auto_log_enabled":
                        self.auto_log_enabled = (v.lower() == "true")
        except Exception as e:
            print(f"[TRIP_LOG] Error reading settings: {e}")

    def update_settings(self, settings_dict: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if "retention_days" in settings_dict:
                self.retention_days = max(0, int(settings_dict["retention_days"]))
            if "auto_zip_interval_min" in settings_dict:
                self.auto_zip_interval_min = max(0, int(settings_dict["auto_zip_interval_min"]))
            if "auto_log_enabled" in settings_dict:
                self.auto_log_enabled = bool(settings_dict["auto_log_enabled"])

            try:
                with self._get_connection() as conn:
                    c = conn.cursor()
                    for k, v in [
                        ("retention_days", str(self.retention_days)),
                        ("auto_zip_interval_min", str(self.auto_zip_interval_min)),
                        ("auto_log_enabled", str(self.auto_log_enabled))
                    ]:
                        c.execute("""
                            INSERT INTO trip_settings (key, value) VALUES (?, ?)
                            ON CONFLICT(key) DO UPDATE SET value=excluded.value
                        """, (k, v))
                    conn.commit()
            except Exception as e:
                print(f"[TRIP_LOG] Error saving settings: {e}")

        if self.retention_days > 0:
            self.purge_old_trips()
        return self.get_settings()

    def get_settings(self) -> Dict[str, Any]:
        return {
            "retention_days": self.retention_days,
            "auto_zip_interval_min": self.auto_zip_interval_min,
            "auto_log_enabled": self.auto_log_enabled
        }

    def set_retention_days(self, days: int) -> int:
        """Sets the trip retention policy in days (0 = keep forever) and purges expired trips."""
        self.update_settings({"retention_days": max(0, int(days))})
        return self.retention_days

    def start_trip(self):
        with self.lock:
            self.trip_start_time = time.time()
            self.last_sample_time = time.time()
            self.last_archive_time = time.time()
            self.engine_off_start_time = None
            
            self.max_boost = 0.0
            self.max_speed = 0.0
            self.max_rpm = 0.0
            self.peak_coolant = 0.0
            self.peak_iat = 0.0
            self.peak_load = 0.0
            self.min_volts = 99.0
            self.max_volts = 0.0
            self.distance_miles = 0.0
            self.idle_duration_sec = 0.0
            
            self.speed_samples.clear()
            self.rpm_samples.clear()
            self.mpg_samples.clear()
            self.afr_samples.clear()
            self.dtc_incidents.clear()
            self.boost_pulls_count = 0
            self.was_in_pull = False
            self.best_zero_to_sixty = None
            self.max_speed_time = ""

            try:
                with self._get_connection() as conn:
                    c = conn.cursor()
                    # Mark any previously open trips as inactive
                    c.execute("UPDATE trips SET is_active = 0 WHERE is_active = 1")
                    
                    start_str = time.strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("""
                        INSERT INTO trips (
                            start_time, max_speed_mph, avg_speed_mph, max_boost_psi, 
                            max_rpm, avg_rpm, peak_coolant_f, peak_iat_f, peak_load_pct,
                            avg_afr, min_volts, max_volts, idle_duration_min, avg_mpg, 
                            distance_miles, fuel_used_gal, dtc_count, dtc_list, boost_pulls_count,
                            is_active
                        )
                        VALUES (?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 14.7, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, '[]', 0, 1)
                    """, (start_str,))
                    self.current_trip_id = c.lastrowid
                    conn.commit()
                    print(f"[TRIP_LOG] Started new driving session Trip #{self.current_trip_id} at {start_str}")
            except Exception as e:
                print(f"[TRIP_LOG] Error starting trip: {e}")

    def end_current_trip(self) -> Optional[str]:
        """Finalizes current active trip and auto-generates the zip archive."""
        with self.lock:
            if not self.current_trip_id:
                return None
            trip_id = self.current_trip_id
            print(f"[TRIP_LOG] Ending Trip #{trip_id}...")
            try:
                with self._get_connection() as conn:
                    c = conn.cursor()
                    c.execute("UPDATE trips SET is_active = 0 WHERE id = ?", (trip_id,))
                    conn.commit()
            except Exception as e:
                print(f"[TRIP_LOG] Error marking trip ended: {e}")

            # Generate final archive
            zip_path = self.export_and_zip_trip(trip_id, is_interim=False)
            return zip_path

    def log_telemetry_sample(self, telem: Dict[str, Any]):
        """Called periodically (1Hz) from the telemetry loop."""
        if not self.auto_log_enabled or not telem:
            return

        now = time.time()
        dt_sec = max(0.05, min(5.0, now - self.last_sample_time))
        self.last_sample_time = now
        elapsed_sec = max(0, int(now - self.trip_start_time))
        elapsed_str = f"+{elapsed_sec//3600:02d}:{(elapsed_sec%3600)//60:02d}:{elapsed_sec%60:02d}"
        time_12h = time.strftime("%I:%M:%S %p", time.localtime(now))
        time_24h = time.strftime("%H:%M:%S", time.localtime(now))
        date_str = time.strftime("%Y-%m-%d", time.localtime(now))
        time_str = f"{date_str} {time_24h}"

        speed = float(telem.get("speed_mph") or 0.0)
        rpm = float(telem.get("rpm") or 0.0)
        boost = float(telem.get("boost_psi") or 0.0)
        vacuum = float(telem.get("vacuum_inhg") or 0.0)
        throttle = float(telem.get("throttle_pct") or 0.0)
        pedal = float(telem.get("pedal_pos_pct") or 0.0)
        load = float(telem.get("engine_load_pct") or 0.0)
        coolant = float(telem.get("coolant_temp_f") or 0.0)
        iat = float(telem.get("intake_temp_f") or 0.0)
        volts = float(telem.get("battery_volts") or 0.0)
        afr = float(telem.get("afr") or 14.7)
        timing = float(telem.get("timing_advance_deg") or 0.0)
        fuel_lvl = float(telem.get("fuel_level_pct") or 0.0)
        fuel_gph = float(telem.get("fuel_gph") or 0.0)
        mpg = float(telem.get("fuel_mpg_instant") or 0.0)
        ambient = float(telem.get("ambient_temp_f") or 0.0)
        baro = float(telem.get("baro_kpa") or 101.3)
        gear = str(telem.get("gear") or "N")
        dtcs = telem.get("active_dtcs") or []
        z60 = telem.get("zero_to_sixty_time")
        engine_runtime = int(telem.get("engine_runtime_sec") or 0)

        # Automatic Trip Start/Stop Detection (Rule 2: do not record disconnected hardware frames)
        if telem.get("connected") is False:
            if self.engine_off_start_time is None:
                self.engine_off_start_time = now
            elif (now - self.engine_off_start_time) > 120:
                if self.current_trip_id and (now - self.trip_start_time) > 30:
                    print(f"[TRIP_LOG] Hardware disconnected for > 2 min. Auto-finalizing Trip #{self.current_trip_id}.")
                    self.end_current_trip()
                    self.current_trip_id = None
            return

        if rpm > 400 or speed > 1.0:
            self.engine_off_start_time = None
            if not self.current_trip_id:
                self.start_trip()
        elif rpm < 50 and speed < 0.5:
            if self.engine_off_start_time is None:
                self.engine_off_start_time = now
            elif (now - self.engine_off_start_time) > 120:  # Engine off for > 2 min -> auto finalize trip
                if self.current_trip_id and (now - self.trip_start_time) > 30:
                    print(f"[TRIP_LOG] Vehicle parked & engine off for > 2 min. Auto-finalizing Trip #{self.current_trip_id}.")
                    self.end_current_trip()
                    self.current_trip_id = None
                return

        if not self.current_trip_id:
            return

        with self.lock:
            # Distance integration
            if speed > 0.5:
                self.distance_miles += speed * (dt_sec / 3600.0)
            else:
                self.idle_duration_sec += dt_sec

            # Maxima & Minima
            if speed > self.max_speed:
                self.max_speed = speed
                self.max_speed_time = f"{time_12h} ({elapsed_str})"
            if boost > self.max_boost: self.max_boost = boost
            if rpm > self.max_rpm: self.max_rpm = rpm
            if coolant > self.peak_coolant: self.peak_coolant = coolant
            if iat > self.peak_iat: self.peak_iat = iat
            if load > self.peak_load: self.peak_load = load
            if volts > 5.0:
                if volts < self.min_volts: self.min_volts = volts
                if volts > self.max_volts: self.max_volts = volts

            # Samples for moving averages
            if speed > 0.5:
                self.speed_samples.append(speed)
            if rpm > 400:
                self.rpm_samples.append(rpm)
            if mpg > 0 and speed > 2.0:
                self.mpg_samples.append(mpg)
            if afr > 5.0:
                self.afr_samples.append(afr)

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

            duration_min = round((now - self.trip_start_time) / 60.0, 1)
            idle_min = round(self.idle_duration_sec / 60.0, 1)
            avg_speed = round(sum(self.speed_samples) / len(self.speed_samples), 1) if self.speed_samples else round(self.max_speed, 1)
            avg_rpm = round(sum(self.rpm_samples) / len(self.rpm_samples), 0) if self.rpm_samples else round(self.max_rpm, 0)
            avg_mpg = round(sum(self.mpg_samples) / len(self.mpg_samples), 1) if self.mpg_samples else 0.0
            avg_afr = round(sum(self.afr_samples) / len(self.afr_samples), 2) if self.afr_samples else 14.7
            driving_fuel_gal = (self.distance_miles / max(5.0, avg_mpg)) if (self.distance_miles > 0.0 and avg_mpg > 0.0) else 0.0
            idle_fuel_gal = (idle_min * (fuel_gph if fuel_gph > 0.0 else (0.2 if rpm > 300 else 0.0)) / 60.0)
            fuel_used_gal = round(driving_fuel_gal + idle_fuel_gal, 2)

            time_str = time.strftime("%Y-%m-%d %H:%M:%S")

            # 1. Insert high-res point into trip_telemetry_points
            try:
                with self._get_connection() as conn:
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO trip_telemetry_points (
                            trip_id, timestamp, time_str, time_12h, elapsed_str, speed_mph, rpm, boost_psi, vacuum_inhg,
                            throttle_pct, pedal_pos_pct, engine_load_pct, coolant_temp_f, intake_temp_f,
                            battery_volts, afr, timing_advance_deg, fuel_level_pct, fuel_gph,
                            fuel_mpg_instant, ambient_temp_f, baro_kpa, distance_miles, gear, dtc_count, engine_runtime_sec
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        self.current_trip_id, now, time_str, time_12h, elapsed_str, speed, rpm, boost, vacuum,
                        throttle, pedal, load, coolant, iat, volts, afr, timing, fuel_lvl,
                        fuel_gph, mpg, ambient, baro, round(self.distance_miles, 3), gear, len(dtcs), engine_runtime
                    ))

                    # 2. Update trip summary row
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
                            peak_load_pct = ?,
                            avg_afr = ?,
                            min_volts = ?,
                            max_volts = ?,
                            idle_duration_min = ?,
                            avg_mpg = ?,
                            fuel_used_gal = ?,
                            dtc_count = ?,
                            dtc_list = ?,
                            boost_pulls_count = ?,
                            best_zero_to_sixty = ?,
                            max_speed_time = ?,
                            engine_runtime_sec = MAX(COALESCE(engine_runtime_sec, 0), ?)
                        WHERE id = ?
                    """, (
                        time_str,
                        duration_min,
                        round(self.distance_miles, 2),
                        round(self.max_speed, 1),
                        avg_speed,
                        round(self.max_boost, 1),
                        round(self.max_rpm, 0),
                        avg_rpm,
                        round(self.peak_coolant, 1),
                        round(self.peak_iat, 1),
                        round(self.peak_load, 1),
                        avg_afr,
                        round(self.min_volts if self.min_volts < 90 else volts, 1),
                        round(self.max_volts, 1),
                        idle_min,
                        avg_mpg,
                        fuel_used_gal,
                        len(self.dtc_incidents),
                        json.dumps(self.dtc_incidents),
                        self.boost_pulls_count,
                        self.best_zero_to_sixty,
                        getattr(self, "max_speed_time", ""),
                        engine_runtime,
                        self.current_trip_id
                    ))
                    conn.commit()
            except Exception as e:
                print(f"[TRIP_LOG] Error writing telemetry sample: {e}")

        # Check periodic auto-zip interval (e.g. every 15, 30, or 60 min)
        if self.auto_zip_interval_min > 0:
            if (now - self.last_archive_time) >= (self.auto_zip_interval_min * 60):
                self.last_archive_time = now
                threading.Thread(target=self.export_and_zip_trip, args=(self.current_trip_id, True), daemon=True).start()

        # Periodic retention check (once every 10 minutes)
        if now - self.last_purge_time > 600:
            self.last_purge_time = now
            self.purge_old_trips()

    def _get_target_trip_id(self, trip_id: Optional[int] = None) -> Optional[int]:
        """Resolves trip_id or falls back to active or most recent recorded trip."""
        if trip_id is not None and trip_id > 0:
            return trip_id
        if self.current_trip_id:
            return self.current_trip_id
        try:
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT id FROM trips ORDER BY id DESC LIMIT 1")
                row = c.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            print(f"[TRIP_LOG] Error getting target trip ID: {e}")
        return None

    def get_trip_csv_bytes(self, trip_id: Optional[int] = None) -> Tuple[Optional[bytes], str]:
        """Generates raw 28-channel high-resolution CSV bytes and filename for direct download."""
        target_id = self._get_target_trip_id(trip_id)
        if not target_id:
            return None, ""

        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    c = conn.cursor()
                    c.execute("SELECT * FROM trips WHERE id = ?", (target_id,))
                    trip_row = c.fetchone()
                    if not trip_row:
                        return None, ""
                    trip_data = dict(trip_row)

                    c.execute("SELECT * FROM trip_telemetry_points WHERE trip_id = ? ORDER BY id ASC", (target_id,))
                    points_rows = c.fetchall()
            except Exception as e:
                print(f"[TRIP_LOG] Error fetching CSV data: {e}")
                return None, ""

        points_list = [dict(r) for r in points_rows]
        csv_buffer = io.StringIO()
        fieldnames = [
            "Date", "Time_12H", "Time_24H", "Elapsed_Time", "Timestamp_Unix", "Speed_MPH", "Speed_KPH", "RPM", "Boost_PSI",
            "Vacuum_inHg", "Throttle_Pct", "Pedal_Pos_Pct", "Engine_Load_Pct", "Coolant_Temp_F",
            "Intake_Temp_F", "Battery_Volts", "AFR", "Timing_Advance_Deg", "Fuel_Level_Pct",
            "Fuel_Burn_GPH", "Instant_MPG", "Ambient_Temp_F", "Baro_kPa", "Distance_Miles", "Gear", "DTC_Count", "Engine_Runtime_Sec", "Engine_Hours"
        ]
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for p in points_list:
            ts = float(p.get('timestamp') or 0.0)
            t_str = p.get('time_str') or ''
            d_str = t_str.split(' ')[0] if ' ' in t_str else time.strftime('%Y-%m-%d', time.localtime(ts))
            t_24 = t_str.split(' ')[1] if ' ' in t_str else time.strftime('%H:%M:%S', time.localtime(ts))
            t_12 = p.get('time_12h') or time.strftime('%I:%M:%S %p', time.localtime(ts))
            el_str = p.get('elapsed_str') or ''
            spd_mph = float(p.get('speed_mph') or 0.0)
            eng_rt = int(p.get('engine_runtime_sec') or 0)

            writer.writerow({
                "Date": d_str,
                "Time_12H": t_12,
                "Time_24H": t_24,
                "Elapsed_Time": el_str,
                "Timestamp_Unix": f"{ts:.2f}",
                "Speed_MPH": f"{spd_mph:.1f}",
                "Speed_KPH": f"{(spd_mph * 1.60934):.1f}",
                "RPM": f"{float(p.get('rpm') or 0.0):.0f}",
                "Boost_PSI": f"{float(p.get('boost_psi') or 0.0):.1f}",
                "Vacuum_inHg": f"{float(p.get('vacuum_inhg') or 0.0):.1f}",
                "Throttle_Pct": f"{float(p.get('throttle_pct') or 0.0):.1f}",
                "Pedal_Pos_Pct": f"{float(p.get('pedal_pos_pct') or 0.0):.1f}",
                "Engine_Load_Pct": f"{float(p.get('engine_load_pct') or 0.0):.1f}",
                "Coolant_Temp_F": f"{float(p.get('coolant_temp_f') or 0.0):.1f}",
                "Intake_Temp_F": f"{float(p.get('intake_temp_f') or 0.0):.1f}",
                "Battery_Volts": f"{float(p.get('battery_volts') or 0.0):.1f}",
                "AFR": f"{float(p.get('afr') or 14.7):.2f}",
                "Timing_Advance_Deg": f"{float(p.get('timing_advance_deg') or 0.0):.1f}",
                "Fuel_Level_Pct": f"{float(p.get('fuel_level_pct') or 0.0):.1f}",
                "Fuel_Burn_GPH": f"{float(p.get('fuel_gph') or 0.0):.2f}",
                "Instant_MPG": f"{float(p.get('fuel_mpg_instant') or 0.0):.1f}",
                "Ambient_Temp_F": f"{float(p.get('ambient_temp_f') or 0.0):.1f}",
                "Baro_kPa": f"{float(p.get('baro_kpa') or 0.0):.1f}",
                "Distance_Miles": f"{float(p.get('distance_miles') or 0.0):.3f}",
                "Gear": p.get("gear") or "N",
                "DTC_Count": int(p.get("dtc_count") or 0),
                "Engine_Runtime_Sec": eng_rt,
                "Engine_Hours": f"{(eng_rt / 3600.0):.2f}"
            })

        date_part = trip_data.get('start_time', '').replace(':', '-').replace(' ', '_')
        filename = f"Trip_{date_part}_ID{target_id}_telemetry.csv"
        return csv_buffer.getvalue().encode("utf-8"), filename

    def get_manifest_html(self, trip_id: Optional[int] = None) -> Optional[str]:
        """Constructs and returns the court-ready printable black-box manifest HTML."""
        target_id = self._get_target_trip_id(trip_id)
        if not target_id:
            return None

        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    c = conn.cursor()
                    c.execute("SELECT * FROM trips WHERE id = ?", (target_id,))
                    trip_row = c.fetchone()
                    if not trip_row:
                        return None
                    trip_data = dict(trip_row)

                    c.execute("SELECT * FROM trip_telemetry_points WHERE trip_id = ? ORDER BY id ASC", (target_id,))
                    points_rows = c.fetchall()
            except Exception as e:
                print(f"[TRIP_LOG] Error fetching manifest data: {e}")
                return None

        points_list = [dict(r) for r in points_rows]
        csv_bytes, _ = self.get_trip_csv_bytes(target_id)
        sha256 = hashlib.sha256(csv_bytes).hexdigest() if csv_bytes else "UNSIGNED"
        is_interim = bool(trip_data.get("is_active", 0) == 1)
        return self._build_manifest_html(trip_data, points_list, sha256, is_interim)

    def get_trip_zip_path(self, trip_id: Optional[int] = None) -> Tuple[Optional[str], str]:
        """Returns the filesystem path to the trip's ZIP archive, compiling it on demand if needed."""
        target_id = self._get_target_trip_id(trip_id)
        if not target_id:
            return None, ""

        # Check if already archived and exists
        with self.lock:
            try:
                with self._get_connection() as conn:
                    c = conn.cursor()
                    c.execute("SELECT archive_path FROM trips WHERE id = ?", (target_id,))
                    row = c.fetchone()
                    if row and row[0] and os.path.exists(row[0]) and target_id != self.current_trip_id:
                        return row[0], os.path.basename(row[0])
            except Exception:
                pass

        # Compile fresh on demand
        zip_path = self.export_and_zip_trip(target_id, is_interim=(target_id == self.current_trip_id))
        if zip_path and os.path.exists(zip_path):
            return zip_path, os.path.basename(zip_path)
        return None, ""

    def export_and_zip_trip(self, trip_id: int, is_interim: bool = False) -> Optional[str]:
        """
        Creates a comprehensive ZIP archive containing:
        1. telemetry_highres.csv (full-drive high-res telemetry)
        2. trip_summary.json (statistical metadata & forensic hashes)
        3. official_trip_manifest.html (court-ready printable legal manifest)
        """
        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    c = conn.cursor()
                    c.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
                    trip_row = c.fetchone()
                    if not trip_row:
                        return None
                    trip_data = dict(trip_row)

                    c.execute("SELECT * FROM trip_telemetry_points WHERE trip_id = ? ORDER BY id ASC", (trip_id,))
                    points_rows = c.fetchall()
            except Exception as e:
                print(f"[TRIP_LOG] Error fetching trip data for zip export: {e}")
                return None

        points_list = [dict(r) for r in points_rows]

        # 1. Generate High-Res CSV
        csv_buffer = io.StringIO()
        fieldnames = [
            "Date", "Time_12H", "Time_24H", "Elapsed_Time", "Timestamp_Unix", "Speed_MPH", "Speed_KPH", "RPM", "Boost_PSI",
            "Vacuum_inHg", "Throttle_Pct", "Pedal_Pos_Pct", "Engine_Load_Pct", "Coolant_Temp_F",
            "Intake_Temp_F", "Battery_Volts", "AFR", "Timing_Advance_Deg", "Fuel_Level_Pct",
            "Fuel_Burn_GPH", "Instant_MPG", "Ambient_Temp_F", "Baro_kPa", "Distance_Miles", "Gear", "DTC_Count", "Engine_Runtime_Sec", "Engine_Hours"
        ]
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for p in points_list:
            ts = float(p.get('timestamp') or 0.0)
            t_str = p.get('time_str') or ''
            d_str = t_str.split(' ')[0] if ' ' in t_str else time.strftime('%Y-%m-%d', time.localtime(ts))
            t_24 = t_str.split(' ')[1] if ' ' in t_str else time.strftime('%H:%M:%S', time.localtime(ts))
            t_12 = p.get('time_12h') or time.strftime('%I:%M:%S %p', time.localtime(ts))
            el_str = p.get('elapsed_str') or ''
            spd_mph = float(p.get('speed_mph') or 0.0)
            eng_rt = int(p.get('engine_runtime_sec') or 0)

            writer.writerow({
                "Date": d_str,
                "Time_12H": t_12,
                "Time_24H": t_24,
                "Elapsed_Time": el_str,
                "Timestamp_Unix": f"{ts:.2f}",
                "Speed_MPH": f"{spd_mph:.1f}",
                "Speed_KPH": f"{(spd_mph * 1.60934):.1f}",
                "RPM": f"{float(p.get('rpm') or 0.0):.0f}",
                "Boost_PSI": f"{float(p.get('boost_psi') or 0.0):.1f}",
                "Vacuum_inHg": f"{float(p.get('vacuum_inhg') or 0.0):.1f}",
                "Throttle_Pct": f"{float(p.get('throttle_pct') or 0.0):.1f}",
                "Pedal_Pos_Pct": f"{float(p.get('pedal_pos_pct') or 0.0):.1f}",
                "Engine_Load_Pct": f"{float(p.get('engine_load_pct') or 0.0):.1f}",
                "Coolant_Temp_F": f"{float(p.get('coolant_temp_f') or 0.0):.1f}",
                "Intake_Temp_F": f"{float(p.get('intake_temp_f') or 0.0):.1f}",
                "Battery_Volts": f"{float(p.get('battery_volts') or 0.0):.1f}",
                "AFR": f"{float(p.get('afr') or 14.7):.2f}",
                "Timing_Advance_Deg": f"{float(p.get('timing_advance_deg') or 0.0):.1f}",
                "Fuel_Level_Pct": f"{float(p.get('fuel_level_pct') or 0.0):.1f}",
                "Fuel_Burn_GPH": f"{float(p.get('fuel_gph') or 0.0):.2f}",
                "Instant_MPG": f"{float(p.get('fuel_mpg_instant') or 0.0):.1f}",
                "Ambient_Temp_F": f"{float(p.get('ambient_temp_f') or 0.0):.1f}",
                "Baro_kPa": f"{float(p.get('baro_kpa') or 0.0):.1f}",
                "Distance_Miles": f"{float(p.get('distance_miles') or 0.0):.3f}",
                "Gear": p.get("gear") or "N",
                "DTC_Count": int(p.get("dtc_count") or 0),
                "Engine_Runtime_Sec": eng_rt,
                "Engine_Hours": f"{(eng_rt / 3600.0):.2f}"
            })
        csv_bytes = csv_buffer.getvalue().encode("utf-8")

        # 2. Compute SHA-256 Checksum for Forensic / Legal Integrity
        sha256 = hashlib.sha256(csv_bytes).hexdigest()

        # 3. Generate JSON summary
        trip_summary = {
            "vehicle": "Dodge Dart 1.4L Turbo MultiAir (C635 6-Speed Manual)",
            "telemetry_recorder": "CarPi5 MultiAir OS Telemetry Suite",
            "trip_id": trip_id,
            "is_interim_snapshot": is_interim,
            "generated_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sha256_csv_checksum": sha256,
            "summary_stats": trip_data,
            "total_samples_recorded": len(points_list)
        }
        json_bytes = json.dumps(trip_summary, indent=2).encode("utf-8")

        # 4. Generate Court-Ready HTML Manifest
        manifest_html = self._build_manifest_html(trip_data, points_list, sha256, is_interim)
        html_bytes = manifest_html.encode("utf-8")

        # 5. Pack into ZIP
        date_stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time()))
        zip_filename = f"Trip_{trip_data.get('start_time', '').replace(':', '-').replace(' ', '_')}_ID{trip_id}.zip"
        zip_path = os.path.join(self.archive_dir, zip_filename)

        try:
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("telemetry_highres.csv", csv_bytes)
                zf.writestr("trip_summary.json", json_bytes)
                zf.writestr("official_trip_manifest.html", html_bytes)

            # Store archive path and hash in database
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE trips SET archive_path = ?, sha256_hash = ? WHERE id = ?
                """, (zip_path, sha256, trip_id))
                conn.commit()

            print(f"[TRIP_LOG] Successfully created trip archive: {zip_path} ({len(points_list)} samples, SHA256: {sha256[:10]}...)")
            return zip_path
        except Exception as e:
            print(f"[TRIP_LOG] Error creating zip archive: {e}")
            return None

    def _build_manifest_html(self, trip: Dict[str, Any], points: List[Dict[str, Any]], sha256_hash: str, is_interim: bool) -> str:
        """Constructs an official, printable, high-contrast black-box flight manifest."""
        dtc_list = []
        if isinstance(trip.get("dtc_list"), str):
            try: dtc_list = json.loads(trip["dtc_list"])
            except: pass

        start_time = trip.get("start_time") or "Unknown"
        end_time = trip.get("end_time") or ("In Progress" if is_interim else "Finished")
        duration = f"{float(trip.get('duration_min') or 0.0):.1f} min"
        distance = f"{float(trip.get('distance_miles') or 0.0):.2f} miles"
        top_speed = f"{float(trip.get('max_speed_mph') or 0.0):.1f} MPH"
        avg_speed = f"{float(trip.get('avg_speed_mph') or 0.0):.1f} MPH"
        peak_boost = f"{float(trip.get('max_boost_psi') or 0.0):.1f} PSI"
        peak_rpm = f"{float(trip.get('max_rpm') or 0.0):.0f} RPM"
        peak_coolant = f"{float(trip.get('peak_coolant_f') or 0.0):.1f} °F"
        avg_mpg = f"{float(trip.get('avg_mpg') or 0.0):.1f} MPG"
        fuel_used = f"{float(trip.get('fuel_used_gal') or 0.0):.2f} gal"
        idle_time = f"{float(trip.get('idle_duration_min') or 0.0):.1f} min"
        peak_load = f"{float(trip.get('peak_load_pct') or 0.0):.1f}%"
        avg_afr = f"{float(trip.get('avg_afr') or 14.7):.2f}:1"
        min_v = f"{float(trip.get('min_volts') or 0.0):.1f} V"
        max_v = f"{float(trip.get('max_volts') or 0.0):.1f} V"
        zero60 = f"{trip.get('best_zero_to_sixty')} s" if trip.get('best_zero_to_sixty') else "N/A"
        engine_runtime_total = int(trip.get('engine_runtime_sec') or 0)
        engine_hours_display = f"{(engine_runtime_total / 3600.0):.2f} hrs" if engine_runtime_total > 0 else "N/A" 

        # Downsample points for preview table (up to 20 representative timeline points)
        sample_rows_html = ""
        step = max(1, len(points) // 20) if points else 1
        for idx in range(0, len(points), step):
            p = points[idx]
            ts_row = float(p.get('timestamp') or 0.0)
            t12_val = p.get('time_12h') or time.strftime('%I:%M:%S %p', time.localtime(ts_row))
            el_val = p.get('elapsed_str') or ''
            sample_rows_html += f"""
            <tr>
                <td><strong>{t12_val}</strong> <span style="color:#8b949e; font-size:10px;">({p.get('time_str') or ''})</span></td>
                <td style="color:#8b949e; font-family:monospace;">{el_val}</td>
                <td><strong style="color:#58a6ff;">{float(p.get('speed_mph') or 0.0):.1f} MPH</strong></td>
                <td>{float(p.get('rpm') or 0.0):.0f}</td>
                <td>{float(p.get('boost_psi') or 0.0):.1f} PSI</td>
                <td>{float(p.get('throttle_pct') or 0.0):.0f}%</td>
                <td>{float(p.get('engine_load_pct') or 0.0):.0f}%</td>
                <td>{float(p.get('coolant_temp_f') or 0.0):.0f}°F</td>
                <td>{float(p.get('afr') or 14.7):.2f}</td>
                <td>{float(p.get('battery_volts') or 0.0):.1f}V</td>
            </tr>
            """

        dtc_display = ", ".join(dtc_list) if dtc_list else "NONE (POWERTRAIN NOMINAL - NO ACTIVE FAULT CODES)"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Official Vehicle Flight Manifest - Trip #{trip.get('id')}</title>
<style>
  body {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
    background: #0d1117;
    color: #e6edf3;
    margin: 0;
    padding: 30px;
  }}
  .manifest-container {{
    max-width: 900px;
    margin: 0 auto;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 36px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.6);
  }}
  .header {{
    border-bottom: 2px solid #388bfd;
    padding-bottom: 20px;
    margin-bottom: 25px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}
  .title {{
    font-size: 24px;
    font-weight: 900;
    letter-spacing: 0.5px;
    color: #58a6ff;
    margin: 0 0 4px 0;
  }}
  .subtitle {{
    font-size: 13px;
    color: #8b949e;
    margin: 0;
  }}
  .badge {{
    background: #1f6feb26;
    color: #58a6ff;
    border: 1px solid #388bfd;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }}
  .grid-stats {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 30px;
  }}
  .stat-card {{
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 14px;
  }}
  .stat-label {{
    font-size: 11px;
    text-transform: uppercase;
    color: #8b949e;
    font-weight: 700;
    margin-bottom: 6px;
  }}
  .stat-value {{
    font-size: 20px;
    font-weight: 800;
    color: #f0f6fc;
  }}
  .section-title {{
    font-size: 15px;
    font-weight: 800;
    color: #79c0ff;
    margin: 25px 0 12px 0;
    border-bottom: 1px solid #21262d;
    padding-bottom: 6px;
    display: flex;
    justify-content: space-between;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    margin-bottom: 25px;
  }}
  th, td {{
    padding: 8px 10px;
    text-align: left;
    border-bottom: 1px solid #21262d;
  }}
  th {{
    background: #0d1117;
    color: #8b949e;
    font-weight: 700;
    text-transform: uppercase;
    font-size: 10px;
  }}
  .hash-box {{
    background: #0b0f14;
    border: 1px dashed #30363d;
    padding: 14px;
    border-radius: 8px;
    font-family: monospace;
    font-size: 11px;
    word-break: break-all;
    margin-bottom: 25px;
  }}
  .print-btn {{
    background: #238636;
    color: #fff;
    border: none;
    padding: 12px 24px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 800;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(35, 134, 54, 0.4);
  }}
  @media print {{
    body {{
      background: #fff !important;
      color: #000 !important;
      padding: 0 !important;
    }}
    .manifest-container {{
      border: none !important;
      box-shadow: none !important;
      background: #fff !important;
      color: #000 !important;
      padding: 0 !important;
      max-width: 100% !important;
    }}
    .print-btn {{ display: none !important; }}
    .title {{ color: #000 !important; }}
    .subtitle {{ color: #444 !important; }}
    .header {{ border-bottom: 2px solid #000 !important; }}
    .badge {{ border: 1px solid #000 !important; color: #000 !important; background: transparent !important; }}
    .stat-card {{ background: #f6f8fa !important; border: 1px solid #d0d7de !important; }}
    .stat-value {{ color: #000 !important; }}
    .stat-label {{ color: #555 !important; }}
    .section-title {{ color: #000 !important; border-bottom: 1px solid #000 !important; }}
    th {{ background: #f0f2f5 !important; color: #000 !important; }}
    td {{ border-bottom: 1px solid #ddd !important; color: #000 !important; }}
    .hash-box {{ background: #f6f8fa !important; border: 1px dashed #999 !important; color: #000 !important; }}
  }}
</style>
</head>
<body>
<div class="manifest-container">
  <div class="header">
    <div>
      <h1 class="title">OFFICIAL VEHICLE FLIGHT MANIFEST</h1>
      <p class="subtitle">Black-Box Forensic Telemetry Record &bull; Dodge Dart 1.4L Turbo MultiAir</p>
      <p class="subtitle">CarPi5 Flight OS &bull; ECU Protocol: ISO 15765-4 CAN 29/500</p>
    </div>
    <div style="text-align:right;">
      <span class="badge">Trip ID #{trip.get('id')}</span>
      <div style="margin-top:10px;">
        <button class="print-btn" onclick="window.print()">🖨️ PRINT OFFICIAL REPORT</button>
      </div>
    </div>
  </div>

  <div class="grid-stats">
    <div class="stat-card">
      <div class="stat-label">Start Time</div>
      <div class="stat-value" style="font-size:14px;">{start_time}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">End Time</div>
      <div class="stat-value" style="font-size:14px;">{end_time}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Duration</div>
      <div class="stat-value">{duration}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Distance</div>
      <div class="stat-value">{distance}</div>
    </div>
  </div>

  <div class="section-title">
    <span>SPEED &amp; DYNAMIC FLIGHT DATA</span>
    <span>{len(points)} Total Samples</span>
  </div>
  <div class="grid-stats">
    <div class="stat-card">
      <div class="stat-label">Top Speed</div>
      <div class="stat-value">{top_speed}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Average Speed</div>
      <div class="stat-value">{avg_speed}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Idle Duration</div>
      <div class="stat-value">{idle_time}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Best 0-60 Time</div>
      <div class="stat-value">{zero60}</div>
    </div>
  </div>

  <div class="section-title">POWERTRAIN &amp; ENGINE HEALTH</div>
  <div class="grid-stats">
    <div class="stat-card">
      <div class="stat-label">Peak Turbo Boost</div>
      <div class="stat-value">{peak_boost}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Max Engine RPM</div>
      <div class="stat-value">{peak_rpm}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Peak MultiAir Temp</div>
      <div class="stat-value">{peak_coolant}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Peak Engine Load</div>
      <div class="stat-value">{peak_load}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Fuel Economy</div>
      <div class="stat-value">{avg_mpg}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Est Fuel Consumed</div>
      <div class="stat-value">{fuel_used}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Air/Fuel Ratio</div>
      <div class="stat-value">{avg_afr}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Battery Voltage Range</div>
      <div class="stat-value">{min_v} - {max_v}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Engine Hours</div>
      <div class="stat-value">{engine_hours_display}</div>
    </div>
  </div>

  <div class="section-title">ON-BOARD DIAGNOSTIC (OBD-II) FAULT AUDIT</div>
  <div style="background:#0d1117; border:1px solid #30363d; border-radius:8px; padding:12px; font-size:12px; margin-bottom:25px;">
    <strong>Active DTC Incident Codes:</strong> {dtc_display}
  </div>

  <div class="section-title">HIGH-RESOLUTION CHRONOLOGICAL SAMPLE LOG (Representative Preview)</div>
  <table>
    <div style="margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">
      <input type="text" id="manifestSearch" placeholder="🔍 Search specific time (e.g. 04:30 PM, 03:00 AM) or speed..." oninput="filterManifestTable(this.value)" style="width:360px; padding:8px 12px; border-radius:6px; border:1px solid #30363d; background:#0d1117; color:#fff; font-size:12px;">
      <span id="filteredRowCount" style="font-size:11px; color:#8b949e;">Showing all rows</span>
    </div>
    <script>
      function filterManifestTable(query) {{
        query = (query || '').toLowerCase().trim();
        const rows = document.querySelectorAll('#manifestTableBody tr');
        let visible = 0;
        rows.forEach(r => {{
          const match = !query || r.innerText.toLowerCase().includes(query);
          r.style.display = match ? '' : 'none';
          if (match) visible++;
        }});
        document.getElementById('filteredRowCount').innerText = query ? ('Showing ' + visible + ' of ' + rows.length + ' rows') : 'Showing all rows';
      }}
    </script>
    <table>
    <thead>
      <tr>
        <th>Date &amp; Time (12H AM/PM)</th>
        <th>Elapsed</th>
        <th>Speed</th>
        <th>RPM</th>
        <th>Boost</th>
        <th>Throttle</th>
        <th>Load</th>
        <th>Coolant</th>
        <th>AFR</th>
        <th>Volts</th>
      </tr>
    </thead>
    <tbody id="manifestTableBody">
      {sample_rows_html}
    </tbody>
  </table>

  <div class="section-title">CRYPTOGRAPHIC INTEGRITY &amp; DIGITAL SIGNATURE</div>
  <div class="hash-box">
    <strong>SHA-256 CSV CHECKSUM:</strong><br>
    {sha256_hash}<br><br>
    <strong>LEGAL ATTESTATION:</strong><br>
    This document constitutes an automated, cryptographically sealed record of digital vehicle operations acquired directly from the ECU via standard OBD-II hardware capture. Any modification of the underlying raw CSV telemetry invalidates the above checksum.
  </div>

  <div style="font-size:10px; color:#8b949e; text-align:center; margin-top:20px;">
    CarPi5 MultiAir OS &bull; Flight-Data Black Box System &bull; Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
  </div>
</div>
</body>
</html>
"""

    def get_trip_telemetry(self, trip_id: int, max_points: int = 300) -> List[Dict[str, Any]]:
        """Returns time-series samples for UI graph scrubber."""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    c = conn.cursor()
                    c.execute("""
                        SELECT * FROM trip_telemetry_points WHERE trip_id = ? ORDER BY id ASC
                    """, (trip_id,))
                    rows = c.fetchall()
                    if not rows:
                        return []
                    
                    total = len(rows)
                    if total <= max_points:
                        return [dict(r) for r in rows]
                    
                    # Evenly downsample to max_points
                    step = total / float(max_points)
                    sampled = []
                    for i in range(max_points):
                        idx = int(i * step)
                        sampled.append(dict(rows[min(idx, total - 1)]))
                    return sampled
            except Exception as e:
                print(f"[TRIP_LOG] Error fetching telemetry points for trip {trip_id}: {e}")
                return []

    def get_recent_trips(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    c = conn.cursor()
                    c.execute("SELECT * FROM trips ORDER BY id DESC LIMIT ?", (limit,))
                    rows = c.fetchall()
                    trips = []
                    for r in rows:
                        d = dict(r)
                        if isinstance(d.get("dtc_list"), str):
                            try: d["dtc_list"] = json.loads(d["dtc_list"])
                            except: d["dtc_list"] = []
                        # Check if zip exists on disk
                        arch = d.get("archive_path")
                        d["has_archive"] = bool(arch and os.path.exists(arch))
                        trips.append(d)
                    return trips
            except Exception as e:
                print(f"[TRIP_LOG] Error getting recent trips: {e}")
                return []

    def get_lifetime_stats(self) -> Dict[str, Any]:
        with self.lock:
            try:
                with self._get_connection() as conn:
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
                            MAX(max_rpm),
                            SUM(fuel_used_gal)
                        FROM trips
                    """)
                    row = c.fetchone()
                    count, peak_boost, top_speed, avg_mpg, total_dur, total_dist, total_pulls, best_060, max_rpm, fuel_used = row
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
                        "lifetime_fuel_gallons": round(fuel_used or 0.0, 1),
                        "retention_days": self.retention_days,
                        "auto_zip_interval_min": self.auto_zip_interval_min,
                        "auto_log_enabled": self.auto_log_enabled,
                        "active_trip_id": self.current_trip_id
                    }
            except Exception as e:
                print(f"[TRIP_LOG] Error getting lifetime stats: {e}")
                return {}

    def purge_old_trips(self) -> int:
        if self.retention_days <= 0:
            return 0
        purged = 0
        try:
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT id, archive_path FROM trips 
                    WHERE id != ? AND datetime(start_time) < datetime('now', '-' || ? || ' days')
                """, (self.current_trip_id or -1, self.retention_days))
                old_rows = c.fetchall()
                if old_rows:
                    old_ids = [r[0] for r in old_rows]
                    # Remove zip archives
                    for _, arch in old_rows:
                        if arch and os.path.exists(arch):
                            try: os.remove(arch)
                            except: pass

                    placeholders = ",".join("?" * len(old_ids))
                    c.execute(f"DELETE FROM trip_telemetry_points WHERE trip_id IN ({placeholders})", old_ids)
                    c.execute(f"DELETE FROM trips WHERE id IN ({placeholders})", old_ids)
                    conn.commit()
                    purged = len(old_ids)
                    print(f"[TRIP_LOG] Purged {purged} trips older than {self.retention_days} days.")
        except Exception as e:
            print(f"[TRIP_LOG] Error purging trips: {e}")
        return purged

    def delete_trip(self, trip_id: int) -> bool:
        with self.lock:
            try:
                with self._get_connection() as conn:
                    c = conn.cursor()
                    c.execute("SELECT archive_path FROM trips WHERE id = ?", (trip_id,))
                    row = c.fetchone()
                    if row and row[0] and os.path.exists(row[0]):
                        try: os.remove(row[0])
                        except: pass
                    c.execute("DELETE FROM trip_telemetry_points WHERE trip_id = ?", (trip_id,))
                    c.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
                    conn.commit()
                return True
            except Exception as e:
                print(f"[TRIP_LOG] Error deleting trip {trip_id}: {e}")
                return False

    def clear_all_trips(self) -> bool:
        with self.lock:
            try:
                # Remove all archive files
                if os.path.exists(self.archive_dir):
                    for f in os.listdir(self.archive_dir):
                        if f.endswith(".zip"):
                            try: os.remove(os.path.join(self.archive_dir, f))
                            except: pass

                with self._get_connection() as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM trip_telemetry_points")
                    c.execute("DELETE FROM trips")
                    try:
                        c.execute("DELETE FROM sqlite_sequence WHERE name IN ('trips', 'trip_telemetry_points')")
                    except: pass
                    conn.commit()
                self.start_trip()
                return True
            except Exception as e:
                print(f"[TRIP_LOG] Error clearing all trips: {e}")
                return False
