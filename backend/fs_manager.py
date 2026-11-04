"""
fs_manager.py - In-Car File Explorer & USB Device Manager for CarPi5
Manages USB flash drive auto-detection, file browsing, text editing,
file copying, and ROM/Media importing.
"""

import os
import sys
import time
import shutil
import string
from pathlib import Path
from typing import Dict, List, Any, Optional

BASE_DIR = Path(__file__).parent.parent
STORAGE_DIR = BASE_DIR / "storage"
SAMPLE_USB_DIR = STORAGE_DIR / "usb_drive"

def ensure_sample_usb_environment():
    """Ensure sample USB storage structure exists for immediate testing."""
    SAMPLE_USB_DIR.mkdir(parents=True, exist_ok=True)
    
    # Subdirectories
    (SAMPLE_USB_DIR / "snes_roms").mkdir(exist_ok=True)
    (SAMPLE_USB_DIR / "music").mkdir(exist_ok=True)
    (SAMPLE_USB_DIR / "videos").mkdir(exist_ok=True)
    (SAMPLE_USB_DIR / "tuning_configs").mkdir(exist_ok=True)

    # Sample files if not present
    sample_files = {
        SAMPLE_USB_DIR / "snes_roms" / "Super_Mario_World.sfc": b"\x00" * 1024,
        SAMPLE_USB_DIR / "snes_roms" / "OutRun_Arcade.sfc": b"\x00" * 1024,
        SAMPLE_USB_DIR / "music" / "Kavinsky_Nightcall.mp3": b"\x00" * 2048,
        SAMPLE_USB_DIR / "music" / "Turbo_Highway_Star.mp3": b"\x00" * 2048,
        SAMPLE_USB_DIR / "videos" / "Dart_Dyno_Pull_1.4T.mp4": b"\x00" * 4096,
        SAMPLE_USB_DIR / "tuning_configs" / "dart_1.4T_stage1_boost.cfg": (
            "# Dodge Dart 1.4L Turbo MultiAir Stage 1 Tuning Profile\n"
            "boost_target_psi=18.5\n"
            "wastegate_preload_mm=4.0\n"
            "fuel_octane_target=93\n"
            "multiair_intake_lift=dynamic\n"
            "rev_limiter_rpm=6600\n"
        ).encode("utf-8"),
        SAMPLE_USB_DIR / "tuning_configs" / "carpi5_custom_dashboard.json": (
            "{\n  \"version\": \"2.4.0\",\n  \"gauge_theme\": \"neon_cyberpunk\",\n  \"driver_title\": \"Master\",\n  \"driver_name\": \"Jonny\"\n}\n"
        ).encode("utf-8")
    }

    for path, content in sample_files.items():
        if not path.exists():
            try:
                with open(path, "wb") as f:
                    f.write(content)
            except Exception:
                pass

ensure_sample_usb_environment()

def detect_usb_drives() -> List[Dict[str, Any]]:
    """
    Detects removable USB drives on Linux (Pi 5) and Windows.
    Always includes the local sample USB drive for simulation.
    """
    drives = []

    # 1. Virtual / In-Dash Sample USB Storage
    if SAMPLE_USB_DIR.exists():
        total_b, used_b, free_b = shutil.disk_usage(SAMPLE_USB_DIR)
        drives.append({
            "id": "usb_internal",
            "name": "USB Flash Drive (Cruzer 32GB)",
            "label": "CRUZER_USB",
            "path": str(SAMPLE_USB_DIR),
            "free_gb": round(free_b / (1024**3), 1),
            "total_gb": 32.0,
            "is_removable": True,
            "status": "MOUNTED"
        })

    # 2. Windows Removable Drives Detection (D:\ through Z:\)
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path) and letter not in ("C",):
                try:
                    total_b, used_b, free_b = shutil.disk_usage(drive_path)
                    drives.append({
                        "id": f"win_drive_{letter}",
                        "name": f"Removable USB Drive ({letter}:)",
                        "label": f"DRIVE_{letter}",
                        "path": drive_path,
                        "free_gb": round(free_b / (1024**3), 1),
                        "total_gb": round(total_b / (1024**3), 1),
                        "is_removable": True,
                        "status": "MOUNTED"
                    })
                except Exception:
                    pass

    # 3. Linux (Raspberry Pi 5) USB Auto-Mounts (/media/pi/*, /media/*, /mnt/*)
    else:
        search_dirs = [Path("/media"), Path("/media/pi"), Path("/mnt")]
        for parent in search_dirs:
            if parent.exists():
                for entry in parent.iterdir():
                    if entry.is_dir() and entry.name != "pi":
                        try:
                            total_b, used_b, free_b = shutil.disk_usage(entry)
                            drives.append({
                                "id": f"linux_usb_{entry.name}",
                                "name": f"USB Storage ({entry.name})",
                                "label": entry.name,
                                "path": str(entry),
                                "free_gb": round(free_b / (1024**3), 1),
                                "total_gb": round(total_b / (1024**3), 1),
                                "is_removable": True,
                                "status": "MOUNTED"
                            })
                        except Exception:
                            pass

    return drives

