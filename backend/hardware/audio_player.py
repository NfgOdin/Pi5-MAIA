"""
audio_player.py - High-Performance In-Dash Audio & TTS Engine for CarPi5 on Raspberry Pi 5
Outputs directly to HDMI 0 ALSA hardware sink (aplay -D plughw:0,0) or PipeWire.
Features:
- Pre-loads Piper TTS neural voice model in memory for near-instant speech synthesis.
- Automatically prepends 0.8s silence to wake up HDMI monitor sink before audio frames.
- Background non-blocking worker queue.
- Full volume gain for in-dash speaker clarity.
"""

import os
import sys
import time
import wave
import queue
import tempfile
import threading
import subprocess
from pathlib import Path
from typing import Optional

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
        self._piper_voice = None
        self._piper_loaded = False
        
        # Candidate paths for Piper neural model
        self.model_candidates = [
            "/home/nfgodin/odin-core/models/en_US-amy-medium.onnx",
            "/home/nfgodin/CarPi5/models/en_US-amy-medium.onnx",
            "/home/nfgodin/odin-core/models/en_US-hfc_female-medium.onnx",
            "/home/nfgodin/CarPi5/models/en_US-hfc_female-medium.onnx",
            "/home/nfgodin/odin-core/models/en_US-lessac-low.onnx",
            "/home/nfgodin/CarPi5/models/en_US-lessac-low.onnx",
            str(Path(__file__).parent.parent.parent / "models" / "en_US-amy-medium.onnx"),
            str(Path(__file__).parent.parent.parent / "models" / "en_US-lessac-low.onnx")
        ]
        
        # Audio output device on Raspberry Pi 5 (HDMI 0 is card 0 device 0)
        self.alsa_device = "plughw:0,0" if sys.platform.startswith("linux") else None

        # Start worker thread
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

        # Warm up Piper TTS in background thread
        threading.Thread(target=self._init_piper, daemon=True).start()

    def _init_piper(self):
        """Loads the Piper neural voice into RAM."""
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
        """Queue text to be spoken aloud through in-dash speakers."""
        if not text or not text.strip():
            return
        clean_text = text.strip()
        # Clean markdown formatting or quotes from text
        clean_text = clean_text.replace("*", "").replace("`", "").replace('"', '')
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

    def _synthesize_and_play(self, text: str):
        """Synthesize text via Piper, prepend 0.8s HDMI wake silence, and play."""
        if not self._piper_voice:
            # Try to load if not yet ready
            self._init_piper()

        if not self._piper_voice:
            # Fallback on Linux if Piper library not available: espeak-ng / festival
            if sys.platform.startswith("linux"):
                try:
                    subprocess.run(["espeak-ng", "-v", "en-us", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
            return

        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name

            # Synthesize wave
            with wave.open(wav_path, "wb") as wav_file:
                self._piper_voice.synthesize_wav(text, wav_file)

            # Prepend 0.8s silence so HDMI monitor sink wakes up before speech begins
            try:
                with wave.open(wav_path, "rb") as r:
                    params = r.getparams()
                    frames = r.readframes(params.nframes)

                silent_count = int(params.framerate * 0.8)
                silence = b"\x00" * (silent_count * params.nchannels * params.sampwidth)

                with wave.open(wav_path, "wb") as w:
                    w.setparams(params)
                    w.writeframes(silence + frames)
            except Exception as ex:
                print(f"[AUDIO] Prepend silence note: {ex}")

            # Play the generated WAV file
            self._play_file_direct(wav_path)

        except Exception as e:
            print(f"[AUDIO] TTS synthesize failed: {e}")
        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

    def _play_file_direct(self, file_path: str):
        """Play WAV audio via aplay on HDMI 0 (or fallback to pw-play / aplay default)."""
        if not os.path.exists(file_path):
            return

        if sys.platform.startswith("linux"):
            # Try 1: Direct ALSA HDMI 0
            played = False
            try:
                res = subprocess.run(["aplay", "-D", "plughw:0,0", "-B", "100000", "-q", file_path], capture_output=True, timeout=15)
                if res.returncode == 0:
                    played = True
            except Exception:
                pass

            # Try 2: PipeWire pw-play
            if not played:
                try:
                    res = subprocess.run(["pw-play", file_path], capture_output=True, timeout=15)
                    if res.returncode == 0:
                        played = True
                except Exception:
                    pass

            # Try 3: Default ALSA
            if not played:
                try:
                    subprocess.run(["aplay", "-B", "100000", "-q", file_path], capture_output=True, timeout=15)
                except Exception:
                    pass
        elif sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(file_path, winsound.SND_FILENAME)
            except Exception:
                pass