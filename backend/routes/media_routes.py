"""HTTP route handlers for media playback, AVRCP, PipeWire audio controls, and TTS cache/prewarm."""

import os
import re
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
    """Handle media player, PipeWire audio, and TTS cache GET endpoints."""
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

    if path == "/api/audio/volume":
        vol = 80
        muted = False
        try:
            res = subprocess.run(
                ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                capture_output=True,
                text=True,
                env=_wpctl_env(),
                timeout=2,
            )
            m = re.search(r"Volume:\s*([\d\.]+)", res.stdout)
            if m:
                vol = int(float(m.group(1)) * 100)
            muted = "[MUTED]" in res.stdout
        except Exception:
            pass
        send_json(handler, {"status": "ok", "volume": vol, "muted": muted})
        return True

    if path == "/api/audio/devices":
        send_json(handler, state.bluetooth.get_audio_devices())
        return True

    if path == "/api/audio/cache":
        send_json(handler, {"status": "ok", "cache": state.audio.get_cache_stats()})
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle media, AVRCP, PipeWire audio, TTS prewarm, and cockpit action POST endpoints."""
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

    if path == "/api/audio/volume":
        req_data = read_json_body(handler)
        vol_val = req_data.get("volume")
        delta = req_data.get("delta")
        act = req_data.get("action")
        if act == "mute":
            _run_wpctl("set-mute", "@DEFAULT_AUDIO_SINK@", "toggle")
        elif vol_val is not None:
            frac = max(0.0, min(1.5, float(vol_val) / 100.0))
            _run_wpctl("set-volume", "@DEFAULT_AUDIO_SINK@", f"{frac:.2f}")
        elif delta is not None:
            d_str = f"{abs(int(delta))}%+" if int(delta) > 0 else f"{abs(int(delta))}%-"
            _run_wpctl("set-volume", "@DEFAULT_AUDIO_SINK@", d_str)
        send_json(handler, {"status": "ok"})
        return True

    if path == "/api/audio/output":
        req_data = read_json_body(handler)
        sink = req_data.get("sink")
        auto_r = req_data.get("auto_route")
        if auto_r is not None:
            state.bluetooth.set_auto_route(bool(auto_r))
        if sink is not None:
            res = state.bluetooth.set_audio_sink(sink)
        else:
            res = {"status": "ok", "auto_route": state.bluetooth.config.get("auto_route_audio", True)}
        send_json(handler, res)
        return True

    if path == "/api/audio/input":
        req_data = read_json_body(handler)
        source = req_data.get("source")
        if source is not None and getattr(state, "bluetooth", None):
            res = state.bluetooth.set_audio_source(source)
        else:
            res = {"status": "ok"}
        send_json(handler, res)
        return True

    if path == "/api/audio/cache/limit":
        req_data = read_json_body(handler)
        limit_mb = int(req_data.get("limit_mb", 1024))
        if bool(req_data.get("dry_run", False)):
            res = {"status": "ok", "impact": state.audio.calculate_downsize_impact(limit_mb)}
        else:
            stats = state.audio.set_cache_limit(limit_mb)
            state.settings["tts_cache_limit_mb"] = limit_mb
            state.save_settings(state.settings)
            if getattr(state, "llm", None) and hasattr(state.llm, "settings"):
                state.llm.settings["tts_cache_limit_mb"] = limit_mb
                state.llm.save_settings(state.llm.settings)
            res = {"status": "ok", "cache": stats}
        send_json(handler, res)
        return True

    if path == "/api/audio/cache/clear":
        send_json(handler, {"status": "ok", "cache": state.audio.clear_cache()})
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
