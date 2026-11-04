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
from ai.copilot import AICopilot
from ai.llm_client import LLMClient, PERSONALITIES
from fs_manager import (
    detect_usb_drives, list_directory, read_text_file,
    write_text_file, delete_item, copy_item, create_directory
)
from wifi_manager import WifiManager
from hardware.system_monitor import SystemMonitor
from hardware.gpio_controller import GpioController
from hardware.audio_player import AudioPlayer
from games.rom_manager import RomManager
from telemetry.trip_logger import TripLogger

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
                    if " - " in clean_name:
                        parts = clean_name.split(" - ", 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                    elif "_" in clean_name:
                        title = clean_name.replace("_", " ")

                    # Clean leading track numbers like 01, 02.
                    title = re.sub(r'^\d+[\.\s\-]+', '', title)
                    if artist.startswith("0") or artist.startswith("1"):
                        artist = re.sub(r'^\d+[\.\s\-]+', '', artist)

                    tracks.append({
                        "id": track_id,
                        "title": title or clean_name,
                        "artist": artist if artist != clean_name else "Grey59 / Dodge Dart",
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
        "personality": "MAIA",
        "voice_mode": "COPILOT",
        "speed_units": "MPH"
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
        self.sys_monitor = SystemMonitor()
        self.gpio = GpioController()
        self.rom_mgr = RomManager()
        self.trip_logger = TripLogger()
        self.audio = AudioPlayer()
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

class CarPi5Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

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
                    
                    # Package payload
                    payload = {
                        "telemetry": frame_dict,
                        "ai_event": ai_dict if ai_dict != last_ai_id else None,
                        "action": action_to_send
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

        elif parsed.path == "/api/dtc/clear":
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
                "personality": state.llm.settings.get("personality", "MAIA"),
                "driver_address": state.llm.get_driver_address(),
                "mode": state.llm.settings.get("mode", "BUILTIN"),
                "model_loaded": state.llm._llama_model is not None
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

        elif parsed.path == "/api/ui/navigate":
            from urllib.parse import parse_qs
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

        elif parsed.path == "/api/system/health":
            health = state.sys_monitor.get_system_health()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(health).encode("utf-8"))
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

        elif parsed.path == "/api/media/playlist":
            tracks = get_media_playlist()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
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

        # Default static file serving (index.html, js, css)
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
        
        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        if parsed.path == "/api/ai/chat":
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
                "persona": res.get("persona", state.llm.settings.get("personality", "MAIA"))
            }).encode("utf-8"))
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
                address = state.llm.get_driver_address()
                state.copilot.driver_name = address
                reply_settings = state.llm.settings

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "settings": reply_settings}).encode("utf-8"))
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

        elif parsed.path == "/api/system/brightness":
            val = req_data.get("brightness", 100)
            ok = state.sys_monitor.set_brightness(val)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "brightness": state.sys_monitor.current_brightness}).encode("utf-8"))
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
                proc = subprocess.Popen(["kodi"], env=env)
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
                cmd = ["retroarch"]
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
