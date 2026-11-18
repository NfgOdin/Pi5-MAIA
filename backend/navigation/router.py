"""
router.py - Real Offline Turn-by-Turn A* Navigation & Semantic Search Engine for CarPi5

Routes on compiled OpenStreetMap SQLite graphs (`storage/map_tiles/arizona_nav_graph.db`)
built by `tools/build_az_nav_db.py`. Zero synthetic S-curves or hardcoded turns:
when the offline graph DB is absent or coordinates cannot be reached, returns explicit
`graph_ready: False` / `error: "offline_graph_missing"` | `"no_route_found"`.
"""

import contextlib
import heapq
import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .speed_limits import DEFAULT_NAV_DB_PATH, SpeedLimitEngine, haversine_m

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BOOKMARKS_FILE = BASE_DIR / "config" / "nav_bookmarks.json"

DEFAULT_BOOKMARKS = [
    {"id": "dest_home", "name": "Home", "icon": "🏠", "address": "Globe, AZ (Historic District)", "lat": 33.3942, "lon": -110.7865, "category": "personal"},
    {"id": "dest_gas", "name": "Chevron Gas Station", "icon": "⛽", "address": "US-60 West & Russell Rd", "lat": 33.4025, "lon": -110.8150, "category": "fuel"},
    {"id": "dest_food", "name": "Safeway & Deli", "icon": "🍔", "address": "Highway 60 Shopping Center", "lat": 33.4010, "lon": -110.7920, "category": "dining"},
    {"id": "dest_pass", "name": "Pinal Mountain Scenic Pass", "icon": "🏔️", "address": "Pinal Peak Forest Highway", "lat": 33.2850, "lon": -110.8800, "category": "adventure"},
    {"id": "dest_lake", "name": "Roosevelt Lake Marina", "icon": "⛵", "address": "AZ-188 Lake Viewpoint", "lat": 33.6600, "lon": -111.1200, "category": "adventure"},
    {"id": "dest_metro", "name": "Phoenix Sky Harbor", "icon": "✈️", "address": "3400 E Sky Harbor Blvd, Phoenix", "lat": 33.4350, "lon": -112.0080, "category": "transit"},
]
BOOKMARKED_DESTINATIONS = DEFAULT_BOOKMARKS


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _turn_delta_deg(b1: float, b2: float) -> float:
    return ((b2 - b1 + 180.0) % 360.0) - 180.0


def _classify_turn(delta_deg: float, prev_hw: str, next_hw: str) -> Tuple[str, str]:
    abs_d = abs(delta_deg)
    if next_hw == "roundabout" and prev_hw != "roundabout":
        return "roundabout", "Enter roundabout"
    if abs_d < 22.0:
        return "continue", "Continue onto"
    if delta_deg < -125.0 or delta_deg > 125.0:
        return ("turn-left" if delta_deg < 0 else "turn-right"), "Make a sharp turn onto"
    if delta_deg <= -42.0:
        return "turn-left", "Turn left onto"
    if delta_deg >= 42.0:
        return "turn-right", "Turn right onto"
    if delta_deg < 0:
        return "keep-left", "Keep left onto"
    return "keep-right", "Keep right onto"


class RouteManeuver:
    """Single real turn-by-turn instruction anchored at a road transition vertex."""

    def __init__(
        self,
        maneuver_type: str,
        instruction: str,
        street_name: str,
        lat: float,
        lon: float,
        distance_m: float,
        spoken_prompt: str,
    ):
        self.maneuver_type = maneuver_type
        self.instruction = instruction
        self.street_name = street_name
        self.lat = lat
        self.lon = lon
        self.distance_m = distance_m
        self.spoken_prompt = spoken_prompt
        self.announced_500ft = False
        self.announced_now = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.maneuver_type,
            "instruction": self.instruction,
            "street": self.street_name,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "distance_m": round(self.distance_m, 1),
            "distance_ft": int(round(self.distance_m * 3.28084)),
            "spoken_prompt": self.spoken_prompt,
        }


