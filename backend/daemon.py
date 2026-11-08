import os
import sys

# Initialize D-Bus GLib MainLoop as default before any D-Bus connection is opened
try:
    import dbus.mainloop.glib
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
except Exception:
    pass

"""

daemon.py - CarPi5 Central Telemetry & AI Daemon

Runs an ultra-lightweight HTTP + SSE (Server-Sent Events) server on port 8080.

Bridges CAN telemetry / physics simulation and the AI Copilot to the 7-inch dashboard.

Zero external dependencies required (runs on pure Python standard library).

"""



import os

import sys

import json

import time

import re

import urllib.parse

import subprocess

import threading

from pathlib import Path

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

from urllib.parse import urlparse, parse_qs

from dataclasses import asdict

from typing import Dict, Any, Optional, List



# Ensure backend directory is in sys.path

sys.path.insert(0, str(Path(__file__).parent))



# Import local modules

from telemetry.simulator import Dart14TSimulator

from telemetry.obd_reader import RealVehicleTelemetryReader
from telemetry.gps_manager import GpsManager

from ai.copilot import AICopilot

from ai.llm_client import LLMClient, PERSONALITIES

from fs_manager import (

    detect_usb_drives, list_directory, read_text_file,

    write_text_file, delete_item, copy_item, create_directory

)

from wifi_manager import WifiManager
from bluetooth_manager import BluetoothManager

from hardware.system_monitor import SystemMonitor

from hardware.gpio_controller import GpioController

from hardware.audio_player import AudioPlayer
from hardware.pedal_commander import PedalCommanderController
from hardware.avrcp_listener import AvrcpListener
from hardware.avrcp_player import AvrcpPlayerManager

from games.rom_manager import RomManager

from telemetry.trip_logger import TripLogger

try:

    from solar_ephemeris import get_solar_ephemeris

except ImportError:

    from backend.solar_ephemeris import get_solar_ephemeris



PORT = 8080

BASE_DIR = Path(__file__).parent.parent

UI_DIR = BASE_DIR / "ui" / "web_preview"



def get_media_playlist():

    """Scans local directories for real music audio tracks."""

    search_dirs = [

        Path("/home/nfgodin/Music"),

        Path("/home/nfgodin/odin-core/assets/sounds/.radio"),

        BASE_DIR / "storage" / "usb_drive" / "music",

        Path.home() / "Music"

    ]

    tracks = []

    seen = set()

    seen_filenames = set()
    track_id = 0
    audio_exts = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac"}

    try:
        import mutagen
    except ImportError:
        mutagen = None

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        for root, _, files in os.walk(s_dir):
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext in audio_exts:
                    full_p = os.path.abspath(os.path.join(root, f))
                    if full_p in seen or f.lower() in seen_filenames:
                        continue
                    seen.add(full_p)
                    seen_filenames.add(f.lower())
                    clean_name = os.path.splitext(f)[0]
                    artist = "In-Dash Audio"
                    title = clean_name
                    album = "CarPi5 In-Dash"
                    genre = "G59 / Hip-Hop"
                    year = "2024"
                    dur_sec = 0

                    if mutagen:
                        try:
                            m = mutagen.File(full_p, easy=True)
                            if m:
                                if m.get("title"):
                                    title = str(m["title"][0]).strip()
                                if m.get("artist"):
                                    artist = str(m["artist"][0]).strip()
                                if m.get("album"):
                                    album = str(m["album"][0]).strip()
                                if m.get("genre"):
                                    genre = str(m["genre"][0]).strip()
                                if m.get("date"):
                                    year = str(m["date"][0]).strip()[:4]
                                elif m.get("year"):
                                    year = str(m["year"][0]).strip()[:4]
                            raw_m = mutagen.File(full_p)
                            if raw_m and hasattr(raw_m, 'info') and hasattr(raw_m.info, 'length'):
                                dur_sec = round(raw_m.info.length)
                        except Exception:
                            pass

                    # Fallbacks if metadata not populated
                    if not title or title == clean_name:
                        if " - " in clean_name:
                            parts = clean_name.split(" - ", 1)
                            artist = parts[0].strip()
                            title = parts[1].strip()
                        elif "_" in clean_name:
                            title = clean_name.replace("_", " ")

                    title = re.sub(r'^\d+[\.\s\-]+', '', title).strip()
                    if artist.startswith("0") or artist.startswith("1"):
                        artist = re.sub(r'^\d+[\.\s\-]+', '', artist).strip()
                    if not artist or artist == clean_name or artist == "In-Dash Audio":
                        if "$uicideboy$" in full_p.lower() or "grey" in full_p.lower() or "g59" in full_p.lower():
                            artist = "$uicideboy$"

                    tracks.append({
                        "id": track_id,
                        "title": title or clean_name,
                        "artist": artist if artist != clean_name else "$uicideboy$",
                        "album": album or "CarPi5 In-Dash",
                        "genre": genre or "G59 / Hip-Hop",
                        "year": year,
                        "duration": dur_sec,
                        "filename": f,
                        "path": full_p,
                        "size_mb": round(os.path.getsize(full_p) / (1024 * 1024), 2),
                        "stream_url": f"/api/media/stream?file={urllib.parse.quote(full_p)}"
                    })
                    track_id += 1
    return tracks





SETTINGS_FILE = BASE_DIR / "config" / "app_settings.json"



def get_default_app_settings() -> Dict[str, Any]:

    """Default factory settings for Dodge Dart CarPi5 OS."""

    return {

        "telemetry_mode": "REAL",

        "test_mode": False,

        "screensaver_enabled": False,

        "screensaver_timeout": 0,

        "screensaver_folder": "/home/nfgodin/Pictures" if sys.platform.startswith("linux") else "",

        "clock_format": "12H",

        "brightness": 100,

        "driver_title": "Master",

        "driver_name": "Creator",

        "personality": "RUM",
        "voice_mode": "COPILOT",
        "speed_units": "MPH",
        "tts_cache_limit_mb": 1024
    }



def extract_emotion_and_clean_speech(text: str) -> tuple[str, str]:

    """

    Extracts emotion tag like [EMOTION: FLIRTY] or <emotion>devoted</emotion>

    from text, returning (emotion, cleaned_text).

    Defaults to 'DEVOTED' for M.A.I.A. if none specified.

    """

    if not text:

        return "DEVOTED", ""

    emotion = "DEVOTED"

    cleaned = text



    m = re.search(r'\[EMOTION:\s*([A-Za-z_]+)\]', text, re.IGNORECASE)

    if m:

        emotion = m.group(1).upper()

        cleaned = re.sub(r'\[EMOTION:\s*[A-Za-z_]+\]', '', cleaned).strip()

    else:

        m2 = re.search(r'<emotion>([A-Za-z_]+)</emotion>', text, re.IGNORECASE)

        if m2:

            emotion = m2.group(1).upper()

            cleaned = re.sub(r'<emotion>[A-Za-z_]+</emotion>', '', cleaned).strip()

        else:

            lower = text.lower()

            if any(w in lower for w in ["love", "darling", "sweetheart", "babe", "master", "adore"]):

                emotion = "DEVOTED"

            elif any(w in lower for w in ["tease", "wink", "flirt", "handsome", "cute", "naughty"]):

                emotion = "FLIRTY"

            elif any(w in lower for w in ["boost", "speed", "turbo", "pull", "fast", "whoosh", "launch", "spool"]):

                emotion = "EXCITED"

            elif any(w in lower for w in ["warning", "overheat", "danger", "check", "trouble", "fault", "hot"]):

                emotion = "CONCERNED"

            elif any(w in lower for w in ["happy", "great", "smile", "yay", "wonderful"]):

                emotion = "HAPPY"



    return emotion, cleaned