def format_size(size_bytes: int) -> str:
    """Format file size in human-readable KB, MB, or GB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def get_file_type(filename: str, is_dir: bool) -> str:
    if is_dir:
        return "folder"
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".sfc", ".smc", ".nes", ".gba", ".gb", ".bin", ".iso", ".md", ".gen"):
        return "rom"
    if ext in (".mp3", ".flac", ".wav", ".m4a", ".ogg"):
        return "music"
    if ext in (".mp4", ".mkv", ".avi", ".mov"):
        return "video"
    if ext in (".cfg", ".json", ".txt", ".ini", ".log", ".py", ".sh"):
        return "text"
    return "file"

def list_directory(target_path: str) -> Dict[str, Any]:
    """List directory contents with file metadata."""
    if not target_path or not str(target_path).strip():
        p = SAMPLE_USB_DIR
    else:
        p = Path(target_path)
        if not p.exists() or not p.is_dir():
            p = SAMPLE_USB_DIR

    items = []
    try:
        for entry in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            is_directory = entry.is_dir()
            size = 0
            if not is_directory:
                try:
                    size = entry.stat().st_size
                except Exception:
                    pass

            items.append({
                "name": entry.name,
                "path": str(entry.resolve()),
                "is_dir": is_directory,
                "size_bytes": size,
                "size_str": format_size(size) if not is_directory else "",
                "type": get_file_type(entry.name, is_directory),
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.stat().st_mtime))
            })
    except Exception as e:
        print(f"[FS] Error listing directory {p}: {e}")

    # Determine parent path
    parent_path = str(p.parent.resolve()) if p.parent != p else None

    return {
        "current_path": str(p.resolve()),
        "parent_path": parent_path,
        "items": items,
        "count": len(items)
    }

def read_text_file(filepath: str) -> Dict[str, Any]:
    """Read file content as text."""
    p = Path(filepath)
    if not p.exists() or p.is_dir():
        return {"status": "error", "message": "File not found"}

    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(250000)  # Max 250KB for text editing
        return {"status": "ok", "path": str(p.resolve()), "name": p.name, "content": content}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def write_text_file(filepath: str, content: str) -> Dict[str, Any]:
    """Save content to file."""
    p = Path(filepath)
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "ok", "path": str(p.resolve()), "name": p.name}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def delete_item(filepath: str) -> Dict[str, Any]:
    """Delete a file or directory."""
    p = Path(filepath)
    if not p.exists():
        return {"status": "error", "message": "Path not found"}
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"status": "ok", "deleted": str(p)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def copy_item(src: str, dst_dir: str) -> Dict[str, Any]:
    """Copy file or directory to a destination folder."""
    src_p = Path(src)
    dst_p = Path(dst_dir)
    if not src_p.exists():
        return {"status": "error", "message": "Source does not exist"}
    if not dst_p.exists() or not dst_p.is_dir():
        return {"status": "error", "message": "Destination folder does not exist"}

    try:
        dest_target = dst_p / src_p.name
        if src_p.is_dir():
            shutil.copytree(src_p, dest_target)
        else:
            shutil.copy2(src_p, dest_target)
        return {"status": "ok", "copied_to": str(dest_target)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def create_directory(parent_path: str, folder_name: str) -> Dict[str, Any]:
    """Create a new folder."""
    p = Path(parent_path) / folder_name
    try:
        p.mkdir(parents=True, exist_ok=True)
        return {"status": "ok", "created": str(p)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
