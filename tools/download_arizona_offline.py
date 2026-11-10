#!/usr/bin/env python3
"""
tools/download_arizona_offline.py
High-Performance Offline Tile Seeder for the State of Arizona.
Seeds storage/map_tiles/arizona_offline.db with complete statewide coverage
from statewide overview (Zoom 0-11) through regional highways (Zoom 12)
and city streets / corridors (Zoom 13-14).
"""

import sys
import os
import math
import time
import sqlite3
import urllib.request
import concurrent.futures
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "storage" / "map_tiles" / "arizona_offline.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# User-Agent compliance
HEADERS = {
    "User-Agent": "CarPi5-Automotive-Cockpit/1.0 (https://github.com/NfgOdin/Pi5-MAIA; carpi5@local.net)"
}

def deg2num(lat_deg: float, lon_deg: float, zoom: int):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)

def init_db(conn: sqlite3.Connection):
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS map_tiles (
        style TEXT,
        z INTEGER,
        x INTEGER,
        y INTEGER,
        content_type TEXT,
        data BLOB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (style, z, x, y)
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_map_tiles ON map_tiles(style, z, x, y);")
    conn.commit()

def fetch_single_tile(item):
    style, z, x, y = item
    url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = resp.read()
                if data and len(data) > 64:
                    return (style, z, x, y, "image/png", data)
        except Exception:
            time.sleep(0.3 * (attempt + 1))
    return None

def generate_tile_list(max_zoom: int = 12, include_phoenix_detailed: bool = True):
    # Arizona Statewide Bounding Box
    min_lon, min_lat = -114.82, 31.33
    max_lon, max_lat = -109.04, 37.01

    tiles = set()

    # Statewide zooms
    for z in range(0, max_zoom + 1):
        x_min, y_max = deg2num(min_lat, min_lon, z)
        x_max, y_min = deg2num(max_lat, max_lon, z)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tiles.add(("streets", z, x, y))

    # Detailed Zoom 13 & 14 for Phoenix Metro / Local Driving
    if include_phoenix_detailed:
        # Valley of the Sun bounding box: [min_lon, min_lat, max_lon, max_lat]
        phx_min_lon, phx_min_lat = -112.45, 33.25
        phx_max_lon, phx_max_lat = -111.65, 33.75
        for z in [13, 14]:
            x_min, y_max = deg2num(phx_min_lat, phx_min_lon, z)
            x_max, y_min = deg2num(phx_max_lat, phx_max_lon, z)
            for x in range(x_min, x_max + 1):
                for y in range(y_min, y_max + 1):
                    tiles.add(("streets", z, x, y))

    return list(tiles)

def main():
    print(f"=== CarPi5 Arizona Offline Tile Seeder ===")
    print(f"Target SQLite Archive: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    # Check already cached tiles to skip
    existing = set()
    cursor = conn.cursor()
    cursor.execute("SELECT style, z, x, y FROM map_tiles WHERE style='streets'")
    for row in cursor.fetchall():
        existing.add((row[0], row[1], row[2], row[3]))
    print(f"Already cached in database: {len(existing):,} tiles")

    # Generate full Arizona tile target list (Zoom 0-12 statewide + Zoom 13-14 Phoenix)
    target_tiles = generate_tile_list(max_zoom=12, include_phoenix_detailed=True)
    needed = [t for t in target_tiles if t not in existing]
    print(f"Total target tiles for Arizona: {len(target_tiles):,}")
    print(f"Tiles needed to download: {len(needed):,}")

    if not needed:
        print("All target Arizona tiles are already downloaded and cached!")
        conn.close()
        return

    # Download in parallel using ThreadPoolExecutor
    batch_size = 50
    downloaded_count = 0
    start_time = time.time()

    print(f"Starting parallel download with 8 workers...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for i in range(0, len(needed), batch_size):
            batch = needed[i:i + batch_size]
            results = list(executor.map(fetch_single_tile, batch))
            
            # Commit batch to SQLite
            valid_results = [r for r in results if r is not None]
            if valid_results:
                conn.executemany(
                    "INSERT OR REPLACE INTO map_tiles (style, z, x, y, content_type, data) VALUES (?, ?, ?, ?, ?, ?)",
                    valid_results
                )
                conn.commit()
                downloaded_count += len(valid_results)

            elapsed = time.time() - start_time
            rate = downloaded_count / elapsed if elapsed > 0 else 0
            pct = ((i + len(batch)) / len(needed)) * 100
            print(f"[{pct:5.1f}%] Downloaded: {downloaded_count:,} / {len(needed):,} tiles ({rate:.1f} tiles/sec)")
            time.sleep(0.05) # Polite throttle to upstream volunteer OSM servers

    total_time = time.time() - start_time
    total_in_db = conn.execute("SELECT count(*) FROM map_tiles").fetchone()[0]
    db_size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    conn.close()

    print(f"\n✅ Arizona Offline Map Download Completed!")
    print(f"Downloaded {downloaded_count:,} new tiles in {total_time:.1f}s.")
    print(f"Total tiles in arizona_offline.db: {total_in_db:,}")
    print(f"Archive file size: {db_size_mb:.2f} MB")

if __name__ == "__main__":
    main()
