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
import sys
import json
import time
import wave
import queue
import tempfile
import threading
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any


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
        self.is_playing = False
        self.is_speaking = False

        # Voice Engine Configuration (persisted in app_settings / ai_settings)
        self.tts_engine = "KOKORO"          # "KOKORO" | "PIPER" | "ELEVENLABS" | "OPENAI_TTS"
        self.kokoro_voice = "af_nicole"     # "af_nicole" (Whisper / ASMR) | "af_bella" | "af_heart" | "af_sky"
        self.pitch_factor = 1.18            # Youthful anime pitch factor (1.18x = light, delicate anime girl timbre)
        self.elevenlabs_api_key = ""
        self.elevenlabs_voice_id = "jBpfuIE2acCO8z3wKNLl"  # 'Gigi' (Young Girl / Child anime-style voice)
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
        self.kokoro_model_candidates = [
            "/home/nfgodin/CarPi5/models/kokoro-v1.0.int8.onnx",
            str(base_models / "kokoro-v1.0.int8.onnx"),
            "/home/nfgodin/odin-core/models/kokoro-v1.0.int8.onnx",
        ]
        self.kokoro_voices_candidates = [
            "/home/nfgodin/CarPi5/models/voices-v1.0.bin",
            str(base_models / "voices-v1.0.bin"),
            "/home/nfgodin/odin-core/models/voices-v1.0.bin",
        ]

        # Candidate paths for Piper neural model (en_US-hfc_female-medium as primary default)
        self.model_candidates = [
            "/home/nfgodin/odin-core/models/en_US-hfc_female-medium.onnx",
            "/home/nfgodin/CarPi5/models/en_US-hfc_female-medium.onnx",
            str(base_models / "en_US-hfc_female-medium.onnx"),
            "/home/nfgodin/odin-core/models/en_US-amy-medium.onnx",
            "/home/nfgodin/CarPi5/models/en_US-amy-medium.onnx",
            str(base_models / "en_US-amy-medium.onnx"),
            "/home/nfgodin/odin-core/models/en_US-lessac-low.onnx",
            "/home/nfgodin/CarPi5/models/en_US-lessac-low.onnx",
            str(base_models / "en_US-lessac-low.onnx"),
        ]

        self.alsa_device = "plughw:0,0" if sys.platform.startswith("linux") else None

        # Start worker thread
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

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
            self.elevenlabs_voice_id = str(settings["elevenlabs_voice_id"]).strip()
        if "api_key" in settings and settings["api_key"]:
            self.openai_api_key = str(settings["api_key"]).strip()

    def get_tts_status(self) -> Dict[str, Any]:
        return {
            "tts_engine": self.tts_engine,
            "kokoro_voice": self.kokoro_voice,
            "tts_pitch": self.pitch_factor,
            "kokoro_ready": self._kokoro_loaded,
            "piper_ready": self._piper_loaded,
            "elevenlabs_configured": bool(self.elevenlabs_api_key),
            "elevenlabs_voice_id": self.elevenlabs_voice_id,
        }

    def _init_kokoro(self):
        """Loads Kokoro-82M int8 ONNX model and voices into RAM if available."""
        with self._kokoro_lock:
            if self._kokoro_instance is not None:
                return
            try:
                from kokoro_onnx import Kokoro
                model_p = next((p for p in self.kokoro_model_candidates if os.path.exists(p) and os.path.getsize(p) > 1000000), None)
                voices_p = next((p for p in self.kokoro_voices_candidates if os.path.exists(p) and os.path.getsize(p) > 100000), None)
                if model_p and voices_p:
                    print(f"[AUDIO] Loading Kokoro-82M neural voice model: {model_p}...")
                    self._kokoro_instance = Kokoro(model_p, voices_p)
                    self._kokoro_loaded = True
                    print("[AUDIO] Kokoro-82M neural voice ready for in-dash speech!")
            except Exception as e:
                print(f"[AUDIO] Kokoro-82M init note: {e}")

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

    def speak(self, text: str, priority: bool = False):
        """Queue text to be spoken aloud through in-dash speakers with automatic de-duplication."""
        if not text or not text.strip():
            return
        clean_text = text.strip()
        clean_text = clean_text.replace("*", "").replace("`", "").replace('"', '')

        now = time.time()
        if clean_text == self._last_spoken_text and ((now - self._last_spoken_time) < 8.0 or self.is_speaking):
            print(f"[AUDIO] De-duplicating repeat speech request: {clean_text[:40]}...")
            return
        self._last_spoken_text = clean_text
        self._last_spoken_time = now

        self.speech_queue.put(clean_text)

    def play_wav_file(self, wav_path: str):
        """Directly queue a WAV sound file for playback."""
        if os.path.exists(wav_path):
            self.speech_queue.put({"file": wav_path})

    def _worker_loop(self):
        """Background loop continuously consuming queued speech."""
        while True:
            try:
                item = self.speech_queue.get()
                if item is None:
                    break

                if isinstance(item, dict) and "file" in item:
                    self._play_file_direct(item["file"])
                elif isinstance(item, str):
                    self._synthesize_and_play(item)

                self.speech_queue.task_done()
            except Exception as e:
                print(f"[AUDIO] Playback error: {e}")
                time.sleep(0.1)

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
        except Exception as e:
            print(f"[AUDIO] ElevenLabs cloud TTS note (falling back to local): {e}")
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

    def _synthesize_and_play(self, text: str):
        """Synthesize text using the selected TTS engine (with automatic fallback), pitch-tune, and play."""
        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
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

            # Apply youthful 12-year-old girl pitch transform (unless ElevenLabs Gigi child voice is already used)
            if used_engine != "ELEVENLABS" and abs(self.pitch_factor - 1.0) > 0.01:
                try:
                    with wave.open(wav_path, "rb") as r:
                        sr = r.getframerate()
                    pf = self.pitch_factor
                    pitched_path = wav_path + ".pitched.wav"
                    cmd = [
                        "ffmpeg", "-y", "-i", wav_path,
                        "-af", f"asetrate={int(sr * pf)},atempo={1.0 / pf:.6f},aresample={sr}",
                        pitched_path
                    ]
                    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6)
                    if res.returncode == 0 and os.path.exists(pitched_path) and os.path.getsize(pitched_path) > 1000:
                        os.replace(pitched_path, wav_path)
                except Exception as p_err:
                    print(f"[AUDIO] Pitch shift note: {p_err}")

            # Prepend 0.12s silence so HDMI monitor sink wakes up cleanly
            try:
                with wave.open(wav_path, "rb") as r:
                    params = r.getparams()
                    frames = r.readframes(params.nframes)

                silent_count = int(params.framerate * 0.12)
                silence = b"\x00" * (silent_count * params.nchannels * params.sampwidth)

                with wave.open(wav_path, "wb") as w:
                    w.setparams(params)
                    w.writeframes(silence + frames)
            except Exception as ex:
                print(f"[AUDIO] Prepend silence note: {ex}")

            # Play the generated WAV file with exact hardware speaking state tracking
            self._play_file_direct(wav_path, lead_in_silence_sec=0.12)

        except Exception as e:
            print(f"[AUDIO] TTS synthesize failed: {e}")
        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

    def _play_file_direct(self, file_path: str, lead_in_silence_sec: float = 0.0):
        """Play WAV audio via aplay on HDMI 0 (or fallback to pw-play / aplay default) with exact lip-sync state tracking."""
        if not os.path.exists(file_path):
            return

        def mark_speaking():
            if lead_in_silence_sec > 0:
                time.sleep(lead_in_silence_sec)
            self.is_speaking = True

        threading.Thread(target=mark_speaking, daemon=True).start()

        try:
            if sys.platform.startswith("linux"):
                played = False
                try:
                    res = subprocess.run(["aplay", "-D", "plughw:0,0", "-B", "100000", "-q", file_path], capture_output=True, timeout=25)
                    if res.returncode == 0:
                        played = True
                except Exception:
                    pass

                if not played:
                    try:
                        res = subprocess.run(["pw-play", file_path], capture_output=True, timeout=25)
                        if res.returncode == 0:
                            played = True
                    except Exception:
                        pass

                if not played:
                    try:
                        subprocess.run(["aplay", "-B", "100000", "-q", file_path], capture_output=True, timeout=25)
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
