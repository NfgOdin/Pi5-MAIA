"""
multiair_virtual_dyno.py - Dodge Dart 1.4L Turbo MultiAir Telemetry & Virtual Dyno Engine
Calibrated specifically for:
- 1.368L 16V MultiAir Turbo (Magneti Marelli 8GM ECU, Fiat Fire 1.4T)
- Garrett GT1446 Wastegate & Diverter Valve Spool Health Analysis
- Fiat C635 6-Speed Manual Transmission Rev-Match Scoring
- MultiAir UniAir Brick Hydraulic Viscosity & Thermal Protection
"""

import time
import math
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

# Physical Constants for 2013-2016 Dodge Dart 1.4T
DISPLACEMENT_M3 = 0.001368       # 1,368 cc (1.368 L)
CURB_WEIGHT_KG = 1445.0          # 3,186 lbs curb weight
DRIVER_WEIGHT_KG = 80.0          # ~176 lbs driver
TOTAL_MASS_KG = CURB_WEIGHT_KG + DRIVER_WEIGHT_KG
DRIVETRAIN_EFFICIENCY = 0.865    # FWD Manual transaxle loss ~13.5%
GAS_CONSTANT_AIR = 287.05        # J / (kg * K)

# C635 Gear Ratios & Drivetrain
GEAR_RATIOS: Dict[str, float] = {
    "1": 3.909,
    "2": 2.118,
    "3": 1.360,
    "4": 0.978,
    "5": 0.756,
    "6": 0.622
}
FINAL_DRIVE = 3.824
TIRE_CIRCUMFERENCE_M = 2.015     # Standard 225/45R17 tire

@dataclass
class SpoolRun:
    start_time: float
    start_rpm: float
    start_boost: float
    peak_rpm: float
    peak_boost: float
    gradient_psi_per_1000rpm: float
    health_score: float
    gear: str

@dataclass
class ShiftEvent:
    timestamp: float
    from_gear: str
    to_gear: str
    speed_mph: float
    actual_rpm: float
    target_rpm: float
    delta_rpm: float
    score: int
    classification: str

