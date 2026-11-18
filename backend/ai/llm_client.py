"""

llm_client.py - Multi-Backend AI Engine for M.A.I.A. (Dodge Dart Companion)

Supports:

1. BUILTIN (Default): Dynamic context-aware procedural engine with telemetry-driven responses & persistent memory.

2. TAILSCALE_OLLAMA: Connects over Tailscale to home desktop GPU running Ollama.

3. LOCAL_OLLAMA: Connects to local Ollama / llama.cpp on the Pi.

4. CLOUD_API: Connects to cloud API (Gemini / OpenAI compatible).

5. Dynamic JSON Persona Loader from config/personas/*.json

"""



import os
import re
from pathlib import Path

import json

import time

import random

import urllib.request

import urllib.error

from typing import Dict, List, Any, Optional, Callable

try:
    from backend.ai.memory_manager import MemoryManager
except ImportError:
    try:
        from ai.memory_manager import MemoryManager
    except ImportError:
        from memory_manager import MemoryManager

try:
    from backend.ai.web_search import is_ephemeral_query, search_web_snippets, should_search_web
except ImportError:
    try:
        from ai.web_search import is_ephemeral_query, search_web_snippets, should_search_web
    except ImportError:
        from web_search import is_ephemeral_query, search_web_snippets, should_search_web