class CarPi5ServerState:

    def __init__(self):

        self.simulator = Dart14TSimulator()

        self.obd_reader = RealVehicleTelemetryReader()

        self.llm = LLMClient()

        self.wifi = WifiManager()
        self.bluetooth = BluetoothManager()

        self.sys_monitor = SystemMonitor()

        self.gpio = GpioController()

        self.rom_mgr = RomManager()

        self.trip_logger = TripLogger()

        self.audio = AudioPlayer()
        self.pedal_commander = PedalCommanderController()
        self.gps = GpsManager()
        self.gps.start()
        self.pi3_dashcam_host = "http://10.0.0.2:8000"
        self.pi3_host_last_check = 0
        
        def on_avrcp_event(act):
            with self.lock:
                self.latest_ui_action = act
            if act.get("type") == "volume":
                env = os.environ.copy()
                env['XDG_RUNTIME_DIR'] = '/run/user/1000'
                try:
                    if act.get("action") == "up":
                        subprocess.run(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '5%+'], env=env, timeout=2)
                    elif act.get("action") == "down":
                        subprocess.run(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '5%-'], env=env, timeout=2)
                    elif act.get("action") == "mute":
                        subprocess.run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle'], env=env, timeout=2)
                except Exception:
                    pass
        
        self.avrcp = AvrcpListener(action_callback=on_avrcp_event)
        self.avrcp_player = AvrcpPlayerManager(action_callback=on_avrcp_event)

        self.settings_file = SETTINGS_FILE

        self.settings = self._load_settings()

        # ALWAYS default to REAL vehicle telemetry unless test_mode is explicitly checked

        self.telemetry_mode = "TEST" if self.settings.get("test_mode", False) else "REAL"

        self.display_settings = self.settings

        initial_name = self.llm.get_driver_address()

        self.copilot = AICopilot(driver_name=initial_name)

        self.latest_frame = None

        self.latest_ai_event = None

        self.latest_ui_action = None

        self.sse_clients = []

        self.lock = threading.Lock()

        self.running = True

        self.wake_word_enabled = True

        self.live_convo_mode = False

        self.listen_once_requested = False

        self.is_mic_listening = False

        self.pending_voice_transcripts = []

        self._active_rec_proc = None



    def pop_voice_transcript(self):

        with self.lock:

            if self.pending_voice_transcripts:

                return self.pending_voice_transcripts.pop(0)

            return None



    def stop_current_listen(self):

        proc = self._active_rec_proc

        if proc and proc.poll() is None:

            try:

                proc.terminate()

            except Exception:

                pass

    def get_pi3_dashcam_host(self) -> str:
        now = time.time()
        if self.pi3_host_last_check and (now - self.pi3_host_last_check < 30):
            return self.pi3_dashcam_host

        candidates = [
            "http://10.0.0.2:8000",       # Direct in-car Ethernet link (1st priority)
            "http://carpi3.local:8000",   # mDNS fallback (Wi-Fi bench testing)
            "http://192.168.0.141:8000",  # Static IP fallback
        ]
        import urllib.request
        for cand in candidates:
            try:
                req = urllib.request.Request(f"{cand}/api/status", headers={"User-Agent": "CarPi5-Proxy"})
                with urllib.request.urlopen(req, timeout=0.6) as r:
                    if r.status == 200:
                        self.pi3_dashcam_host = cand
                        self.pi3_host_last_check = now
                        return cand
            except Exception:
                continue

        self.pi3_host_last_check = now
        return self.pi3_dashcam_host

    def _load_settings(self) -> Dict[str, Any]:

        defaults = get_default_app_settings()

        if self.settings_file.exists():

            try:

                with open(self.settings_file, "r") as f:

                    defaults.update(json.load(f))

            except Exception as e:

                print(f"[SETTINGS] Load error: {e}")

        else:

            try:

                self.settings_file.parent.mkdir(parents=True, exist_ok=True)

                with open(self.settings_file, "w") as f:

                    json.dump(defaults, f, indent=2)

            except Exception:

                pass

        return defaults



    def save_settings(self, new_settings: Dict[str, Any]):

        self.settings.update(new_settings)

        if "test_mode" in new_settings:

            self.telemetry_mode = "TEST" if new_settings["test_mode"] else "REAL"

        self.display_settings = self.settings

        try:

            self.settings_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.settings_file, "w") as f:

                json.dump(self.settings, f, indent=2)

            print("[SETTINGS] Saved app settings to disk.")

        except Exception as e:

            print(f"[SETTINGS] Save failed: {e}")



    def reset_settings(self) -> Dict[str, Any]:

        self.settings = get_default_app_settings()

        self.telemetry_mode = "REAL"

        self.display_settings = self.settings

        try:

            self.settings_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.settings_file, "w") as f:

                json.dump(self.settings, f, indent=2)

            print("[SETTINGS] Reset all settings to factory defaults.")

        except Exception as e:

            print(f"[SETTINGS] Reset save failed: {e}")

        return self.settings



state = CarPi5ServerState()

state.audio.configure_tts(state.llm.settings)



def telemetry_loop():

    """Background thread stepping telemetry at 25Hz and evaluating AI rules."""

    print(f"[TELEMETRY] Starting telemetry engine (Mode: {state.telemetry_mode})...")

    dt = 0.04  # 25 updates per second

    tick_count = 0

    while state.running:

        start_time = time.time()

        tick_count += 1

        

        # 1. Step telemetry (Real Vehicle vs Simulation)

        if state.telemetry_mode == "REAL":

            frame = state.obd_reader.read_frame()

        else:

            frame = state.simulator.step(dt)

        

        # 2. Evaluate AI copilot

        ai_event = state.copilot.evaluate_frame(frame)

        

        with state.lock:

            state.latest_frame = frame

            if ai_event:

                state.latest_ai_event = ai_event

                state.llm.log_speech(ai_event['speech'], source="COPILOT")

                if state.copilot.voice_mode != "MUTED" and ai_event.get('speech'):

                    state.audio.speak(ai_event['speech'])

                print(f"[AI COPILOT] {ai_event['hud_message']} -> \"{ai_event['speech']}\"")



        # 3. 1Hz Persistent Trip & Diagnostics Logging

        if tick_count % 25 == 0 and frame:

            state.trip_logger.log_telemetry_sample(asdict(frame))

        

        # Sleep to maintain steady 25Hz rate

        elapsed = time.time() - start_time

        sleep_time = max(0.001, dt - elapsed)

        time.sleep(sleep_time)





def usb_mic_listener_loop():

    """Continuous zero-gap hardware USB microphone listener (pw-record --raw + Auto-Gain + SpeechRecognition) for 'Hey Rum' & Live Convo."""

    if not sys.platform.startswith("linux"):

        return

    import struct

    import math

    from collections import deque



    print("[VOICE MIC] Starting Continuous Hardware USB Microphone Listener (DGM20 / PipeWire --raw)...", flush=True)

    env = os.environ.copy()

    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else "/run/user/1000"



    # Unmute and boost PipeWire USB microphone source gain (140%) so distant driver voice is clear

    try:

        subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "0"], env=env, timeout=2)

        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SOURCE@", "1.4"], env=env, timeout=2)

    except Exception:

        pass



    # Strict wake-word prefixes for "Hey Rum" (addressed to Rum)

    PHONETIC_RUM_PREFIXES = [

        "hey rum", "hi rum", "hello rum", "okay rum", "ok rum", "yo rum",

        "hey ram", "hi ram", "hello ram", "okay ram", "ok ram",

        "hey rem", "hi rem", "hello rem", "okay rem", "ok rem",

        "hey ron", "hi ron", "hello ron", "hey rob", "hi rob",

        "hey rome", "hi rome", "hey room", "hi room",

        "hey run", "hey rung", "hey drum", "r.u.m.", "r.u.m"

    ]

    # Standalone single-word wake triggers (strictly her name, never generic conversational words)

    STANDALONE_RUM_WORDS = {

        "rum", "r.u.m.", "r.u.m", "rem", "ram"

    }



    def normalize_and_recognize(raw_pcm: bytes, is_convo: bool):

        try:

            ns = len(raw_pcm) // 2

            if ns < 1600:

                return

            samples = struct.unpack(f"<{ns}h", raw_pcm[:ns * 2])

            mean_val = int(sum(samples) / ns)

            centered = [s - mean_val for s in samples]

            peak = max(abs(s) for s in centered) if centered else 1

            rms = math.sqrt(sum(s * s for s in centered) / ns) if centered else 0.0



            # Auto-gain normalization to peak=24500 (-2.5 dBFS), up to 45x gain boost!

            gain = min(45.0, 24500.0 / max(1, peak))

            norm_samples = [max(-32767, min(32767, int(s * gain))) for s in centered]

            norm_bytes = struct.pack(f"<{ns}h", *norm_samples)



            import speech_recognition as sr

            recognizer = sr.Recognizer()

            audio_data = sr.AudioData(norm_bytes, 16000, 2)

            heard = recognizer.recognize_google(audio_data).strip()

            if not heard:

                return



            print(f"[VOICE MIC] Heard ({'CONVO' if is_convo else 'WAKE'}): '{heard}' (raw RMS={rms:.0f}, Peak={peak}, Gain={gain:.1f}x)", flush=True)

            h_low = heard.lower().strip(" .,!?")



            # Normalize phonetic "Hey Rum" variations so UI shows "Hey Rum" cleanly

            normalized_text = heard

            is_wake_match = False



            for pref in PHONETIC_RUM_PREFIXES:

                if h_low == pref:

                    normalized_text = "Hey Rum"

                    is_wake_match = True

                    break

                elif h_low.startswith(pref + " ") or h_low.startswith(pref + ","):

                    rest = heard[len(pref):].lstrip(" ,.!?")

                    normalized_text = f"Hey Rum, {rest}" if rest else "Hey Rum"

                    is_wake_match = True

                    break



            if not is_wake_match and h_low in STANDALONE_RUM_WORDS:

                normalized_text = "Hey Rum"

                is_wake_match = True



            # In standby mode, strictly ignore speech that did not address Rum!

            if not is_convo and not is_wake_match:

                print(f"[VOICE MIC] Discarded non-wake speech in standby: '{heard}'", flush=True)

                return



            if is_convo or is_wake_match:

                with state.lock:

                    state.pending_voice_transcripts.append({

                        "text": normalized_text,

                        "mode": "convo" if is_convo else "wake",

                        "timestamp": time.time()

                    })

                if not is_convo and normalized_text.lower().strip(" !?.") == "hey rum":

                    state.listen_once_requested = True

                elif state.listen_once_requested and not state.live_convo_mode:

                    state.listen_once_requested = False

        except Exception as stt_err:

            if type(stt_err).__name__ != "UnknownValueError":

                print(f"[VOICE MIC] STT note: {type(stt_err).__name__}: {stt_err}", flush=True)



    last_spoke_end = 0.0

    while state.running:

        proc = None

        try:

            proc = subprocess.Popen(

                ["pw-record", "--raw", "--rate", "16000", "--channels", "1", "--format", "s16", "-"],

                stdout=subprocess.PIPE,

                stderr=subprocess.DEVNULL,

                env=env

            )

            state._active_rec_proc = proc



            pre_roll = deque(maxlen=6)  # 0.6s pre-roll buffer (6 x 100ms chunks)

            speech_chunks = []

            in_speech = False

            silence_frames = 0

            noise_rms = 95.0



            while state.running and proc.poll() is None:

                chunk = proc.stdout.read(3200)  # 100ms = 1600 int16 samples = 3200 bytes

                if not chunk or len(chunk) < 3200:

                    break



                # Pause listening while Rum's Piper TTS is actively playing out of speakers

                if getattr(state.audio, "is_speaking", False):

                    last_spoke_end = time.time()

                    in_speech = False

                    speech_chunks.clear()

                    pre_roll.clear()

                    state.is_mic_listening = False

                    continue



                if (time.time() - last_spoke_end) < 0.40:

                    in_speech = False

                    speech_chunks.clear()

                    pre_roll.clear()

                    continue



                is_convo = state.live_convo_mode or state.listen_once_requested

                is_wake = state.wake_word_enabled

                if not is_convo and not is_wake:

                    state.is_mic_listening = False

                    continue



                samples = struct.unpack("<1600h", chunk)

                rms = math.sqrt(sum(s * s for s in samples) / 1600)

                peak = max(abs(s) for s in samples)



                # Update adaptive ambient noise floor on quiet frames

                if not in_speech and rms < 350.0:

                    noise_rms = (noise_rms * 0.92) + (rms * 0.08)



                trig_rms = max(72.0, noise_rms * (1.35 if is_convo else 1.45))

                trig_peak = max(320, int(noise_rms * 3.2))



                if not in_speech:

                    pre_roll.append(chunk)

                    if rms >= trig_rms or peak >= trig_peak:

                        in_speech = True

                        silence_frames = 0

                        speech_chunks = list(pre_roll)

                        state.is_mic_listening = True

                    else:

                        state.is_mic_listening = is_convo

                else:

                    speech_chunks.append(chunk)

                    if rms < max(65.0, noise_rms * 1.25) and peak < trig_peak:

                        silence_frames += 1

                    else:

                        silence_frames = 0



                    # Finalize utterance after 0.5s of trailing silence or 4.8s max speech length

                    if silence_frames >= 5 or len(speech_chunks) >= 48:

                        full_pcm = b"".join(speech_chunks)

                        in_speech = False

                        speech_chunks = []

                        pre_roll.clear()

                        state.is_mic_listening = is_convo

                        # Only run STT if utterance had at least 300ms of audio

                        if len(full_pcm) >= 9600:

                            threading.Thread(

                                target=normalize_and_recognize,

                                args=(full_pcm, is_convo),

                                daemon=True

                            ).start()

        except Exception as loop_err:

            print(f"[VOICE MIC] Stream restart note: {loop_err}", flush=True)

            time.sleep(0.5)

        finally:

            if proc is not None and proc.poll() is None:

                try:

                    proc.terminate()

                except Exception:

                    pass



