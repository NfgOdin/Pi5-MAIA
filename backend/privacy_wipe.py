"""
privacy_wipe.py - Tiered Privacy Inventory & Data Wipe Engine for CarPi5

Provides live disk/database inventory and atomic selective or full personal data wipe across:
1. ai_memory      - Episodic memories, driver facts, diary entries, custom RAG notes, bond, ai_memory.json, speech log
2. voice_clips    - TTS WAV cache (storage/tts_cache), last_speech.wav, RAM audio clips, viseme ring buffer
3. phone_accounts - Call history, SMS threads, synced/saved contacts, Google OAuth tokens, saved BT pairing
4. trips_logs     - Telemetry trips SQLite history, exported trip ZIP archives, runtime logs

Preserves factory Dodge Dart maintenance intervals/manuals, offline AZ OSM navigation graph,
installed GGUF/ONNX AI models, and OS/persona configuration files.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

ALL_WIPE_CATEGORIES = ("ai_memory", "voice_clips", "phone_accounts", "trips_logs")


def _base_dir(state: Any) -> Path:
    bd = getattr(state, "base_dir", None)
    if bd:
        return Path(bd)
    return Path(__file__).resolve().parent.parent


def _dir_stats(directory: Path) -> Dict[str, Any]:
    if not directory.exists():
        return {"files": 0, "bytes": 0}
    files = 0
    total_bytes = 0
    try:
        for p in directory.rglob("*"):
            if p.is_file():
                files += 1
                try:
                    total_bytes += p.stat().st_size
                except OSError:
                    pass
    except Exception:
        pass
    return {"files": files, "bytes": total_bytes}


def get_privacy_inventory(state: Any) -> Dict[str, Any]:
    """Return live item counts and byte usage for every wipeable personal data category."""
    base = _base_dir(state)
    storage_dir = base / "storage"

    # 1. AI Memory & Chat
    rag = getattr(state, "rag", None)
    rag_counts = {"episodic": 0, "facts": 0, "diary": 0, "notes": 0, "total": 0}
    if rag and hasattr(rag, "get_ai_memory_counts"):
        try:
            rag_counts = rag.get_ai_memory_counts()
        except Exception:
            pass
    llm = getattr(state, "llm", None)
    speech_log_count = len(getattr(llm, "speech_log", []) or []) if llm else 0
    ai_notes_count = len((getattr(getattr(llm, "memory_mgr", None), "memory", {}) or {}).get("known_notes", []))
    ai_mem_file = base / "backend" / "ai" / "ai_memory.json"
    ai_bytes = ai_mem_file.stat().st_size if ai_mem_file.exists() else 0

    # 2. Voice Clips & Cache
    audio = getattr(state, "audio", None)
    cache_stats = {}
    if audio and hasattr(audio, "get_cache_stats"):
        try:
            cache_stats = audio.get_cache_stats() or {}
        except Exception:
            pass
    tts_dir_stats = _dir_stats(storage_dir / "tts_cache")
    last_wav = base / "ui" / "web_preview" / "last_speech.wav"
    last_wav_bytes = last_wav.stat().st_size if last_wav.exists() else 0
    ram_dir = Path(os.environ.get("CARPI5_RAM_AUDIO_DIR", "/dev/shm/carpi5_audio"))
    ram_stats = _dir_stats(ram_dir) if os.name != "nt" and ram_dir.exists() else {"files": 0, "bytes": 0}
    ring_clips = len(getattr(audio, "_speech_clips", {}) or {}) if audio else 0
    voice_files = int(cache_stats.get("cached_phrases", tts_dir_stats["files"])) + (1 if last_wav.exists() else 0) + ram_stats["files"] + ring_clips
    voice_bytes = int(tts_dir_stats["bytes"] + last_wav_bytes + ram_stats["bytes"])

    # 3. Phone, SMS & Accounts
    phone = getattr(state, "phone", None)
    sms = getattr(state, "sms", None)
    contacts_count = len(phone.kinship.get_contacts()) if (phone and hasattr(phone, "kinship")) else 0
    calls_count = len(getattr(phone, "history", []) or []) if phone else 0
    sms_threads = sms.get_threads() if (sms and hasattr(sms, "get_threads")) else {}
    sms_msg_count = sum(len(v) for v in sms_threads.values()) if isinstance(sms_threads, dict) else 0
    oauth_file = base / "backend" / "ai" / "google_oauth_tokens.json"
    bt_saved_file = base / "backend" / "bluetooth_saved.json"
    has_oauth = oauth_file.exists() and oauth_file.stat().st_size > 4
    has_bt_saved = bt_saved_file.exists() and bt_saved_file.stat().st_size > 2
    phone_items = contacts_count + calls_count + sms_msg_count + (1 if has_oauth else 0) + (1 if has_bt_saved else 0)

    # 4. Trips & Logs
    trip_logger = getattr(state, "trip_logger", None)
    trips_count = 0
    if trip_logger and hasattr(trip_logger, "get_recent_trips"):
        try:
            trips_count = len(trip_logger.get_recent_trips(limit=10000) or [])
        except Exception:
            pass
    archives_stats = _dir_stats(storage_dir / "trip_archives")
    logs_stats = _dir_stats(storage_dir / "logs")
    daemon_log = base / "daemon.log"
    shm_log = Path("/dev/shm/daemon.log")
    log_bytes = logs_stats["bytes"] + (daemon_log.stat().st_size if daemon_log.exists() else 0) + (shm_log.stat().st_size if shm_log.exists() else 0)

    return {
        "ai_memory": {
            "label": "AI Memory & Chat",
            "episodic": rag_counts["episodic"],
            "facts": rag_counts["facts"],
            "diary": rag_counts["diary"],
            "notes": rag_counts["notes"] + ai_notes_count,
            "speech_log": speech_log_count,
            "total_items": rag_counts["total"] + ai_notes_count + speech_log_count,
            "bytes": ai_bytes,
            "mb": round(ai_bytes / (1024 * 1024), 2),
        },
        "voice_clips": {
            "label": "Saved Voice Clips & Cache",
            "cached_phrases": int(cache_stats.get("cached_phrases", tts_dir_stats["files"])),
            "ring_clips": ring_clips,
            "ram_files": ram_stats["files"],
            "has_last_speech": last_wav.exists(),
            "total_items": voice_files,
            "bytes": voice_bytes,
            "mb": round(voice_bytes / (1024 * 1024), 2),
        },
        "phone_accounts": {
            "label": "Phone, SMS, Contacts & Accounts",
            "contacts": contacts_count,
            "calls": calls_count,
            "sms_messages": sms_msg_count,
            "sms_threads": len(sms_threads),
            "oauth_linked": has_oauth,
            "bt_saved": has_bt_saved,
            "total_items": phone_items,
        },
        "trips_logs": {
            "label": "Trips, Telemetry & Logs",
            "trips": trips_count,
            "archive_files": archives_stats["files"],
            "log_files": logs_stats["files"],
            "total_items": trips_count + archives_stats["files"] + logs_stats["files"],
            "bytes": archives_stats["bytes"] + log_bytes,
            "mb": round((archives_stats["bytes"] + log_bytes) / (1024 * 1024), 2),
        },
    }


def _wipe_ai_memory(state: Any, base: Path) -> Dict[str, Any]:
    res: Dict[str, Any] = {}
    rag = getattr(state, "rag", None)
    if rag and hasattr(rag, "wipe_ai_memory"):
        res["rag"] = rag.wipe_ai_memory()
    llm = getattr(state, "llm", None)
    if llm:
        if hasattr(llm, "memory_mgr") and hasattr(llm.memory_mgr, "wipe_memory"):
            res["memory_mgr"] = llm.memory_mgr.wipe_memory()
        if hasattr(llm, "speech_log") and isinstance(llm.speech_log, list):
            res["speech_log_cleared"] = len(llm.speech_log)
            llm.speech_log.clear()
    else:
        ai_mem = base / "backend" / "ai" / "ai_memory.json"
        if ai_mem.exists():
            ai_mem.write_text(json.dumps({"total_drives": 0, "all_time_stats": {}, "last_session_stats": {}, "recent_greeting_hashes": [], "known_notes": [], "wiped": True}, indent=2), encoding="utf-8")
    return res


def _wipe_voice_clips(state: Any, base: Path) -> Dict[str, Any]:
    audio = getattr(state, "audio", None)
    if audio and hasattr(audio, "clear_voice_clips_and_ram"):
        res = audio.clear_voice_clips_and_ram()
    else:
        res = {"cache": {}, "ring_clips_cleared": 0, "ram_files_removed": 0, "last_speech_removed": 0}
        tts_dir = base / "storage" / "tts_cache"
        if tts_dir.exists():
            removed = 0
            for item in tts_dir.iterdir():
                if item.is_file():
                    item.unlink(missing_ok=True)
                    removed += 1
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    removed += 1
            res["cache"] = {"files_removed": removed}
    last_wav = base / "ui" / "web_preview" / "last_speech.wav"
    if last_wav.exists():
        try:
            last_wav.unlink()
            res["last_speech_removed"] = 1
        except OSError:
            pass
    return res


def _wipe_phone_accounts(state: Any, base: Path) -> Dict[str, Any]:
    res: Dict[str, Any] = {}
    phone = getattr(state, "phone", None)
    if phone and hasattr(phone, "clear_all_phone_data"):
        res["phone"] = phone.clear_all_phone_data()
    else:
        for rel, empty_val in (("storage/call_history.json", []), ("config/family_kinship.json", {"contacts": []})):
            p = base / rel
            if p.exists():
                p.write_text(json.dumps(empty_val, indent=2), encoding="utf-8")
    sms = getattr(state, "sms", None)
    if sms and hasattr(sms, "clear_all_threads"):
        res["sms"] = sms.clear_all_threads()
    else:
        sp = base / "storage" / "sms_threads.json"
        if sp.exists():
            sp.write_text("{}", encoding="utf-8")

    llm = getattr(state, "llm", None)
    if llm and hasattr(llm, "google_auth") and hasattr(llm.google_auth, "logout"):
        try:
            llm.google_auth.logout()
            res["google_oauth_cleared"] = True
        except Exception:
            pass
    oauth_file = base / "backend" / "ai" / "google_oauth_tokens.json"
    if oauth_file.exists():
        try:
            oauth_file.unlink()
            res["google_oauth_cleared"] = True
        except OSError:
            pass

    bt_file = base / "backend" / "bluetooth_saved.json"
    if bt_file.exists():
        try:
            bt_file.unlink()
            res["bluetooth_saved_cleared"] = True
        except OSError:
            pass
    return res


def _wipe_trips_logs(state: Any, base: Path) -> Dict[str, Any]:
    res: Dict[str, Any] = {}
    trip_logger = getattr(state, "trip_logger", None)
    if trip_logger and hasattr(trip_logger, "clear_all_trips"):
        try:
            res["trips_cleared"] = bool(trip_logger.clear_all_trips())
        except Exception as e:
            res["trips_error"] = str(e)
    archives_dir = base / "storage" / "trip_archives"
    arch_removed = 0
    if archives_dir.exists():
        for item in archives_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    arch_removed += 1
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    arch_removed += 1
            except OSError:
                pass
    res["archives_removed"] = arch_removed

    logs_dir = base / "storage" / "logs"
    logs_removed = 0
    if logs_dir.exists():
        for item in logs_dir.rglob("*"):
            if item.is_file():
                try:
                    item.unlink()
                    logs_removed += 1
                except OSError:
                    pass
    for log_path in (base / "daemon.log", base / "storage" / "daemon.log", Path("/dev/shm/daemon.log")):
        if log_path.exists():
            try:
                log_path.write_text("", encoding="utf-8")
            except OSError:
                pass
    res["logs_removed"] = logs_removed
    return res


def execute_privacy_wipe(state: Any, categories: Optional[List[str]] = None) -> Dict[str, Any]:
    """Wipe selected categories (or all categories when ['all'] or empty/unspecified all=True)."""
    base = _base_dir(state)
    raw_cats = categories or list(ALL_WIPE_CATEGORIES)
    if "all" in raw_cats:
        selected = list(ALL_WIPE_CATEGORIES)
    else:
        selected = [c for c in raw_cats if c in ALL_WIPE_CATEGORIES]
    if not selected:
        return {"status": "error", "message": "No valid wipe categories selected.", "wiped": {}}

    wiped: Dict[str, Any] = {}
    if "ai_memory" in selected:
        wiped["ai_memory"] = _wipe_ai_memory(state, base)
    if "voice_clips" in selected:
        wiped["voice_clips"] = _wipe_voice_clips(state, base)
    if "phone_accounts" in selected:
        wiped["phone_accounts"] = _wipe_phone_accounts(state, base)
    if "trips_logs" in selected:
        wiped["trips_logs"] = _wipe_trips_logs(state, base)

    return {
        "status": "ok",
        "categories": selected,
        "wiped": wiped,
        "inventory": get_privacy_inventory(state),
    }
