"""HTTP route handlers for GPS, offline map tiles, solar ephemeris, and turn-by-turn navigation."""

from typing import Any, Optional, Tuple
from urllib.parse import parse_qs

from navigation.tile_cache import get_cached_map_tile
from routes import read_json_body, send_bytes, send_json

try:
    from solar_ephemeris import get_solar_ephemeris
except ImportError:
    from backend.solar_ephemeris import get_solar_ephemeris


def _parse_tile_coords(path: str) -> Optional[Tuple[str, int, int, int]]:
    parts = [p for p in path.split("/") if p]
    try:
        if len(parts) >= 7:
            return parts[3], int(parts[4]), int(parts[5]), int(parts[6].split(".")[0])
        if len(parts) == 6:
            return "dark", int(parts[3]), int(parts[4]), int(parts[5].split(".")[0])
    except Exception:
        return None
    return None


def _serve_map_tile(handler: Any, path: str, head_only: bool = False) -> None:
    coords = _parse_tile_coords(path)
    if coords is None:
        handler.send_error(400, "Invalid tile coordinates")
        return
    style, z, x, y = coords
    tile_data, content_type = get_cached_map_tile(style, z, x, y)
    if tile_data:
        send_bytes(
            handler,
            tile_data,
            content_type,
            status=200,
            cache_control="public, max-age=604800, immutable",
            head_only=head_only,
        )
    else:
        handler.send_error(502, "Map tile unavailable")


def handle_head(handler: Any, parsed: Any) -> bool:
    """Handle HEAD requests for cached map tiles."""
    if parsed.path.startswith("/api/maps/tiles/"):
        _serve_map_tile(handler, parsed.path, head_only=True)
        return True
    return False


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle navigation, GPS, drag status, map tile, and solar ephemeris GET requests."""
    path = parsed.path

    if path == "/api/gps":
        send_json(handler, state.gps.get_telemetry())
        return True

    if path == "/api/drag/status":
        telem = state.gps.get_telemetry() if getattr(state, "gps", None) else {}
        send_json(
            handler,
            {
                "dragy": telem.get("dragy", {}),
                "g_forces": telem.get("g_forces", {}),
                "speed_mph": telem.get("speed_mph", 0.0),
                "road_grade_pct": telem.get("road_grade_pct", 0.0),
            },
        )
        return True

    if path.startswith("/api/maps/tiles/"):
        _serve_map_tile(handler, path, head_only=False)
        return True

    if path == "/api/nav/status":
        q = parse_qs(parsed.query)
        try:
            lat = float(q.get("lat", [0.0])[0])
            lon = float(q.get("lon", [0.0])[0])
        except Exception:
            lat, lon = 0.0, 0.0
        router = getattr(state, "router", None)
        status = router.get_navigation_status(lat, lon) if router else {"is_navigating": False}
        send_json(handler, {"status": "ok", "navigation": status})
        return True

    if path == "/api/nav/bookmarks":
        router = getattr(state, "router", None)
        bms = router.get_bookmarks() if router else []
        send_json(handler, {"status": "ok", "bookmarks": bms})
        return True

    if path == "/api/nav/search":
        q = parse_qs(parsed.query)
        query_text = q.get("q", [""])[0]
        try:
            near_lat = float(q["lat"][0]) if "lat" in q else None
            near_lon = float(q["lon"][0]) if "lon" in q else None
        except Exception:
            near_lat, near_lon = None, None
        router = getattr(state, "router", None)
        if router and hasattr(router, "search_places"):
            res = router.search_places(query_text, near_lat=near_lat, near_lon=near_lon, limit=10)
        else:
            res = {"status": "error", "graph_ready": False, "results": []}
        send_json(handler, res)
        return True

    if path == "/api/nav/speed_limit":
        q = parse_qs(parsed.query)
        try:
            lat = float(q.get("lat", [33.3942])[0])
            lon = float(q.get("lon", [-110.7865])[0])
        except Exception:
            lat, lon = 33.3942, -110.7865
        router = getattr(state, "router", None)
        road_info = (
            router.speed_engine.snap_to_road(lat, lon)
            if router
            else {"road_name": "Local Road", "speed_limit_mph": 35}
        )
        send_json(handler, {"status": "ok", "speed_limit": road_info})
        return True

    if path == "/api/solar/ephemeris":
        try:
            send_json(handler, get_solar_ephemeris())
        except Exception as e:
            send_json(handler, {"status": "error", "message": str(e)}, status=500)
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle turn-by-turn navigation POST requests."""
    path = parsed.path
    if path not in ("/api/nav/route", "/api/nav/stop", "/api/nav/update"):
        return False

    req_data = read_json_body(handler)
    router = getattr(state, "router", None)
    nav_res = {"status": "ok"}

    if path == "/api/nav/route":
        s_lat = float(req_data.get("start_lat", 33.3942))
        s_lon = float(req_data.get("start_lon", -110.7865))
        d_lat = float(req_data.get("dest_lat", 33.4010))
        d_lon = float(req_data.get("dest_lon", -110.7920))
        d_name = req_data.get("dest_name", "Destination")
        if router:
            nav_res["route"] = router.calculate_route(s_lat, s_lon, d_lat, d_lon, d_name)
    elif path == "/api/nav/stop":
        if router:
            router.stop_navigation()
        nav_res["stopped"] = True
    elif path == "/api/nav/update":
        lat = float(req_data.get("lat", 0.0))
        lon = float(req_data.get("lon", 0.0))
        spd = float(req_data.get("speed", 0.0))
        if router:
            nav_res["update"] = router.update_position(lat, lon, spd)

    send_json(handler, nav_res)
    return True