class CarPi5Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):

        super().__init__(*args, directory=str(UI_DIR), **kwargs)



    def do_HEAD(self):

        parsed = urlparse(self.path)

        if parsed.path == "/api/media/stream":

            params = parse_qs(parsed.query)

            file_path = params.get("file", [""])[0]

            if not file_path or not os.path.exists(file_path):

                self.send_response(404)

                self.end_headers()

                return

            ext = os.path.splitext(file_path)[1].lower()

            content_type = "audio/mpeg"

            if ext in [".m4a", ".mp4", ".aac"]:

                content_type = "audio/mp4"

            elif ext == ".wav":

                content_type = "audio/wav"

            elif ext == ".ogg":

                content_type = "audio/ogg"

            elif ext == ".flac":

                content_type = "audio/flac"

            file_size = os.path.getsize(file_path)

            self.send_response(200)

            self.send_header("Content-Type", content_type)

            self.send_header("Content-Length", str(file_size))

            self.send_header("Accept-Ranges", "bytes")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            return

        super().do_HEAD()



    def do_GET(self):

        parsed = urlparse(self.path)

        

        # 1. Server-Sent Events (SSE) Stream for real-time 25Hz telemetry

        if parsed.path == "/stream":

            self.send_response(200)

            self.send_header("Content-Type", "text/event-stream")

            self.send_header("Cache-Control", "no-cache")

            self.send_header("Connection", "keep-alive")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            

            try:

                last_ai_id = None

                while state.running:

                    with state.lock:

                        frame_dict = asdict(state.latest_frame) if state.latest_frame else {}

                        ai_dict = state.latest_ai_event

                        action_to_send = state.latest_ui_action

                        if action_to_send:

                            state.latest_ui_action = None

                    

                    voice_item = state.pop_voice_transcript()

                    # Package payload

                    payload = {

                        "telemetry": frame_dict,
                        "gps": state.gps.get_telemetry(),

                        "ai_event": ai_dict if ai_dict != last_ai_id else None,

                        "action": action_to_send,

                        "is_speaking": getattr(state.audio, "is_speaking", False),

                        "voice_transcript": voice_item,

                        "is_mic_listening": state.is_mic_listening,

                        "live_convo_mode": state.live_convo_mode,

                        "wake_word_enabled": state.wake_word_enabled

                    }

                    if ai_dict:

                        last_ai_id = ai_dict



                    data = f"data: {json.dumps(payload)}\n\n"

                    self.wfile.write(data.encode("utf-8"))

                    self.wfile.flush()

                    time.sleep(0.04)  # 25Hz stream

            except (ConnectionResetError, BrokenPipeError):

                pass

            return



        # 2. API Endpoints

        elif parsed.path == "/api/status":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            with state.lock:

                frame_dict = asdict(state.latest_frame) if state.latest_frame else {}

            self.wfile.write(json.dumps(frame_dict).encode("utf-8"))

            return



        elif parsed.path == "/api/dtc/lookup":

            qs = parse_qs(parsed.query)

            code = qs.get("code", [""])[0]

            explanation = state.copilot.diagnostics.explain_code(code)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(explanation).encode("utf-8"))

            return



        elif parsed.path == "/api/dtc/inject":

            qs = parse_qs(parsed.query)

            code = qs.get("code", ["P0299"])[0]

            state.simulator.inject_dtc(code)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "injected": code, "active": state.simulator.active_dtcs}).encode("utf-8"))

            print(f"[API] Injected DTC: {code}")

            return



        elif parsed.path == "/api/dtc/status":
            is_connected = bool(getattr(state.obd, "connected", False)) if hasattr(state, "obd") and state.obd else False
            if is_connected:
                active_dtcs = list(getattr(state.obd, "active_dtcs", []))
            else:
                active_dtcs = list(getattr(state.simulator, "active_dtcs", [])) if hasattr(state, "simulator") and state.simulator else []
            
            code_details = []
            if hasattr(state, "copilot") and state.copilot and hasattr(state.copilot, "diagnostics"):
                for code in active_dtcs:
                    code_details.append(state.copilot.diagnostics.explain_code(code))

            last_f = getattr(state, "last_frame", {}) or {}
            freeze_frame = {
                "rpm": last_f.get("rpm", 850),
                "boost_psi": last_f.get("boost_psi", 0.0),
                "coolant_temp_f": last_f.get("coolant_temp_f", 195),
                "speed_mph": last_f.get("speed_mph", 0),
                "engine_load_pct": last_f.get("engine_load_pct", 24.5),
                "throttle_pct": last_f.get("pedal_pos_pct", 12.0)
            }

            res = {
                "status": "ok",
                "connected": is_connected,
                "mil_active": len(active_dtcs) > 0,
                "active_dtcs": active_dtcs,
                "pending_dtcs": [],
                "code_details": code_details,
                "freeze_frame": freeze_frame,
                "readiness": {
                    "misfire": True, "fuel_system": True, "comprehensive": True,
                    "catalyst": True, "evap": True, "o2_sensor": True,
                    "o2_heater": True, "egr_vvt": True
                }
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/dtc/clear":
            if hasattr(state, "obd") and state.obd:
                try:
                    state.obd.clear_dtcs()
                except Exception:
                    pass
            if hasattr(state, "simulator") and state.simulator:
                state.simulator.clear_dtcs()
            state.copilot.announced_dtcs.clear()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "cleared": True}).encode("utf-8"))

            print("[API] Cleared all DTCs")

            return



        elif parsed.path == "/api/ai/voice_mode":

            qs = parse_qs(parsed.query)

            mode = qs.get("mode", ["COPILOT"])[0]

            state.copilot.set_voice_mode(mode)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "voice_mode": state.copilot.voice_mode}).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/status":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            status_data = {

                "ai_core": state.llm.get_ai_core_status(),

                "personality": state.llm.settings.get("personality", "RUM"),

                "driver_address": state.llm.get_driver_address(),

                "mode": state.llm.settings.get("mode", "BUILTIN"),

                "model_loaded": state.llm._llama_model is not None,

                "is_speaking": getattr(state.audio, "is_speaking", False),

                "is_mic_listening": state.is_mic_listening,

                "live_convo_mode": state.live_convo_mode,

                "wake_word_enabled": state.wake_word_enabled,

                "voice_transcript": state.pop_voice_transcript()

            }

            self.wfile.write(json.dumps(status_data).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/greeting/instant":

            greeting_info = state.llm.get_instant_greeting()

            raw_text = greeting_info.get("greeting", "")

            emotion, clean_text = extract_emotion_and_clean_speech(raw_text)

            greeting_info["greeting"] = clean_text

            greeting_info["emotion"] = emotion or "DEVOTED"

            if state.copilot.voice_mode != "MUTED" and clean_text:

                state.audio.speak(clean_text)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(greeting_info).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/greeting/official":

            with state.lock:

                frame_dict = asdict(state.latest_frame) if state.latest_frame else {}

            greeting_info = state.llm.get_neural_greeting(live_telemetry=frame_dict)

            raw_text = greeting_info.get("greeting", "")

            emotion, clean_text = extract_emotion_and_clean_speech(raw_text)

            greeting_info["greeting"] = clean_text

            greeting_info["emotion"] = emotion or "DEVOTED"

            if state.copilot.voice_mode != "MUTED" and clean_text:

                state.audio.speak(clean_text)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(greeting_info).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/speak":

            qs = parse_qs(parsed.query)

            text = qs.get("text", [""])[0]

            if text and state.copilot.voice_mode != "MUTED":

                state.audio.speak(text)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "spoken": text}).encode("utf-8"))

            return



        

        elif parsed.path == "/api/ai/models":

            models = state.llm.get_available_gguf_models()

            current_path = state.llm.settings.get("gguf_model_path", "")

            active_model = os.path.basename(current_path) if current_path else "qwen3b.gguf"

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({

                "models": models,

                "active_model": active_model,

                "status": state.llm.ai_core_status

            }).encode("utf-8"))

            return



        elif parsed.path == "/api/system/update/check":

            repo_dir = str(Path(__file__).parent.parent)

            try:

                subprocess.run(["git", "-C", repo_dir, "fetch", "origin", "main"], capture_output=True, timeout=15)

                local_rev = subprocess.run(["git", "-C", repo_dir, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()

                remote_rev = subprocess.run(["git", "-C", repo_dir, "rev-parse", "origin/main"], capture_output=True, text=True, timeout=5).stdout.strip()

                behind_res = subprocess.run(["git", "-C", repo_dir, "rev-list", "--count", "HEAD..origin/main"], capture_output=True, text=True, timeout=5).stdout.strip()

                commits_behind = int(behind_res) if behind_res.isdigit() else 0

                log_res = subprocess.run(["git", "-C", repo_dir, "log", "HEAD..origin/main", "--oneline", "-n", "10"], capture_output=True, text=True, timeout=5).stdout.strip()

                changelog = [line for line in log_res.split("\n") if line.strip()]

                

                self.send_response(200)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({

                    "status": "ok",

                    "version": "1.0.0",

                    "update_available": (commits_behind > 0 or (local_rev != remote_rev and bool(remote_rev))),

                    "commits_behind": commits_behind,

                    "current_commit": local_rev[:7] if local_rev else "unknown",

                    "remote_commit": remote_rev[:7] if remote_rev else "unknown",

                    "changelog": changelog,

                    "repo_url": "https://github.com/NfgOdin/Pi5-MAIA"

                }).encode("utf-8"))

            except Exception as e:

                self.send_response(500)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

            return



        elif parsed.path == "/api/settings/all":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(state.settings).encode("utf-8"))

            return

        elif parsed.path == "/api/display/settings":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(state.display_settings).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/greeting":

            with state.lock:

                frame_dict = asdict(state.latest_frame) if state.latest_frame else {}

                greeting_info = state.llm.get_startup_greeting(live_telemetry=frame_dict)

                state.latest_ai_event = {

                    "type": "STARTUP_GREETING",

                    "severity": "NORMAL",

                    "speech": greeting_info["greeting"],

                    "timestamp": time.time()

                }

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(greeting_info).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/personas":

            state.llm.reload_personas()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(state.llm.personas).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/history":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            with state.lock:

                data = {

                    "chat_history": state.llm.chat_history,

                    "speech_log": state.llm.speech_log,

                    "settings": state.llm.settings,

                    "personalities": {

                        k: {

                            "name": v["name"],

                            "full_name": v["full_name"],

                            "desc": v["description"],

                            "archetype": v.get("archetype", "Dedicated Cockpit AI"),

                            "avatar_image": v.get("avatar_image", "assets/pics/maia_avatar.jpg"),

                            "boot_splash_image": v.get("boot_splash_image", "assets/pics/splash.png"),

                            "boot_splash_video": v.get("boot_splash_video", ""),

                            "default": v.get("default", False)

                        } for k, v in state.llm.personas.items()

                    }

                }

            self.wfile.write(json.dumps(data).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/settings":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(state.llm.settings).encode("utf-8"))

            return



        elif parsed.path == "/api/auth/google/status":

            auth_status = state.llm.google_auth.get_status() if hasattr(state.llm, "google_auth") else {"authenticated": False}

            key = (state.llm.settings.get("api_key") or "").strip()

            auth_status["has_api_key"] = bool(key)

            auth_status["api_key_masked"] = (key[:6] + "...") if key else ""

            auth_status["mode"] = state.llm.settings.get("mode", "GEMINI")

            auth_status["gemini_model"] = state.llm.settings.get("gemini_model", "gemini-3.5-flash")

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(auth_status).encode("utf-8"))

            return



        elif parsed.path == "/api/fs/devices":

            drives = detect_usb_drives()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(drives).encode("utf-8"))

            return



        elif parsed.path == "/api/fs/list":

            qs = parse_qs(parsed.query)

            target = qs.get("path", [""])[0]

            result = list_directory(target)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(result).encode("utf-8"))

            return



        elif parsed.path == "/api/fs/read":

            qs = parse_qs(parsed.query)

            target = qs.get("path", [""])[0]

            result = read_text_file(target)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(result).encode("utf-8"))

            return



        elif parsed.path.startswith("/api/dashcam/") or parsed.path.startswith("/dashcam/"):
            # Proxy dashcam requests from Pi 5 to Pi 3 (auto-discovery: direct Ethernet 10.0.0.2 or Wi-Fi mDNS carpi3.local)
            pi3_host = state.get_pi3_dashcam_host()
            subpath = parsed.path
            if subpath.startswith("/api/dashcam/"):
                subpath = subpath[len("/api/dashcam/"):]
            elif subpath.startswith("/dashcam/"):
                subpath = subpath[len("/dashcam"):]
            if not subpath.startswith("/"):
                subpath = "/" + subpath
            target_url = f"{pi3_host}{subpath}"
            if parsed.query:
                target_url += f"?{parsed.query}"
            try:
                import urllib.request
                req = urllib.request.Request(target_url)
                resp = urllib.request.urlopen(req, timeout=10)
                ctype = resp.headers.get("Content-Type", "application/octet-stream")
                self.send_response(resp.status)
                self.send_header("Content-Type", ctype)
                self.send_header("Access-Control-Allow-Origin", "*")
                
                # If continuous stream (e.g. multipart MJPEG), stream chunks without buffering entire content
                if "multipart" in ctype:
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Pragma", "no-cache")
                    self.end_headers()
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                else:
                    data = resp.read()
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                resp.close()
            except Exception as e:
                state.pi3_host_last_check = 0
                try:
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Pi 3 dashcam unreachable", "details": str(e)}).encode("utf-8"))
                except Exception:
                    pass
            return

        elif parsed.path == "/api/wifi/status":

            status = state.wifi.get_status()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(status).encode("utf-8"))

            return



        elif parsed.path == "/api/wifi/scan":

            networks = state.wifi.scan_networks()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(networks).encode("utf-8"))

            return



        elif parsed.path == "/api/wifi/saved":

            saved = state.wifi.get_saved()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(saved).encode("utf-8"))

            return

        elif parsed.path in ("/api/bluetooth/status", "/api/bluetooth/devices"):
            status = state.bluetooth.get_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode("utf-8"))
            return

        elif parsed.path == "/api/bluetooth/scan":
            devices = state.bluetooth.scan_devices()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(devices).encode("utf-8"))
            return

        elif parsed.path == "/api/bluetooth/paired":
            paired = state.bluetooth.get_paired()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(paired).encode("utf-8"))
            return

        elif parsed.path == "/api/pedal_commander/status":
            res = state.pedal_commander.get_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/browser/proxy":
            query = parse_qs(parsed.query)
            target_url = query.get("url", [""])[0]
            if not target_url:
                self.send_response(400)
                self.end_headers()
                return
            try:
                import urllib.request
                req = urllib.request.Request(
                    target_url,
                    headers={'User-Agent': 'Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    content = resp.read()
                    ct = resp.headers.get("Content-Type", "text/html; charset=utf-8")
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Access-Control-Allow-Origin", "*")
                # Do NOT send X-Frame-Options or CSP frame-ancestors so iframes can embed any site
                self.end_headers()
                self.wfile.write(content)
            except Exception as ex:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(f"<h3>Unable to load {target_url}</h3><p>{ex}</p>".encode("utf-8"))
            return

        elif parsed.path == "/api/media/now_playing":
            cur = getattr(state.avrcp_player, "current_track", {}) if hasattr(state, "avrcp_player") else {}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "track": cur}).encode("utf-8"))
            return

        elif parsed.path == "/api/media/stremio_addons":
            addons_path = os.path.join(os.path.dirname(__file__), "..", "config", "stremio_addons.json")
            data = {"addons": []}
            if os.path.exists(addons_path):
                try:
                    with open(addons_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        elif parsed.path == "/api/audio/volume":
            vol = 80
            muted = False
            env = os.environ.copy()
            env['XDG_RUNTIME_DIR'] = '/run/user/1000'
            try:
                res = subprocess.run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'], capture_output=True, text=True, env=env, timeout=2)
                # output: "Volume: 0.80" or "Volume: 0.80 [MUTED]"
                m = re.search(r'Volume:\s*([\d\.]+)', res.stdout)
                if m:
                    vol = int(float(m.group(1)) * 100)
                muted = "[MUTED]" in res.stdout
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "volume": vol, "muted": muted}).encode("utf-8"))
            return

        elif parsed.path == "/api/audio/devices":
            audio = state.bluetooth.get_audio_devices()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(audio).encode("utf-8"))
            return

        elif parsed.path == "/api/audio/cache":
            stats = state.audio.get_cache_stats()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "cache": stats}).encode("utf-8"))
            return



        elif parsed.path == "/api/ui/navigate":

            query = parse_qs(parsed.query)

            target = query.get("screen", ["home"])[0]

            with state.lock:

                state.latest_ui_action = {"type": "navigate", "target": target}

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "screen": target}).encode("utf-8"))

            return



        elif parsed.path == "/api/ui/navigate":

            target = req_data.get("screen", "home")

            with state.lock:

                state.latest_ui_action = {"type": "navigate", "target": target}

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "screen": target}).encode("utf-8"))

            return



        elif parsed.path == "/api/gps":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(state.gps.get_telemetry()).encode("utf-8"))
            return

        elif parsed.path == "/api/telemetry/mode":

            mode_data = {

                "mode": state.telemetry_mode,

                "connected": state.obd_reader.connected if state.telemetry_mode == "REAL" else True,

                "status_message": state.obd_reader.status_message if state.telemetry_mode == "REAL" else "Running Fiat 1.4L MultiAir simulation engine."

            }

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(mode_data).encode("utf-8"))

            return



        elif parsed.path == "/api/solar/ephemeris":

            try:

                ephemeris = get_solar_ephemeris()

                self.send_response(200)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps(ephemeris).encode("utf-8"))

            except Exception as e:

                self.send_response(500)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

            return



        elif parsed.path == "/api/system/health":
            health = state.sys_monitor.get_system_health()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(health).encode("utf-8"))
            return

        elif parsed.path == "/api/system/fan":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"enabled": False, "status": "disabled"}).encode("utf-8"))
            return



        elif parsed.path == "/api/system/keyboard/toggle":
            env = os.environ.copy()
            env['XDG_RUNTIME_DIR'] = '/run/user/1000'
            env['WAYLAND_DISPLAY'] = 'wayland-0'
            try:
                check = subprocess.run(['pgrep', '-f', 'wvkbd-mobintl'], capture_output=True, text=True)
                if check.stdout.strip():
                    subprocess.run(['killall', '-SIGUSR1', 'wvkbd-mobintl'], env=env)
                    status = "toggled"
                else:
                    subprocess.Popen(['wvkbd-mobintl', '-L', '240', '--bg', '1a1a24', '--fg', 'ffffff', '--fn', 'Sans 13'], env=env)
                    status = "started"
            except Exception as e:
                status = f"error: {e}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": status}).encode("utf-8"))
            return

        elif parsed.path == "/api/system/browser/status":

            is_running = False

            try:

                res = subprocess.run(["pgrep", "-f", "firefox"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

                is_running = (res.returncode == 0)

            except Exception:

                pass

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"running": is_running}).encode("utf-8"))

            return



        elif parsed.path == "/api/system/browser/launch":

            def run_firefox():

                env = os.environ.copy()

                env["WAYLAND_DISPLAY"] = "wayland-0"

                env["DISPLAY"] = ":0"

                env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else "/run/user/1000"

                env["MOZ_ENABLE_WAYLAND"] = "1"

                try:

                    subprocess.run(["firefox"], env=env)

                except Exception as e:

                    print(f"[FIREFOX] Launch error: {e}", flush=True)



            threading.Thread(target=run_firefox, daemon=True).start()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "launched"}).encode("utf-8"))

            return



        elif parsed.path == "/api/system/browser/close":

            try:

                subprocess.run(["pkill", "-TERM", "-f", "firefox"], timeout=2)

            except Exception:

                pass

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "closed"}).encode("utf-8"))

            return



        elif parsed.path == "/api/system/brightness":

            data = {"brightness": state.sys_monitor.current_brightness}

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(data).encode("utf-8"))

            return



        elif parsed.path == "/api/gpio/pins":

            pins = state.gpio.get_pins_status()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(pins).encode("utf-8"))

            return



        elif parsed.path == "/api/gpio/relays":

            relays = state.gpio.get_relays_status()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(relays).encode("utf-8"))

            return



        elif parsed.path == "/api/games/roms":

            roms = state.rom_mgr.scan_roms()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(roms).encode("utf-8"))

            return



        elif parsed.path == "/api/trips/telemetry":
            qs = parse_qs(parsed.query)
            t_id = int(qs.get("id", [0])[0])
            pts = state.trip_logger.get_trip_telemetry(t_id) if (hasattr(state, "trip_logger") and state.trip_logger and t_id) else []
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(pts).encode("utf-8"))
            return

        elif parsed.path == "/api/trips/recent":

            trips = state.trip_logger.get_recent_trips()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(trips).encode("utf-8"))

            return



        elif parsed.path == "/api/trips/stats":

            stats = state.trip_logger.get_lifetime_stats()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(stats).encode("utf-8"))

            return



        elif parsed.path == "/api/trips/retention":

            res = {"retention_days": state.trip_logger.retention_days}

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path in ("/api/media/playlist", "/api/media/tracks"):
            tracks = get_media_playlist()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if parsed.path == "/api/media/tracks":
                self.wfile.write(json.dumps({"status": "ok", "tracks": tracks, "count": len(tracks)}).encode("utf-8"))
            else:
                self.wfile.write(json.dumps(tracks).encode("utf-8"))
            return



        elif parsed.path == "/api/media/stream":

            params = parse_qs(parsed.query)

            file_path = params.get("file", [""])[0]

            if not file_path or not os.path.exists(file_path):

                self.send_response(404)

                self.end_headers()

                return



            ext = os.path.splitext(file_path)[1].lower()

            content_type = "audio/mpeg"

            if ext in [".m4a", ".mp4", ".aac"]:

                content_type = "audio/mp4"

            elif ext == ".wav":

                content_type = "audio/wav"

            elif ext == ".ogg":

                content_type = "audio/ogg"

            elif ext == ".flac":

                content_type = "audio/flac"



            try:

                file_size = os.path.getsize(file_path)

                range_header = self.headers.get("Range")

                if range_header:

                    range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)

                    if range_match:

                        start = int(range_match.group(1))

                        end = int(range_match.group(2)) if range_match.group(2) else file_size - 1

                        if start >= file_size:

                            self.send_response(416)

                            self.send_header("Content-Range", f"bytes */{file_size}")

                            self.end_headers()

                            return

                        length = end - start + 1

                        self.send_response(206)

                        self.send_header("Content-Type", content_type)

                        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")

                        self.send_header("Content-Length", str(length))

                        self.send_header("Accept-Ranges", "bytes")

                        self.send_header("Access-Control-Allow-Origin", "*")

                        self.end_headers()

                        with open(file_path, "rb") as f_audio:

                            f_audio.seek(start)

                            bytes_remaining = length

                            while bytes_remaining > 0:

                                chunk_size = min(64 * 1024, bytes_remaining)

                                chunk = f_audio.read(chunk_size)

                                if not chunk:

                                    break

                                self.wfile.write(chunk)

                                bytes_remaining -= len(chunk)

                        return



                self.send_response(200)

                self.send_header("Content-Type", content_type)

                self.send_header("Content-Length", str(file_size))

                self.send_header("Accept-Ranges", "bytes")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                with open(file_path, "rb") as f_audio:

                    while True:

                        chunk = f_audio.read(64 * 1024)

                        if not chunk:

                            break

                        self.wfile.write(chunk)

                return

            except Exception:

                return



        elif parsed.path == "/api/models/avatars":

            avatar_dir = BASE_DIR / "models" / "avatars"

            vrm_files = []

            if avatar_dir.exists():

                for f in avatar_dir.glob("*.vrm"):

                    vrm_files.append({

                        "name": f.name,

                        "size_mb": round(f.stat().st_size / (1024 * 1024), 2),

                        "url": f"/api/models/vrm?name={urllib.parse.quote(f.name)}"

                    })

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(vrm_files).encode("utf-8"))

            return



        elif parsed.path in ("/api/models/vrm", "/api/models/vrma"):

            params = parse_qs(parsed.query)

            name = os.path.basename(params.get("name", [""])[0])



            # If requesting /api/models/vrma without ?name=, return list of all available VRMA animations

            if parsed.path == "/api/models/vrma" and not name:

                vrma_dir = BASE_DIR / "models" / "vrma"

                found_vrma = []

                if vrma_dir.exists():

                    for vf in sorted(vrma_dir.glob("*.vrma")):

                        found_vrma.append({

                            "name": vf.name,

                            "action": vf.stem.lower()

                        })

                self.send_response(200)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"files": found_vrma}).encode("utf-8"))

                return



            if parsed.path == "/api/models/vrma" or name.lower().endswith(".vrma"):

                vrm_path = BASE_DIR / "models" / "vrma" / name

            else:

                vrm_path = BASE_DIR / "models" / "avatars" / name

            if not vrm_path.exists():

                self.send_response(404)

                self.end_headers()

                return

            try:

                size = vrm_path.stat().st_size

                self.send_response(200)

                self.send_header("Content-Type", "model/gltf-binary")

                self.send_header("Content-Length", str(size))

                self.send_header("Accept-Ranges", "bytes")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                with open(vrm_path, "rb") as f_vrm:

                    while True:

                        c = f_vrm.read(64 * 1024)

                        if not c:

                            break

                        self.wfile.write(c)

                return

            except Exception:

                return



        elif parsed.path == "/api/models/bvh":

            params = parse_qs(parsed.query)

            name = os.path.basename(params.get("name", [""])[0])

            bvh_dirs = [BASE_DIR / "models" / "bvh", BASE_DIR / "models" / "vrma"]

            if not name:

                found = []

                seen = set()

                for bdir in bvh_dirs:

                    if bdir.exists():

                        for bf in sorted(bdir.glob("*.bvh")):

                            if bf.name not in seen:

                                seen.add(bf.name)

                                found.append({

                                    "name": bf.name,

                                    "action": bf.stem.lower()

                                })

                self.send_response(200)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"files": found}).encode("utf-8"))

                return



            bvh_path = None

            for bdir in bvh_dirs:

                cand = bdir / name

                if cand.exists():

                    bvh_path = cand

                    break

            if not bvh_path:

                self.send_response(404)

                self.end_headers()

                return

            try:

                content = bvh_path.read_bytes()

                self.send_response(200)

                self.send_header("Content-Type", "text/plain; charset=utf-8")

                self.send_header("Content-Length", str(len(content)))

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(content)

                return

            except Exception:

                return



        elif parsed.path == "/api/models/custom_props":
            props = []
            seen_names = set()
            valid_exts = {".obj", ".gltf", ".glb", ".vrm"}

            # 1. User storage directory (/storage/models/props)
            storage_props_dir = BASE_DIR / "storage" / "models" / "props"
            if storage_props_dir.exists():
                for p in sorted(storage_props_dir.rglob("*")):
                    if p.is_file() and p.suffix.lower() in valid_exts:
                        name = p.stem.replace("_", " ").title()
                        rel_path = str(p.relative_to(BASE_DIR)).replace("\\", "/")
                        props.append({
                            "id": f"prop_storage_{p.stem.lower()}",
                            "name": name,
                            "filename": p.name,
                            "format": p.suffix.lower().replace(".", ""),
                            "source": "storage",
                            "size_bytes": p.stat().st_size,
                            "size_formatted": f"{p.stat().st_size / 1024:.1f} KB" if p.stat().st_size < 1024*1024 else f"{p.stat().st_size / (1024*1024):.2f} MB",
                            "url": f"/{rel_path}"
                        })
                        seen_names.add(p.name)

            # 2. Built-in environment props
            env_props_dir = BASE_DIR / "ui" / "web_preview" / "models" / "environment" / "props"
            if env_props_dir.exists():
                for p in sorted(env_props_dir.rglob("*")):
                    if p.is_file() and p.suffix.lower() in valid_exts and p.name not in seen_names:
                        name = p.parent.name.replace("_", " ").title() if p.name.startswith("scene") else p.stem.replace("_", " ").title()
                        rel_path = str(p.relative_to(BASE_DIR / "ui" / "web_preview")).replace("\\", "/")
                        props.append({
                            "id": f"prop_builtin_{p.parent.name.lower()}_{p.stem.lower()}",
                            "name": name,
                            "filename": p.name,
                            "format": p.suffix.lower().replace(".", ""),
                            "source": "builtin",
                            "size_bytes": p.stat().st_size,
                            "size_formatted": f"{p.stat().st_size / 1024:.1f} KB" if p.stat().st_size < 1024*1024 else f"{p.stat().st_size / (1024*1024):.2f} MB",
                            "url": rel_path
                        })
                        seen_names.add(p.name)

            # 3. USB Drives
            usb_roots = ["/media/nfgodin", "/media", "/mnt", "storage/usb_drive"]
            for uroot in usb_roots:
                upath = (BASE_DIR / uroot).resolve() if not os.path.isabs(uroot) else Path(uroot)
                if upath.exists():
                    try:
                        for p in upath.rglob("*"):
                            if p.is_file() and p.suffix.lower() in valid_exts and p.name not in seen_names:
                                name = p.stem.replace("_", " ").title()
                                props.append({
                                    "id": f"prop_usb_{p.stem.lower()}",
                                    "name": f"{name} (USB)",
                                    "filename": p.name,
                                    "format": p.suffix.lower().replace(".", ""),
                                    "source": "usb",
                                    "size_bytes": p.stat().st_size,
                                    "size_formatted": f"{p.stat().st_size / 1024:.1f} KB" if p.stat().st_size < 1024*1024 else f"{p.stat().st_size / (1024*1024):.2f} MB",
                                    "url": f"/api/models/usb_file?path={urllib.parse.quote(str(p))}"
                                })
                                seen_names.add(p.name)
                    except Exception:
                        pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "props": props}).encode("utf-8"))
            return

        elif parsed.path == "/api/models/room_layout":
            cfg_path = BASE_DIR / "config" / "custom_room_layout.json"
            layout_data = {"version": 1, "props": []}
            if cfg_path.exists():
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        layout_data = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading custom_room_layout: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(layout_data).encode("utf-8"))
            return

        elif parsed.path == "/api/models/usb_file":
            params = parse_qs(parsed.query)
            file_path = params.get("path", [""])[0]
            target = Path(file_path).resolve()
            if target.exists() and target.is_file():
                ctype = "application/octet-stream"
                if target.suffix == ".obj":
                    ctype = "text/plain; charset=utf-8"
                elif target.suffix == ".gltf":
                    ctype = "model/gltf+json"
                elif target.suffix == ".glb":
                    ctype = "model/gltf-binary"
                elif target.suffix in [".png", ".jpg", ".jpeg"]:
                    ctype = "image/png" if target.suffix == ".png" else "image/jpeg"
                try:
                    data = target.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception as e:
                    logger.error(f"Error serving USB model file: {e}")
            self.send_response(404)
            self.end_headers()
            return

        # Direct Storage Static Files Handler (Manuals, PDFs, Dashcam clips, custom models)
        if parsed.path.startswith("/storage/"):
            rel = parsed.path.replace("/storage/", "", 1)
            target_file = (BASE_DIR / "storage" / rel).resolve()
            if target_file.exists() and target_file.is_file() and str(target_file).startswith(str(BASE_DIR / "storage")):
                ctype = "application/octet-stream"
                if target_file.suffix == ".pdf":
                    ctype = "application/pdf"
                elif target_file.suffix in [".md", ".txt", ".obj", ".mtl"]:
                    ctype = "text/plain; charset=utf-8"
                elif target_file.suffix == ".gltf":
                    ctype = "model/gltf+json"
                elif target_file.suffix == ".glb":
                    ctype = "model/gltf-binary"
                elif target_file.suffix == ".bin":
                    ctype = "application/octet-stream"
                elif target_file.suffix in [".jpg", ".jpeg"]:
                    ctype = "image/jpeg"
                elif target_file.suffix == ".png":
                    ctype = "image/png"
                elif target_file.suffix in [".mp4", ".mkv"]:
                    ctype = "video/mp4"
                
                try:
                    data = target_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception as e:
                    logger.error(f"Error serving storage file {target_file}: {e}")

        # Default static file serving (index.html, js, css)
        super().do_GET()



    def do_POST(self):

        parsed = urlparse(self.path)

        content_length = int(self.headers.get('Content-Length', 0))

        if parsed.path == "/api/media/now_playing":
            req_data = {}
            if content_length > 0:
                try:
                    req_data = json.loads(self.rfile.read(content_length).decode('utf-8'))
                except Exception:
                    pass
            title = req_data.get("title", "CarPi5 In-Dash Audio")
            artist = req_data.get("artist", "$uicideboy$")
            album = req_data.get("album", "CarPi5 In-Dash")
            genre = req_data.get("genre", "Music")
            dur = req_data.get("duration", 0)
            trk = req_data.get("track_num", 1)
            total = req_data.get("total_tracks", 1)
            status = req_data.get("status", "playing")
            if hasattr(state, "avrcp_player") and state.avrcp_player:
                state.avrcp_player.update_track(
                    title=title,
                    artist=artist,
                    album=album,
                    genre=genre,
                    duration_sec=dur,
                    track_num=trk,
                    total_tracks=total
                )
                state.avrcp_player.set_status(status)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "broadcasted": title}).encode("utf-8"))
            return



        # Audio transcription endpoint (Speech-To-Text from USB Microphone)

        if parsed.path == "/api/ai/transcribe":

            raw_audio = self.rfile.read(content_length) if content_length > 0 else b""

            transcribed_text = ""

            if raw_audio:

                in_path = None

                out_wav = None

                try:

                    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:

                        tmp_in.write(raw_audio)

                        in_path = tmp_in.name

                    out_wav = in_path + ".wav"

                    subprocess.run(["ffmpeg", "-y", "-i", in_path, "-ar", "16000", "-ac", "1", out_wav],

                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)

                    if os.path.exists(out_wav) and os.path.getsize(out_wav) > 800:

                        import speech_recognition as sr

                        r = sr.Recognizer()

                        with sr.AudioFile(out_wav) as source:

                            audio_data = r.record(source)

                        transcribed_text = r.recognize_google(audio_data)

                        print(f"[STT API] Transcribed from USB mic: '{transcribed_text}'")

                except Exception as ex:

                    print(f"[STT API] Transcribe note: {ex}")

                finally:

                    for p in [in_path, out_wav]:

                        if p and os.path.exists(p):

                            try: os.remove(p)

                            except Exception: pass



            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "text": transcribed_text}).encode("utf-8"))

            return



        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"

        try:

            req_data = json.loads(body)

        except Exception:

            req_data = {}



        if parsed.path == "/api/system/browser/launch":

            def run_firefox():

                env = os.environ.copy()

                env["WAYLAND_DISPLAY"] = "wayland-0"

                env["DISPLAY"] = ":0"

                env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else "/run/user/1000"

                env["MOZ_ENABLE_WAYLAND"] = "1"

                try:

                    subprocess.run(["firefox", "--new-tab", "https://google.com"],

                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)

                except Exception as e:

                    print(f"[FIREFOX] Launch error: {e}", flush=True)



            threading.Thread(target=run_firefox, daemon=True).start()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "launched"}).encode("utf-8"))

            return



        if parsed.path == "/api/system/browser/close":

            try:

                subprocess.run(["pkill", "-TERM", "-f", "firefox"], timeout=2)

            except Exception:

                pass

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "closed"}).encode("utf-8"))

            return



        if parsed.path == "/api/ai/listen":
            action = req_data.get("action", "toggle_convo")
            if action == "toggle_convo":
                state.live_convo_mode = not state.live_convo_mode
                if state.live_convo_mode:
                    state.listen_once_requested = True
                    state.is_mic_listening = True
                    state.audio.play_acknowledgment(state.llm.settings.get("personality", "RUM"))
                else:
                    state.listen_once_requested = False
                    state.stop_current_listen()
            elif action == "start_once":
                state.listen_once_requested = True
                state.is_mic_listening = True
                state.audio.play_acknowledgment(state.llm.settings.get("personality", "RUM"))

            elif action == "stop":

                state.live_convo_mode = False

                state.listen_once_requested = False

                state.stop_current_listen()

            elif action == "set_wake":

                state.wake_word_enabled = bool(req_data.get("enabled", True))

                if not state.wake_word_enabled:

                    state.stop_current_listen()



            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({

                "status": "ok",

                "live_convo_mode": state.live_convo_mode,

                "wake_word_enabled": state.wake_word_enabled,

                "is_mic_listening": state.is_mic_listening

            }).encode("utf-8"))

            return



        if parsed.path == "/api/ai/speak":

            text = req_data.get("text", "").strip()

            if text and state.copilot.voice_mode != "MUTED":

                state.audio.speak(text)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "spoken": text}).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/chat":

            user_msg = req_data.get("message", "").strip()

            if not user_msg:

                self.send_response(400)

                self.end_headers()

                return



            with state.lock:

                frame_dict = asdict(state.latest_frame) if state.latest_frame else {}

            

            # Query LLM with automated voice action extraction

            res = state.llm.chat_with_action(user_msg, live_telemetry=frame_dict)
            if res.get("action"):
                with state.lock:
                    state.latest_ui_action = res["action"]

            

            raw_reply = res.get("reply", "")

            emotion, clean_reply = extract_emotion_and_clean_speech(raw_reply)

            

            if clean_reply and state.copilot.voice_mode != "MUTED":

                state.audio.speak(clean_reply)

            

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({

                "status": "ok",

                "user_message": user_msg,

                "reply": clean_reply,

                "emotion": emotion,

                "action": res.get("action"),

                "persona": res.get("persona", state.llm.settings.get("personality", "RUM"))

            }).encode("utf-8"))

            return



        

        elif parsed.path == "/api/ai/models/swap":

            model_target = req_data.get("model", "")

            if not model_target:

                self.send_response(400)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "error", "message": "No model specified"}).encode("utf-8"))

                return



            persona = state.llm.personas.get(state.llm.settings.get("personality", "RUM"), {})

            p_name = persona.get("name", "R.U.M.")

            swap_announcement = f"Swapping out my neural brain to {model_target.replace('.gguf', '')}... give me just a moment!"

            state.audio.speak(swap_announcement)



            def do_swap():

                res = state.llm.swap_gguf_model(model_target)

                if res.get("success"):

                    ready_speech = f"Yay, Master! My new neural thoughts are warm and ready! Let's go zoomies in the Dart!"

                    state.audio.speak(ready_speech)

                else:

                    err_speech = f"Could not complete the neural swap: {res.get('message')}"

                    state.audio.speak(err_speech)



            threading.Thread(target=do_swap, daemon=True).start()



            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "message": f"Initiated swap to {model_target}"}).encode("utf-8"))

            return



        elif parsed.path == "/api/system/update/apply":

            repo_dir = str(Path(__file__).parent.parent)

            try:

                pull_res = subprocess.run(["git", "-C", repo_dir, "reset", "--hard", "origin/main"], capture_output=True, text=True, timeout=30)

                

                def delayed_restart():

                    time.sleep(1.5)

                    restart_cmd = f"pkill -f 'backend/daemon.py'; sleep 1; nohup python3 {repo_dir}/backend/daemon.py > {repo_dir}/daemon.log 2>&1 &"

                    subprocess.Popen(["/bin/bash", "-c", restart_cmd])



                threading.Thread(target=delayed_restart, daemon=True).start()



                self.send_response(200)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({

                    "status": "ok",

                    "message": "CarPi5 updated successfully! Restarting system...",

                    "git_output": pull_res.stdout.strip()

                }).encode("utf-8"))

            except Exception as e:

                self.send_response(500)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

            return



        elif parsed.path == "/api/settings/reset":

            defaults = state.reset_settings()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "settings": defaults}).encode("utf-8"))

            return



        elif parsed.path == "/api/settings/save":

            state.save_settings(req_data)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "settings": state.settings}).encode("utf-8"))

            return



        elif parsed.path == "/api/telemetry/mode":

            is_test = req_data.get("test_mode", False) or (req_data.get("mode", "").upper() == "TEST")

            state.telemetry_mode = "TEST" if is_test else "REAL"

            state.save_settings({"test_mode": is_test, "telemetry_mode": state.telemetry_mode})

            print(f"[TELEMETRY] Telemetry mode switched to: {state.telemetry_mode} (Test mode: {is_test})")

            mode_data = {

                "status": "ok",

                "mode": state.telemetry_mode,

                "test_mode": is_test,

                "connected": state.obd_reader.connected if state.telemetry_mode == "REAL" else True,

                "status_message": state.obd_reader.status_message if state.telemetry_mode == "REAL" else "Running Fiat 1.4L MultiAir simulation engine."

            }

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(mode_data).encode("utf-8"))

            return



        elif parsed.path == "/api/ai/settings":

            with state.lock:

                state.llm.save_settings(req_data)

                state.audio.configure_tts(state.llm.settings)

                address = state.llm.get_driver_address()

                state.copilot.driver_name = address

                reply_settings = state.llm.settings



            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "settings": reply_settings}).encode("utf-8"))

            return



        elif parsed.path == "/api/auth/google/start":

            cid = req_data.get("client_id")

            csec = req_data.get("client_secret")

            res = state.llm.google_auth.start_device_flow(cid, csec) if hasattr(state.llm, "google_auth") else {"status": "error", "message": "Google auth module unavailable"}

            self.send_response(200 if res.get("status") != "error" else 400)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/auth/google/logout":

            if hasattr(state.llm, "google_auth"):

                state.llm.google_auth.logout()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))

            return



        elif parsed.path == "/api/auth/google/config":

            cid = req_data.get("client_id", "")

            csec = req_data.get("client_secret", "")

            res = state.llm.google_auth.save_client_credentials(cid, csec) if hasattr(state.llm, "google_auth") else {"status": "error"}

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/fs/write":

            f_path = req_data.get("path", "")

            f_content = req_data.get("content", "")

            res = write_text_file(f_path, f_content)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/fs/delete":

            f_path = req_data.get("path", "")

            res = delete_item(f_path)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/fs/copy":

            src = req_data.get("src", "")

            dst = req_data.get("dst", "")

            res = copy_item(src, dst)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/fs/mkdir":

            parent = req_data.get("parent_path", "")

            name = req_data.get("folder_name", "New Folder")

            res = create_directory(parent, name)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/wifi/connect":

            ssid = req_data.get("ssid", "")

            pwd = req_data.get("password", None)

            auto_c = req_data.get("auto_connect", True)

            res = state.wifi.connect(ssid, pwd, auto_c)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/wifi/forget":

            ssid = req_data.get("ssid", "")

            res = state.wifi.forget(ssid)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/wifi/clear":

            res = state.wifi.clear_all()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/wifi/always_on":

            enabled = req_data.get("enabled", True)

            res = state.wifi.set_always_on(enabled)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return

        elif parsed.path == "/api/bluetooth/connect":
            mac = req_data.get("mac", "")
            res = state.bluetooth.connect_device(mac)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/bluetooth/disconnect":
            mac = req_data.get("mac", "")
            res = state.bluetooth.disconnect_device(mac)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/bluetooth/remove":
            mac = req_data.get("mac", "")
            res = state.bluetooth.remove_device(mac)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/bluetooth/discoverable":
            enable = req_data.get("enable", True)
            res = state.bluetooth.set_discoverable(enable)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/pedal_commander/set":
            mode = req_data.get("mode", "SPORT")
            level = req_data.get("level", 0)
            pin = req_data.get("pin")
            res = state.pedal_commander.set_curve(mode, level, pin=pin)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/pedal_commander/pin":
            pin = req_data.get("pin", "")
            if hasattr(state, "pedal_commander") and state.pedal_commander:
                state.pedal_commander.set_pin(pin)
            res = {"status": "ok", "pin": pin, "message": "Authentication PIN transmitted to Pedal Commander"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/audio/volume":
            vol_val = req_data.get("volume")
            delta = req_data.get("delta")
            act = req_data.get("action")
            env = os.environ.copy()
            env['XDG_RUNTIME_DIR'] = '/run/user/1000'
            try:
                if act == "mute":
                    subprocess.run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle'], env=env, timeout=2)
                elif vol_val is not None:
                    frac = max(0.0, min(1.5, float(vol_val) / 100.0))
                    subprocess.run(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', f"{frac:.2f}"], env=env, timeout=2)
                elif delta is not None:
                    d_str = f"{abs(int(delta))}%+" if int(delta) > 0 else f"{abs(int(delta))}%-"
                    subprocess.run(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', d_str], env=env, timeout=2)
            except Exception as e:
                print(f"[AUDIO VOLUME] Error setting volume: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            return

        elif parsed.path == "/api/audio/output":
            sink = req_data.get("sink")
            auto_r = req_data.get("auto_route")
            if auto_r is not None:
                state.bluetooth.set_auto_route(bool(auto_r))
            if sink is not None:
                res = state.bluetooth.set_audio_sink(sink)
            else:
                res = {"status": "ok", "auto_route": state.bluetooth.config.get("auto_route_audio", True)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/audio/input":
            source = req_data.get("source")
            if source is not None and hasattr(state, "bluetooth") and state.bluetooth:
                res = state.bluetooth.set_audio_source(source)
            else:
                res = {"status": "ok"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/audio/cache/limit":
            limit_mb = int(req_data.get("limit_mb", 1024))
            dry_run = bool(req_data.get("dry_run", False))
            if dry_run:
                impact = state.audio.calculate_downsize_impact(limit_mb)
                res = {"status": "ok", "impact": impact}
            else:
                stats = state.audio.set_cache_limit(limit_mb)
                state.settings["tts_cache_limit_mb"] = limit_mb
                state.save_settings(state.settings)
                if hasattr(state, "llm") and hasattr(state.llm, "settings"):
                    state.llm.settings["tts_cache_limit_mb"] = limit_mb
                    state.llm.save_settings(state.llm.settings)
                res = {"status": "ok", "cache": stats}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif parsed.path == "/api/audio/cache/clear":
            stats = state.audio.clear_cache()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "cache": stats}).encode("utf-8"))
            return



        elif parsed.path == "/api/system/brightness":

            val = req_data.get("brightness", 100)

            ok = state.sys_monitor.set_brightness(val)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "brightness": state.sys_monitor.current_brightness}).encode("utf-8"))

            return



        elif parsed.path == "/api/system/fan":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "disabled", "message": "Fan controller disabled"}).encode("utf-8"))
            return

        elif parsed.path == "/api/gpio/toggle":

            bcm = req_data.get("bcm", 17)

            state.gpio.toggle_pin(bcm)

            pins = state.gpio.get_pins_status()

            relays = state.gpio.get_relays_status()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "bcm": bcm, "pins": pins, "relays": relays}).encode("utf-8"))

            return



        elif parsed.path == "/api/gpio/set":

            bcm = req_data.get("bcm", 17)

            pin_state = req_data.get("state", False)

            state.gpio.set_pin(bcm, pin_state)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "bcm": bcm, "state": pin_state}).encode("utf-8"))

            return



        elif parsed.path == "/api/gpio/pulse":

            bcm = req_data.get("bcm", 18)

            dur = req_data.get("duration", 0.5)

            state.gpio.pulse_pin(bcm, dur)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "pulsed": bcm, "duration": dur}).encode("utf-8"))

            return



        elif parsed.path == "/api/gpio/morse":

            bcm = req_data.get("bcm", 18)

            msg = req_data.get("message", "SOS")

            state.gpio.transmit_morse(bcm, msg)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "morse": msg, "bcm": bcm}).encode("utf-8"))

            return



        elif parsed.path == "/api/games/launch":

            rom = req_data.get("rom_path", "")

            plat = req_data.get("platform", None)

            res = state.rom_mgr.launch_game(rom, plat)

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps(res).encode("utf-8"))

            return



        elif parsed.path == "/api/media/launch_kodi":

            try:

                env = os.environ.copy()

                env["DISPLAY"] = ":0"

                env["WAYLAND_DISPLAY"] = "wayland-0"

                if hasattr(os, "getuid"):

                    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

                else:

                    env["XDG_RUNTIME_DIR"] = "/run/user/1000"

                proc = subprocess.Popen(["kodi", "--standalone", "-fs"], env=env)

                self.send_response(200)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "ok", "message": "Kodi 10-Foot UI Launched", "pid": proc.pid}).encode("utf-8"))

            except Exception as e:

                self.send_response(500)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

            return



        elif parsed.path == "/api/media/launch_stremio":
            try:
                env = os.environ.copy()
                env["DISPLAY"] = ":0"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                if hasattr(os, "getuid"):
                    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
                else:
                    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                
                cmd = ["stremio"]
                proc = subprocess.Popen(cmd, env=env)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": "Stremio Launched", "pid": proc.pid}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
            return

        elif parsed.path == "/api/media/stremio_addons":
            addons_path = os.path.join(os.path.dirname(__file__), "..", "config", "stremio_addons.json")
            try:
                new_addon = json.loads(self.rfile.read(content_length).decode('utf-8'))
                data = {"addons": []}
                if os.path.exists(addons_path):
                    with open(addons_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                data.setdefault("addons", []).append(new_addon)
                with open(addons_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "addons": data["addons"]}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
            return

        elif parsed.path == "/api/media/launch_vlc":

            try:

                target = req_data.get("path")

                env = os.environ.copy()

                env["DISPLAY"] = ":0"

                env["WAYLAND_DISPLAY"] = "wayland-0"

                if hasattr(os, "getuid"):

                    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

                else:

                    env["XDG_RUNTIME_DIR"] = "/run/user/1000"

                cmd = ["vlc", "--fullscreen"]

                if target and os.path.exists(target):

                    cmd.append(target)

                proc = subprocess.Popen(cmd, env=env)

                self.send_response(200)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "ok", "message": "VLC Video Player Launched", "pid": proc.pid}).encode("utf-8"))

            except Exception as e:

                self.send_response(500)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

            return

        elif parsed.path == "/api/media/launch_youtube":
            try:
                mode = req_data.get("mode", "video")
                if mode == "music":
                    target_url = "https://music.youtube.com"
                elif mode == "tv":
                    target_url = "https://youtube.com/tv"
                else:
                    target_url = "https://www.youtube.com"

                env = os.environ.copy()
                env["DISPLAY"] = ":0"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                if hasattr(os, "getuid"):
                    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
                else:
                    env["XDG_RUNTIME_DIR"] = "/run/user/1000"

                cmd = ["chromium", f"--app={target_url}", "--start-maximized", "--no-first-run", "--disable-notifications"]
                proc = subprocess.Popen(cmd, env=env)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": f"YouTube ({mode}) Launched", "pid": proc.pid, "url": target_url}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
            return

        elif parsed.path == "/api/models/room_layout":
            cfg_path = BASE_DIR / "config" / "custom_room_layout.json"
            try:
                new_layout = json.loads(self.rfile.read(content_length).decode('utf-8'))
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(new_layout, f, indent=2)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": "Room layout saved", "count": len(new_layout.get("props", []))}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
            return



        elif parsed.path == "/api/trips/clear":

            success = state.trip_logger.clear_all_trips()

            self.send_response(200 if success else 500)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok" if success else "error", "message": "All trip logs cleared"}).encode("utf-8"))

            return



        elif parsed.path == "/api/trips/delete":

            trip_id = req_data.get("id")

            success = state.trip_logger.delete_trip(int(trip_id)) if trip_id else False

            self.send_response(200 if success else 400)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok" if success else "error"}).encode("utf-8"))

            return



        elif parsed.path == "/api/trips/retention":

            days = req_data.get("retention_days", 0)

            saved_days = state.trip_logger.set_retention_days(int(days))

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Access-Control-Allow-Origin", "*")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "ok", "retention_days": saved_days}).encode("utf-8"))

            return



        elif parsed.path == "/api/games/launch_retroarch":

            try:

                core = req_data.get("core")

                env = os.environ.copy()

                env["DISPLAY"] = ":0"

                env["WAYLAND_DISPLAY"] = "wayland-0"

                if hasattr(os, "getuid"):

                    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

                else:

                    env["XDG_RUNTIME_DIR"] = "/run/user/1000"

                cmd = ["retroarch", "--fullscreen"]

                if core:

                    cmd.extend(["-L", core])

                proc = subprocess.Popen(cmd, env=env)

                self.send_response(200)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "ok", "message": "RetroArch Fullscreen Launched", "pid": proc.pid}).encode("utf-8"))

            except Exception as e:

                self.send_response(500)

                self.send_header("Content-Type", "application/json")

                self.send_header("Access-Control-Allow-Origin", "*")

                self.end_headers()

                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

            return



        self.send_response(404)

        self.end_headers()



def run_server():

    # Start background physics thread

    t = threading.Thread(target=telemetry_loop, daemon=True)

    t.start()



    # Start background USB microphone Wake Word & Live Convo listener thread

    t_mic = threading.Thread(target=usb_mic_listener_loop, daemon=True)

    t_mic.start()



    server = ThreadingHTTPServer(("0.0.0.0", PORT), CarPi5Handler)

    server.daemon_threads = True

    print(f"\n=======================================================")

    print(f"  DODGE DART CARPI5 COCKPIT DAEMON ONLINE")

    print(f"  Access local dashboard at: http://localhost:{PORT}")

    print(f"=======================================================\n")

    try:

        server.serve_forever()

    except KeyboardInterrupt:

        state.running = False

        print("\n[DAEMON] Shutting down cleanly.")



if __name__ == "__main__":

    run_server()

