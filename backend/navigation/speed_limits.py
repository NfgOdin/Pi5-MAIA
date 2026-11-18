"""
speed_limits.py - Offline OSM Road-Snapping & Live Posted Speed Limit Engine for CarPi5

Uses compiled SQLite OSM road graph (`storage/map_tiles/arizona_nav_graph.db` built by
`tools/build_az_nav_db.py`) with 3x3 spatial grid lookup and perpendicular segment projection.
When no offline graph database is built (and no explicit road list is supplied), faithfully
reports `graph_ready: False` / `snapped: False` with `speed_limit_mph: None` instead of fabricating.
"""

import contextlib
import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_NAV_DB_PATH = BASE_DIR / "storage" / "map_tiles" / "arizona_nav_graph.db"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two WGS84 points in meters."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r * c


def point_to_segment_distance_m(
    lat: float,
    lon: float,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
) -> float:
    """Equirectangular local tangent projection distance in meters from `(lat, lon)` to segment AB."""
    lat_scale = 111320.0
    lon_scale = max(1000.0, 111320.0 * math.cos(math.radians(lat)))
    px, py = (lon - a_lon) * lon_scale, (lat - a_lat) * lat_scale
    bx, by = (b_lon - a_lon) * lon_scale, (b_lat - a_lat) * lat_scale
    denom = bx * bx + by * by
    if denom <= 1e-6:
        return math.hypot(px, py)
    t = max(0.0, min(1.0, (px * bx + py * by) / denom))
    dx = px - t * bx
    dy = py - t * by
    return math.hypot(dx, dy)


def _neighbor_cells(lat: float, lon: float) -> List[str]:
    cy = int(math.floor(lat * 100.0))
    cx = int(math.floor(lon * 100.0))
    return [f"{cy + dy}:{cx + dx}" for dy in (-1, 0, 1) for dx in (-1, 0, 1)]


class SpeedLimitEngine:
    """Offline OSM spatial road-snapping and posted speed-limit engine."""

    def __init__(self, roads: Optional[List[Dict[str, Any]]] = None, db_path: Optional[Path] = None):
        self.roads = roads
        self.db_path = Path(db_path) if db_path else DEFAULT_NAV_DB_PATH
        self.last_warning_time = 0.0

    def is_graph_ready(self) -> bool:
        if self.roads is not None:
            return len(self.roads) > 0
        return self.db_path.exists() and self.db_path.is_file() and self.db_path.stat().st_size > 4096

    def snap_to_road(self, lat: float, lon: float, max_dist_m: float = 250.0) -> Dict[str, Any]:
        """Find closest real road segment and return its OSM road name, posted limit, and source."""
        if not lat and not lon:
            return {
                "snapped": False,
                "graph_ready": self.is_graph_ready(),
                "road_name": "GPS Fix Pending",
                "speed_limit_mph": None,
                "maxspeed_source": None,
                "road_type": None,
                "distance_to_road_m": None,
            }

        best_road: Optional[Dict[str, Any]] = None
        min_dist = float("inf")

        if self.roads is not None:
            for road in self.roads:
                pts = road["coords"]
                for i in range(len(pts) - 1):
                    d = point_to_segment_distance_m(lat, lon, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
                    if d < min_dist:
                        min_dist = d
                        best_road = road
            if best_road and min_dist <= max_dist_m:
                return {
                    "snapped": True,
                    "graph_ready": True,
                    "road_name": best_road["name"],
                    "speed_limit_mph": best_road["speed_limit_mph"],
                    "maxspeed_source": best_road.get("maxspeed_source", "osm_tag"),
                    "road_type": best_road.get("type", "road"),
                    "distance_to_road_m": round(min_dist, 1),
                }
            return {
                "snapped": False,
                "graph_ready": True,
                "road_name": "Off-Road / Unmapped",
                "speed_limit_mph": None,
                "maxspeed_source": None,
                "road_type": None,
                "distance_to_road_m": round(min_dist, 1) if min_dist != float("inf") else None,
            }

        if not self.is_graph_ready():
            return {
                "snapped": False,
                "graph_ready": False,
                "road_name": "Offline Nav DB Not Built",
                "speed_limit_mph": None,
                "maxspeed_source": None,
                "road_type": None,
                "distance_to_road_m": None,
            }

        cells = _neighbor_cells(lat, lon)
        placeholders = ",".join("?" for _ in cells)
        try:
            with contextlib.closing(sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=1.5)) as conn:
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT e.id, e.name, e.highway, e.maxspeed_mph, e.maxspeed_source, e.geom_json
                    FROM nav_edge_cells c
                    JOIN nav_edges e ON e.id = c.edge_id
                    WHERE c.cell_key IN ({placeholders})
                    """,
                    cells,
                ).fetchall()
        except Exception as e:
            return {
                "snapped": False,
                "graph_ready": False,
                "road_name": f"Nav DB Read Error ({e})",
                "speed_limit_mph": None,
                "maxspeed_source": None,
                "road_type": None,
                "distance_to_road_m": None,
            }

        for _eid, name, hw, spd_mph, spd_src, geom_json in rows:
            try:
                pts = json.loads(geom_json)
            except Exception:
                continue
            for i in range(len(pts) - 1):
                d = point_to_segment_distance_m(lat, lon, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
                if d < min_dist:
                    min_dist = d
                    best_road = {
                        "name": name,
                        "speed_limit_mph": int(spd_mph),
                        "maxspeed_source": spd_src,
                        "type": hw,
                    }

        if best_road and min_dist <= max_dist_m:
            return {
                "snapped": True,
                "graph_ready": True,
                "road_name": best_road["name"],
                "speed_limit_mph": best_road["speed_limit_mph"],
                "maxspeed_source": best_road["maxspeed_source"],
                "road_type": best_road["type"],
                "distance_to_road_m": round(min_dist, 1),
            }

        return {
            "snapped": False,
            "graph_ready": True,
            "road_name": "Off-Road / Unmapped",
            "speed_limit_mph": None,
            "maxspeed_source": None,
            "road_type": None,
            "distance_to_road_m": round(min_dist, 1) if min_dist != float("inf") else None,
        }

    def evaluate_speeding(self, current_speed_mph: float, lat: float, lon: float) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether vehicle exceeds real posted limit by >=12 MPH.
        Skips cleanly when no real road speed limit is available (`speed_limit_mph is None`).
        """
        info = self.snap_to_road(lat, lon)
        limit = info.get("speed_limit_mph")
        if not info.get("snapped") or limit is None:
            return False, None

        delta = float(current_speed_mph) - float(limit)
        now = time.time()
        if delta >= 12.0 and (now - self.last_warning_time > 120.0):
            self.last_warning_time = now
            speech = (
                f"Heads up, speed limit is {limit} here on {info['road_name']}, "
                f"and we're doing {int(current_speed_mph)}."
            )
            return True, speech
        return False, None
