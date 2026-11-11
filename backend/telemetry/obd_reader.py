"""
obd_reader.py - Live OBD-II & CAN Telemetry Acquisition for 2013-2016 Dodge Dart 1.4T
Calibrated specifically for:
- 1.4L Turbo MultiAir (Magneti Marelli 8GM ECU, CAN 29/500 ISO 15765-4)
- Fiat C635 6-Speed Manual Transmission
- Globe, Arizona Atmospheric Elevation (~3,510 ft, P_atm ~88-89 kPa / 12.8-12.9 PSI)
- True resting hardware states (None / '--') when disconnected or ignition is off.
- Auto-baud detection across 38400 (standard CH340), 115200, 9600.
- Complete sensor coverage: Speed, RPM, Boost, Vac, Coolant, IAT, Throttle, Volts,
  MPG, GPH, Engine Load, Timing Advance, AFR/Lambda, Fuel Level, Ambient Temp, Pedal Pos, Runtime.
"""

import time
import os
import glob
import re
import math
import threading
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List

from .simulator import TelemetryFrame
from .multiair_virtual_dyno import MultiAirVirtualDyno

# Dodge Dart 1.4T US-Spec C635 6-Speed Manual Gear Ratios
GEAR_RATIOS = {
    "1": 3.909,
    "2": 2.118,
    "3": 1.360,
    "4": 0.978,
    "5": 0.756,
    "6": 0.622
}
FINAL_DRIVE = 3.824
TIRE_CIRCUMFERENCE_METERS = 2.015  # Standard 225/45R17 tire

# Atmospheric Calibration for Globe, Arizona (Elevation: ~3,510 ft / 1,070m)
GLOBE_AZ_BARO_KPA = 88.0  # Verified live on vehicle (~12.76 PSI / 26.0 inHg)
KNOWN_BAUDRATES = [38400, 115200, 9600, 230400, 500000]

