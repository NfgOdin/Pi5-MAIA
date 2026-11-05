"""
obd_reader.py - Live OBD-II & CAN Telemetry Acquisition for 2013-2016 Dodge Dart 1.4T
Calibrated specifically for:
- 1.4L Turbo MultiAir (Magneti Marelli 8GM ECU, CAN 29/500 ISO 15765-4)
- Fiat C635 6-Speed Manual Transmission
- Globe, Arizona Atmospheric Elevation (~3,510 ft, P_atm ~88-89 kPa / 12.8-12.9 PSI)
- True resting hardware states (None / '--') when disconnected or ignition is off.
- Auto-baud detection across 38400 (standard CH340), 115200, 9600.
"""

import time
import os
import glob
import re
import math
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List

from .simulator import TelemetryFrame

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
        self.multiair_ready = False
        self.active_dtcs: List[str] = []
        
        # 0-60 Launch Tracker
        self.launch_start_time: Optional[float] = None
        self.last_0_60_time: Optional[float] = None
        self.is_launching = False

        self._try_connect()

    def find_serial_port(self) -> Optional[str]:
        """Auto-detect USB OBD-II adapter across Linux and Windows."""
        if self.preferred_port:
            return self.preferred_port

        # Linux / Raspberry Pi serial devices (CH340, FTDI, STN, ELM327)
        linux_candidates = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
        if linux_candidates:
            return linux_candidates[0]

        # Windows COM ports
        if os.name == 'nt':
            for com_num in range(1, 16):
                port_name = f"COM{com_num}"
                try:
                    import serial
                    s = serial.Serial(port_name)
                    s.close()
                    return port_name
                except Exception:
                    pass

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
                
                self._send_cmd("ATE0", timeout=0.25)     # Echo off
                self._send_cmd("ATL0", timeout=0.20)     # Linefeeds off
                self._send_cmd("ATH0", timeout=0.20)     # Headers off
                self._send_cmd("ATAT1", timeout=0.20)    # Adaptive timing enabled
                
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
        """Calculate active transmission gear on C635 6-speed manual from ratio."""
        if speed_mph < 2.5 or rpm < 500:
            return "N"

        speed_ms = speed_mph * 0.44704
        wheel_rpm = (speed_ms / TIRE_CIRCUMFERENCE_METERS) * 60.0
        if wheel_rpm < 1.0:
            return "N"

        current_ratio = (rpm / wheel_rpm) / FINAL_DRIVE

        best_gear = "N"
        min_diff = 0.32
        for g, ratio in GEAR_RATIOS.items():
            diff = abs(current_ratio - ratio)
            if diff < min_diff:
                min_diff = diff
                best_gear = g

        return best_gear

    def read_frame(self) -> TelemetryFrame:
        """Query live vehicle sensors using non-blocking staggered polling."""
        now = time.time()
        self.tick_count += 1

        if not self.serial_conn or (not self.connected and (now - self.last_attempt_time > 2.5)):
            self._try_connect()

        # If still disconnected, return pure resting states (no fake numbers)
        if not self.connected or not self.serial_conn:
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
                status_message=self.status_message
            )

        # Vehicle is connected - execute staggered PID queries for max smoothness
        try:
            # High-priority alternating queries:
            # Even ticks -> RPM (010C)
            # Odd ticks  -> MAP / Boost (010B)
            if self.tick_count % 2 == 0:
                rpm_raw = self._send_cmd("010C", timeout=0.35)
                m = re.search(r'41\s+0C\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{2})', rpm_raw)
                if m:
                    a = int(m.group(1), 16)
                    b = int(m.group(2), 16)
                    self.rpm = float(((a * 256) + b) / 4)
                    self.connected = True
                elif "UNABLE TO CONNECT" in rpm_raw or "BUS INIT" in rpm_raw:
                    self.connected = False
                    self.status_message = "IGNITION TURNED OFF"
            else:
                map_raw = self._send_cmd("010B", timeout=0.35)
                m = re.search(r'41\s+0B\s+([0-9A-Fa-f]{2})', map_raw)
                if m:
                    map_kpa = float(int(m.group(1), 16))
                    delta_p = map_kpa - self.baro_kpa
                    if delta_p > 0.4:
                        self.boost_psi = round(delta_p * 0.145038, 1)
                        self.vacuum_inhg = 0.0
                        self.is_in_boost = True
                    else:
                        self.boost_psi = 0.0
                        self.vacuum_inhg = round(abs(delta_p) * 0.2953, 0)
                        self.is_in_boost = False

            # Query Group 2: Speed (PID 010D) every 6 ticks
            if self.tick_count % 6 == 0:
                spd_raw = self._send_cmd("010D", timeout=0.35)
                m = re.search(r'41\s+0D\s+([0-9A-Fa-f]{2})', spd_raw)
                if m:
                    kph = float(int(m.group(1), 16))
                    self.speed_mph = kph * 0.621371

            # Query Group 3: Throttle (PID 0111) every 8 ticks
            if self.tick_count % 8 == 0:
                throt_raw = self._send_cmd("0111", timeout=0.35)
                m = re.search(r'41\s+11\s+([0-9A-Fa-f]{2})', throt_raw)
                if m:
                    self.throttle_pct = round((int(m.group(1), 16) * 100.0) / 255.0, 1)

            # Query Group 4: Coolant Temp (PID 0105) every 20 ticks (~1s)
            if self.tick_count % 20 == 0:
                clt_raw = self._send_cmd("0105", timeout=0.35)
                m = re.search(r'41\s+05\s+([0-9A-Fa-f]{2})', clt_raw)
                if m:
                    celsius = int(m.group(1), 16) - 40
                    self.coolant_temp_f = round(celsius * 9/5 + 32, 1)
                    self.multiair_ready = (self.coolant_temp_f >= 170.0)

            # Query Group 5: Intake Temp (PID 010F) every 25 ticks
            if self.tick_count % 25 == 0:
                iat_raw = self._send_cmd("010F", timeout=0.35)
                m = re.search(r'41\s+0F\s+([0-9A-Fa-f]{2})', iat_raw)
                if m:
                    celsius = int(m.group(1), 16) - 40
                    self.intake_temp_f = round(celsius * 9/5 + 32, 1)

            # Query Group 6: Battery Voltage (AT RV) every 50 ticks (~2s)
            if self.tick_count % 50 == 0:
                volt_raw = self._send_cmd("ATRV", timeout=0.25)
                v_match = re.search(r'([0-9]+\.[0-9]+)', volt_raw)
                if v_match:
                    self.battery_volts = round(float(v_match.group(1)), 1)

            # Query Group 7: Barometric Pressure (PID 0133) every 100 ticks
            if self.tick_count % 100 == 0:
                baro_raw = self._send_cmd("0133", timeout=0.35)
                m = re.search(r'41\s+33\s+([0-9A-Fa-f]{2})', baro_raw)
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

        # Calculate active transmission gear
        self.gear = self._calculate_gear(self.speed_mph, self.rpm)

        # Sequential F1 Shift Lights for 1.4T MultiAir
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
            status_message=self.status_message
        )
