"""
prewarm_tts_cache.py - Automated In-Cabin Voice Pre-Warming Suite for CarPi5
Pre-renders and locks ~150 core automotive phrases into SQLite WAL tts_cache.db
with is_locked=1 so they are permanent, never pruned, and cached into RAM (/dev/shm)
for instant <10ms replay without synthesis lag.
"""

import os
import sys
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.hardware.audio_player import AudioPlayer, TTSCacheManager

# Core phrase library categorized for the Dodge Dart 1.4T cockpit & R.U.M. persona
PREWARM_PHRASES = [
    # 1. System Boot & Greetings
    "Good morning, Dad! CarPi5 is online and ready to roll.",
    "Good afternoon, Dad! Systems are running smooth.",
    "Good evening, Dad! All sensors calibrated.",
    "Hey Dad! Ready whenever you are.",
    "All systems nominal, Dad.",
    "Ignition detected! Let's hit the road.",
    "Offline mode active. Local neural models ready.",
    "I'm here, Dad!",
    "CarPi5 system ready.",
    "Connecting to Dodge Dart onboard computer.",

    # 2. Powertrain & MultiAir Protection
    "MultiAir oil is cold. Please keep RPMs under 3,000.",
    "MultiAir operating temperature reached. Full boost unlocked!",
    "Coolant temperature is nominal at 195 degrees.",
    "Heads up Dad, coolant temperature is climbing over 215 degrees.",
    "Turbo boost holding steady at 15 PSI.",
    "Peak boost achieved! 22 PSI on that pull, Dad!",
    "Wastegate spool health is at 100 percent.",
    "Intake air temperature is nice and cool.",
    "Battery voltage is looking strong at 14 volts.",
    "Engine running smooth.",
    "MultiAir actuation solenoids fully primed.",
    "Oil pressure and temperature are right in the sweet spot.",

    # 3. Transmission & Shift Coaching
    "Clean shift! 100 point rev match, Dad!",
    "Silky smooth shift! Perfect gear transition.",
    "Nice launch! Clutch bite was spot on.",
    "Shift up to second gear.",
    "Shift up to third gear.",
    "Shift up to fourth gear.",
    "Shift up to fifth gear.",
    "Shift into sixth gear for cruising.",
    "You're in neutral.",
    "Coasting in neutral.",

    # 4. Drag Racing & Dyno Studio
    "Staged at the tree. Ready for launch!",
    "Three, two, one, launch!",
    "Zero to sixty recorded in 6.8 seconds! Great pull!",
    "Zero to sixty complete. New personal best, Dad!",
    "Virtual dyno measuring wheel horsepower...",
    "Pull complete! 175 wheel horsepower recorded.",
    "Peak wheel torque measured at 210 pound feet.",
    "Launch timer armed.",
    "Launch aborted.",

    # 5. Turn-by-Turn Navigation
    "In 500 feet, turn left.",
    "In 500 feet, turn right.",
    "In 1000 feet, keep left.",
    "In 1000 feet, keep right.",
    "Turn left onto the main road.",
    "Turn right onto the highway.",
    "Continue straight for 2 miles.",
    "Take the highway on-ramp.",
    "Take the upcoming exit.",
    "At the roundabout, take the second exit.",
    "Speed limit is 25 miles per hour.",
    "Speed limit is 35 miles per hour.",
    "Speed limit is 45 miles per hour.",
    "Speed limit is 55 miles per hour.",
    "Speed limit is 65 miles per hour.",
    "Speed limit is 75 miles per hour.",
    "You have arrived at your destination, Dad.",
    "Recalculating route...",
    "Route set. Let's get going!",

    # 6. Telephony & Family Kinship (Phase 15)
    "Dad, Nanny is calling!",
    "Dad, Papa is calling!",
    "Dad, Uncle Steven is calling!",
    "Dad, Aunt is calling!",
    "Incoming call from an unknown number. Should I screen it?",
    "Call connected through car speakers.",
    "Call ended.",
    "Dad, Uncle Steven sent you a text message.",
    "Dad, Nanny sent you a text message.",
    "Would you like me to reply?",
    "Say your message after the tone.",
    "Your message has been sent, Dad.",
    "Screening incoming call now.",
    "The caller hung up.",

    # 7. Living Mind & Bond Milestones (Phase 12)
    "How's your shoulder feeling today, Dad?",
    "Remember that third gear pull we did up the mountain pass?",
    "We've driven over 100 miles together now, Dad!",
    "We just crossed 500 miles together! I wrote all about it in my diary.",
    "We reached 1,000 miles together, Dad! Best co-pilot ever!",
    "I really love going on drives with you, Dad.",
    "Dream consolidation complete. I saved our drive to my memory.",
    "I'm keeping an eye on everything for you, Papa."
]

