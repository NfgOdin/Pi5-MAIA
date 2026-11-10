"""
simulator.py - Dodge Dart 1.4L Turbo MultiAir Physics & Telemetry Simulator
Simulates realistic 6-speed manual shifting, turbo spooling (boost/vacuum),
MultiAir thermal warmup curves, 0-60 launch timing, and UDS DTC code injection.
"""

import time
import math
import random
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from .multiair_virtual_dyno import MultiAirVirtualDyno
from typing import Optional, Dict, Any, List

@dataclass
class TelemetryFrame:
    timestamp: float
    speed_mph: float
    speed_kph: float
    rpm: float
    gear: str  # "N", "1", "2", "3", "4", "5", "6", "R"
    throttle_pct: float
    boost_psi: Optional[float] = 0.0
    vacuum_inhg: Optional[float] = 0.0
    is_in_boost: bool = False
    coolant_temp_f: Optional[float] = None
    intake_temp_f: Optional[float] = None
    battery_volts: Optional[float] = None
    fuel_mpg_instant: Optional[float] = None
    multiair_ready: bool = False
    shift_indicator: bool = False  # True when >= 5800 RPM
    f1_light_level: int = 0    # 0 to 5 (for sequential LED lightbar)
    launch_timer_active: bool = False
    zero_to_sixty_time: Optional[float] = None
    active_dtcs: Optional[List[str]] = None
    connected: bool = True
    status_message: str = "ONLINE"
    engine_load_pct: Optional[float] = None
    timing_advance_deg: Optional[float] = None
    afr: Optional[float] = None
    fuel_level_pct: Optional[float] = None
    ambient_temp_f: Optional[float] = None
    pedal_pos_pct: Optional[float] = None
    engine_runtime_sec: Optional[int] = None
    fuel_gph: Optional[float] = None
    baro_kpa: Optional[float] = None
    virtual_whp: float = 0.0
    virtual_wtq: float = 0.0
    multiair_oil_temp_f: Optional[float] = None
    oil_temp_f: Optional[float] = None
    multiair_status: str = "WARM_OPTIMAL"
    wastegate_spool_health: float = 100.0
    wastegate_spool_gradient: float = 9.8
    last_shift_score: Optional[int] = None
    last_shift_type: Optional[str] = None
    last_shift_delta: Optional[float] = None
    avg_shift_score: float = 100.0
    headlights_on: bool = False
    ambient_light_lux: float = 100.0
    lateral_g: float = 0.0
    longitudinal_g: float = 0.0
    lateral_accel: float = 0.0
    steering_angle: float = 0.0

