"""External media app supervisor, Wayland environment helper, and CDP exit-pill injector."""

import json
import os
import subprocess
import threading
import time
import urllib.request
from typing import Any, Dict


KIOSK_URL_PREFIX = "file:///home/nfgodin/CarPi5"
CDP_TARGETS_URL = "http://127.0.0.1:9222/json"

TOUCH_EXIT_PILL_JS = r"""
(() => {
    try {
        if (document.getElementById('carpiTouchExitPill')) return 'present';
        const btn = document.createElement('div');
        btn.id = 'carpiTouchExitPill';
        btn.textContent = '◀ EXIT TO CARPI5';
        btn.style.cssText = [
            'position: fixed !important',
            'top: 10px !important',
            'left: 10px !important',
            'z-index: 2147483647 !important',
            'width: 175px !important',
            'height: 48px !important',
            'border-radius: 24px !important',
            'background: linear-gradient(135deg, #ff0055, #cc0033) !important',
            'color: #ffffff !important',
            'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important',
            'font-size: 15px !important',
            'font-weight: 900 !important',
            'letter-spacing: 0.5px !important',
            'display: flex !important',
            'align-items: center !important',
            'justify-content: center !important',
            'box-shadow: 0 4px 20px rgba(0, 0, 0, 0.8), 0 0 16px rgba(255, 0, 85, 0.7) !important',
            'border: 2px solid rgba(255, 255, 255, 0.8) !important',
            'cursor: pointer !important',
            'user-select: none !important',
            'touch-action: none !important',
            'transition: transform 0.1s ease, opacity 0.2s ease !important'
        ].join(';');

        let isDragging = false;
        let startX = 0, startY = 0, initialLeft = 10, initialTop = 10, hasMoved = false;

        btn.addEventListener('touchstart', (e) => {
            isDragging = true;
            hasMoved = false;
            const touch = e.touches[0];
            startX = touch.clientX;
            startY = touch.clientY;
            const rect = btn.getBoundingClientRect();
            initialLeft = rect.left;
            initialTop = rect.top;
            btn.style.transform = 'scale(0.96)';
        }, { passive: false });

        window.addEventListener('touchmove', (e) => {
            if (!isDragging) return;
            const touch = e.touches[0];
            const dx = touch.clientX - startX;
            const dy = touch.clientY - startY;
            if (Math.abs(dx) > 6 || Math.abs(dy) > 6) hasMoved = true;
            btn.style.left = Math.max(6, Math.min(window.innerWidth - btn.offsetWidth - 6, initialLeft + dx)) + 'px';
            btn.style.top = Math.max(6, Math.min(window.innerHeight - btn.offsetHeight - 6, initialTop + dy)) + 'px';
            e.preventDefault();
        }, { passive: false });

        const triggerExit = () => {
            btn.textContent = 'Closing...';
            btn.style.opacity = '0.5';
            document.title = '__CARPI_EXIT__';
            try { window.location.hash = '#carpi_exit'; } catch(e){}
        };

        btn.addEventListener('touchend', () => {
            if (!isDragging) return;
            isDragging = false;
            btn.style.transform = 'scale(1.0)';
            if (!hasMoved) triggerExit();
        });

        btn.addEventListener('click', () => {
            if (!hasMoved) triggerExit();
        });

        (document.documentElement || document.body).appendChild(btn);
        return 'injected';
    } catch(e) {
        return 'error: ' + e.message;
    }
})();
"""


def wayland_env() -> Dict[str, str]:
    """Build display environment variables for launching Wayland/XWayland media apps."""
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    env["WAYLAND_DISPLAY"] = "wayland-0"
    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else "/run/user/1000"
    return env


def get_external_app_status(timeout: float = 1.0) -> Dict[str, Any]:
    """Inspect Chrome DevTools Protocol targets to detect active external app pages."""
    is_active = False
    active_title = ""
    active_url = ""
    try:
        res = urllib.request.urlopen(CDP_TARGETS_URL, timeout=timeout)
        targets = json.loads(res.read().decode())
        for t in targets:
            url = t.get("url", "")
            if t.get("type") == "page" and KIOSK_URL_PREFIX not in url:
                is_active = True
                active_title = t.get("title", "")
                active_url = url
                break
    except Exception:
        pass
    return {"status": "ok", "active": is_active, "title": active_title, "url": active_url}


def close_external_apps_via_cdp(timeout: float = 2.0) -> None:
    """Close any non-kiosk Chromium targets via CDP and kill standalone app windows."""
    try:
        import websocket

        res = urllib.request.urlopen(CDP_TARGETS_URL, timeout=timeout)
        targets = json.loads(res.read().decode())
        for t in targets:
            url = t.get("url", "")
            ws_url = t.get("webSocketDebuggerUrl")
            if t.get("type") == "page" and KIOSK_URL_PREFIX not in url and ws_url:
                ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
                ws.send(json.dumps({"id": 999, "method": "Page.close"}))
                ws.close()
    except Exception as e_cdp:
        print(f"[DAEMON] CDP closeTarget error: {e_cdp}")
    subprocess.run(["pkill", "-f", "chromium.*--app="], check=False)


def start_external_app_supervisor() -> None:
    """Monitor CDP page targets, inject the draggable exit pill, and handle exit triggers."""
    def _supervisor_loop() -> None:
        try:
            import websocket
        except Exception as e_ws:
            print(f"[SUPERVISOR] websocket unavailable: {e_ws}")
            return

        while True:
            time.sleep(0.5)
            try:
                res = urllib.request.urlopen(CDP_TARGETS_URL, timeout=0.8)
                targets = json.loads(res.read().decode())
                for t in targets:
                    url = t.get("url", "")
                    title = t.get("title", "")
                    if t.get("type") != "page" or KIOSK_URL_PREFIX in url:
                        continue
                    ws_url = t.get("webSocketDebuggerUrl")
                    if title == "__CARPI_EXIT__" or "#carpi_exit" in url:
                        if ws_url:
                            try:
                                ws = websocket.create_connection(ws_url, timeout=1.5, suppress_origin=True)
                                ws.send(json.dumps({"id": 999, "method": "Page.close"}))
                                ws.close()
                            except Exception:
                                pass
                        subprocess.run(["pkill", "-9", "-f", "chromium.*--app="], check=False)
                        print("[SUPERVISOR] Closed external app cleanly upon user exit!")
                        continue
                    if ws_url:
                        try:
                            ws = websocket.create_connection(ws_url, timeout=1.5, suppress_origin=True)
                            ws.send(json.dumps({
                                "id": 1,
                                "method": "Runtime.evaluate",
                                "params": {"expression": TOUCH_EXIT_PILL_JS},
                            }))
                            ws.close()
                        except Exception:
                            pass
            except Exception:
                pass

    t = threading.Thread(target=_supervisor_loop, daemon=True, name="ExternalAppSupervisor")
    t.start()
    print("[DAEMON] ExternalAppSupervisor started successfully!")
