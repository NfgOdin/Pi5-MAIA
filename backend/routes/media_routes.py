"""HTTP route handlers for media playback, AVRCP, TTS cache/prewarm, and voice cockpit actions."""

import os
import subprocess
import threading
from typing import Any

from routes import read_json_body, send_json


def _wpctl_env() -> dict:
    env = os.environ.copy()
    if "XDG_RUNTIME_DIR" not in env and os.path.exists("/run/user/1000"):
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    return env


def _run_wpctl(*args: str) -> None:
    try:
        subprocess.run(["wpctl", *args], env=_wpctl_env(), timeout=2)
    except Exception:
        pass


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle media player, ducking, and TTS cache GET endpoints."""
    path = parsed.path

    if path == "/api/audio/duck_status":
        send_json(
            handler,
            {
                "status": "ok",
                "is_ducking": getattr(state.audio, "_is_currently_ducking", False),
                "is_speaking": getattr(state.audio, "is_speaking", False),
                "is_music_playing": getattr(state, "is_music_playing", False),
                "music_playing": getattr(state, "is_music_playing", False),
            },
        )
        return True

    if path == "/api/tts/stats":
        stats = state.audio.cache_mgr.get_stats() if getattr(state, "audio", None) else {}
        send_json(handler, {"status": "ok", "stats": stats})
        return True

    if path == "/api/tts/prewarm":
        try:
            from tools.prewarm_tts_cache import get_prewarm_status

            pw_status = get_prewarm_status()
        except Exception:
            pw_status = {"is_running": False, "pct": 0}
        send_json(handler, {"status": "ok", "prewarm": pw_status})
        return True

    if path == "/api/media/player/status":
        avrcp = getattr(state, "avrcp_player", None)
        cur = getattr(avrcp, "current_track", {}) if avrcp else {}
        status = getattr(avrcp, "playback_status", "paused") if avrcp else "paused"
        send_json(
            handler,
            {
                "status": "ok",
                "playback_status": status,
                "current_track": cur,
                "is_music_playing": getattr(state, "is_music_playing", False),
            },
        )
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle media, AVRCP, TTS prewarm, and cockpit action POST endpoints."""
    path = parsed.path

    if path == "/api/media/now_playing":
        req_data = read_json_body(handler)
        title = req_data.get("title", "CarPi5 In-Dash Audio")
        status = req_data.get("status", "playing")
        if getattr(state, "avrcp_player", None):
            state.avrcp_player.update_track(
                title=title,
                artist=req_data.get("artist", "$uicideboy$"),
                album=req_data.get("album", "CarPi5 In-Dash"),
                genre=req_data.get("genre", "Music"),
                duration_sec=req_data.get("duration", 0),
                track_num=req_data.get("track_num", 1),
                total_tracks=req_data.get("total_tracks", 1),
            )
            state.avrcp_player.set_status(status)
            state.is_music_playing = status.lower() == "playing"
        send_json(handler, {"status": "ok", "broadcasted": title})
        return True

    if path in ("/api/media/player/control", "/api/avrcp/action"):
        req_data = read_json_body(handler)
        action = req_data.get("action", "toggle")
        val = req_data.get("value")
        avrcp = getattr(state, "avrcp_player", None)
        if avrcp:
            if action in ("play", "resume"):
                avrcp.set_status("playing")
                state.is_music_playing = True
            elif action in ("pause", "stop"):
                avrcp.set_status("paused")
                state.is_music_playing = False
            elif action == "toggle":
                new_status = "paused" if state.is_music_playing else "playing"
                avrcp.set_status(new_status)
                state.is_music_playing = new_status == "playing"

        if action == "volume_up":
            _run_wpctl("set-volume", "@DEFAULT_AUDIO_SINK@", "5%+")
        elif action == "volume_down":
            _run_wpctl("set-volume", "@DEFAULT_AUDIO_SINK@", "5%-")
        elif action == "volume" and val is not None:
            try:
                v_pct = max(0, min(100, int(val)))
                _run_wpctl("set-volume", "@DEFAULT_AUDIO_SINK@", f"{v_pct / 100.0:.2f}")
            except Exception:
                pass

        send_json(
            handler,
            {
                "status": "ok",
                "action": action,
                "playback_status": getattr(avrcp, "playback_status", "paused") if avrcp else "paused",
            },
        )
        return True

    if path == "/api/cockpit/action":
        req_data = read_json_body(handler)
        cmd = req_data.get("command", "")
        reply_speech = None

        if cmd == "volume_up":
            _run_wpctl("set-volume", "@DEFAULT_AUDIO_SINK@", "8%+")
            reply_speech = "Turning it up for you, Dad!"
        elif cmd == "volume_down":
            _run_wpctl("set-volume", "@DEFAULT_AUDIO_SINK@", "8%-")
            reply_speech = "Turned the volume down, Dad."
        elif cmd == "mute":
            _run_wpctl("set-mute", "@DEFAULT_AUDIO_SINK@", "1")
            reply_speech = "Audio muted, Dad."
        elif cmd == "unmute":
            _run_wpctl("set-mute", "@DEFAULT_AUDIO_SINK@", "0")
            reply_speech = "Audio unmuted!"
        elif cmd == "night_mode":
            reply_speech = "Switching to Obsidian Midnight mode, easier on your eyes Dad!"
        elif cmd == "day_mode":
            reply_speech = "Day mode active, Dad!"
        elif cmd == "reset_trip":
            if getattr(state, "trip_logger", None):
                state.trip_logger.reset_current_trip()
            reply_speech = "Trip counters reset to zero, Dad!"

        send_json(handler, {"status": "ok", "command": cmd, "speech": reply_speech})
        return True

    if path == "/api/tts/prewarm":
        try:
            from tools.prewarm_tts_cache import get_prewarm_status, run_prewarm_job

            status = get_prewarm_status()
            if not status.get("is_running"):
                threading.Thread(target=run_prewarm_job, daemon=True, name="TTSPrewarmJob").start()
            send_json(handler, {"status": "started", "prewarm": get_prewarm_status()})
        except Exception as e:
            send_json(handler, {"status": "error", "error": str(e)}, status=500)
        return True

    return False
