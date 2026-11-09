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

    High-Performance Voice Response Memoization & LRU Cache Manager for CarPi5.

    Caches synthesized speech WAV clips to eliminate synthesis lag (<15ms replay).

    Supports user-configurable size limit (128MB - 8GB) with automatic LRU pruning.

    """

    def __init__(self, cache_dir: Optional[str] = None, limit_mb: int = 1024):

        if cache_dir is None:

            base = Path(__file__).parent.parent.parent

            self.cache_dir = base / "storage" / "tts_cache"

        else:

            self.cache_dir = Path(cache_dir)

            

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.index_file = self.cache_dir / "cache_index.json"

        self.limit_mb = max(128, int(limit_mb))

        self.lock = threading.Lock()

        self.index: Dict[str, Dict[str, Any]] = self._load_index()



    def _load_index(self) -> Dict[str, Dict[str, Any]]:

        if self.index_file.exists():

            try:

                with open(self.index_file, "r", encoding="utf-8") as f:

                    return json.load(f)

            except Exception:

                pass

        return {}



    def _save_index(self):

        try:

            with open(self.index_file, "w", encoding="utf-8") as f:

                json.dump(self.index, f, indent=2)

        except Exception as e:

            print(f"[TTS-CACHE] Failed saving index: {e}")



    def _make_key(self, text: str, voice: str, pitch: float) -> str:

        clean = "".join(c for c in text.lower().strip() if c.isalnum() or c.isspace())

        norm = " ".join(clean.split())

        raw = f"{norm}|{voice.lower()}|{pitch:.2f}"

        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]



    def get(self, text: str, voice: str, pitch: float) -> Optional[str]:

        """Returns path to cached audio file if present, updating LRU metrics."""

        key = self._make_key(text, voice, pitch)

        with self.lock:

            if key in self.index:

                meta = self.index[key]

                fpath = self.cache_dir / meta.get("file", f"{key}.wav")

                if fpath.exists():

                    meta["last_accessed"] = time.time()

                    meta["hit_count"] = meta.get("hit_count", 0) + 1

                    self._save_index()

                    return str(fpath)

                else:

                    del self.index[key]

        return None



    def put(self, text: str, voice: str, pitch: float, src_wav_path: str) -> Optional[str]:

        """Stores a newly synthesized WAV file in the cache and manages LRU limits."""

        if not os.path.exists(src_wav_path) or os.path.getsize(src_wav_path) < 500:

            return None

        key = self._make_key(text, voice, pitch)

        dest_filename = f"{key}.wav"

        dest_path = self.cache_dir / dest_filename



        try:

            shutil.copy2(src_wav_path, str(dest_path))

            size_bytes = dest_path.stat().st_size

            with self.lock:

                self.index[key] = {

                    "text": text[:120],

                    "voice": voice,

                    "pitch": round(pitch, 2),

                    "file": dest_filename,

                    "size_bytes": size_bytes,

                    "created_at": time.time(),

                    "last_accessed": time.time(),

                    "hit_count": 1

                }

                self._save_index()

            self.auto_prune_if_needed()

            return str(dest_path)

        except Exception as e:

            print(f"[TTS-CACHE] Error storing cache for '{text[:30]}': {e}")

            return None



    def get_stats(self) -> Dict[str, Any]:

        """Returns live storage statistics, phrase counts, and hit metrics."""

        with self.lock:

            total_bytes = sum(item.get("size_bytes", 0) for item in self.index.values())

            total_hits = sum(item.get("hit_count", 0) for item in self.index.values())

            total_files = len(self.index)

            total_mb = total_bytes / (1024 * 1024)

            pct = (total_mb / self.limit_mb * 100.0) if self.limit_mb > 0 else 0.0



            return {

                "total_phrases": total_files,

                "total_bytes": total_bytes,

                "total_mb": round(total_mb, 2),

                "limit_mb": self.limit_mb,

                "usage_pct": round(pct, 1),

                "total_hits": total_hits,

                "cache_dir": str(self.cache_dir)

            }



    def calculate_downsize_impact(self, new_limit_mb: int) -> Dict[str, Any]:

        """Calculates how many phrases and megabytes would be deleted if downsized."""

        with self.lock:

            total_bytes = sum(item.get("size_bytes", 0) for item in self.index.values())

            current_mb = total_bytes / (1024 * 1024)

            if current_mb <= new_limit_mb:

                return {"needs_prune": False, "bytes_to_delete": 0, "mb_to_delete": 0.0, "phrases_to_delete": 0}



            target_bytes = int(new_limit_mb * 1024 * 1024 * 0.90)

            bytes_needed = max(0, total_bytes - target_bytes)



            sorted_items = sorted(

                self.index.items(),

                key=lambda x: (x[1].get("hit_count", 1) > 2, x[1].get("last_accessed", 0))

            )



            freed = 0

            count = 0

            for k, meta in sorted_items:

                freed += meta.get("size_bytes", 0)

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

        """Sets new capacity limit and executes pruning if current usage exceeds it."""

        new_limit = max(128, int(new_limit_mb))

        self.limit_mb = new_limit

        self.auto_prune_if_needed()

        return self.get_stats()



    def auto_prune_if_needed(self):

        """Prunes oldest / lowest-hit phrases if total size exceeds limit_mb."""

        with self.lock:

            total_bytes = sum(item.get("size_bytes", 0) for item in self.index.values())

            max_bytes = self.limit_mb * 1024 * 1024

            if total_bytes <= max_bytes:

                return



            target_bytes = int(max_bytes * 0.85)

            sorted_items = sorted(

                self.index.items(),

                key=lambda x: (x[1].get("hit_count", 1) > 2, x[1].get("last_accessed", 0))

            )



            for key, meta in sorted_items:

                fpath = self.cache_dir / meta.get("file", f"{key}.wav")

                if fpath.exists():

                    try:

                        fpath.unlink()

                    except Exception:

                        pass

                total_bytes -= meta.get("size_bytes", 0)

                del self.index[key]

                if total_bytes <= target_bytes:

                    break



            self._save_index()

            print(f"[TTS-CACHE] Auto-pruned cache down to {round(total_bytes / (1024*1024), 2)} MB")



    def clear(self) -> Dict[str, Any]:

        """Clears all cached audio files and resets the registry."""

        with self.lock:

            for f in self.cache_dir.glob("*.wav"):

                try:

                    f.unlink()

                except Exception:

                    pass

            self.index = {}

            self._save_index()

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

        """Splits multi-sentence / multi-clause responses into punctuation-bounded phrases."""

        import re

        text = text.strip()

        if not text:

            return []

        raw_chunks = re.split(r'(?<=[.!?])\s+|\n+', text)

        clauses = []

        for c in raw_chunks:

            c = c.strip()

            if not c:

                continue

            if len(c) < 4 and clauses:

                clauses[-1] = f"{clauses[-1]} {c}".strip()

            else:

                clauses.append(c)

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

                        subprocess.run(["espeak-ng", "-v", "en-us", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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

                    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)

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

                # 1. Primary: Use PipeWire pw-play so speech honors the selected audio sink (Uconnect Car Speakers or HDMI)

                try:

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



