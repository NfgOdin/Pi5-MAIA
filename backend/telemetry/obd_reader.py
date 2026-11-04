"""
obd_reader.py - Live OBD-II & CAN Telemetry Acquisition for 2013-2016 Dodge Dart 1.4T
Calibrated specifically for:
- 1.4L Turbo MultiAir (Magneti Marelli 8GM ECU)
- Fiat C635 6-Speed Manual Transmission
- Globe, Arizona Atmospheric Elevation (~3,510 ft, P_atm ~89.2 kPa / 12.94 PSI)
- True resting hardware states (None / '--') when disconnected or ignition is off.
"""

import time
import os
import glob
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
GLOBE_AZ_BARO_KPA = 89.2  # ~12.94 PSI / 26.34 inHg

class RealVehicleTelemetryReader:
    def __init__(self, port: Optional[str] = None, baudrate: int = 115200):
        self.preferred_port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.connected = False
        self.last_attempt_time = 0.0
        self.status_message = "DISCONNECTED"
        
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

        # Linux / Raspberry Pi serial devices (FTDI, STN, ELM327)
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

    def _try_connect(self):
        """Attempt to open serial connection to the USB OBD-II interface."""
        now = time.time()
        if now - self.last_attempt_time < 3.0:
            return
        self.last_attempt_time = now

        target_port = self.find_serial_port()
        if not target_port:
            self.connected = False
            self.status_message = "NO OBD-II CABLE DETECTED"
            return

        try:
            import serial
            self.serial_conn = serial.Serial(target_port, self.baudrate, timeout=0.12)
            # Initialize ELM327 / STN commands
            self._send_cmd("AT Z")      # Reset adapter
            time.sleep(0.08)
            self._send_cmd("AT E0")     # Echo off
            self._send_cmd("AT L0")     # Linefeeds off
            self._send_cmd("AT SP 6")   # ISO 15765-4 CAN 11-bit 500k (Dodge Dart standard)
            
            # Test ping with battery voltage command
            resp = self._send_cmd("AT RV")
            if resp and "V" in resp:
                self.connected = True
                self.status_message = f"ONLINE ({os.path.basename(target_port)})"
                print(f"[REAL OBD] Connected to Dodge Dart OBD-II on {target_port}")
            else:
                self.connected = False
                self.status_message = "CABLE CONNECTED - KEY OFF"
        except Exception as e:
            self.connected = False
            self.status_message = f"PORT ERROR: {e}"

    def _send_cmd(self, cmd: str) -> str:
        """Send command to ELM327 adapter and return cleaned response string."""
        if not self.serial_conn:
            return ""
        try:
            self.serial_conn.write((cmd.strip() + "\r").encode("ascii"))
            resp = b""
            start = time.time()
            while time.time() - start < 0.10:
                chunk = self.serial_conn.read(64)
                if chunk:
                    resp += chunk
                    if b">" in resp:
                        break
            return resp.decode("ascii", errors="ignore").replace(">", "").strip()
        except Exception:
            self.connected = False
            return ""

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
        """Query live vehicle sensors or return resting safe telemetry if disconnected."""
        now = time.time()

        if not self.connected or not self.serial_conn:
            self._try_connect()

        # If still disconnected, return pure resting states (no fake numbers)
        if not self.connected:
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
                battery_volts=None,
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

        # Vehicle is connected - query live PIDs
        try:
            # 1. Battery Voltage (AT RV)
            volt_raw = self._send_cmd("AT RV")
            if "V" in volt_raw:
                try:
                    self.battery_volts = round(float(volt_raw.replace("V", "").strip()), 1)
                except ValueError:
                    pass

            # 2. RPM (PID 010C)
            rpm_raw = self._send_cmd("010C")
            if "41 0C" in rpm_raw or len(rpm_raw.split()) >= 4:
                parts = rpm_raw.split()
                idx = parts.index("0C") if "0C" in parts else 1
                if len(parts) > idx + 2:
                    a, b = int(parts[idx+1], 16), int(parts[idx+2], 16)
                    self.rpm = float(((a * 256) + b) / 4)

            # 3. Speed (PID 010D)
            spd_raw = self._send_cmd("010D")
            if "41 0D" in spd_raw or len(spd_raw.split()) >= 3:
                parts = spd_raw.split()
                idx = parts.index("0D") if "0D" in parts else 1
                if len(parts) > idx + 1:
                    kph = float(int(parts[idx+1], 16))
                    self.speed_mph = kph * 0.621371

            # 4. Barometric Pressure (PID 0133) for Elevation Calibration
            baro_raw = self._send_cmd("0133")
            if "41 33" in baro_raw:
                parts = baro_raw.split()
                idx = parts.index("33") if "33" in parts else 1
                if len(parts) > idx + 1:
                    measured_baro = float(int(parts[idx+1], 16))
                    if 60.0 <= measured_baro <= 110.0:
                        self.baro_kpa = measured_baro
                        self.baro_calibrated = True

            # 5. MAP (Intake Manifold Absolute Pressure - PID 010B)
            map_raw = self._send_cmd("010B")
            if "41 0B" in map_raw or len(map_raw.split()) >= 3:
                parts = map_raw.split()
                idx = parts.index("0B") if "0B" in parts else 1
                if len(parts) > idx + 1:
                    map_kpa = float(int(parts[idx+1], 16))
                    
                    # Key-on elevation calibration: If engine is stopped, MAP directly equals ambient baro
                    if not self.baro_calibrated and self.rpm < 300 and 70.0 <= map_kpa <= 105.0:
                        self.baro_kpa = map_kpa
                        self.baro_calibrated = True

                    # Accurate Boost / Vacuum calculated against Globe, AZ ambient baro
                    delta_p = map_kpa - self.baro_kpa
                    if delta_p > 0.4:
                        self.boost_psi = round(delta_p * 0.145038, 1)
                        self.vacuum_inhg = 0.0
                        self.is_in_boost = True
                    else:
                        self.boost_psi = 0.0
                        self.vacuum_inhg = round(abs(delta_p) * 0.2953, 0)
                        self.is_in_boost = False

            # 6. Coolant Temp (PID 0105)
            clt_raw = self._send_cmd("0105")
            if "41 05" in clt_raw or len(clt_raw.split()) >= 3:
                parts = clt_raw.split()
                idx = parts.index("05") if "05" in parts else 1
                if len(parts) > idx + 1:
                    celsius = int(parts[idx+1], 16) - 40
                    self.coolant_temp_f = round(celsius * 9/5 + 32, 1)
                    # MultiAir hydraulic VVA requires oil/coolant at least 170°F
                    self.multiair_ready = (self.coolant_temp_f >= 170.0)

            # 7. Intake Air Temp (PID 010F)
            iat_raw = self._send_cmd("010F")
            if "41 0F" in iat_raw or len(iat_raw.split()) >= 3:
                parts = iat_raw.split()
                idx = parts.index("0F") if "0F" in parts else 1
                if len(parts) > idx + 1:
                    celsius = int(parts[idx+1], 16) - 40
                    self.intake_temp_f = round(celsius * 9/5 + 32, 1)

            # 8. Throttle Position (PID 0111)
            throt_raw = self._send_cmd("0111")
            if "41 11" in throt_raw or len(throt_raw.split()) >= 3:
                parts = throt_raw.split()
                idx = parts.index("11") if "11" in parts else 1
                if len(parts) > idx + 1:
                    self.throttle_pct = round((int(parts[idx+1], 16) * 100.0) / 255.0, 1)

        except Exception as e:
            print(f"[REAL OBD] Read error: {e}")
            self.connected = False
            self.status_message = "COMMUNICATION LOST"

        # Calculate gear from live RPM & Speed
        self.gear = self._calculate_gear(self.speed_mph, self.rpm)

        # F1 Sequential Shift Lights for 1.4T MultiAir
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
