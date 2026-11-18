"""daemon.py - CarPi5 Central Telemetry, SSE Stream & HTTP Daemon."""

import os
import sys

# Initialize D-Bus GLib MainLoop as default before any D-Bus connection is opened
try:
    import dbus.mainloop.glib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
except Exception:
    pass

from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import urllib.request

# Ensure backend directory is in sys.path
sys.path.insert(0, str(Path(__file__).parent))

from ai.copilot import AICopilot
from ai.llm_client import LLMClient
from ai.pip_connectome import PipConnectome
from ai.voice_listener import start_voice_listener
from bluetooth_manager import BluetoothManager
from games.rom_manager import RomManager
from hardware.audio_player import AudioPlayer
from hardware.avrcp_listener import AvrcpListener
from hardware.avrcp_player import AvrcpPlayerManager
from hardware.external_apps import start_external_app_supervisor
from hardware.gesture_detector import InCabinGestureController
from hardware.gpio_controller import GpioController
from hardware.pedal_commander import PedalCommanderController
from hardware.system_monitor import SystemMonitor
from navigation.tile_cache import (  # noqa: F401 - re-exported for legacy callers
    MAP_TILE_CACHE_DIR,
    MAP_TILE_DB_PATH,
    _get_tile_from_sqlite,
    get_cached_map_tile,
)
from routes import dispatch_get, dispatch_head, dispatch_post
from routes.ai_routes import extract_emotion_and_clean_speech  # noqa: F401
from routes.media_routes import get_media_playlist  # noqa: F401
from telemetry.gps_manager import GpsManager
from telemetry.obd_reader import RealVehicleTelemetryReader
from telemetry.simulator import Dart14TSimulator
from telemetry.trip_logger import TripLogger
from wifi_manager import WifiManager

PORT = 8080
BASE_DIR = Path(__file__).parent.parent
UI_DIR = BASE_DIR / "ui" / "web_preview"
LOGS_DIR = BASE_DIR / "storage" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = BASE_DIR / "config" / "app_settings.json"

