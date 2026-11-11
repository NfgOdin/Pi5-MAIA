"""



audio_player.py - High-Performance In-Dash Audio & Multi-Engine TTS for CarPi5 on Raspberry Pi 5



Outputs directly to HDMI 0 ALSA hardware sink (aplay -D plughw:0,0) or PipeWire.



Supported Voice Engines (selectable in Settings):



1. KOKORO (Local Neural 82M via kokoro-onnx) - Warm, expressive human cadence on Pi 5 CPU



2. PIPER  (Local Fast ONNX via piper-tts)    - Ultra-low latency offline neural voice



3. ELEVENLABS (Cloud Turbo v2.5 Stream API)  - Studio-grade child/young girl voice ('Gigi' / 'Bella') with automatic local fallback when offline



4. OPENAI_TTS (Cloud OpenAI Audio API)       - OpenAI 'nova'/'shimmer' voice with automatic local fallback when offline



"""







import os
import re
import sys
import json
import sqlite3
import time



import wave



import queue



import tempfile



import threading

import subprocess

import urllib.request

import hashlib

import shutil

import random

from pathlib import Path

from typing import Optional, Dict, Any, Union

# POSIX Shared Memory RAM tmpfs path for zero-wear NVMe/SD flash protection
RAM_AUDIO_DIR = Path("/dev/shm/carpi5_audio") if sys.platform.startswith("linux") and os.path.exists("/dev/shm") else Path(tempfile.gettempdir())
try:
    RAM_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    RAM_AUDIO_DIR = Path(tempfile.gettempdir())

# Audio Priority Levels for Cockpit Ducking Matrix
PRIORITY_CRITICAL = 0   # Faults, coolant >215F, MultiAir protection, safety alerts (always speaks, ducks music)
PRIORITY_COMMAND = 1    # User queries, wake-word, boost pull milestones, shift ratings (speaks, ducks music)
PRIORITY_BANTER = 2     # Shower thoughts, morning digital dreams, idle chatter (silenced if music playing)