class MultiAirVirtualDyno:
    def __init__(self):
        # Virtual Dyno Real-Time State
        self.current_whp: float = 0.0
        self.current_wtq: float = 0.0
        self.peak_whp: float = 0.0
        self.peak_wtq: float = 0.0
        self.peak_whp_rpm: float = 0.0
        self.peak_wtq_rpm: float = 0.0

        # MultiAir Hydraulic Thermal State
        self.estimated_oil_temp_f: float = 75.0
        self.multiair_status: str = "COLD_PROTECT"
        self.multiair_ready: bool = False

        # Garrett GT1446 Wastegate & Diverter Health Tracking
        self.in_spool_pull: bool = False
        self.spool_start_time: float = 0.0
        self.spool_start_rpm: float = 0.0
        self.spool_start_boost: float = 0.0
        self.spool_pull_gear: str = "N"
        self.recent_spool_runs: List[SpoolRun] = []
        self.wastegate_health_pct: float = 100.0
        self.latest_spool_gradient: float = 9.8  # Default calibrated baseline

        # C635 Rev-Match & Shift Quality Tracking
        self.last_gear: str = "N"
        self.gear_transition_start_time: float = 0.0
        self.gear_transition_from: str = "N"
        self.shift_history: List[ShiftEvent] = []
        self.latest_shift_score: Optional[int] = None
        self.latest_shift_type: Optional[str] = None
        self.latest_shift_delta: Optional[float] = None
        self.total_shift_score: int = 0
        self.total_shift_count: int = 0

    def compute_volumetric_efficiency(self, rpm: float, boost_psi: float) -> float:
        """
        Dodge Dart 1.4L MultiAir Volumetric Efficiency curve.
        The electro-hydraulic UniAir system maximizes valve lift and duration
        between 2,500 and 4,500 RPM, while the small GT1446 turbine chokes beyond 5,500 RPM.
        """
        if rpm <= 1000:
            ve = 0.74
        elif rpm <= 2000:
            ve = 0.78 + (rpm - 1000) / 1000.0 * 0.08
        elif rpm <= 4200:
            ve = 0.86 + (rpm - 2000) / 2200.0 * 0.08  # Peaks around 0.94 under boost
        elif rpm <= 5500:
            ve = 0.94 - (rpm - 4200) / 1300.0 * 0.06
        else:
            ve = max(0.78, 0.88 - (rpm - 5500) / 1500.0 * 0.10)
        
        # Boost packing efficiency modifier
        if boost_psi > 0.0:
            ve = min(0.98, ve + (boost_psi / 25.0) * 0.04)
        return ve

    def process_frame(
        self,
        speed_mph: float,
        rpm: float,
        gear: str,
        throttle_pct: float,
        boost_psi: Optional[float],
        coolant_temp_f: Optional[float],
        intake_temp_f: Optional[float],
        engine_load_pct: Optional[float] = None,
        dt: float = 0.04
    ) -> Dict[str, Any]:
        """
        Evaluate real-time physics, thermodynamics, spool health, and shift ergonomics.
        """
        valid_boost = boost_psi if (boost_psi is not None) else 0.0
        valid_coolant = coolant_temp_f if (coolant_temp_f is not None) else 190.0
        valid_iat = intake_temp_f if (intake_temp_f is not None) else 80.0

        # -------------------------------------------------------------
        # 1. MultiAir UniAir Brick Thermal & Hydraulic Viscosity State
        # -------------------------------------------------------------
        # Engine oil heats slower than coolant during warm-up, and runs slightly
        # hotter under prolonged turbo boost.
        if getattr(self, '_first_frame_seen', False) is False:
            self._first_frame_seen = True
            if valid_coolant >= 150.0:
                self.estimated_oil_temp_f = valid_coolant * 0.92

        if valid_coolant < 160.0:
            self.estimated_oil_temp_f = valid_coolant * 0.88
        else:
            boost_thermal_load = max(0.0, valid_boost) * 0.4
            target_oil = valid_coolant + 5.0 + boost_thermal_load
            # Smoothly lag oil temperature
            self.estimated_oil_temp_f += (target_oil - self.estimated_oil_temp_f) * (dt / 15.0)

        if self.estimated_oil_temp_f < 150.0:
            self.multiair_status = "COLD_PROTECT"
            self.multiair_ready = False
        elif self.estimated_oil_temp_f > 235.0:
            self.multiair_status = "THERMAL_ALERT"
            self.multiair_ready = True
        else:
            self.multiair_status = "WARM_OPTIMAL"
            self.multiair_ready = True

        # -------------------------------------------------------------
        # 2. Realtime Virtual Dyno (WHP & WTQ)
        # -------------------------------------------------------------
        if rpm > 600 and throttle_pct > 5.0:
            # Intake Air Temperature in Kelvin
            iat_kelvin = (valid_iat - 32.0) * (5.0 / 9.0) + 273.15
            # Manifold Absolute Pressure in Pa (Globe, AZ baro ~88.0 kPa + boost in kPa)
            boost_kpa = valid_boost * 6.89476
            map_kpa = max(25.0, 88.0 + boost_kpa)
            map_pa = map_kpa * 1000.0

            # Air Density in intake plenum (kg/m3)
            rho_air = map_pa / (GAS_CONSTANT_AIR * iat_kelvin)
            ve = self.compute_volumetric_efficiency(rpm, valid_boost)

            # Volumetric displacement rate (m3/s) for 4-stroke engine
            volume_rate = DISPLACEMENT_M3 * (rpm / 120.0)
            # Mass air flow rate (g/s)
            maf_gps = volume_rate * rho_air * ve * 1000.0

            # Thermodynamic Brake Horsepower
            # Standard automotive combustion factor: 1 g/s of air ~ 1.25 Crank HP
            throttle_factor = min(1.0, max(0.1, throttle_pct / 85.0))
            crank_hp = (maf_gps / 0.74) * throttle_factor

            # Wheel Horsepower & Wheel Torque
            whp = max(0.0, crank_hp * DRIVETRAIN_EFFICIENCY)
            wtq = (whp * 5252.0) / max(rpm, 800.0)

            # Cap realistic boundaries for Dart 1.4T on GT1446 turbo (max ~235 WHP, 255 WTQ)
            self.current_whp = round(min(240.0, whp), 1)
            self.current_wtq = round(min(265.0, wtq), 1)

            # Track peak power
            if self.current_whp > self.peak_whp and rpm > 2000:
                self.peak_whp = self.current_whp
                self.peak_whp_rpm = round(rpm, 0)
            if self.current_wtq > self.peak_wtq and rpm > 1800:
                self.peak_wtq = self.current_wtq
                self.peak_wtq_rpm = round(rpm, 0)
        else:
            # Idle, coasting, or decelerating
            self.current_whp = 0.0
            self.current_wtq = 0.0

        # -------------------------------------------------------------
        # 3. Garrett GT1446 Wastegate & Diverter Valve Spool Health
        # -------------------------------------------------------------
        now = time.time()
        is_spool_candidate = (
            throttle_pct >= 75.0 and
            gear in ("2", "3", "4") and
            rpm >= 2100 and
            rpm <= 4800
        )

        if is_spool_candidate:
            if not self.in_spool_pull:
                self.in_spool_pull = True
                self.spool_start_time = now
                self.spool_start_rpm = rpm
                self.spool_start_boost = valid_boost
                self.spool_pull_gear = gear
            else:
                # Active pull ongoing - check if we reached peak spool (>= 12 PSI or RPM > 3500)
                rpm_delta = rpm - self.spool_start_rpm
                boost_delta = valid_boost - self.spool_start_boost
                if rpm_delta >= 1000 and boost_delta >= 6.0:
                    gradient = (boost_delta / rpm_delta) * 1000.0
                    # Healthy GT1446 achieves 9.0 - 12.0 PSI per 1000 RPM
                    health = min(100.0, max(25.0, (gradient / 9.5) * 100.0))
                    
                    self.latest_spool_gradient = round(gradient, 2)
                    self.wastegate_health_pct = round(health, 1)

                    spool_run = SpoolRun(
                        start_time=self.spool_start_time,
                        start_rpm=self.spool_start_rpm,
                        start_boost=self.spool_start_boost,
                        peak_rpm=rpm,
                        peak_boost=valid_boost,
                        gradient_psi_per_1000rpm=self.latest_spool_gradient,
                        health_score=self.wastegate_health_pct,
                        gear=self.spool_pull_gear
                    )
                    self.recent_spool_runs.append(spool_run)
                    if len(self.recent_spool_runs) > 10:
                        self.recent_spool_runs.pop(0)

                    # Reset pull to prevent re-triggering during the same gear sweep
                    self.in_spool_pull = False
        else:
            if self.in_spool_pull and (now - self.spool_start_time > 3.0 or throttle_pct < 50.0):
                self.in_spool_pull = False

        # -------------------------------------------------------------
        # 4. C635 Manual Transmission Rev-Match & Shift Quality Scoring
        # -------------------------------------------------------------
        if gear != self.last_gear:
            # Shift detected!
            old_gear = self.last_gear
            new_gear = gear
            self.last_gear = gear

            if old_gear in GEAR_RATIOS and new_gear in GEAR_RATIOS:
                old_ratio = GEAR_RATIOS[old_gear]
                new_ratio = GEAR_RATIOS[new_gear]
                is_downshift = new_ratio > old_ratio  # Higher numeric ratio = lower numerical gear

                # Calculate theoretical synchronized RPM for the new gear at current vehicle speed
                # speed_kph = (rpm * TIRE * 60) / (1000 * ratio * final_drive)
                # RPM_target = (speed_mph * 1.60934 * 1000 * ratio * final_drive) / (TIRE * 60)
                speed_kph = speed_mph * 1.60934
                target_rpm = (speed_kph * 1000.0 * new_ratio * FINAL_DRIVE) / (TIRE_CIRCUMFERENCE_M * 60.0)

                delta_rpm = abs(rpm - target_rpm)
                self.latest_shift_delta = round(delta_rpm, 0)

                if is_downshift:
                    # Heel-toe rev-match evaluation
                    if delta_rpm <= 120.0:
                        score = 100
                        classification = "PERFECT_REV_MATCH"
                    elif delta_rpm <= 260.0:
                        score = 90
                        classification = "CLEAN_REV_MATCH"
                    elif delta_rpm <= 480.0:
                        score = 75
                        classification = "ACCEPTABLE_REV_MATCH"
                    else:
                        score = max(35, int(70 - (delta_rpm - 480.0) / 15.0))
                        classification = "CLUTCH_JERK"
                else:
                    # Upshift evaluation (smooth rev drop matching)
                    if delta_rpm <= 180.0:
                        score = 100
                        classification = "PERFECT_UPSHIFT"
                    elif delta_rpm <= 350.0:
                        score = 90
                        classification = "SMOOTH_UPSHIFT"
                    else:
                        score = max(40, int(75 - (delta_rpm - 350.0) / 20.0))
                        classification = "LUGGING_OR_JERK"

                self.latest_shift_score = score
                self.latest_shift_type = classification
                self.total_shift_score += score
                self.total_shift_count += 1

                shift_event = ShiftEvent(
                    timestamp=now,
                    from_gear=old_gear,
                    to_gear=new_gear,
                    speed_mph=round(speed_mph, 1),
                    actual_rpm=round(rpm, 0),
                    target_rpm=round(target_rpm, 0),
                    delta_rpm=round(delta_rpm, 0),
                    score=score,
                    classification=classification
                )
                self.shift_history.append(shift_event)
                if len(self.shift_history) > 20:
                    self.shift_history.pop(0)

        avg_shift = round(self.total_shift_score / max(1, self.total_shift_count), 1) if self.total_shift_count > 0 else 100.0

        return {
            "virtual_whp": self.current_whp,
            "virtual_wtq": self.current_wtq,
            "peak_whp": self.peak_whp,
            "peak_wtq": self.peak_wtq,
            "peak_whp_rpm": self.peak_whp_rpm,
            "peak_wtq_rpm": self.peak_wtq_rpm,
            "multiair_oil_temp_f": round(self.estimated_oil_temp_f, 1),
            "multiair_status": self.multiair_status,
            "multiair_ready": self.multiair_ready,
            "spool_gradient": self.latest_spool_gradient,
            "wastegate_health_pct": self.wastegate_health_pct,
            "latest_shift_score": self.latest_shift_score,
            "latest_shift_type": self.latest_shift_type,
            "latest_shift_delta": self.latest_shift_delta,
            "avg_shift_score": avg_shift,
            "total_shifts": self.total_shift_count
        }