class NavigationRouter:
    """Offline A* OSM navigation session manager, FTS5 search, and real road-snapping."""

    def __init__(self, db_path: Optional[Path] = None, bookmarks_file: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_NAV_DB_PATH
        self.bookmarks_file = Path(bookmarks_file) if bookmarks_file else BOOKMARKS_FILE
        self.speed_engine = SpeedLimitEngine(db_path=self.db_path)
        self.is_navigating = False
        self.destination_name = ""
        self.destination_coords = (0.0, 0.0)
        self.waypoints: List[List[float]] = []
        self.maneuvers: List[RouteManeuver] = []
        self.current_maneuver_index = 0
        self.total_distance_m = 0.0
        self.remaining_distance_m = 0.0
        self.estimated_duration_sec = 0
        self.start_time = 0.0
        self.last_error: Optional[str] = None
        self._audio_player = None

    def set_audio_player(self, player) -> None:
        self._audio_player = player

    def _open_ro(self):
        return contextlib.closing(sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0))

    def get_bookmarks(self) -> List[Dict[str, Any]]:
        if self.bookmarks_file.exists():
            try:
                data = json.loads(self.bookmarks_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return data
            except Exception:
                pass
        return list(DEFAULT_BOOKMARKS)

    def get_graph_status(self) -> Dict[str, Any]:
        ready = self.speed_engine.is_graph_ready()
        meta: Dict[str, str] = {}
        if ready:
            try:
                with self._open_ro() as conn:
                    meta = dict(conn.execute("SELECT key, value FROM nav_meta").fetchall())
            except Exception:
                ready = False
        return {
            "graph_ready": ready,
            "db_path": str(self.db_path),
            "node_count": int(meta.get("node_count", 0)),
            "edge_count": int(meta.get("edge_count", 0)),
            "place_count": int(meta.get("place_count", 0)),
            "source": meta.get("source", ""),
        }

    def search_places(
        self,
        query: str,
        near_lat: Optional[float] = None,
        near_lon: Optional[float] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search bookmarks and offline SQLite FTS5 Arizona streets/POIs."""
        q = (query or "").strip()
        if not q:
            return {"status": "ok", "graph_ready": self.speed_engine.is_graph_ready(), "results": self.get_bookmarks()[:limit]}

        results: List[Dict[str, Any]] = []
        ql = q.lower()
        for b in self.get_bookmarks():
            hay = f"{b.get('name', '')} {b.get('address', '')} {b.get('category', '')}".lower()
            if ql in hay:
                results.append({
                    "name": b["name"],
                    "kind": "bookmark",
                    "category": b.get("category", "bookmark"),
                    "subtitle": b.get("address", "Saved Bookmark"),
                    "lat": b["lat"],
                    "lon": b["lon"],
                })

        if not self.speed_engine.is_graph_ready():
            return {
                "status": "ok" if results else "error",
                "error": None if results else "offline_graph_missing",
                "graph_ready": False,
                "results": results[:limit],
            }

        tokens = [t for t in "".join(ch if ch.isalnum() else " " for ch in q).split() if t]
        fts_query = " ".join(f"{tok}*" for tok in tokens) if tokens else q
        rows: List[Tuple[Any, ...]] = []
        try:
            with self._open_ro() as conn:
                rows = conn.execute(
                    """
                    SELECT name, kind, category, subtitle, lat, lon, bm25(nav_places_fts) AS rank
                    FROM nav_places_fts
                    WHERE nav_places_fts MATCH ?
                    ORDER BY rank
                    LIMIT 40
                    """,
                    (fts_query,),
                ).fetchall()
        except Exception:
            rows = []

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for name, kind, cat, sub, lat, lon, rank in rows:
            dist_km = 0.0
            if near_lat is not None and near_lon is not None:
                dist_km = haversine_m(near_lat, near_lon, float(lat), float(lon)) / 1000.0
            score = float(rank) + (dist_km * 0.02)
            if name.lower().startswith(ql):
                score -= 2.5
            scored.append((
                score,
                {
                    "name": name,
                    "kind": kind,
                    "category": cat,
                    "subtitle": sub,
                    "lat": float(lat),
                    "lon": float(lon),
                    "distance_miles": round(dist_km * 0.621371, 1) if (near_lat is not None and near_lon is not None) else None,
                },
            ))
        scored.sort(key=lambda item: item[0])

        seen = {(r["name"].lower(), round(r["lat"], 4), round(r["lon"], 4)) for r in results}
        for _s, item in scored:
            k = (item["name"].lower(), round(item["lat"], 4), round(item["lon"], 4))
            if k not in seen:
                seen.add(k)
                results.append(item)
            if len(results) >= limit:
                break

        return {"status": "ok", "graph_ready": True, "results": results[:limit]}

    def _find_nearest_node(self, conn: sqlite3.Connection, lat: float, lon: float) -> Optional[Tuple[int, float, float, float]]:
        cy = int(math.floor(lat * 100.0))
        cx = int(math.floor(lon * 100.0))
        for radius in (1, 3, 8, 20):
            cells = [f"{cy + dy}:{cx + dx}" for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)]
            placeholders = ",".join("?" for _ in cells)
            rows = conn.execute(
                f"SELECT id, lat, lon FROM nav_nodes WHERE cell_key IN ({placeholders})",
                cells,
            ).fetchall()
            if rows:
                best = None
                best_d = float("inf")
                for nid, nlat, nlon in rows:
                    d = haversine_m(lat, lon, float(nlat), float(nlon))
                    if d < best_d:
                        best_d = d
                        best = (int(nid), float(nlat), float(nlon), d)
                return best
        return None

    def _astar_route(
        self,
        conn: sqlite3.Connection,
        start_nid: int,
        goal_nid: int,
        goal_lat: float,
        goal_lon: float,
        max_expansions: int = 220000,
    ) -> Optional[List[Dict[str, Any]]]:
        node_cache: Dict[int, Tuple[float, float]] = {}
        edge_cache: Dict[int, List[Tuple[int, int, str, str, int, float, float]]] = {}
        loaded_cells: set = set()

        def _get_node(nid: int) -> Tuple[float, float]:
            if nid not in node_cache:
                row = conn.execute("SELECT lat, lon FROM nav_nodes WHERE id=?", (nid,)).fetchone()
                node_cache[nid] = (float(row[0]), float(row[1])) if row else (goal_lat, goal_lon)
            return node_cache[nid]

        def _fast_dist_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            dx = (lon2 - lon1) * 92800.0
            dy = (lat2 - lat1) * 111320.0
            return math.hypot(dx, dy)

        def _prefetch_cell_for(nid: int) -> None:
            if nid in edge_cache:
                return
            lat, lon = _get_node(nid)
            cy = int(math.floor(lat * 100.0))
            cx = int(math.floor(lon * 100.0))
            cells_needed = [
                f"{cy + dy}:{cx + dx}"
                for dy in (-1, 0, 1)
                for dx in (-1, 0, 1)
                if f"{cy + dy}:{cx + dx}" not in loaded_cells
            ]
            if not cells_needed:
                edge_cache.setdefault(nid, [])
                return
            loaded_cells.update(cells_needed)
            placeholders = ",".join("?" for _ in cells_needed)
            n_rows = conn.execute(
                f"SELECT id, lat, lon FROM nav_nodes WHERE cell_key IN ({placeholders})",
                cells_needed,
            ).fetchall()
            seed_ids = []
            for r_id, r_lat, r_lon in n_rows:
                ri = int(r_id)
                node_cache[ri] = (float(r_lat), float(r_lon))
                if ri not in edge_cache:
                    edge_cache[ri] = []
                    seed_ids.append(ri)
            for i in range(0, len(seed_ids), 400):
                batch = seed_ids[i:i + 400]
                bp = ",".join("?" for _ in batch)
                e_rows = conn.execute(
                    f"""
                    SELECT e.id, e.u, e.v, e.name, e.highway, e.maxspeed_mph, e.length_m, e.cost_sec, n.lat, n.lon
                    FROM nav_edges e
                    JOIN nav_nodes n ON n.id = e.v
                    WHERE e.u IN ({bp})
                    """,
                    batch,
                ).fetchall()
                for eid, u, v, name, hw, spd, length_m, cost_sec, v_lat, v_lon in e_rows:
                    vi = int(v)
                    node_cache[vi] = (float(v_lat), float(v_lon))
                    edge_cache[int(u)].append((int(eid), vi, name, hw, int(spd), float(length_m), float(cost_sec)))
            edge_cache.setdefault(nid, [])

        s_lat, s_lon = _get_node(start_nid)
        mid_route_dist = _fast_dist_m(s_lat, s_lon, goal_lat, goal_lon)
        long_trip = mid_route_dist > 12000.0
        hw_penalty_map = {
            "motorway": 1.0,
            "motorway_link": 1.05,
            "trunk": 1.0,
            "trunk_link": 1.05,
            "primary": 1.05,
            "primary_link": 1.1,
            "secondary": 1.25,
            "secondary_link": 1.3,
            "tertiary": 1.85,
            "tertiary_link": 1.9,
            "unclassified": 3.2,
            "residential": 4.5,
            "living_street": 6.0,
            "service": 6.5,
        }

        g_score: Dict[int, float] = {start_nid: 0.0}
        came_from: Dict[int, Tuple[int, int]] = {}
        pq: List[Tuple[float, float, int]] = [((mid_route_dist / 30.0) * 1.35, 0.0, start_nid)]
        closed: set = set()
        expansions = 0

        while pq and expansions < max_expansions:
            _f, cur_g, cur = heapq.heappop(pq)
            if cur in closed:
                continue
            if cur == goal_nid:
                win_eids: List[int] = []
                walker = goal_nid
                while walker in came_from:
                    prev_u, win_eid = came_from[walker]
                    win_eids.append(win_eid)
                    walker = prev_u
                win_eids.reverse()
                if not win_eids:
                    return []
                eid_map: Dict[int, Dict[str, Any]] = {}
                for i in range(0, len(win_eids), 400):
                    batch = win_eids[i:i + 400]
                    ep = ",".join("?" for _ in batch)
                    for row in conn.execute(
                        f"SELECT id, u, v, name, highway, maxspeed_mph, length_m, cost_sec, geom_json FROM nav_edges WHERE id IN ({ep})",
                        batch,
                    ).fetchall():
                        eid_map[int(row[0])] = {
                            "u": int(row[1]),
                            "v": int(row[2]),
                            "name": row[3],
                            "highway": row[4],
                            "maxspeed_mph": int(row[5]),
                            "length_m": float(row[6]),
                            "cost_sec": float(row[7]),
                            "geom": json.loads(row[8]),
                        }
                return [eid_map[eid] for eid in win_eids if eid in eid_map]

            closed.add(cur)
            expansions += 1

            if cur not in edge_cache:
                _prefetch_cell_for(cur)

            clat, clon = node_cache.get(cur, (goal_lat, goal_lon))
            use_hier = long_trip and _fast_dist_m(clat, clon, s_lat, s_lon) > 3500.0 and _fast_dist_m(clat, clon, goal_lat, goal_lon) > 3500.0

            for eid, nxt, _name, hw, _spd, _lm, cost_sec in edge_cache.get(cur, ()):
                if nxt in closed:
                    continue
                step_cost = cost_sec * hw_penalty_map.get(hw, 2.5) if use_hier else cost_sec
                tentative_g = cur_g + step_cost
                if tentative_g < g_score.get(nxt, float("inf")):
                    g_score[nxt] = tentative_g
                    came_from[nxt] = (cur, eid)
                    nlat, nlon = _get_node(nxt)
                    h = (_fast_dist_m(nlat, nlon, goal_lat, goal_lon) / 30.0) * 1.35
                    heapq.heappush(pq, (tentative_g + h, tentative_g, nxt))

        return None

    @staticmethod
    def _build_maneuvers(edges: List[Dict[str, Any]], dest_name: str) -> List[RouteManeuver]:
        if not edges:
            return []

        def _edge_start_bearing(e: Dict[str, Any]) -> float:
            g = e["geom"]
            return _bearing_deg(g[0][0], g[0][1], g[1][0], g[1][1])

        def _edge_end_bearing(e: Dict[str, Any]) -> float:
            g = e["geom"]
            return _bearing_deg(g[-2][0], g[-2][1], g[-1][0], g[-1][1])

        maneuvers: List[RouteManeuver] = []
        first = edges[0]
        cum_dist = first["length_m"]

        # Group consecutive edges sharing the same road name & small bearing change
        pending_start_lat, pending_start_lon = first["geom"][0]
        pending_type = "depart"
        pending_instr = f"Depart on {first['name']}"
        pending_street = first["name"]

        for i in range(1, len(edges)):
            prev_e = edges[i - 1]
            cur_e = edges[i]
            delta = _turn_delta_deg(_edge_end_bearing(prev_e), _edge_start_bearing(cur_e))
            same_road = (prev_e["name"].lower() == cur_e["name"].lower())
            turn_type, verb = _classify_turn(delta, prev_e["highway"], cur_e["highway"])

            if same_road and abs(delta) < 42.0:
                cum_dist += cur_e["length_m"]
                continue

            # Emit previous leg before starting new street maneuver
            spoken = (
                f"Starting route to {dest_name}. Proceed on {pending_street}."
                if pending_type == "depart"
                else f"In 500 feet, {pending_instr.lower()}."
            )
            maneuvers.append(
                RouteManeuver(
                    maneuver_type=pending_type,
                    instruction=pending_instr,
                    street_name=pending_street,
                    lat=pending_start_lat,
                    lon=pending_start_lon,
                    distance_m=cum_dist,
                    spoken_prompt=spoken,
                )
            )
            pending_start_lat, pending_start_lon = cur_e["geom"][0]
            pending_type = "continue" if same_road else turn_type
            pending_instr = f"{verb} {cur_e['name']}"
            pending_street = cur_e["name"]
            cum_dist = cur_e["length_m"]

        spoken_last = (
            f"Starting route to {dest_name}. Proceed on {pending_street}."
            if pending_type == "depart"
            else f"In 500 feet, {pending_instr.lower()}."
        )
        maneuvers.append(
            RouteManeuver(
                maneuver_type=pending_type,
                instruction=pending_instr,
                street_name=pending_street,
                lat=pending_start_lat,
                lon=pending_start_lon,
                distance_m=cum_dist,
                spoken_prompt=spoken_last,
            )
        )

        end_lat, end_lon = edges[-1]["geom"][-1]
        maneuvers.append(
            RouteManeuver(
                maneuver_type="arrive",
                instruction=f"Arrive at {dest_name}",
                street_name=edges[-1]["name"],
                lat=end_lat,
                lon=end_lon,
                distance_m=0.0,
                spoken_prompt=f"You have arrived at {dest_name}.",
            )
        )
        return maneuvers

    def calculate_route(
        self,
        start_lat: float,
        start_lon: float,
        dest_lat: float,
        dest_lon: float,
        dest_name: str = "Destination",
    ) -> Dict[str, Any]:
        """Compute a real A* route on `arizona_nav_graph.db`; zero synthetic polylines."""
        if not self.speed_engine.is_graph_ready():
            self.stop_navigation()
            self.last_error = "offline_graph_missing"
            return {
                "status": "error",
                "error": "offline_graph_missing",
                "graph_ready": False,
                "is_navigating": False,
                "destination_name": dest_name,
                "destination_coords": (dest_lat, dest_lon),
                "message": "Offline Arizona road graph is not built yet. Run tools/build_az_nav_db.py --download.",
                "maneuvers": [],
                "polyline": [],
                "bookmarks": self.get_bookmarks(),
            }

        try:
            with self._open_ro() as conn:
                s_snap = self._find_nearest_node(conn, start_lat, start_lon)
                d_snap = self._find_nearest_node(conn, dest_lat, dest_lon)
                if not s_snap or not d_snap:
                    self.stop_navigation()
                    self.last_error = "outside_map_coverage"
                    return {
                        "status": "error",
                        "error": "outside_map_coverage",
                        "graph_ready": True,
                        "is_navigating": False,
                        "destination_name": dest_name,
                        "destination_coords": (dest_lat, dest_lon),
                        "message": "Start or destination coordinates are outside offline map road coverage.",
                        "maneuvers": [],
                        "polyline": [],
                        "bookmarks": self.get_bookmarks(),
                    }

                edges = self._astar_route(conn, s_snap[0], d_snap[0], d_snap[1], d_snap[2])
        except Exception as e:
            self.stop_navigation()
            self.last_error = f"routing_error:{e}"
            return {
                "status": "error",
                "error": "routing_error",
                "graph_ready": False,
                "is_navigating": False,
                "destination_name": dest_name,
                "message": f"Navigation routing error: {e}",
                "maneuvers": [],
                "polyline": [],
                "bookmarks": self.get_bookmarks(),
            }

        if not edges:
            self.stop_navigation()
            self.last_error = "no_route_found"
            return {
                "status": "error",
                "error": "no_route_found",
                "graph_ready": True,
                "is_navigating": False,
                "destination_name": dest_name,
                "destination_coords": (dest_lat, dest_lon),
                "message": f"No connected drivable road path found to {dest_name}.",
                "maneuvers": [],
                "polyline": [],
                "bookmarks": self.get_bookmarks(),
            }

        coords: List[List[float]] = []
        total_dist_m = 0.0
        total_sec = 0.0
        for edge in edges:
            total_dist_m += edge["length_m"]
            total_sec += edge["cost_sec"]
            for pt in edge["geom"]:
                if not coords or (abs(coords[-1][0] - pt[0]) > 1e-6 or abs(coords[-1][1] - pt[1]) > 1e-6):
                    coords.append([round(pt[0], 6), round(pt[1], 6)])

        maneuvers = self._build_maneuvers(edges, dest_name)

        self.is_navigating = True
        self.last_error = None
        self.destination_name = dest_name
        self.destination_coords = (dest_lat, dest_lon)
        self.waypoints = coords
        self.maneuvers = maneuvers
        self.current_maneuver_index = 0
        self.total_distance_m = total_dist_m
        self.remaining_distance_m = total_dist_m
        self.estimated_duration_sec = max(60, int(round(total_sec)))
        self.start_time = time.time()

        if self._audio_player:
            miles = total_dist_m * 0.000621371
            mins = max(1, int(round(total_sec / 60.0)))
            self._audio_player.speak(
                f"Route set to {dest_name}, {miles:.1f} miles, about {mins} minutes.",
                priority=1,
            )

        res = self.get_navigation_status(start_lat, start_lon)
        res["status"] = "ok"
        res["graph_ready"] = True
        return res

    def update_position(self, current_lat: float, current_lon: float, current_speed_mph: float = 0.0) -> Dict[str, Any]:
        """Advance turn-by-turn state and posted speed-limit check along active route."""
        if not self.is_navigating:
            road = self.speed_engine.snap_to_road(current_lat, current_lon)
            return {
                "is_navigating": False,
                "graph_ready": road.get("graph_ready", False),
                "current_road": road["road_name"],
                "speed_limit_mph": road["speed_limit_mph"],
                "maxspeed_source": road.get("maxspeed_source"),
                "speed_warning": None,
            }

        is_speeding, warning_speech = self.speed_engine.evaluate_speeding(current_speed_mph, current_lat, current_lon)
        if is_speeding and warning_speech and self._audio_player:
            self._audio_player.speak(warning_speech, priority=0)

        rem_m = haversine_m(current_lat, current_lon, self.destination_coords[0], self.destination_coords[1])
        self.remaining_distance_m = rem_m

        if rem_m <= 35.0:
            dest_done = self.destination_name
            self.stop_navigation()
            if self._audio_player:
                self._audio_player.speak(f"You have arrived at {dest_done}.", priority=1)
            return {
                "is_navigating": False,
                "arrived": True,
                "destination": dest_done,
            }

        if self.current_maneuver_index < len(self.maneuvers):
            current_m = self.maneuvers[self.current_maneuver_index]
            dist_to_turn = haversine_m(current_lat, current_lon, current_m.lat, current_m.lon)
            if dist_to_turn <= 160.0 and not current_m.announced_500ft:
                current_m.announced_500ft = True
                if self._audio_player:
                    self._audio_player.speak(current_m.spoken_prompt, priority=1)
            if dist_to_turn <= 25.0 and self.current_maneuver_index + 1 < len(self.maneuvers):
                self.current_maneuver_index += 1

        return self.get_navigation_status(current_lat, current_lon)

    def get_navigation_status(self, current_lat: float = 0.0, current_lon: float = 0.0) -> Dict[str, Any]:
        road = self.speed_engine.snap_to_road(current_lat, current_lon)

        current_m = None
        dist_to_next = 0.0
        if self.is_navigating and self.current_maneuver_index < len(self.maneuvers):
            m_obj = self.maneuvers[self.current_maneuver_index]
            current_m = m_obj.to_dict()
            if current_lat != 0.0 or current_lon != 0.0:
                dist_to_next = haversine_m(current_lat, current_lon, m_obj.lat, m_obj.lon)

        rem_miles = round(self.remaining_distance_m * 0.000621371, 1)
        if self.total_distance_m > 0 and self.estimated_duration_sec > 0:
            ratio = min(1.0, self.remaining_distance_m / self.total_distance_m)
            rem_mins = max(1, int(round((self.estimated_duration_sec * ratio) / 60.0))) if self.is_navigating else 0
        else:
            rem_mins = 0

        return {
            "is_navigating": self.is_navigating,
            "graph_ready": road.get("graph_ready", False),
            "last_error": self.last_error,
            "destination_name": self.destination_name,
            "destination_coords": self.destination_coords,
            "current_road": road["road_name"],
            "speed_limit_mph": road["speed_limit_mph"],
            "maxspeed_source": road.get("maxspeed_source"),
            "remaining_distance_miles": rem_miles,
            "remaining_distance_m": round(self.remaining_distance_m, 0),
            "estimated_minutes": rem_mins,
            "current_maneuver": current_m,
            "distance_to_next_turn_m": round(dist_to_next, 0),
            "distance_to_next_turn_ft": int(round(dist_to_next * 3.28084)),
            "maneuvers": [m.to_dict() for m in self.maneuvers],
            "polyline": self.waypoints,
            "bookmarks": self.get_bookmarks(),
        }

    def stop_navigation(self) -> None:
        self.is_navigating = False
        self.destination_name = ""
        self.waypoints = []
        self.maneuvers = []
        self.current_maneuver_index = 0
        self.total_distance_m = 0.0
        self.remaining_distance_m = 0.0
        self.estimated_duration_sec = 0
