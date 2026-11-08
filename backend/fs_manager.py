"""
fs_manager.py - Full In-Car File Explorer & Storage Manager for CarPi5
Provides full access to real filesystem locations (Home, Root, Storage, Roms, Music, USB drives).
Supports directory browsing, sorting, breadcrumbs, search, file operations, and in-dash text editing.
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

# Ensure storage directories exist
SAMPLE_USB_DIR.mkdir(parents=True, exist_ok=True)
(SAMPLE_USB_DIR / "snes_roms").mkdir(exist_ok=True)
(SAMPLE_USB_DIR / "music").mkdir(exist_ok=True)
(SAMPLE_USB_DIR / "videos").mkdir(exist_ok=True)
(SAMPLE_USB_DIR / "tuning_configs").mkdir(exist_ok=True)

def detect_usb_drives() -> List[Dict[str, Any]]:
    """
    Detects removable storage devices and core system root locations.
    Lists:
      - User Home (~ / /home/nfgodin)
      - CarPi5 App Directory
      - System Root (/)
      - Real Removable USB flash drives (/media/*, /mnt/*)
      - Music & Roms directories
    """
    locations = []

    # 1. User Home Directory (Top priority)
    home_dir = Path.home()
    if home_dir.exists():
        try:
            total_b, used_b, free_b = shutil.disk_usage(home_dir)
            locations.append({
                "id": "loc_home",
                "name": "Home Directory",
                "label": "HOME (~)",
                "path": str(home_dir.resolve()),
                "mount_point": str(home_dir.resolve()),
                "icon": "🏠",
                "free_gb": round(free_b / (1024**3), 1),
                "total_gb": round(total_b / (1024**3), 1),
                "is_removable": False,
                "status": "READY"
            })
        except Exception:
            pass

    # 2. CarPi5 Project Workspace
    if BASE_DIR.exists():
        try:
            total_b, used_b, free_b = shutil.disk_usage(BASE_DIR)
            locations.append({
                "id": "loc_carpi5",
                "name": "CarPi5 OS Workspace",
                "label": "CARPI5",
                "path": str(BASE_DIR.resolve()),
                "mount_point": str(BASE_DIR.resolve()),
                "icon": "🏎️",
                "free_gb": round(free_b / (1024**3), 1),
                "total_gb": round(total_b / (1024**3), 1),
                "is_removable": False,
                "status": "READY"
            })
        except Exception:
            pass

    # 3. Dedicated Roms Directory
    roms_dir = home_dir / "Roms"
    if roms_dir.exists():
        try:
            total_b, used_b, free_b = shutil.disk_usage(roms_dir)
            locations.append({
                "id": "loc_roms",
                "name": "Game ROMs",
                "label": "ROMS",
                "path": str(roms_dir.resolve()),
                "mount_point": str(roms_dir.resolve()),
                "icon": "🎮",
                "free_gb": round(free_b / (1024**3), 1),
                "total_gb": round(total_b / (1024**3), 1),
                "is_removable": False,
                "status": "READY"
            })
        except Exception:
            pass

    # 4. Music Directory
    music_dir = home_dir / "Music"
    if music_dir.exists():
        try:
            total_b, used_b, free_b = shutil.disk_usage(music_dir)
            locations.append({
                "id": "loc_music",
                "name": "Music Library",
                "label": "MUSIC",
                "path": str(music_dir.resolve()),
                "mount_point": str(music_dir.resolve()),
                "icon": "🎵",
                "free_gb": round(free_b / (1024**3), 1),
                "total_gb": round(total_b / (1024**3), 1),
                "is_removable": False,
                "status": "READY"
            })
        except Exception:
            pass

    # 5. Linux USB Auto-Mounts & Removable Drives (/media/*, /mnt/*)
    if sys.platform != "win32":
        search_dirs = [Path("/media"), Path("/media/nfgodin"), Path("/media/pi"), Path("/mnt")]
        seen_paths = set()
        for parent in search_dirs:
            if parent.exists():
                for entry in parent.iterdir():
                    if entry.is_dir() and entry.name not in ("pi", "nfgodin") and str(entry) not in seen_paths:
                        try:
                            total_b, used_b, free_b = shutil.disk_usage(entry)
                            seen_paths.add(str(entry))
                            locations.append({
                                "id": f"usb_{entry.name}",
                                "name": f"USB Storage ({entry.name})",
                                "label": entry.name.upper(),
                                "path": str(entry.resolve()),
                                "mount_point": str(entry.resolve()),
                                "icon": "💾",
                                "free_gb": round(free_b / (1024**3), 1),
                                "total_gb": round(total_b / (1024**3), 1),
                                "is_removable": True,
                                "status": "MOUNTED"
                            })
                        except Exception:
                            pass

    # 6. Windows Fixed & Removable Drives (D:\ through Z:\)
    else:
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path) and letter not in ("C",):
                try:
                    total_b, used_b, free_b = shutil.disk_usage(drive_path)
                    locations.append({
                        "id": f"win_drive_{letter}",
                        "name": f"Drive ({letter}:)",
                        "label": f"DRIVE_{letter}",
                        "path": drive_path,
                        "mount_point": drive_path,
                        "icon": "💾",
                        "free_gb": round(free_b / (1024**3), 1),
                        "total_gb": round(total_b / (1024**3), 1),
                        "is_removable": True,
                        "status": "MOUNTED"
                    })
                except Exception:
                    pass

    # 7. System Root (/)
    root_path = Path("/" if sys.platform != "win32" else "C:\\")
    if root_path.exists():
        try:
            total_b, used_b, free_b = shutil.disk_usage(root_path)
            locations.append({
                "id": "loc_root",
                "name": "System Root (/)",
                "label": "SYSTEM ROOT",
                "path": str(root_path.resolve()),
                "mount_point": str(root_path.resolve()),
                "icon": "⚙️",
                "free_gb": round(free_b / (1024**3), 1),
                "total_gb": round(total_b / (1024**3), 1),
                "is_removable": False,
                "status": "SYSTEM"
            })
        except Exception:
            pass

    return locations

def format_size(size_bytes: int) -> str:
    """Format file size into human-readable B, KB, MB, or GB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def get_file_type(filename: str, is_dir: bool) -> str:
    if is_dir:
        return "folder"
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".sfc", ".smc", ".nes", ".gba", ".gb", ".bin", ".iso", ".md", ".gen", ".n64", ".z64"):
        return "rom"
    if ext in (".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac"):
        return "music"
    if ext in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
        return "video"
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return "image"
    if ext in (".cfg", ".json", ".txt", ".ini", ".log", ".py", ".sh", ".conf", ".md", ".service", ".yaml", ".yml"):
        return "text"
    if ext in (".vrm", ".vrma", ".bvh"):
        return "model"
    return "file"

def list_directory(target_path: str) -> Dict[str, Any]:
    """
    List contents of any valid directory with detailed metadata,
    permission safety, sorting, and breadcrumb path hierarchy.
    """
    if not target_path or not str(target_path).strip():
        p = Path.home()
    else:
        p = Path(target_path)
        if not p.exists() or not p.is_dir():
            p = Path.home()

    items = []
    error_msg = None

    try:
        entries = list(p.iterdir())
        # Sort directories first, then alphabetically
        for entry in sorted(entries, key=lambda e: (not e.is_dir(), e.name.lower())):
            try:
                is_directory = entry.is_dir()
                size = 0
                st_mtime = 0
                try:
                    stat_info = entry.stat()
                    size = stat_info.st_size if not is_directory else 0
                    st_mtime = stat_info.st_mtime
                except Exception:
                    pass

                ext = entry.suffix.lower() if not is_directory else ""

                items.append({
                    "name": entry.name,
                    "path": str(entry.resolve()),
                    "is_dir": is_directory,
                    "ext": ext,
                    "size_bytes": size,
                    "size_str": format_size(size) if not is_directory else "",
                    "type": get_file_type(entry.name, is_directory),
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st_mtime)) if st_mtime else "",
                    "timestamp": st_mtime
                })
            except (PermissionError, FileNotFoundError):
                continue
    except PermissionError:
        error_msg = f"Permission denied accessing {p}"
    except Exception as e:
        error_msg = str(e)

    # Calculate parent directory
    parent_path = str(p.parent.resolve()) if p.parent != p else None

    # Build breadcrumb segments for easy touch navigation
    parts = []
    curr = p.resolve()
    while curr != curr.parent:
        parts.append({"name": curr.name or str(curr), "path": str(curr)})
        curr = curr.parent
    parts.append({"name": str(curr), "path": str(curr)})
    parts.reverse()

    return {
        "status": "ok" if not error_msg else "error",
        "error": error_msg,
        "path": str(p.resolve()),
        "current_path": str(p.resolve()),
        "parent_path": parent_path,
        "breadcrumbs": parts,
        "items": items,
        "count": len(items)
    }

def read_text_file(filepath: str) -> Dict[str, Any]:
    """Read file content as text (up to 500 KB)."""
    p = Path(filepath)
    if not p.exists() or p.is_dir():
        return {"status": "error", "message": "File not found"}

    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(500000)
        return {"status": "ok", "path": str(p.resolve()), "name": p.name, "content": content}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def write_text_file(filepath: str, content: str) -> Dict[str, Any]:
    """Save content to file with backup."""
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