logger = logging.getLogger("carpi5")
logger.setLevel(logging.INFO)
if not logger.handlers:
    rfh = RotatingFileHandler(
        str(LOGS_DIR / "daemon.log"),
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    rfh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(rfh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(sh)


def get_default_app_settings() -> Dict[str, Any]:
    """Return default factory settings for Dodge Dart CarPi5 OS."""
    return {
        "telemetry_mode": "REAL",
        "test_mode": False,
        "screensaver_enabled": False,
        "screensaver_timeout": 0,
        "screensaver_folder": str(Path.home() / "Pictures") if sys.platform.startswith("linux") else "",
        "clock_format": "12H",
        "brightness": 100,
        "driver_title": "Dad",
        "driver_name": "",
        "personality": None,
        "voice_mode": "COPILOT",
        "speed_units": "MPH",
        "tts_cache_limit_mb": 1024,
    }


class CarPi5ServerState:
    """Shared runtime state across telemetry, AI companion, hardware, and HTTP route handlers."""

    def __init__(self):
        self.base_dir = BASE_DIR
        self.lock = threading.Lock()
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
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                try:
                    if act.get("action") == "up":
                        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"], env=env, timeout=2)
                    elif act.get("action") == "down":
                        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"], env=env, timeout=2)
                    elif act.get("action") == "mute":
                        subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], env=env, timeout=2)
                except Exception:
                    pass

        self.avrcp = AvrcpListener(action_callback=on_avrcp_event)
        self.avrcp_player = AvrcpPlayerManager(action_callback=on_avrcp_event)

        def on_gesture_event(ev):
            with self.lock:
                self.latest_ui_action = {
                    "type": "gesture",
                    "gesture": ev.get("type"),
                    "confidence": ev.get("confidence", 1.0),
                }

        self.gesture_ctrl = InCabinGestureController("/dev/video0")
        self.gesture_ctrl.add_listener(on_gesture_event)
        self.gesture_ctrl.start()

        self.settings_file = SETTINGS_FILE
        self.settings = self._load_settings()
        if not self.settings.get("personality") and hasattr(self.llm, "get_default_persona_id"):
            self.settings["personality"] = self.llm.get_default_persona_id()

        # Phase 6 Audio Ducking Matrix & Music Courtesy Hookup
        self.is_music_playing = False
        self.audio.set_music_playing_checker(
            lambda: getattr(self, "is_music_playing", False)
            or (hasattr(self, "avrcp_player") and getattr(self.avrcp_player, "playback_status", "paused") == "playing")
        )
        self._vosk_model = None
        self._vosk_wake_rec = None

        # Phase 8 Offline Vector Memory & Maintenance Engine
        try:
            from ai.rag_memory import RagMemoryEngine

            self.rag = RagMemoryEngine()
            if hasattr(self.llm, "set_rag_engine"):
                self.llm.set_rag_engine(self.rag)
            threading.Thread(
                target=lambda: self.rag.ingest_manuals_directory(),
                daemon=True,
                name="rag_manual_sync",
            ).start()
        except Exception as e:
            print(f"[DAEMON] RAG Memory init note: {e}")
            self.rag = None

        # Phase 15 Cockpit Telephony, Family Kinship & AI Receptionist Studio
        try:
            from telephony.phone_manager import PhoneManager
            from telephony.sms_manager import SMSManager

            self.phone = PhoneManager()
            self.phone.set_audio_player(self.audio)
            self.phone.set_rag_engine(self.rag)
            self.sms = SMSManager()
            self.sms.set_dependencies(self.audio, self.rag, self.phone.kinship)
        except Exception as e:
            print(f"[DAEMON] Telephony init note: {e}")
            self.phone = None
            self.sms = None

        # Phase 11 Offline Turn-by-Turn Route Navigation & Semantic Waypoint Engine
        try:
            from navigation.router import NavigationRouter

            self.router = NavigationRouter()
            self.router.set_audio_player(self.audio)
        except Exception as e:
            print(f"[DAEMON] Navigation router init note: {e}")
            self.router = None

        # Phase 18 Canyon Run Lap Timer & Brake/Tire Thermal Degradation Telemetry
        try:
            from telemetry.lap_timer import CanyonLapTimer
            from telemetry.thermal_model import BrakeTireThermalModel

            self.thermal_model = BrakeTireThermalModel()
            self.thermal_model.set_audio_player(self.audio)
            self.lap_timer = CanyonLapTimer()
            self.lap_timer.set_audio_player(self.audio)
        except Exception as e:
            print(f"[DAEMON] Thermal / Lap timer init note: {e}")
            self.thermal_model = None
            self.lap_timer = None

        self.latest_thermal_data = None
        self.telemetry_mode = "TEST" if self.settings.get("test_mode", False) else "REAL"
        self.display_settings = self.settings
        initial_name = self.llm.get_driver_address()
        self.pip = PipConnectome()
        self.latest_pip_state = None
        self.copilot = AICopilot(driver_name=initial_name)
        if hasattr(self.copilot, "set_llm_client"):
            self.copilot.set_llm_client(self.llm)
        if self.rag and hasattr(self.copilot, "set_rag_engine"):
            self.copilot.set_rag_engine(self.rag)

        # Phase 12 Living Memory Fast Drive Buffer & Hippocampal Replay
        try:
            from ai.memory_manager import FastDriveMemoryBuffer, HippocampalReplayEngine

            self.drive_buffer = FastDriveMemoryBuffer()
            self.hippocampus = HippocampalReplayEngine()
        except Exception as e:
            print(f"[DAEMON] Memory buffer init note: {e}")
            self.drive_buffer = None
            self.hippocampus = None

        self.latest_frame = None
        self.latest_ai_event = None
        self.latest_ai_stream = None
        self._active_chat_cancel: Optional[threading.Event] = None
        self._active_stream_id: Optional[str] = None
        self.latest_ui_action = None
        self.sse_clients = []
        self.running = True
        self.wake_word_enabled = True
        self.live_convo_mode = False
        self.listen_once_requested = False
        self.is_mic_listening = False
        self.pending_voice_transcripts = []
        self._active_rec_proc = None

    def interrupt_ai_turn(self, reason: str = "USER_BARGE_IN") -> Dict[str, Any]:
        """Cancel active LLM stream, abort hardware speech playback, and reset stream state."""
        with self.lock:
            cancel_ev = self._active_chat_cancel
            active_sid = self._active_stream_id
            if cancel_ev is not None:
                cancel_ev.set()
            if active_sid:
                self.latest_ai_stream = {
                    "id": int(time.time() * 1000),
                    "stream_id": active_sid,
                    "interrupted": True,
                    "done": True,
                    "reason": reason,
                }
        seq = self.audio.stop_speaking() if hasattr(self.audio, "stop_speaking") else 0
        self.is_mic_listening = True
        print(f"[AI BARGE-IN] Interrupted active turn ({reason}, seq={seq})")
        return {"status": "ok", "interrupt_seq": seq, "reason": reason}

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

    def emit_ai_speech(
        self,
        text: str,
        source: str = "COPILOT",
        emotion: Optional[str] = None,
        hud_message: Optional[str] = None,
        speak: bool = True,
        priority: int = 1,
        client_id: Optional[str] = None,
        event_type: Optional[str] = None,
        action: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Unified backend speech emitter: cleans emotion tags, logs to history, updates SSE ai_event, and speaks."""
        import re
        raw = str(text or "").strip()
        if not raw:
            return None
        try:
            from ai.emote_choreographer import analyze_reply_choreography
        except ImportError:
            from backend.ai.emote_choreographer import analyze_reply_choreography

        choreo = analyze_reply_choreography(
            raw,
            explicit_emotion=emotion,
            explicit_action=action,
            persona_data=self.llm.get_active_persona() if hasattr(self.llm, "get_active_persona") else None,
            telemetry=asdict(self.latest_frame) if self.latest_frame else None,
        )
        clean_text = choreo["speech"]
        if not clean_text:
            return None
        detected_emotion = choreo["hud_emotion"]

        entry = self.llm.log_speech(
            clean_text,
            source=source,
            emotion=detected_emotion,
            client_id=client_id,
            hud_message=hud_message,
        )
        ev = {
            "id": entry["id"] if entry else int(time.time() * 1000),
            "client_id": client_id,
            "type": event_type or str(source or "COPILOT").upper(),
            "source": str(source or "COPILOT").upper(),
            "persona": entry.get("persona") if entry else self.llm.get_active_persona().get("name", "Companion"),
            "emotion": detected_emotion,
            "goemotion": choreo["goemotion"],
            "facial_preset": choreo["facial_preset"],
            "emote_clip": choreo["emote_clip"],
            "beats": choreo["beats"],
            "speech": clean_text,
            "hud_message": hud_message,
            "action": action,
            "timestamp": entry["timestamp"] if entry else time.time(),
            "time_str": entry["time_str"] if entry else time.strftime("%I:%M %p"),
        }
        with self.lock:
            self.latest_ai_event = ev
        if speak and self.copilot.voice_mode != "MUTED":
            self.audio.speak(clean_text, priority=priority)
            self.copilot.last_spoken_time = time.time()
        return ev

    def get_pi3_dashcam_host(self) -> str:
        now = time.time()
        if self.pi3_host_last_check and (now - self.pi3_host_last_check < 30):
            return self.pi3_dashcam_host
        candidates = [
            "http://10.0.0.2:8000",
            "http://carpi3.local:8000",
            "http://192.168.0.141:8000",
        ]
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
    dt = 0.04
    tick_count = 0

    while state.running:
        start_time = time.time()
        tick_count += 1

        if state.telemetry_mode == "REAL":
            frame = state.obd_reader.read_frame()
        else:
            frame = state.simulator.step(dt)

        circ_state = state.llm.get_circadian_state()
        state.latest_pip_state = state.pip.step(dt=dt, telemetry=frame, is_night=circ_state["is_night"])
        ai_event = state.copilot.evaluate_frame(
            frame,
            dt=dt,
            is_night=circ_state["is_night"],
            pip_state=state.latest_pip_state,
            gps_data=state.gps.get_telemetry(),
        )

        with state.lock:
            state.latest_frame = frame
            if getattr(state, "thermal_model", None) and frame:
                lat_g = 0.0
                long_g = 0.0
                if getattr(state, "gps", None):
                    gps_t = state.gps.get_telemetry()
                    if gps_t and gps_t.get("g_forces"):
                        lat_g = gps_t["g_forces"].get("lateral", 0.0)
                        long_g = gps_t["g_forces"].get("longitudinal", 0.0)
                state.latest_thermal_data = state.thermal_model.step(
                    frame.speed_mph or 0.0, lat_g=lat_g, long_g=long_g, dt=dt
                )
            if getattr(state, "lap_timer", None) and getattr(state, "gps", None):
                gps_t = state.gps.get_telemetry()
                if gps_t and gps_t.get("lat") and gps_t.get("lon"):
                    lat_g = gps_t.get("g_forces", {}).get("lateral", 0.0)
                    state.lap_timer.step(gps_t["lat"], gps_t["lon"], gps_t.get("speed_mph", 0.0), lat_g)
            if ai_event:
                ev_type = str(ai_event.get("type", "")).lower()
                is_critical = any(k in ev_type for k in ["fault", "overheat", "temp", "cold", "panic", "dtc"])
                p_level = 0 if is_critical else 1
                state.emit_ai_speech(
                    ai_event.get("speech", ""),
                    source="COPILOT",
                    emotion=ai_event.get("emotion", "DEVOTED"),
                    hud_message=ai_event.get("hud_message"),
                    speak=True,
                    priority=p_level,
                    event_type=ai_event.get("type"),
                    action=ai_event.get("action"),
                )
                print(f"[AI COPILOT] {ai_event.get('hud_message')} -> \"{ai_event.get('speech')}\"")

        if tick_count % 25 == 0 and frame:
            state.trip_logger.log_telemetry_sample(asdict(frame))
            if getattr(state, "rag", None) and frame:
                if frame.speed_mph and frame.speed_mph > 2.0:
                    state.rag.advance_odometer(frame.speed_mph * 1.0 / 3600.0)
                if tick_count % (25 * 30) == 0:
                    state.rag.sync_completed_trips()

        elapsed = time.time() - start_time
        time.sleep(max(0.001, dt - elapsed))


class CarPi5Handler(SimpleHTTPRequestHandler):
    """HTTP + SSE handler delegating API requests to modular route dispatchers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if dispatch_head(self, parsed):
            return
        super().do_HEAD()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                last_ai_id = None
                last_stream_pkt_id = None
                last_viseme_seq = 0
                while state.running:
                    with state.lock:
                        frame_dict = asdict(state.latest_frame) if state.latest_frame else {}
                        ai_dict = state.latest_ai_event
                        stream_pkt = state.latest_ai_stream
                        action_to_send = state.latest_ui_action
                        if action_to_send:
                            state.latest_ui_action = None

                    voice_item = state.pop_voice_transcript()
                    cur_seq = state.audio.get_speech_seq() if hasattr(state.audio, "get_speech_seq") else 0
                    viseme_to_send = None
                    if cur_seq and cur_seq != last_viseme_seq and hasattr(state.audio, "get_speech_viseme"):
                        viseme_to_send = state.audio.get_speech_viseme(cur_seq)
                        last_viseme_seq = cur_seq
                    stream_pkt_id = stream_pkt.get("id") if isinstance(stream_pkt, dict) else None
                    payload = {
                        "telemetry": frame_dict,
                        "gps": state.gps.get_telemetry(),
                        "circadian": state.llm.get_circadian_state(),
                        "mood": state.copilot.get_current_mood(),
                        "pip": state.latest_pip_state,
                        "ai_event": ai_dict if ai_dict != last_ai_id else None,
                        "ai_stream": stream_pkt if (stream_pkt and stream_pkt_id != last_stream_pkt_id) else None,
                        "action": action_to_send,
                        "is_speaking": getattr(state.audio, "is_speaking", False),
                        "speech_seq": cur_seq,
                        "speech_interrupt_seq": state.audio.get_speech_interrupt_seq() if hasattr(state.audio, "get_speech_interrupt_seq") else 0,
                        "speech_viseme": viseme_to_send,
                        "audio_duck": getattr(state.audio, "_is_currently_ducking", False),
                        "is_music_playing": getattr(state, "is_music_playing", False),
                        "music_playing": getattr(state, "is_music_playing", False),
                        "thermal": getattr(state, "latest_thermal_data", None),
                        "lap_timer": state.lap_timer.get_status() if getattr(state, "lap_timer", None) else None,
                        "voice_transcript": voice_item,
                        "is_mic_listening": state.is_mic_listening,
                        "live_convo_mode": state.live_convo_mode,
                        "wake_word_enabled": state.wake_word_enabled,
                    }
                    if ai_dict:
                        last_ai_id = ai_dict
                    if stream_pkt_id is not None:
                        last_stream_pkt_id = stream_pkt_id

                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.04)
            except (ConnectionResetError, BrokenPipeError):
                pass
            return

        if dispatch_get(self, parsed, state):
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if dispatch_post(self, parsed, state):
            return
        self.send_response(404)
        self.end_headers()


def run_server():
    """Start telemetry, voice listener, external app supervisor, and HTTP server."""
    threading.Thread(target=telemetry_loop, daemon=True, name="TelemetryLoop").start()
    start_voice_listener(state, BASE_DIR)
    start_external_app_supervisor()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), CarPi5Handler)
    server.daemon_threads = True

    print("\n=======================================================")
    print("  DODGE DART CARPI5 COCKPIT DAEMON ONLINE")
    print(f"  Access local dashboard at: http://localhost:{PORT}")
    print("=======================================================\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        state.running = False
        print("\n[DAEMON] Shutting down cleanly.")


if __name__ == "__main__":
    run_server()