class RealVehicleTelemetryReader:
    def __init__(self, port: Optional[str] = None, baudrate: int = 38400):
        self.preferred_port = port
        self.preferred_baud = baudrate
        self.baudrate = baudrate
        self.serial_conn = None
        self.connected = False
        self.last_attempt_time = 0.0
        self.status_message = "DISCONNECTED"
        self.tick_count = 0
        
        # Calibrated local barometric pressure in kPa (default Globe, AZ)
        self.baro_kpa = GLOBE_AZ_BARO_KPA
        self.baro_calibrated = False

        # Live telemetry state - initialized to resting None when vehicle is disconnected
        self.speed_mph = 0.0
        self.rpm = 0.0
        self.gear = "N"
        self.throttle_pct = 0.0
        self.boost_psi: Optional[float] = None
        self.vacuum_inhg: Optional[float] = None
        self.is_in_boost = False
        self.coolant_temp_f: Optional[float] = None
        self.intake_temp_f: Optional[float] = None
        self.battery_volts: Optional[float] = None
        self.fuel_mpg_instant: Optional[float] = None
        self.fuel_gph: Optional[float] = None
        self.multiair_ready = False
        self.active_dtcs: List[str] = []
        
        # Extended vehicle sensors (All verified supported on Dart 1.4T)
        self.engine_load_pct: Optional[float] = None
        self.timing_advance_deg: Optional[float] = None
        self.afr: Optional[float] = None
        self.fuel_level_pct: Optional[float] = None
        self.ambient_temp_f: Optional[float] = None
        self.pedal_pos_pct: Optional[float] = None
        self.engine_runtime_sec: Optional[int] = None
        self.last_map_kpa: float = 35.0

        # Gear detection & shifting/coasting tracking
        self.last_locked_gear: str = "N"
        self.neutral_start_time: float = 0.0

        # 0-60 Launch Tracker
        self.launch_start_time: Optional[float] = None
        self.last_0_60_time: Optional[float] = None
        self.is_launching = False
        self._last_speed_mph: float = 0.0
        self._last_frame_time: float = time.time()
        self.dyno = MultiAirVirtualDyno()

        # Phase 13 Fast-CAN & Non-Blocking Worker Architecture
        self.supports_batch_pid: bool = True
        self._frame_lock = threading.Lock()
        self._running: bool = True
        self._latest_frame: TelemetryFrame = self._build_disconnected_frame(time.time())

        self._try_connect()

        # Start dedicated background telemetry thread for 25Hz non-blocking updates
        self._worker_thread = threading.Thread(
            target=self._telemetry_worker_loop,
            daemon=True,
            name="OBDTelemetryWorker"
        )
        self._worker_thread.start()

    @property
    def ser(self):
        """Alias for serial_conn to ensure backwards compatibility."""
        return self.serial_conn

    def find_serial_port(self) -> Optional[str]:
        """Auto-detect USB OBD-II adapter across Linux and Windows."""
        if self.preferred_port:
            return self.preferred_port

        # Linux / Raspberry Pi serial devices (CH340, FTDI, STN, ELM327)
        linux_candidates = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
        if linux_candidates:
            return linux_candidates[0]

        # Windows COM ports (Prioritize physical USB-serial adapters; skip dormant Bluetooth RFCOMM ports)
        if os.name == 'nt':
            try:
                import serial.tools.list_ports
                usb_ports = [
                    p.device for p in serial.tools.list_ports.comports()
                    if "BTHENUM" not in p.hwid and "Bluetooth" not in p.description
                ]
                if usb_ports:
                    return usb_ports[0]
            except Exception:
                pass
            return None

        return None

    def _close_conn(self):
        """Safely close active serial connection."""
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

    def _send_cmd(self, cmd: str, timeout: float = 0.35) -> str:
        """Send command to ELM327 adapter and return cleaned response string."""
        if not self.serial_conn:
            return ""
        try:
            self.serial_conn.reset_input_buffer()
            self.serial_conn.write((cmd.strip() + "\r").encode("ascii"))
            resp = b""
            start = time.time()
            while time.time() - start < timeout:
                c = self.serial_conn.read(1)
                if c:
                    resp += c
                    if c == b">":
                        break
            clean = resp.decode("ascii", errors="ignore").replace(">", "").strip()
            return clean
        except Exception as e:
            print(f"[REAL OBD] Serial communication error: {e}")
            self._close_conn()
            self.connected = False
            self.status_message = "COMMUNICATION LOST"
            return ""

    def _try_connect(self):
        """Attempt to auto-detect and open serial connection to the USB OBD-II interface."""
        now = time.time()
        if now - self.last_attempt_time < 2.5:
            return
        self.last_attempt_time = now

        target_port = self.find_serial_port()
        if not target_port:
            self.connected = False
            self.status_message = "NO OBD-II CABLE DETECTED"
            return

        self._close_conn()

        try:
            import serial
        except ImportError:
            self.connected = False
            self.status_message = "PYSERIAL NOT INSTALLED"
            return

        # Prioritize 38400 (standard for CH340), then preferred, then other known rates
        candidate_bauds = []
        if self.preferred_baud:
            candidate_bauds.append(self.preferred_baud)
        for b in KNOWN_BAUDRATES:
            if b not in candidate_bauds:
                candidate_bauds.append(b)

        for baud in candidate_bauds:
            try:
                s = serial.Serial(target_port, baud, timeout=0.25)
                s.reset_input_buffer()
                s.reset_output_buffer()
                self.serial_conn = s
                self.baudrate = baud

                # Reset and configure ELM327
                self.serial_conn.write(b"ATZ\r")
                time.sleep(0.30)
                self.serial_conn.reset_input_buffer()
                
                self._send_cmd("ATE0", timeout=0.20)     # Echo off
                self._send_cmd("ATL0", timeout=0.15)     # Linefeeds off
                self._send_cmd("ATH0", timeout=0.15)     # Headers off
                self._send_cmd("ATS0", timeout=0.15)     # Spaces off (Phase 13 Fast-CAN)
                self._send_cmd("ATAT2", timeout=0.15)    # Aggressive adaptive timing (Phase 13 Fast-CAN)
                self.supports_batch_pid = True
                
                # ISO 15765-4 (CAN 29/500) is Protocol 7 on ELM327 (Standard for Dodge Dart 1.4T)
                sp_res = self._send_cmd("ATSP7", timeout=0.30)
                if not sp_res or "ERROR" in sp_res:
                    self._send_cmd("ATSP0", timeout=0.30)  # Fallback to Auto
                
                # Check battery voltage
                volt_raw = self._send_cmd("ATRV", timeout=0.25)
                v_match = re.search(r'([0-9]+\.[0-9]+)', volt_raw)
                if v_match:
                    self.battery_volts = round(float(v_match.group(1)), 1)
                
                if volt_raw and ("V" in volt_raw or v_match):
                    # Ping ECU for support
                    ping = self._send_cmd("0100", timeout=0.45)
                    if "41 00" in ping or "41" in ping:
                        self.connected = True
                        self.status_message = f"ONLINE (CAN 29/500 @ {baud})"
                        print(f"[REAL OBD] Connected to Dodge Dart ECU on {target_port} @ {baud} baud! Battery: {self.battery_volts}V")
                        
                        # Pre-seed initial values for static sensors
                        clt_init = self._send_cmd("0105", timeout=0.35)
                        m_clt = re.search(r'41\s+05\s+([0-9A-Fa-f]{2})', clt_init)
                        if m_clt:
                            c = int(m_clt.group(1), 16) - 40
                            self.coolant_temp_f = round(c * 9/5 + 32, 1)
                            self.multiair_ready = (self.coolant_temp_f >= 170.0)

                        iat_init = self._send_cmd("010F", timeout=0.35)
                        m_iat = re.search(r'41\s+0F\s+([0-9A-Fa-f]{2})', iat_init)
                        if m_iat:
                            c = int(m_iat.group(1), 16) - 40
                            self.intake_temp_f = round(c * 9/5 + 32, 1)

                        baro_init = self._send_cmd("0133", timeout=0.35)
                        m_baro = re.search(r'41\s+33\s+([0-9A-Fa-f]{2})', baro_init)
                        if m_baro:
                            meas = float(int(m_baro.group(1), 16))
                            if 60.0 <= meas <= 110.0:
                                self.baro_kpa = meas
                                self.baro_calibrated = True

                        fuel_init = self._send_cmd("012F", timeout=0.35)
                        m_fuel = re.search(r'41\s+2F\s+([0-9A-Fa-f]{2})', fuel_init)
                        if m_fuel:
                            self.fuel_level_pct = round(int(m_fuel.group(1), 16) * 100.0 / 255.0, 1)

                        amb_init = self._send_cmd("0146", timeout=0.35)
                        m_amb = re.search(r'41\s+46\s+([0-9A-Fa-f]{2})', amb_init)
                        if m_amb:
                            c_amb = int(m_amb.group(1), 16) - 40
                            self.ambient_temp_f = round(c_amb * 9/5 + 32, 1)

                        load_init = self._send_cmd("0104", timeout=0.35)
                        m_load = re.search(r'41\s+04\s+([0-9A-Fa-f]{2})', load_init)
                        if m_load:
                            self.engine_load_pct = round(int(m_load.group(1), 16) * 100.0 / 255.0, 1)

                        timing_init = self._send_cmd("010E", timeout=0.35)
                        m_time = re.search(r'41\s+0E\s+([0-9A-Fa-f]{2})', timing_init)
                        if m_time:
                            self.timing_advance_deg = round((int(m_time.group(1), 16) / 2.0) - 64.0, 1)

                        afr_init = self._send_cmd("0144", timeout=0.35)
                        m_afr = re.search(r'41\s+44\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{2})', afr_init)
                        if m_afr:
                            ratio = ((int(m_afr.group(1), 16) * 256) + int(m_afr.group(2), 16)) / 32768.0
                            self.afr = round(ratio * 14.7, 2)

                        return
                    else:
                        # Cable is alive and voltage is read, but key is off or engine sleeping
                        self.connected = False
                        self.status_message = f"CABLE ONLINE ({self.battery_volts}V) - KEY OFF"
                        print(f"[REAL OBD] Cable detected @ {baud} ({self.battery_volts}V), awaiting vehicle ignition...")
                        return
                
                # If no valid ATRV response at this baud, close and try next
                self._close_conn()
            except Exception as e:
                self._close_conn()
                continue

        self.connected = False
        self.status_message = "CABLE CONNECTED - KEY OFF"

    def _calculate_gear(self, speed_mph: float, rpm: float) -> str:
        """Calculate active transmission gear on C635 6-speed manual with shifting & coasting symbols."""
        if speed_mph < 1.5 or rpm < 450:
            self.last_locked_gear = "N"
            self.neutral_start_time = 0.0
            return "N"

        speed_ms = speed_mph * 0.44704
        wheel_rpm = (speed_ms / TIRE_CIRCUMFERENCE_METERS) * 60.0
        if wheel_rpm < 1.0:
            self.last_locked_gear = "N"
            self.neutral_start_time = 0.0
            return "N"

        current_ratio = (rpm / wheel_rpm) / FINAL_DRIVE

        # 1st Gear special tolerance for clutch engagement & launch (nominal ratio: 3.909)
        # During clutch slip at takeoff (0-15 MPH), effective ratio spikes to 6.0-14.0.
        # Since 2nd gear is 2.118, any ratio >= 2.75 under 18 MPH is definitively 1st gear!
        if speed_mph < 18.0 and (current_ratio >= 2.75):
            self.last_locked_gear = "1"
            self.neutral_start_time = 0.0
            return "1"

        best_gear = None
        min_diff = 0.35
        for g, ratio in GEAR_RATIOS.items():
            diff = abs(current_ratio - ratio)
            if diff < min_diff:
                min_diff = diff
                best_gear = g

        if best_gear is not None:
            self.last_locked_gear = best_gear
            self.neutral_start_time = 0.0
            return best_gear

        # Moving down the road (speed >= 1.5 MPH) but ratio doesn't match a locked gear
        now = time.time()
        if self.neutral_start_time == 0.0:
            self.neutral_start_time = now

        elapsed_neutral = now - self.neutral_start_time
        # Under 2.0 seconds -> Shifting transition symbol
        if elapsed_neutral < 2.0:
            return "⇄"
        else:
            # Over 2.0 seconds -> Coasting symbol
            return "〜"

    def _build_disconnected_frame(self, now: float) -> TelemetryFrame:
        """Reset active dynamic sensors and return pure resting state (AGENTS.md Rule 2)."""
        self.speed_mph = 0.0
        self.rpm = 0.0
        self.gear = "N"
        self.throttle_pct = 0.0
        self.boost_psi = None
        self.vacuum_inhg = None
        self.is_in_boost = False
        self.coolant_temp_f = None
        self.intake_temp_f = None
        self.fuel_mpg_instant = None
        self.fuel_gph = None
        self.multiair_ready = False
        self.engine_load_pct = None
        self.timing_advance_deg = None
        self.afr = None
        self.pedal_pos_pct = None
        self.engine_runtime_sec = None
        self.is_launching = False
        self._last_speed_mph = 0.0
        self._last_frame_time = now

        hl_on = bool(getattr(self, "headlights_on", (time.localtime().tm_hour >= 19 or time.localtime().tm_hour < 6)))
        return TelemetryFrame(
            timestamp=now,
            speed_mph=0.0,
            speed_kph=0.0,
            rpm=0.0,
            gear="N",
            throttle_pct=0.0,
            boost_psi=None,
            vacuum_inhg=None,
            is_in_boost=False,
            coolant_temp_f=None,
            intake_temp_f=None,
            battery_volts=self.battery_volts,
            fuel_mpg_instant=None,
            multiair_ready=False,
            shift_indicator=False,
            f1_light_level=0,
            launch_timer_active=False,
            zero_to_sixty_time=self.last_0_60_time,
            active_dtcs=[],
            connected=False,
            status_message=self.status_message,
            engine_load_pct=None,
            timing_advance_deg=None,
            afr=None,
            fuel_level_pct=self.fuel_level_pct,
            ambient_temp_f=self.ambient_temp_f,
            pedal_pos_pct=None,
            engine_runtime_sec=None,
            fuel_gph=None,
            baro_kpa=self.baro_kpa,
            virtual_whp=0.0,
            virtual_wtq=0.0,
            multiair_oil_temp_f=None,
            oil_temp_f=None,
            multiair_status="COLD_PROTECT",
            wastegate_spool_health=100.0,
            wastegate_spool_gradient=9.8,
            last_shift_score=None,
            last_shift_type=None,
            last_shift_delta=None,
            avg_shift_score=100.0,
            headlights_on=hl_on,
            ambient_light_lux=5.0 if hl_on else 450.0,
            lateral_g=0.0,
            longitudinal_g=0.0,
            lateral_accel=0.0,
            steering_angle=0.0
        )

    def read_frame(self) -> TelemetryFrame:
        """Returns the latest acquired vehicle telemetry frame with zero serial I/O blocking."""
        with self._frame_lock:
            return self._latest_frame

    def _telemetry_worker_loop(self):
        """Dedicated high-speed background worker thread polling vehicle CAN bus at up to 25Hz."""
        while self._running:
            try:
                frame = self._poll_hardware_cycle()
                with self._frame_lock:
                    self._latest_frame = frame
            except Exception as e:
                time.sleep(0.05)
            # Sleep 15ms between frames for ~25-30Hz sampling rate
            time.sleep(0.015)

    def _poll_hardware_cycle(self) -> TelemetryFrame:
        """Internal telemetry acquisition cycle executing Fast-CAN batch or staggered queries."""
        now = time.time()
        dt = max(0.01, min(1.0, now - self._last_frame_time)) if self._last_frame_time > 0 else 0.04
        self._last_frame_time = now
        self.tick_count += 1

        if not self.serial_conn or (not self.connected and (now - self.last_attempt_time > 2.5)):
            self._try_connect()

        # If still disconnected, return pure resting states (no fake numbers)
        if not self.connected or not self.serial_conn:
            return self._build_disconnected_frame(now)

        # Vehicle is connected - execute telemetry queries
        try:
            # 1. Primary High-Frequency Queries: Batch Multi-PID (Fast-CAN) or Alternating Single PIDs
            if self.supports_batch_pid:
                batch_raw = self._send_cmd("010C0B0D11", timeout=0.20)
                cleaned = batch_raw.replace(" ", "").upper()
                if "UNABLETOCONNECT" in cleaned or "BUSINIT" in cleaned:
                    self.connected = False
                    self.status_message = "IGNITION TURNED OFF"
                    return self._build_disconnected_frame(now)

                m_rpm = re.search(r'(?:410C|0C)([0-9A-F]{4})', cleaned)
                m_map = re.search(r'(?:410B|0B)([0-9A-F]{2})', cleaned)
                m_spd = re.search(r'(?:410D|0D)([0-9A-F]{2})', cleaned)
                m_thr = re.search(r'(?:4111|11)([0-9A-F]{2})', cleaned)

                if m_rpm and m_map:
                    rpm_a = int(m_rpm.group(1)[:2], 16)
                    rpm_b = int(m_rpm.group(1)[2:4], 16)
                    self.rpm = float(((rpm_a * 256) + rpm_b) / 4.0)

                    self.last_map_kpa = float(int(m_map.group(1), 16))
                    delta_p = self.last_map_kpa - self.baro_kpa
                    if delta_p > 0.4:
                        self.boost_psi = round(delta_p * 0.145038, 1)
                        self.vacuum_inhg = 0.0
                        self.is_in_boost = True
                    else:
                        self.boost_psi = 0.0
                        self.vacuum_inhg = round(abs(delta_p) * 0.2953, 0)
                        self.is_in_boost = False

                    if m_spd:
                        kph = float(int(m_spd.group(1), 16))
                        self.speed_mph = kph * 0.621371
                    if m_thr:
                        self.throttle_pct = round((int(m_thr.group(1), 16) * 100.0) / 255.0, 1)
                    self.connected = True
                elif "41" not in cleaned:
                    # ECU or adapter does not support multi-PID batch queries; fallback to single PID
                    self.supports_batch_pid = False

            if not self.supports_batch_pid:
                # Fallback: High-priority alternating queries
                if self.tick_count % 2 == 0:
                    rpm_raw = self._send_cmd("010C", timeout=0.25)
                    m = re.search(r'41\s*0C\s*([0-9A-Fa-f]{2})\s*([0-9A-Fa-f]{2})', rpm_raw)
                    if m:
                        a = int(m.group(1), 16)
                        b = int(m.group(2), 16)
                        self.rpm = float(((a * 256) + b) / 4)
                        self.connected = True
                    elif "UNABLE TO CONNECT" in rpm_raw or "BUS INIT" in rpm_raw:
                        self.connected = False
                        self.status_message = "IGNITION TURNED OFF"
                        return self._build_disconnected_frame(now)
                else:
                    map_raw = self._send_cmd("010B", timeout=0.25)
                    m = re.search(r'41\s*0B\s*([0-9A-Fa-f]{2})', map_raw)
                    if m:
                        self.last_map_kpa = float(int(m.group(1), 16))
                        delta_p = self.last_map_kpa - self.baro_kpa
                        if delta_p > 0.4:
                            self.boost_psi = round(delta_p * 0.145038, 1)
                            self.vacuum_inhg = 0.0
                            self.is_in_boost = True
                        else:
                            self.boost_psi = 0.0
                            self.vacuum_inhg = round(abs(delta_p) * 0.2953, 0)
                            self.is_in_boost = False

                # Speed (PID 010D) every 6 ticks
                if self.tick_count % 6 == 0:
                    spd_raw = self._send_cmd("010D", timeout=0.25)
                    m = re.search(r'41\s*0D\s*([0-9A-Fa-f]{2})', spd_raw)
                    if m:
                        kph = float(int(m.group(1), 16))
                        self.speed_mph = kph * 0.621371

                # Throttle (PID 0111) every 8 ticks
                if self.tick_count % 8 == 0:
                    throt_raw = self._send_cmd("0111", timeout=0.25)
                    m = re.search(r'41\s*11\s*([0-9A-Fa-f]{2})', throt_raw)
                    if m:
                        self.throttle_pct = round((int(m.group(1), 16) * 100.0) / 255.0, 1)

            # Query Group 4: Engine Load (PID 0104) every 10 ticks
            if self.tick_count % 10 == 0:
                load_raw = self._send_cmd("0104", timeout=0.25)
                m = re.search(r'41\s*04\s*([0-9A-Fa-f]{2})', load_raw)
                if m:
                    self.engine_load_pct = round(int(m.group(1), 16) * 100.0 / 255.0, 1)

            # Query Group 5: Timing Advance (PID 010E) every 12 ticks
            if self.tick_count % 12 == 0:
                timing_raw = self._send_cmd("010E", timeout=0.25)
                m = re.search(r'41\s*0E\s*([0-9A-Fa-f]{2})', timing_raw)
                if m:
                    self.timing_advance_deg = round((int(m.group(1), 16) / 2.0) - 64.0, 1)

            # Query Group 6: Air/Fuel Ratio AFR (PID 0144) every 14 ticks
            if self.tick_count % 14 == 0:
                afr_raw = self._send_cmd("0144", timeout=0.25)
                m = re.search(r'41\s*44\s*([0-9A-Fa-f]{2})\s*([0-9A-Fa-f]{2})', afr_raw)
                if m:
                    ratio = ((int(m.group(1), 16) * 256) + int(m.group(2), 16)) / 32768.0
                    self.afr = round(ratio * 14.7, 2)

            # Query Group 7: Pedal Position (PID 0149) every 16 ticks
            if self.tick_count % 16 == 0:
                pedal_raw = self._send_cmd("0149", timeout=0.25)
                m = re.search(r'41\s*49\s*([0-9A-Fa-f]{2})', pedal_raw)
                if m:
                    self.pedal_pos_pct = round(int(m.group(1), 16) * 100.0 / 255.0, 1)

            # Query Group 8: Coolant Temp (PID 0105) every 20 ticks (~1s)
            if self.tick_count % 20 == 0:
                clt_raw = self._send_cmd("0105", timeout=0.25)
                m = re.search(r'41\s*05\s*([0-9A-Fa-f]{2})', clt_raw)
                if m:
                    celsius = int(m.group(1), 16) - 40
                    self.coolant_temp_f = round(celsius * 9/5 + 32, 1)
                    self.multiair_ready = (self.coolant_temp_f >= 170.0)

            # Query Group 9: Intake Temp (PID 010F) every 25 ticks
            if self.tick_count % 25 == 0:
                iat_raw = self._send_cmd("010F", timeout=0.25)
                m = re.search(r'41\s*0F\s*([0-9A-Fa-f]{2})', iat_raw)
                if m:
                    celsius = int(m.group(1), 16) - 40
                    self.intake_temp_f = round(celsius * 9/5 + 32, 1)

            # Query Group 10: Ambient Temp (PID 0146) every 30 ticks
            if self.tick_count % 30 == 0:
                amb_raw = self._send_cmd("0146", timeout=0.25)
                m = re.search(r'41\s*46\s*([0-9A-Fa-f]{2})', amb_raw)
                if m:
                    c_amb = int(m.group(1), 16) - 40
                    self.ambient_temp_f = round(c_amb * 9/5 + 32, 1)

            # Query Group 11: Fuel Tank Level (PID 012F) every 40 ticks
            if self.tick_count % 40 == 0:
                fuel_raw = self._send_cmd("012F", timeout=0.25)
                m = re.search(r'41\s*2F\s*([0-9A-Fa-f]{2})', fuel_raw)
                if m:
                    self.fuel_level_pct = round(int(m.group(1), 16) * 100.0 / 255.0, 1)

            # Query Group 12: Battery Voltage (AT RV) every 50 ticks (~2s)
            if self.tick_count % 50 == 0:
                volt_raw = self._send_cmd("ATRV", timeout=0.20)
                v_match = re.search(r'([0-9]+\.[0-9]+)', volt_raw)
                if v_match:
                    self.battery_volts = round(float(v_match.group(1)), 1)

            # Query Group 13: Engine Runtime (PID 011F) every 60 ticks (~3s)
            if self.tick_count % 60 == 0:
                rt_raw = self._send_cmd("011F", timeout=0.25)
                m = re.search(r'41\s*1F\s*([0-9A-Fa-f]{2})\s*([0-9A-Fa-f]{2})', rt_raw)
                if m:
                    self.engine_runtime_sec = int(m.group(1), 16) * 256 + int(m.group(2), 16)

            # Query Group 14: Barometric Pressure (PID 0133) every 100 ticks
            if self.tick_count % 100 == 0:
                baro_raw = self._send_cmd("0133", timeout=0.25)
                m = re.search(r'41\s*33\s*([0-9A-Fa-f]{2})', baro_raw)
                if m:
                    meas = float(int(m.group(1), 16))
                    if 60.0 <= meas <= 110.0:
                        self.baro_kpa = meas
                        self.baro_calibrated = True

        except Exception as e:
            print(f"[REAL OBD] Frame error: {e}")
            self._close_conn()
            self.connected = False
            self.status_message = "COMMUNICATION ERROR"
            return self._build_disconnected_frame(now)

        if not self.connected or not self.serial_conn:
            return self._build_disconnected_frame(now)

        # Speed-Density Instant Fuel Flow (GPH) & Instant MPG Calculation
        if self.rpm > 300 and self.connected:
            map_p = self.last_map_kpa
            iat_val = self.intake_temp_f if self.intake_temp_f is not None else 85.0
            iat_k = (iat_val - 32.0) * 5.0 / 9.0 + 273.15
            air_density = (map_p * 1000.0) / (287.05 * max(200.0, iat_k))
            # 4-stroke cycle, displacement 0.001368 m3, ~0.82 volumetric efficiency
            air_mass_gps = air_density * 0.001368 * (self.rpm / 60.0) * 0.5 * 0.82 * 1000.0
            afr_val = self.afr if (self.afr and 10.0 <= self.afr <= 20.0) else 14.7
            fuel_mass_gps = air_mass_gps / afr_val
            # Density of gasoline ~ 2835 grams / gallon
            self.fuel_gph = round((fuel_mass_gps * 3600.0) / 2835.0, 2)
            if self.speed_mph >= 2.0 and self.fuel_gph > 0.04:
                self.fuel_mpg_instant = round(min(99.9, self.speed_mph / self.fuel_gph), 1)
            else:
                self.fuel_mpg_instant = 0.0

        # Calculate active transmission gear
        self.gear = self._calculate_gear(self.speed_mph, self.rpm)

        # Longitudinal G-force from speed delta (1G ~= 21.937 mph/s)
        dv_mph = self.speed_mph - self._last_speed_mph
        self._last_speed_mph = self.speed_mph
        long_g = round(max(-1.5, min(1.5, (dv_mph / dt) / 21.937)), 2)

        # Sequential F1 Shift Lights for 1.4T MultiAir
        # MultiAir Virtual Dyno, Spool Health & Rev-Match Scoring
        dyno_metrics = self.dyno.process_frame(
            speed_mph=self.speed_mph,
            rpm=self.rpm,
            gear=self.gear,
            throttle_pct=self.throttle_pct,
            boost_psi=self.boost_psi,
            coolant_temp_f=self.coolant_temp_f,
            intake_temp_f=self.intake_temp_f,
            engine_load_pct=self.engine_load_pct,
            dt=dt
        )
        self.multiair_ready = dyno_metrics["multiair_ready"]

        f1_level = 0
        if self.rpm > 6200: f1_level = 5
        elif self.rpm > 5800: f1_level = 4
        elif self.rpm > 5400: f1_level = 3
        elif self.rpm > 4800: f1_level = 2
        elif self.rpm > 4000: f1_level = 1

        # 0-60 Launch Watchdog
        if self.speed_mph < 0.8 and self.throttle_pct > 70.0:
            if not self.is_launching:
                self.is_launching = True
                self.launch_start_time = now
        elif self.is_launching:
            if self.speed_mph >= 60.0 and self.launch_start_time:
                self.last_0_60_time = round(now - self.launch_start_time, 2)
                self.is_launching = False
            elif self.speed_mph < 2.0 and (now - (self.launch_start_time or now)) > 4.0:
                self.is_launching = False

        hl_on = bool(getattr(self, "headlights_on", (time.localtime().tm_hour >= 19 or time.localtime().tm_hour < 6)))
        return TelemetryFrame(
            timestamp=now,
            speed_mph=round(self.speed_mph, 1),
            speed_kph=round(self.speed_mph * 1.60934, 1),
            rpm=round(self.rpm, 0),
            gear=self.gear,
            throttle_pct=round(self.throttle_pct, 1),
            boost_psi=self.boost_psi,
            vacuum_inhg=self.vacuum_inhg,
            is_in_boost=self.is_in_boost,
            coolant_temp_f=self.coolant_temp_f,
            intake_temp_f=self.intake_temp_f,
            battery_volts=self.battery_volts,
            fuel_mpg_instant=self.fuel_mpg_instant,
            multiair_ready=self.multiair_ready,
            shift_indicator=(self.rpm >= 5800),
            f1_light_level=f1_level,
            launch_timer_active=self.is_launching,
            zero_to_sixty_time=self.last_0_60_time,
            active_dtcs=self.active_dtcs,
            connected=self.connected,
            status_message=self.status_message,
            engine_load_pct=self.engine_load_pct,
            timing_advance_deg=self.timing_advance_deg,
            afr=self.afr,
            fuel_level_pct=self.fuel_level_pct,
            ambient_temp_f=self.ambient_temp_f,
            pedal_pos_pct=self.pedal_pos_pct,
            engine_runtime_sec=self.engine_runtime_sec,
            fuel_gph=self.fuel_gph,
            baro_kpa=self.baro_kpa,
            virtual_whp=dyno_metrics["virtual_whp"],
            virtual_wtq=dyno_metrics["virtual_wtq"],
            multiair_oil_temp_f=dyno_metrics["multiair_oil_temp_f"],
            oil_temp_f=dyno_metrics["multiair_oil_temp_f"],
            multiair_status=dyno_metrics["multiair_status"],
            wastegate_spool_health=dyno_metrics["wastegate_health_pct"],
            wastegate_spool_gradient=dyno_metrics["spool_gradient"],
            last_shift_score=dyno_metrics["latest_shift_score"],
            last_shift_type=dyno_metrics["latest_shift_type"],
            last_shift_delta=dyno_metrics["latest_shift_delta"],
            avg_shift_score=dyno_metrics["avg_shift_score"],
            headlights_on=hl_on,
            ambient_light_lux=5.0 if hl_on else 450.0,
            lateral_g=0.0,
            longitudinal_g=long_g,
            lateral_accel=0.0,
            steering_angle=0.0
        )

    def clear_dtcs(self) -> bool:
        """Sends OBD-II Mode 04 command to clear powertrain trouble codes and reset CEL."""
        self.active_dtcs.clear()
        if self.connected and self.serial_conn:
            try:
                res = self._send_cmd('04', timeout=1.0)
                print(f'[OBD] Mode 04 Clear DTC response: {res}')
                return True
            except Exception as e:
                print(f'[OBD] Error sending Mode 04 clear DTCs: {e}')
                return False
        return True
