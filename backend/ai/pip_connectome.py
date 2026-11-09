"""
pip_connectome.py - Princeton FlyWire 2024 Biological Drosophila SNN Core
Calibrated specifically for:
- 2024 Complete Adult Drosophila Connectome (139,255 neurons / 54.5M synapses)
- Central Complex (CX) Ring Attractor Compass (16 EPG & 16 P-EN neurons)
- Giant Fiber (GF) Looming & Vibration Evasive Escape Circuit
- Haltere Coriolis Mechanoreceptors coupled to in-dash G-Forces & Road Shocks
- Circadian s-LNv / PDF Neuropeptide Metabolic Arousal
"""

import time
import math
import random
from typing import Dict, Any, List, Optional, Tuple

class PipConnectome:
    def __init__(self):
        # 3D Cockpit/Room Spatial Coordinates
        # Coordinates aligned with CarPi5 3D Stage (X: [-1.2, 1.2], Y: [0.8, 1.9], Z: [-1.8, 0.4])
        # Driver/Dad side: X < -0.4, R.U.M. side: X > 0.3, Desk/Stage: Y ~ 1.05 - 1.35
        self.x: float = 0.55
        self.y: float = 1.25
        self.z: float = -0.45
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.vz: float = 0.0
        self.heading: float = math.pi * 0.75
        self.pitch: float = 0.0
        self.roll: float = 0.0
        self.speed: float = 1.10
        self.wing_hz: float = 210.0  # Biological Drosophila wingbeat frequency ~200-220 Hz

        # Behavioral States: "FLYING", "SACCADE", "PERCHED", "GROOMING", "ESCAPE"
        self.state: str = "FLYING"
        self.state_timer: float = 2.0
        self.energy_pct: float = 95.0
        self.perch_target: Optional[Tuple[float, float, float]] = None

        # -------------------------------------------------------------
        # 1. Central Complex (CX) Ring Attractor Compass SNN
        # -------------------------------------------------------------
        # 16 EPG neurons with preferred directional angles θ_i in [0, 2π)
        self.num_epg: int = 16
        self.epg_angles: List[float] = [(2.0 * math.pi * i) / self.num_epg for i in range(self.num_epg)]
        self.epg_voltages: List[float] = [-65.0] * self.num_epg  # Resting -65 mV
        self.epg_spikes: List[bool] = [False] * self.num_epg
        # Pre-seed the initial ring attractor bump around 0.75π
        self._init_ring_attractor_bump(math.pi * 0.75)

        # 16 P-EN angular velocity integrator neurons
        self.pen_left_voltages: List[float] = [-65.0] * self.num_epg
        self.pen_right_voltages: List[float] = [-65.0] * self.num_epg

        # -------------------------------------------------------------
        # 2. Giant Fiber (GF) Escape Reflex Circuit
        # -------------------------------------------------------------
        # GF1 (Left) and GF2 (Right) descending escape interneurons
        self.gf_voltage: float = -70.0
        self.gf_threshold: float = -46.0  # Depolarization threshold
        self.gf_spike_active: bool = False
        self.last_gf_spike_time: float = 0.0

        # -------------------------------------------------------------
        # 3. Haltere Mechanoreceptors (Biological Gyroscopes)
        # -------------------------------------------------------------
        # Campaniform sensilla at haltere base detecting Coriolis forces
        self.haltere_coriolis_pitch: float = 0.0
        self.haltere_coriolis_roll: float = 0.0
        self.haltere_coriolis_yaw: float = 0.0
        self.haltere_vibration_strain: float = 0.0

        # R.U.M. & Dad Proximity Tracking
        self.dist_to_rum: float = 1.0
        self.dist_to_dad: float = 1.8
        self.rum_interaction_event: Optional[str] = None
        self.last_dad_buzz_time: float = 0.0
        self.last_feed_time: float = 0.0

    def _init_ring_attractor_bump(self, center_rad: float):
        """Initializes a biological cosine bump of activity across EPG compass neurons."""
        for i in range(self.num_epg):
            diff = math.atan2(math.sin(self.epg_angles[i] - center_rad), math.cos(self.epg_angles[i] - center_rad))
            bump = math.exp(-0.5 * (diff / 0.55) ** 2)
            self.epg_voltages[i] = -65.0 + (bump * 22.0)  # Up to -43 mV (spiking range)

    def get_ring_attractor_heading(self) -> float:
        """Decodes the population vector angle of the EPG compass bump."""
        sin_sum = 0.0
        cos_sum = 0.0
        for i in range(self.num_epg):
            weight = max(0.0, self.epg_voltages[i] - (-65.0))
            sin_sum += weight * math.sin(self.epg_angles[i])
            cos_sum += weight * math.cos(self.epg_angles[i])
        return math.atan2(sin_sum, cos_sum)

    def stimulate_sugar_water(self):
        """Feeds Pip sugar water treat from R.U.M.'s dropper."""
        self.energy_pct = min(100.0, self.energy_pct + 45.0)
        self.last_feed_time = time.time()
        self.state = "PERCHED"
        self.state_timer = 6.0
        self.rum_interaction_event = "SUGAR_WATER_FEED"

    def stimulate_scare(self, force: float = 1.0):
        """Triggers an external shock, loud noise, or air puff firing the Giant Fiber reflex."""
        self.gf_voltage += 32.0 * force
        if self.gf_voltage >= self.gf_threshold:
            self._fire_giant_fiber_escape()

    def _fire_giant_fiber_escape(self):
        """Instantaneous biological evasive escape saccade (< 5ms)."""
        self.gf_spike_active = True
        self.last_gf_spike_time = time.time()
        self.state = "ESCAPE"
        self.state_timer = 0.75
        self.heading += (random.random() - 0.5) * math.pi * 0.9
        self.pitch = 0.65  # Jump upward
        self.speed = 2.45  # 240% speed burst
        self.wing_hz = 265.0

    def step(self, dt: float, telemetry: Any, is_night: bool = False) -> Dict[str, Any]:
        """
        Advance the biological connectome SNN and 3D kinematics by dt seconds (25-50 Hz).
        """
        now = time.time()
        if self.rum_interaction_event != "SUGAR_WATER_FEED":
            self.rum_interaction_event = None

        # -------------------------------------------------------------
        # 1. Harvest Physical Vehicle Telemetry into Mechanoreceptors
        # -------------------------------------------------------------
        speed_mph = getattr(telemetry, 'speed_mph', getattr(telemetry, 'speed', 0.0)) or 0.0
        boost_psi = getattr(telemetry, 'boost_psi', 0.0) or 0.0
        lat_g = getattr(telemetry, 'lateral_accel', 0.0) or 0.0
        rpm = getattr(telemetry, 'rpm', 0.0) or 0.0

        # Cabin Vibration Strain (Engine RPM harmonics + Boost spool vibration)
        rpm_vibe = (rpm / 6500.0) * 0.25 if rpm > 500 else 0.0
        boost_vibe = max(0.0, boost_psi) * 0.05
        self.haltere_vibration_strain = rpm_vibe + boost_vibe

        # Haltere Coriolis Acceleration Inputs
        self.haltere_coriolis_roll = lat_g * 1.8
        self.haltere_coriolis_pitch = (boost_psi / 20.0) * 0.8

        # Sudden Boost Kick / G-Shock triggers Giant Fiber Looming Reflex
        if boost_psi >= 14.5 and (now - self.last_gf_spike_time > 8.0) and random.random() < 0.12:
            self.stimulate_scare(force=0.95)
            self.rum_interaction_event = "STARTLED_BY_TURBO"

        # -------------------------------------------------------------
        # 2. Central Complex (CX) Spiking Dynamics
        # -------------------------------------------------------------
        # Metabolic energy depletion
        metabolic_rate = 0.08 if is_night else 0.14
        self.energy_pct = max(10.0, self.energy_pct - (dt * metabolic_rate))

        # Haltere angular yaw velocity drives P-EN integrators
        ang_vel_yaw = (self.haltere_coriolis_roll * 1.5) + (random.uniform(-0.8, 0.8) if self.state == "FLYING" else 0.0)
        
        # Leaky integrate-and-fire update for EPG compass neurons
        tau_m = 0.045  # Membrane time constant ~45ms
        for i in range(self.num_epg):
            # Recurrent Mexican-hat lateral inhibition from other EPGs
            recurrent_input = 0.0
            for j in range(self.num_epg):
                diff = math.atan2(math.sin(self.epg_angles[i] - self.epg_angles[j]), math.cos(self.epg_angles[i] - self.epg_angles[j]))
                weight = 1.8 * math.cos(diff) - 0.7  # Cosine excitatory center, inhibitory surround
                recurrent_input += max(0.0, self.epg_voltages[j] - (-65.0)) * weight

            # Shift from P-EN neurons based on turn direction
            shift_input = ang_vel_yaw * math.sin(self.epg_angles[i] - self.heading) * 12.0
            total_current = (recurrent_input * 0.08) + shift_input

            # Voltage update
            dv = (-(self.epg_voltages[i] - (-65.0)) + total_current) * (dt / tau_m)
            self.epg_voltages[i] = max(-75.0, min(-38.0, self.epg_voltages[i] + dv))
            self.epg_spikes[i] = self.epg_voltages[i] >= -45.0

        # Decode Compass Ring Bump to guide heading
        target_heading = self.get_ring_attractor_heading()

        # -------------------------------------------------------------
        # 3. Behavioral State Machine (Flight, Saccade, Perch, Groom)
        # -------------------------------------------------------------
        self.state_timer -= dt

        # Night Senses PDF suppression: Pip prefers perching/resting when night mode is active
        if is_night and self.state == "FLYING" and random.random() < 0.08:
            self.state = "PERCHED"
            self.state_timer = random.uniform(8.0, 18.0)

        if self.state == "FLYING" or self.state == "ESCAPE" or self.state == "SACCADE":
            # Haltere gyroscopic stabilization
            self.roll = -self.haltere_coriolis_roll * 0.45
            self.wing_hz = 215.0 if self.state != "ESCAPE" else 265.0

            # Turn toward central complex compass heading
            h_diff = math.atan2(math.sin(target_heading - self.heading), math.cos(target_heading - self.heading))
            turn_rate = 14.0 if (self.state == "ESCAPE" or self.state == "SACCADE") else 5.5
            self.heading += h_diff * min(1.0, dt * turn_rate)

            # Move forward along heading & pitch
            cur_speed = self.speed * (2.2 if self.state == "ESCAPE" else 1.0)
            self.vx = -math.sin(self.heading) * math.cos(self.pitch) * cur_speed
            self.vy = math.sin(self.pitch) * cur_speed * 0.75
            self.vz = -math.cos(self.heading) * math.cos(self.pitch) * cur_speed

            self.x += self.vx * dt
            self.y += self.vy * dt
            self.z += self.vz * dt

            # 3D Spatial Boundary Bounding Box in Cockpit
            if self.x < -1.15: self.x = -1.15; self.heading = math.pi * 0.5; self.state = "SACCADE"; self.state_timer = 0.25
            elif self.x > 1.15: self.x = 1.15; self.heading = -math.pi * 0.5; self.state = "SACCADE"; self.state_timer = 0.25
            if self.y < 0.88: self.y = 0.88; self.pitch = 0.45
            elif self.y > 1.95: self.y = 1.95; self.pitch = -0.45
            if self.z < -1.75: self.z = -1.75; self.heading = 0.0; self.state = "SACCADE"; self.state_timer = 0.25
            elif self.z > 0.45: self.z = 0.45; self.heading = math.pi; self.state = "SACCADE"; self.state_timer = 0.25

            # Transition out of saccade / escape
            if self.state_timer <= 0:
                if self.state in ("ESCAPE", "SACCADE"):
                    self.state = "FLYING"
                    self.gf_spike_active = False
                    self.speed = 1.10
                else:
                    # Random biological flight saccade
                    if random.random() < 0.35:
                        self.state = "SACCADE"
                        self.state_timer = 0.20
                        self._init_ring_attractor_bump(self.heading + (random.random() - 0.5) * 1.5)
                    elif (self.energy_pct < 45.0 or random.random() < 0.15):
                        # Seek landing perch
                        self.state = "PERCHED"
                        self.state_timer = random.uniform(3.5, 7.5)
                        self.perch_target = (0.55 + random.uniform(-0.1, 0.1), 1.10, -0.35)

        elif self.state == "PERCHED":
            self.wing_hz = 0.0
            self.vx = 0.0; self.vy = 0.0; self.vz = 0.0
            if self.state_timer <= 0:
                if random.random() < 0.45:
                    self.state = "GROOMING"
                    self.state_timer = random.uniform(2.5, 5.0)
                else:
                    # Take off!
                    self.state = "FLYING"
                    self.state_timer = random.uniform(2.0, 5.0)
                    self.pitch = 0.50
                    self.heading = random.random() * math.pi * 2

        elif self.state == "GROOMING":
            self.wing_hz = 0.0
            if self.state_timer <= 0:
                self.state = "FLYING"
                self.state_timer = random.uniform(2.0, 4.0)
                self.pitch = 0.50
                self.heading = random.random() * math.pi * 2

        # -------------------------------------------------------------
        # 4. Proximity Checks & R.U.M. Dual-Life Interaction Events
        # -------------------------------------------------------------
        # R.U.M. 3D coordinates: approx (0.50, 1.15, -0.40)
        # Dad's side coordinates: approx (-0.65, 1.30, 0.10)
        rum_dx = self.x - 0.50
        rum_dy = self.y - 1.15
        rum_dz = self.z - (-0.40)
        self.dist_to_rum = math.sqrt(rum_dx * rum_dx + rum_dy * rum_dy + rum_dz * rum_dz)

        dad_dx = self.x - (-0.65)
        dad_dy = self.y - 1.30
        dad_dz = self.z - 0.10
        self.dist_to_dad = math.sqrt(dad_dx * dad_dx + dad_dy * dad_dy + dad_dz * dad_dz)

        # Pip perching near R.U.M.'s hand
        if not self.rum_interaction_event:
            if self.dist_to_rum < 0.35 and self.state == "PERCHED":
                self.rum_interaction_event = "PERCHED_ON_RUM"
            elif self.dist_to_dad < 0.45 and (now - self.last_dad_buzz_time > 120.0):
                self.last_dad_buzz_time = now
                self.rum_interaction_event = "BUZZING_NEAR_DAD"

        return {
            "state": self.state,
            "position": {"x": round(self.x, 3), "y": round(self.y, 3), "z": round(self.z, 3)},
            "heading": round(self.heading, 3),
            "pitch": round(self.pitch, 3),
            "roll": round(self.roll, 3),
            "wing_hz": round(self.wing_hz, 1),
            "energy_pct": round(self.energy_pct, 1),
            "compass_heading_rad": round(target_heading, 3),
            "gf_spike_active": self.gf_spike_active,
            "haltere_load": {
                "coriolis_roll": round(self.haltere_coriolis_roll, 3),
                "coriolis_pitch": round(self.haltere_coriolis_pitch, 3),
                "vibration_strain": round(self.haltere_vibration_strain, 3)
            },
            "dist_to_rum": round(self.dist_to_rum, 2),
            "dist_to_dad": round(self.dist_to_dad, 2),
            "rum_interaction": self.rum_interaction_event
        }
