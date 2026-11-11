"""
thermal_model.py - Thermodynamic Brake & Tire Degradation Telemetry for CarPi5
Calibrated specifically for Dodge Dart 1.4L Turbo MultiAir:
- Curb weight: 3,186 lbs (1,445 kg) + driver (~80 kg) = 1,525 kg.
- Front brakes: 11.8 in (300 mm) vented cast-iron rotors, 70% brake bias.
- Rear brakes: 10.4 in (264 mm) solid discs, 30% brake bias.
- Tires: 225/45R17 performance street compound (optimal window 155°F - 195°F).
- Dynamic weight transfer: lateral cornering (Gx) & longitudinal braking/accel (Gy).
- Real-time rotor heat, pad fade %, tire carcass/tread temp, and grip estimation.
- Proactive R.U.M. daughter audio warnings before brake fade or tire overheating.
"""

import math
import time
from typing import Dict, Any, Optional, Tuple

class BrakeTireThermalModel:
    def __init__(self, ambient_temp_f: float = 75.0):
        self.ambient_temp_f = ambient_temp_f
        self.last_update_ts = time.time()
        self.last_speed_mph = 0.0
        self.last_warning_time = 0.0

        # Initial resting temperatures (°F)
        self.front_rotor_temp_f = ambient_temp_f
        self.rear_rotor_temp_f = ambient_temp_f
        self.pad_fade_pct = 0.0

        # 4-corner tire temperatures (°F)
        self.tire_temps = {
            "FL": ambient_temp_f,
            "FR": ambient_temp_f,
            "RL": ambient_temp_f,
            "RR": ambient_temp_f
        }

        # 4-corner tire grip level (0 - 100%)
        self.tire_grip = {
            "FL": 85.0,
            "FR": 85.0,
            "RL": 85.0,
            "RR": 85.0
        }

        self.audio_player = None

    def set_audio_player(self, player):
        self.audio_player = player

    def _f_to_c(self, f: float) -> float:
        return (f - 32.0) * (5.0 / 9.0)

    def _c_to_f(self, c: float) -> float:
        return (c * 9.0 / 5.0) + 32.0

    def step(self, speed_mph: float, lat_g: float = 0.0, long_g: float = 0.0, dt: Optional[float] = None) -> Dict[str, Any]:
        """
        Executes one thermodynamic integration step based on vehicle telemetry.
        lat_g: lateral G (positive = right turn, loading left tires).
        long_g: longitudinal G (positive = accel, negative = braking).
        """
        now = time.time()
        if dt is None:
            dt = max(0.01, min(1.0, now - self.last_update_ts))
        self.last_update_ts = now

        speed_ms = speed_mph * 0.44704
        prev_speed_ms = self.last_speed_mph * 0.44704
        self.last_speed_mph = speed_mph

        # 1. BRAKE ROTOR KINETIC ENERGY & HEATING
        # Mass: 1,525 kg total vehicle
        m_total = 1525.0
        c_p_iron = 460.0  # J / (kg * K)
        m_front_rotors = 16.4  # kg (2 x 8.2 kg vented discs)
        m_rear_rotors = 9.0    # kg (2 x 4.5 kg solid discs)

        speed_delta_ms = prev_speed_ms - speed_ms
        is_braking = (speed_delta_ms > 0.3) or (long_g < -0.15)

        if is_braking and speed_ms > 1.0:
            # Kinetic energy dissipated
            decel_rate = max(0.1, abs(long_g) * 9.81 if long_g < -0.15 else speed_delta_ms / dt)
            power_watts = m_total * decel_rate * speed_ms * 0.85  # 85% mechanical to thermal
            delta_heat_j = power_watts * dt

            # 70% front bias, 30% rear bias
            d_temp_front_c = (0.70 * delta_heat_j) / (m_front_rotors * c_p_iron)
            d_temp_rear_c = (0.30 * delta_heat_j) / (m_rear_rotors * c_p_iron)

            self.front_rotor_temp_f += d_temp_front_c * 1.8
            self.rear_rotor_temp_f += d_temp_rear_c * 1.8

        # 2. BRAKE ROTOR CONVECTIVE COOLING
        # Convection scales with speed^0.8
        airflow_factor = 1.0 + 0.06 * (speed_mph ** 0.8)
        cooling_rate_front = 0.012 * airflow_factor * dt
        cooling_rate_rear = 0.009 * airflow_factor * dt

        self.front_rotor_temp_f -= (self.front_rotor_temp_f - self.ambient_temp_f) * cooling_rate_front
        self.rear_rotor_temp_f -= (self.rear_rotor_temp_f - self.ambient_temp_f) * cooling_rate_rear

        # Clamp rotor temps
        self.front_rotor_temp_f = max(self.ambient_temp_f, min(1450.0, self.front_rotor_temp_f))
        self.rear_rotor_temp_f = max(self.ambient_temp_f, min(1100.0, self.rear_rotor_temp_f))

        # 3. BRAKE PAD FADE MODEL
        # Street ceramic / semi-metallic pads hold friction up to ~550°F, fade rapidly past 650°F
        if self.front_rotor_temp_f < 550.0:
            self.pad_fade_pct = 0.0
        elif self.front_rotor_temp_f >= 950.0:
            self.pad_fade_pct = 100.0
        else:
            self.pad_fade_pct = round(((self.front_rotor_temp_f - 550.0) / 400.0) * 100.0, 1)

        # 4. TIRE CONTACT PATCH & BULK THERMAL DYNAMICS
        # Load distribution from lateral & longitudinal weight transfer
        # Nominal: 62% front, 38% rear (FWD Dodge Dart)
        w_front = 0.62 + max(-0.25, min(0.25, -long_g * 0.18))
        w_rear = 1.0 - w_front

        # Lateral transfer: positive lat_g (right turn) loads Left side
        lat_transfer = max(-0.35, min(0.35, lat_g * 0.22))
        load_FL = (w_front * 0.5) + (w_front * lat_transfer)
        load_FR = (w_front * 0.5) - (w_front * lat_transfer)
        load_RL = (w_rear * 0.5) + (w_rear * lat_transfer)
        load_RR = (w_rear * 0.5) - (w_rear * lat_transfer)

        tire_loads = {
            "FL": max(0.05, load_FL),
            "FR": max(0.05, load_FR),
            "RL": max(0.05, load_RL),
            "RR": max(0.05, load_RR)
        }

        # Cornering & braking scrubbing work
        total_g_vector = math.sqrt(lat_g**2 + long_g**2)
        tire_cooling_rate = (0.005 + 0.0003 * speed_mph) * dt

        for corner in ["FL", "FR", "RL", "RR"]:
            corner_load = tire_loads[corner]
            # Heating energy generated per tire
            heat_work = (total_g_vector ** 1.6) * (speed_mph / 40.0) * corner_load * 1.8 * dt
            # Radiative/convective heat from hot adjacent brake rotor
            rotor_bleed = 0.0008 * (self.front_rotor_temp_f if "F" in corner else self.rear_rotor_temp_f) * dt

            self.tire_temps[corner] += heat_work + rotor_bleed
            # Convective decay towards ambient
            self.tire_temps[corner] -= (self.tire_temps[corner] - self.ambient_temp_f) * tire_cooling_rate
            self.tire_temps[corner] = max(self.ambient_temp_f, min(260.0, self.tire_temps[corner]))

            # Grip % calculation based on optimal 155°F - 195°F window
            t = self.tire_temps[corner]
            if t < 155.0:
                # Cold tire ramp: 70% @ 40°F -> 100% @ 155°F
                grip = 70.0 + ((t - 40.0) / 115.0) * 30.0
            elif t <= 195.0:
                grip = 100.0
            else:
                # Overheated "greasy" tire falloff: 100% @ 195°F -> 75% @ 240°F
                grip = max(70.0, 100.0 - ((t - 195.0) / 45.0) * 25.0)
            self.tire_grip[corner] = round(max(50.0, min(100.0, grip)), 1)

        # 5. R.U.M. PROACTIVE DAUGHTER AUDIO WARNINGS
        warning = self._evaluate_warnings()

        return {
            "brakes": {
                "front_rotor_temp_f": round(self.front_rotor_temp_f, 1),
                "rear_rotor_temp_f": round(self.rear_rotor_temp_f, 1),
                "pad_fade_pct": self.pad_fade_pct,
                "status": "DANGER" if self.pad_fade_pct > 50 else ("CAUTION" if self.pad_fade_pct > 25 else "NORMAL")
            },
            "tires": {
                "temperatures_f": {k: round(v, 1) for k, v in self.tire_temps.items()},
                "grip_pct": self.tire_grip,
                "overall_grip_pct": round(sum(self.tire_grip.values()) / 4.0, 1),
                "status": "HOT" if max(self.tire_temps.values()) > 210 else ("COLD" if min(self.tire_temps.values()) < 110 else "OPTIMAL")
            },
            "warning": warning
        }

    def _evaluate_warnings(self) -> Optional[str]:
        now = time.time()
        if now - self.last_warning_time < 90.0:
            return None

        # 1. Brake Fade Alert (>650°F front rotors or >40% fade)
        if self.front_rotor_temp_f >= 650.0 or self.pad_fade_pct >= 40.0:
            self.last_warning_time = now
            msg = (
                f"Heads up Dad! Front rotors are at {int(self.front_rotor_temp_f)} degrees with "
                f"{int(self.pad_fade_pct)} percent pad fade! Let's drop into 3rd gear and use engine braking."
            )
            if self.audio_player and hasattr(self.audio_player, "speak_instant"):
                self.audio_player.speak_instant(msg)
            return msg

        # 2. Tire Overheat Alert (>215°F on any tire)
        hottest_corner = max(self.tire_temps, key=self.tire_temps.get)
        if self.tire_temps[hottest_corner] >= 215.0:
            self.last_warning_time = now
            msg = (
                f"Dad, the {hottest_corner} tire is getting greasy at {int(self.tire_temps[hottest_corner])} degrees! "
                "Let's give the rubber a cooling lap to preserve adhesion."
            )
            if self.audio_player and hasattr(self.audio_player, "speak_instant"):
                self.audio_player.speak_instant(msg)
            return msg

        return None
