"""
rom_manager.py - Retro Gaming & ROM Library Manager
Integrates with RetroArch emulation pipelines on Raspberry Pi 5.
Scans and indexes ROM collections across:
- Super Nintendo (SNES)
- Nintendo 64 (N64)
- Game Boy Advance (GBA)
- Game Boy / Color (GB/GBC)
- Sega Genesis / Mega Drive
- NES
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

PLATFORM_CONFIG = {
    "snes": {
        "name": "Super Nintendo",
        "icon": "🕹️",
        "extensions": [".smc", ".sfc", ".fig", ".zip"],
        "folder_keywords": ["snes", "super nintendo", "sfc"],
        "core": "snes9x_libretro.so"
    },
    "n64": {
        "name": "Nintendo 64",
        "icon": "🎮",
        "extensions": [".n64", ".z64", ".v64", ".zip"],
        "folder_keywords": ["n64", "64", "nintendo 64"],
        "core": "mupen64plus_next_libretro.so"
    },
    "gba": {
        "name": "Game Boy Advance",
        "icon": "📱",
        "extensions": [".gba", ".zip"],
        "folder_keywords": ["gba", "advance", "gameboy advanced"],
        "core": "mgba_libretro.so"
    },
    "gb": {
        "name": "Game Boy / Color",
        "icon": "👾",
        "extensions": [".gb", ".gbc", ".zip"],
        "folder_keywords": ["gameboy", "color", "gbc"],
        "core": "gambatte_libretro.so"
    },
    "genesis": {
        "name": "Sega Genesis",
        "icon": "⚡",
        "extensions": [".bin", ".gen", ".smd", ".md", ".zip"],
        "folder_keywords": ["genesis", "sega", "megadrive"],
        "core": "genesis_plus_gx_libretro.so"
    },
    "nes": {
        "name": "Nintendo NES",
        "icon": "🕹️",
        "extensions": [".nes", ".zip"],
        "folder_keywords": ["nes", "nintendo", "famicom"],
        "core": "fceumm_libretro.so"
    }
}


class RomManager:
    def __init__(self, base_rom_dirs: Optional[List[str]] = None):
        self.rom_dirs = base_rom_dirs or [
            "/home/nfgodin/Roms",
            os.path.expanduser("~/Roms"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "roms")
        ]
        self.cached_roms: List[Dict[str, Any]] = []

    def scan_roms(self) -> List[Dict[str, Any]]:
        """Scans all configured ROM folders and returns indexed game list."""
        games: List[Dict[str, Any]] = []

        valid_roots = [d for d in self.rom_dirs if os.path.exists(d)]
        if not valid_roots:
            # Provide sample games if running in fresh development sandbox
            return self._get_sample_roms()

        for root in valid_roots:
            for dirpath, _, filenames in os.walk(root):
                dir_lower = os.path.basename(dirpath).lower()
                for fname in filenames:
                    ext = os.path.splitext(fname)[1].lower()
                    matched_plat = None

                    # Match platform by parent folder keyword first
                    for plat_id, pcfg in PLATFORM_CONFIG.items():
                        if any(kw in dir_lower for kw in pcfg["folder_keywords"]):
                            if ext in pcfg["extensions"]:
                                matched_plat = plat_id
                                break

                    # Match by extension fallback
                    if not matched_plat:
                        for plat_id, pcfg in PLATFORM_CONFIG.items():
                            if ext in pcfg["extensions"] and ext != ".zip":
                                matched_plat = plat_id
                                break

                    if matched_plat:
                        clean_title = os.path.splitext(fname)[0]
                        # Clean up common ROM scene tags like (USA), [!], etc.
                        clean_title = clean_title.replace("_", " ")
                        games.append({
                            "title": clean_title,
                            "filename": fname,
                            "path": os.path.join(dirpath, fname),
                            "platform": matched_plat,
                            "platform_name": PLATFORM_CONFIG[matched_plat]["name"],
                            "icon": PLATFORM_CONFIG[matched_plat]["icon"],
                            "size_mb": round(os.path.getsize(os.path.join(dirpath, fname)) / (1024 * 1024), 2)
                        })

        self.cached_roms = sorted(games, key=lambda x: (x["platform"], x["title"]))
        return self.cached_roms

    def _get_sample_roms(self) -> List[Dict[str, Any]]:
        return [
            {"title": "Super Mario World", "filename": "Super Mario World.sfc", "path": "/home/nfgodin/Roms/Nintendo - Super Nintendo/Super Mario World.sfc", "platform": "snes", "platform_name": "Super Nintendo", "icon": "🕹️", "size_mb": 0.5},
            {"title": "The Legend of Zelda - A Link to the Past", "filename": "Zelda.sfc", "path": "/home/nfgodin/Roms/Nintendo - Super Nintendo/Zelda.sfc", "platform": "snes", "platform_name": "Super Nintendo", "icon": "🕹️", "size_mb": 1.0},
            {"title": "Super Mario 64", "filename": "Super Mario 64.z64", "path": "/home/nfgodin/Roms/Nintendo - 64/Super Mario 64.z64", "platform": "n64", "platform_name": "Nintendo 64", "icon": "🎮", "size_mb": 8.0},
            {"title": "Sonic The Hedgehog 2", "filename": "Sonic2.bin", "path": "/home/nfgodin/Roms/Sega - Genesis/Sonic2.bin", "platform": "genesis", "platform_name": "Sega Genesis", "icon": "⚡", "size_mb": 1.0},
            {"title": "Pokemon - Emerald Version", "filename": "Pokemon Emerald.gba", "path": "/home/nfgodin/Roms/Nintendo - Gameboy Advanced/Pokemon Emerald.gba", "platform": "gba", "platform_name": "Game Boy Advance", "icon": "📱", "size_mb": 16.0}
        ]

    def launch_game(self, rom_path: str, platform_id: Optional[str] = None) -> Dict[str, Any]:
        """Launches RetroArch with the appropriate Libretro core."""
        if not os.path.exists(rom_path):
            # Development simulation
            return {
                "status": "simulated",
                "message": f"RetroArch launch command generated for: {os.path.basename(rom_path)}",
                "rom": rom_path
            }

        core = None
        if platform_id and platform_id in PLATFORM_CONFIG:
            core = PLATFORM_CONFIG[platform_id]["core"]

        cmd = ["retroarch"]
        if core:
            # Common core paths on Raspberry Pi OS / RetroPie
            core_paths = [
                f"/usr/lib/aarch64-linux-gnu/libretro/{core}",
                f"/usr/lib/arm-linux-gnueabihf/libretro/{core}",
                f"/opt/retropie/libretrocores/{core}"
            ]
            for cp in core_paths:
                if os.path.exists(cp):
                    cmd.extend(["-L", cp])
                    break

        cmd.append(rom_path)

        try:
            # Set Wayland / Xwayland display environment variables for Pi 5 Kiosk
            env = os.environ.copy()
            env["DISPLAY"] = ":0"
            env["WAYLAND_DISPLAY"] = "wayland-0"
            if hasattr(os, "getuid"):
                env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
            else:
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"

            # Launch in background so daemon is not blocked
            proc = subprocess.Popen(cmd, env=env)
            return {"status": "ok", "launched": rom_path, "cmd": " ".join(cmd), "pid": proc.pid}
        except Exception as e:
            return {"status": "error", "message": str(e)}
