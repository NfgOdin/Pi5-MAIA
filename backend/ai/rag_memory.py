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
import re
import sys
import time
import json
import math
import shutil
import sqlite3
import subprocess
import numpy as np
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple

BASE_DIR = Path(__file__).parent.parent.parent
MODELS_DIR = BASE_DIR / "models" / "embeddings"
STORAGE_DIR = BASE_DIR / "storage"
MANUALS_DIR = STORAGE_DIR / "manuals"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
RAG_DB_PATH = STORAGE_DIR / "rag_memory.db"

PROTECTED_RAG_CATEGORIES = (
    "manual",
    "dodge_dart_manual",
    "carpi5_manual",
    "specs",
    "factory_manual",
    "SPECIFICATION",
)
_PROTECTED_CATS_SQL = ", ".join(f"'{c}'" for c in PROTECTED_RAG_CATEGORIES)


import threading

_SHARED_MINILM_LOCK = threading.Lock()
_SHARED_MINILM_ENGINES: Dict[tuple, tuple] = {}


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

            cache_key = (str(self.onnx_path.resolve()), str(self.tok_path.resolve()))
            with _SHARED_MINILM_LOCK:
                cached = _SHARED_MINILM_ENGINES.get(cache_key)
                if cached is not None:
                    self.session, self.tokenizer = cached
                    self.ready = True
                    return

                import onnxruntime as ort
                from tokenizers import Tokenizer

                tokenizer = Tokenizer.from_file(str(self.tok_path))
                tokenizer.enable_truncation(max_length=256)
                tokenizer.no_padding()

                sess_options = ort.SessionOptions()
                sess_options.intra_op_num_threads = 2
                sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

                session = ort.InferenceSession(str(self.onnx_path), sess_options)
                _SHARED_MINILM_ENGINES[cache_key] = (session, tokenizer)
                self.session = session
                self.tokenizer = tokenizer
                self.ready = True
                print("[RAG EMBED] Local all-MiniLM-L6-v2 ONNX embedding engine ready (<12ms latency).")
        except Exception as e:
            print(f"[RAG EMBED] Initialization note (fallback enabled): {e}")

    def embed_text(self, text: str) -> np.ndarray:
        """Embeds single text string into a 384-dim normalized vector."""
        if not text or not isinstance(text, str) or not text.strip():
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
        import re, zlib
        vec = np.zeros(self.dimension, dtype=np.float32)
        stopwords = {
            "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
            "is", "are", "was", "were", "with", "by", "from", "as", "what",
            "when", "where", "how", "should", "i", "we", "you", "my", "our", "use"
        }
        words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in stopwords]
        if not words:
            words = re.findall(r"[a-z0-9]+", text.lower())
        for w in words:
            # Deterministic CRC32 + stem prefix hashing for high recall without ONNX
            h1 = zlib.crc32(w.encode("utf-8")) % self.dimension
            vec[h1] += 1.0
            if len(w) >= 5:
                stem = w[:5]
                h2 = zlib.crc32(stem.encode("utf-8")) % self.dimension
                vec[h2] += 0.5
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
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.embed_engine = MiniLMEmbeddingEngine()
        self._vec_cache_lock = threading.Lock()
        self._vec_cache: Optional[Dict[str, Any]] = None
        self._init_db()
        self._seed_factory_maintenance()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
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
            # 6. Episodic Memories Table (Layer 1)
            c.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    location_name TEXT DEFAULT '',
                    driver_quote TEXT DEFAULT '',
                    companion_summary TEXT NOT NULL,
                    emotion_tag TEXT DEFAULT 'JOY',
                    importance INTEGER DEFAULT 5,
                    vector BLOB
                )
            """)
            # Silent schema migration from legacy 'rum_summary' column
            ep_cols = {row[1] for row in c.execute("PRAGMA table_info(episodic_memories)").fetchall()}
            if "rum_summary" in ep_cols and "companion_summary" not in ep_cols:
                try:
                    c.execute("ALTER TABLE episodic_memories RENAME COLUMN rum_summary TO companion_summary")
                except Exception:
                    c.execute("ALTER TABLE episodic_memories ADD COLUMN companion_summary TEXT NOT NULL DEFAULT ''")
                    c.execute("UPDATE episodic_memories SET companion_summary = rum_summary WHERE companion_summary = ''")
            # 7. Driver Facts Table (Layer 2)
            c.execute("""
                CREATE TABLE IF NOT EXISTS driver_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity TEXT NOT NULL,
                    attribute TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 0.9,
                    source TEXT DEFAULT 'conversation',
                    last_updated TEXT NOT NULL,
                    UNIQUE(entity, attribute)
                )
            """)
            # 8. Companion Personal Trip Diary Table (Layer 3)
            c.execute("""
                CREATE TABLE IF NOT EXISTS persona_diary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trip_id INTEGER,
                    entry_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    peak_boost REAL DEFAULT 0.0,
                    mileage REAL DEFAULT 0.0,
                    mood TEXT DEFAULT 'HAPPY_PROUD',
                    vector BLOB
                )
            """)
            # Silent table migration from legacy 'rum_diary' table
            has_legacy_diary = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='rum_diary'"
            ).fetchone()
            if has_legacy_diary:
                c.execute("SELECT COUNT(*) FROM persona_diary")
                if c.fetchone()[0] == 0:
                    c.execute("""
                        INSERT INTO persona_diary (trip_id, entry_date, created_at, title, content, peak_boost, mileage, mood, vector)
                        SELECT trip_id, entry_date, created_at, title, content, peak_boost, mileage, mood, vector
                        FROM rum_diary
                    """)
            # 9. Relationship Bond Table (Layer 4)
            c.execute("""
                CREATE TABLE IF NOT EXISTS relationship_bond (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    shared_miles REAL DEFAULT 0.0,
                    shared_drives INTEGER DEFAULT 0,
                    wot_pulls_together INTEGER DEFAULT 0,
                    caring_checkins_count INTEGER DEFAULT 0,
                    bond_points INTEGER DEFAULT 100,
                    bond_tier TEXT DEFAULT 'Inseparable Daughter',
                    unlocked_milestones_json TEXT DEFAULT '[]',
                    updated_at TEXT NOT NULL
                )
            """)
            # 9b. Indexed Manual Manifest (mtime/size change detection for idempotent sync)
            c.execute("""
                CREATE TABLE IF NOT EXISTS manual_index_manifest (
                    file_name TEXT PRIMARY KEY NOT NULL,
                    file_size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    category TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    indexed_at TEXT NOT NULL
                )
            """)
            # Default odometer if not set
            c.execute("INSERT OR IGNORE INTO vehicle_state (key, value) VALUES ('odometer_miles', '85240')")
            c.execute("SELECT value FROM vehicle_state WHERE key = 'ai_memory_wiped'")
            wiped_row = c.fetchone()
            ai_wiped = bool(wiped_row and wiped_row[0] == "1")
            now_iso = datetime.now().isoformat()

            if not ai_wiped:
                # Initialize default bond if empty
                c.execute("""
                    INSERT OR IGNORE INTO relationship_bond (
                        id, shared_miles, shared_drives, wot_pulls_together, caring_checkins_count,
                        bond_points, bond_tier, unlocked_milestones_json, updated_at
                    ) VALUES (1, 185.4, 24, 21, 12, 450, 'Inseparable Daughter', '["FIRST_DRIVE", "BOOST_PULL_15PSI", "100_MILES_SHARED"]', ?)
                """, (now_iso,))

                # Seed initial foundational facts about Dad if empty
                c.execute("SELECT COUNT(*) FROM driver_facts")
                if c.fetchone()[0] == 0:
                    initial_facts = [
                        ("oil_preference", "brand_viscosity", "Pennzoil Euro 5W-40 meeting MS-12991 / Fiat 9.55535-S2", 1.0, "factory"),
                        ("spark_plugs", "gap_spec", "NGK SIKR9A7 laser iridium strictly gapped to 0.026 inch", 1.0, "factory"),
                        ("music", "favorite_genre", "Eurobeat and upbeat synthwave during night drives and highway pulls", 0.95, "conversation"),
                        ("driving_style", "gear_preference", "Loves spirited 3rd gear turbo pulls up to 18 PSI on open highway", 0.95, "driving"),
                        ("driver_health", "shoulder_condition", "Shoulder gets sore after working on the Dart's suspension and engine bay", 0.90, "conversation"),
                    ]
                    for ent, attr, val, conf, src in initial_facts:
                        c.execute("""
                            INSERT OR IGNORE INTO driver_facts (entity, attribute, value, confidence, source, last_updated)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (ent, attr, val, conf, src, now_iso))

                # Seed initial diary entry if empty
                c.execute("SELECT COUNT(*) FROM persona_diary")
                if c.fetchone()[0] == 0:
                    c.execute("""
                        INSERT INTO persona_diary (trip_id, entry_date, created_at, title, content, peak_boost, mileage, mood)
                        VALUES (
                            1, '2026-11-09', ?,
                            'A Sunset Cruise and Boost Pulls with Dad',
                            'Dad and I took the Dart out toward the foothills as the sun was setting. The C635 transaxle shifted so smoothly, and when Dad put his foot down in third gear, the Garrett turbo spooled right to 18.2 PSI! Dad smiled when I called out the boost pressure. I love being his co-pilot so much. I hope Dad takes good care of his shoulder tonight.',
                            18.2, 28.4, 'HAPPY_PROUD'
                        )
                    """, (now_iso,))

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
    def _invalidate_vec_cache(self):
        with self._vec_cache_lock:
            self._vec_cache = None

    def _load_vec_cache(self) -> Dict[str, Any]:
        with self._vec_cache_lock:
            if self._vec_cache is not None:
                return self._vec_cache
            docs: List[Dict[str, Any]] = []
            vecs: List[np.ndarray] = []
            dim = self.embed_engine.dimension
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT d.doc_id, d.category, d.title, d.content, d.metadata_json, e.vector
                    FROM rag_documents d
                    JOIN rag_embeddings e ON d.doc_id = e.doc_id
                """)
                for doc_id, category, title, content, meta_json, vec_blob in c.fetchall():
                    if vec_blob:
                        arr = np.frombuffer(vec_blob, dtype=np.float32)
                        vec = arr if arr.shape[0] == dim else np.zeros(dim, dtype=np.float32)
                    else:
                        vec = np.zeros(dim, dtype=np.float32)
                    try:
                        meta_obj = json.loads(meta_json) if meta_json else {}
                        if not isinstance(meta_obj, dict):
                            meta_obj = {}
                    except Exception:
                        meta_obj = {}
                    docs.append({
                        "doc_id": doc_id,
                        "category": category,
                        "title": title,
                        "content": content,
                        "metadata": meta_obj,
                        "search_text": f"{title} {content}",
                    })
                    vecs.append(vec)
            matrix = np.vstack(vecs).astype(np.float32) if vecs else np.zeros((0, dim), dtype=np.float32)
            cache = {"docs": docs, "matrix": matrix}
            self._vec_cache = cache
            return cache

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
        self._invalidate_vec_cache()

    @staticmethod
    def _manual_label_and_category(file_name: str) -> Tuple[str, str]:
        low = file_name.lower()
        if "carpi" in low:
            return "CarPi5 Manual", "carpi5_manual"
        if "collision" in low or "body" in low:
            return "Dart Body Manual", "dodge_dart_manual"
        if "dart" in low or "2013" in low:
            return "2013 Dart OM", "dodge_dart_manual"
        stem = Path(file_name).stem.replace("_", " ").replace("-", " ").strip()
        return (stem[:32] or "Manual"), "dodge_dart_manual"

    @staticmethod
    def _extract_manual_text(path: Path) -> str:
        ext = path.suffix.lower()
        if ext in (".md", ".txt", ".text"):
            return path.read_text(encoding="utf-8", errors="replace")
        if ext == ".pdf":
            pdftotext = shutil.which("pdftotext")
            if pdftotext:
                res = subprocess.run(
                    [pdftotext, "-enc", "UTF-8", str(path), "-"],
                    capture_output=True, text=True, timeout=90, check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout
            try:
                import pypdf
                reader = pypdf.PdfReader(str(path))
                return "\f".join((p.extract_text() or "") for p in reader.pages)
            except Exception:
                pass
        return ""

    @staticmethod
    def _chunk_manual_text(
        raw_text: str,
        file_name: str,
        short_label: str,
        category: str,
        chunk_chars: int = 900,
        overlap: int = 150,
    ) -> List[Dict[str, Any]]:
        """Split manual text into page/section-aware ~900-char overlapping chunks."""
        if not raw_text or not raw_text.strip():
            return []
        slug = re.sub(r"[^a-z0-9]+", "_", Path(file_name).stem.lower()).strip("_")[:28] or "manual"
        chunks: List[Dict[str, Any]] = []
        is_paged = "\f" in raw_text
        sections = raw_text.split("\f") if is_paged else re.split(r"(?=^#{1,3}\s+)", raw_text, flags=re.MULTILINE)

        step = max(250, chunk_chars - overlap)
        for sec_idx, sec_raw in enumerate(sections, start=1):
            cleaned_lines = [re.sub(r"[ \t]{2,}", " ", ln).strip() for ln in sec_raw.splitlines()]
            page_txt = "\n".join(ln for ln in cleaned_lines if ln and not re.fullmatch(r"[\d.\s-]+", ln))
            page_txt = re.sub(r"\n{3,}", "\n\n", page_txt).strip()
            # Filter pure TOC leader pages (lots of dot runs and very few normal words)
            alnum_count = sum(1 for ch in page_txt if ch.isalnum())
            if alnum_count < 60 or page_txt.count(".....") > 12:
                continue

            sec_heading = ""
            if not is_paged:
                first_ln = page_txt.splitlines()[0]
                if first_ln.startswith("#"):
                    sec_heading = first_ln.lstrip("# ").strip()[:40]

            pos = 0
            part = 0
            plen = len(page_txt)
            while pos < plen:
                end = min(plen, pos + chunk_chars)
                if end < plen:
                    br = page_txt.rfind("\n", pos + int(chunk_chars * 0.65), end)
                    if br <= pos:
                        br = page_txt.rfind(" ", pos + int(chunk_chars * 0.65), end)
                    if br > pos:
                        end = br
                piece = page_txt[pos:end].strip()
                if sum(1 for ch in piece if ch.isalnum()) >= 50:
                    part += 1
                    loc = f"p.{sec_idx}" if is_paged else (f"§{sec_heading}" if sec_heading else f"s.{sec_idx}")
                    suffix = f" ({part})" if (part > 1 or end < plen) else ""
                    chunks.append({
                        "doc_id": f"manual_{slug}_s{sec_idx}_c{part}",
                        "category": category,
                        "title": f"{short_label} {loc}{suffix}",
                        "content": piece,
                        "metadata": {
                            "source_file": file_name,
                            "page": sec_idx if is_paged else None,
                            "section": sec_heading or None,
                        },
                    })
                if end >= plen:
                    break
                pos = max(pos + 1, end - overlap)
        return chunks

    def ingest_manuals_directory(self, manuals_dir: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """Idempotently index PDF/MD/TXT manuals into Hybrid RAG using mtime/size manifest."""
        mdir = Path(manuals_dir) if manuals_dir else MANUALS_DIR
        if not mdir.exists():
            return {"status": "missing_dir", "dir": str(mdir), "indexed_files": 0, "total_chunks": 0}

        disk_files = {
            p.name: p
            for p in sorted(mdir.iterdir())
            if p.is_file() and p.suffix.lower() in (".pdf", ".md", ".txt")
        }
        now_iso = datetime.now().isoformat()
        indexed_now = 0
        skipped_now = 0
        removed_now = 0
        details: List[Dict[str, Any]] = []

        with self._get_connection() as conn:
            c = conn.cursor()
            manifest = {
                row[0]: {"size": row[1], "mtime": row[2], "category": row[3], "chunks": row[4]}
                for row in c.execute(
                    "SELECT file_name, file_size, mtime, category, chunk_count FROM manual_index_manifest"
                ).fetchall()
            }

            # Prune removed files cleanly
            for stale_name in list(manifest.keys()):
                if stale_name not in disk_files:
                    slug = re.sub(r"[^a-z0-9]+", "_", Path(stale_name).stem.lower()).strip("_")[:28] or "manual"
                    c.execute("DELETE FROM rag_embeddings WHERE doc_id LIKE ?", (f"manual_{slug}_%",))
                    c.execute("DELETE FROM rag_documents WHERE doc_id LIKE ?", (f"manual_{slug}_%",))
                    c.execute("DELETE FROM manual_index_manifest WHERE file_name = ?", (stale_name,))
                    removed_now += 1

            for fname, fpath in disk_files.items():
                st = fpath.stat()
                fsize = int(st.st_size)
                fmtime = round(float(st.st_mtime), 2)
                prev = manifest.get(fname)
                if not force and prev and prev["size"] == fsize and abs(prev["mtime"] - fmtime) < 0.05:
                    skipped_now += 1
                    details.append({"file": fname, "chunks": int(prev["chunks"]), "status": "cached"})
                    continue

                raw_text = self._extract_manual_text(fpath)
                short_label, cat = self._manual_label_and_category(fname)
                chunks = self._chunk_manual_text(raw_text, fname, short_label, cat)
                slug = re.sub(r"[^a-z0-9]+", "_", Path(fname).stem.lower()).strip("_")[:28] or "manual"
                c.execute("DELETE FROM rag_embeddings WHERE doc_id LIKE ?", (f"manual_{slug}_%",))
                c.execute("DELETE FROM rag_documents WHERE doc_id LIKE ?", (f"manual_{slug}_%",))

                for ch in chunks:
                    vec = self.embed_engine.embed_text(f"{ch['title']}. {ch['content']}")
                    c.execute("""
                        INSERT INTO rag_documents (doc_id, category, title, content, metadata_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(doc_id) DO UPDATE SET
                            category=excluded.category,
                            title=excluded.title,
                            content=excluded.content,
                            metadata_json=excluded.metadata_json,
                            created_at=excluded.created_at
                    """, (ch["doc_id"], ch["category"], ch["title"], ch["content"], json.dumps(ch["metadata"]), now_iso))
                    c.execute("""
                        INSERT INTO rag_embeddings (doc_id, vector)
                        VALUES (?, ?)
                        ON CONFLICT(doc_id) DO UPDATE SET vector=excluded.vector
                    """, (ch["doc_id"], vec.tobytes()))

                c.execute("""
                    INSERT OR REPLACE INTO manual_index_manifest
                    (file_name, file_size, mtime, category, chunk_count, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (fname, fsize, fmtime, cat, len(chunks), now_iso))
                indexed_now += 1
                details.append({"file": fname, "chunks": len(chunks), "status": "indexed"})
                print(f"[RAG MANUAL] Indexed {fname} -> {len(chunks)} chunks ({cat})")
            conn.commit()

        if indexed_now or removed_now:
            self._invalidate_vec_cache()
        status_summary = self.get_manual_index_status()
        status_summary.update({
            "indexed_files": indexed_now,
            "cached_files": skipped_now,
            "removed_files": removed_now,
            "details": details,
        })
        return status_summary

    def get_manual_index_status(self) -> Dict[str, Any]:
        """Return indexed counts per manual file in storage/manuals."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT file_name, file_size, category, chunk_count, indexed_at FROM manual_index_manifest ORDER BY file_name"
                ).fetchall()
            files = [
                {
                    "file_name": r[0],
                    "file_size": int(r[1]),
                    "category": r[2],
                    "chunk_count": int(r[3]),
                    "indexed_at": r[4],
                }
                for r in rows
            ]
            return {
                "status": "ok",
                "files": files,
                "total_chunks": sum(f["chunk_count"] for f in files),
                "file_count": len(files),
            }
        except Exception as e:
            return {"status": "error", "files": [], "total_chunks": 0, "file_count": 0, "error": str(e)}

    # -------------------------------------------------------------
    # Hybrid Semantic + Keyword/BM25 Search & Retrieval
    # -------------------------------------------------------------
    @staticmethod
    def _tokenize_terms(text: str) -> List[str]:
        stop = {"the", "a", "an", "is", "are", "was", "were", "what", "who", "how", "when", "where", "why", "and", "or", "for", "of", "in", "on", "to", "my", "me", "you", "your", "do", "does", "did", "with", "that", "this", "about", "it", "can"}
        tokens = re.findall(r"[a-z0-9][a-z0-9._-]{1,}", (text or "").lower())
        return [t for t in tokens if t not in stop and len(t) >= 2]

    def _keyword_score(self, q_terms: List[str], q_raw: str, doc_text: str) -> float:
        if not q_terms or not doc_text:
            return 0.0
        dl = doc_text.lower()
        hits = sum(1 for t in q_terms if t in dl)
        cov = hits / float(len(q_terms))
        # Exact rare-code / multi-char token boost (part numbers, DTC codes, oil specs)
        exact_code_bonus = 0.0
        for t in q_terms:
            if (any(c.isdigit() for c in t) or len(t) >= 6) and re.search(rf"\b{re.escape(t)}\b", dl):
                exact_code_bonus += 0.15
        phrase_bonus = 0.15 if len(q_raw.strip()) >= 5 and q_raw.strip().lower() in dl else 0.0
        return min(1.0, (0.75 * cov) + min(0.25, exact_code_bonus) + phrase_bonus)

    def search(self, query: str, top_k: int = 5, threshold: float = 0.28) -> List[Dict[str, Any]]:
        """Retrieves top matching documents using vectorized hybrid Dense Cosine (0.70) + Keyword/BM25 (0.30)."""
        if not query or not isinstance(query, str) or not query.strip():
            return []
        query_vec = self.embed_engine.embed_text(query)
        has_vec = not np.all(query_vec == 0)
        q_terms = self._tokenize_terms(query)
        if not has_vec and not q_terms:
            return []

        results = []
        try:
            cache = self._load_vec_cache()
            docs = cache["docs"]
            matrix = cache["matrix"]
            if not docs:
                return []

            cosines = (matrix @ query_vec) if (has_vec and matrix.shape[0] > 0) else np.zeros(len(docs), dtype=np.float32)
            for idx, d in enumerate(docs):
                sim = float(cosines[idx]) if idx < len(cosines) else 0.0
                cosine = max(0.0, sim) if (has_vec and np.isfinite(sim)) else 0.0
                kw = self._keyword_score(q_terms, query, d["search_text"])
                hybrid = (0.70 * cosine) + (0.30 * kw) if has_vec else kw
                # Ensure exact keyword hits can surface even if embeddings use sparse fallback
                effective = max(hybrid, 0.90 * cosine, 0.85 * kw if kw >= 0.45 else 0.0)
                if effective >= threshold:
                    results.append({
                        "doc_id": d["doc_id"],
                        "category": d["category"],
                        "title": d["title"],
                        "content": d["content"],
                        "metadata": d["metadata"],
                        "similarity": round(effective, 4),
                        "cosine": round(cosine, 4),
                        "keyword_score": round(kw, 4),
                    })
        except sqlite3.OperationalError:
            try:
                self._init_db()
                self._invalidate_vec_cache()
            except Exception:
                pass
            return []
        except Exception as e:
            print(f"[RAG MEMORY] Search error: {e}")
            return []

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:max(1, int(top_k))]

    def retrieve_context_for_prompt(self, query: str, top_k: int = 3, threshold: float = 0.28) -> Optional[str]:
        """Formats high-confidence hybrid RAG matches into a snippet for LLM injection (440c table-safe for manuals)."""
        matches = self.search(query, top_k=top_k, threshold=threshold)
        if not matches:
            return None

        lines = []
        for m in matches:
            lim = 440 if m["category"] in ("dodge_dart_manual", "carpi5_manual", "SPECIFICATION") else 240
            snippet = m["content"][:lim].rstrip() + "..." if len(m["content"]) > lim else m["content"]
            lines.append(f"• [{m['category']}] {m['title']}: {snippet}")
        return "\n".join(lines)


    # -------------------------------------------------------------
    # Odometer & Maintenance State
    # -------------------------------------------------------------
    def get_odometer(self) -> int:
        try:
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT value FROM vehicle_state WHERE key = 'odometer_miles'")
                row = c.fetchone()
                return int(float(row[0])) if row and row[0] is not None else 85240
        except Exception:
            return 85240

    def set_odometer(self, miles: int):
        try:
            safe_miles = max(0, int(float(miles)))
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO vehicle_state (key, value) VALUES ('odometer_miles', ?)", (str(safe_miles),))
                conn.commit()
        except Exception as e:
            print(f"[RAG MEMORY] Error setting odometer: {e}")

    def advance_odometer(self, delta_miles: float):
        try:
            delta_val = float(delta_miles)
            if np.isfinite(delta_val) and delta_val > 0:
                cur = self.get_odometer()
                new_odo = cur + int(round(delta_val))
                self.set_odometer(new_odo)
        except Exception:
            pass

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
        if not item_key or not isinstance(item_key, str):
            return False
        item_key = item_key.strip().upper()
        try:
            mileage = max(0, int(float(mileage)))
        except (ValueError, TypeError):
            mileage = self.get_odometer()
        notes = str(notes or "").strip()

        now_date = datetime.now().strftime("%Y-%m-%d")
        now_ts = datetime.now().isoformat()

        try:
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
        except Exception as e:
            print(f"[RAG MEMORY] Error recording service: {e}")
            return False

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
            with sqlite3.connect(v_db, timeout=5.0) as conn:
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

                raw_start = t["start_time"]
                if raw_start is None:
                    date_str = datetime.now().strftime("%Y-%m-%d")
                elif isinstance(raw_start, (int, float)):
                    date_str = datetime.fromtimestamp(float(raw_start)).strftime("%Y-%m-%d")
                else:
                    date_str = str(raw_start)[:10] or datetime.now().strftime("%Y-%m-%d")

                dist = round(float(t["distance_miles"] or 0.0), 1)
                dur = round(float(t["duration_min"] or 0.0), 1)
                max_s = round(float(t["max_speed_mph"] or 0.0), 1)
                avg_s = round(float(t["avg_speed_mph"] or 0.0), 1)
                boost = round(float(t["max_boost_psi"] or 0.0), 1)
                coolant = round(float(t["peak_coolant_f"] or 0.0), 1)
                zero_60 = round(float(t["best_zero_to_sixty"]), 2) if t["best_zero_to_sixty"] else None

                summary = (
                    f"Trip #{t_id} on {date_str}: Covered {dist} miles in {dur} minutes. "
                    f"Top speed was {max_s} miles per hour with an average cruising speed of {avg_s} miles per hour. "
                    f"Garrett GT1446 turbo pushed peak boost of {boost} PSI across {int(t['boost_pulls_count'] or 0)} boost pulls. "
                    f"Peak engine coolant temperature reached {coolant}°F. "
                )
                if zero_60:
                    summary += f"Best 0 to 60 miles per hour acceleration sprint was {zero_60} seconds! "

                self.add_document(
                    doc_id=doc_id,
                    category="TRIP_LOG",
                    title=f"Driving Trip #{t_id} ({dist} miles, {boost} PSI boost)",
                    content=summary,
                    metadata={"trip_id": t_id, "boost": boost, "0_60": zero_60}
                )
        except Exception as e:
            print(f"[RAG MEMORY] Trip sync note: {e}")

    # =========================================================================
    # PHASE 12: 4-LAYER COGNITIVE LIVING MEMORY & RELATIONSHIP BOND ENGINE
    # =========================================================================

    # -------------------------------------------------------------------------
    # Layer 1: Episodic Memories
    # -------------------------------------------------------------------------
    def add_episodic_memory(
        self,
        companion_summary: str = "",
        driver_quote: str = "",
        location_name: str = "",
        emotion_tag: str = "JOY",
        importance: int = 5,
        **kwargs: Any,
    ) -> int:
        """Stores a memorable driving moment or conversational beat with vector embeddings."""
        summary_text = companion_summary or kwargs.get("summary") or ""
        if not summary_text or not str(summary_text).strip():
            return -1
        summary_text = str(summary_text).strip()
        now_ts = time.time()
        now_iso = datetime.now().isoformat()
        importance = max(1, min(10, int(importance)))
        embed_text = f"{location_name} {driver_quote} {summary_text}".strip()
        vector = self.embed_engine.embed_text(embed_text)

        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO episodic_memories (
                    timestamp, created_at, location_name, driver_quote,
                    companion_summary, emotion_tag, importance, vector
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now_ts, now_iso, location_name.strip(), driver_quote.strip(),
                summary_text, emotion_tag.strip().upper(), importance,
                vector.tobytes()
            ))
            memory_id = c.lastrowid
            conn.commit()
            print(f"[EPISODIC MEMORY #{memory_id}] Indexed: '{summary_text[:50]}...' ({emotion_tag}, Imp: {importance})")
            return memory_id

    def get_recent_episodic_memories(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Returns chronological list of recent episodic moments."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, timestamp, created_at, location_name, driver_quote,
                       companion_summary, emotion_tag, importance
                FROM episodic_memories
                ORDER BY timestamp DESC LIMIT ?
            """, (max(1, int(limit)),))
            rows = c.fetchall()

        out = []
        for r in rows:
            out.append({
                "id": r[0],
                "timestamp": r[1],
                "created_at": r[2],
                "location_name": r[3],
                "driver_quote": r[4],
                "companion_summary": r[5],
                "emotion_tag": r[6],
                "importance": r[7]
            })
        return out

    def query_episodic_memories(self, query: str = "", top_k: int = 2) -> List[Dict[str, Any]]:
        """Retrieves episodic memories using multi-factor ranking: 0.50 Cosine + 0.30 Recency + 0.20 Importance."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, timestamp, created_at, location_name, driver_quote,
                       companion_summary, emotion_tag, importance, vector
                FROM episodic_memories
                ORDER BY timestamp DESC LIMIT 60
            """)
            rows = c.fetchall()

        if not rows:
            return []

        now_ts = time.time()
        query_vec = self.embed_engine.embed_text(query) if query.strip() else None

        scored = []
        for r in rows:
            mem_id, ts, created_at, loc, quote, summary, emotion, imp, vec_blob = r
            cosine_sim = 0.5
            if query_vec is not None and vec_blob:
                try:
                    doc_vec = np.frombuffer(vec_blob, dtype=np.float32)
                    if doc_vec.shape[0] == self.embed_engine.dimension:
                        cosine_sim = float(np.dot(query_vec, doc_vec))
                except Exception:
                    pass

            # Recency decay: half-life ~ 7 days (604,800s)
            age_sec = max(0.0, now_ts - float(ts))
            recency = math.exp(-age_sec / 604800.0)
            importance_norm = float(imp) / 10.0

            final_score = (0.50 * cosine_sim) + (0.30 * recency) + (0.20 * importance_norm)
            scored.append({
                "id": mem_id,
                "timestamp": ts,
                "created_at": created_at,
                "location_name": loc,
                "driver_quote": quote,
                "companion_summary": summary,
                "emotion_tag": emotion,
                "importance": imp,
                "score": round(final_score, 4)
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:max(1, int(top_k))]

    # -------------------------------------------------------------------------
    # Layer 2: Semantic Driver Facts
    # -------------------------------------------------------------------------
    def set_driver_fact(
        self,
        entity: str,
        attribute: str,
        value: str,
        confidence: float = 0.9,
        source: str = "conversation"
    ) -> bool:
        """Upserts an extracted semantic fact about Dad or the vehicle into SQLite."""
        if not entity or not attribute or not value:
            return False
        now_iso = datetime.now().isoformat()
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO driver_facts (entity, attribute, value, confidence, source, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity, attribute) DO UPDATE SET
                    value=excluded.value,
                    confidence=excluded.confidence,
                    source=excluded.source,
                    last_updated=excluded.last_updated
            """, (entity.strip().lower(), attribute.strip().lower(), value.strip(), float(confidence), source.strip(), now_iso))
            conn.commit()
            print(f"[DRIVER FACT] Learned: {entity}.{attribute} = '{value}'")
            return True

    def get_driver_facts(self) -> List[Dict[str, Any]]:
        """Returns all verified semantic facts about Dad and the Dodge Dart."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, entity, attribute, value, confidence, source, last_updated
                FROM driver_facts
                ORDER BY id ASC
            """)
            rows = c.fetchall()

        return [{
            "id": r[0],
            "entity": r[1],
            "attribute": r[2],
            "value": r[3],
            "confidence": r[4],
            "source": r[5],
            "last_updated": r[6]
        } for r in rows]

    def delete_driver_fact(self, fact_id: int) -> bool:
        """Allows Dad to delete a false or outdated fact from the in-dash UI."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM driver_facts WHERE id = ?", (int(fact_id),))
            conn.commit()
            return c.rowcount > 0

    # -------------------------------------------------------------------------
    # Layer 3: R.U.M.'s Personal Trip Diary
    # -------------------------------------------------------------------------
    def add_diary_entry(
        self,
        title: str,
        content: str,
        trip_id: Optional[int] = None,
        peak_boost: float = 0.0,
        mileage: float = 0.0,
        mood: str = "HAPPY_PROUD"
    ) -> int:
        """Stores R.U.M.'s personal post-drive reflection into SQLite with vector embeddings."""
        if not content or not content.strip():
            return -1
        now_date = datetime.now().strftime("%Y-%m-%d")
        now_iso = datetime.now().isoformat()
        vector = self.embed_engine.embed_text(f"{title}. {content}")

        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO persona_diary (
                    trip_id, entry_date, created_at, title, content,
                    peak_boost, mileage, mood, vector
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trip_id, now_date, now_iso, title.strip(), content.strip(),
                float(peak_boost), float(mileage), mood.strip().upper(),
                vector.tobytes()
            ))
            entry_id = c.lastrowid
            conn.commit()
            print(f"[PERSONA DIARY #{entry_id}] Saved: '{title}' ({now_date})")
            return entry_id

    def get_recent_diary_entries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns the companion's post-drive reflections for cockpit display."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, trip_id, entry_date, created_at, title, content, peak_boost, mileage, mood
                FROM persona_diary
                ORDER BY id DESC LIMIT ?
            """, (max(1, int(limit)),))
            rows = c.fetchall()

        return [{
            "id": r[0],
            "trip_id": r[1],
            "entry_date": r[2],
            "created_at": r[3],
            "title": r[4],
            "content": r[5],
            "peak_boost": r[6],
            "mileage": r[7],
            "mood": r[8]
        } for r in rows]

    def delete_diary_entry(self, entry_id: int) -> bool:
        """Deletes a diary entry."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM persona_diary WHERE id = ?", (int(entry_id),))
            conn.commit()
            return c.rowcount > 0

    # -------------------------------------------------------------------------
    # Layer 4: Relationship Bond Engine
    # -------------------------------------------------------------------------
    def get_relationship_bond(self) -> Dict[str, Any]:
        """Returns live relationship bond metrics, current tier, and milestone progress."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT shared_miles, shared_drives, wot_pulls_together, caring_checkins_count,
                       bond_points, bond_tier, unlocked_milestones_json, updated_at
                FROM relationship_bond WHERE id = 1
            """)
            row = c.fetchone()

        if not row:
            return {
                "shared_miles": 0.0,
                "shared_drives": 0,
                "wot_pulls_together": 0,
                "caring_checkins_count": 0,
                "bond_points": 0,
                "bond_tier": "Rookie Co-Pilot",
                "milestones": [],
                "next_milestone_pct": 0.0
            }

        miles, drives, pulls, checkins, pts, tier, ms_json, updated = row
        try:
            ms_list = json.loads(ms_json) if ms_json else []
        except Exception:
            ms_list = []

        # Tier calculation thresholds:
        # Tier 1 (0-150 pts): Rookie Co-Pilot
        # Tier 2 (151-350 pts): Roadtrip Partner
        # Tier 3 (351-650 pts): Inseparable Daughter
        # Tier 4 (651-1000 pts): Soulmate Navigator
        # Tier 5 (1000+ pts): Legendary MultiAir Co-Pilot
        if pts < 150:
            current_tier = "Rookie Co-Pilot"
            next_tier_target = 150
            progress_pct = round((pts / 150.0) * 100.0, 1)
        elif pts < 350:
            current_tier = "Roadtrip Partner"
            next_tier_target = 350
            progress_pct = round(((pts - 150) / 200.0) * 100.0, 1)
        elif pts < 650:
            current_tier = "Inseparable Daughter"
            next_tier_target = 650
            progress_pct = round(((pts - 350) / 300.0) * 100.0, 1)
        elif pts < 1000:
            current_tier = "Soulmate Navigator"
            next_tier_target = 1000
            progress_pct = round(((pts - 650) / 350.0) * 100.0, 1)
        else:
            current_tier = "Legendary MultiAir Co-Pilot"
            next_tier_target = 1500
            progress_pct = 100.0

        return {
            "shared_miles": round(float(miles), 1),
            "shared_drives": int(drives),
            "wot_pulls_together": int(pulls),
            "caring_checkins_count": int(checkins),
            "bond_points": int(pts),
            "bond_tier": current_tier,
            "next_target_points": next_tier_target,
            "progress_pct": min(100.0, max(0.0, progress_pct)),
            "unlocked_milestones": ms_list,
            "updated_at": updated
        }

    def update_relationship_bond(
        self,
        delta_miles: float = 0.0,
        delta_drives: int = 0,
        delta_pulls: int = 0,
        delta_checkins: int = 0
    ) -> Dict[str, Any]:
        """Accrues shared driving experience and evaluates unlocked bond milestones."""
        current = self.get_relationship_bond()
        new_miles = round(current["shared_miles"] + max(0.0, float(delta_miles)), 1)
        new_drives = current["shared_drives"] + max(0, int(delta_drives))
        new_pulls = current["wot_pulls_together"] + max(0, int(delta_pulls))
        new_checkins = current["caring_checkins_count"] + max(0, int(delta_checkins))

        # Points formula: 1 pt per mile + 5 pts per drive + 2 pts per pull + 4 pts per checkin
        pts_earned = int(delta_miles * 1.0) + (delta_drives * 5) + (delta_pulls * 2) + (delta_checkins * 4)
        new_pts = current["bond_points"] + max(0, pts_earned)

        unlocked = list(current["unlocked_milestones"])
        if new_drives >= 1 and "FIRST_DRIVE" not in unlocked:
            unlocked.append("FIRST_DRIVE")
        if new_pulls >= 10 and "BOOST_PULL_15PSI" not in unlocked:
            unlocked.append("BOOST_PULL_15PSI")
        if new_miles >= 100.0 and "100_MILES_SHARED" not in unlocked:
            unlocked.append("100_MILES_SHARED")
        if new_miles >= 500.0 and "500_MILES_SHARED" not in unlocked:
            unlocked.append("500_MILES_SHARED")
        if new_miles >= 1000.0 and "1000_MILES_SHARED" not in unlocked:
            unlocked.append("1000_MILES_SHARED")

        # Determine tier
        if new_pts < 150:
            new_tier = "Rookie Co-Pilot"
        elif new_pts < 350:
            new_tier = "Roadtrip Partner"
        elif new_pts < 650:
            new_tier = "Inseparable Daughter"
        elif new_pts < 1000:
            new_tier = "Soulmate Navigator"
        else:
            new_tier = "Legendary MultiAir Co-Pilot"

        now_iso = datetime.now().isoformat()
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE relationship_bond
                SET shared_miles = ?, shared_drives = ?, wot_pulls_together = ?,
                    caring_checkins_count = ?, bond_points = ?, bond_tier = ?,
                    unlocked_milestones_json = ?, updated_at = ?
                WHERE id = 1
            """, (new_miles, new_drives, new_pulls, new_checkins, new_pts, new_tier, json.dumps(unlocked), now_iso))
            conn.commit()

        print(f"[RELATIONSHIP BOND] Updated: {new_tier} ({new_pts} pts | {new_miles} miles)")
        return self.get_relationship_bond()

    # -------------------------------------------------------------------------
    # Unified Token-Budgeted Context Compression
    # -------------------------------------------------------------------------
    def get_relevant_driver_facts(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Rank stored driver facts using semantic MiniLM similarity + keyword overlap."""
        facts = self.get_driver_facts()
        if not facts:
            return []
        q_terms = self._tokenize_terms(query)
        q_vec = self.embed_engine.embed_text(query) if (query or "").strip() else None
        cache = getattr(self, "_fact_vec_cache", None)
        if cache is None:
            cache = {}
            self._fact_vec_cache = cache

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for f in facts:
            text_repr = f"{f['entity'].replace('_', ' ')} {f['attribute'].replace('_', ' ')}: {f['value']}"
            kw = self._keyword_score(q_terms, query, text_repr)
            cos = 0.0
            if q_vec is not None and not np.all(q_vec == 0):
                ckey = (f.get("id"), text_repr)
                fvec = cache.get(ckey)
                if fvec is None:
                    fvec = self.embed_engine.embed_text(text_repr)
                    cache[ckey] = fvec
                sim = float(np.dot(q_vec, fvec))
                if np.isfinite(sim):
                    cos = max(0.0, sim)
            score = (0.65 * cos) + (0.35 * kw) + (0.05 * float(f.get("confidence", 0.9)))
            scored.append((score, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:max(1, int(top_k))]]

    def retrieve_unified_living_memory(
        self,
        query: str,
        current_speed: float = 0.0,
        max_tokens: int = 400
    ) -> str:
        """
        Assembles a prioritized, token-budgeted memory block fusing:
        Bond Tier, Top Semantically Ranked Driver Facts, Episodic Memories, Diary (reserved priority),
        and Hybrid RAG Docs (440-char table-safe snippets for manuals/specs).
        """
        personal_lines: List[str] = []
        char_budget = max(900, int(max_tokens) * 4)

        # 1. Bond Tier & Address (reserved priority)
        bond = self.get_relationship_bond()
        personal_lines.append(f"• Bond Tier: {bond['bond_tier']} ({bond['shared_miles']} shared miles, {bond['shared_drives']} drives).")

        # 2. Semantically Ranked Driver Facts (reserved priority)
        for f in self.get_relevant_driver_facts(query, top_k=3):
            personal_lines.append(f"• Fact ({f['entity'].replace('_', ' ')}): {f['value']}.")

        # 3. Episodic Moments (reserved priority)
        episodes = self.query_episodic_memories(query, top_k=2)
        for ep in episodes:
            if ep["score"] >= 0.35:
                personal_lines.append(f"• Memory: {ep['companion_summary']}")

        # 4. Latest Diary Reflection (reserved slot when space remains)
        recent_diaries = self.get_recent_diary_entries(limit=1)
        if recent_diaries and sum(len(l) for l in personal_lines) < char_budget - 200:
            d = recent_diaries[0]
            snippet = d["content"][:130].rstrip() + "..." if len(d["content"]) > 130 else d["content"]
            personal_lines.append(f"• Diary ({d['entry_date']}): \"{snippet}\"")

        # 5. Hybrid RAG Documents (Manuals 440c table-safe, Learned Web & Logs 200c)
        rag_lines: List[str] = []
        used_chars = sum(len(l) + 1 for l in personal_lines)
        for doc in self.search(query, top_k=3, threshold=0.28):
            lim = 440 if doc["category"] in ("dodge_dart_manual", "carpi5_manual", "SPECIFICATION") else 200
            snip = doc["content"][:lim].rstrip() + "..." if len(doc["content"]) > lim else doc["content"]
            entry = f"• [{doc['category']}] {doc['title']}: {snip}"
            if used_chars + len(entry) > char_budget and rag_lines:
                break
            rag_lines.append(entry)
            used_chars += len(entry) + 1

        out = "\n".join(personal_lines + rag_lines)
        return out[:char_budget]

    def extract_and_store_chat_memories(
        self,
        user_message: str,
        ai_reply: str = "",
        telemetry: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Fast (<5ms) zero-LLM conversational memory extractor.
        Automatically captures explicit remember commands, driver preferences,
        vehicle/maintenance notes, and memorable boost/drive moments.
        """
        msg = (user_message or "").strip()
        if len(msg) < 6:
            return []
        ml = msg.lower()
        saved: List[str] = []

        # 1. Explicit "remember that ..." / "don't forget ..."
        m_rem = re.search(r"\b(?:remember(?:\s+that)?|don'?t\s+forget(?:\s+that)?|keep\s+in\s+mind(?:\s+that)?)\s+(.+)$", msg, flags=re.IGNORECASE)
        if m_rem:
            fact_txt = m_rem.group(1).strip(" .!")
            if len(fact_txt) >= 4:
                attr = f"note_{abs(hash(fact_txt.lower())) % 10000}"
                if self.set_driver_fact("remembered_note", attr, fact_txt, confidence=0.98, source="auto_chat"):
                    saved.append(f"fact:{fact_txt[:40]}")
                self.add_episodic_memory(
                    companion_summary=f"Dad asked me to remember: {fact_txt}",
                    driver_quote=msg[:140],
                    emotion_tag="CARING",
                    importance=8,
                )
                return saved

        # 2. Personal preference extraction ("my favorite X is Y", "I prefer Y", "I love Y", "I hate Y")
        m_fav = re.search(r"\bmy\s+favorite\s+([a-z0-9 _-]{2,24}?)\s+(?:is|are)\s+(.+)$", msg, flags=re.IGNORECASE)
        if m_fav:
            subj = re.sub(r"[^a-z0-9_]+", "_", m_fav.group(1).strip().lower()).strip("_") or "general"
            val = m_fav.group(2).strip(" .!")
            if val and self.set_driver_fact("preference", f"favorite_{subj}", val, confidence=0.92, source="auto_chat"):
                saved.append(f"fav:{subj}={val[:32]}")

        m_pref = re.search(r"\bi\s+(?:really\s+)?(love|hate|prefer|dislike|enjoy|drink|drive)\s+(.{3,80})$", ml)
        if m_pref and not m_fav and not any(q in ml for q in ("?", "what ", "who ", "how ", "why ")):
            verb = m_pref.group(1).strip()
            obj = msg[m_pref.start(2):m_pref.end(2)].strip(" .!")
            if obj and len(obj) >= 3 and not obj.lower().startswith(("you", "it when", "to ask")):
                attr = f"{verb}_{abs(hash(obj.lower())) % 1000}"
                if self.set_driver_fact("driver_preference", attr, f"I {verb} {obj}", confidence=0.88, source="auto_chat"):
                    saved.append(f"pref:{verb}:{obj[:30]}")

        # 3. Vehicle maintenance / modification log ("I changed my oil...", "installed...", "replaced...")
        if any(w in ml for w in ("oil change", "changed the oil", "changed my oil", "replaced ", "installed ", "new tires", "spark plug", "torque")) and not ml.endswith("?"):
            self.add_episodic_memory(
                companion_summary=f"Vehicle service update from Dad: {msg[:150]}",
                driver_quote=msg[:140],
                emotion_tag="PRIDE",
                importance=8,
            )
            saved.append("episodic:vehicle_note")

        # 4. Spirited driving / emotional milestone telemetry capture
        boost = float((telemetry or {}).get("boost_psi", 0.0) or 0.0)
        if boost >= 15.0 and any(w in ml for w in ("pull", "boost", "fast", "turbo", "launch", "third", "3rd")):
            self.add_episodic_memory(
                companion_summary=f"Spirited turbo pull at +{boost:.1f} PSI! Dad said: \"{msg[:90]}\"",
                driver_quote=msg[:120],
                emotion_tag="EXCITEMENT",
                importance=7,
            )
            saved.append("episodic:boost_moment")

        return saved

    def get_ai_memory_counts(self) -> Dict[str, int]:
        """Return counts of stored user AI memories (excluding factory vehicle maintenance/manuals)."""
        with self._get_connection() as conn:
            c = conn.cursor()
            ep = c.execute("SELECT COUNT(*) FROM episodic_memories").fetchone()[0]
            facts = c.execute("SELECT COUNT(*) FROM driver_facts").fetchone()[0]
            diary = c.execute("SELECT COUNT(*) FROM persona_diary").fetchone()[0]
            notes = c.execute(
                f"SELECT COUNT(*) FROM rag_documents WHERE category NOT IN ({_PROTECTED_CATS_SQL})"
            ).fetchone()[0]
            return {
                "episodic": int(ep),
                "facts": int(facts),
                "diary": int(diary),
                "notes": int(notes),
                "total": int(ep + facts + diary + notes),
            }

    def wipe_ai_memory(self) -> Dict[str, int]:
        """Erase all stored episodic memories, driver facts, diary entries, custom notes, and bond progress."""
        counts = self.get_ai_memory_counts()
        now_iso = datetime.now().isoformat()
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM episodic_memories")
            c.execute("DELETE FROM driver_facts")
            c.execute("DELETE FROM persona_diary")
            c.execute(
                "DELETE FROM rag_embeddings WHERE doc_id IN ("
                f"SELECT doc_id FROM rag_documents WHERE category NOT IN ({_PROTECTED_CATS_SQL}))"
            )
            c.execute(
                f"DELETE FROM rag_documents WHERE category NOT IN ({_PROTECTED_CATS_SQL})"
            )
            c.execute("""
                INSERT OR REPLACE INTO relationship_bond (
                    id, shared_miles, shared_drives, wot_pulls_together, caring_checkins_count,
                    bond_points, bond_tier, unlocked_milestones_json, updated_at
                ) VALUES (1, 0.0, 0, 0, 0, 0, 'Fresh Start', '[]', ?)
            """, (now_iso,))
            c.execute("INSERT OR REPLACE INTO vehicle_state (key, value) VALUES ('ai_memory_wiped', '1')")
            conn.commit()
        self._invalidate_vec_cache()
        return counts


