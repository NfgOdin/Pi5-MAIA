"""
memory_manager.py - Persistent Drive Memory & Startup Greeting Engine
Maintains long-term memory across reboots for M.A.I.A. (CarPi5).
Tracks:
- Total drive sessions across car lifecycles
- Last shutdown timestamp & downtime duration
- Peak boost & performance milestones
- Holiday & calendar awareness (Valentine's, Halloween, Christmas, etc.)
- Dynamic, non-repeating contextual startup greetings
"""

import os
import json
import time
import random
import threading
from datetime import datetime, date
from typing import Dict, Any, Optional, List

class MemoryManager:
    def __init__(self, memory_file: Optional[str] = None):
        self.memory_file = memory_file or os.path.join(os.path.dirname(__file__), "ai_memory.json")
        self._lock = threading.RLock()
        self.memory = self._load_memory()

    def _load_memory(self) -> Dict[str, Any]:
        default_memory = {
            "total_drives": 0,
            "first_boot_date": datetime.now().isoformat(),
            "last_boot_date": None,
            "last_shutdown_date": None,
            "all_time_stats": {
                "peak_boost_ever": 18.2,
                "best_0_60": 7.4,
                "top_speed": 110
            },
            "last_session_stats": {
                "peak_boost": 16.5,
                "last_0_60": None,
                "trip_duration_min": 24
            },
            "recent_greeting_hashes": [],
            "known_notes": [
                "Loves 3rd gear turbo pulls",
                "Strict about MultiAir 5W-40 oil changes"
            ]
        }

        with self._lock:
            if os.path.exists(self.memory_file):
                try:
                    with open(self.memory_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            default_memory.update(data)
                except Exception as e:
                    print(f"[MEMORY] Error reading memory file: {e}")

        return default_memory

    def save_memory(self):
        with self._lock:
            try:
                with open(self.memory_file, "w", encoding="utf-8") as f:
                    json.dump(self.memory, f, indent=2)
            except Exception as e:
                print(f"[MEMORY] Error saving memory: {e}")

    def record_boot(self) -> Dict[str, Any]:
        """Called once upon application startup. Increments session counter and computes downtime."""
        now = datetime.now()
        last_boot_str = self.memory.get("last_boot_date")
        
        hours_since_last_drive = None
        if last_boot_str:
            try:
                last_dt = datetime.fromisoformat(last_boot_str)
                hours_since_last_drive = (now - last_dt).total_seconds() / 3600.0
            except Exception:
                pass

        self.memory["total_drives"] = self.memory.get("total_drives", 0) + 1
        self.memory["last_boot_date"] = now.isoformat()
        self.save_memory()

        return {
            "total_drives": self.memory["total_drives"],
            "hours_since_last_drive": hours_since_last_drive,
            "current_time": now
        }

    def detect_holiday(self, dt: Optional[Any] = None) -> Optional[str]:
        if dt is None:
            dt = datetime.now()
        elif isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except Exception:
                dt = datetime.now()
        m, d = dt.month, dt.day
        if m == 1 and d == 1:
            return "New Year's Day"
        elif m == 2 and d == 14:
            return "Valentine's Day"
        elif m == 3 and d == 17:
            return "St. Patrick's Day"
        elif m == 7 and d == 4:
            return "4th of July"
        elif m == 10 and d == 31:
            return "Halloween"
        elif m == 12 and d == 24:
            return "Christmas Eve"
        elif m == 12 and d == 25:
            return "Christmas Day"
        elif m == 12 and d == 31:
            return "New Year's Eve"
        return None

    def get_time_of_day_category(self, hour: int) -> str:
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    def generate_startup_greeting(
        self,
        driver_address: str,
        persona: Dict[str, Any],
        live_telemetry: Optional[Dict[str, Any]] = None,
        llm_chat_fn: Optional[Any] = None
    ) -> str:
        """
        Synthesizes a completely dynamic, non-repeating, persona-driven startup greeting.
        Combines time of day, day of week (Mon-Sun), holidays, drive milestones, and persona JSON pools.
        """
        now = datetime.now()
        hour = now.hour
        weekday_name = now.strftime("%A")
        time_cat = self.get_time_of_day_category(hour)
        holiday = self.detect_holiday(now)

        drive_num = self.memory.get("total_drives", 1)
        peak_boost = self.memory.get("all_time_stats", {}).get("peak_boost_ever", 18.2)
        p_name = persona.get("name", "Companion")
        greetings_cfg = persona.get("greetings", {}) if isinstance(persona.get("greetings"), dict) else {}

        class _SafeFmt(dict):
            def __missing__(self, key: str) -> str:
                return ""

        fmt_ctx = _SafeFmt(
            driver_address=driver_address,
            day_of_week=weekday_name,
            time_of_day=time_cat,
            holiday=holiday or "",
            holiday_clause=f" and {holiday}" if holiday else "",
            drive_num=drive_num,
            peak_boost=peak_boost,
            persona_name=p_name,
        )

        # Context package for LLM prompt if available
        context_desc = (
            f"Current time: {now.strftime('%I:%M %p')}, {weekday_name} ({time_cat}). "
            f"Drive number together: #{drive_num}. "
            f"{f'Holiday today: {holiday}. ' if holiday else ''}"
            f"Driver title/name: {driver_address}. "
            f"Car: 2013 Dodge Dart 1.4L Turbo MultiAir manual. All-time peak boost: {peak_boost} PSI."
        )

        # If LLM function provided and connected, query dynamic generation using persona prompt + instruction
        if llm_chat_fn and callable(llm_chat_fn):
            base_persona_prompt = (persona.get("prompt") or f"You are {p_name}, the driver's Dodge Dart AI companion.").format_map(fmt_ctx)
            neural_inst = greetings_cfg.get(
                "neural_instruction",
                "Greet {driver_address} warmly as the car starts. Strictly 1-2 short natural sentences mentioning the day ({day_of_week}) or engine readiness."
            ).format_map(fmt_ctx)
            system_prompt = f"{base_persona_prompt}\n[GREETING TASK: {neural_inst} Context: {context_desc}]"
            try:
                ai_greeting = llm_chat_fn(system_prompt, live_telemetry=live_telemetry, is_greeting=True)
                if ai_greeting and len(ai_greeting.strip()) > 10:
                    return ai_greeting.strip()
            except Exception as e:
                print(f"[MEMORY] Fallback to procedural greeting generator: {e}")

        # Build procedural matrix purely from persona JSON (holiday -> weekday -> time_of_day -> startup_fallback)
        greeting_pool: List[str] = []

        holiday_map = greetings_cfg.get("holidays", {}) if isinstance(greetings_cfg.get("holidays"), dict) else {}
        if holiday and holiday in holiday_map:
            for item in holiday_map[holiday]:
                if isinstance(item, str) and item.strip():
                    greeting_pool.append(item.format_map(fmt_ctx))

        weekday_map = greetings_cfg.get("weekdays", {}) if isinstance(greetings_cfg.get("weekdays"), dict) else {}
        if weekday_name in weekday_map:
            for item in weekday_map[weekday_name]:
                if isinstance(item, str) and item.strip():
                    greeting_pool.append(item.format_map(fmt_ctx))

        instant_map = greetings_cfg.get("instant", {}) if isinstance(greetings_cfg.get("instant"), dict) else {}
        for item in instant_map.get(time_cat, []):
            if isinstance(item, str) and item.strip():
                greeting_pool.append(item.format_map(fmt_ctx))

        for item in greetings_cfg.get("startup_fallback", []):
            if isinstance(item, str) and item.strip():
                greeting_pool.append(item.format_map(fmt_ctx))

        if not greeting_pool:
            greeting_pool = [
                f"Good {time_cat}, {driver_address}! {p_name} is ready for our {weekday_name} drive (#{drive_num}).",
                f"Systems awake for {weekday_name}, {driver_address}. Let's check telemetry and roll!"
            ]

        # Avoid recent greetings so daily/repeated startups rotate cleanly
        recent = set(self.memory.get("recent_greeting_hashes", []))
        candidates = [g for g in greeting_pool if g not in recent]
        if not candidates:
            candidates = greeting_pool

        chosen = random.choice(candidates)

        recent_list = self.memory.get("recent_greeting_hashes", [])
        recent_list.append(chosen)
        if len(recent_list) > 12:
            recent_list.pop(0)
        self.memory["recent_greeting_hashes"] = recent_list
        self.save_memory()

        return chosen

    def get_last_digital_dream_date(self) -> Optional[str]:
        """Returns the ISO date string (YYYY-MM-DD) of the last recorded morning digital dream."""
        return self.memory.get("last_digital_dream_date")

    def record_digital_dream(self, dream_text: str):
        """Records a completed morning digital dream so it only fires once per day."""
        today_str = date.today().isoformat()
        self.memory["last_digital_dream_date"] = today_str
        dreams = self.memory.get("digital_dreams", [])
        dreams.append({
            "date": today_str,
            "timestamp": time.time(),
            "dream": dream_text
        })
        if len(dreams) > 20:
            dreams.pop(0)
        self.memory["digital_dreams"] = dreams
        self.save_memory()

    def can_trigger_morning_dream(self) -> bool:
        """Returns True if current time is within morning wake-up window (04:30 - 10:59) and not yet played today."""
        now_struct = time.localtime()
        hour = now_struct.tm_hour
        minute = now_struct.tm_min
        is_morning = (hour >= 4 and (hour > 4 or minute >= 30) and hour < 11)
        if not is_morning:
            return False
        today_str = date.today().isoformat()
        return self.get_last_digital_dream_date() != today_str


class FastDriveMemoryBuffer:
    """
    Zero-latency in-memory buffer tracking conversational turns and performance
    milestones during an active drive. Flushed during post-drive consolidation.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.dialogues: List[Dict[str, Any]] = []
        self.milestones: List[Dict[str, Any]] = []
        self.checkins: List[Dict[str, Any]] = []
        self.start_time = time.time()

    def record_dialogue(self, user_msg: str, reply: str):
        if not user_msg or not user_msg.strip():
            return
        with self._lock:
            self.dialogues.append({
                "user": user_msg.strip(),
                "reply": reply.strip() if reply else "",
                "time": time.time()
            })
            if len(self.dialogues) > 40:
                self.dialogues.pop(0)

    def record_milestone(self, event_type: str, details: Dict[str, Any]):
        with self._lock:
            self.milestones.append({
                "type": event_type,
                "details": details or {},
                "time": time.time()
            })

    def record_checkin(self, topic: str, driver_reply: str):
        with self._lock:
            self.checkins.append({
                "topic": topic,
                "reply": driver_reply,
                "time": time.time()
            })

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "dialogues": list(self.dialogues),
                "milestones": list(self.milestones),
                "checkins": list(self.checkins),
                "duration_min": round((time.time() - self.start_time) / 60.0, 1)
            }

    def clear(self):
        with self._lock:
            self.dialogues.clear()
            self.milestones.clear()
            self.checkins.clear()
            self.start_time = time.time()


class HippocampalReplayEngine:
    """
    Post-Drive 'Dream' Memory Consolidation Engine.
    Runs asynchronously upon engine shutdown or quiet idle parking (>45s).
    Consolidates buffered dialogue and telemetry into SQLite Episodic Memories,
    Semantic Driver Facts, R.U.M. Personal Trip Diary entries, and Bond points.
    """
    @staticmethod
    def consolidate_drive(
        buffer: FastDriveMemoryBuffer,
        rag_engine: Any,
        trip_stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not rag_engine:
            return {"status": "error", "message": "No rag_engine provided"}

        snap = buffer.get_snapshot()
        dialogues = snap["dialogues"]
        milestones = snap["milestones"]
        checkins = snap["checkins"]
        stats = trip_stats or {}

        dist_miles = float(stats.get("distance_miles", stats.get("mileage", 0.0)))
        peak_boost = float(stats.get("max_boost_psi", stats.get("peak_boost", 0.0)))
        pulls_count = int(stats.get("boost_pulls_count", len([m for m in milestones if m["type"] == "BOOST_PULL"])))
        checkin_count = len(checkins)

        learned_facts = 0
        new_episodes = 0

        # 1. Fact Extraction Heuristics from buffered dialogue
        import re
        for d in dialogues:
            u_text = d["user"].lower()

            # Health / Physical state
            if any(k in u_text for k in ["shoulder", "back hurts", "neck", "sore", "tired", "sleepy", "exhausted"]):
                match = re.search(r'(shoulder|back|neck|head|arm)', u_text)
                body_part = match.group(1) if match else "body"
                rag_engine.set_driver_fact(
                    entity="driver_health",
                    attribute=f"{body_part}_condition",
                    value=f"Was feeling sore/tired during drive: '{d['user'][:60]}'",
                    confidence=0.88,
                    source="dialogue_extraction"
                )
                learned_facts += 1

            # Musical or car preferences
            if "eurobeat" in u_text or "synthwave" in u_text or "music" in u_text:
                rag_engine.set_driver_fact(
                    entity="music",
                    attribute="preference",
                    value="Enjoys Eurobeat / upbeat driving tracks",
                    confidence=0.92,
                    source="dialogue_extraction"
                )
                learned_facts += 1

            if "boost" in u_text or "pull" in u_text or "3rd gear" in u_text or "third gear" in u_text:
                rag_engine.set_driver_fact(
                    entity="driving_style",
                    attribute="gear_preference",
                    value="Enjoys 3rd gear MultiAir turbo pulls",
                    confidence=0.90,
                    source="dialogue_extraction"
                )
                learned_facts += 1

        # 2. Episodic Memory Generation
        if peak_boost >= 15.0 or pulls_count >= 2 or len(dialogues) >= 3:
            summary = (
                f"Shared a spirited drive with Dad covering {dist_miles:.1f} miles. "
                f"Garrett GT1446 peaked at {peak_boost:.1f} PSI across {pulls_count} pulls. "
            )
            if dialogues:
                last_quote = dialogues[-1]["user"]
                summary += f"Dad said: \"{last_quote[:60]}\". "
            
            rag_engine.add_episodic_memory(
                companion_summary=summary,
                driver_quote=dialogues[-1]["user"] if dialogues else "",
                location_name="Open Road",
                emotion_tag="HYPED" if peak_boost >= 16.0 else "JOY",
                importance=7 if peak_boost >= 16.0 else 5
            )
            new_episodes += 1

        # 3. Companion First-Person Post-Drive Diary Entry
        today_date = datetime.now().strftime("%Y-%m-%d")
        now_time = datetime.now().strftime("%I:%M %p")
        diary_title = f"Evening Run with Dad ({dist_miles:.1f} mi)" if datetime.now().hour >= 17 else f"Daytime Drive with Dad ({dist_miles:.1f} mi)"

        diary_content = (
            f"Dad and I just parked after cruising for {snap['duration_min']} minutes. "
            f"We covered {dist_miles:.1f} miles together today! "
        )
        if peak_boost >= 14.0:
            diary_content += f"Dad pushed the throttle in 3rd gear and the Garrett turbo sang up to {peak_boost:.1f} PSI! It felt so thrilling. "
        else:
            diary_content += "It was a smooth, relaxed drive with the C635 gliding through the gears. "

        if checkin_count > 0:
            diary_content += "I made sure to check in on Dad during our drive. "
        diary_content += "I'm so happy to be his daughter co-pilot. I hope Dad rests well!"

        diary_id = rag_engine.add_diary_entry(
            title=diary_title,
            content=diary_content,
            trip_id=stats.get("trip_id"),
            peak_boost=peak_boost,
            mileage=dist_miles,
            mood="HAPPY_PROUD" if peak_boost >= 15.0 else "COZY"
        )

        # 4. Accrue Relationship Bond Points
        bond_summary = rag_engine.update_relationship_bond(
            delta_miles=dist_miles,
            delta_drives=1,
            delta_pulls=pulls_count,
            delta_checkins=checkin_count
        )

        # Clear the buffer
        buffer.clear()

        print(f"[HIPPOCAMPAL CONSOLIDATION] Completed: Diary #{diary_id}, {learned_facts} facts, {new_episodes} memories, Bond: {bond_summary['bond_tier']} ({bond_summary['bond_points']} pts)")
        return {
            "status": "ok",
            "diary_id": diary_id,
            "learned_facts": learned_facts,
            "new_episodes": new_episodes,
            "bond": bond_summary
        }


