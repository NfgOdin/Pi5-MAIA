"""HTTP route handlers for 3D VRM/VRMA/BVH/props assets, storage static files, and Pi 3 dashcam proxy."""

import getpass
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request
from typing import Any
from urllib.parse import parse_qs

from routes import read_json_body, send_bytes, send_json


def _base_dir(state: Any) -> Path:
    return Path(getattr(state, "base_dir", Path(__file__).resolve().parent.parent.parent))


def _proxy_dashcam(handler: Any, parsed: Any, state: Any) -> bool:
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
        req = urllib.request.Request(target_url)
        resp = urllib.request.urlopen(req, timeout=10)
        ctype = resp.headers.get("Content-Type", "application/octet-stream")
        handler.send_response(resp.status)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Access-Control-Allow-Origin", "*")
        if "multipart" in ctype:
            handler.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            handler.send_header("Pragma", "no-cache")
            handler.end_headers()
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                handler.wfile.write(chunk)
                handler.wfile.flush()
        else:
            data = resp.read()
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
        resp.close()
    except Exception as e:
        state.pi3_host_last_check = 0
        try:
            send_json(handler, {"error": "Pi 3 dashcam unreachable", "details": str(e)}, status=502)
        except Exception:
            pass
    return True


def _content_type_for_storage(suffix: str) -> str:
    suf = suffix.lower()
    if suf == ".pdf":
        return "application/pdf"
    if suf in (".md", ".txt", ".obj", ".mtl"):
        return "text/plain; charset=utf-8"
    if suf == ".gltf":
        return "model/gltf+json"
    if suf == ".glb":
        return "model/gltf-binary"
    if suf in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suf == ".png":
        return "image/png"
    if suf in (".mp4", ".mkv"):
        return "video/mp4"
    return "application/octet-stream"


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle dashcam proxy, 3D model/animation/prop endpoints, and /storage static file GET requests."""
    path = parsed.path
    base_dir = _base_dir(state)

    if path.startswith("/api/dashcam/") or path.startswith("/dashcam/"):
        return _proxy_dashcam(handler, parsed, state)

    if path == "/api/models/avatars":
        avatar_dir = base_dir / "models" / "avatars"
        vrm_files = []
        if avatar_dir.exists():
            for f in avatar_dir.glob("*.vrm"):
                vrm_files.append({
                    "name": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "url": f"/api/models/vrm?name={urllib.parse.quote(f.name)}",
                })
        send_json(handler, vrm_files)
        return True

    if path in ("/api/models/vrm", "/api/models/vrma"):
        params = parse_qs(parsed.query)
        name = os.path.basename(params.get("name", [""])[0])

        if path == "/api/models/vrma" and not name:
            vrma_dir = base_dir / "models" / "vrma"
            found_vrma = []
            if vrma_dir.exists():
                for vf in sorted(vrma_dir.rglob("*.vrma")):
                    found_vrma.append({"name": vf.name, "action": vf.stem.lower()})
            send_json(handler, {"files": found_vrma})
            return True

        if path == "/api/models/vrma" or name.lower().endswith(".vrma"):
            vrm_path = base_dir / "models" / "vrma" / name
            if not vrm_path.exists():
                sub_vrma = list((base_dir / "models" / "vrma").rglob(name))
                if sub_vrma:
                    vrm_path = sub_vrma[0]
        else:
            vrm_path = base_dir / "models" / "avatars" / name

        if not vrm_path.exists() or not vrm_path.is_file():
            handler.send_response(404)
            handler.end_headers()
            return True

        try:
            size = vrm_path.stat().st_size
            handler.send_response(200)
            handler.send_header("Content-Type", "model/gltf-binary")
            handler.send_header("Content-Length", str(size))
            handler.send_header("Accept-Ranges", "bytes")
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            with open(vrm_path, "rb") as f_vrm:
                while True:
                    c = f_vrm.read(64 * 1024)
                    if not c:
                        break
                    handler.wfile.write(c)
        except Exception:
            pass
        return True

    if path == "/api/models/bvh":
        params = parse_qs(parsed.query)
        name = os.path.basename(params.get("name", [""])[0])
        bvh_dirs = [base_dir / "models" / "bvh", base_dir / "models" / "vrma"]
        if not name:
            found = []
            seen = set()
            for bdir in bvh_dirs:
                if bdir.exists():
                    for bf in sorted(bdir.rglob("*.bvh")):
                        if bf.name not in seen:
                            seen.add(bf.name)
                            found.append({"name": bf.name, "action": bf.stem.lower()})
            send_json(handler, {"files": found})
            return True

        bvh_path = None
        for bdir in bvh_dirs:
            cand = bdir / name
            if cand.exists():
                bvh_path = cand
                break
            sub_matches = list(bdir.rglob(name))
            if sub_matches:
                bvh_path = sub_matches[0]
                break
        if not bvh_path:
            handler.send_response(404)
            handler.end_headers()
            return True
        try:
            send_bytes(handler, bvh_path.read_bytes(), "text/plain; charset=utf-8")
        except Exception:
            pass
        return True

    if path == "/api/models/custom_props":
        props = []
        seen_names = set()
        valid_exts = {".obj", ".gltf", ".glb", ".vrm"}

        storage_props_dir = base_dir / "storage" / "models" / "props"
        if storage_props_dir.exists():
            for p in sorted(storage_props_dir.rglob("*")):
                if p.is_file() and p.suffix.lower() in valid_exts:
                    rel_path = str(p.relative_to(base_dir)).replace("\\", "/")
                    sz = p.stat().st_size
                    is_scene_entry = p.name.lower().startswith("scene.")
                    prop_name = p.parent.name.replace("_", " ").title() if is_scene_entry else p.stem.replace("_", " ").title()
                    prop_id = f"prop_storage_{p.parent.name.lower()}_{p.stem.lower()}" if is_scene_entry else f"prop_storage_{p.stem.lower()}"
                    props.append({
                        "id": prop_id,
                        "name": prop_name,
                        "filename": p.name,
                        "format": p.suffix.lower().replace(".", ""),
                        "source": "storage",
                        "size_bytes": sz,
                        "size_formatted": f"{sz / 1024:.1f} KB" if sz < 1024 * 1024 else f"{sz / (1024 * 1024):.2f} MB",
                        "url": f"/{rel_path}",
                    })
                    seen_names.add(p.name)

        env_props_dir = base_dir / "ui" / "web_preview" / "models" / "environment" / "props"
        if env_props_dir.exists():
            for p in sorted(env_props_dir.rglob("*")):
                if p.is_file() and p.suffix.lower() in valid_exts and p.name not in seen_names:
                    name = p.parent.name.replace("_", " ").title() if p.name.startswith("scene") else p.stem.replace("_", " ").title()
                    rel_path = str(p.relative_to(base_dir / "ui" / "web_preview")).replace("\\", "/")
                    sz = p.stat().st_size
                    props.append({
                        "id": f"prop_builtin_{p.parent.name.lower()}_{p.stem.lower()}",
                        "name": name,
                        "filename": p.name,
                        "format": p.suffix.lower().replace(".", ""),
                        "source": "builtin",
                        "size_bytes": sz,
                        "size_formatted": f"{sz / 1024:.1f} KB" if sz < 1024 * 1024 else f"{sz / (1024 * 1024):.2f} MB",
                        "url": rel_path,
                    })
                    seen_names.add(p.name)

        usb_roots = ["/media", "/mnt", "storage/usb_drive"] + ([f"/media/{getpass.getuser()}"] if sys.platform.startswith("linux") else [])
        for uroot in usb_roots:
            upath = (base_dir / uroot).resolve() if not os.path.isabs(uroot) else Path(uroot)
            if upath.exists():
                try:
                    for p in upath.rglob("*"):
                        if p.is_file() and p.suffix.lower() in valid_exts and p.name not in seen_names:
                            sz = p.stat().st_size
                            props.append({
                                "id": f"prop_usb_{p.stem.lower()}",
                                "name": f"{p.stem.replace('_', ' ').title()} (USB)",
                                "filename": p.name,
                                "format": p.suffix.lower().replace(".", ""),
                                "source": "usb",
                                "size_bytes": sz,
                                "size_formatted": f"{sz / 1024:.1f} KB" if sz < 1024 * 1024 else f"{sz / (1024 * 1024):.2f} MB",
                                "url": f"/api/models/usb_file?path={urllib.parse.quote(str(p))}",
                            })
                            seen_names.add(p.name)
                except Exception:
                    pass

        send_json(handler, {"status": "ok", "props": props})
        return True

    if path == "/api/models/room_layout":
        cfg_path = base_dir / "config" / "custom_room_layout.json"
        layout_data = {"version": 1, "props": []}
        if cfg_path.exists():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    layout_data = json.load(f)
            except Exception as e:
                print(f"[MODELS] Error loading custom_room_layout: {e}")
        send_json(handler, layout_data)
        return True

    if path == "/api/models/usb_file":
        file_path = parse_qs(parsed.query).get("path", [""])[0]
        target = Path(file_path).resolve()
        if target.exists() and target.is_file():
            try:
                send_bytes(handler, target.read_bytes(), _content_type_for_storage(target.suffix))
                return True
            except Exception as e:
                print(f"[MODELS] Error serving USB model file: {e}")
        handler.send_response(404)
        handler.end_headers()
        return True

    if path.startswith("/storage/"):
        rel = path.replace("/storage/", "", 1)
        storage_root = (base_dir / "storage").resolve()
        target_file = (storage_root / rel).resolve()
        if target_file.exists() and target_file.is_file() and target_file.is_relative_to(storage_root):
            try:
                send_bytes(handler, target_file.read_bytes(), _content_type_for_storage(target_file.suffix))
                return True
            except Exception as e:
                print(f"[STORAGE] Error serving file {target_file}: {e}")
        handler.send_response(404)
        handler.end_headers()
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle custom room layout POST updates."""
    if parsed.path != "/api/models/room_layout":
        return False

    base_dir = _base_dir(state)
    cfg_path = base_dir / "config" / "custom_room_layout.json"
    try:
        new_layout = read_json_body(handler)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(new_layout, f, indent=2)
        send_json(
            handler,
            {
                "status": "ok",
                "message": "Room layout saved",
                "count": len(new_layout.get("props", [])),
            },
        )
    except Exception as e:
        send_json(handler, {"status": "error", "message": str(e)}, status=500)
    return True
