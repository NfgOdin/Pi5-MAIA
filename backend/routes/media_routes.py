"""HTTP route handlers for media playback, AVRCP, PipeWire audio controls, external launchers, and TTS cache/prewarm."""

import json
import os
from pathlib import Path
import re
import subprocess
import threading
import urllib.parse
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

from hardware.external_apps import (
    close_external_apps_via_cdp,
    get_external_app_status,
    wayland_env,
)
from routes import read_json_body, send_bytes, send_json


def _base_dir(state: Any) -> Path:
    return Path(getattr(state, "base_dir", Path(__file__).resolve().parent.parent.parent))


def get_media_playlist(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Scan local directories for real music audio tracks with mutagen ID3 metadata."""
    root_dir = base_dir or Path(__file__).resolve().parent.parent.parent
    search_dirs = [
        Path.home() / "Music",
        root_dir / "storage" / "usb_drive" / "music",
        root_dir / "assets" / "sounds",
    ]
    tracks: List[Dict[str, Any]] = []
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
                if os.path.splitext(f)[1].lower() not in audio_exts:
                    continue
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
                        if raw_m and hasattr(raw_m, "info") and hasattr(raw_m.info, "length"):
                            dur_sec = round(raw_m.info.length)
                    except Exception:
                        pass

                if not title or title == clean_name:
                    if " - " in clean_name:
                        parts = clean_name.split(" - ", 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                    elif "_" in clean_name:
                        title = clean_name.replace("_", " ")

                title = re.sub(r"^\d+[\.\s\-]+", "", title).strip()
                if artist.startswith("0") or artist.startswith("1"):
                    artist = re.sub(r"^\d+[\.\s\-]+", "", artist).strip()
                if not artist or artist == clean_name or artist == "In-Dash Audio":
                    low_p = full_p.lower()
                    if "$uicideboy$" in low_p or "grey" in low_p or "g59" in low_p:
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
                    "stream_url": f"/api/media/stream?file={urllib.parse.quote(full_p)}",
                })
                track_id += 1

    return tracks


def _audio_content_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".m4a", ".mp4", ".aac"):
        return "audio/mp4"
    if ext == ".wav":
        return "audio/wav"
    if ext == ".ogg":
        return "audio/ogg"
    if ext == ".flac":
        return "audio/flac"
    return "audio/mpeg"


def handle_head(handler: Any, parsed: Any) -> bool:
    """Handle HEAD requests for audio streaming length and range headers."""
    if parsed.path != "/api/media/stream":
        return False
    file_path = parse_qs(parsed.query).get("file", [""])[0]
    if not file_path or not os.path.exists(file_path):
        handler.send_response(404)
        handler.end_headers()
        return True
    file_size = os.path.getsize(file_path)
    handler.send_response(200)
    handler.send_header("Content-Type", _audio_content_type(file_path))
    handler.send_header("Content-Length", str(file_size))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    return True


def _stream_audio_file(handler: Any, file_path: str) -> bool:
    if not file_path or not os.path.exists(file_path):
        handler.send_response(404)
        handler.end_headers()
        return True

    content_type = _audio_content_type(file_path)

    try:
        file_size = os.path.getsize(file_path)
        range_header = handler.headers.get("Range")
        if range_header:
            range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
                if start >= file_size:
                    handler.send_response(416)
                    handler.send_header("Content-Range", f"bytes */{file_size}")
                    handler.end_headers()
                    return True
                length = end - start + 1
                handler.send_response(206)
                handler.send_header("Content-Type", content_type)
                handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                handler.send_header("Content-Length", str(length))
                handler.send_header("Accept-Ranges", "bytes")
                handler.send_header("Access-Control-Allow-Origin", "*")
                handler.end_headers()
                with open(file_path, "rb") as f_audio:
                    f_audio.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f_audio.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        handler.wfile.write(chunk)
                        remaining -= len(chunk)
                return True

        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(file_size))
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        with open(file_path, "rb") as f_audio:
            while True:
                chunk = f_audio.read(64 * 1024)
                if not chunk:
                    break
                handler.wfile.write(chunk)
    except Exception:
        pass
    return True


def _handle_close_external_app(handler: Any) -> bool:
    try:
        close_external_apps_via_cdp()
        send_json(handler, {"status": "ok", "message": "External media app closed"})
    except Exception as e:
        send_json(handler, {"status": "error", "message": str(e)}, status=500)
    return True


def _launch_wayland_app(handler: Any, cmd: List[str], label: str, extra: Optional[Dict[str, Any]] = None) -> bool:
    try:
        proc = subprocess.Popen(cmd, env=wayland_env())
        payload: Dict[str, Any] = {"status": "ok", "message": label, "pid": proc.pid}
        if extra:
            payload.update(extra)
        send_json(handler, payload)
    except Exception as e:
        send_json(handler, {"status": "error", "message": str(e)}, status=500)
    return True


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

    if path == "/api/audio/speech_clip":
        seq_raw = parse_qs(parsed.query).get("seq", ["0"])[0]
        try:
            seq = int(seq_raw)
        except ValueError:
            seq = 0
        clip_bytes = state.audio.get_speech_clip(seq) if hasattr(state.audio, "get_speech_clip") else None
        if not clip_bytes:
            handler.send_response(404)
            handler.end_headers()
            return True
        send_bytes(handler, clip_bytes, "audio/wav", cache_control="no-store")
        return True

    if path == "/api/media/now_playing":
        cur = getattr(state.avrcp_player, "current_track", {}) if hasattr(state, "avrcp_player") else {}
        send_json(handler, {"status": "ok", "track": cur})
        return True

    if path == "/api/media/stremio_addons":
        addons_path = _base_dir(state) / "config" / "stremio_addons.json"
        data: Dict[str, Any] = {"addons": []}
        if addons_path.exists():
            try:
                with open(addons_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        send_json(handler, data)
        return True

    if path in ("/api/media/playlist", "/api/media/tracks"):
        tracks = get_media_playlist(_base_dir(state))
        if path == "/api/media/tracks":
            send_json(handler, {"status": "ok", "tracks": tracks, "count": len(tracks)})
        else:
            send_json(handler, tracks)
        return True

    if path == "/api/media/stream":
        file_path = parse_qs(parsed.query).get("file", [""])[0]
        return _stream_audio_file(handler, file_path)

    if path == "/api/media/close_external_app":
        return _handle_close_external_app(handler)

    if path == "/api/media/external_app_status":
        try:
            send_json(handler, get_external_app_status())
        except Exception as e:
            send_json(handler, {"status": "error", "message": str(e)}, status=500)
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

    if path == "/api/media/launch_kodi":
        return _launch_wayland_app(handler, ["kodi", "--standalone", "-fs"], "Kodi 10-Foot UI Launched")

    if path == "/api/media/launch_stremio":
        return _launch_wayland_app(handler, ["stremio"], "Stremio Launched")

    if path == "/api/media/stremio_addons":
        addons_path = _base_dir(state) / "config" / "stremio_addons.json"
        try:
            new_addon = read_json_body(handler)
            data: Dict[str, Any] = {"addons": []}
            if addons_path.exists():
                with open(addons_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data.setdefault("addons", []).append(new_addon)
            addons_path.parent.mkdir(parents=True, exist_ok=True)
            with open(addons_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            send_json(handler, {"status": "ok", "addons": data["addons"]})
        except Exception as e:
            send_json(handler, {"status": "error", "message": str(e)}, status=500)
        return True

    if path == "/api/media/launch_vlc":
        req_data = read_json_body(handler)
        target = req_data.get("path")
        cmd = ["vlc", "--fullscreen"]
        if target and os.path.exists(target):
            cmd.append(target)
        return _launch_wayland_app(handler, cmd, "VLC Video Player Launched")

    if path == "/api/media/launch_youtube":
        req_data = read_json_body(handler)
        mode = req_data.get("mode", "video")
        if mode == "music":
            target_url = "https://music.youtube.com"
        elif mode == "tv":
            target_url = "https://youtube.com/tv"
        else:
            target_url = "https://www.youtube.com"
        cmd = [
            "chromium",
            f"--app={target_url}",
            "--start-maximized",
            "--no-first-run",
            "--disable-notifications",
            "--disable-features=BlockInsecurePrivateNetworkRequests,PrivateNetworkAccessSendPreflights,PrivateNetworkAccessRespectPreflightResults",
        ]
        return _launch_wayland_app(handler, cmd, f"YouTube ({mode}) Launched", extra={"url": target_url})

    if path == "/api/media/close_external_app":
        return _handle_close_external_app(handler)

    return False
