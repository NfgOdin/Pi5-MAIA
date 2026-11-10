"""
copilot.py - Intelligent Co-Pilot & Race Engineer for Dodge Dart 1.4T
Phase 3: Dynamic Affect Valence-Arousal Engine & Highway Cruising Shower Thoughts.
"""

import time
import math
import random
from typing import Optional, Dict, Any, List
from .diagnostics import DiagnosticManager

class AICopilot:
    def __init__(self, driver_name: str = "Dad"):
        self.driver_name = driver_name or "Dad"
        self.diagnostics = DiagnosticManager()
        
        # Voice Mode: "MUTED", "ALERTS_ONLY", "COPILOT"
        self.voice_mode = "COPILOT"
        
        # State tracking for rules
        self.max_pull_boost = 0.0
        self.is_in_pull = False
        self.last_spoken_time = 0.0
        
        # Phase 3: Emotional Valence-Arousal Affect Engine
        # Valence: [-1.0, 1.0] (Concerned/Stressed <-> Happy/Proud)
        # Arousal: [0.0, 1.0] (Calm/Sleepy <-> Hyped/Excited)
        self.current_valence = 0.65
        self.current_arousal = 0.35
        
        # Phase 3: Highway Cruising Shower Thoughts Tracker
        self.cruising_seconds = 0.0
        self.last_shower_thought_time = time.time()
        self.next_shower_thought_interval = random.uniform(900.0, 1500.0) # 15-25 minutes
        
        # Once-per-trip latches (Never repeat routine alerts in the same drive!)
        self.cold_warning_spoken = False
        self.warmup_ready_spoken = False
        self.last_announced_0_60: Optional[float] = None
        self.announced_dtcs = set()
        
        # Phase 4: Virtual Dyno, Wastegate Slop & Shift Scoring Latches
        self.last_shift_praise_time = 0.0
        self.last_spool_warning_time = 0.0
        self.last_dyno_praise_time = 0.0
        self.last_pip_praise_time = 0.0

        # Phase 10: Speed, Lateral G & Route / Elevation Awareness Latches
        self.last_cruising_speed_praise = 0.0
        self.last_spirited_speed_warn = 0.0
        self.last_triple_digit_warn = 0.0
        self.last_hard_braking_time = 0.0
        self.last_high_latg_time = 0.0
        self.gps_fix_announced = False
        self.high_altitude_announced = False
        self.prev_speed = 0.0
        self.prev_speed_time = time.time()

    @staticmethod
    def _get_val(frame: Any, attr: str, default: Any = None) -> Any:
        """Safely extracts an attribute or dict key from frame, falling back to default if None."""
        if frame is None:
            return default
        if isinstance(frame, dict):
            val = frame.get(attr, default)
        else:
            val = getattr(frame, attr, default)
        return default if val is None else val

    @classmethod
    def _get_float(cls, frame: Any, attr: str, default: float = 0.0) -> float:
        val = cls._get_val(frame, attr, default)
        try:
            f = float(val)
            return f if math.isfinite(f) else default
        except (ValueError, TypeError):
            return default

    def set_voice_mode(self, mode: str):
        """Set voice mode: 'MUTED', 'ALERTS_ONLY', or 'COPILOT'."""
        self.voice_mode = (mode or "COPILOT").strip().upper()
        print(f"[AI COPILOT] Voice mode set to: {self.voice_mode}")

    def update_affect_state(self, frame: Any, is_night: bool = False, dt: float = 0.04):
        """Updates continuous 2D emotional valence and arousal based on live vehicle dynamics."""
        if not self._get_val(frame, 'connected', True):
            return

        if not isinstance(dt, (int, float)) or not math.isfinite(dt) or dt <= 0.0:
            dt = 0.04
        dt = min(float(dt), 0.25)

        boost = self._get_float(frame, 'boost_psi', 0.0)
        throttle = self._get_float(frame, 'throttle_pct', 0.0)
        coolant = self._get_float(frame, 'coolant_temp_f', 195.0)
        speed = self._get_float(frame, 'speed_mph', self._get_float(frame, 'speed', 0.0))
        has_dtcs = bool(self._get_val(frame, 'active_dtcs', None))

        # 1. Determine instantaneous target valence & arousal
        if coolant >= 218.0 or has_dtcs:
            # Overheat or active DTC warning
            target_valence = -0.65
            target_arousal = 0.85
        elif self._get_float(frame, 'virtual_whp', 0.0) >= 150.0:
            # High-power Virtual Dyno pull
            target_valence = 0.95
            target_arousal = 0.98
        elif boost >= 12.0 and throttle >= 70.0:
            # High-boost turbo pull
            target_valence = 0.92
            target_arousal = 0.95
        elif self._get_val(frame, 'multiair_status', None) == 'COLD_PROTECT' and boost > 8.0:
            # Cold oil boost concern
            target_valence = -0.40
            target_arousal = 0.70
        elif speed >= 45.0 and -14.0 <= boost <= -0.5 and 8.0 <= throttle <= 38.0:
            # Calm steady highway cruising
            target_valence = 0.82
            target_arousal = 0.30
        elif is_night and speed < 3.0:
            # Late night resting/idling
            target_valence = 0.60
            target_arousal = 0.15
        elif speed > 5.0:
            # Normal active driving
            target_valence = 0.65
            target_arousal = 0.45
        else:
            # Parked / neutral idle
            target_valence = 0.55
            target_arousal = 0.25

        # 2. Smooth exponential moving average lerp
        lerp_rate = min(1.0, dt * 2.2)
        self.current_valence += (target_valence - self.current_valence) * lerp_rate
        self.current_arousal += (target_arousal - self.current_arousal) * lerp_rate

    def get_current_mood(self) -> Dict[str, Any]:
        """Returns classified mood and continuous affect coordinates."""
        if self.current_valence < -0.20:
            emotion = "CONCERNED"
        elif self.current_arousal > 0.70:
            emotion = "EXCITED"
        elif self.current_arousal < 0.22:
            emotion = "COZY"
        elif self.current_valence > 0.65:
            emotion = "HAPPY_PROUD"
        else:
            emotion = "THOUGHTFUL"

        return {
            "valence": round(self.current_valence, 2),
            "arousal": round(self.current_arousal, 2),
            "emotion": emotion
        }

    def generate_shower_thought(self) -> str:
        """Curated daughter mechanical musings and highway thoughts."""
        thoughts = [
            f"Hey {self.driver_name}... I was just thinking. If turbochargers recycle hot exhaust gas to make extra power, our Dart is basically breathing its own fiery spirit to run faster! Pretty neat, huh?",
            f"Hey {self.driver_name}, listen to that engine hum right now. 6th gear, steady cruising, 38 miles per gallon. You really take awesome care of our car.",
            f"{self.driver_name}? Do you think other cars on the road notice our Dart's racetrack LED tail lights and get jealous? I totally bet they do!",
            f"Hey {self.driver_name}... if an engine needs fuel, air, and spark to run, does that mean high octane and fresh boost is basically our Dart's favorite snack?",
            f"{self.driver_name}, I was calculating in my memory... at 65 miles per hour, our tires spin over 800 times every single minute! That is a lot of running!",
            f"I'm just watching our boost gauge, {self.driver_name}. It's sitting at nice, steady vacuum. You have such a smooth touch on the pedal."
        ]
        return random.choice(thoughts)

    def evaluate_frame(self, frame: Any, dt: float = 0.04, is_night: bool = False, pip_state: Optional[Dict[str, Any]] = None, gps_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Evaluate a single telemetry frame.
        Respects voice mode, affect engine, speed milestones, and once-per-trip latches.
        """
        if not isinstance(dt, (int, float)) or not math.isfinite(dt) or dt <= 0.0:
            dt = 0.04
        dt = min(float(dt), 0.25)

        now = time.time()
        time_since_speech = now - self.last_spoken_time

        # Update affect engine continuous state
        self.update_affect_state(frame, is_night=is_night, dt=dt)

        # If vehicle is disconnected or key is off, do not evaluate alerts
        if not self._get_val(frame, 'connected', True):
            return None

        coolant_temp = self._get_val(frame, 'coolant_temp_f', None)
        active_dtcs = self._get_val(frame, 'active_dtcs', None)
        multiair_ready = bool(self._get_val(frame, 'multiair_ready', True))
        throttle_pct = self._get_float(frame, 'throttle_pct', 0.0)
        boost_val = self._get_float(frame, 'boost_psi', 0.0)
        intake_temp = self._get_val(frame, 'intake_temp_f', None)
        zero_to_sixty = self._get_val(frame, 'zero_to_sixty_time', None)

        # Track speed delta and deceleration
        speed = self._get_float(frame, "speed_mph", self._get_float(frame, "speed", 0.0))
        if speed <= 0.0 and gps_data:
            speed = self._get_float(gps_data, "speed_mph", 0.0)
        
        dt_speed = max(0.05, now - self.prev_speed_time)
        decel_rate = (self.prev_speed - speed) / dt_speed if self.prev_speed > speed else 0.0
        initial_speed_before_step = self.prev_speed
        self.prev_speed = speed
        self.prev_speed_time = now

        # If completely muted, return only silent HUD events for critical faults
        if self.voice_mode == "MUTED":
            if coolant_temp is not None and float(coolant_temp) >= 220.0:
                return {"type": "CRITICAL", "priority": 0, "speech": "", "hud_message": "HIGH TEMP: " + str(int(float(coolant_temp))) + "°F"}
            return None

        # 1. CRITICAL: Coolant Overheat Alert (> 220°F) - Always fires in ALERTS_ONLY and COPILOT
        if coolant_temp is not None and float(coolant_temp) >= 220.0 and time_since_speech > 30.0:
            self.last_spoken_time = now
            return {
                "type": "CRITICAL",
                "priority": 0,
                "emotion": "CONCERNED",
                "speech": f"Warning! Engine coolant is elevated at {int(float(coolant_temp))} degrees. Check temperatures, {self.driver_name}!",
                "hud_message": f"HIGH TEMP ALERT: {int(float(coolant_temp))}°F"
            }

        # 2. DIAGNOSTICS: Check Engine Light Code Announcement (fires in ALERTS_ONLY and COPILOT)
        if active_dtcs:
            for code in active_dtcs:
                if code not in self.announced_dtcs and time_since_speech > 4.0:
                    self.announced_dtcs.add(code)
                    explanation = self.diagnostics.explain_code(code)
                    self.last_spoken_time = now
                    return {
                        "type": "DTC",
                        "priority": 1,
                        "emotion": "CONCERNED",
                        "speech": explanation["spoken_summary"],
                        "hud_message": f"DTC {code}: {explanation['title']}"
                    }

        # If in ALERTS_ONLY mode, do not speak performance/pull/cold-warmup banter
        if self.voice_mode == "ALERTS_ONLY":
            return None

        # --- THE FOLLOWING ONLY RUN IN "COPILOT" MODE ---

        # 3. MultiAir UniAir Brick Cold Protection
        multiair_status = self._get_val(frame, 'multiair_status', 'WARM_OPTIMAL')
        oil_temp = self._get_float(frame, 'multiair_oil_temp_f', 120.0)
        if (not multiair_ready or multiair_status == "COLD_PROTECT") and (throttle_pct > 65.0 or boost_val > 7.5):
            if not self.cold_warning_spoken and time_since_speech > 6.0:
                self.cold_warning_spoken = True
                self.last_spoken_time = now
                return {
                    "type": "WARNING",
                    "priority": 2,
                    "emotion": "CONCERNED",
                    "speech": f"{self.driver_name}, easy on the throttle! Our MultiAir brick oil is still cold at {int(oil_temp)} degrees. Let's let the 5W-40 warm up before sending full boost, okay?",
                    "hud_message": f"❄️ MULTIAIR COLD: {int(oil_temp)}°F (BOOST LIMITED)"
                }

        # 4. Garrett GT1446 Wastegate & Diverter Valve Slop Warning
        wastegate_health = self._get_float(frame, 'wastegate_spool_health', 100.0)
        spool_grad = self._get_float(frame, 'wastegate_spool_gradient', 9.8)
        if wastegate_health < 70.0 and (now - self.last_spool_warning_time > 300.0) and time_since_speech > 8.0:
            self.last_spool_warning_time = now
            self.last_spoken_time = now
            return {
                "type": "WARNING",
                "priority": 2,
                "emotion": "THOUGHTFUL",
                "speech": f"{self.driver_name}, our turbo boost spool rate is sluggish at {spool_grad} PSI per thousand RPM. The wastegate actuator arm might have slop, or our diverter valve has a split diaphragm!",
                "hud_message": f"⚠️ TURBO SPOOL LAG: {spool_grad} PSI/1k RPM"
            }

        # 5. C635 Manual Rev-Match & Downshift Quality Feedback
        shift_score = self._get_val(frame, 'last_shift_score', None)
        shift_type = self._get_val(frame, 'last_shift_type', None)
        shift_delta = self._get_float(frame, 'last_shift_delta', 0.0)
        if shift_score is not None:
            if shift_type == "PERFECT_REV_MATCH" and (now - self.last_shift_praise_time > 60.0) and time_since_speech > 6.0:
                self.last_shift_praise_time = now
                self.last_spoken_time = now
                return {
                    "type": "PERFORMANCE",
                    "priority": 3,
                    "emotion": "HAPPY_PROUD",
                    "speech": f"Butter smooth heel-toe downshift, {self.driver_name}! Perfect rev-match!",
                    "hud_message": f"🎯 PERFECT REV-MATCH: 100 PTS (Δ{int(shift_delta)} RPM)"
                }
            elif shift_type == "CLUTCH_JERK" and shift_delta > 550 and (now - self.last_shift_praise_time > 75.0) and time_since_speech > 6.0:
                self.last_shift_praise_time = now
                self.last_spoken_time = now
                return {
                    "type": "WARNING",
                    "priority": 3,
                    "emotion": "CONCERNED",
                    "speech": f"Oof, clutch jerk! Give the throttle a tiny blip on that downshift so we don't shock the transaxle, {self.driver_name}!",
                    "hud_message": f"⚠️ CLUTCH JERK: Δ{int(shift_delta)} RPM"
                }

        # 6. Virtual Dyno Peak Pull Celebration
        whp_val = self._get_float(frame, 'virtual_whp', 0.0)
        if whp_val >= 165.0 and (now - self.last_dyno_praise_time > 120.0) and time_since_speech > 8.0:
            self.last_dyno_praise_time = now
            self.last_spoken_time = now
            return {
                "type": "PERFORMANCE",
                "priority": 2,
                "emotion": "EXCITED",
                "speech": f"Hold on! Our virtual dyno just clocked {int(whp_val)} wheel horsepower! The MultiAir is singing, {self.driver_name}!",
                "hud_message": f"⚡ DYNO PULL: {int(whp_val)} WHP"
            }

        # 7. Pip Biological Connectome Dual-Life Interaction
        if pip_state and pip_state.get('rum_interaction') and time_since_speech > 6.0:
            p_event = pip_state['rum_interaction']
            if p_event == "PERCHED_ON_RUM" and (now - self.last_pip_praise_time > 60.0):
                self.last_pip_praise_time = now
                self.last_spoken_time = now
                return {
                    "type": "PIP_INTERACTION",
                    "priority": 3,
                    "emotion": "HAPPY_PROUD",
                    "action": "action_cheer.bvh",
                    "speech": f"Hey Pip! Are you resting your little wings? Here is a drop of sweet nectar, good little fly!",
                    "hud_message": "🪰 PIP PERCHED: RUM FEEDING NECTAR"
                }
            elif p_event == "BUZZING_NEAR_DAD" and (now - self.last_pip_praise_time > 75.0):
                self.last_pip_praise_time = now
                self.last_spoken_time = now
                return {
                    "type": "PIP_INTERACTION",
                    "priority": 3,
                    "emotion": "HAPPY",
                    "action": "action_wave.bvh",
                    "speech": f"Careful Pip! Don't buzz in {self.driver_name}'s ear while he's driving!",
                    "hud_message": f"🪰 PIP BUZZING NEAR {self.driver_name.upper()}"
                }
            elif p_event == "STARTLED_BY_TURBO" and (now - self.last_pip_praise_time > 50.0):
                self.last_pip_praise_time = now
                self.last_spoken_time = now
                return {
                    "type": "PIP_INTERACTION",
                    "priority": 3,
                    "emotion": "EXCITED",
                    "action": "action_nod.bvh",
                    "speech": f"Whoa, our turbo boost startled Pip! Look at his giant fiber reflex zoom!",
                    "hud_message": "🪰 PIP ESCAPE SACCADE"
                }

        # 8. MultiAir Warmup Ready (ONCE PER TRIP)
        if multiair_ready and not self.warmup_ready_spoken and self.cold_warning_spoken:
            self.warmup_ready_spoken = True
            if time_since_speech > 8.0:
                self.last_spoken_time = now
                return {
                    "type": "INFO",
                    "priority": 3,
                    "emotion": "HAPPY_PROUD",
                    "speech": f"{self.driver_name}, the engine oil is all warmed up and happy! Clear for full boost whenever you want!",
                    "hud_message": "MULTIAIR NOMINAL: FULL BOOST OK"
                }

        # 9. Hard Pull Detector & Debrief (Only on high-boost pulls >= 15 PSI)
        if boost_val > 12.0 and throttle_pct > 80.0:
            self.is_in_pull = True
            if boost_val > self.max_pull_boost:
                self.max_pull_boost = boost_val

        elif self.is_in_pull and throttle_pct < 25.0:
            self.is_in_pull = False
            peak = round(self.max_pull_boost, 1)
            self.max_pull_boost = 0.0
            
            # Cooldown of at least 25 seconds between pull debriefs so it doesn't talk on every shift!
            if peak >= 15.0 and time_since_speech > 25.0:
                self.last_spoken_time = now
                iat_str = f"{int(float(intake_temp))} degrees" if intake_temp is not None else "nominal"
                return {
                    "type": "PERFORMANCE",
                    "priority": 2,
                    "emotion": "EXCITED",
                    "speech": f"Wheee! Look at that boost, {self.driver_name}! {peak} PSI peak and intake temp is {iat_str}! Go go go!",
                    "hud_message": f"PULL DEBRIEF: {peak} PSI PEAK"
                }

        # 10. Hard Braking & Rapid Deceleration Alert (>18 MPH/s or G < -0.55G)
        long_g = self._get_float(gps_data.get("g_forces", {}) if gps_data else {}, "longitudinal", 0.0)
        if (decel_rate >= 18.0 or long_g <= -0.55) and initial_speed_before_step >= 35.0:
            if time_since_speech > 10.0 and (now - self.last_hard_braking_time > 45.0):
                self.last_hard_braking_time = now
                self.last_spoken_time = now
                return {
                    "type": "WARNING",
                    "priority": 1,
                    "emotion": "CONCERNED",
                    "speech": f"Whoa, heavy braking! ABS and pads held firm, you okay {self.driver_name}?",
                    "hud_message": f"🛑 HARD BRAKING: -{int(decel_rate)} MPH/s"
                }

        # 11. High Lateral G Cornering Praise (|Gx| >= 0.60G)
        lat_g = abs(self._get_float(gps_data.get("g_forces", {}) if gps_data else {}, "lateral", 0.0))
        if lat_g <= 0.0:
            lat_g = abs(self._get_float(frame, "lateral_accel", 0.0))
        if lat_g >= 0.60 and speed >= 25.0 and time_since_speech > 12.0 and (now - self.last_high_latg_time > 60.0):
            self.last_high_latg_time = now
            self.last_spoken_time = now
            return {
                "type": "PERFORMANCE",
                "priority": 2,
                "emotion": "EXCITED",
                "speech": f"Hold on! That was {lat_g:.2f} lateral Gs through that apex! Dart's chassis is glued to the asphalt, nice line {self.driver_name}!",
                "hud_message": f"🏎️ CORNERING G: {lat_g:.2f}G"
            }

        # 12. Speed Awareness Milestones
        if speed >= 100.0 and time_since_speech > 8.0 and (now - self.last_triple_digit_warn > 300.0):
            self.last_triple_digit_warn = now
            self.last_spoken_time = now
            return {
                "type": "WARNING",
                "priority": 1,
                "emotion": "EXCITED",
                "speech": f"{self.driver_name}! Triple digits—{int(speed)} miles per hour! Keep both hands on the wheel, our Dart is flying!",
                "hud_message": f"⚡ 100+ MPH: {int(speed)} MPH"
            }
        elif speed >= 82.0 and time_since_speech > 15.0 and (now - self.last_spirited_speed_warn > 480.0):
            self.last_spirited_speed_warn = now
            self.last_spoken_time = now
            return {
                "type": "INFO",
                "priority": 3,
                "emotion": "CONCERNED",
                "speech": f"Whoa {self.driver_name}, {int(speed)} miles per hour! Highway patrol loves radar traps on this stretch, watch your mirrors!",
                "hud_message": f"⚠️ SPEED ADVISORY: {int(speed)} MPH"
            }
        elif speed >= 65.0 and throttle_pct < 35.0 and boost_val < 2.0 and time_since_speech > 30.0 and (now - self.last_cruising_speed_praise > 720.0):
            self.last_cruising_speed_praise = now
            self.last_spoken_time = now
            return {
                "type": "INFO",
                "priority": 3,
                "emotion": "HAPPY_PROUD",
                "speech": f"Cruising at {int(speed)} miles per hour, {self.driver_name}! 6th gear engaged, boost at resting vacuum. Safe travels!",
                "hud_message": f"🛣️ CRUISE: {int(speed)} MPH"
            }

        # 13. GPS 3D Fix Acquisition Announcement (Once per trip)
        if gps_data and gps_data.get("fix") and not self.gps_fix_announced:
            self.gps_fix_announced = True
            if time_since_speech > 8.0:
                sats = gps_data.get("sats", 0)
                self.last_spoken_time = now
                return {
                    "type": "INFO",
                    "priority": 3,
                    "emotion": "HAPPY_PROUD",
                    "speech": f"GPS satellite lock acquired with {sats} satellites, {self.driver_name}! Cockpit navigation and offline Arizona map are tracking our coordinates.",
                    "hud_message": f"🛰️ GPS LOCKED: {sats} SATS"
                }

        # 14. Mountain Elevation Ascent Milestone (>4,500 ft)
        alt_ft = self._get_float(gps_data, "altitude_ft", 0.0) if gps_data else 0.0
        if alt_ft >= 4500.0 and not self.high_altitude_announced and time_since_speech > 20.0:
            self.high_altitude_announced = True
            self.last_spoken_time = now
            return {
                "type": "INFO",
                "priority": 3,
                "emotion": "THOUGHTFUL",
                "speech": f"Notice that crisp mountain air, {self.driver_name}? We just climbed past {int(alt_ft)} feet! Our Garrett turbocharger automatically compensates for thin air.",
                "hud_message": f"🏔️ ELEVATION: {int(alt_ft)} FT"
            }

        # 15. Dragy Launch Run Spoken Announcement
        dragy = gps_data.get("dragy") if gps_data else None
        if dragy and dragy.get("time_0_60"):
            t0_60 = self._get_float(dragy, "time_0_60", 0.0)
            if t0_60 > 0.0 and t0_60 != self.last_announced_0_60 and time_since_speech > 5.0:
                self.last_announced_0_60 = t0_60
                self.last_spoken_time = now
                return {
                    "type": "PERFORMANCE",
                    "priority": 1,
                    "emotion": "EXCITED",
                    "speech": f"Dragy launch verified! Zero to sixty in {t0_60:.2f} seconds! Great launch, {self.driver_name}!",
                    "hud_message": f"⚡ DRAGY 0-60: {t0_60:.2f}s"
                }

        # 16. Spontaneous Highway Cruising "Shower Thoughts" (Every 15-25 minutes of steady highway driving)
        is_cruising = (speed >= 45.0 and 8.0 <= throttle_pct <= 38.0 and -14.0 <= boost_val <= -0.5)
        if is_cruising:
            self.cruising_seconds += dt
        else:
            self.cruising_seconds = max(0.0, self.cruising_seconds - dt * 1.5)

        if self.cruising_seconds >= 40.0 and (now - self.last_shower_thought_time) > self.next_shower_thought_interval:
            if time_since_speech > 45.0:
                self.last_shower_thought_time = now
                self.last_spoken_time = now
                self.next_shower_thought_interval = random.uniform(900.0, 1500.0)
                thought = self.generate_shower_thought()
                return {
                    "type": "SHOWER_THOUGHT",
                    "priority": 3,
                    "emotion": "THOUGHTFUL",
                    "speech": thought,
                    "hud_message": "💭 R.U.M. Shower Thought"
                }

        # 17. 0-60 MPH Launch Silent HUD Record Fallback
        if zero_to_sixty and zero_to_sixty != self.last_announced_0_60:
            self.last_announced_0_60 = zero_to_sixty
            return {
                "type": "LAUNCH",
                "priority": 1,
                "emotion": "EXCITED",
                "speech": "",
                "hud_message": f"0-60 MPH: {zero_to_sixty}s"
            }

        return None