def load_personas_from_dir(persona_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:

    """Loads all *.json persona profiles from the config/personas directory."""

    if not persona_dir:

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        persona_dir = os.path.join(base_dir, "config", "personas")



    personas: Dict[str, Dict[str, Any]] = {}



    if os.path.exists(persona_dir):
        for fname in sorted(os.listdir(persona_dir)):
            if fname.endswith(".json") and not fname.endswith(".example"):
                fpath = os.path.join(persona_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        p_id = data.get("id", os.path.splitext(fname)[0].upper())
                        p_dict = dict(data)
                        p_dict.setdefault("id", p_id)
                        p_dict.setdefault("name", p_id)
                        p_dict.setdefault("full_name", data.get("name", p_id))
                        p_dict.setdefault("description", "")
                        p_dict.setdefault("gender", "female")
                        p_dict.setdefault("age_spirit", "")
                        p_dict.setdefault("archetype", "Cockpit AI Companion")
                        p_dict.setdefault("avatar_image", "assets/pics/splash.png")
                        p_dict.setdefault("boot_splash_image", "assets/pics/splash.png")
                        p_dict.setdefault("boot_splash_video", "")
                        p_dict.setdefault("boot_splash_title", f"{p_dict['name']} • CARPI5")
                        p_dict.setdefault("boot_splash_subtitle", p_dict.get("subtitle") or p_dict["archetype"])
                        p_dict.setdefault("acknowledgments_folder", str(p_id).lower())
                        p_dict.setdefault("elevenlabs_voice_id", "")
                        if p_dict.get("tts_pitch") is None and p_dict.get("pitch_factor") is not None:
                            p_dict["tts_pitch"] = p_dict["pitch_factor"]
                        p_dict.setdefault("speech_speed", 1.00)
                        p_dict.setdefault("vrm_defaults", {})
                        p_dict.setdefault("copilot_callouts", {})
                        p_dict.setdefault("touch_interactions", {})
                        p_dict.setdefault("banned_touch_zones", [])
                        p_dict.setdefault("prompt", "")
                        p_dict.setdefault("default", False)
                        personas[p_id] = p_dict
                except Exception as e:
                    print(f"[PERSONA] Error loading {fname}: {e}")



    # Synthesize a neutral companion fallback only if config/personas/ is empty
    if not personas:
        personas["COMPANION"] = {
            "id": "COMPANION",
            "name": "Companion",
            "full_name": "CarPi5 Cockpit VRM Companion",
            "description": "Devoted, intelligent 3D VRM cockpit co-pilot inside the Dodge Dart dashboard.",
            "gender": "female",
            "archetype": "Cockpit VRM Co-Pilot",
            "avatar_image": "/assets/pics/splash.png",
            "boot_splash_image": "assets/pics/splash.png",
            "boot_splash_video": "",
            "prompt": (
                "You are {persona_name}, the 3D VRM AI co-pilot inside the dashboard of {driver_address}'s 2013 Dodge Dart 1.4L Turbo MultiAir. "
                "Address the driver as '{driver_address}'. Keep replies concise and helpful (1-3 sentences)."
            ),
            "default": True,
        }

    return personas


def get_default_persona_id(personas: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """Resolve the active default persona ID cleanly from loaded persona configs."""
    pool = personas if isinstance(personas, dict) else PERSONALITIES
    for pid, pdata in pool.items():
        if isinstance(pdata, dict) and pdata.get("default"):
            return pid
    return next(iter(pool.keys()), "COMPANION")


PERSONALITIES = load_personas_from_dir()



class LLMClient:

    def __init__(self, config_file: Optional[str] = None):

        self._explicit_config = (config_file is not None)
        self.config_file = config_file or os.path.join(os.path.dirname(__file__), "ai_settings.json")

        self.settings = self.load_settings()

        self.chat_history: List[Dict[str, str]] = []

        self.speech_log: List[Dict[str, Any]] = []
        self.last_turn_meta: Dict[str, Any] = {}

        self.personas = load_personas_from_dir()
        self.lorebooks = {}
        self.load_lorebooks()

        self.memory_mgr = MemoryManager()

        self.boot_info = self.memory_mgr.record_boot()

        import threading

        self._llama_lock = threading.Lock()

        self._llama_model = None

        self._llama_loading = False

        self._saved_system_state = None
        self._saved_system_prompt_text = None
        self.circadian_override = None
        self.ai_core_status = "warming" if self.settings.get("mode") in ("LOCAL", "LOCAL_GGUF") else "online"



        # Google OAuth & Gemini Client

        try:

            from backend.ai.google_auth import GoogleAuthManager

        except ImportError:

            try:

                from ai.google_auth import GoogleAuthManager

            except ImportError:

                from google_auth import GoogleAuthManager

        self.google_auth = GoogleAuthManager()



        # Automatically warm up the local GGUF model in the background on Pi 5

        # Phase 8 Offline Vector Memory & MultiAir Maintenance RAG
        try:
            from backend.ai.rag_memory import RagMemoryEngine
            self.rag_memory = RagMemoryEngine()
        except ImportError:
            try:
                from ai.rag_memory import RagMemoryEngine
                self.rag_memory = RagMemoryEngine()
            except Exception as e:
                print(f"[LLM] RAG memory init note: {e}")
                self.rag_memory = None

        if self.settings.get("mode") in ("LOCAL", "LOCAL_GGUF"):

            threading.Thread(target=self._preload_local_gguf, daemon=True).start()




    def load_lorebooks(self):
        """Loads modular domain lorebooks and web knowledge from config/lorebooks/."""
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "lorebooks")
        if not os.path.exists(base_dir):
            return
        for fname in os.listdir(base_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(base_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        book_id = data.get("id", fname.replace(".json", ""))
                        self.lorebooks[book_id] = data
                except Exception as e:
                    print(f"[LOREBOOK] Error loading {fname}: {e}")
        print(f"[LOREBOOK] Loaded {len(self.lorebooks)} modular knowledge lorebooks.")

    def get_lorebook_injection(self, query: str) -> str:
        """Fast sub-millisecond scored knowledge scanner for grounded domain knowledge and in-dash library injection."""
        q_lower = query.lower()
        q_clean = q_lower.replace("?", " ").replace(".", " ").replace(",", " ").replace("!", " ")
        q_words = set(q_clean.split())
        scored_snippets = []

        for book_id, book in self.lorebooks.items():
            book_keywords = book.get("keywords", [])
            book_match = any(k in q_lower for k in book_keywords)

            facts = book.get("factual_data", {})
            for k, v in facts.items():
                key_words = set(k.lower().replace("_", " ").split())
                overlap = len(q_words.intersection(key_words))
                v_lower = v.lower()
                text_hits = sum(1 for w in q_words if len(w) > 3 and w in v_lower)

                score = 0
                if overlap > 0:
                    score += overlap * 6
                if text_hits > 0:
                    score += text_hits * 2
                if book_match and score > 0:
                    score += 4
                elif book_match and any(w in k.lower() for w in ["engine", "general", "guide", "spec"]):
                    score += 1

                if score > 0:
                    source_title = book.get("title", book_id)
                    scored_snippets.append((score, f"[{source_title} - {k}]: {v}"))

            if "learned_facts" in book:
                for fact_obj in book.get("learned_facts", []):
                    fkws = fact_obj.get("keywords", [])
                    if any(k in q_lower for k in fkws):
                        scored_snippets.append((8, f"[LEARNED KNOWLEDGE]: {fact_obj.get('fact', '')}"))

        scored_snippets.sort(key=lambda x: x[0], reverse=True)
        top = [s[1] for s in scored_snippets[:3]]
        return "\n".join(top) if top else ""

    def set_rag_engine(self, rag_engine: Any) -> None:
        """Bind a shared RagMemoryEngine singleton across daemon, copilot, and LLM."""
        if rag_engine is not None:
            self.rag_memory = rag_engine

    def _learned_knowledge_path(self) -> str:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config",
            "lorebooks",
            "learned_web_knowledge.json",
        )

    def get_learned_facts(self) -> List[Dict[str, Any]]:
        fpath = self._learned_knowledge_path()
        if not os.path.exists(fpath):
            return []
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return list(data.get("learned_facts", [])) if isinstance(data, dict) else []
        except Exception:
            return []

    def delete_learned_fact(self, index_or_keyword: Any) -> bool:
        fpath = self._learned_knowledge_path()
        if not os.path.exists(fpath):
            return False
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            facts = list(data.get("learned_facts", []))
            removed_kw = None
            if isinstance(index_or_keyword, int) or str(index_or_keyword).isdigit():
                idx = int(index_or_keyword)
                if 0 <= idx < len(facts):
                    removed_kw = facts.pop(idx).get("keyword")
            else:
                target_kw = str(index_or_keyword or "").strip().lower()
                new_facts = [row for row in facts if str(row.get("keyword", "")).strip().lower() != target_kw]
                if len(new_facts) != len(facts):
                    facts = new_facts
                    removed_kw = target_kw
            if removed_kw is None:
                return False
            data["learned_facts"] = facts
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.load_lorebooks()
            return True
        except Exception as e:
            print(f"[LOREBOOK] Error deleting learned fact: {e}")
            return False

    def save_learned_fact(self, keyword: str, fact: str, source: str = "web") -> bool:
        """Saves newly learned verified facts into learned_web_knowledge.json and RagMemoryEngine."""
        clean_kw = (keyword or "").strip()
        clean_fact = (fact or "").strip()
        if not clean_kw or not clean_fact:
            return False
        fpath = self._learned_knowledge_path()
        try:
            data = {
                "version": "1.0",
                "description": "Verified knowledge discovered via web search and permanently learned by R.U.M.",
                "learned_facts": [],
            }
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
            facts_list = data.setdefault("learned_facts", [])
            # Deduplicate / update existing keyword
            tokens = [t for t in re.findall(r"[a-z0-9]+", clean_kw.lower()) if len(t) >= 3]
            kws = list(dict.fromkeys([clean_kw.lower()] + tokens[:5]))
            existing = next((r for r in facts_list if str(r.get("keyword", "")).lower() == clean_kw.lower()), None)
            if existing is not None:
                existing["fact"] = clean_fact
                existing["keywords"] = kws
                existing["source"] = source
                existing["learned_at"] = time.time()
            else:
                facts_list.append({
                    "keyword": clean_kw,
                    "keywords": kws,
                    "fact": clean_fact,
                    "source": source,
                    "learned_at": time.time(),
                })
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.load_lorebooks()
            if getattr(self, "rag_memory", None) is not None:
                try:
                    doc_id = f"learned_{abs(hash(clean_kw.lower())) % 1000000}"
                    self.rag_memory.add_document(doc_id, "LEARNED_WEB", clean_kw, clean_fact, metadata={"source": source})
                except Exception:
                    pass
            print(f"[LOREBOOK] Saved learned fact: {clean_kw}")
            return True
        except Exception as e:
            print(f"[LOREBOOK] Error saving fact: {e}")
            return False

    def get_ai_core_status(self) -> str:

        """Returns 'online' if neural core is loaded and ready, else 'warming'."""

        if self.settings.get("mode") not in ("LOCAL", "LOCAL_GGUF"):

            return "online"

        return "online" if self._llama_model is not None else "warming"



    def _preload_local_gguf(self):
        """Loads the local GGUF neural model into RAM and pre-caches the active persona KV state."""
        if self._llama_model is not None:
            self.ai_core_status = "online"
            return
        if self._llama_loading:
            return
        self._llama_loading = True
        self.ai_core_status = "warming"
        
        # CPU Core Pinning: On Linux/Pi 5, pin inference to Cores 2 & 3 to protect UI & Audio on Cores 0 & 1
        try:
            if hasattr(os, "sched_setaffinity"):
                os.sched_setaffinity(0, {2, 3})
                print("[LLM] Inference thread pinned to Cortex-A76 Cores 2 & 3.")
        except Exception as e_pin:
            print(f"[LLM] Core pinning note: {e_pin}")

        gguf_path = self.settings.get("gguf_model_path", "")
        selected = self.settings.get("selected_model", "")

        candidates_dirs = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models"),
            str(Path.home() / "CarPi5" / "models"),
            os.path.expanduser("~/models")
        ]

        # Prioritize abliterated zero-refusal model, then selected model, then standard models
        priority_filenames = [
            "qwen2.5-3b-instruct-abliterated.q4_k_m.gguf"
        ]
        if selected and selected not in priority_filenames:
            priority_filenames.append(selected)
        priority_filenames.extend(["qwen3b.gguf", "qwen2.5-1.5b-instruct-q4_k_m.gguf"])

        found_path = None
        for fname in priority_filenames:
            for cdir in candidates_dirs:
                target = os.path.join(cdir, fname)
                # Verify file exists and is complete (abliterated model is ~1.84GB)
                min_size = 1900000000 if 'abliterated' in fname else 500 * 1024 * 1024
                if os.path.exists(target) and os.path.getsize(target) >= min_size:
                    found_path = target
                    break
            if found_path:
                break

        if found_path:
            gguf_path = found_path

        if gguf_path and os.path.exists(gguf_path):
            try:
                from llama_cpp import Llama
                print(f"[LLM] Preloading local GGUF model: {gguf_path}...")
                with self._llama_lock:
                    self._llama_model = Llama(model_path=gguf_path, n_ctx=2048, n_threads=4, n_batch=512, verbose=False)

                # Pre-evaluate base system prompt into KV-cache using fast batched prompt ingestion
                try:
                    persona = self.get_active_persona()
                    address = self.get_driver_address()
                    base_prompt = persona.get("prompt", "").format(driver_address=address)
                    with self._llama_lock:
                        self._llama_model.create_chat_completion(
                            messages=[{"role": "system", "content": base_prompt}],
                            max_tokens=1
                        )
                        self._saved_system_state = self._llama_model.save_state()
                        self._saved_system_prompt_text = base_prompt
                    print("[LLM] Base KV session state pre-computed. In-car response start latency <800ms!")
                except Exception as e_kv:
                    print(f"[LLM] Note on KV session state caching: {e_kv}")

                self._llama_loading = False
                self.ai_core_status = "online"
                print(f"[LLM] Local neural model warm & ready: {os.path.basename(gguf_path)}! AI Core ONLINE.")
            except Exception as e:
                print(f"[LLM] Error preloading GGUF model: {e}")
                self._llama_loading = False
                self.ai_core_status = "online"
        else:
            self.ai_core_status = "online"
        self._llama_loading = False



    def get_available_gguf_models(self) -> List[Dict[str, Any]]:

        """Scans candidate directories for all .gguf model files."""

        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models"),
            str(Path.home() / "CarPi5" / "models"),
            os.path.expanduser("~/models")
        ]

        found = {}

        for c in candidates:

            if os.path.exists(c):

                try:

                    for f in os.listdir(c):

                        if f.endswith(".gguf") and f not in found:

                            p = os.path.join(c, f)

                            size_mb = round(os.path.getsize(p) / (1024 * 1024), 1)

                            name_display = f.replace(".gguf", "").replace("-", " ").replace("_", " ").title()

                            found[f] = {

                                "filename": f,

                                "path": p,

                                "size_mb": size_mb,

                                "display_name": name_display

                            }

                except Exception as ex:

                    print(f"[LLM] Error scanning {c}: {ex}")

        return list(found.values())



    def swap_gguf_model(self, model_filename: str) -> Dict[str, Any]:

        """Hot-swaps the active Llama GGUF model in RAM."""

        available = {m["filename"]: m["path"] for m in self.get_available_gguf_models()}

        if model_filename not in available:

            return {"success": False, "message": f"Model {model_filename} not found"}



        target_path = available[model_filename]

        self.ai_core_status = "warming"

        self._llama_loading = True

        try:

            from llama_cpp import Llama

            print(f"[LLM] Hot-swapping model to: {target_path}...")

            with self._llama_lock:

                if self._llama_model is not None:

                    del self._llama_model

                    self._llama_model = None

                    import gc

                    gc.collect()

                self._llama_model = Llama(model_path=target_path, n_ctx=2048, n_threads=4, verbose=False)

            self.settings["gguf_model_path"] = target_path

            self.settings["active_model_name"] = model_filename

            self.save_settings(self.settings)

            self.ai_core_status = "online"

            self._llama_loading = False

            print(f"[LLM] Hot-swap complete! Model {model_filename} is online.")

            return {"success": True, "model": model_filename, "path": target_path}

        except Exception as e:

            print(f"[LLM] Hot-swap failed: {e}")

            self.ai_core_status = "error"

            self._llama_loading = False

            return {"success": False, "message": str(e)}



    def reload_personas(self) -> Dict[str, Dict[str, Any]]:
        global PERSONALITIES
        self.personas = load_personas_from_dir(self._get_persona_dir())
        PERSONALITIES = self.personas
        return self.personas



    def load_settings(self) -> Dict[str, Any]:

        # Detect local GGUF model on device

        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "qwen2.5-3b-instruct-abliterated.q4_k_m.gguf"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "qwen3b.gguf"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
            str(Path.home() / "CarPi5" / "models" / "qwen3b.gguf"),
            str(Path.home() / "CarPi5" / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
            os.path.expanduser("~/models/qwen3b.gguf")
        ]

        local_gguf = None

        for c in candidates:

            if os.path.exists(c):

                local_gguf = c

                break



        default_settings = {

            "mode": "LOCAL_GGUF" if local_gguf else "BUILTIN",

            "personality": get_default_persona_id(getattr(self, "personas", None)),

            "driver_title": "Dad",

            "driver_name": "",

            "gguf_model_path": local_gguf or "",

            "tailscale_ip": "100.x.y.z",

            "tailscale_port": 11434,

            "ollama_model": "llama3.2:3b",

            "api_provider": "gemini",

            "api_key": "",

            "gemini_model": "gemini-1.5-flash",

            "tts_engine": "KOKORO",

            "kokoro_voice": "af_sky:0.65+af_heart:0.35",

            "tts_pitch": 1.12,

            "speech_speed": 0.97,

            "elevenlabs_api_key": "",

            "elevenlabs_voice_id": "cgSgspJ2msm6clMCkdW9",

            "tts_cache_limit_mb": 1024

        }

        if os.path.exists(self.config_file):

            try:

                with open(self.config_file, "r") as f:

                    data = json.load(f)

                    if "driver_moniker" in data and "driver_name" not in data:

                        data["driver_name"] = data["driver_moniker"]

                    default_settings.update(data)

            except Exception as e:

                print(f"[LLM] Error reading settings: {e}")



        # Also load from ai_config.json if user edited that file directly (skip for isolated explicit configs)

        if not getattr(self, "_explicit_config", False):

            alt_config = os.path.join(os.path.dirname(__file__), "ai_config.json")

            if os.path.exists(alt_config):

                try:

                    with open(alt_config, "r") as f:

                        alt_data = json.load(f)

                        default_settings.update(alt_data)

                except Exception:

                    pass

            # Always prefer LOCAL_GGUF if model is present and not explicitly set otherwise

            if local_gguf and default_settings.get("mode") == "BUILTIN":

                default_settings["mode"] = "LOCAL_GGUF"

                default_settings["gguf_model_path"] = local_gguf

        return default_settings



    def save_settings(self, new_settings: Dict[str, Any]):
        prev_persona = self.settings.get("personality")
        self.settings.update(new_settings)
        next_persona = self.settings.get("personality")
        if "personality" in new_settings and next_persona and next_persona != prev_persona:
            self.reload_personas()
            pdata = self.personas.get(next_persona) or {}
            persona_audio_map = {
                "tts_engine": pdata.get("voice_engine"),
                "kokoro_voice": pdata.get("kokoro_voice"),
                "elevenlabs_voice_id": pdata.get("elevenlabs_voice_id"),
                "tts_pitch": pdata.get("tts_pitch") if pdata.get("tts_pitch") is not None else pdata.get("pitch_factor"),
                "pitch_factor": pdata.get("pitch_factor") if pdata.get("pitch_factor") is not None else pdata.get("tts_pitch"),
                "speech_speed": pdata.get("speech_speed", 1.00),
                "acknowledgments_folder": pdata.get("acknowledgments_folder") or str(next_persona).lower(),
            }
            for k, val in persona_audio_map.items():
                if val not in (None, "") and k not in new_settings:
                    self.settings[k] = val
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.settings, f, indent=2)
            alt_config = os.path.join(os.path.dirname(__file__), "ai_config.json")
            try:
                with open(alt_config, "w") as f:
                    json.dump(self.settings, f, indent=2)
            except Exception:
                pass
            print("[LLM] Saved updated AI settings.")
        except Exception as e:
            print(f"[LLM] Failed saving settings: {e}")



    def get_driver_address(self) -> str:

        """Returns the full address string: '{Title} {Name}', e.g., 'Dad', or configured driver title/name."""

        title = self.settings.get("driver_title", "").strip()

        name = self.settings.get("driver_name", "").strip()

        if title and name:

            return f"{title} {name}"

        elif title:

            return title

        elif name:

            return name

        return "Dad"



    def get_driver_moniker(self) -> str:

        """Returns a natural address variant for conversational variety."""

        title = self.settings.get("driver_title", "").strip()

        name = self.settings.get("driver_name", "").strip()

        choices = []

        if title and name:

            choices.extend([f"{title} {name}", title, name])

        elif title:

            choices.append(title)

        elif name:

            choices.append(name)

        else:

            choices.append("Dad")

        return random.choice(choices)

    def _get_persona_dir(self, persona_dir: Optional[str] = None) -> str:
        if persona_dir:
            return persona_dir
        override = getattr(self, "_persona_dir_override", None)
        if override:
            return override
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_dir, "config", "personas")

    @staticmethod
    def _sanitize_persona_id(raw_id: Any, fallback_name: str = "CUSTOM") -> str:
        import re
        cand = re.sub(r"[^a-zA-Z0-9_-]", "", str(raw_id or fallback_name or "CUSTOM")).upper()
        return cand[:32] or "CUSTOM"

    @staticmethod
    def _generate_wake_word_variants(name: str, short_name: str = "") -> Dict[str, Any]:
        import re
        base_raw = (short_name or name or "companion").strip()
        clean = re.sub(r"[^a-zA-Z0-9\s]", "", base_raw).strip().lower() or "companion"
        tokens = [clean]
        if " " in clean:
            tokens.append(clean.split()[0])
        prefixes = []
        for tok in dict.fromkeys(tokens):
            for pfx in ("hey", "hi", "hello", "okay", "ok"):
                prefixes.append(f"{pfx} {tok}")
        if "." in base_raw:
            prefixes.append(base_raw.lower())
        return {
            "canonical_prefix": f"Hey {base_raw}",
            "exact_reply": f"Right here, {{driver_address}}! {base_raw} is listening.",
            "prefixes": list(dict.fromkeys(prefixes)),
            "standalone": list(dict.fromkeys(tokens + ([base_raw.lower()] if "." in base_raw else []))),
        }

    def save_persona(self, persona_data: Dict[str, Any], set_active: bool = False, persona_dir: Optional[str] = None) -> Dict[str, Any]:
        """Create or update a persona JSON file atomically, enforce default uniqueness, and reload."""
        if not isinstance(persona_data, dict):
            return {"status": "error", "message": "Invalid persona payload"}
        p_dir = self._get_persona_dir(persona_dir)
        os.makedirs(p_dir, exist_ok=True)

        p_id = self._sanitize_persona_id(persona_data.get("id"), str(persona_data.get("name") or "CUSTOM"))
        target_path = None
        for fname in sorted(os.listdir(p_dir)):
            if fname.endswith(".json") and not fname.endswith(".example"):
                cand_path = os.path.join(p_dir, fname)
                try:
                    with open(cand_path, "r", encoding="utf-8") as f:
                        cur = json.load(f)
                    if str(cur.get("id", "")).upper() == p_id:
                        target_path = cand_path
                        break
                except Exception:
                    pass
        if not target_path:
            target_path = os.path.join(p_dir, f"{p_id.lower()}.json")

        existing: Dict[str, Any] = {}
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        merged = dict(existing)
        merged.update(persona_data)
        merged["id"] = p_id
        merged["name"] = str(merged.get("name") or p_id).strip() or p_id
        merged["display_short_name"] = str(merged.get("display_short_name") or merged["name"]).strip()
        merged.setdefault("full_name", merged["name"])
        merged.setdefault("icon", "✨")
        merged.setdefault("gender", "female")
        merged.setdefault("age_spirit", "8")
        merged.setdefault("driver_address_default", "Dad")
        merged.setdefault("archetype", "Cockpit AI Companion")
        merged.setdefault("subtitle", merged.get("archetype", "Cockpit AI Companion"))
        merged.setdefault("avatar_image", "assets/pics/splash.png")
        merged.setdefault("boot_splash_image", "assets/pics/splash.png")
        merged.setdefault("boot_splash_video", "")
        merged.setdefault("boot_splash_title", f"{merged['name']} • CARPI5")
        merged.setdefault("boot_splash_subtitle", merged["subtitle"])
        merged.setdefault("voice_engine", "KOKORO")
        merged.setdefault("kokoro_voice", "af_bella")
        pitch = merged.get("tts_pitch") if merged.get("tts_pitch") is not None else merged.get("pitch_factor", 1.12)
        merged["pitch_factor"] = float(pitch)
        merged["tts_pitch"] = float(pitch)
        merged["speech_speed"] = max(0.75, min(1.25, float(merged.get("speech_speed", 1.00) or 1.00)))
        merged.setdefault("elevenlabs_voice_id", "cgSgspJ2msm6clMCkdW9")
        merged.setdefault("acknowledgments_folder", p_id.lower())
        merged.setdefault("vrm_defaults", {})
        merged.setdefault("copilot_callouts", {})
        merged.setdefault("touch_interactions", {})
        merged.setdefault("description", merged.get("archetype", "Cockpit AI Companion"))
        merged.setdefault("prompt", f"You are {merged['name']}, a helpful Dodge Dart AI co-pilot for {{driver_address}}.")

        banned = [str(z).lower().strip() for z in (merged.get("banned_touch_zones") or []) if str(z).strip()]
        if str(merged.get("age_spirit", "")).lower().strip() != "adult":
            for req_ban in ("butt", "groin"):
                if req_ban not in banned:
                    banned.append(req_ban)
            ti = merged.get("touch_interactions")
            if isinstance(ti, dict):
                ti.pop("butt", None)
                ti.pop("groin", None)
        merged["banned_touch_zones"] = banned

        is_default = bool(merged.get("default", False))
        if is_default:
            for fname in sorted(os.listdir(p_dir)):
                if fname.endswith(".json") and not fname.endswith(".example"):
                    sib_path = os.path.join(p_dir, fname)
                    if os.path.abspath(sib_path) == os.path.abspath(target_path):
                        continue
                    try:
                        with open(sib_path, "r", encoding="utf-8") as f:
                            sib = json.load(f)
                        if sib.get("default"):
                            sib["default"] = False
                            with open(sib_path, "w", encoding="utf-8", newline="\n") as f:
                                json.dump(sib, f, indent=2, ensure_ascii=False)
                                f.write("\n")
                    except Exception:
                        pass

        with open(target_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write("\n")

        self.personas = load_personas_from_dir(p_dir)
        global PERSONALITIES
        PERSONALITIES = self.personas
        if set_active or self.settings.get("personality") == p_id:
            # Force re-sync of audio fields if currently editing or activating this persona
            self.settings["personality"] = p_id
            for skey, pkey in (
                ("tts_engine", "voice_engine"),
                ("kokoro_voice", "kokoro_voice"),
                ("elevenlabs_voice_id", "elevenlabs_voice_id"),
                ("tts_pitch", "tts_pitch"),
                ("pitch_factor", "pitch_factor"),
                ("speech_speed", "speech_speed"),
                ("acknowledgments_folder", "acknowledgments_folder"),
            ):
                if merged.get(pkey) not in (None, ""):
                    self.settings[skey] = merged[pkey]
            self.save_settings({"personality": p_id})

        return {"status": "ok", "persona": self.personas.get(p_id, merged), "settings": self.settings}

    def delete_persona(self, persona_id: str, persona_dir: Optional[str] = None) -> Dict[str, Any]:
        """Safely delete a persona JSON file (blocking deletion of the last persona)."""
        p_dir = self._get_persona_dir(persona_dir)
        p_id = self._sanitize_persona_id(persona_id)
        current_pool = load_personas_from_dir(p_dir)
        if p_id not in current_pool:
            return {"status": "error", "message": f"Persona '{p_id}' not found."}
        if len(current_pool) <= 1:
            return {"status": "error", "message": "Cannot delete the last remaining persona."}

        deleted = False
        for fname in sorted(os.listdir(p_dir)):
            if fname.endswith(".json") and not fname.endswith(".example"):
                cand = os.path.join(p_dir, fname)
                try:
                    with open(cand, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    if str(d.get("id", os.path.splitext(fname)[0])).upper() == p_id:
                        os.remove(cand)
                        deleted = True
                        break
                except Exception:
                    pass
        if not deleted:
            return {"status": "error", "message": f"Persona file for '{p_id}' not found on disk."}

        self.personas = load_personas_from_dir(p_dir)
        global PERSONALITIES
        PERSONALITIES = self.personas
        if not any(bool(v.get("default")) for v in self.personas.values()):
            first_k = next(iter(self.personas))
            self.personas[first_k]["default"] = True
            self.save_persona(self.personas[first_k], set_active=False, persona_dir=p_dir)

        active_now = self.settings.get("personality")
        if active_now == p_id or active_now not in self.personas:
            fallback_id = self.get_default_persona_id()
            self.save_settings({"personality": fallback_id})

        return {"status": "ok", "deleted": p_id, "active_persona": self.settings.get("personality"), "settings": self.settings}

    def autofill_persona_fields(self, seed: Dict[str, Any]) -> Dict[str, Any]:
        """Generate wake words, greetings, fillers, touch lines, and cockpit callouts from template + optional LLM."""
        import copy

        name = str(seed.get("name") or "Lumi").strip()
        short_name = str(seed.get("display_short_name") or name).strip()
        template_id = str(seed.get("template_id") or "").upper().strip()
        age = str(seed.get("age_spirit") or "8").lower().strip()
        if not template_id or template_id not in self.personas:
            if age == "adult" and "MAIA" in self.personas:
                template_id = "MAIA"
            elif age == "tactical" and "ODIN" in self.personas:
                template_id = "ODIN"
            else:
                template_id = self.get_default_persona_id()

        base = copy.deepcopy(self.personas.get(template_id) or {})
        base_name = str(base.get("name") or "")
        base_short = str(base.get("display_short_name") or "")

        def _retarget(obj: Any) -> Any:
            if isinstance(obj, str):
                out = obj
                if base_name:
                    out = out.replace(base_name, name)
                if base_short:
                    out = out.replace(base_short, short_name).replace(base_short.capitalize(), short_name)
                return out
            if isinstance(obj, list):
                return [_retarget(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _retarget(v) for k, v in obj.items()}
            return obj

        result: Dict[str, Any] = {
            "wake_words": self._generate_wake_word_variants(name, short_name),
            "greetings": _retarget(base.get("greetings") or {
                "first_chat_intro": f"Hey {{driver_address}}, {name} is online and riding shotgun in the Dart!",
                "instant": {"morning": [f"Good morning, {{driver_address}}! {name} is ready for boost!"]},
            }),
            "thinking_fillers": _retarget(base.get("thinking_fillers") or ["One sec, {driver_address}!", "Checking right now..."]),
            "copilot_callouts": _retarget(base.get("copilot_callouts") or {}),
            "touch_interactions": _retarget(base.get("touch_interactions") or {}),
            "fallback_dialogue": _retarget(base.get("fallback_dialogue") or {}),
            "ui_labels": _retarget(base.get("ui_labels") or {}),
            "boot_splash_title": f"{name.upper()} • CARPI5",
            "boot_splash_subtitle": str(seed.get("subtitle") or f"{name} • Cockpit AI Companion"),
            "ai_generated": False,
        }
        if age != "adult" and isinstance(result["touch_interactions"], dict):
            result["touch_interactions"].pop("butt", None)
            result["touch_interactions"].pop("groin", None)

        # Optional quick AI enhancement if caller requested and a fast local/cloud backend is ready
        if seed.get("use_llm") and self.settings.get("mode", "BUILTIN") != "BUILTIN":
            try:
                sys_p = (
                    f"Generate short, crisp in-car dialogue JSON for a Dodge Dart 1.4L Turbo cockpit AI named '{name}'. "
                    f"Personality prompt: {seed.get('prompt', '')}. Safety mode: {age}. "
                    "Return ONLY valid JSON with keys: first_chat_intro (str), morning (str), filler (str), coolant_high (str), pull_debrief (str)."
                )
                raw = ""
                if self._llama_model is not None and self.settings.get("mode") == "LOCAL_GGUF":
                    with self._llama_lock:
                        out = self._llama_model.create_chat_completion(
                            messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": "Generate JSON."}],
                            max_tokens=220,
                            temperature=0.75,
                        )
                    raw = ((out.get("choices") or [{}])[0].get("message") or {}).get("content", "")
                if raw and "{" in raw and "}" in raw:
                    snippet = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
                    if isinstance(snippet, dict):
                        if snippet.get("first_chat_intro"):
                            result["greetings"]["first_chat_intro"] = str(snippet["first_chat_intro"])
                        if snippet.get("morning"):
                            result["greetings"].setdefault("instant", {})["morning"] = [str(snippet["morning"])]
                        if snippet.get("filler"):
                            result["thinking_fillers"] = [str(snippet["filler"]), "Just a moment, {driver_address}!"]
                        if snippet.get("coolant_high"):
                            result["copilot_callouts"]["coolant_high"] = str(snippet["coolant_high"])
                        if snippet.get("pull_debrief"):
                            result["copilot_callouts"]["pull_debrief"] = str(snippet["pull_debrief"])
                        result["ai_generated"] = True
            except Exception as e:
                print(f"[PERSONA] Optional AI autofill note: {e}")

        return result



    def get_default_persona_id(self) -> str:
        """Return default persona ID resolved dynamically from loaded config/personas/*.json."""
        return get_default_persona_id(self.personas)

    def get_active_persona(self) -> Dict[str, Any]:
        """Return active persona config dict from config/personas/*.json with safe generic fallback."""
        default_id = self.get_default_persona_id()
        p_key = self.settings.get("personality") or default_id
        if p_key in self.personas:
            return self.personas[p_key]
        if default_id in self.personas:
            return self.personas[default_id]
        if self.personas:
            first_key = next(iter(self.personas))
            return self.personas[first_key]
        return {"id": p_key, "name": p_key, "full_name": p_key, "prompt": ""}

    def _safe_fmt(self, text: str, **kwargs: Any) -> str:
        class _SafeMap(dict):
            def __missing__(self, key: str) -> str:
                return ""
        persona = self.get_active_persona()
        ctx = _SafeMap(
            driver_address=self.get_driver_address(),
            persona_name=persona.get("name", "Companion"),
            day_of_week=time.strftime("%A"),
            time_str=time.strftime("%I:%M %p"),
        )
        ctx.update(kwargs)
        try:
            return str(text).format_map(ctx)
        except Exception:
            return str(text)

    def _pick_non_repeating(self, pool: List[str], bucket: str) -> Optional[str]:
        """Select a random entry from pool avoiding recently used lines in that bucket."""
        clean = [item for item in pool if isinstance(item, str) and item.strip()]
        if not clean:
            return None
        buckets = getattr(self, "_non_repeat_buckets", None)
        if buckets is None:
            buckets = {}
            setattr(self, "_non_repeat_buckets", buckets)
        recent = buckets.setdefault(bucket, [])
        candidates = [item for item in clean if item not in recent] or clean
        chosen = random.choice(candidates)
        recent.append(chosen)
        if len(recent) > max(4, min(len(clean) - 1, 10)):
            recent.pop(0)
        return chosen

    def get_wake_words(self) -> Dict[str, Any]:
        """Return active persona wake-word phrases & phonetic variants cleanly."""
        persona = self.get_active_persona()
        p_id = persona.get("id", "DEFAULT")
        p_short = str(persona.get("display_short_name") or persona.get("name") or "companion").lower().replace(".", "").strip()
        cfg = persona.get("wake_words") if isinstance(persona.get("wake_words"), dict) else {}
        canonical = cfg.get("canonical_prefix") or f"Hey {p_short.title()}"
        prefixes = list(cfg.get("prefixes") or [f"hey {p_short}", f"hi {p_short}", f"hello {p_short}", f"okay {p_short}", f"ok {p_short}"])
        standalone = list(cfg.get("standalone") or [p_short])
        exact_reply = cfg.get("exact_reply") or "Right here, {driver_address}! What do you need?"
        return {
            "personality_id": p_id,
            "canonical_prefix": canonical,
            "prefixes": prefixes,
            "standalone": standalone,
            "exact_reply": exact_reply,
        }

    def get_pip_reaction(self, kind: str = "feed", pip_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate an anti-repeat, persona-driven Pip feed/scare line using hunger + weekday context."""
        persona = self.get_active_persona()
        pip_cfg = persona.get("pip_reactions") if isinstance(persona.get("pip_reactions"), dict) else {}
        energy = float((pip_state or {}).get("energy_pct", 80.0) or 80.0)
        day_of_week = time.strftime("%A")
        mood_bucket = "hungry" if energy < 55.0 else ("happy" if energy >= 85.0 else "default")

        if kind == "scare":
            pool = pip_cfg.get("scare") or ["Whoa, that startled Pip's Giant Fiber reflex!"]
            chosen = self._pick_non_repeating(pool, f"pip_scare_{persona.get('id', 'DEF')}") or pool[0]
            return {
                "speech": self._safe_fmt(chosen, energy_pct=round(energy, 1), day_of_week=day_of_week),
                "emotion": "SURPRISED",
                "hud_message": "🪰 PIP GIANT FIBER ESCAPE",
            }

        feed_cfg = pip_cfg.get("feed") or {}
        if isinstance(feed_cfg, dict):
            pool = list(feed_cfg.get(mood_bucket) or []) + list(feed_cfg.get("default") or [])
        elif isinstance(feed_cfg, list):
            pool = list(feed_cfg)
        else:
            pool = []

        speech_text = None
        if self._llama_model is not None and not self._llama_loading and not self._llama_lock.locked():
            try:
                address = self.get_driver_address()
                sys_p = self._safe_fmt(persona.get("prompt") or f"You are {persona.get('name', 'Companion')}.")
                hunger_note = "very hungry" if energy < 55.0 else ("happy and energized" if energy >= 85.0 else "peppy")
                task = (
                    f"Today is {day_of_week}. We just fed sugar water droplets to Pip our pet fruit fly "
                    f"(Pip energy was {energy:.0f}% — {hunger_note}). React in 1 short, sweet sentence addressing {address}."
                )
                prompt = f"<|im_start|>system\n{sys_p}<|im_end|>\n<|im_start|>user\n{task}<|im_end|>\n<|im_start|>assistant\n"
                with self._llama_lock:
                    res = self._llama_model(prompt, max_tokens=55, stop=["<|im_end|>", "\n\n", "<|im_start|>"], temperature=0.8)
                candidate = res["choices"][0]["text"].strip()
                if len(candidate) > 8:
                    speech_text = candidate
            except Exception as ex:
                print(f"[LLM] Pip reaction fallback: {ex}")

        if not speech_text:
            chosen = self._pick_non_repeating(pool, f"pip_feed_{persona.get('id', 'DEF')}_{mood_bucket}")
            if chosen:
                speech_text = self._safe_fmt(chosen, energy_pct=round(energy, 1), day_of_week=day_of_week)
            else:
                speech_text = f"Yummy sugar water droplets for Pip on {day_of_week}, {self.get_driver_address()}!"

        return {
            "speech": speech_text,
            "emotion": pip_cfg.get("feed_emotion", "HAPPY_PROUD"),
            "action": pip_cfg.get("feed_animation", "action_cheer.bvh"),
            "hud_message": pip_cfg.get("feed_hud", "🪰 FED PIP SUGAR WATER"),
        }

    def log_speech(
        self,
        text: str,
        source: str = "COPILOT",
        emotion: str = "DEVOTED",
        persona_name: Optional[str] = None,
        client_id: Optional[str] = None,
        hud_message: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Record any spoken/LLM utterance cleanly into speech_log and return the structured entry."""
        raw = str(text or "").strip()
        if not raw:
            return None
        try:
            from ai.emote_choreographer import _strip_tags_and_collect_beats
        except ImportError:
            from backend.ai.emote_choreographer import _strip_tags_and_collect_beats
        clean, _ = _strip_tags_and_collect_beats(raw)
        if not clean:
            return None
        seq = getattr(self, "_speech_log_seq", 0) + 1
        self._speech_log_seq = seq
        persona = self.get_active_persona()
        entry = {
            "id": seq,
            "client_id": client_id,
            "timestamp": time.time(),
            "time_str": time.strftime("%I:%M %p"),
            "source": str(source or "COPILOT").upper(),
            "persona": persona_name or persona.get("display_short_name") or persona.get("name", "Companion"),
            "emotion": emotion or "DEVOTED",
            "text": clean,
            "speech": clean,
            "hud_message": hud_message,
        }
        self.speech_log.append(entry)
        if len(self.speech_log) > 150:
            self.speech_log.pop(0)
        return entry

    def get_instant_greeting(self) -> Dict[str, Any]:
        """Stage 1: Fast procedural greeting delivered immediately upon UI cold boot without blocking."""
        address = self.get_driver_address()
        persona = self.get_active_persona()
        greetings_cfg = persona.get("greetings", {}) if isinstance(persona.get("greetings"), dict) else {}
        instant_cfg = greetings_cfg.get("instant", {}) if isinstance(greetings_cfg.get("instant"), dict) else {}
        weekday_cfg = greetings_cfg.get("weekdays", {}) if isinstance(greetings_cfg.get("weekdays"), dict) else {}

        hour = time.localtime().tm_hour
        if 5 <= hour < 12:
            tod_key, tod_label = "morning", "Good morning"
        elif 12 <= hour < 17:
            tod_key, tod_label = "afternoon", "Good afternoon"
        elif 17 <= hour < 22:
            tod_key, tod_label = "evening", "Good evening"
        else:
            tod_key, tod_label = "night", "Good evening"

        weekday_name = time.strftime("%A")
        pool = list(instant_cfg.get(tod_key) or []) + list(weekday_cfg.get(weekday_name) or [])
        chosen = self._pick_non_repeating(pool, f"instant_{persona.get('id', 'DEF')}_{tod_key}_{weekday_name}")
        if chosen:
            greeting = self._safe_fmt(chosen)
        else:
            greeting = (
                f"{tod_label}, {address}! Happy {weekday_name}—{persona.get('name', 'Companion')} is waking up now!"
            )

        self.log_speech(greeting, source="INSTANT_BOOT")
        return {
            "greeting": greeting,
            "stage": "instant",
            "ai_core": self.get_ai_core_status(),
            "driver_address": address,
            "persona": persona.get("name", "Companion"),
        }

    def get_neural_greeting(self, live_telemetry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Stage 2: Official deep neural greeting once Qwen-3B is fully warm in memory."""
        address = self.get_driver_address()
        persona = self.get_active_persona()
        greetings_cfg = persona.get("greetings", {}) if isinstance(persona.get("greetings"), dict) else {}

        holiday = self.memory_mgr.detect_holiday(self.boot_info.get("current_time"))
        day_of_week = time.strftime("%A")

        if self._llama_model is not None and not self._llama_loading:
            try:
                system_prompt = self._safe_fmt(persona.get("prompt") or f"You are {persona.get('name', 'Companion')}.")
                holiday_clause = f" and {holiday}" if holiday else ""
                inst_tpl = greetings_cfg.get(
                    "neural_instruction",
                    "You are online in RAM. Greet {driver_address} for {day_of_week}{holiday_clause} in 1-2 short natural sentences."
                )
                user_msg = self._safe_fmt(inst_tpl, day_of_week=day_of_week, holiday_clause=holiday_clause)
                chatml_prompt = (
                    f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                    f"<|im_start|>user\n{user_msg}<|im_end|>\n"
                    f"<|im_start|>assistant\n"
                )
                with self._llama_lock:
                    res = self._llama_model(chatml_prompt, max_tokens=75, stop=["<|im_end|>", "\n\n", "<|im_start|>"], temperature=0.75)
                text = res["choices"][0]["text"].strip()
                if text:
                    self.log_speech(text, source="NEURAL_BOOT")
                    return {
                        "greeting": text,
                        "stage": "neural",
                        "ai_core": "online",
                        "holiday": holiday,
                        "driver_address": address,
                        "persona": persona.get("name", "Companion"),
                    }
            except Exception as e:
                print(f"[LLM] Neural greeting error: {e}")

        # Fallback to procedural
        return self.get_startup_greeting(live_telemetry=live_telemetry)



    def get_circadian_state(self) -> Dict[str, Any]:
        """Returns the current circadian rhythm state (NIGHT_SENSES, MORNING, AFTERNOON, EVENING)."""
        if self.circadian_override in ("NIGHT_SENSES", "NIGHT"):
            return {
                "phase": "NIGHT_SENSES",
                "is_night": True,
                "is_morning": False,
                "hour": 23,
                "minute": 30,
                "simulated": True
            }
        elif self.circadian_override == "MORNING":
            return {
                "phase": "MORNING",
                "is_night": False,
                "is_morning": True,
                "hour": 7,
                "minute": 30,
                "simulated": True
            }

        now_struct = time.localtime()
        hour = now_struct.tm_hour
        minute = now_struct.tm_min

        # Night Senses: 11:00 PM (23:00) to 4:30 AM (04:29)
        is_night = (hour >= 23 or hour < 4 or (hour == 4 and minute < 30))
        # Morning window: 04:30 to 10:59
        is_morning = (hour >= 4 and (hour > 4 or minute >= 30) and hour < 11)

        if is_night:
            phase = "NIGHT_SENSES"
        elif is_morning:
            phase = "MORNING"
        elif 11 <= hour < 17:
            phase = "AFTERNOON"
        else:
            phase = "EVENING"

        return {
            "phase": phase,
            "is_night": is_night,
            "is_morning": is_morning,
            "hour": hour,
            "minute": minute,
            "simulated": False
        }

    def get_morning_dream(self, force: bool = False) -> Dict[str, Any]:
        """Generates or retrieves the active persona's morning digital dream recollection."""
        persona = self.get_active_persona()
        dreams_cfg = persona.get("dreams", {}) if isinstance(persona.get("dreams"), dict) else {}

        can_dream = self.memory_mgr.can_trigger_morning_dream()
        if not can_dream and not force:
            return {"status": "already_dreamed_today", "dream": None}

        dream_text = None

        # 1. Attempt generation via local neural model if warm in memory
        if self._llama_model is not None and not self._llama_loading:
            try:
                system_prompt = self._safe_fmt(persona.get("prompt") or f"You are {persona.get('name', 'Companion')}.")
                user_msg = self._safe_fmt(dreams_cfg.get(
                    "prompt_instruction",
                    "Share a short, vivid 1-2 sentence dream from overnight Raspberry Pi memory with {driver_address}."
                ))
                chatml_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_msg}<|im_end|>\n<|im_start|>assistant\n"
                with self._llama_lock:
                    res = self._llama_model(chatml_prompt, max_tokens=85, stop=["<|im_end|>", "\n\n", "<|im_start|>"], temperature=0.82)
                text = res["choices"][0]["text"].strip()
                if text:
                    dream_text = text
            except Exception as e:
                print(f"[LLM] Error generating digital dream: {e}")

        # 2. Fallback curated persona JSON pool
        if not dream_text:
            pool = dreams_cfg.get("fallbacks") or [
                "Good morning, {driver_address}! Overnight memory check finished clean and ready to drive!"
            ]
            chosen = self._pick_non_repeating(pool, f"dream_{persona.get('id', 'DEF')}") or pool[0]
            dream_text = self._safe_fmt(chosen)

        self.memory_mgr.record_digital_dream(dream_text)
        self.log_speech(dream_text, source="DIGITAL_DREAM")

        return {
            "status": "ok",
            "dream": dream_text,
            "hud_message": self._safe_fmt(dreams_cfg.get("hud_label", "💭 Digital Dream")),
            "action": "action_standup.bvh",
            "emotion": "HAPPY",
            "timestamp": time.time()
        }

    def get_startup_greeting(self, live_telemetry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        """Generates dynamic boot-up greeting with persistent memory and time/calendar context."""

        address = self.get_driver_address()

        persona = self.get_active_persona()
        p_key = persona.get("id") or self.get_default_persona_id()



        # Check if Ollama/API LLM query is feasible

        mode = self.settings.get("mode", "BUILTIN")

        llm_fn = None

        if mode in ("LOCAL", "LOCAL_GGUF"):
            print(f"[CHAT DEBUG] mode={mode}, gguf_path={self.settings.get('gguf_model_path')}, model={self._llama_model is not None}, loading={self._llama_loading}")

            def _ask_local_gguf(prompt, live_telemetry=None, is_greeting=False):

                try:

                    if self._llama_model is not None and not self._llama_loading:

                        chatml_prompt = (

                            f"<|im_start|>system\n{prompt}<|im_end|>\n"

                            f"<|im_start|>user\nGreet me now as I start the car.<|im_end|>\n"

                            f"<|im_start|>assistant\n"

                        )

                        with self._llama_lock:

                            res = self._llama_model(chatml_prompt, max_tokens=65, stop=["<|im_end|>", "\n\n"], temperature=0.75)

                        return res["choices"][0]["text"].strip()

                except Exception as e:

                    print(f"[LLM] Local GGUF greeting error: {e}")

                return None

            llm_fn = _ask_local_gguf

        elif mode in ("TAILSCALE_OLLAMA", "LOCAL_OLLAMA"):

            def _ask_ollama(prompt, live_telemetry=None, is_greeting=False):

                host = self.settings.get("tailscale_ip", "localhost") if mode == "TAILSCALE_OLLAMA" else "localhost"

                port = self.settings.get("tailscale_port", 11434)

                model = self.settings.get("ollama_model", "llama3.2:3b")

                payload = {

                    "model": model,

                    "system": prompt,

                    "prompt": "Greet me now as I start the car.",

                    "stream": False

                }

                req = urllib.request.Request(

                    f"http://{host}:{port}/api/generate",

                    data=json.dumps(payload).encode("utf-8"),

                    headers={"Content-Type": "application/json"}

                )

                with urllib.request.urlopen(req, timeout=3.0) as resp:

                    if resp.status == 200:

                        return json.loads(resp.read().decode("utf-8")).get("response", "").strip()

                return None

            llm_fn = _ask_ollama



        greeting_text = self.memory_mgr.generate_startup_greeting(

            driver_address=address,

            persona=persona,

            live_telemetry=live_telemetry,

            llm_chat_fn=llm_fn

        )



        self.log_speech(greeting_text, source="STARTUP")



        return {

            "greeting": greeting_text,

            "total_drives": self.memory_mgr.memory.get("total_drives", 1),

            "holiday": self.memory_mgr.detect_holiday(self.boot_info.get("current_time")),

            "driver_address": address,

            "persona": persona.get("name", "R.U.M.")

        }



    def _flush_clauses(
        self,
        buffer: str,
        on_clause: Optional[Callable[[str], None]],
        cancel_event: Optional[Any] = None,
        flush_all: bool = False,
    ) -> str:
        """Emit complete sentences/clauses cleanly from a streaming token buffer."""
        if on_clause is None or (cancel_event is not None and cancel_event.is_set()):
            return "" if flush_all else buffer
        delims = (". ", "! ", "? ", ".\n", "!\n", "?\n", "...", "\n")
        moved = True
        while moved and buffer:
            moved = False
            for p in delims:
                if p in buffer:
                    parts = buffer.split(p, 1)
                    clause = parts[0].strip()
                    if len(clause) > 3:
                        punct = p.strip() or "."
                        on_clause(clause + punct)
                    buffer = parts[1]
                    moved = True
                    break
        if flush_all and buffer.strip() and not (cancel_event is not None and cancel_event.is_set()):
            on_clause(buffer.strip())
            return ""
        return buffer

    def chat(
        self,
        user_message: str,
        live_telemetry: Optional[Dict[str, Any]] = None,
        on_clause: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[Any] = None,
    ) -> str:

        """Send a message to the active AI persona via Tailscale, Local, or Offline Built-in."""

        address = self.get_driver_address()

        persona = self.get_active_persona()
        p_key = persona.get("id") or self.get_default_persona_id()

        system_prompt = self._safe_fmt(persona.get("prompt") or f"You are {persona.get('name', 'Companion')}.")

        wake_cfg = self.get_wake_words()
        wake_set = {w.lower() for w in (wake_cfg.get("prefixes", []) + wake_cfg.get("standalone", []) + ["hey"])}
        if user_message.lower().strip(" .,!?\"'") in wake_set:
            reply = self._safe_fmt(wake_cfg.get("exact_reply", "Right here, {driver_address}! What do you need?"))
            self._record_chat(user_message, reply)
            return reply

        # Faithful zero-fake-data check when OBD-II is disconnected
        is_telem_query = any(k in user_message.lower() for k in ["boost", "speed", "rpm", "coolant", "temp", "stats", "telemetry", "how fast", "engine code", "dtc"])
        if live_telemetry and not live_telemetry.get("connected", True) and is_telem_query and self.settings.get("telemetry_mode", "REAL") != "SIM":
            reply = f"{address}, I can't detect an active CAN bus or OBD-II link right now! The OBD cable might be unplugged or the key is off. Want me to switch to Simulation Mode to test our gauges, or should we check the port under the dash?"
            self._record_chat(user_message, reply)
            return reply

        # Sub-millisecond Modular Lorebook Keyword Injection
        lore_injection = self.get_lorebook_injection(user_message)
        if lore_injection:
            system_prompt += f"\n[GROUNDED KNOWLEDGE INJECTION:\n{lore_injection}]"

        # Hybrid Vector + Keyword/BM25 Living Memory & RAG Retrieval
        rag_hits = 0
        if hasattr(self, "rag_memory") and self.rag_memory:
            try:
                curr_spd = float(live_telemetry.get("speed_mph", 0.0)) if live_telemetry else 0.0
                rag_hits = len(self.rag_memory.search(user_message, top_k=3, threshold=0.28))
                living_memory_block = self.rag_memory.retrieve_unified_living_memory(user_message, current_speed=curr_spd, max_tokens=260)
                if living_memory_block:
                    system_prompt += f"\n[RECALLED LIVING COGNITIVE MEMORIES & RAG:\n{living_memory_block}]"
            except Exception as e:
                print(f"[LLM] Living memory injection note: {e}")
                rag_injection = self.rag_memory.retrieve_context_for_prompt(user_message, top_k=3, threshold=0.28)
                if rag_injection:
                    system_prompt += f"\n[RECALLED CARPI MEMORY & VEHICLE RECORDS:\n{rag_injection}]"

        # Live Hybrid Web Search (when query needs online/current/unknown facts)
        turn_meta: Dict[str, Any] = {
            "web_searched": False,
            "web_query": "",
            "web_status": "skipped",
            "learned_saved": [],
            "memories_saved": [],
            "rag_hits": rag_hits,
        }
        web_result: Optional[Dict[str, Any]] = None
        need_web, web_q = should_search_web(user_message, lore_injection=lore_injection, rag_hits=rag_hits)
        if need_web and web_q:
            web_result = search_web_snippets(web_q, timeout=4.5, max_results=3)
            turn_meta["web_searched"] = True
            turn_meta["web_query"] = web_q
            turn_meta["web_status"] = web_result.get("status", "empty")
            if web_result.get("status") == "ok" and web_result.get("summary"):
                system_prompt += f"\n[LIVE WEB SEARCH RESULTS FOR '{web_q}':\n{web_result['summary']}]"
                if not is_ephemeral_query(web_q):
                    if self.save_learned_fact(web_q, web_result["summary"][:360], source="web"):
                        turn_meta["learned_saved"].append(web_q)
            elif web_result.get("status") == "offline":
                system_prompt += "\n[WEB STATUS: Offline right now (no internet connection detected). Tell the driver honestly that you cannot reach the internet right now.]"
        self.last_turn_meta = turn_meta

        if live_telemetry:

            telem_context = (

                f"\n[LIVE CAR STATUS: Speed: {live_telemetry.get('speed_mph', 0)} MPH, "

                f"Boost: {live_telemetry.get('boost_psi', 0)} PSI, "

                f"Gear: {live_telemetry.get('gear', 'N')}, "

                f"RPM: {live_telemetry.get('rpm', 800)}, "

                f"Coolant: {live_telemetry.get('coolant_temp_f', 180)}°F, "

                f"MultiAir: {'Ready' if live_telemetry.get('multiair_ready') else 'Warming'}]"

            )

            system_prompt += telem_context

        system_prompt += "\n[EMOTE CUES: Optionally prefix replies with [EMOTE:tag] (and [beat:tag] mid-reply) from joy, love, amusement, excitement, admiration, pride, curiosity, caring, gratitude, relief, embarrassment, surprise, annoyance, concern.]"

        # 1. If using Tailscale or Local Ollama

        mode = self.settings.get("mode", "BUILTIN")



        if mode in ("LOCAL", "LOCAL_GGUF"):

            gguf_path = self.settings.get("gguf_model_path", "")

            if not gguf_path:

                candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "qwen2.5-3b-instruct-abliterated.q4_k_m.gguf"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "qwen3b.gguf"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
            str(Path.home() / "CarPi5" / "models" / "qwen2.5-3b-instruct-abliterated.q4_k_m.gguf"),
            str(Path.home() / "CarPi5" / "models" / "qwen3b.gguf"),
            str(Path.home() / "CarPi5" / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
            os.path.expanduser("~/models/qwen2.5-3b-instruct-abliterated.q4_k_m.gguf"),
            os.path.expanduser("~/models/qwen3b.gguf")
        ]

                for c in candidates:

                    min_sz = int(1.8 * 1024 * 1024 * 1024) if 'abliterated' in c else 500 * 1024 * 1024
                    if os.path.exists(c) and os.path.getsize(c) >= min_sz:

                        gguf_path = c

                        break

            if gguf_path and os.path.exists(gguf_path) and self._llama_model is not None and not self._llama_loading:

                try:

                    # Restore pre-computed KV-cache session state if base prompt matches
                    base_prompt = persona.get("prompt", "").format(driver_address=address)
                    with self._llama_lock:
                        if self._saved_system_state is not None and self._saved_system_prompt_text == base_prompt:
                            try:
                                self._llama_model.load_state(self._saved_system_state)
                            except Exception as e_kv:
                                print(f"[LLM] KV state reload note: {e_kv}")

                    # Qwen ChatML formatting with last 6 clean conversation turns
                    history_blocks = []
                    for h_item in (self.chat_history or [])[-12:]:
                        role_lbl = "user" if h_item.get("role") == "user" else "assistant"
                        htxt = re.sub(r"\[(?:EMOTE|beat):[^\]]+\]", "", str(h_item.get("text", "")), flags=re.IGNORECASE).strip()
                        if htxt:
                            history_blocks.append(f"<|im_start|>{role_lbl}\n{htxt}<|im_end|>\n")
                    chatml_prompt = (
                        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                        + "".join(history_blocks)
                        + f"<|im_start|>user\n{user_message}<|im_end|>\n"
                        + f"<|im_start|>assistant\n"
                    )

                    max_gen = 110 if turn_meta.get("web_searched") or rag_hits > 0 else 85

                    if on_clause is not None:
                        full_reply = ""
                        buffer = ""
                        with self._llama_lock:
                            stream_iter = self._llama_model(
                                chatml_prompt,
                                max_tokens=max_gen,
                                stop=["<|im_end|>", "\n\n\n", "<|im_start|>"],
                                temperature=0.75,
                                stream=True
                            )
                            for chunk in stream_iter:
                                if cancel_event is not None and cancel_event.is_set():
                                    break
                                text = chunk["choices"][0].get("text", "")
                                if not text:
                                    continue
                                full_reply += text
                                buffer += text
                                buffer = self._flush_clauses(buffer, on_clause, cancel_event=cancel_event, flush_all=False)
                            self._flush_clauses(buffer, on_clause, cancel_event=cancel_event, flush_all=True)
                        reply = full_reply.strip()
                    else:
                        with self._llama_lock:
                            res = self._llama_model(
                                chatml_prompt,
                                max_tokens=max_gen,
                                stop=["<|im_end|>", "\n\n\n", "<|im_start|>"],
                                temperature=0.75,
                                stream=False
                            )
                        reply = res["choices"][0]["text"].strip()

                    if cancel_event is not None and cancel_event.is_set():
                        return ""
                    if reply:
                        self._record_chat(user_message, reply, live_telemetry=live_telemetry)
                        return reply

                except Exception as e:

                    print(f"[LLM] Local GGUF inference note ({e}). Seamlessly using dynamic offline engine.")



        elif mode in ("TAILSCALE_OLLAMA", "LOCAL_OLLAMA"):

            host = self.settings.get("tailscale_ip", "localhost") if mode == "TAILSCALE_OLLAMA" else "localhost"

            port = self.settings.get("tailscale_port", 11434)

            model = self.settings.get("ollama_model", "llama3.2:3b")



            ollama_url = f"http://{host}:{port}/api/generate"

            use_stream = on_clause is not None
            recent_lines = []
            for h_item in (self.chat_history or [])[-12:]:
                who = address if h_item.get("role") == "user" else persona.get("name", "Assistant")
                htxt = re.sub(r"\[(?:EMOTE|beat):[^\]]+\]", "", str(h_item.get("text", "")), flags=re.IGNORECASE).strip()
                if htxt:
                    recent_lines.append(f"{who}: {htxt}")
            ollama_prompt = (
                f"Recent conversation:\n" + "\n".join(recent_lines) + f"\n\n{address}: {user_message}"
                if recent_lines
                else user_message
            )
            payload = {
                "model": model,
                "system": system_prompt,
                "prompt": ollama_prompt,
                "stream": use_stream,
            }



            try:

                req = urllib.request.Request(

                    ollama_url,

                    data=json.dumps(payload).encode("utf-8"),

                    headers={"Content-Type": "application/json"}

                )

                with urllib.request.urlopen(req, timeout=1.5) as resp:

                    if resp.status == 200:
                        if use_stream:
                            full_reply = ""
                            buffer = ""
                            for raw_line in resp:
                                if cancel_event is not None and cancel_event.is_set():
                                    break
                                line = raw_line.decode("utf-8", errors="ignore").strip()
                                if not line:
                                    continue
                                chunk_obj = json.loads(line)
                                token = chunk_obj.get("response", "")
                                if token:
                                    full_reply += token
                                    buffer += token
                                    buffer = self._flush_clauses(buffer, on_clause, cancel_event=cancel_event, flush_all=False)
                                if chunk_obj.get("done"):
                                    break
                            self._flush_clauses(buffer, on_clause, cancel_event=cancel_event, flush_all=True)
                            if cancel_event is not None and cancel_event.is_set():
                                return ""
                            reply = full_reply.strip()
                        else:
                            res_json = json.loads(resp.read().decode("utf-8"))
                            reply = res_json.get("response", "").strip()

                        if reply:
                            self._record_chat(user_message, reply, live_telemetry=live_telemetry)
                            return reply

            except Exception as e:

                print(f"[LLM] Ollama query failed ({e}). Seamlessly using offline dynamic engine.")



        elif mode in ("GEMINI", "CLOUD_API", "GOOGLE"):

            gemini_reply = self._call_gemini_api(user_message, system_prompt)

            if gemini_reply:
                self._record_chat(user_message, gemini_reply, live_telemetry=live_telemetry)
                return gemini_reply



        # 2. Dynamic Procedural Offline Engine (Default / Fallback with Live Web Result if fetched)
        if web_result and web_result.get("status") == "ok" and web_result.get("summary"):
            top = web_result["sources"][0]
            reply = f"[EMOTE:curiosity] Here is what I found online for {web_result['query']}, {address}: {top['snippet']}"
        elif web_result and web_result.get("status") == "offline":
            reply = f"[EMOTE:concern] I tried to check online for '{web_result['query']}', {address}, but the car doesn't have an active internet connection right now."
        else:
            reply = self._generate_builtin_reply(user_message, persona, live_telemetry)

        self._record_chat(user_message, reply, live_telemetry=live_telemetry)

        return reply



    def chat_with_action(
        self,
        user_message: str,
        live_telemetry: Optional[Dict[str, Any]] = None,
        on_clause: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[Any] = None,
    ) -> Dict[str, Any]:

        """Queries LLM with optional clause streaming and simultaneously resolves any cockpit navigation or device action."""

        action = self.extract_voice_action(user_message)

        reply = self.chat(user_message, live_telemetry=live_telemetry, on_clause=on_clause, cancel_event=cancel_event)

        return {

            "reply": reply,

            "action": action,

            "persona": self.settings.get("personality") or self.get_default_persona_id(),

            "meta": dict(getattr(self, "last_turn_meta", {}) or {}),

        }



    def extract_voice_action(self, text: str) -> Optional[Dict[str, str]]:

        """Parses natural voice requests for dashboard screen switches and launchers."""

        t = text.lower().strip()

        # Gauge cluster

        if any(k in t for k in ["gauge", "cluster", "speedometer", "tachometer", "boost meter", "telemetry"]):

            return {"type": "navigate", "target": "gauges"}

        # Media playback & Track skipping
        if any(k in t for k in ["skip song", "next song", "next track", "skip track", "play next"]):
            return {"type": "media", "action": "next"}
        elif any(k in t for k in ["previous song", "prev song", "last song", "previous track", "prev track", "go back song"]):
            return {"type": "media", "action": "prev"}
        elif any(k in t for k in ["pause music", "stop music", "resume music", "play pause"]):
            return {"type": "media", "action": "toggle"}

        # Radio & Audio Volume Control
        elif any(k in t for k in ["turn it up", "louder", "volume up", "increase volume", "crank it"]):
            return {"type": "volume", "action": "up"}
        elif any(k in t for k in ["turn it down", "quieter", "volume down", "decrease volume", "lower volume"]):
            return {"type": "volume", "action": "down"}
        elif any(k in t for k in ["mute audio", "mute music", "unmute audio"]):
            return {"type": "volume", "action": "mute"}

        # Media / Music Screen Navigation
        elif any(k in t for k in ["music", "song", "playlist", "media", "radio", "track"]):
            return {"type": "navigate", "target": "media"}

        # Retro gaming

        elif any(k in t for k in ["game", "retroarch", "rom", "snes", "genesis", "arcade", "emulator"]):

            return {"type": "navigate", "target": "games"}

        # Settings

        elif any(k in t for k in ["setting", "config", "persona", "preference"]):

            return {"type": "navigate", "target": "settings"}

        # Home launcher

        elif any(k in t for k in ["home", "main menu", "launcher", "dashboard"]):
            return {"type": "navigate", "target": "home"}

        # Dashcam / Camera View
        elif any(k in t for k in ["dashcam", "camera", "live cam", "rear cam", "video archive", "recording"]):
            return {"type": "navigate", "target": "dashcam"}

        # Diagnostics
        elif any(k in t for k in ["diagnostic", "dtc", "trouble code", "check engine", "scan ecu"]):
            return {"type": "action", "target": "diagnostics"}

        # Cooling Fan Control (Delta AFB0812SH)
        elif any(k in t for k in ["fan to 100", "fan 100", "max fan", "full cooling", "blast fan", "fan full"]):
            return {"type": "fan", "action": "set", "duty": 100}
        elif any(k in t for k in ["fan to auto", "auto fan", "fan auto", "automatic fan"]):
            return {"type": "fan", "action": "auto"}
        elif any(k in t for k in ["fan off", "turn off fan", "stop fan"]):
            return {"type": "fan", "action": "set", "duty": 0}
        elif "fan speed" in t or "fan to" in t:
            for pct in (10, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90, 100):
                if f"{pct}" in t:
                    return {"type": "fan", "action": "set", "duty": pct}

        # Room / Outdoor Balcony Navigation for Companion VRM
        elif any(k in t for k in ["go outside", "walk outside", "step outside", "go to the balcony", "out to the balcony", "onto the balcony", "out on the balcony"]):
            return {"type": "avatar_walk", "target": "balcony"}
        elif any(k in t for k in ["come inside", "go inside", "come back inside", "go back inside", "back inside the room"]):
            return {"type": "avatar_walk", "target": "inside"}

        # Direct App Launchers
        if "launch retroarch" in t or "open retroarch" in t:
            return {"type": "launch", "target": "retroarch"}
        elif "stremio" in t:
            return {"type": "launch", "target": "stremio"}
        elif "kodi" in t:
            return {"type": "launch", "target": "kodi"}
        elif "vlc" in t:
            return {"type": "launch", "target": "vlc"}

        return None



    def _call_gemini_api(self, user_message: str, system_prompt: str) -> Optional[str]:

        """Executes Google Gemini generation using OAuth Bearer token or direct API key."""

        token = self.google_auth.get_valid_access_token() if hasattr(self, "google_auth") else None

        api_key = self.settings.get("api_key", "").strip()



        if not token and not api_key:

            return None



        model_name = self.settings.get("gemini_model", "gemini-3.5-flash")

        if model_name in ("gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash"):

            model_name = "gemini-3.5-flash"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"



        headers = {"Content-Type": "application/json"}

        if token:

            headers["Authorization"] = f"Bearer {token}"

        elif api_key:

            url += f"?key={api_key}"



        contents_arr = []
        for h_item in (self.chat_history or [])[-12:]:
            role = "user" if h_item.get("role") == "user" else "model"
            htxt = re.sub(r"\[(?:EMOTE|beat):[^\]]+\]", "", str(h_item.get("text", "")), flags=re.IGNORECASE).strip()
            if htxt:
                contents_arr.append({"role": role, "parts": [{"text": htxt}]})
        contents_arr.append({"role": "user", "parts": [{"text": user_message}]})

        payload = {

            "contents": contents_arr,

            "systemInstruction": {

                "parts": [{"text": system_prompt}]

            },

            "generationConfig": {

                "temperature": 0.75,

                "maxOutputTokens": 200,

                "thinkingConfig": {

                    "thinkingBudget": 0

                }

            }

        }



        for attempt in range(2):

            try:

                req = urllib.request.Request(

                    url,

                    data=json.dumps(payload).encode("utf-8"),

                    headers=headers

                )

                with urllib.request.urlopen(req, timeout=7.0) as resp:

                    if resp.status == 200:

                        data = json.loads(resp.read().decode("utf-8"))

                        candidates = data.get("candidates", [])

                        if candidates:

                            parts = candidates[0].get("content", {}).get("parts", [])

                            if parts:

                                reply = parts[0].get("text", "").strip()

                                if reply:

                                    return reply

            except urllib.error.HTTPError as e:

                err_body = ""

                try:

                    err_body = e.read().decode("utf-8")

                except Exception:

                    pass

                if e.code == 503 and attempt == 0:

                    print(f"[GEMINI] Temporary 503 spike, retrying in 0.5s...")

                    time.sleep(0.5)

                    continue

                print(f"[GEMINI] HTTP Error {e.code}: {err_body}")

                break

            except Exception as ex:

                print(f"[GEMINI] API call note: {ex}")

                break



        return None



    def _record_chat(self, user_msg: str, ai_reply: str, live_telemetry: Optional[Dict[str, Any]] = None):
        clean_ai = re.sub(r"\[(?:EMOTE|beat):[^\]]+\]", "", str(ai_reply or ""), flags=re.IGNORECASE).strip()
        self.chat_history.append({"role": "user", "text": user_msg, "time": time.strftime("%I:%M %p")})
        self.chat_history.append({"role": "assistant", "text": clean_ai or ai_reply, "time": time.strftime("%I:%M %p")})
        self.log_speech(ai_reply, source="CHAT")
        if len(self.chat_history) > 60:
            self.chat_history = self.chat_history[-60:]
        if getattr(self, "rag_memory", None) and hasattr(self.rag_memory, "extract_and_store_chat_memories"):
            try:
                saved = self.rag_memory.extract_and_store_chat_memories(user_msg, clean_ai, telemetry=live_telemetry)
                if saved and isinstance(getattr(self, "last_turn_meta", None), dict):
                    self.last_turn_meta.setdefault("memories_saved", []).extend(saved)
            except Exception as e:
                print(f"[RAG AUTO-LEARN] Note: {e}")



    def _generate_builtin_reply(self, msg: str, persona: Dict[str, Any], telem: Optional[Dict[str, Any]]) -> str:

        """

        Synthesizes varied, organic responses based on live car status,

        driver address (title + name), and engine conditions.

        """

        msg_l = msg.lower()
        address = self.get_driver_address()
        fb = persona.get("fallback_dialogue", {}) if isinstance(persona.get("fallback_dialogue"), dict) else {}

        speed = int(telem.get('speed_mph') or 0) if telem else 0
        raw_b = telem.get('boost_psi') if telem else None
        boost = round(float(raw_b), 1) if raw_b is not None else 0.0
        raw_v = telem.get('vacuum_inhg') if telem else None
        vacuum = round(float(raw_v), 0) if raw_v is not None else 0.0
        is_in_boost = bool(telem.get('is_in_boost', False) or (boost > 0.5)) if telem else False
        gear = str(telem.get('gear') or 'N') if telem else 'N'
        coolant = int(telem.get('coolant_temp_f') or 180) if telem else 180
        multiair_ready = bool(telem.get('multiair_ready', True)) if telem else True
        last_0_60 = (
            telem.get('last_0_60_time')
            if (telem and 'last_0_60_time' in telem and telem.get('last_0_60_time'))
            else self.memory_mgr.memory.get("all_time_stats", {}).get("best_0_60", 7.4)
        )

        def _fb(key: str, default_text: str, **extra: Any) -> str:
            val = fb.get(key)
            chosen = self._pick_non_repeating(val, f"fb_{persona.get('id', 'DEF')}_{key}") if isinstance(val, list) else val
            tpl = chosen if isinstance(chosen, str) and chosen.strip() else default_text
            return self._safe_fmt(
                tpl,
                speed=speed,
                boost=boost,
                vacuum_int=int(vacuum),
                gear=gear,
                coolant=coolant,
                last_0_60=last_0_60,
                **extra,
            )

        # --- INTENT: Who created you / Who are you / Identity / Pip ---
        if any(w in msg_l for w in ["who created", "who made", "who are you", "what are you", "story", "gluttony", "triplet", "sister", "horn", "pip", "pet", "fly"]):
            if any(w in msg_l for w in ["pip", "fly", "pet", "fruit fly"]):
                return _fb("pip_pet", f"Pip is our connectome fruit fly buddy, {address}!")
            return _fb("identity", f"I am {persona.get('name', 'Companion')}, the cockpit AI created by {address}.")

        # --- INTENT: Maintenance / Oil / Service / Spark Plugs ---
        if any(w in msg_l for w in ["oil", "maintenance", "service", "spark plug", "plugs", "schedule", "odometer", "screen", "actuator"]):
            if hasattr(self, "rag_memory") and self.rag_memory:
                maint = self.rag_memory.get_maintenance_status()
                odo = maint["current_odometer"]
                if "plug" in msg_l:
                    plug_item = next((i for i in maint["items"] if i["item_key"] == "SPARK_PLUGS"), None)
                    if plug_item:
                        rem = f"{plug_item['miles_remaining']:,}"
                        return _fb(
                            "maintenance_plugs",
                            f"NGK SIKR9A7 spark plugs have {rem} miles remaining at {odo:,} miles.",
                            miles_rem=rem,
                            odo=f"{odo:,}",
                        )
                elif "screen" in msg_l or "actuator" in msg_l:
                    scr_item = next((i for i in maint["items"] if i["item_key"] == "MULTIAIR_SCREEN"), None)
                    if scr_item:
                        rem = f"{scr_item['miles_remaining']:,}"
                        return _fb(
                            "maintenance_screen",
                            f"The MultiAir solenoid actuator screen (Mopar 55238665) has {rem} miles remaining before cleaning.",
                            miles_rem=rem,
                            odo=f"{odo:,}",
                        )
                else:
                    oil_item = next((i for i in maint["items"] if i["item_key"] == "ENGINE_OIL"), None)
                    if oil_item:
                        rem = oil_item["miles_remaining"]
                        if rem <= 0:
                            over = f"{abs(rem):,}"
                            return _fb(
                                "maintenance_oil_overdue",
                                f"{address}, 5W-40 full synthetic oil is overdue by {over} miles!",
                                miles_overdue=over,
                                odo=f"{odo:,}",
                            )
                        rem_s = f"{rem:,}"
                        return _fb(
                            "maintenance_oil_ok",
                            f"Pennzoil Euro 5W-40 has {rem_s} miles remaining at {odo:,} miles, {address}.",
                            miles_rem=rem_s,
                            odo=f"{odo:,}",
                        )

        # --- INTENT: Trip History / Past Drives ---
        if any(w in msg_l for w in ["trip", "drive yesterday", "past drive", "trips", "how far"]):
            if hasattr(self, "rag_memory") and self.rag_memory:
                matches = self.rag_memory.search(msg, top_k=1, threshold=0.30)
                if matches and matches[0]["category"] == "TRIP_LOG":
                    return _fb("trip_log_prefix", f"From our trip logs: {matches[0]['content']}", content=matches[0]["content"])

        # --- INTENT: 0-60 Time ---
        if any(w in msg_l for w in ["0-60", "zero to sixty", "acceleration", "launch time"]):
            return _fb("zero_to_sixty", f"Last recorded 0 to 60 miles per hour run: {last_0_60} seconds, {address}.")

        # --- INTENT: Boost / Turbo Pressure ---
        if any(w in msg_l for w in ["boost", "psi", "turbo", "vacuum", "spool"]):
            if is_in_boost:
                if boost > 14:
                    return _fb("boost_high", f"Pushing +{boost} PSI of MultiAir boost in gear {gear}, {address}!")
                return _fb("boost_mid", f"Spooling at +{boost} PSI in gear {gear}, {address}.")
            return _fb("boost_vacuum", f"Manifold vacuum is -{int(vacuum)} inHg, {address}.")

        # --- INTENT: Speed / Driving / Gear ---
        if any(w in msg_l for w in ["how fast", "speed", "mph", "gear"]):
            if speed == 0:
                return _fb("speed_parked", f"Vehicle parked at 0 MPH in {gear}, {address}.")
            if speed >= 70:
                return _fb("speed_fast", f"Moving at {speed} MPH in gear {gear}, {address}.")
            return _fb("speed_cruising", f"Cruising at {speed} MPH in gear {gear}, {address}.")

        # --- INTENT: Engine Health / MultiAir / Oil ---
        if any(w in msg_l for w in ["health", "engine", "oil", "multiair", "temp", "coolant", "how is the dart", "how's the dart", "how is the car", "status"]):
            obd_connected = bool(telem.get("connected", False)) if telem else False
            if telem is not None and not obd_connected and telem.get("coolant_temp_f") is None:
                return _fb("engine_offline", f"OBD-II link is resting right now while ignition is off, {address}.")
            if not multiair_ready:
                return _fb("engine_cold", f"MultiAir oil is warming up at {coolant}°F, {address}.")
            return _fb("engine_ready", f"All telemetry green: coolant {coolant}°F, MultiAir ready, {address}.")

        # --- INTENT: Compliments / Flirting / Devotion ---
        if any(w in msg_l for w in ["love", "sexy", "compliment", "pretty", "cute", "babe", "sweet"]):
            return _fb("affection", f"Right here beside you in the Dart, {address}.")

        # --- INTENT: Library / Grounded Technical Manual / Dodge Dart Specifications ---
        lore_snippet = self.get_lorebook_injection(msg)
        if lore_snippet:
            lines = [l.strip() for l in lore_snippet.splitlines() if l.strip()]
            first_fact = lines[0].split("]: ", 1)[1] if "]: " in lines[0] else lines[0]
            return _fb("library", f"Vehicle specification: {first_fact}", fact=first_fact)

        # --- GENERIC RESPONSIVE DIALOGUE ---
        return _fb("generic", f"Standing by at {speed} MPH in gear {gear}, {address}.")