class Dart14TSimulator:
    def __init__(self, config_path: Optional[str] = None):
        if not config_path:
            config_path = str(Path(__file__).parent.parent.parent / "config" / "vehicle_config.json")
        
        with open(config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)["vehicle"]["specs"]
        
        # State variables
        self.speed_mph = 0.0
        self.rpm = float(self.cfg["idle_rpm"])
        self.gear = "N"
        self.throttle_pct = 0.0
        self.boost_psi = 0.0
        self.vacuum_inhg = 20.0
        self.coolant_temp_f = 75.0  # Starts cold to test MultiAir guardian
        self.intake_temp_f = 78.0
        self.battery_volts = 14.2
        self.active_dtcs: List[str] = []
        self.lateral_g = 0.0
        self.longitudinal_g = 0.0
        self.steering_angle = 0.0
        
        # 0-60 Launch Tracker
        self.launch_start_time: Optional[float] = None
        self.last_0_60_time: Optional[float] = None
        self.is_launching = False

        # Simulation driver profile
        self.sim_time = 0.0
        self.current_gear_idx = 0  # 0: N, 1: 1st, 2: 2nd, etc.
        self.shift_pause = 0.0
        self.dyno = MultiAirVirtualDyno()

    def _sync_rpm_for_gear(self, speed_mph: float, gear: str) -> float:
        """Compute exact C635 synchronized engine RPM for a given road speed and gear."""
        ratio = float(self.cfg["gear_ratios"].get(gear, 1.0))
        final_drive = float(self.cfg.get("final_drive_ratio", 3.824))
        tire_circ = float(self.cfg.get("tire_circumference_meters", 2.015))
        speed_kph = max(0.0, speed_mph) * 1.60934
        return (speed_kph * 1000.0 * ratio * final_drive) / (max(0.5, tire_circ) * 60.0)

    def step(self, dt: float = 0.05) -> TelemetryFrame:
        """Advance the physics simulation by dt seconds (default 20Hz / 50ms)."""
        try:
            dt = float(dt) if dt is not None else 0.05
            if not math.isfinite(dt) or dt <= 0.0:
                dt = 0.05
            dt = min(dt, 1.0)
        except (ValueError, TypeError):
            dt = 0.05

        prev_speed_mph = self.speed_mph
        self.sim_time += dt

        # 1. Warm up MultiAir coolant slowly
        if self.coolant_temp_f < 195.0:
            self.coolant_temp_f += dt * 0.85  # Warms up to 195°F over a couple minutes
            if self.coolant_temp_f > 195.0:
                self.coolant_temp_f = 195.0

        # MultiAir UniAir COLD_PROTECT limits boost to < 7.5 PSI until 5W-40 oil > 150°F
        cold_protect_active = (self.dyno.estimated_oil_temp_f < 150.0)
        max_allowed_boost = 7.2 if cold_protect_active else float(self.cfg.get("stock_peak_boost_psi", 18.0))
        
        # 2. Automated driving cycle (simulate spirited acceleration pull + rev-matched downshift)
        cycle_time = self.sim_time % 35.0  # 35-second looping driving cycle
        
        if cycle_time < 3.0:
            # Idling at a standstill
            self.gear = "N"
            self.throttle_pct = 0.0
            self.speed_mph = 0.0
            self.rpm = float(self.cfg["idle_rpm"]) + random.uniform(-15, 15)
            self.boost_psi = 0.0
            self.vacuum_inhg = 21.0 + random.uniform(-0.5, 0.5)
            self.lateral_g = 0.0
            self.steering_angle = 0.0
            self.is_launching = False
            self.launch_start_time = None

        elif cycle_time < 8.0:
            # 1st Gear Hard Launch!
            self.gear = "1"
            self.throttle_pct = 95.0
            if not self.is_launching:
                self.is_launching = True
                self.launch_start_time = time.time()
            
            # Accelerate in 1st up to ~28.5 MPH (~5,670 RPM on C635 3.909 ratio)
            accel = 5.7 * dt
            self.speed_mph += accel
            self.rpm = self._sync_rpm_for_gear(self.speed_mph, "1")
            self.rpm = max(float(self.cfg["idle_rpm"]), min(self.rpm, 6200.0))
            
            # Turbo spooling up to 16.5 PSI (or 7.2 PSI during COLD_PROTECT)
            self.boost_psi = min(min(16.5, max_allowed_boost), self.boost_psi + (dt * 15.0))
            self.vacuum_inhg = 0.0
            self.lateral_g = round(0.04 * math.sin(cycle_time * 2.0), 2)
            self.steering_angle = round(self.lateral_g * 15.0, 1)

        elif cycle_time < 8.6:
            # Shift 1st -> 2nd (Clutch in, throttle lift, blow-off valve dump, rev drop to 2nd sync)
            self.gear = "⇄"
            self.throttle_pct = 10.0
            target_2nd_rpm = self._sync_rpm_for_gear(self.speed_mph, "2")
            self.rpm = max(target_2nd_rpm, self.rpm - (dt * 4500.0))
            self.boost_psi = 0.0
            self.vacuum_inhg = 22.0
            self.lateral_g = 0.0
            self.steering_angle = 0.0

        elif cycle_time < 15.5:
            # 2nd Gear Pull to ~54 MPH (~5,820 RPM on C635 2.118 ratio)
            self.gear = "2"
            self.throttle_pct = 100.0
            accel = 3.7 * dt
            self.speed_mph += accel
            self.rpm = min(self._sync_rpm_for_gear(self.speed_mph, "2"), 6300.0)
            
            # Turbo peak boost!
            self.boost_psi = min(min(17.8, max_allowed_boost), self.boost_psi + (dt * 18.0))
            self.vacuum_inhg = 0.0
            self.lateral_g = round(0.18 * math.sin((cycle_time - 8.6) * 0.9), 2)
            self.steering_angle = round(self.lateral_g * 28.0, 1)

        elif cycle_time < 16.1:
            # Shift 2nd -> 3rd (Clutch in, rev drop to 3rd sync)
            self.gear = "⇄"
            self.throttle_pct = 10.0
            target_3rd_rpm = self._sync_rpm_for_gear(self.speed_mph, "3")
            self.rpm = max(target_3rd_rpm, self.rpm - (dt * 3800.0))
            self.boost_psi = 0.0
            self.vacuum_inhg = 22.0
            self.lateral_g = 0.05
            self.steering_angle = 1.5

        elif cycle_time < 24.5:
            # 3rd Gear Pull crosses 60 MPH up to ~74 MPH (~5,120 RPM on C635 1.360 ratio)
            self.gear = "3"
            self.throttle_pct = 85.0
            accel = 2.4 * dt
            self.speed_mph += accel
            self.rpm = min(self._sync_rpm_for_gear(self.speed_mph, "3"), 6300.0)
            
            # Record 0-60 timestamp!
            if self.is_launching and self.speed_mph >= 60.0 and self.launch_start_time:
                self.last_0_60_time = round(time.time() - self.launch_start_time, 2)
                self.is_launching = False
            
            self.boost_psi = min(min(16.0, max_allowed_boost), self.boost_psi + (dt * 10.0))
            self.vacuum_inhg = 0.0
            self.lateral_g = round(0.32 * math.sin((cycle_time - 16.1) * 0.75), 2)
            self.steering_angle = round(self.lateral_g * 35.0, 1)

        elif cycle_time < 25.0:
            # Smooth upshift 3rd -> 4th
            self.gear = "⇄"
            self.throttle_pct = 5.0
            target_4th_rpm = self._sync_rpm_for_gear(self.speed_mph, "4")
            self.rpm = max(target_4th_rpm, self.rpm - (dt * 3200.0))
            self.boost_psi = 0.0
            self.vacuum_inhg = 21.0
            self.lateral_g = 0.0
            self.steering_angle = 0.0

        elif cycle_time < 29.0:
            # 4th Gear engine braking / deceleration from ~74 MPH down to ~44 MPH
            self.gear = "4"
            self.throttle_pct = 0.0
            self.speed_mph = max(0.0, self.speed_mph - (dt * 7.5))
            self.rpm = max(float(self.cfg["idle_rpm"]), self._sync_rpm_for_gear(self.speed_mph, "4"))
            self.boost_psi = 0.0
            self.vacuum_inhg = 23.5 + random.uniform(-0.4, 0.4)
            self.lateral_g = round(-0.22 * math.sin((cycle_time - 25.0) * 0.8), 2)
            self.steering_angle = round(self.lateral_g * 30.0, 1)

        elif cycle_time < 29.4:
            # Heel-toe throttle blip in neutral before engaging 3rd gear downshift
            self.gear = "⇄"
            self.throttle_pct = 45.0
            self.speed_mph = max(0.0, self.speed_mph - (dt * 6.0))
            self.rpm = self._sync_rpm_for_gear(self.speed_mph, "3")
            self.boost_psi = 0.0
            self.vacuum_inhg = 14.0
            self.lateral_g = -0.10
            self.steering_angle = -3.0

        elif cycle_time < 32.5:
            # Rev-matched 3rd gear engine braking down to ~15 MPH
            self.gear = "3"
            self.throttle_pct = 0.0
            self.speed_mph = max(0.0, self.speed_mph - (dt * 9.0))
            self.rpm = max(float(self.cfg["idle_rpm"]), self._sync_rpm_for_gear(self.speed_mph, "3"))
            self.boost_psi = 0.0
            self.vacuum_inhg = 24.0 + random.uniform(-0.3, 0.3)
            self.lateral_g = 0.0
            self.steering_angle = 0.0

        else:
            # Final braking in Neutral back to 0 MPH
            self.gear = "N"
            self.throttle_pct = 0.0
            self.speed_mph = max(0.0, self.speed_mph - (dt * 10.0))
            self.rpm = float(self.cfg["idle_rpm"]) + random.uniform(-10, 10)
            self.boost_psi = 0.0
            self.vacuum_inhg = 21.5 + random.uniform(-0.4, 0.4)
            self.lateral_g = 0.0
            self.steering_angle = 0.0

        # Calculate instantaneous longitudinal G-force (1G ~= 21.937 mph/s)
        dv_mph = self.speed_mph - prev_speed_mph
        self.longitudinal_g = round(max(-1.2, min(1.2, (dv_mph / dt) / 21.937)), 2)

        # 3. Calculate F1-style sequential shift lights (0 to 5)
        f1_level = 0
        if self.rpm > 3500: f1_level = 1  # Green 1
        if self.rpm > 4500: f1_level = 2  # Green 2
        if self.rpm > 5200: f1_level = 3  # Yellow
        if self.rpm > 5600: f1_level = 4  # Red
        if self.rpm >= float(self.cfg["shift_indicator_rpm"]): f1_level = 5  # Flash Blue!

        # 4. Assemble Telemetry Sensors
        sim_load = round(min(100.0, 20.0 + self.throttle_pct * 0.75), 1)
        sim_timing = round(max(-5.0, min(35.0, 5.0 + (self.rpm / 400.0) - (self.boost_psi * 0.4))), 1)
        sim_afr = round(14.7 - (0.15 * max(0.0, self.boost_psi)), 2)
        sim_gph = round(max(0.22, (self.rpm / 750.0) * 0.25 + (self.throttle_pct * 0.05)), 2)
        sim_mpg = 0.0 if self.speed_mph < 1.0 else round(min(99.9, self.speed_mph / sim_gph), 1)

        # 5. Step MultiAir Virtual Dyno & Spool Health
        dyno_metrics = self.dyno.process_frame(
            speed_mph=self.speed_mph,
            rpm=self.rpm,
            gear=self.gear,
            throttle_pct=self.throttle_pct,
            boost_psi=self.boost_psi,
            coolant_temp_f=self.coolant_temp_f,
            intake_temp_f=self.intake_temp_f,
            engine_load_pct=sim_load,
            dt=dt
        )

        hl_on = bool(getattr(self, "_injected_headlights", (time.localtime().tm_hour >= 19 or time.localtime().tm_hour < 6)))
        lux_val = 5.0 if hl_on else 450.0

        frame = TelemetryFrame(
            timestamp=time.time(),
            speed_mph=round(self.speed_mph, 1),
            speed_kph=round(self.speed_mph * 1.60934, 1),
            rpm=round(self.rpm, 0),
            gear=self.gear,
            throttle_pct=round(self.throttle_pct, 1),
            boost_psi=round(max(0.0, self.boost_psi), 1),
            vacuum_inhg=round(max(0.0, self.vacuum_inhg), 1),
            is_in_boost=self.boost_psi > 0.5,
            coolant_temp_f=round(self.coolant_temp_f, 1),
            intake_temp_f=round(self.intake_temp_f + (self.boost_psi * 1.2), 1),
            battery_volts=round(14.2 + random.uniform(-0.1, 0.1), 2),
            fuel_mpg_instant=sim_mpg,
            multiair_ready=dyno_metrics["multiair_ready"],
            shift_indicator=self.rpm >= float(self.cfg["shift_indicator_rpm"]),
            f1_light_level=f1_level,
            launch_timer_active=self.is_launching,
            zero_to_sixty_time=self.last_0_60_time,
            active_dtcs=self.active_dtcs.copy(),
            engine_load_pct=sim_load,
            timing_advance_deg=sim_timing,
            afr=sim_afr,
            fuel_level_pct=68.5,
            ambient_temp_f=75.0,
            pedal_pos_pct=round(self.throttle_pct, 1),
            engine_runtime_sec=int(self.sim_time),
            fuel_gph=sim_gph,
            baro_kpa=88.0,
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
            ambient_light_lux=lux_val,
            lateral_g=self.lateral_g,
            longitudinal_g=self.longitudinal_g,
            lateral_accel=self.lateral_g,
            steering_angle=self.steering_angle
        )
        return frame

    def set_headlights(self, state: bool):
        """Explicitly override headlights state for testing / CAN bridge."""
        self._injected_headlights = bool(state)

    def inject_dtc(self, code: str):
        """Simulate an engine trouble code for testing the AI mechanic."""
        if code not in self.active_dtcs:
            self.active_dtcs.append(code)

    def clear_dtcs(self):
        """Clear all active codes."""
        self.active_dtcs.clear()