class TTSCacheManager:
    """
    Phase 14 Crash-Safe SQLite WAL Voice Response Registry & Multi-Tier Hot-Pool.
    - Atomic SQLite database (tts_cache.db) with WAL mode (zero corruption on power loss).
    - Multi-tier RAM hot-pool (/dev/shm) pinning top 50 phrases for 0ms I/O latency.
    - Multi-take prosody variations (up to 3 takes for high-frequency phrases).
    - Punctuation-sensitive keying preserving expressive intonation.
    - Permanent frequency-protected retention policy (hit_count >= 2 or is_locked never pruned).
    """
    def __init__(self, cache_dir: Optional[str] = None, limit_mb: int = 4096):
        if cache_dir is None:
            base = Path(__file__).parent.parent.parent
            self.cache_dir = base / "storage" / "tts_cache"
        else:
            self.cache_dir = Path(cache_dir)
            
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "tts_cache.db"
        self.index_file = self.cache_dir / "cache_index.json"
        self.limit_mb = max(256, int(limit_mb))
        self.lock = threading.Lock()
        
        # RAM hotpool directory for 0ms access
        self.hotpool_dir = RAM_AUDIO_DIR / "hotpool"
        try:
            self.hotpool_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.hotpool_dir = Path(tempfile.gettempdir()) / "hotpool"
            self.hotpool_dir.mkdir(parents=True, exist_ok=True)

        self._init_db()
        self._migrate_json_if_needed()
        self.sync_hotpool()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tts_cache (
                    hash_key TEXT PRIMARY KEY,
                    norm_text TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    voice TEXT NOT NULL,
                    pitch REAL NOT NULL,
                    take_index INTEGER DEFAULT 0,
                    file_name TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    hit_count INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    is_locked INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tts_lookup ON tts_cache (norm_text, voice, pitch)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tts_access ON tts_cache (is_locked, hit_count, last_accessed)")

    def _migrate_json_if_needed(self):
        """Migrate legacy cache_index.json into SQLite WAL database."""
        if not self.index_file.exists():
            return
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                legacy = json.load(f)
            if legacy and isinstance(legacy, dict):
                with self._get_conn() as conn:
                    for key, meta in legacy.items():
                        fname = meta.get("file", f"{key}.wav")
                        fpath = self.cache_dir / fname
                        if fpath.exists():
                            norm = self._make_norm(meta.get("text", ""))
                            conn.execute("""
                                INSERT OR IGNORE INTO tts_cache 
                                (hash_key, norm_text, raw_text, voice, pitch, take_index, file_name, size_bytes, hit_count, created_at, last_accessed, is_locked)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                key,
                                norm,
                                meta.get("text", ""),
                                meta.get("voice", "kokoro"),
                                float(meta.get("pitch", 1.0)),
                                0,
                                fname,
                                int(meta.get("size_bytes", fpath.stat().st_size if fpath.exists() else 0)),
                                int(meta.get("hit_count", 1)),
                                float(meta.get("created_at", time.time())),
                                float(meta.get("last_accessed", time.time())),
                                1 if int(meta.get("hit_count", 1)) >= 2 else 0
                            ))
                bak_file = self.cache_dir / "cache_index.json.bak"
                self.index_file.replace(bak_file)
                print(f"[TTS-CACHE] Migrated {len(legacy)} entries from JSON to SQLite WAL.")
        except Exception as e:
            print(f"[TTS-CACHE] Migration notice: {e}")

    def _make_norm(self, text: str) -> str:
        # Preserve emotional punctuation tokens (!, ?, ..., commas)
        clean = "".join(c for c in text.lower().strip() if c.isalnum() or c.isspace() or c in ".!?,:;")
        return " ".join(clean.split())

    def _make_key(self, norm_text: str, voice: str, pitch: float, take_index: int = 0) -> str:
        raw = f"{norm_text}|{voice.lower()}|{pitch:.2f}|take{take_index}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def get(self, text: str, voice: str, pitch: float) -> Optional[str]:
        """Returns path to cached audio file (RAM hotpool or disk) with multi-take alternating selection."""
        norm = self._make_norm(text)
        with self.lock:
            with self._get_conn() as conn:
                rows = conn.execute("""
                    SELECT hash_key, file_name, hit_count, is_locked 
                    FROM tts_cache 
                    WHERE norm_text = ? AND voice = ? AND ABS(pitch - ?) < 0.03
                    ORDER BY take_index ASC
                """, (norm, voice.lower(), float(pitch))).fetchall()

                if not rows:
                    return None

                # Multi-take natural variation: randomly select across available takes
                selected_row = random.choice(rows)
                h_key = selected_row["hash_key"]
                fname = selected_row["file_name"]

                # 1. Check RAM Hotpool for 0ms instantaneous memory hit
                hot_path = self.hotpool_dir / fname
                disk_path = self.cache_dir / fname

                target_path = None
                if hot_path.exists():
                    target_path = str(hot_path)
                elif disk_path.exists():
                    target_path = str(disk_path)
                else:
                    conn.execute("DELETE FROM tts_cache WHERE hash_key = ?", (h_key,))
                    return None

                # Update hit metrics atomically
                conn.execute("""
                    UPDATE tts_cache 
                    SET hit_count = hit_count + 1, last_accessed = ?, is_locked = CASE WHEN hit_count >= 1 THEN 1 ELSE is_locked END
                    WHERE hash_key = ?
                """, (time.time(), h_key))

                return target_path

    def put(self, text: str, voice: str, pitch: float, src_wav_path: str, is_locked: bool = False, take_index: int = 0) -> Optional[str]:
        """Stores a newly synthesized WAV file in the cache with crash-safe SQLite registration."""
        if not os.path.exists(src_wav_path) or os.path.getsize(src_wav_path) < 500:
            return None

        norm = self._make_norm(text)
        key = self._make_key(norm, voice, pitch, take_index=take_index)
        dest_filename = f"{key}.wav"
        dest_path = self.cache_dir / dest_filename

        try:
            shutil.copy2(src_wav_path, str(dest_path))
            size_bytes = dest_path.stat().st_size
            now = time.time()

            with self.lock:
                with self._get_conn() as conn:
                    conn.execute("""
                        INSERT INTO tts_cache 
                        (hash_key, norm_text, raw_text, voice, pitch, take_index, file_name, size_bytes, hit_count, created_at, last_accessed, is_locked)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                        ON CONFLICT(hash_key) DO UPDATE SET
                            last_accessed = excluded.last_accessed,
                            hit_count = hit_count + 1,
                            size_bytes = excluded.size_bytes,
                            is_locked = MAX(is_locked, excluded.is_locked)
                    """, (
                        key, norm, text[:150], voice.lower(), round(float(pitch), 2),
                        take_index, dest_filename, size_bytes, now, now, 1 if is_locked else 0
                    ))

            self.auto_prune_if_needed()
            return str(dest_path)
        except Exception as e:
            print(f"[TTS-CACHE] Error storing cache for '{text[:30]}': {e}")
            return None

    def sync_hotpool(self):
        """Pins the top 50 most frequently used audio clips directly in RAM (/dev/shm)."""
        try:
            with self._get_conn() as conn:
                top_rows = conn.execute("""
                    SELECT file_name FROM tts_cache 
                    ORDER BY hit_count DESC, last_accessed DESC 
                    LIMIT 50
                """).fetchall()

            for row in top_rows:
                fname = row["file_name"]
                src = self.cache_dir / fname
                dst = self.hotpool_dir / fname
                if src.exists() and not dst.exists():
                    shutil.copy2(str(src), str(dst))
        except Exception as e:
            print(f"[TTS-CACHE] Hotpool sync notice: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Returns live storage statistics, phrase counts, and hit metrics from SQLite."""
        try:
            with self._get_conn() as conn:
                row = conn.execute("""
                    SELECT 
                        COUNT(*) as total_files,
                        COALESCE(SUM(size_bytes), 0) as total_bytes,
                        COALESCE(SUM(hit_count), 0) as total_hits,
                        COALESCE(SUM(CASE WHEN is_locked = 1 THEN 1 ELSE 0 END), 0) as locked_count
                    FROM tts_cache
                """).fetchone()

                total_files = row["total_files"] if row else 0
                total_bytes = row["total_bytes"] if row else 0
                total_hits = row["total_hits"] if row else 0
                locked_count = row["locked_count"] if row else 0
                total_mb = total_bytes / (1024 * 1024)
                pct = (total_mb / self.limit_mb * 100.0) if self.limit_mb > 0 else 0.0

                return {
                    "total_phrases": total_files,
                    "total_bytes": total_bytes,
                    "total_mb": round(total_mb, 2),
                    "limit_mb": self.limit_mb,
                    "usage_pct": round(pct, 1),
                    "total_hits": total_hits,
                    "locked_count": locked_count,
                    "cache_dir": str(self.cache_dir),
                    "db_path": str(self.db_path)
                }
        except Exception:
            return {
                "total_phrases": 0, "total_bytes": 0, "total_mb": 0.0,
                "limit_mb": self.limit_mb, "usage_pct": 0.0, "total_hits": 0,
                "locked_count": 0, "cache_dir": str(self.cache_dir)
            }

    def auto_prune_if_needed(self):
        """
        Permanent Frequency-Protected Retention Policy:
        - Phrases with hit_count >= 2 or is_locked == 1 are NEVER deleted!
        - Only single-hit phrases older than 60 days are eligible for eviction.
        """
        try:
            with self.lock:
                stats = self.get_stats()
                if stats["total_mb"] <= self.limit_mb:
                    return

                target_bytes = int(self.limit_mb * 1024 * 1024 * 0.85)
                bytes_to_free = stats["total_bytes"] - target_bytes
                if bytes_to_free <= 0:
                    return

                sixty_days_ago = time.time() - (60 * 86400)
                with self._get_conn() as conn:
                    candidates = conn.execute("""
                        SELECT hash_key, file_name, size_bytes 
                        FROM tts_cache 
                        WHERE is_locked = 0 AND hit_count < 2 AND last_accessed < ?
                        ORDER BY last_accessed ASC
                    """, (sixty_days_ago,)).fetchall()

                    freed = 0
                    deleted_keys = []
                    for c in candidates:
                        fpath = self.cache_dir / c["file_name"]
                        if fpath.exists():
                            try:
                                fpath.unlink()
                            except Exception:
                                pass
                        freed += c["size_bytes"]
                        deleted_keys.append(c["hash_key"])
                        if freed >= bytes_to_free:
                            break

                    if deleted_keys:
                        conn.executemany("DELETE FROM tts_cache WHERE hash_key = ?", [(k,) for k in deleted_keys])
                        print(f"[TTS-CACHE] Auto-pruned {len(deleted_keys)} legacy single-hit phrases ({round(freed / (1024*1024), 2)} MB freed).")
        except Exception as e:
            print(f"[TTS-CACHE] Auto-prune error: {e}")

    def calculate_downsize_impact(self, new_limit_mb: int) -> Dict[str, Any]:
        """Calculates eligible single-hit phrases that would be deleted if downsized."""
        stats = self.get_stats()
        if stats["total_mb"] <= new_limit_mb:
            return {"needs_prune": False, "bytes_to_delete": 0, "mb_to_delete": 0.0, "phrases_to_delete": 0}

        target_bytes = int(new_limit_mb * 1024 * 1024 * 0.90)
        bytes_needed = max(0, stats["total_bytes"] - target_bytes)

        with self._get_conn() as conn:
            candidates = conn.execute("""
                SELECT hash_key, size_bytes 
                FROM tts_cache 
                WHERE is_locked = 0 AND hit_count < 2
                ORDER BY last_accessed ASC
            """).fetchall()

            freed = 0
            count = 0
            for c in candidates:
                freed += c["size_bytes"]
                count += 1
                if freed >= bytes_needed:
                    break

            return {
                "needs_prune": True,
                "bytes_to_delete": freed,
                "mb_to_delete": round(freed / (1024 * 1024), 2),
                "phrases_to_delete": count
            }

    def set_limit_mb(self, new_limit_mb: int) -> Dict[str, Any]:
        self.limit_mb = max(256, int(new_limit_mb))
        self.auto_prune_if_needed()
        return self.get_stats()

    def clear(self) -> Dict[str, Any]:
        with self.lock:
            for f in self.cache_dir.glob("*.wav"):
                try:
                    f.unlink()
                except Exception:
                    pass
            for f in self.hotpool_dir.glob("*.wav"):
                try:
                    f.unlink()
                except Exception:
                    pass
            with self._get_conn() as conn:
                conn.execute("DELETE FROM tts_cache")
            print("[TTS-CACHE] Cache cleared completely.")
            return self.get_stats()





class AudioPlayer:



    _instance = None



    _lock = threading.Lock()







    def __new__(cls, *args, **kwargs):



        with cls._lock:



            if cls._instance is None:



                cls._instance = super().__new__(cls)



                cls._instance._initialized = False



            return cls._instance







    def __init__(self):



        if self._initialized:



            return



        self._initialized = True







        self.speech_queue = queue.Queue()
        self._duck_callback = None
        self._music_playing_checker = None
        self._is_currently_ducking = False
        self._duck_lock = threading.Lock()



        self.is_playing = False



        self.is_speaking = False







        # Voice Engine Configuration (persisted in app_settings / ai_settings)



        self.tts_engine = "KOKORO"          # "KOKORO" | "PIPER" | "ELEVENLABS" | "OPENAI_TTS"



        self.kokoro_voice = "af_nicole"     # "af_nicole" (Whisper / ASMR) | "af_bella" | "af_heart" | "af_sky"



        self.pitch_factor = 1.18            # Youthful anime pitch factor (1.18x = light, delicate anime girl timbre)



        self.elevenlabs_api_key = ""



        self.elevenlabs_voice_id = "cgSgspJ2msm6clMCkdW9"  # 'Jessica' (Playful, Bright, Warm - Free & Paid supported)



        self.openai_api_key = ""



        self.openai_voice = "nova"







        self._piper_voice = None



        self._piper_loaded = False



        self._piper_lock = threading.Lock()







        self._kokoro_instance = None



        self._kokoro_loaded = False



        self._kokoro_lock = threading.Lock()







        self._last_spoken_text = ""



        self._last_spoken_time = 0.0







        base_models = Path(__file__).parent.parent.parent / "models"

        home_models = Path.home() / "CarPi5" / "models"



        self.kokoro_model_candidates = [

            str(base_models / "kokoro-v1.0.int8.onnx"),

            str(home_models / "kokoro-v1.0.int8.onnx"),

        ]



        self.kokoro_voices_candidates = [

            str(base_models / "voices-v1.0.bin"),

            str(home_models / "voices-v1.0.bin"),

        ]



        # Candidate paths for Piper neural model (en_US-hfc_female-medium as primary default)

        self.model_candidates = [

            str(base_models / "en_US-hfc_female-medium.onnx"),

            str(home_models / "en_US-hfc_female-medium.onnx"),

            str(base_models / "en_US-amy-medium.onnx"),

            str(home_models / "en_US-amy-medium.onnx"),

            str(base_models / "en_US-lessac-low.onnx"),

            str(home_models / "en_US-lessac-low.onnx"),

        ]







        self.alsa_device = "plughw:0,0" if sys.platform.startswith("linux") else None



        # Voice Response Cache & LRU Manager (Default 1GB reserve)

        self.cache_mgr = TTSCacheManager(limit_mb=1024)



        # Dual-Stage Synthesis & Playback Queues for Non-Blocking Clause Streaming

        self.synthesis_queue = queue.Queue(maxsize=64)

        self.playback_queue = queue.Queue(maxsize=32)

        self.speech_queue = self.synthesis_queue  # Backwards compatibility



        # Start dual worker threads

        self.synthesis_thread = threading.Thread(target=self._synthesis_loop, daemon=True, name="TTSSynthesisThread")

        self.synthesis_thread.start()



        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True, name="TTSPlaybackThread")

        self.playback_thread.start()







        # Warm up both Piper and Kokoro TTS in background threads



        threading.Thread(target=self._init_piper, daemon=True).start()



        threading.Thread(target=self._init_kokoro, daemon=True).start()







    def configure_tts(self, settings: Dict[str, Any]):



        """Update active TTS engine, voice preset, pitch, and cloud keys from settings."""



        if not settings:



            return



        if "tts_engine" in settings and settings["tts_engine"]:



            self.tts_engine = str(settings["tts_engine"]).upper()



        if "kokoro_voice" in settings and settings["kokoro_voice"]:



            self.kokoro_voice = str(settings["kokoro_voice"])



        pitch_val = settings.get("tts_pitch") if settings.get("tts_pitch") is not None else settings.get("pitch_factor")



        if pitch_val is not None:



            try:



                self.pitch_factor = max(0.50, min(2.00, float(pitch_val)))



            except Exception:



                pass



        if "elevenlabs_api_key" in settings:



            self.elevenlabs_api_key = str(settings["elevenlabs_api_key"] or "").strip()



        if "elevenlabs_voice_id" in settings and settings["elevenlabs_voice_id"]:



            vid = str(settings["elevenlabs_voice_id"]).strip()



            # If still set to old Gigi voice ID which is restricted on free tier, auto-migrate to Jessica



            if vid == "jBpfuIE2acCO8z3wKNLl":



                vid = "cgSgspJ2msm6clMCkdW9"



            self.elevenlabs_voice_id = vid



        if "api_key" in settings and settings["api_key"]:

            self.openai_api_key = str(settings["api_key"]).strip()



        if "tts_cache_limit_mb" in settings and settings["tts_cache_limit_mb"]:

            try:

                self.cache_mgr.set_limit_mb(int(settings["tts_cache_limit_mb"]))

            except Exception:

                pass



    def get_tts_status(self) -> Dict[str, Any]:

        return {

            "tts_engine": self.tts_engine,

            "kokoro_voice": self.kokoro_voice,

            "tts_pitch": self.pitch_factor,

            "kokoro_ready": self._kokoro_loaded,

            "piper_ready": self._piper_loaded,

            "elevenlabs_configured": bool(self.elevenlabs_api_key),

            "elevenlabs_voice_id": self.elevenlabs_voice_id,

            "cache": self.cache_mgr.get_stats(),

        }







    def _init_kokoro(self):

        """Loads Kokoro-82M int8 ONNX model and voices into RAM if available."""

        with self._kokoro_lock:

            if self._kokoro_instance is not None:

                return

            model_p = None

            voices_p = None

            try:

                import onnxruntime as ort

                from kokoro_onnx import Kokoro

                model_p = next((p for p in self.kokoro_model_candidates if os.path.exists(p) and os.path.getsize(p) > 1000000), None)

                voices_p = next((p for p in self.kokoro_voices_candidates if os.path.exists(p) and os.path.getsize(p) > 100000), None)

                if model_p and voices_p:

                    print(f"[AUDIO] Loading Kokoro-82M neural voice model: {model_p}...")

                    opts = ort.SessionOptions()

                    opts.intra_op_num_threads = 4

                    opts.inter_op_num_threads = 2

                    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

                    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

                    session = ort.InferenceSession(model_p, sess_options=opts, providers=['CPUExecutionProvider'])

                    self._kokoro_instance = Kokoro.from_session(session, voices_p)

                    self._kokoro_loaded = True

                    print("[AUDIO] Kokoro-82M multi-threaded neural voice ready for in-dash speech!")

            except Exception as e:

                print(f"[AUDIO] Kokoro-82M optimized init note: {e}")

                try:

                    from kokoro_onnx import Kokoro

                    if model_p and voices_p:

                        self._kokoro_instance = Kokoro(model_p, voices_p)

                        self._kokoro_loaded = True

                        print("[AUDIO] Kokoro-82M fallback loaded.")

                except Exception:

                    pass







    def _init_piper(self):



        """Loads the Piper neural voice into RAM."""



        with self._piper_lock:



            if self._piper_voice is not None:



                return



            try:



                from piper.voice import PiperVoice



                for path in self.model_candidates:



                    if os.path.exists(path):



                        config_path = path + ".json"



                        print(f"[AUDIO] Loading Piper TTS model: {path}...")



                        self._piper_voice = PiperVoice.load(path, config_path=config_path if os.path.exists(config_path) else None)



                        self._piper_loaded = True



                        print("[AUDIO] Piper TTS voice ready for in-dash speech!")



                        return



                print("[AUDIO] Note: No Piper ONNX voice file found at candidates.")



            except Exception as e:



                print(f"[AUDIO] Piper TTS init note: {e}")







    def _split_clauses(self, text: str) -> list:
        """Splits multi-sentence / multi-clause responses into fine-grained memoizable phrases."""
        import re
        text = text.strip()
        if not text:
            return []
        # Split on sentence terminals first (. ! ? \n)
        sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
        clauses = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            # If sentence is long (> 50 chars) and contains commas or semicolons, sub-split
            if len(s) > 50 and ("," in s or ";" in s):
                sub_parts = re.split(r'(?<=[,;])\s+', s)
                for part in sub_parts:
                    p = part.strip()
                    if not p:
                        continue
                    if len(p.split()) < 3 and clauses:
                        clauses[-1] = f"{clauses[-1]} {p}".strip()
                    else:
                        clauses.append(p)
            else:
                if len(s.split()) < 3 and clauses:
                    clauses[-1] = f"{clauses[-1]} {s}".strip()
                else:
                    clauses.append(s)
        return clauses if clauses else [text]



    def is_music_playing(self) -> bool:
        if self._music_playing_checker:
            try:
                return bool(self._music_playing_checker())
            except Exception:
                pass
        return False

    def set_music_playing_checker(self, fn):
        self._music_playing_checker = fn

    def set_duck_callback(self, fn):
        self._duck_callback = fn

    def _trigger_duck_state(self, is_ducking: bool):
        with self._duck_lock:
            self._is_currently_ducking = is_ducking
            if self._duck_callback:
                try:
                    self._duck_callback(is_ducking)
                except Exception as e:
                    print(f"[AUDIO DUCK] Duck callback exception: {e}")
            if sys.platform.startswith("linux"):
                try:
                    self._apply_pipewire_ducking(is_ducking)
                except Exception:
                    pass

    def _apply_pipewire_ducking(self, is_ducking: bool):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        try:
            res = subprocess.run(["wpctl", "status"], capture_output=True, text=True, env=env, timeout=1.5)
            if res.returncode == 0:
                in_streams = False
                for line in res.stdout.splitlines():
                    if "Streams:" in line:
                        in_streams = True
                        continue
                    if in_streams and line.strip() and not line.startswith(" "):
                        break
                    if in_streams:
                        m = re.search(r"(\d+)\.\s+(.+)", line.strip())
                        if m:
                            stream_id = m.group(1)
                            name = m.group(2).lower()
                            if "record" not in name and "play" not in name and "vosk" not in name:
                                target_vol = "0.18" if is_ducking else "1.00"
                                subprocess.run(["wpctl", "set-volume", stream_id, target_vol], env=env, timeout=1.0)
        except Exception:
            pass

    def speak(self, text: str, priority: Any = 1):
        """Queue text to be spoken aloud through in-dash speakers with automatic clause streaming & de-duplication."""
        if not text or not text.strip():
            return
        clean_text = text.strip()
        clean_text = clean_text.replace("*", "").replace("`", "").replace('"', '')
        # Automotive Metric & Acronym Phonetic Normalization
        clean_text = re.sub(r'\bM\.?P\.?H\.?\b', 'miles per hour', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'(\d+)\s*mph\b', r'\1 miles per hour', clean_text, flags=re.IGNORECASE)

        # Audio Ducking Matrix Priority Mapping:
        # Priority 0: Critical alerts (coolant > 215F, MultiAir protection, safety alerts) -> always speaks, ducks music
        # Priority 1: User command response, direct queries, peak boost pulls, 100-pt shift rating -> speaks, ducks music
        # Priority 2: Routine banter, morning digital dreams, highway shower thoughts -> silenced when in-dash music is playing!
        if isinstance(priority, bool):
            p_level = PRIORITY_CRITICAL if priority else PRIORITY_COMMAND
        elif isinstance(priority, int):
            p_level = priority
        else:
            p_level = PRIORITY_COMMAND

        if p_level == PRIORITY_BANTER and self.is_music_playing():
            print(f"[AUDIO DUCKING MATRIX] Silencing routine banter (Priority 2): '{clean_text[:40]}...' because in-dash music is playing.")
            return



        now = time.time()

        if clean_text == self._last_spoken_text and ((now - self._last_spoken_time) < 8.0 or self.is_speaking):

            print(f"[AUDIO] De-duplicating repeat speech request: {clean_text[:40]}...")

            return

        self._last_spoken_text = clean_text

        self._last_spoken_time = now



        clauses = self._split_clauses(clean_text)

        for clause in clauses:

            self.synthesis_queue.put(clause)



    def play_wav_file(self, wav_path: str):

        """Directly queue a WAV sound file for instant hardware playback."""

        if os.path.exists(wav_path):

            self.playback_queue.put({"file": wav_path, "lead_in": 0.0, "cleanup": False})



    def _synthesis_loop(self):

        """Worker thread continuously synthesizing queued text clauses into audio WAV clips."""

        while True:

            try:

                item = self.synthesis_queue.get()

                if item is None:

                    break

                if isinstance(item, dict) and "file" in item:

                    self.playback_queue.put(item)

                elif isinstance(item, str):

                    self._synthesize_clause_pipelined(item)

                self.synthesis_queue.task_done()

            except Exception as e:

                print(f"[AUDIO] Synthesis pipeline error: {e}")

                time.sleep(0.05)



    def _playback_loop(self):

        """Dedicated ALSA / PipeWire hardware audio playback thread."""

        while True:

            try:

                item = self.playback_queue.get()

                if item is None:

                    break

                fpath = item.get("file") if isinstance(item, dict) else str(item)

                lead_in = item.get("lead_in", 0.0) if isinstance(item, dict) else 0.0

                cleanup = item.get("cleanup", False) if isinstance(item, dict) else False



                if fpath and os.path.exists(fpath):
                    if not self._is_currently_ducking:
                        self._trigger_duck_state(True)
                    self._play_file_direct(fpath, lead_in_silence_sec=lead_in)



                if cleanup and fpath and os.path.exists(fpath):

                    try:

                        os.remove(fpath)

                    except Exception:

                        pass

                self.playback_queue.task_done()

            except Exception as e:

                print(f"[AUDIO] Playback error: {e}")

                time.sleep(0.05)

            finally:

                if self.playback_queue.empty():
                    self.is_speaking = False
                    if self._is_currently_ducking:
                        self._trigger_duck_state(False)







    def _synthesize_cloud_elevenlabs(self, text: str, out_wav_path: str) -> bool:



        """Synthesizes speech via ElevenLabs Turbo v2.5 API and converts to WAV."""



        if not self.elevenlabs_api_key:



            return False



        mp3_path = out_wav_path + ".el.mp3"



        try:



            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.elevenlabs_voice_id}"



            payload = json.dumps({



                "text": text,



                "model_id": "eleven_turbo_v2_5",



                "voice_settings": {"stability": 0.48, "similarity_boost": 0.80, "style": 0.35, "use_speaker_boost": True}



            }).encode("utf-8")



            req = urllib.request.Request(



                url,



                data=payload,



                headers={



                    "xi-api-key": self.elevenlabs_api_key,



                    "Content-Type": "application/json",



                    "Accept": "audio/mpeg"



                },



                method="POST"



            )



            with urllib.request.urlopen(req, timeout=6.0) as resp:



                audio_bytes = resp.read()



            if len(audio_bytes) < 500:



                return False



            with open(mp3_path, "wb") as f:



                f.write(audio_bytes)



            subprocess.run(["ffmpeg", "-y", "-i", mp3_path, "-ar", "24000", "-ac", "1", out_wav_path],



                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)



            return os.path.exists(out_wav_path) and os.path.getsize(out_wav_path) > 1000



        except urllib.error.HTTPError as e:



            err_body = e.read().decode('utf-8', errors='replace')



            print(f"[AUDIO] ElevenLabs cloud TTS HTTP {e.code}: {err_body}")



            return False



        except Exception as e:



            print(f"[AUDIO] ElevenLabs cloud TTS error (falling back to local): {e}")



            return False



        finally:



            if os.path.exists(mp3_path):



                try: os.remove(mp3_path)



                except Exception: pass







    def _synthesize_cloud_openai(self, text: str, out_wav_path: str) -> bool:



        """Synthesizes speech via OpenAI Audio API (tts-1) and converts to WAV."""



        if not self.openai_api_key:



            return False



        mp3_path = out_wav_path + ".oa.mp3"



        try:



            url = "https://api.openai.com/v1/audio/speech"



            payload = json.dumps({



                "model": "tts-1",



                "input": text,



                "voice": self.openai_voice or "nova",



                "response_format": "mp3"



            }).encode("utf-8")



            req = urllib.request.Request(



                url,



                data=payload,



                headers={



                    "Authorization": f"Bearer {self.openai_api_key}",



                    "Content-Type": "application/json"



                },



                method="POST"



            )



            with urllib.request.urlopen(req, timeout=6.0) as resp:



                audio_bytes = resp.read()



            if len(audio_bytes) < 500:



                return False



            with open(mp3_path, "wb") as f:



                f.write(audio_bytes)



            subprocess.run(["ffmpeg", "-y", "-i", mp3_path, "-ar", "24000", "-ac", "1", out_wav_path],



                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)



            return os.path.exists(out_wav_path) and os.path.getsize(out_wav_path) > 1000



        except Exception as e:



            print(f"[AUDIO] OpenAI cloud TTS note (falling back to local): {e}")



            return False



        finally:



            if os.path.exists(mp3_path):



                try: os.remove(mp3_path)



                except Exception: pass







    def _synthesize_local_kokoro(self, text: str, out_wav_path: str) -> bool:



        """Synthesizes warm, human-like speech locally on Pi 5 CPU via Kokoro-82M ONNX."""



        if not self._kokoro_instance:



            self._init_kokoro()



        if not self._kokoro_instance:



            return False



        try:



            import soundfile as sf



            voice_name = self.kokoro_voice if self.kokoro_voice in self._kokoro_instance.get_voices() else "af_bella"



            samples, sample_rate = self._kokoro_instance.create(



                text,



                voice=voice_name,



                speed=1.06,



                lang="en-us"



            )



            sf.write(out_wav_path, samples, sample_rate, subtype="PCM_16")



            return os.path.exists(out_wav_path) and os.path.getsize(out_wav_path) > 1000



        except Exception as e:



            print(f"[AUDIO] Kokoro synthesis note (falling back to Piper): {e}")



            return False







    def _synthesize_local_piper(self, text: str, out_wav_path: str) -> bool:



        """Synthesizes fast local speech via Piper ONNX."""



        if not self._piper_voice:



            self._init_piper()



        if not self._piper_voice:



            return False



        try:



            with wave.open(out_wav_path, "wb") as wav_file:



                self._piper_voice.synthesize_wav(text, wav_file)



            return os.path.exists(out_wav_path) and os.path.getsize(out_wav_path) > 1000



        except Exception as e:



            print(f"[AUDIO] Piper synthesis error: {e}")



            return False







    def _synthesize_clause_pipelined(self, text: str):

        """Synthesize a single clause using the selected engine, cache it, and push to playback queue."""

        voice_id = self.kokoro_voice if self.tts_engine == "KOKORO" else self.tts_engine

        pitch = self.pitch_factor



        # 1. Fast Cache Lookup (Zero-Latency Replay < 15ms)

        cached_wav = self.cache_mgr.get(text, voice_id, pitch)

        if cached_wav and os.path.exists(cached_wav):

            print(f"[AUDIO] TTS Cache HIT ({self.cache_mgr.get_stats()['total_hits']} hits): '{text[:40]}'")

            self.playback_queue.put({"file": cached_wav, "lead_in": 0.04, "cleanup": False})

            return



        wav_path = None

        try:

            with tempfile.NamedTemporaryFile(suffix=".wav", dir=str(RAM_AUDIO_DIR), delete=False) as tmp:

                wav_path = tmp.name



            synthesized = False

            used_engine = self.tts_engine



            if self.tts_engine == "ELEVENLABS":

                synthesized = self._synthesize_cloud_elevenlabs(text, wav_path)

                if not synthesized:

                    used_engine = "KOKORO"



            elif self.tts_engine == "OPENAI_TTS":

                synthesized = self._synthesize_cloud_openai(text, wav_path)

                if not synthesized:

                    used_engine = "KOKORO"



            if not synthesized and used_engine == "KOKORO":

                synthesized = self._synthesize_local_kokoro(text, wav_path)

                if not synthesized:

                    used_engine = "PIPER"



            if not synthesized:

                synthesized = self._synthesize_local_piper(text, wav_path)

                used_engine = "PIPER"



            if not synthesized:

                if sys.platform.startswith("linux"):

                    try:

                        self.is_speaking = True

                        subprocess.run(["espeak-ng", "-v", "en-us", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15.0)

                    except Exception:

                        pass

                    finally:

                        self.is_speaking = False

                return



            # Apply youthful pitch transform ONLY for local TTS (Kokoro/Piper) and only if pitch factor is notably different from 1.0

            if used_engine not in ("ELEVENLABS", "OPENAI_TTS") and abs(self.pitch_factor - 1.0) > 0.05:

                try:

                    with wave.open(wav_path, "rb") as r:

                        sr = r.getframerate()

                    pf = self.pitch_factor

                    pitched_path = wav_path + ".pitched.wav"

                    cmd = [

                        "ffmpeg", "-y", "-threads", "2", "-i", wav_path,

                        "-af", f"asetrate={int(sr * pf)},atempo={1.0 / pf:.6f},aresample={sr}",

                        pitched_path

                    ]

                    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4.0)

                    if res.returncode == 0 and os.path.exists(pitched_path) and os.path.getsize(pitched_path) > 1000:

                        os.replace(pitched_path, wav_path)

                except Exception as p_err:

                    print(f"[AUDIO] Pitch shift note: {p_err}")



            # Prepend 0.08s silence so HDMI monitor / Bluetooth sink wakes up cleanly

            try:

                with wave.open(wav_path, "rb") as r:

                    params = r.getparams()

                    frames = r.readframes(params.nframes)



                silent_count = int(params.framerate * 0.08)

                silence = b"\x00" * (silent_count * params.nchannels * params.sampwidth)



                with wave.open(wav_path, "wb") as w:

                    w.setparams(params)

                    w.writeframes(silence + frames)

            except Exception as ex:

                print(f"[AUDIO] Prepend silence note: {ex}")



            # Save newly synthesized phrase into speech cache for instant future replay

            cached_file = self.cache_mgr.put(text, voice_id, pitch, wav_path)

            if cached_file and os.path.exists(cached_file):

                self.playback_queue.put({"file": cached_file, "lead_in": 0.04, "cleanup": False})

                if os.path.exists(wav_path):

                    try:

                        os.remove(wav_path)

                    except Exception:

                        pass

            else:

                self.playback_queue.put({"file": wav_path, "lead_in": 0.04, "cleanup": True})



        except Exception as e:

            print(f"[AUDIO] TTS synthesize failed: {e}")

            if wav_path and os.path.exists(wav_path):

                try:

                    os.remove(wav_path)

                except Exception:

                    pass



    def _synthesize_and_play(self, text: str):

        """Backwards compatibility wrapper."""

        self._synthesize_clause_pipelined(text)







    def _play_file_direct(self, file_path: str, lead_in_silence_sec: float = 0.0):



        """Play WAV audio via aplay on HDMI 0 (or fallback to pw-play / aplay default) with exact lip-sync state tracking."""



        if not os.path.exists(file_path):



            return



        # Keep a copy of the latest speech audio for remote web clients (PC / phone)

        try:

            target_web = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ui", "web_preview", "last_speech.wav")

            import shutil

            shutil.copy2(file_path, target_web)

        except Exception:

            pass









        def mark_speaking():



            if lead_in_silence_sec > 0:



                time.sleep(lead_in_silence_sec)



            self.is_speaking = True







        threading.Thread(target=mark_speaking, daemon=True).start()







        try:



            if sys.platform.startswith("linux"):

                played = False

                env = os.environ.copy()

                env["XDG_RUNTIME_DIR"] = "/run/user/1000"

                # 1. Primary: Use PipeWire pw-play targeting CarPi-Master-Sink for AEC loopback reference
                try:
                    # Target CarPi-Master-Sink first so WebRTC AEC receives reference audio
                    res = subprocess.run(["pw-play", "--target", "CarPi-Master-Sink", file_path], capture_output=True, timeout=25, env=env)
                    if res.returncode == 0:
                        played = True
                    else:
                        # Fallback to default sink if custom master sink node is not active
                        res = subprocess.run(["pw-play", file_path], capture_output=True, timeout=25, env=env)
                        if res.returncode == 0:
                            played = True
                except Exception:
                    pass

                # 2. Secondary: Default ALSA player

                if not played:

                    try:

                        res = subprocess.run(["aplay", "-B", "100000", "-q", file_path], capture_output=True, timeout=25, env=env)

                        if res.returncode == 0:

                            played = True

                    except Exception:

                        pass

                # 3. Fallback: Direct ALSA HDMI plughw:0,0

                if not played:

                    try:

                        subprocess.run(["aplay", "-D", "plughw:0,0", "-B", "100000", "-q", file_path], capture_output=True, timeout=25)

                    except Exception:

                        pass

            elif sys.platform == "win32":



                try:



                    import winsound



                    winsound.PlaySound(file_path, winsound.SND_FILENAME)



                except Exception:



                    pass



        finally:

            self.is_speaking = False



    def play_acknowledgment(self, persona: str = "RUM") -> bool:

        """Plays a natural, instant (<15ms) voice acknowledgment when mic opens."""

        base = Path(__file__).parent.parent.parent

        ack_dir = base / "assets" / "sounds" / "acknowledgments" / persona.lower()

        if not ack_dir.exists():

            ack_dir = base / "assets" / "sounds" / "acknowledgments" / "rum"

        if ack_dir.exists():

            wavs = sorted(list(ack_dir.glob("*.wav")))

            if wavs:

                chosen = random.choice(wavs)

                print(f"[AUDIO] Playing instant R.U.M. voice acknowledgment: {chosen.name}")

                threading.Thread(target=self._play_file_direct, args=(str(chosen), 0.0), daemon=True).start()

                return True

        return False



    def get_cache_stats(self) -> Dict[str, Any]:

        """Returns live statistics of the TTS cache."""

        return self.cache_mgr.get_stats()



    def set_cache_limit(self, new_limit_mb: int) -> Dict[str, Any]:

        """Updates the speech cache storage limit."""

        return self.cache_mgr.set_limit_mb(new_limit_mb)



    def calculate_downsize_impact(self, new_limit_mb: int) -> Dict[str, Any]:

        """Calculates pruning impact if downsizing cache limit."""

        return self.cache_mgr.calculate_downsize_impact(new_limit_mb)



    def clear_cache(self) -> Dict[str, Any]:

        """Empties the speech cache."""

        return self.cache_mgr.clear()

    def set_system_volume(self, volume_pct: int) -> bool:
        """Sets master hardware volume (0-100%) via wpctl, pactl, or amixer with strict timeouts."""
        if not sys.platform.startswith("linux"):
            return False
        pct = max(0, min(100, int(volume_pct)))
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        for cmd in (
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{pct / 100.0:.2f}"],
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"],
            ["amixer", "-q", "sset", "Master", f"{pct}%"]
        ):
            try:
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=1.5)
                if res.returncode == 0:
                    return True
            except Exception:
                continue
        return False

    def get_system_volume(self) -> Optional[int]:
        """Reads master hardware volume (0-100%) via wpctl, pactl, or amixer with strict timeouts."""
        if not sys.platform.startswith("linux"):
            return None
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        try:
            res = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], capture_output=True, text=True, env=env, timeout=1.5)
            if res.returncode == 0 and "Volume:" in res.stdout:
                val = float(res.stdout.split("Volume:")[1].strip().split()[0])
                return max(0, min(100, int(round(val * 100.0))))
        except Exception:
            pass
        try:
            res = subprocess.run(["amixer", "sget", "Master"], capture_output=True, text=True, env=env, timeout=1.5)
            if res.returncode == 0:
                m = re.search(r"\[(\d+)%\]", res.stdout)
                if m:
                    return max(0, min(100, int(m.group(1))))
        except Exception:
            pass
        return None




