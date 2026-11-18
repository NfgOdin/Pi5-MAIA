#!/usr/bin/env python3
"""
tools/build_az_nav_db.py - Offline Arizona OSM PBF -> SQLite Navigation & Speed-Limit Compiler.

Zero external native dependencies (pure Python stdlib protobuf + zlib + sqlite3 FTS5).
Compiles Geofabrik `arizona-latest.osm.pbf` into `storage/map_tiles/arizona_nav_graph.db`:
  - `nav_meta`: build metadata & counts
  - `nav_nodes`: routing intersection vertices `(id, lat, lon, cell_key)`
  - `nav_edges`: directed road segments `(u, v, way_id, name, highway, maxspeed_mph, maxspeed_source, length_m, cost_sec, geom_json, cell_key)`
  - `nav_edge_cells`: spatial grid index mapping `(cell_key -> edge_id)` across segment bounding boxes
  - `nav_places_fts`: SQLite FTS5 index of street names, towns, and POIs for offline search
"""

import argparse
import json
import math
import os
import sqlite3
import struct
import sys
import time
import urllib.request
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PBF_URL = "https://download.geofabrik.de/north-america/us/arizona-latest.osm.pbf"
DEFAULT_PBF_PATH = BASE_DIR / "storage" / "map_tiles" / "arizona-latest.osm.pbf"
DEFAULT_DB_PATH = BASE_DIR / "storage" / "map_tiles" / "arizona_nav_graph.db"

DRIVABLE_HIGHWAYS: Dict[str, int] = {
    "motorway": 75,
    "motorway_link": 45,
    "trunk": 65,
    "trunk_link": 45,
    "primary": 55,
    "primary_link": 40,
    "secondary": 45,
    "secondary_link": 35,
    "tertiary": 35,
    "tertiary_link": 30,
    "unclassified": 35,
    "residential": 25,
    "living_street": 15,
    "service": 15,
}

