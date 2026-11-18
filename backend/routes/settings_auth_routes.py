"""HTTP route handlers for core status, settings, display, Google OAuth, OTA updates, and UI navigation."""

import json
import os
import shlex
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from routes import frame_to_dict, read_json_body, send_json


def _repo_dir(state: Any) -> Path:
    return Path(getattr(state, "base_dir", Path(__file__).resolve().parent.parent.parent))


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle core status, settings, Google Auth, OTA update check, browser proxy, and UI navigate GET endpoints."""
    path = parsed.path

    if path == "/api/status":
        with state.lock:
            frame_dict = frame_to_dict(state.latest_frame)
        send_json(handler, frame_dict)
        return True

    if path == "/api/settings/all":
        send_json(handler, state.settings)
        return True

    if path == "/api/display/settings":
        send_json(handler, state.display_settings)
        return True

    if path == "/api/auth/google/status":
        auth_status = state.llm.google_auth.get_status() if hasattr(state.llm, "google_auth") else {"authenticated": False}
        key = (state.llm.settings.get("api_key") or "").strip()
        auth_status["has_api_key"] = bool(key)
        auth_status["api_key_masked"] = (key[:6] + "...") if key else ""
        auth_status["mode"] = state.llm.settings.get("mode", "GEMINI")
        auth_status["gemini_model"] = state.llm.settings.get("gemini_model", "gemini-3.5-flash")
        send_json(handler, auth_status)
        return True

    if path == "/api/system/update/check":
        repo_dir = str(_repo_dir(state))
        try:
            subprocess.run(["git", "-C", repo_dir, "fetch", "origin", "main"], capture_output=True, timeout=15)
            local_rev = subprocess.run(["git", "-C", repo_dir, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
            remote_rev = subprocess.run(["git", "-C", repo_dir, "rev-parse", "origin/main"], capture_output=True, text=True, timeout=5).stdout.strip()
            behind_res = subprocess.run(["git", "-C", repo_dir, "rev-list", "--count", "HEAD..origin/main"], capture_output=True, text=True, timeout=5).stdout.strip()
            commits_behind = int(behind_res) if behind_res.isdigit() else 0
            log_res = subprocess.run(["git", "-C", repo_dir, "log", "HEAD..origin/main", "--oneline", "-n", "10"], capture_output=True, text=True, timeout=5).stdout.strip()
            changelog = [line for line in log_res.split("\n") if line.strip()]
            send_json(
                handler,
                {
                    "status": "ok",
                    "version": "1.0.0",
                    "update_available": (commits_behind > 0 or (local_rev != remote_rev and bool(remote_rev))),
                    "commits_behind": commits_behind,
                    "current_commit": local_rev[:7] if local_rev else "unknown",
                    "remote_commit": remote_rev[:7] if remote_rev else "unknown",
                    "changelog": changelog,
                    "repo_url": "https://github.com/NfgOdin/Pi5-MAIA",
                },
            )
        except Exception as e:
            send_json(handler, {"status": "error", "message": str(e)}, status=500)
        return True

    if path == "/api/ui/navigate":
        target = parse_qs(parsed.query).get("screen", ["home"])[0]
        with state.lock:
            state.latest_ui_action = {"type": "navigate", "target": target}
        send_json(handler, {"status": "ok", "screen": target})
        return True

    if path == "/api/browser/proxy":
        target_url = parse_qs(parsed.query).get("url", [""])[0]
        if not target_url:
            handler.send_response(400)
            handler.end_headers()
            return True
        try:
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                content = resp.read()
                ct = resp.headers.get("Content-Type", "text/html; charset=utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", ct)
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            handler.wfile.write(content)
        except Exception as ex:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.end_headers()
            handler.wfile.write(f"<h3>Unable to load {target_url}</h3><p>{ex}</p>".encode("utf-8"))
        return True

    if path == "/api/privacy/inventory":
        try:
            from privacy_wipe import get_privacy_inventory
        except ImportError:
            from backend.privacy_wipe import get_privacy_inventory
        send_json(handler, {"status": "ok", "inventory": get_privacy_inventory(state)})
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle settings save/reset, Google OAuth, OTA update apply, and UI navigate POST endpoints."""
    path = parsed.path

    if path == "/api/privacy/wipe":
        req_data = read_json_body(handler)
        try:
            from privacy_wipe import execute_privacy_wipe
        except ImportError:
            from backend.privacy_wipe import execute_privacy_wipe
        cats = req_data.get("categories")
        res = execute_privacy_wipe(state, categories=cats)
        send_json(handler, res, status=200 if res.get("status") == "ok" else 400)
        return True

    if path == "/api/settings/reset":
        defaults = state.reset_settings()
        send_json(handler, {"status": "ok", "settings": defaults})
        return True

    if path == "/api/settings/save":
        req_data = read_json_body(handler)
        state.save_settings(req_data)
        send_json(handler, {"status": "ok", "settings": state.settings})
        return True

    if path == "/api/ui/navigate":
        req_data = read_json_body(handler)
        target = req_data.get("screen", "home")
        with state.lock:
            state.latest_ui_action = {"type": "navigate", "target": target}
        send_json(handler, {"status": "ok", "screen": target})
        return True

    if path == "/api/auth/google/start":
        req_data = read_json_body(handler)
        cid = req_data.get("client_id")
        csec = req_data.get("client_secret")
        res = (
            state.llm.google_auth.start_device_flow(cid, csec)
            if hasattr(state.llm, "google_auth")
            else {"status": "error", "message": "Google auth module unavailable"}
        )
        send_json(handler, res, status=200 if res.get("status") != "error" else 400)
        return True

    if path == "/api/auth/google/logout":
        if hasattr(state.llm, "google_auth"):
            state.llm.google_auth.logout()
        send_json(handler, {"status": "ok"})
        return True

    if path == "/api/auth/google/config":
        req_data = read_json_body(handler)
        cid = req_data.get("client_id", "")
        csec = req_data.get("client_secret", "")
        res = state.llm.google_auth.save_client_credentials(cid, csec) if hasattr(state.llm, "google_auth") else {"status": "error"}
        send_json(handler, res)
        return True

    if path == "/api/system/update/apply":
        repo_dir = str(_repo_dir(state))
        try:
            subprocess.run(["git", "-C", repo_dir, "fetch", "origin", "main"], capture_output=True, text=True, timeout=25)
            pull_res = subprocess.run(["git", "-C", repo_dir, "reset", "--hard", "origin/main"], capture_output=True, text=True, timeout=30)

            def delayed_restart() -> None:
                time.sleep(1.5)
                my_pid = os.getpid()
                q_repo = shlex.quote(repo_dir)
                q_py = shlex.quote(sys.executable or "python3")
                restart_cmd = (
                    f"sleep 0.5; kill {my_pid} 2>/dev/null || true; sleep 1.2; "
                    f"cd {q_repo} && nohup {q_py} {q_repo}/backend/daemon.py < /dev/null > {q_repo}/daemon.log 2>&1 &"
                )
                subprocess.Popen(
                    ["/bin/bash", "-c", restart_cmd],
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            threading.Thread(target=delayed_restart, daemon=True).start()
            send_json(
                handler,
                {
                    "status": "ok",
                    "message": "CarPi5 updated successfully! Restarting system...",
                    "git_output": pull_res.stdout.strip(),
                },
            )
        except Exception as e:
            send_json(handler, {"status": "error", "message": str(e)}, status=500)
        return True

    return False
