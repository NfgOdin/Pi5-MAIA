"""
copilot.py - Intelligent Co-Pilot & Race Engineer for Dodge Dart 1.4T
Phase 3: Dynamic Affect Valence-Arousal Engine & Highway Cruising Shower Thoughts.
"""

import time
import random
from typing import Optional, Dict, Any, List
from .diagnostics import DiagnosticManager

class AICopilot:
    def __init__(self, driver_name: str = "Dad"):
        self.driver_name = driver_name
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

    def set_voice_mode(self, mode: str):
        """Set voice mode: 'MUTED', 'ALERTS_ONLY', or 'COPILOT'."""
        self.voice_mode = mode.upper()
        print(f"[AI COPILOT] Voice mode set to: {self.voice_mode}")

    def update_affect_state(self, frame: Any, is_night: bool = False, dt: float = 0.04):
        """Updates continuous 2D emotional valence and arousal based on live vehicle dynamics."""
        if not getattr(frame, 'connected', True):
            return

        boost = getattr(frame, 'boost_psi', 0.0) or 0.0
        throttle = getattr(frame, 'throttle_pct', 0.0) or 0.0
        coolant = getattr(frame, 'coolant_temp_f', 195.0) or 195.0
        speed = getattr(frame, 'speed_mph', getattr(frame, 'speed', 0.0)) or 0.0
        has_dtcs = bool(getattr(frame, 'active_dtcs', None))

        # 1. Determine instantaneous target valence & arousal
        if coolant >= 218.0 or has_dtcs:
            # Overheat or active DTC warning
            target_valence = -0.65
            target_arousal = 0.85
        elif boost >= 12.0 and throttle >= 70.0:
            # High-boost turbo pull
            target_valence = 0.92
            target_arousal = 0.95
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

    def evaluate_frame(self, frame: Any, dt: float = 0.04, is_night: bool = False) -> Optional[Dict[str, Any]]:
        """
        Evaluate a single telemetry frame.
        Respects voice mode, affect engine, and once-per-trip latches.
        """
        now = time.time()
        time_since_speech = now - self.last_spoken_time

        # Update affect engine continuous state
        self.update_affect_state(frame, is_night=is_night, dt=dt)

        # If vehicle is disconnected or key is off, do not evaluate alerts
        if not getattr(frame, 'connected', True):
            return None

        # If completely muted, return only silent HUD events for critical faults
        if self.voice_mode == "MUTED":
            if frame.coolant_temp_f is not None and frame.coolant_temp_f >= 220.0:
                return {"type": "CRITICAL", "priority": 0, "speech": "", "hud_message": "HIGH TEMP: " + str(int(frame.coolant_temp_f)) + "°F"}
            return None

        # 1. CRITICAL: Coolant Overheat Alert (> 220°F) - Always fires in ALERTS_ONLY and COPILOT
        if frame.coolant_temp_f is not None and frame.coolant_temp_f >= 220.0 and time_since_speech > 30.0:
            self.last_spoken_time = now
            return {
                "type": "CRITICAL",
                "priority": 0,
                "emotion": "CONCERNED",
                "speech": f"Warning! Engine coolant is elevated at {int(frame.coolant_temp_f)} degrees. Check temperatures, {self.driver_name}!",
                "hud_message": f"HIGH TEMP ALERT: {int(frame.coolant_temp_f)}°F"
            }

        # 2. DIAGNOSTICS: Check Engine Light Code Announcement (fires in ALERTS_ONLY and COPILOT)
        if frame.active_dtcs:
            for code in frame.active_dtcs:
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

        # 3. MultiAir Cold Boost Protection (ONCE PER TRIP)
        if not frame.multiair_ready and frame.throttle_pct > 65.0:
            if not self.cold_warning_spoken and time_since_speech > 6.0:
                self.cold_warning_spoken = True
                self.last_spoken_time = now
                return {
                    "type": "WARNING",
                    "priority": 2,
                    "emotion": "CONCERNED",
                    "speech": f"{self.driver_name}, the oil is still chilly. Let's take it easy so our MultiAir doesn't get hurt, okay?",
                    "hud_message": "COLD ENGINE: BOOST LIMITED"
                }

        # 4. MultiAir Warmup Ready (ONCE PER TRIP)
        if frame.multiair_ready and not self.warmup_ready_spoken and self.cold_warning_spoken:
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

        # 5. Hard Pull Detector & Debrief (Only on high-boost pulls >= 15 PSI)
        if frame.boost_psi is not None and frame.boost_psi > 12.0 and frame.throttle_pct > 80.0:
            self.is_in_pull = True
            if frame.boost_psi > self.max_pull_boost:
                self.max_pull_boost = frame.boost_psi

        elif self.is_in_pull and frame.throttle_pct < 25.0:
            self.is_in_pull = False
            peak = self.max_pull_boost
            self.max_pull_boost = 0.0
            
            # Cooldown of at least 25 seconds between pull debriefs so it doesn't talk on every shift!
            if peak >= 15.0 and time_since_speech > 25.0:
                self.last_spoken_time = now
                iat_str = f"{int(frame.intake_temp_f)} degrees" if frame.intake_temp_f is not None else "nominal"
                return {
                    "type": "PERFORMANCE",
                    "priority": 2,
                    "emotion": "EXCITED",
                    "speech": f"Wheee! Look at that boost, {self.driver_name}! {peak} PSI peak and intake temp is {iat_str}! Go go go!",
                    "hud_message": f"PULL DEBRIEF: {peak} PSI PEAK"
                }

        # 6. Spontaneous Highway Cruising "Shower Thoughts" (Every 15-25 minutes of steady highway driving)
        speed = getattr(frame, "speed_mph", getattr(frame, "speed", 0.0)) or 0.0
        boost = getattr(frame, "boost_psi", 0.0) or 0.0
        throttle = getattr(frame, "throttle_pct", 0.0) or 0.0
        
        is_cruising = (speed >= 45.0 and 8.0 <= throttle <= 38.0 and -14.0 <= boost <= -0.5)
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

        # 7. 0-60 MPH Launch Silent HUD Record
        if frame.zero_to_sixty_time and frame.zero_to_sixty_time != self.last_announced_0_60:
            self.last_announced_0_60 = frame.zero_to_sixty_time
            return {
                "type": "LAUNCH",
                "priority": 1,
                "emotion": "EXCITED",
                "speech": "",
                "hud_message": f"0-60 MPH: {frame.zero_to_sixty_time}s"
            }

        return None
