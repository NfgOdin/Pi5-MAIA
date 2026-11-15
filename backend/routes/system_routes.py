"""HTTP route handlers for browser control, on-screen keyboard, logs, and RetroArch/ROM launcher."""

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from routes import read_json_body, send_bytes, send_json

LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("carpi5")


def _wayland_env() -> dict:
    env = os.environ.copy()
    env["WAYLAND_DISPLAY"] = "wayland-0"
    env["DISPLAY"] = ":0"
    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else "/run/user/1000"
    env["MOZ_ENABLE_WAYLAND"] = "1"
    return env


def _launch_firefox(url: str = None) -> None:
    def run_firefox():
        cmd = ["firefox"] + (["--new-tab", url] if url else [])
        try:
            subprocess.run(
                cmd,
                env=_wayland_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"[FIREFOX] Launch error: {e}", flush=True)

    threading.Thread(target=run_firefox, daemon=True).start()


def _close_firefox() -> None:
    try:
        subprocess.run(["pkill", "-TERM", "-f", "firefox"], timeout=2)
    except Exception:
        pass


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle keyboard, browser, log viewer, and ROM listing GET requests."""
    path = parsed.path

    if path == "/api/system/keyboard/toggle":
        env = _wayland_env()
        try:
            check = subprocess.run(["pgrep", "-f", "wvkbd-mobintl"], capture_output=True, text=True)
            if check.stdout.strip():
                subprocess.run(["killall", "-SIGUSR1", "wvkbd-mobintl"], env=env)
                status = "toggled"
            else:
                subprocess.Popen(
                    ["wvkbd-mobintl", "-L", "240", "--bg", "1a1a24", "--fg", "ffffff", "--fn", "Sans 13"],
                    env=env,
                )
                status = "started"
        except Exception as e:
            status = f"error: {e}"
        send_json(handler, {"status": status})
        return True

    if path == "/api/system/browser/status":
        is_running = False
        try:
            res = subprocess.run(["pgrep", "-f", "firefox"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            is_running = res.returncode == 0
        except Exception:
            pass
        send_json(handler, {"running": is_running})
        return True

    if path == "/api/system/browser/launch":
        _launch_firefox()
        send_json(handler, {"status": "launched"})
        return True

    if path == "/api/system/browser/close":
        _close_firefox()
        send_json(handler, {"status": "closed"})
        return True

    if path.startswith("/api/logs/view"):
        log_type = parse_qs(parsed.query).get("type", ["ui"])[0]
        log_filename = "daemon.log" if log_type == "daemon" else "ui_errors.log"
        target_file = LOGS_DIR / log_filename
        content = f"--- Log file: {log_filename} ---\n"
        if target_file.exists():
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    content += "".join(f.readlines()[-250:])
            except Exception as e:
                content += f"Error reading log: {e}\n"
        else:
            content += "No entries logged yet.\n"
        send_bytes(handler, content.encode("utf-8"), "text/plain; charset=utf-8")
        return True

    if path == "/api/games/roms":
        send_json(handler, state.rom_mgr.scan_roms())
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle browser, UI error logging, and game launcher POST requests."""
    path = parsed.path

    if path == "/api/system/browser/launch":
        _launch_firefox("https://google.com")
        send_json(handler, {"status": "launched"})
        return True

    if path == "/api/system/browser/close":
        _close_firefox()
        send_json(handler, {"status": "closed"})
        return True

    if path == "/api/logs/client_error":
        log_file = LOGS_DIR / "ui_errors.log"
        try:
            data = read_json_body(handler)
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            entry = (
                f"[{ts}] [{data.get('source', 'UI')}] {data.get('message', 'Unknown Error')}\n"
                f"  Stack: {data.get('stack', 'N/A')}\n"
                f"  URL: {data.get('url', 'N/A')}\n\n"
            )
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.warning(f"[CLIENT_UI_ERROR] {data.get('source')}: {data.get('message')}")
            send_json(handler, {"status": "recorded"})
        except Exception as e:
            send_json(handler, {"error": str(e)}, status=500)
        return True

    if path == "/api/games/launch":
        req_data = read_json_body(handler)
        res = state.rom_mgr.launch_game(req_data.get("rom_path", ""), req_data.get("platform", None))
        send_json(handler, res)
        return True

    if path == "/api/games/launch_retroarch":
        req_data = read_json_body(handler)
        try:
            core = req_data.get("core")
            cmd = ["retroarch", "--fullscreen"]
            if core:
                cmd.extend(["-L", core])
            proc = subprocess.Popen(cmd, env=_wayland_env())
            send_json(handler, {"status": "ok", "message": "RetroArch Fullscreen Launched", "pid": proc.pid})
        except Exception as e:
            send_json(handler, {"status": "error", "message": str(e)}, status=500)
        return True

    return False
