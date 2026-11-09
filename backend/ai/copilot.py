"""
copilot.py - Intelligent Co-Pilot & Race Engineer for Dodge Dart 1.4T
Updated with strict verbosity levels and "once-per-trip" alert latching.
"""

import time
from typing import Optional, Dict, Any, List
from .diagnostics import DiagnosticManager

class AICopilot:
    def __init__(self, driver_name: str = "Master Creator"):
        self.driver_name = driver_name
        self.diagnostics = DiagnosticManager()
        
        # Voice Mode: "MUTED", "ALERTS_ONLY", "COPILOT"
        self.voice_mode = "COPILOT"
        
        # State tracking for rules
        self.max_pull_boost = 0.0
        self.is_in_pull = False
        self.last_spoken_time = 0.0
        
        # Once-per-trip latches (Never repeat routine alerts in the same drive!)
        self.cold_warning_spoken = False
        self.warmup_ready_spoken = False
        self.last_announced_0_60: Optional[float] = None
        self.announced_dtcs = set()

    def set_voice_mode(self, mode: str):
        """Set voice mode: 'MUTED', 'ALERTS_ONLY', or 'COPILOT'."""
        self.voice_mode = mode.upper()
        print(f"[AI COPILOT] Voice mode set to: {self.voice_mode}")

    def evaluate_frame(self, frame: Any) -> Optional[Dict[str, Any]]:
        """
        Evaluate a single telemetry frame.
        Respects voice mode and once-per-trip latches.
        """
        now = time.time()
        time_since_speech = now - self.last_spoken_time

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
                "speech": f"Warning! Engine coolant is elevated at {int(frame.coolant_temp_f)} degrees. Check temperatures.",
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
                    "speech": f"{self.driver_name}, the oil is still chilly. Let's take it easy so our engine doesn't get hurt, okay?",
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
                    "emotion": "HAPPY",
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

        # 6. 0-60 MPH Launch Silent HUD Record (Do NOT speak automatically; answer when asked!)
        if frame.zero_to_sixty_time and frame.zero_to_sixty_time != self.last_announced_0_60:
            self.last_announced_0_60 = frame.zero_to_sixty_time
            return {
                "type": "LAUNCH",
                "priority": 1,
                "emotion": "EXCITED",
                "speech": "",  # Silent HUD badge - ask AI to hear spoken time!
                "hud_message": f"0-60 MPH: {frame.zero_to_sixty_time}s"
            }

        return None
