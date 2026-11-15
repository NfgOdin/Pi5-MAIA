"""Offline SQLite, disk, and upstream tile cache for cockpit Leaflet maps."""

import logging
import sqlite3
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("carpi5")

MAP_TILE_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "map_tiles"
MAP_TILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
MAP_TILE_DB_PATH = MAP_TILE_CACHE_DIR / "arizona_offline.db"


def _get_tile_from_sqlite(style: str, z: int, x: int, y: int) -> Tuple[Optional[bytes], Optional[str]]:
    if not MAP_TILE_DB_PATH.exists():
        return None, None
    try:
        norm_style = "streets" if style in ("osm", "streets") else style
        with sqlite3.connect(str(MAP_TILE_DB_PATH), timeout=0.8, check_same_thread=False) as conn:
            row = conn.execute(
                "SELECT data, content_type FROM map_tiles WHERE (style=? OR style=?) AND z=? AND x=? AND y=?",
                (norm_style, style, z, x, y),
            ).fetchone()
            if row and row[0]:
                return row[0], row[1]
    except Exception as e:
        logger.debug(f"SQLite tile read error: {e}")
    return None, None


def get_cached_map_tile(style: str, z: int, x: int, y: int) -> Tuple[Optional[bytes], str]:
    """Return `(tile_bytes, content_type)` from SQLite archive, disk cache, or upstream proxy."""
    style = (style or "dark").lower()
    ext = "jpg" if style in ("dark", "satellite") else "png"
    content_type = "image/jpeg" if ext == "jpg" else "image/png"

    db_data, db_content_type = _get_tile_from_sqlite(style, z, x, y)
    if db_data:
        return db_data, (db_content_type or content_type)

    style_dir = MAP_TILE_CACHE_DIR / style
    style_dir.mkdir(parents=True, exist_ok=True)
    cache_file = style_dir / f"{z}_{x}_{y}.{ext}"

    if cache_file.exists():
        try:
            return cache_file.read_bytes(), content_type
        except Exception as e:
            logger.warning(f"Error reading cached tile {cache_file}: {e}")

    headers = {
        "User-Agent": "CarPi5-Automotive-Cockpit/1.0 (https://github.com/NfgOdin/Pi5-MAIA; carpi5@local.net)"
    }
    if style == "satellite":
        upstream_url = (
            f"https://server.arcgisonline.com/ArcGIS/rest/services/"
            f"World_Imagery/MapServer/tile/{z}/{y}/{x}"
        )
    elif style in ("osm", "streets"):
        upstream_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        content_type = "image/png"
    else:
        upstream_url = (
            f"https://server.arcgisonline.com/ArcGIS/rest/services/"
            f"Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        )

    try:
        req = urllib.request.Request(upstream_url, headers=headers)
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            data = resp.read()
            if data and len(data) > 64:
                try:
                    cache_file.write_bytes(data)
                except Exception as ce:
                    logger.debug(f"Failed to cache tile file: {ce}")
                try:
                    norm_style = "streets" if style in ("osm", "streets") else style
                    with sqlite3.connect(str(MAP_TILE_DB_PATH), timeout=1.0, check_same_thread=False) as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO map_tiles (style, z, x, y, content_type, data) VALUES (?, ?, ?, ?, ?, ?)",
                            (norm_style, z, x, y, content_type, data),
                        )
                except Exception:
                    pass
                return data, content_type
    except Exception as e:
        logger.debug(f"Upstream map tile fetch failed ({upstream_url}): {e}")

    return None, content_type
