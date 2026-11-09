"""
rag_memory.py - Offline Vector Memory, Semantic RAG & MultiAir Maintenance Schedule for CarPi5
Provides:
- Local 384-dimensional dense vector embeddings via quantized all-MiniLM-L6-v2 ONNX (<12ms on Pi 5)
- SQLite vector and document store with flash-wear protection (WAL + MEMORY temp store)
- Dodge Dart 1.4L Turbo MultiAir factory maintenance schedule tracking & proactive reminders
- Automatic synchronization and semantic indexing of completed driving trips from TripLogger
- Conversational RAG context retrieval for R.U.M. daughter copilot
"""

import os
import sys
import time
import json
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple

BASE_DIR = Path(__file__).parent.parent.parent
MODELS_DIR = BASE_DIR / "models" / "embeddings"
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
RAG_DB_PATH = STORAGE_DIR / "rag_memory.db"


class MiniLMEmbeddingEngine:
    """Ultra-fast local embedding generator running quantized all-MiniLM-L6-v2 via ONNX Runtime."""
    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir or MODELS_DIR
        self.onnx_path = self.model_dir / "model_quantized.onnx"
        self.tok_path = self.model_dir / "tokenizer.json"
        self.session = None
        self.tokenizer = None
        self.dimension = 384
        self.ready = False
        self._init_engine()

    def _init_engine(self):
        try:
            if not self.onnx_path.exists() or not self.tok_path.exists():
                print(f"[RAG EMBED] Model files not found in {self.model_dir}. Falling back to sparse mode.")
                return

            import onnxruntime as ort
            from tokenizers import Tokenizer

            self.tokenizer = Tokenizer.from_file(str(self.tok_path))
            self.tokenizer.enable_truncation(max_length=128)
            self.tokenizer.no_padding()

            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = 2
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self.session = ort.InferenceSession(str(self.onnx_path), sess_options)
            self.ready = True
            print("[RAG EMBED] Local all-MiniLM-L6-v2 ONNX embedding engine ready (<12ms latency).")
        except Exception as e:
            print(f"[RAG EMBED] Initialization note (fallback enabled): {e}")

    def embed_text(self, text: str) -> np.ndarray:
        """Embeds single text string into a 384-dim normalized vector."""
        if not text or not text.strip():
            return np.zeros(self.dimension, dtype=np.float32)

        if self.ready and self.session and self.tokenizer:
            try:
                encoded = self.tokenizer.encode(text)
                input_ids = np.array([encoded.ids], dtype=np.int64)
                attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
                token_type_ids = np.array([encoded.type_ids], dtype=np.int64)

                inputs = {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "token_type_ids": token_type_ids
                }
                input_names = [inp.name for inp in self.session.get_inputs()]
                model_inputs = {k: inputs[k] for k in input_names if k in inputs}

                out = self.session.run(None, model_inputs)[0]  # (1, seq_len, 384)

                # Mean pooling with attention mask
                mask_expanded = np.expand_dims(attention_mask, -1)
                sum_embeddings = np.sum(out * mask_expanded, axis=1)
                sum_mask = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
                pooled = sum_embeddings / sum_mask
                norm = np.linalg.norm(pooled, axis=1, keepdims=True)
                unit_vec = (pooled / np.clip(norm, a_min=1e-9, a_max=None))[0]
                return unit_vec.astype(np.float32)
            except Exception as e:
                print(f"[RAG EMBED] Inference note: {e}")

        # Fallback sparse hash embedding
        return self._fallback_hash_embedding(text)

    def _fallback_hash_embedding(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dimension, dtype=np.float32)
        words = text.lower().split()
        for w in words:
            h = hash(w) % self.dimension
            vec[h] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