SEARCHABLE_POI_KEYS = ("amenity", "shop", "tourism", "leisure", "place", "aeroway")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 coordinates in meters."""
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def cell_key_for(lat: float, lon: float) -> str:
    """~1.1 km spatial bucket key used for fast SQLite B-tree spatial indexing."""
    return f"{int(math.floor(lat * 100.0))}:{int(math.floor(lon * 100.0))}"


def parse_maxspeed_mph(raw_speed: Optional[str], highway: str) -> Tuple[int, str]:
    """Parse OSM `maxspeed` tags cleanly or fall back to documented road-class limit."""
    default_mph = DRIVABLE_HIGHWAYS.get(highway, 35)
    if not raw_speed:
        return default_mph, "highway_default"
    text = str(raw_speed).strip().lower()
    digits = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            digits += ch
        elif digits:
            break
    if not digits:
        return default_mph, "highway_default"
    try:
        val = float(digits)
    except ValueError:
        return default_mph, "highway_default"
    if "mph" in text or ("km" not in text and "kph" not in text):
        mph = int(round(val))
    else:
        mph = int(round(val * 0.621371))
    mph = max(5, min(85, mph))
    return mph, "osm_tag"


# --- Minimal Pure-Python Protobuf / OSM PBF Wire Reader ---

def _read_varint(buf: memoryview, pos: int) -> Tuple[int, int]:
    shift = 0
    val = 0
    while True:
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, pos
        shift += 7


def _read_svarint(buf: memoryview, pos: int) -> Tuple[int, int]:
    u, pos = _read_varint(buf, pos)
    return (u >> 1) ^ -(u & 1), pos


def _iter_fields(buf: memoryview) -> Iterable[Tuple[int, int, Any]]:
    pos = 0
    end = len(buf)
    while pos < end:
        tag, pos = _read_varint(buf, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:
            val, pos = _read_varint(buf, pos)
            yield field_num, wire_type, val
        elif wire_type == 1:
            val = struct.unpack_from("<Q", buf, pos)[0]
            pos += 8
            yield field_num, wire_type, val
        elif wire_type == 2:
            length, pos = _read_varint(buf, pos)
            yield field_num, wire_type, buf[pos:pos + length]
            pos += length
        elif wire_type == 5:
            val = struct.unpack_from("<I", buf, pos)[0]
            pos += 4
            yield field_num, wire_type, val
        else:
            raise ValueError(f"Unsupported protobuf wire_type={wire_type}")


def _decode_stringtable(buf: memoryview) -> List[str]:
    strings: List[str] = []
    for fnum, wtype, val in _iter_fields(buf):
        if fnum == 1 and wtype == 2:
            strings.append(bytes(val).decode("utf-8", errors="replace"))
    return strings


def _decode_blob(buf: memoryview) -> bytes:
    raw_bytes: Optional[bytes] = None
    zlib_bytes: Optional[bytes] = None
    for fnum, wtype, val in _iter_fields(buf):
        if fnum == 1 and wtype == 2:
            raw_bytes = bytes(val)
        elif fnum == 3 and wtype == 2:
            zlib_bytes = bytes(val)
    if raw_bytes is not None:
        return raw_bytes
    if zlib_bytes is not None:
        return zlib.decompress(zlib_bytes)
    raise ValueError("Unsupported OSM Blob compression (expected raw or zlib)")


def _iter_pbf_blocks(pbf_path: Path) -> Iterable[Tuple[str, memoryview]]:
    with open(pbf_path, "rb") as f:
        while True:
            hdr_len_bytes = f.read(4)
            if not hdr_len_bytes:
                break
            hdr_len = struct.unpack(">I", hdr_len_bytes)[0]
            hdr_buf = memoryview(f.read(hdr_len))
            block_type = ""
            datasize = 0
            for fnum, wtype, val in _iter_fields(hdr_buf):
                if fnum == 1 and wtype == 2:
                    block_type = bytes(val).decode("ascii", errors="replace")
                elif fnum == 3 and wtype == 0:
                    datasize = int(val)
            blob_buf = memoryview(f.read(datasize))
            payload = _decode_blob(blob_buf)
            yield block_type, memoryview(payload)


def _decode_ways_from_group(group_buf: memoryview, strings: List[str]) -> List[Dict[str, Any]]:
    ways: List[Dict[str, Any]] = []
    for fnum, wtype, val in _iter_fields(group_buf):
        if fnum != 3 or wtype != 2:
            continue
        way_id = 0
        keys: List[int] = []
        vals: List[int] = []
        refs: List[int] = []
        for wf, wt, wv in _iter_fields(val):
            if wf == 1 and wt == 0:
                way_id = int(wv)
            elif wf == 2 and wt == 2:
                pos = 0
                while pos < len(wv):
                    k, pos = _read_varint(wv, pos)
                    keys.append(k)
            elif wf == 3 and wt == 2:
                pos = 0
                while pos < len(wv):
                    v, pos = _read_varint(wv, pos)
                    vals.append(v)
            elif wf == 8 and wt == 2:
                pos = 0
                cur_ref = 0
                while pos < len(wv):
                    delta, pos = _read_svarint(wv, pos)
                    cur_ref += delta
                    refs.append(cur_ref)
        tags = {strings[k]: strings[v] for k, v in zip(keys, vals) if k < len(strings) and v < len(strings)}
        hw = tags.get("highway", "")
        if hw in DRIVABLE_HIGHWAYS and len(refs) >= 2:
            ways.append({"id": way_id, "tags": tags, "refs": refs})
    return ways


def _decode_dense_nodes_and_pois(
    group_buf: memoryview,
    strings: List[str],
    granularity: int,
    lat_offset: int,
    lon_offset: int,
    needed_nodes: Set[int],
    node_coords: Dict[int, Tuple[float, float]],
    places: List[Dict[str, Any]],
) -> None:
    for fnum, wtype, val in _iter_fields(group_buf):
        if fnum == 1 and wtype == 2:
            nid = 0
            nlat = 0.0
            nlon = 0.0
            keys: List[int] = []
            vals: List[int] = []
            for nf, nt, nv in _iter_fields(val):
                if nf == 1 and nt == 0:
                    nid = int(nv)
                elif nf == 8 and nt == 0:
                    sv = (nv >> 1) ^ -(nv & 1)
                    nlat = 1e-9 * (lat_offset + granularity * sv)
                elif nf == 9 and nt == 0:
                    sv = (nv >> 1) ^ -(nv & 1)
                    nlon = 1e-9 * (lon_offset + granularity * sv)
                elif nf == 10 and nt == 2:
                    pos = 0
                    while pos < len(nv):
                        k, pos = _read_varint(nv, pos)
                        keys.append(k)
                elif nf == 11 and nt == 2:
                    pos = 0
                    while pos < len(nv):
                        v, pos = _read_varint(nv, pos)
                        vals.append(v)
            if nid in needed_nodes:
                node_coords[nid] = (nlat, nlon)
            if keys:
                tags = {strings[k]: strings[v] for k, v in zip(keys, vals) if k < len(strings) and v < len(strings)}
                name = tags.get("name", "").strip()
                if name and any(k in tags for k in SEARCHABLE_POI_KEYS):
                    cat = next((f"{k}:{tags[k]}" for k in SEARCHABLE_POI_KEYS if k in tags), "poi")
                    places.append({
                        "name": name,
                        "kind": "poi",
                        "category": cat,
                        "lat": nlat,
                        "lon": nlon,
                        "subtitle": tags.get("addr:city") or tags.get("place") or cat.split(":")[-1].replace("_", " ").title(),
                    })
        elif fnum == 2 and wtype == 2:
            ids_buf = lats_buf = lons_buf = kv_buf = memoryview(b"")
            for df, dt, dv in _iter_fields(val):
                if df == 1 and dt == 2:
                    ids_buf = dv
                elif df == 8 and dt == 2:
                    lats_buf = dv
                elif df == 9 and dt == 2:
                    lons_buf = dv
                elif df == 10 and dt == 2:
                    kv_buf = dv

            pid = plat = plon = 0
            pos_id = pos_lat = pos_lon = pos_kv = 0
            len_kv = len(kv_buf)
            while pos_id < len(ids_buf):
                did, pos_id = _read_svarint(ids_buf, pos_id)
                dlat, pos_lat = _read_svarint(lats_buf, pos_lat)
                dlon, pos_lon = _read_svarint(lons_buf, pos_lon)
                pid += did
                plat += dlat
                plon += dlon
                lat = 1e-9 * (lat_offset + granularity * plat)
                lon = 1e-9 * (lon_offset + granularity * plon)

                tags: Dict[str, str] = {}
                if pos_kv < len_kv:
                    while pos_kv < len_kv:
                        k, pos_kv = _read_varint(kv_buf, pos_kv)
                        if k == 0:
                            break
                        v, pos_kv = _read_varint(kv_buf, pos_kv)
                        if k < len(strings) and v < len(strings):
                            tags[strings[k]] = strings[v]

                if pid in needed_nodes:
                    node_coords[pid] = (lat, lon)
                if tags:
                    name = tags.get("name", "").strip()
                    if name and any(k in tags for k in SEARCHABLE_POI_KEYS):
                        cat = next((f"{k}:{tags[k]}" for k in SEARCHABLE_POI_KEYS if k in tags), "poi")
                        places.append({
                            "name": name,
                            "kind": "poi",
                            "category": cat,
                            "lat": lat,
                            "lon": lon,
                            "subtitle": tags.get("addr:city") or tags.get("place") or cat.split(":")[-1].replace("_", " ").title(),
                        })


def init_nav_schema(conn: sqlite3.Connection) -> None:
    """Create indexed SQLite schema for offline routing, road-snapping, and FTS5 search."""
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.executescript("""
    DROP TABLE IF EXISTS nav_edge_cells;
    DROP TABLE IF EXISTS nav_edges;
    DROP TABLE IF EXISTS nav_nodes;
    DROP TABLE IF EXISTS nav_places_fts;
    DROP TABLE IF EXISTS nav_meta;

    CREATE TABLE nav_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE nav_nodes (
        id INTEGER PRIMARY KEY,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        cell_key TEXT NOT NULL
    );
    CREATE INDEX idx_nav_nodes_cell ON nav_nodes(cell_key);

    CREATE TABLE nav_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        u INTEGER NOT NULL,
        v INTEGER NOT NULL,
        way_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        highway TEXT NOT NULL,
        maxspeed_mph INTEGER NOT NULL,
        maxspeed_source TEXT NOT NULL,
        length_m REAL NOT NULL,
        speed_mps REAL NOT NULL,
        cost_sec REAL NOT NULL,
        geom_json TEXT NOT NULL,
        cell_key TEXT NOT NULL
    );
    CREATE INDEX idx_nav_edges_u ON nav_edges(u);
    CREATE INDEX idx_nav_edges_cell ON nav_edges(cell_key);

    CREATE TABLE nav_edge_cells (
        cell_key TEXT NOT NULL,
        edge_id INTEGER NOT NULL,
        PRIMARY KEY (cell_key, edge_id)
    ) WITHOUT ROWID;

    CREATE VIRTUAL TABLE nav_places_fts USING fts5(
        name,
        kind,
        category,
        subtitle,
        lat UNINDEXED,
        lon UNINDEXED,
        tokenize='unicode61'
    );
    """)


def build_graph_from_ways(
    node_coords: Dict[int, Tuple[float, float]],
    ways: List[Dict[str, Any]],
    places: Optional[List[Dict[str, Any]]],
    db_path: Path,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    source_label: str = "osm_pbf",
) -> Dict[str, int]:
    """
    Compile `(node_coords, ways, places)` into `arizona_nav_graph.db` with true intersections,
    directional edges, shape polylines, spatial grid index, and FTS5 searchable places.
    `bbox`, if provided, is `(min_lat, min_lon, max_lat, max_lon)`.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = db_path.with_suffix(".db.tmp")
    if tmp_db.exists():
        tmp_db.unlink()

    ref_counts: Dict[int, int] = defaultdict(int)
    filtered_ways: List[Dict[str, Any]] = []
    for w in ways:
        refs = [nid for nid in w.get("refs", []) if nid in node_coords]
        if len(refs) < 2:
            continue
        if bbox is not None:
            min_lat, min_lon, max_lat, max_lon = bbox
            if not any(min_lat <= node_coords[nid][0] <= max_lat and min_lon <= node_coords[nid][1] <= max_lon for nid in refs):
                continue
        tags = w.get("tags", {})
        hw = tags.get("highway", "")
        if hw not in DRIVABLE_HIGHWAYS:
            continue
        filtered_ways.append({"id": int(w.get("id", 0)), "tags": tags, "refs": refs})
        ref_counts[refs[0]] += 2  # endpoints are always graph vertices
        ref_counts[refs[-1]] += 2
        for nid in refs[1:-1]:
            ref_counts[nid] += 1

    intersection_ids: Set[int] = {nid for nid, cnt in ref_counts.items() if cnt >= 2}

    conn = sqlite3.connect(str(tmp_db))
    init_nav_schema(conn)

    # Insert intersection vertices
    node_rows = []
    for nid in intersection_ids:
        lat, lon = node_coords[nid]
        node_rows.append((nid, round(lat, 6), round(lon, 6), cell_key_for(lat, lon)))
    conn.executemany("INSERT INTO nav_nodes (id, lat, lon, cell_key) VALUES (?, ?, ?, ?)", node_rows)

    edge_count = 0
    street_places_seen: Set[Tuple[str, str]] = set()
    derived_places: List[Tuple[str, str, str, str, float, float]] = []

    edge_batch: List[Tuple[Any, ...]] = []
    cell_batch: List[Tuple[str, int]] = []
    next_edge_id = 1

    def _emit_directed_edge(
        u: int,
        v: int,
        way_id: int,
        name: str,
        highway: str,
        maxspeed_mph: int,
        speed_source: str,
        coords_seg: List[Tuple[float, float]],
    ) -> None:
        nonlocal next_edge_id, edge_count
        if len(coords_seg) < 2:
            return
        total_len = 0.0
        for idx in range(len(coords_seg) - 1):
            total_len += haversine_m(coords_seg[idx][0], coords_seg[idx][1], coords_seg[idx + 1][0], coords_seg[idx + 1][1])
        total_len = max(1.0, total_len)
        speed_mps = max(3.0, maxspeed_mph * 0.44704)
        cost_sec = total_len / speed_mps
        mid_lat, mid_lon = coords_seg[len(coords_seg) // 2]
        ckey = cell_key_for(mid_lat, mid_lon)
        geom_json = json.dumps([[round(pt[0], 6), round(pt[1], 6)] for pt in coords_seg], separators=(",", ":"))
        edge_id = next_edge_id
        next_edge_id += 1
        edge_count += 1
        edge_batch.append((
            edge_id,
            u,
            v,
            way_id,
            name,
            highway,
            maxspeed_mph,
            speed_source,
            round(total_len, 2),
            round(speed_mps, 2),
            round(cost_sec, 2),
            geom_json,
            ckey,
        ))

        lats = [p[0] for p in coords_seg]
        lons = [p[1] for p in coords_seg]
        c_lat0 = int(math.floor(min(lats) * 100.0))
        c_lat1 = int(math.floor(max(lats) * 100.0))
        c_lon0 = int(math.floor(min(lons) * 100.0))
        c_lon1 = int(math.floor(max(lons) * 100.0))
        # Cap span against corrupt outlier edges
        if (c_lat1 - c_lat0) <= 20 and (c_lon1 - c_lon0) <= 20:
            for clat in range(c_lat0, c_lat1 + 1):
                for clon in range(c_lon0, c_lon1 + 1):
                    cell_batch.append((f"{clat}:{clon}", edge_id))
        else:
            cell_batch.append((ckey, edge_id))

    for w in filtered_ways:
        tags = w["tags"]
        hw = tags["highway"]
        way_id = w["id"]
        name = (tags.get("name") or tags.get("ref") or hw.replace("_", " ").title()).strip()
        maxspeed_mph, speed_source = parse_maxspeed_mph(tags.get("maxspeed"), hw)
        oneway = str(tags.get("oneway", "")).strip().lower()
        is_roundabout = tags.get("junction", "").strip().lower() in ("roundabout", "circular")
        refs = w["refs"]

        # Split way into sub-chains at intersection vertices
        seg_start_idx = 0
        for i in range(1, len(refs)):
            if refs[i] in intersection_ids or i == len(refs) - 1:
                sub_refs = refs[seg_start_idx:i + 1]
                u = sub_refs[0]
                v = sub_refs[-1]
                coords_seg = [node_coords[nid] for nid in sub_refs]
                if oneway == "-1":
                    _emit_directed_edge(v, u, way_id, name, hw, maxspeed_mph, speed_source, list(reversed(coords_seg)))
                elif oneway in ("yes", "true", "1") or is_roundabout or hw in ("motorway", "motorway_link"):
                    _emit_directed_edge(u, v, way_id, name, hw, maxspeed_mph, speed_source, coords_seg)
                else:
                    _emit_directed_edge(u, v, way_id, name, hw, maxspeed_mph, speed_source, coords_seg)
                    _emit_directed_edge(v, u, way_id, name, hw, maxspeed_mph, speed_source, list(reversed(coords_seg)))
                seg_start_idx = i

        if name and name != hw.replace("_", " ").title():
            mid_pt = node_coords[refs[len(refs) // 2]]
            dedupe_key = (name.lower(), cell_key_for(mid_pt[0], mid_pt[1]))
            if dedupe_key not in street_places_seen:
                street_places_seen.add(dedupe_key)
                derived_places.append((
                    name,
                    "road",
                    hw,
                    f"{maxspeed_mph} MPH {hw.replace('_', ' ').title()}",
                    round(mid_pt[0], 6),
                    round(mid_pt[1], 6),
                ))

        if len(edge_batch) >= 20000:
            conn.executemany(
                "INSERT INTO nav_edges (id, u, v, way_id, name, highway, maxspeed_mph, maxspeed_source, length_m, speed_mps, cost_sec, geom_json, cell_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                edge_batch,
            )
            conn.executemany("INSERT OR IGNORE INTO nav_edge_cells (cell_key, edge_id) VALUES (?, ?)", cell_batch)
            edge_batch.clear()
            cell_batch.clear()

    if edge_batch:
        conn.executemany(
            "INSERT INTO nav_edges (id, u, v, way_id, name, highway, maxspeed_mph, maxspeed_source, length_m, speed_mps, cost_sec, geom_json, cell_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            edge_batch,
        )
        conn.executemany("INSERT OR IGNORE INTO nav_edge_cells (cell_key, edge_id) VALUES (?, ?)", cell_batch)

    # Index POIs & streets into FTS5
    poi_rows = []
    for p in (places or []):
        if bbox is not None:
            min_lat, min_lon, max_lat, max_lon = bbox
            if not (min_lat <= p["lat"] <= max_lat and min_lon <= p["lon"] <= max_lon):
                continue
        poi_rows.append((
            p["name"],
            p.get("kind", "poi"),
            p.get("category", "poi"),
            p.get("subtitle", ""),
            round(float(p["lat"]), 6),
            round(float(p["lon"]), 6),
        ))
    all_places = poi_rows + derived_places
    conn.executemany(
        "INSERT INTO nav_places_fts (name, kind, category, subtitle, lat, lon) VALUES (?, ?, ?, ?, ?, ?)",
        all_places,
    )

    conn.executemany(
        "INSERT INTO nav_meta (key, value) VALUES (?, ?)",
        [
            ("source", source_label),
            ("built_at", str(int(time.time()))),
            ("node_count", str(len(node_rows))),
            ("edge_count", str(edge_count)),
            ("place_count", str(len(all_places))),
        ],
    )
    conn.commit()
    conn.close()

    if db_path.exists():
        db_path.unlink()
    tmp_db.replace(db_path)

    return {
        "nodes": len(node_rows),
        "edges": edge_count,
        "places": len(all_places),
    }


def compile_pbf_to_sqlite(
    pbf_path: Path,
    db_path: Path,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, int]:
    """Two-pass streaming compilation from `.osm.pbf` to `arizona_nav_graph.db`."""
    def log(msg: str):
        if progress_cb:
            progress_cb(msg)
        else:
            print(msg, flush=True)

    log(f"[NAV-BUILD] Pass 1/2: Scanning drivable OSM ways in {pbf_path.name}...")
    ways: List[Dict[str, Any]] = []
    needed_nodes: Set[int] = set()
    block_idx = 0
    for btype, payload in _iter_pbf_blocks(pbf_path):
        if btype != "OSMData":
            continue
        block_idx += 1
        strings: List[str] = []
        groups: List[memoryview] = []
        for fnum, wtype, val in _iter_fields(payload):
            if fnum == 1 and wtype == 2:
                strings = _decode_stringtable(val)
            elif fnum == 2 and wtype == 2:
                groups.append(val)
        for grp in groups:
            for w in _decode_ways_from_group(grp, strings):
                ways.append(w)
                needed_nodes.update(w["refs"])
        if block_idx % 200 == 0:
            log(f"[NAV-BUILD] Pass 1 block {block_idx}: {len(ways):,} drivable ways, {len(needed_nodes):,} nodes queued")

    log(f"[NAV-BUILD] Pass 2/2: Extracting {len(needed_nodes):,} coordinates & searchable POIs...")
    node_coords: Dict[int, Tuple[float, float]] = {}
    places: List[Dict[str, Any]] = []
    block_idx = 0
    for btype, payload in _iter_pbf_blocks(pbf_path):
        if btype != "OSMData":
            continue
        block_idx += 1
        strings = []
        groups = []
        granularity = 100
        lat_offset = 0
        lon_offset = 0
        for fnum, wtype, val in _iter_fields(payload):
            if fnum == 1 and wtype == 2:
                strings = _decode_stringtable(val)
            elif fnum == 2 and wtype == 2:
                groups.append(val)
            elif fnum == 17 and wtype == 0:
                granularity = int(val)
            elif fnum == 19 and wtype == 0:
                lat_offset = int(val)
            elif fnum == 20 and wtype == 0:
                lon_offset = int(val)
        for grp in groups:
            _decode_dense_nodes_and_pois(
                grp, strings, granularity, lat_offset, lon_offset, needed_nodes, node_coords, places
            )
        if block_idx % 200 == 0:
            log(f"[NAV-BUILD] Pass 2 block {block_idx}: {len(node_coords):,} coords, {len(places):,} POIs")

    log(f"[NAV-BUILD] Compiling SQLite road graph & FTS5 index -> {db_path}...")
    stats = build_graph_from_ways(
        node_coords,
        ways,
        places,
        db_path,
        bbox=bbox,
        source_label=pbf_path.name,
    )
    log(f"[NAV-BUILD] Complete! Nodes={stats['nodes']:,}, Edges={stats['edges']:,}, Places={stats['places']:,}")
    return stats


def download_pbf(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".pbf.part")
    print(f"[NAV-BUILD] Downloading {url} -> {dest} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "CarPi5-NavBuilder/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last_pct = -5
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total > 0:
                pct = int((done / total) * 100)
                if pct >= last_pct + 10:
                    last_pct = pct
                    print(f"[NAV-BUILD] Download {pct}% ({done // (1024*1024)} / {total // (1024*1024)} MB)", flush=True)
    if dest.exists():
        dest.unlink()
    tmp.replace(dest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile Geofabrik Arizona OSM PBF to CarPi5 SQLite nav graph.")
    parser.add_argument("--pbf", type=Path, default=DEFAULT_PBF_PATH, help="Input .osm.pbf file path")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Output SQLite DB path")
    parser.add_argument("--url", type=str, default=DEFAULT_PBF_URL, help="PBF download URL if --download is set")
    parser.add_argument("--download", action="store_true", help="Download Geofabrik PBF if missing")
    parser.add_argument("--bbox", type=str, default="", help="Optional filter min_lat,min_lon,max_lat,max_lon")
    args = parser.parse_args()

    bbox_tuple = None
    if args.bbox:
        parts = [float(x.strip()) for x in args.bbox.split(",")]
        if len(parts) != 4:
            print("Invalid --bbox format. Expected: min_lat,min_lon,max_lat,max_lon", file=sys.stderr)
            return 2
        bbox_tuple = (parts[0], parts[1], parts[2], parts[3])

    if args.download and not args.pbf.exists():
        download_pbf(args.url, args.pbf)
    if not args.pbf.exists():
        print(f"[NAV-BUILD] Missing PBF file: {args.pbf}. Re-run with --download to fetch from Geofabrik.", file=sys.stderr)
        return 1

    compile_pbf_to_sqlite(args.pbf, args.db, bbox=bbox_tuple)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