class PrewarmProgress:
    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.current_phrase = ""
        self.is_running = False
        self.completed = False
        self.start_time = 0.0

    def to_dict(self) -> Dict[str, Any]:
        elapsed = round(time.time() - self.start_time, 1) if self.start_time else 0.0
        pct = round((self.current / self.total * 100.0), 1) if self.total > 0 else 0.0
        return {
            "is_running": self.is_running,
            "completed": self.completed,
            "current": self.current,
            "total": self.total,
            "pct": pct,
            "current_phrase": self.current_phrase,
            "elapsed_sec": elapsed
        }

_global_prewarm_progress = PrewarmProgress(len(PREWARM_PHRASES))

def get_prewarm_status() -> Dict[str, Any]:
    return _global_prewarm_progress.to_dict()

def run_prewarm_job(
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    engine: Optional[str] = None,
    voice: Optional[str] = None
) -> Dict[str, Any]:
    """Execute prewarm synthesis across core cockpit phrases."""
    global _global_prewarm_progress
    player = AudioPlayer()
    cache_mgr = player.cache_mgr
    
    _global_prewarm_progress.is_running = True
    _global_prewarm_progress.completed = False
    _global_prewarm_progress.current = 0
    _global_prewarm_progress.start_time = time.time()
    _global_prewarm_progress.total = len(PREWARM_PHRASES)

    voice_id = voice or (player.kokoro_voice if player.tts_engine == "KOKORO" else player.tts_engine)
    pitch = player.pitch_factor

    print(f"[PREWARM] Starting voice pre-warming: {len(PREWARM_PHRASES)} phrases with voice '{voice_id}' at pitch {pitch}...")

    cached_count = 0
    synthesized_count = 0

    for idx, phrase in enumerate(PREWARM_PHRASES):
        _global_prewarm_progress.current = idx + 1
        _global_prewarm_progress.current_phrase = phrase[:45]

        # Check if already cached
        existing = cache_mgr.get(phrase, voice_id, pitch)
        if existing and os.path.exists(existing):
            cached_count += 1
        else:
            # Synthesize phrase synchronously to populate cache
            try:
                # Use piper or kokoro directly
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_wav = tmp.name

                success = False
                if player._kokoro_instance and (engine == "KOKORO" or player.tts_engine == "KOKORO"):
                    success = player._synthesize_kokoro(phrase, tmp_wav)
                elif player._piper_voice:
                    success = player._synthesize_piper(phrase, tmp_wav)
                
                if success and os.path.exists(tmp_wav):
                    cache_mgr.put(phrase, voice_id, pitch, tmp_wav, is_locked=True)
                    synthesized_count += 1
                    try:
                        os.remove(tmp_wav)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[PREWARM] Note synthesizing '{phrase[:30]}': {e}")

        if progress_callback:
            progress_callback(_global_prewarm_progress.to_dict())

    # Pin hot phrases to RAM hotpool
    cache_mgr.sync_hotpool()

    _global_prewarm_progress.is_running = False
    _global_prewarm_progress.completed = True
    stats = cache_mgr.get_stats()

    print(f"[PREWARM] Complete! Synthesized: {synthesized_count}, Already Cached: {cached_count}. Total Cache: {stats['total_mb']} MB")
    return _global_prewarm_progress.to_dict()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-warm CarPi5 TTS speech cache.")
    parser.add_argument("--voice", type=str, default=None, help="TTS voice name")
    parser.add_argument("--engine", type=str, default=None, help="TTS engine (KOKORO | PIPER)")
    args = parser.parse_args()

    run_prewarm_job(engine=args.engine, voice=args.voice)