class RagMemoryEngine:
    """
    Long-term Vector Memory & Maintenance System for Dodge Dart 1.4L Turbo MultiAir.
    Tracks trips, maintenance history, factory specifications, and driver memories.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or RAG_DB_PATH)
        self.embed_engine = MiniLMEmbeddingEngine()
        self._init_db()
        self._seed_factory_maintenance()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA mmap_size = 268435456;")
            conn.execute("PRAGMA cache_size = -64000;")
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            c = conn.cursor()
            # 1. Documents table
            c.execute("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            # 2. Dense vector embeddings table
            c.execute("""
                CREATE TABLE IF NOT EXISTS rag_embeddings (
                    doc_id TEXT PRIMARY KEY NOT NULL,
                    vector BLOB NOT NULL
                )
            """)
            # 3. Vehicle State & Odometer
            c.execute("""
                CREATE TABLE IF NOT EXISTS vehicle_state (
                    key TEXT PRIMARY KEY NOT NULL,
                    value TEXT NOT NULL
                )
            """)
            # 4. Maintenance Schedule & History
            c.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_items (
                    item_key TEXT PRIMARY KEY NOT NULL,
                    item_name TEXT NOT NULL,
                    interval_miles INTEGER NOT NULL,
                    interval_months INTEGER DEFAULT 0,
                    last_service_mileage INTEGER NOT NULL,
                    last_service_date TEXT NOT NULL,
                    part_number TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    criticality TEXT DEFAULT 'HIGH'
                )
            """)
            # 5. Service Log History
            c.execute("""
                CREATE TABLE IF NOT EXISTS service_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_key TEXT NOT NULL,
                    service_date TEXT NOT NULL,
                    mileage INTEGER NOT NULL,
                    technician_notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            # Default odometer if not set
            c.execute("INSERT OR IGNORE INTO vehicle_state (key, value) VALUES ('odometer_miles', '85240')")
            conn.commit()

    def _seed_factory_maintenance(self):
        """Seeds official Dodge Dart 1.4L Turbo MultiAir factory maintenance parameters."""
        factory_items = [
            (
                "ENGINE_OIL",
                "5W-40 Full Synthetic Oil & Filter",
                4000, 6, 82100, "2026-10-15",
                "Mopar 68102241AA / Pennzoil Euro 5W-40 (MS-12991)",
                "Crucial for MultiAir hydraulic actuator solenoids. 4.0 qts (3.8L).",
                "CRITICAL"
            ),
            (
                "MULTIAIR_SCREEN",
                "MultiAir Actuator Oil Filter Screen",
                30000, 36, 60000, "2025-06-10",
                "Mopar 55238665 (10mm Hex Head Screen)",
                "Filters oil feeding UniAir brick. Clean or replace to prevent solenoid clog.",
                "HIGH"
            ),
            (
                "SPARK_PLUGS",
                "Euro-Spec Iridium Spark Plugs",
                30000, 36, 60000, "2025-06-10",
                "NGK SIKR9A7 (OEM Laser Iridium)",
                "Strictly gap to 0.026 inch (0.65 mm). High boost will blow spark on wider gaps.",
                "HIGH"
            ),
            (
                "TRANSMISSION_FLUID",
                "C635 6-Speed Manual Transaxle Fluid",
                40000, 48, 60000, "2025-06-10",
                "Tutela Transmission Gearforce 75W (MS-10216)",
                "2.0 qts (1.87L). Requires low-viscosity 75W GL-4 fluid for smooth synchros.",
                "MEDIUM"
            ),
            (
                "COOLANT",
                "Mopar OAT Purple Engine Coolant (50/50)",
                100000, 60, 60000, "2025-06-10",
                "Mopar Antifreeze OAT MS-12106",
                "6.8 qts (6.4L). Never mix with HOAT orange/pink (forms silicate gel).",
                "MEDIUM"
            ),
            (
                "BRAKE_FLUID",
                "DOT 4 Brake & Clutch Hydraulic Fluid",
                25000, 24, 75000, "2026-04-12",
                "Mopar DOT 4 Motor Vehicle Brake Fluid",
                "Shared reservoir feeds four-wheel discs and manual clutch slave cylinder.",
                "HIGH"
            ),
            (
                "WASTEGATE_INSPECT",
                "Garrett GT1446 Wastegate & Diverter Valve",
                15000, 12, 75000, "2026-04-12",
                "OEM Garrett GT1446 / Pierburg Diverter",
                "Check actuator arm pivot for slop and inspect diverter diaphragm for tears.",
                "MEDIUM"
            )
        ]
        with self._get_connection() as conn:
            c = conn.cursor()
            for item in factory_items:
                c.execute("""
                    INSERT OR IGNORE INTO maintenance_items 
                    (item_key, item_name, interval_miles, interval_months, last_service_mileage, last_service_date, part_number, notes, criticality)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, item)
            conn.commit()

        # Seed initial knowledge documents into RAG vector store
        self.add_document(
            doc_id="spec_engine_oil",
            category="SPECIFICATION",
            title="Dodge Dart 1.4L Turbo MultiAir Engine Oil Specification",
            content="The 2013-2016 Dodge Dart 1.4L Turbo MultiAir requires strictly 4.0 quarts (3.8L) of SAE 5W-40 Full Synthetic engine oil meeting Chrysler Material Standard MS-12991 or Fiat 9.55535-S2 (e.g. Pennzoil Platinum Euro 5W-40, Motul 8100 X-clean, Selenia K Pure Energy). Filter is Mopar 68102241AA or Wix 57060. The UniAir hydraulic brick uses engine oil as hydraulic fluid to actuate the intake valves; using 5W-30, 5W-20, or non-synthetic oil causes valve misfires (codes P1066-P1069) and hydraulic brick failure.",
            metadata={"item_key": "ENGINE_OIL"}
        )
        self.add_document(
            doc_id="spec_spark_plugs",
            category="SPECIFICATION",
            title="Dodge Dart 1.4L Turbo Spark Plug Gap and Spec",
            content="The Dodge Dart 1.4L Turbo MultiAir uses NGK SIKR9A7 laser iridium spark plugs. Factory gap is strictly 0.026 inch (0.65 mm). Replacement interval is every 30,000 miles. Torque specification into the aluminum cylinder head is 13.3 ft-lbs (18 Nm). Do not use non-iridium or standard copper plugs. Under full Garrett GT1446 turbo boost (up to 22 PSI), plug gaps wider than 0.028 inch will suffer spark blowout causing high-RPM cylinder hesitation.",
            metadata={"item_key": "SPARK_PLUGS"}
        )
        self.add_document(
            doc_id="spec_multiair_screen",
            category="SPECIFICATION",
            title="MultiAir Actuator Screen Maintenance",
            content="The MultiAir hydraulic actuator screen (Mopar part 55238665) is a small 10mm hex filter located on the passenger side of the cylinder head beneath the timing cover. It filters pressurized oil before entering the UniAir solenoid brick. It must be inspected and cleaned with brake cleaner or replaced every 30,000 miles. A clogged screen restricts oil pressure to cylinders 1 through 4, triggering limp mode.",
            metadata={"item_key": "MULTIAIR_SCREEN"}
        )
        self.add_document(
            doc_id="spec_transaxle_fluid",
            category="SPECIFICATION",
            title="C635 6-Speed Manual Transaxle Fluid",
            content="The US-spec Dodge Dart 1.4T C635 6-speed manual transaxle takes 2.0 quarts (1.87 liters) of Tutela Transmission Gearforce 75W synthetic gear oil meeting Fiat 9.55550-MZ6 / Chrysler MS-10216. Using standard thick 75W-90 causes difficult notchy gear engagement and synchro grind when cold.",
            metadata={"item_key": "TRANSMISSION_FLUID"}
        )

    # -------------------------------------------------------------
    # Document & Vector Ingestion
    # -------------------------------------------------------------
    def add_document(self, doc_id: str, category: str, title: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Adds or updates a document and generates its 384-dim semantic embedding."""
        now = datetime.now().isoformat()
        meta_str = json.dumps(metadata or {})
        text_to_embed = f"{title}. {content}"
        vector = self.embed_engine.embed_text(text_to_embed)

        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO rag_documents (doc_id, category, title, content, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    category=excluded.category,
                    title=excluded.title,
                    content=excluded.content,
                    metadata_json=excluded.metadata_json,
                    created_at=excluded.created_at
            """, (doc_id, category, title, content, meta_str, now))

            vec_blob = vector.tobytes()
            c.execute("""
                INSERT INTO rag_embeddings (doc_id, vector)
                VALUES (?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET vector=excluded.vector
            """, (doc_id, vec_blob))
            conn.commit()

    # -------------------------------------------------------------
    # Semantic Search & Cosine Retrieval
    # -------------------------------------------------------------
    def search(self, query: str, top_k: int = 5, threshold: float = 0.30) -> List[Dict[str, Any]]:
        """Retrieves top matching documents via cosine similarity."""
        query_vec = self.embed_engine.embed_text(query)
        if np.all(query_vec == 0):
            return []

        results = []
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT d.doc_id, d.category, d.title, d.content, d.metadata_json, e.vector
                FROM rag_documents d
                JOIN rag_embeddings e ON d.doc_id = e.doc_id
            """)
            rows = c.fetchall()

            for doc_id, category, title, content, meta_json, vec_blob in rows:
                doc_vec = np.frombuffer(vec_blob, dtype=np.float32)
                sim = float(np.dot(query_vec, doc_vec))
                if sim >= threshold:
                    results.append({
                        "doc_id": doc_id,
                        "category": category,
                        "title": title,
                        "content": content,
                        "metadata": json.loads(meta_json or "{}"),
                        "similarity": round(sim, 4)
                    })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def retrieve_context_for_prompt(self, query: str, top_k: int = 2, threshold: float = 0.35) -> Optional[str]:
        """Formats high-confidence semantic matches into a concise snippet for LLM injection."""
        matches = self.search(query, top_k=top_k, threshold=threshold)
        if not matches:
            return None

        lines = []
        for m in matches:
            lines.append(f"• [{m['category']}] {m['title']}: {m['content']}")
        return "\n".join(lines)

    # -------------------------------------------------------------
    # Odometer & Maintenance State
    # -------------------------------------------------------------
    def get_odometer(self) -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM vehicle_state WHERE key = 'odometer_miles'")
            row = c.fetchone()
            return int(row[0]) if row else 85240

    def set_odometer(self, miles: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO vehicle_state (key, value) VALUES ('odometer_miles', ?)", (str(int(miles)),))
            conn.commit()

    def advance_odometer(self, delta_miles: float):
        if delta_miles > 0:
            cur = self.get_odometer()
            new_odo = cur + int(round(delta_miles))
            self.set_odometer(new_odo)

    def get_maintenance_status(self) -> Dict[str, Any]:
        """Calculates miles remaining and status alerts for all MultiAir scheduled service items."""
        odo = self.get_odometer()
        items_out = []
        alerts_due = []

        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT item_key, item_name, interval_miles, interval_months, 
                       last_service_mileage, last_service_date, part_number, notes, criticality
                FROM maintenance_items
                ORDER BY interval_miles ASC
            """)
            rows = c.fetchall()
            for r in rows:
                key, name, interval, months, last_mile, last_date, part, notes, crit = r
                due_mileage = last_mile + interval
                miles_remaining = due_mileage - odo

                if miles_remaining <= 0:
                    status = "DUE_NOW"
                    alerts_due.append(f"{name} is overdue by {abs(miles_remaining):,} miles!")
                elif miles_remaining <= 500:
                    status = "DUE_SOON"
                    alerts_due.append(f"{name} is due soon (in {miles_remaining:,} miles).")
                else:
                    status = "OK"

                pct_used = min(100.0, max(0.0, round(((odo - last_mile) / max(1, interval)) * 100.0, 1)))

                items_out.append({
                    "item_key": key,
                    "name": name,
                    "interval_miles": interval,
                    "last_service_mileage": last_mile,
                    "last_service_date": last_date,
                    "due_mileage": due_mileage,
                    "miles_remaining": miles_remaining,
                    "percent_used": pct_used,
                    "status": status,
                    "part_number": part,
                    "notes": notes,
                    "criticality": crit
                })

        return {
            "current_odometer": odo,
            "items": items_out,
            "alerts": alerts_due,
            "timestamp": time.time()
        }

    def record_service(self, item_key: str, mileage: int, notes: str = "") -> bool:
        """Logs completed maintenance, updates interval tracker, and indexes service event into RAG vector memory."""
        now_date = datetime.now().strftime("%Y-%m-%d")
        now_ts = datetime.now().isoformat()

        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT item_name FROM maintenance_items WHERE item_key = ?", (item_key,))
            row = c.fetchone()
            if not row:
                return False
            name = row[0]

            # 1. Update maintenance items table
            c.execute("""
                UPDATE maintenance_items
                SET last_service_mileage = ?, last_service_date = ?
                WHERE item_key = ?
            """, (mileage, now_date, item_key))

            # 2. Append to service log history
            c.execute("""
                INSERT INTO service_history (item_key, service_date, mileage, technician_notes, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (item_key, now_date, mileage, notes, now_ts))
            conn.commit()

        # Update odometer if service was performed at higher mileage
        if mileage > self.get_odometer():
            self.set_odometer(mileage)

        # 3. Ingest into RAG vector memory
        doc_id = f"service_{item_key}_{mileage}"
        content = f"Completed {name} service on {now_date} at {mileage:,} miles. Technician notes: {notes or 'Standard OEM factory specification replacement.'}"
        self.add_document(
            doc_id=doc_id,
            category="MAINTENANCE",
            title=f"{name} Completed at {mileage:,} Miles",
            content=content,
            metadata={"item_key": item_key, "mileage": mileage, "date": now_date}
        )
        print(f"[RAG MEMORY] Recorded service '{name}' at {mileage:,} miles and indexed vector.")
        return True

    # -------------------------------------------------------------
    # Trip Logger Automatic Synchronization
    # -------------------------------------------------------------
    def sync_completed_trips(self, vehicle_db_path: Optional[str] = None):
        """Indexes completed driving sessions from TripLogger into semantic vector memory."""
        v_db = vehicle_db_path or str(BASE_DIR / "backend" / "telemetry" / "vehicle_data.db")
        if not os.path.exists(v_db):
            return

        try:
            with sqlite3.connect(v_db) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("""
                    SELECT id, start_time, duration_min, distance_miles, max_speed_mph, avg_speed_mph,
                           max_boost_psi, peak_coolant_f, peak_iat_f, best_zero_to_sixty, boost_pulls_count
                    FROM trips
                    ORDER BY id DESC LIMIT 50
                """)
                trips = c.fetchall()

            for t in trips:
                t_id = t["id"]
                doc_id = f"trip_summary_{t_id}"

                # Check if already indexed
                with self._get_connection() as r_conn:
                    r_c = r_conn.cursor()
                    r_c.execute("SELECT 1 FROM rag_documents WHERE doc_id = ?", (doc_id,))
                    if r_c.fetchone():
                        continue

                dist = round(t["distance_miles"] or 0.0, 1)
                dur = round(t["duration_min"] or 0.0, 1)
                max_s = round(t["max_speed_mph"] or 0.0, 1)
                avg_s = round(t["avg_speed_mph"] or 0.0, 1)
                boost = round(t["max_boost_psi"] or 0.0, 1)
                coolant = round(t["peak_coolant_f"] or 0.0, 1)
                zero_60 = round(t["best_zero_to_sixty"], 2) if t["best_zero_to_sixty"] else None

                summary = (
                    f"Trip #{t_id} on {t['start_time'][:10]}: Covered {dist} miles in {dur} minutes. "
                    f"Top speed was {max_s} miles per hour with an average cruising speed of {avg_s} mph. "
                    f"Garrett GT1446 turbo pushed peak boost of {boost} PSI across {t['boost_pulls_count'] or 0} boost pulls. "
                    f"Peak engine coolant temperature reached {coolant}°F. "
                )
                if zero_60:
                    summary += f"Best 0 to 60 mph acceleration sprint was {zero_60} seconds! "

                self.add_document(
                    doc_id=doc_id,
                    category="TRIP_LOG",
                    title=f"Driving Trip #{t_id} ({dist} miles, {boost} PSI boost)",
                    content=summary,
                    metadata={"trip_id": t_id, "boost": boost, "0_60": zero_60}
                )
        except Exception as e:
            print(f"[RAG MEMORY] Trip sync note: {e}")
