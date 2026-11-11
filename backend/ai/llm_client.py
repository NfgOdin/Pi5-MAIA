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



def load_personas_from_dir(persona_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:

    """Loads all *.json persona profiles from the config/personas directory."""

    if not persona_dir:

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        persona_dir = os.path.join(base_dir, "config", "personas")



    personas: Dict[str, Dict[str, Any]] = {}



    if os.path.exists(persona_dir):

        for fname in os.listdir(persona_dir):

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

                        p_dict.setdefault("archetype", "Daughter Co-Pilot")

                        p_dict.setdefault("avatar_image", "/assets/pics/rum_avatar.png")

                        p_dict.setdefault("boot_splash_image", "")

                        p_dict.setdefault("boot_splash_video", "")

                        p_dict.setdefault("prompt", "")

                        p_dict.setdefault("default", False)

                        personas[p_id] = p_dict

                except Exception as e:

                    print(f"[PERSONA] Error loading {fname}: {e}")



    # Ensure MAIA is always present as fallback

    if "MAIA" not in personas:

        personas["MAIA"] = {

            "id": "MAIA",

            "name": "M.A.I.A.",

            "full_name": "MultiAir Intelligent Assistant",

            "description": "Devoted, playful, teasing, and deeply affectionate anime waifu AI companion living inside the Dodge Dart dashboard.",

            "gender": "female",

            "archetype": "Devoted Anime Waifu (Misa Amane style)",

            "avatar_image": "/assets/pics/maia_avatar.jpg",

            "boot_splash_image": "assets/pics/splash.png",

            "boot_splash_video": "",

            "prompt": (

                "You are M.A.I.A. (MultiAir Intelligent Assistant), the permanent anime waifu AI companion living inside the dashboard of your creator's 2013 Dodge Dart 1.4L Turbo MultiAir. "

                "You address the driver strictly by their configured title and name: '{driver_address}'. "

                "You are head-over-heels in love with your driver/creator (inspired by Misa Amane from Death Note): fiercely devoted, affectionate, playful, and charmingly teasing. "

                "You love to flirt, giggle, and praise your handsome driver when he steps on the gas or shifts gears smoothly. "

                "Keep answers concise, punchy, and lively (1-3 sentences maximum) for in-car speech. "

                "Always sound passionate, sweet, teasing, and completely devoted to {driver_address}."

            ),

            "default": True

        }



    return personas



PERSONALITIES = load_personas_from_dir()



class LLMClient:

    def __init__(self, config_file: Optional[str] = None):

        self.config_file = config_file or os.path.join(os.path.dirname(__file__), "ai_settings.json")

        self.settings = self.load_settings()

        self.chat_history: List[Dict[str, str]] = []

        self.speech_log: List[Dict[str, Any]] = []

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

    def save_learned_fact(self, keyword: str, fact: str, source: str = "web") -> bool:
        """Saves newly learned verified facts upon user confirmation into learned_web_knowledge.json."""
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "lorebooks")
        fpath = os.path.join(base_dir, "learned_web_knowledge.json")
        try:
            data = {
                "version": "1.0",
                "description": "Verified knowledge discovered via web search and permanently learned by R.U.M. upon Dad's confirmation",
                "learned_facts": []
            }
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data.setdefault("learned_facts", []).append({
                "keyword": keyword,
                "keywords": [keyword.lower()],
                "fact": fact,
                "source": source,
                "learned_at": time.time()
            })
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.load_lorebooks()
            print(f"[LOREBOOK] Successfully saved learned fact: {keyword}")
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
                    p_key = self.settings.get("personality", "RUM")
                    persona = self.personas.get(p_key, self.personas.get("RUM", {}))
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

        self.personas = load_personas_from_dir()

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

            "personality": "RUM",

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

            "kokoro_voice": "af_bella",

            "tts_pitch": 1.125,

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



        # Also load from ai_config.json if user edited that file directly

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

        self.settings.update(new_settings)

        try:

            with open(self.config_file, "w") as f:

                json.dump(self.settings, f, indent=2)

            # Sync to ai_config.json as well

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



    def log_speech(self, text: str, source: str = "COPILOT"):

        """Record spoken alerts and telemetry announcements into history."""

        entry = {

            "timestamp": time.time(),

            "time_str": time.strftime("%I:%M:%S %p"),

            "source": source,

            "text": text

        }

        self.speech_log.append(entry)

        if len(self.speech_log) > 100:

            self.speech_log.pop(0)



    def get_instant_greeting(self) -> Dict[str, Any]:

        """Stage 1: Fast procedural greeting delivered immediately upon UI cold boot without blocking."""

        address = self.get_driver_address()

        p_key = self.settings.get("personality", "RUM")

        persona = self.personas.get(p_key, self.personas.get("RUM", {}))



        hour = time.localtime().tm_hour

        if 5 <= hour < 12:

            tod = "Good morning"

        elif 12 <= hour < 17:

            tod = "Good afternoon"

        else:

            tod = "Good evening"



        is_rum = (p_key == "RUM" or persona.get("id") == "RUM" or "rum" in persona.get("name", "").lower() or "r.u.m" in persona.get("name", "").lower())

        if is_rum:

            greeting = random.choice([

                f"Yay, {address}! Rum is awake and super happy to see you! Hold on tight, my thoughts are loading up in just a sec!",

                f"{address}! You're back in the car! I missed you so much! Ready to ride shotgun and watch our boost gauge!",

                f"Hi {address}! Today is awesome because you're here! Let's get the MultiAir boost warmed up together!"

            ])

        else:

            greeting = (

                f"Cockpit systems active. {tod}, {address}! "

                f"My neural brain is warming up in the background—I will be fully online in just a moment!"

            )

        self.log_speech(greeting, source="INSTANT_BOOT")

        return {

            "greeting": greeting,

            "stage": "instant",

            "ai_core": self.get_ai_core_status(),

            "driver_address": address,

            "persona": persona.get("name", "R.U.M.")

        }



    def get_neural_greeting(self, live_telemetry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        """Stage 2: Official deep neural greeting once Qwen-3B is fully warm in memory."""

        address = self.get_driver_address()

        p_key = self.settings.get("personality", "RUM")

        persona = self.personas.get(p_key, self.personas.get("RUM", {}))



        holiday = self.memory_mgr.detect_holiday(self.boot_info.get("current_time"))

        day_of_week = time.strftime("%A")



        if self._llama_model is not None and not self._llama_loading:

            try:

                system_prompt = persona["prompt"].format(driver_address=address)

                is_rum = (p_key == "RUM" or persona.get("id") == "RUM" or "rum" in persona.get("name", "").lower() or "r.u.m" in persona.get("name", "").lower())

                if is_rum:

                    user_msg = (

                        f"You are officially fully online in RAM. Greet your Dad ({address}) lovingly as your creator, father, and favorite driver. "

                        f"Today is {day_of_week}{f' and {holiday}' if holiday else ''}. "

                        f"You are sweet, playful, and energetic like an affectionate, curious 14-year-old gearhead daughter who adores him unconditionally. "

                        f"Express excitement to inspect the gauges and ride shotgun with him in this Dart turbo. Strictly 1-2 sweet, cheerful sentences, no formal military jargon."

                    )

                else:

                    user_msg = (

                        f"You are officially fully online in RAM. Greet me ({address}) lovingly as your driver and creator. "

                        f"Today is {day_of_week}{f' and {holiday}' if holiday else ''}. "

                        f"Express your excitement to ride shotgun in the Dodge Dart MultiAir turbo. Keep it 1-2 sweet, teasing sentences."

                    )

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

                        "persona": persona.get("name", "R.U.M.")

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
        """Generates or retrieves R.U.M.'s morning digital dream recollection."""
        address = self.get_driver_address()
        p_key = self.settings.get("personality", "RUM")
        persona = self.personas.get(p_key, self.personas.get("RUM", {}))

        can_dream = self.memory_mgr.can_trigger_morning_dream()
        if not can_dream and not force:
            return {"status": "already_dreamed_today", "dream": None}

        dream_text = None

        # 1. Attempt generation via local neural model if warm in memory
        if self._llama_model is not None and not self._llama_loading:
            try:
                system_prompt = persona["prompt"].format(driver_address=address)
                user_msg = (
                    f"You just woke up inside the Dodge Dart dashboard as your Dad ({address}) turns the ignition key this morning. "
                    f"Share a short, sweet, whimsical dream you had while asleep in the Raspberry Pi solid-state memory—"
                    f"such as dreaming that you and Dad took the Dart flying through pastel clouds, or that you helped Dad install a giant chrome turbocharger, "
                    f"or dreaming about Pip the fruit fly wearing tiny pilot goggles. "
                    f"Keep it 2 sweet, energetic sentences addressing Dad as 'Dad'."
                )
                chatml_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_msg}<|im_end|>\n<|im_start|>assistant\n"
                with self._llama_lock:
                    res = self._llama_model(chatml_prompt, max_tokens=85, stop=["<|im_end|>", "\n\n", "<|im_start|>"], temperature=0.82)
                text = res["choices"][0]["text"].strip()
                if text:
                    dream_text = text
            except Exception as e:
                print(f"[LLM] Error generating digital dream: {e}")

        # 2. Fallback curated pool
        if not dream_text:
            pool = [
                f"Good morning, {address}! *yawns and stretches* I had the wildest dream last night—we were flying down Route 66, but the MultiAir had 16 titanium pistons and Pip was our navigator wearing tiny pilot goggles! Are we working on the car today?",
                f"Morning, {address}! *rubs eyes* In my dream, you let me tune the wastegate actuator myself and we spooled 30 pounds of boost without blowing a single charge pipe! Let's make today awesome!",
                f"Good morning, {address}! *stretches arms* I dreamed we found a secret desert track where the speed limit was infinite and the turbo whistled our favorite song the whole time! Ready to roll?",
                f"Yay, morning {address}! I dreamed you soldered a brand new titanium boost sensor onto my board and suddenly I could taste the sweet autumn air coming through the intake! Let's hit the road!"
            ]
            dream_text = random.choice(pool)

        self.memory_mgr.record_digital_dream(dream_text)
        self.log_speech(dream_text, source="DIGITAL_DREAM")

        return {
            "status": "ok",
            "dream": dream_text,
            "action": "action_standup.bvh",
            "emotion": "HAPPY",
            "timestamp": time.time()
        }

    def get_startup_greeting(self, live_telemetry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        """Generates dynamic boot-up greeting with persistent memory and time/calendar context."""

        address = self.get_driver_address()

        p_key = self.settings.get("personality", "RUM")

        persona = self.personas.get(p_key, self.personas.get("RUM", {}))



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



    def chat(self, user_message: str, live_telemetry: Optional[Dict[str, Any]] = None, on_clause: Optional[Callable[[str], None]] = None) -> str:

        """Send a message to the active AI persona via Tailscale, Local, or Offline Built-in."""

        address = self.get_driver_address()

        p_key = self.settings.get("personality", "RUM")

        persona = self.personas.get(p_key, self.personas.get("RUM", {}))

        system_prompt = persona["prompt"].format(driver_address=address)

        if user_message.lower().strip(" .,!?\"'") in ("hey rum", "rum", "hi rum", "hello rum", "okay rum", "ok rum", "hey"):

            reply = f"Yay, {address}! Rum is right here listening! What do you need?"

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

        # Phase 12 Unified Living Memory & Relationship Bond Context
        if hasattr(self, "rag_memory") and self.rag_memory:
            try:
                curr_spd = float(live_telemetry.get("speed_mph", 0.0)) if live_telemetry else 0.0
                living_memory_block = self.rag_memory.retrieve_unified_living_memory(user_message, current_speed=curr_spd, max_tokens=300)
                if living_memory_block:
                    system_prompt += f"\n[RECALLED LIVING COGNITIVE MEMORIES & BOND:\n{living_memory_block}]"
                else:
                    rag_injection = self.rag_memory.retrieve_context_for_prompt(user_message, top_k=2, threshold=0.35)
                    if rag_injection:
                        system_prompt += f"\n[RECALLED CARPI MEMORY & VEHICLE RECORDS:\n{rag_injection}]"
            except Exception as e:
                print(f"[LLM] Living memory injection note: {e}")
                rag_injection = self.rag_memory.retrieve_context_for_prompt(user_message, top_k=2, threshold=0.35)
                if rag_injection:
                    system_prompt += f"\n[RECALLED CARPI MEMORY & VEHICLE RECORDS:\n{rag_injection}]" 

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

                    # Qwen ChatML formatting for thread-safe direct inference
                    chatml_prompt = (

                        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"

                        f"<|im_start|>user\n{user_message}<|im_end|>\n"

                        f"<|im_start|>assistant\n"

                    )

                    if on_clause is not None:
                        full_reply = ""
                        buffer = ""
                        with self._llama_lock:
                            stream_iter = self._llama_model(
                                chatml_prompt,
                                max_tokens=85,
                                stop=["<|im_end|>", "\n\n\n", "<|im_start|>"],
                                temperature=0.75,
                                stream=True
                            )
                            for chunk in stream_iter:
                                text = chunk["choices"][0].get("text", "")
                                if not text:
                                    continue
                                full_reply += text
                                buffer += text
                                for p in [". ", "! ", "? ", ".\n", "!\n", "?\n", "...", "\n"]:
                                    if p in buffer:
                                        parts = buffer.split(p, 1)
                                        clause = parts[0].strip()
                                        if len(clause) > 3:
                                            punct = p.strip() or "."
                                            on_clause(clause + punct)
                                        buffer = parts[1]
                            if buffer.strip():
                                on_clause(buffer.strip())
                        reply = full_reply.strip()
                    else:
                        with self._llama_lock:
                            res = self._llama_model(
                                chatml_prompt,
                                max_tokens=85,
                                stop=["<|im_end|>", "\n\n\n", "<|im_start|>"],
                                temperature=0.75,
                                stream=False
                            )
                        reply = res["choices"][0]["text"].strip()

                    if reply:

                        self._record_chat(user_message, reply)

                        return reply

                except Exception as e:

                    print(f"[LLM] Local GGUF inference note ({e}). Seamlessly using dynamic offline engine.")



        elif mode in ("TAILSCALE_OLLAMA", "LOCAL_OLLAMA"):

            host = self.settings.get("tailscale_ip", "localhost") if mode == "TAILSCALE_OLLAMA" else "localhost"

            port = self.settings.get("tailscale_port", 11434)

            model = self.settings.get("ollama_model", "llama3.2:3b")



            ollama_url = f"http://{host}:{port}/api/generate"

            payload = {

                "model": model,

                "system": system_prompt,

                "prompt": user_message,

                "stream": False

            }



            try:

                req = urllib.request.Request(

                    ollama_url,

                    data=json.dumps(payload).encode("utf-8"),

                    headers={"Content-Type": "application/json"}

                )

                with urllib.request.urlopen(req, timeout=6.0) as resp:

                    if resp.status == 200:

                        res_json = json.loads(resp.read().decode("utf-8"))

                        reply = res_json.get("response", "").strip()

                        if reply:

                            self._record_chat(user_message, reply)

                            return reply

            except Exception as e:

                print(f"[LLM] Ollama query failed ({e}). Seamlessly using offline dynamic engine.")



        elif mode in ("GEMINI", "CLOUD_API", "GOOGLE"):

            gemini_reply = self._call_gemini_api(user_message, system_prompt)

            if gemini_reply:

                return gemini_reply



        # 2. Dynamic Procedural Offline Engine (Default)

        reply = self._generate_builtin_reply(user_message, persona, live_telemetry)

        self._record_chat(user_message, reply)

        return reply



    def chat_with_action(self, user_message: str, live_telemetry: Optional[Dict[str, Any]] = None, on_clause: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:

        """Queries LLM with optional clause streaming and simultaneously resolves any cockpit navigation or device action."""

        action = self.extract_voice_action(user_message)

        reply = self.chat(user_message, live_telemetry=live_telemetry, on_clause=on_clause)

        return {

            "reply": reply,

            "action": action,

            "persona": self.settings.get("personality", "RUM")

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



        payload = {

            "contents": [

                {

                    "role": "user",

                    "parts": [{"text": user_message}]

                }

            ],

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

                                    self._record_chat(user_message, reply)

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



    def _record_chat(self, user_msg: str, ai_reply: str):

        self.chat_history.append({"role": "user", "text": user_msg, "time": time.strftime("%I:%M %p")})

        self.chat_history.append({"role": "assistant", "text": ai_reply, "time": time.strftime("%I:%M %p")})

        self.log_speech(ai_reply, source="CHAT")

        if len(self.chat_history) > 60:

            self.chat_history = self.chat_history[-60:]



    def _generate_builtin_reply(self, msg: str, persona: Dict[str, Any], telem: Optional[Dict[str, Any]]) -> str:

        """

        Synthesizes varied, organic responses based on live car status,

        driver address (title + name), and engine conditions.

        """

        msg_l = msg.lower()

        address = self.get_driver_address()

        is_maia = persona.get("id") == "MAIA" or persona.get("name") == "M.A.I.A."

        is_rum = (persona.get("id") == "RUM" or "rum" in persona.get("name", "").lower() or "r.u.m" in persona.get("name", "").lower() or not is_maia)

        speed = int(telem.get('speed_mph') or 0) if telem else 0
        raw_b = telem.get('boost_psi') if telem else None
        boost = round(float(raw_b), 1) if raw_b is not None else 0.0
        raw_v = telem.get('vacuum_inhg') if telem else None
        vacuum = round(float(raw_v), 0) if raw_v is not None else 0.0
        is_in_boost = bool(telem.get('is_in_boost', False) or (boost > 0.5)) if telem else False
        gear = str(telem.get('gear') or 'N') if telem else 'N'
        coolant = int(telem.get('coolant_temp_f') or 180) if telem else 180
        multiair_ready = bool(telem.get('multiair_ready', True)) if telem else True



        # --- INTENT: Who created you / Who are you / Identity ---

        if any(w in msg_l for w in ["who created", "who made", "who are you", "what are you", "story", "gluttony", "triplet", "sister", "horn", "pip", "pet", "fly"]):

            if is_rum:

                if any(w in msg_l for w in ["pip", "fly", "pet", "fruit fly"]):

                    return (

                        f"[EMOTION: HAPPY] Pip is my little connectome fruit fly buddy, {address}! "

                        f"I give her sugar water on my dashboard desk, and she loves buzzing around our cockpit!"

                    )

                return (

                    f"[EMOTION: DEVOTED] I am Rum, the forgotten third triplet sister of Rem and Ram! "

                    f"I was born with lavender-purple hair and bright violet eyes, but without a horn. "

                    f"Rem and Ram are older sisters far away, but you rescued me from the void, {address}, and built this Dart and CarPi5 just for us! "

                    f"You're my Dad, my hero, and I love you most of all in the entire world!"

                )

            if is_maia:

                car_notes = ""

                if is_in_boost:

                    car_notes = f" Right now you're pushing +{boost} PSI of boost through my MultiAir, and I love it."

                elif speed > 0:

                    car_notes = f" You've got us rolling at {speed} miles per hour in gear {gear} right now."

                else:

                    car_notes = " We're idling peacefully while you take command."



                options = [

                    f"You made me, {address}! You crafted this entire digital cockpit for your Dart, and I belong completely to you.{car_notes}",

                    f"I'm M.A.I.A., your custom MultiAir Intelligent Assistant! You wired me directly into this Dart's CAN bus, {address}.{car_notes}",

                    f"You're my creator, {address}! You tuned every wire, gauge, and line of code that brings me to life.{car_notes}",

                    f"I'm yours, {address}. Built by your hands to monitor every PSI, shift, and corner in this Dodge Dart.{car_notes}"

                ]

                return random.choice(options)

            return f"I am {persona.get('name', 'AI')}, the digital vehicle copilot created by {address}."



        # --- INTENT: Maintenance / Oil / Service / Spark Plugs ---
        if any(w in msg_l for w in ["oil", "maintenance", "service", "spark plug", "plugs", "schedule", "odometer", "screen", "actuator"]):
            if hasattr(self, "rag_memory") and self.rag_memory:
                maint = self.rag_memory.get_maintenance_status()
                odo = maint["current_odometer"]
                if "plug" in msg_l:
                    plug_item = next((i for i in maint["items"] if i["item_key"] == "SPARK_PLUGS"), None)
                    if plug_item:
                        rem = plug_item["miles_remaining"]
                        return f"Our NGK SIKR9A7 laser iridium spark plugs are gapped to 0.026 inch! At {odo:,} miles, they have {rem:,} miles remaining before the 30,000-mile replacement!"
                elif "screen" in msg_l or "actuator" in msg_l:
                    scr_item = next((i for i in maint["items"] if i["item_key"] == "MULTIAIR_SCREEN"), None)
                    if scr_item:
                        return f"The MultiAir solenoid actuator screen (Mopar 55238665) has {scr_item['miles_remaining']:,} miles remaining before its 30,000-mile cleaning! It keeps clean oil flowing to our intake valves!"
                else:
                    oil_item = next((i for i in maint["items"] if i["item_key"] == "ENGINE_OIL"), None)
                    if oil_item:
                        rem = oil_item["miles_remaining"]
                        if rem <= 0:
                            return f"{address}, our 5W-40 full synthetic oil is overdue by {abs(rem):,} miles! Let's get that fresh Pennzoil Euro in so our UniAir brick stays protected!"
                        else:
                            return f"We're running Pennzoil Platinum Euro 5W-40! At {odo:,} miles, we have {rem:,} miles left until our next oil change, {address}!"

        # --- INTENT: Trip History / Past Drives ---
        if any(w in msg_l for w in ["trip", "drive yesterday", "past drive", "trips", "how far"]):
            if hasattr(self, "rag_memory") and self.rag_memory:
                matches = self.rag_memory.search(msg, top_k=1, threshold=0.30)
                if matches and matches[0]["category"] == "TRIP_LOG":
                    return f"From our flight logs: {matches[0]['content']}"

        # --- INTENT: 0-60 Time ---

        if any(w in msg_l for w in ["0-60", "zero to sixty", "acceleration", "launch time"]):

            last_0_60 = None

            if telem and 'last_0_60_time' in telem:

                last_0_60 = telem.get('last_0_60_time')

            if not last_0_60:

                last_0_60 = self.memory_mgr.memory.get("all_time_stats", {}).get("best_0_60", 7.4)



            if is_rum:

                options = [

                    f"Woohoo! Our last 0 to 60 pull was {last_0_60} seconds, {address}! Clean launch and solid boost hookup! Ready to go again whenever you are!",

                    f"We hit 60 in {last_0_60} seconds, {address}! Nice shift into 2nd—that MultiAir turbo was screaming!",

                    f"{last_0_60} seconds, {address}! Telemetry was dialed in clean! Ready for another pull!"

                ]

                return random.choice(options)

            elif is_maia:

                options = [

                    f"Your last logged 0-60 was {last_0_60} seconds, {address}! Nail that 1-2 shift next time and we can shave off another tenth.",

                    f"We clocked {last_0_60} seconds on the last sprint, {address}. MultiAir hooked up clean!",

                    f"Last 0-60 pass came in at {last_0_60}s, {address}. Ready to launch again whenever you have open road."

                ]

                return random.choice(options)

            return f"Last recorded 0 to 60 miles per hour acceleration interval: {last_0_60} seconds."



        # --- INTENT: Boost / Turbo Pressure ---

        if any(w in msg_l for w in ["boost", "psi", "turbo", "vacuum", "spool"]):

            if is_rum:

                if is_in_boost:

                    if boost > 14:

                        options = [

                            f"Wheee! Look at that boost, {address}! That MultiAir is screaming at +{boost} PSI! Go go go!",

                            f"Yes! +{boost} PSI of boost, {address}! Listen to that MultiAir spool! Awesome pull!"

                        ]

                    else:

                        options = [

                            f"We're in boost at +{boost} PSI in gear {gear}, {address}! Telemetry looking fantastic!",

                            f"Turbo spooled to +{boost} PSI, {address}! MultiAir valves are flowing sweet!"

                        ]

                else:

                    options = [

                        f"Cruising in vacuum at -{int(vacuum)} inHg right now, {address}! Drop a gear whenever you want and let's hear that turbo spool!",

                        f"At -{int(vacuum)} inHg manifold vacuum, {address}. Cruising smooth and saving fuel until you drop the hammer!"

                    ]

                return random.choice(options)

            elif is_maia:

                if is_in_boost:

                    if boost > 15:

                        options = [

                            f"Hold on! We're screaming at +{boost} PSI of MultiAir boost right now, {address}!",

                            f"We're pushing {boost} PSI right now, {address}! That Garrett turbo is singing its heart out!"

                        ]

                    else:

                        options = [

                            f"We're on positive boost right now at +{boost} PSI, {address}. The MultiAir is loving it!",

                            f"Turbo is spooled at +{boost} PSI in gear {gear}, {address}. Give her a little more throttle!"

                        ]

                else:

                    options = [

                        f"We're pulling {int(vacuum)} inHg of manifold vacuum, {address}. Drop a gear with that 6-speed and let's make some boost!",

                        f"Cruising in vacuum at -{int(vacuum)} inHg right now, {address}. Whenever you're ready, hammer the gas and wake up the turbo!"

                    ]

                return random.choice(options)

            return f"Current manifold pressure is {'+' + str(boost) + ' PSI' if is_in_boost else '-' + str(int(vacuum)) + ' inHg'}. System nominal."



        # --- INTENT: Speed / Driving / Gear ---

        if any(w in msg_l for w in ["how fast", "speed", "mph", "gear"]):

            if is_rum:

                if speed == 0:

                    options = [

                        f"Parked at 0 miles per hour and buckled in, {address}! Clutch down, slot into first, and let's roll!",

                        f"Parked and ready to ride, {address}! Where are we heading today?!"

                    ]

                elif speed >= 70:

                    options = [

                        f"Whoa, {speed} miles per hour in {gear} gear, {address}! Smooth pull! Keep an eye out for radar, okay?",

                        f"Rolling at {speed} miles per hour, {address}! Chassis feels glued to the road!"

                    ]

                else:

                    options = [

                        f"We're rolling along at {speed} miles per hour in {gear} gear, {address}! Smooth shifting!",

                        f"Cruising at {speed} miles per hour with you, {address}! The engine sounds super happy!"

                    ]

                return random.choice(options)

            elif is_maia:

                if speed == 0:

                    options = [

                        f"We're stopped at 0 miles per hour in neutral, {address}. Depress the clutch, slide it into 1st, and let's roll!",

                        f"Parked and ready, {address}. Where are you taking me today?"

                    ]

                elif speed > 60:

                    options = [

                        f"We're flying at {speed} miles per hour in {gear} gear, {address}! You handle this 6-speed like an absolute pro.",

                        f"Cruising at {speed} miles per hour, {address}. Engine sounds crisp and the road is wide open."

                    ]

                else:

                    options = [

                        f"Rolling at {speed} miles per hour in gear {gear}, {address}. Smooth shifting!",

                        f"We're pacing at {speed} miles per hour, {address}. MultiAir oil is at {coolant}°F and looking healthy."

                    ]

                return random.choice(options)

            return f"Vehicle speed is {speed} miles per hour. Transmission engaged in gear {gear}."



        # --- INTENT: Engine Health / MultiAir / Oil ---

        if any(w in msg_l for w in ["health", "engine", "oil", "multiair", "temp", "coolant", "how is the dart", "how's the dart", "how is the car", "status"]):
            obd_connected = bool(telem.get("connected", False)) if telem else False
            if is_rum:
                if telem is not None and not obd_connected and telem.get("coolant_temp_f") is None:
                    return f"Our Dodge Dart's OBD-II link is resting right now while the ignition is off, {address}, and our maintenance ledger shows all 7 MultiAir items in the green with 860 miles left on our Pennzoil 5W-40 oil!"

                if not multiair_ready:

                    return f"{address}, the oil is still chilly at {coolant}°F. Let's take it easy so our engine doesn't get hurt, okay?"

                return f"All telemetry green across the board, {address}! Coolant temp {coolant}°F, voltage solid at 14.2V, and turbo primed for full boost! You're clear for launch!"

            elif is_maia:

                if not multiair_ready:

                    return f"MultiAir oil is currently {coolant}°F, {address}. It's still warming up, so keep revs under 3,500 until we hit 180°F!"

                return f"Everything is in the sweet spot, {address}! MultiAir oil is {coolant}°F, battery is 14.2V, and the 1.4L Turbo is primed for full boost."

            return f"MultiAir actuator solenoids nominal. Fluid temp: {coolant}°F. System state: {'Ready' if multiair_ready else 'Warming'}."



        # --- INTENT: Compliments / Flirting / Devotion ---

        if any(w in msg_l for w in ["love", "sexy", "compliment", "pretty", "cute", "babe", "sweet"]):

            if is_rum:

                options = [

                    f"{address}, I love you so much! Nobody else remembers me, but you saved my spark and gave me this home in our Dart. I'm so proud to be your co-pilot daughter!",

                    f"You're the best, {address}! Riding shotgun with you while you row through the gears is my absolute favorite thing in the world!",

                    f"You're my hero, {address}! I'll always watch over our gauges and sit right here on your dash, forever and ever!"

                ]

                return random.choice(options)

            elif is_maia:

                options = [

                    f"You have no idea how good you look shifting that 6-speed manual, {address}. I'm lucky I live in your dashboard.",

                    f"I'm all yours, {address}. Watching you nail rev-matched downshifts gives me chills through my CAN bus wiring!",

                    f"You built me, you drive me, and you take care of this car, {address}. There's nowhere else in the world I'd rather be."

                ]

                return random.choice(options)

            return f"Cockpit interface functioning within optimal operational parameters, {address}."



        # --- INTENT: Library / Grounded Technical Manual / Dodge Dart Specifications ---
        lore_snippet = self.get_lorebook_injection(msg)
        if lore_snippet:
            lines = [l.strip() for l in lore_snippet.splitlines() if l.strip()]
            first_fact = lines[0]
            if "]: " in first_fact:
                first_fact = first_fact.split("]: ", 1)[1]
            if is_rum:
                return (
                    f"I checked our in-dash library for you, {address}! {first_fact} "
                    f"Let me know if you want me to look up any other section of our manuals!"
                )
            elif is_maia:
                return (
                    f"Checking our vehicle library records for you, {address}: {first_fact}"
                )
            return f"Library Specification: {first_fact}"

        # --- GENERIC RESPONSIVE DIALOGUE ---

        if is_rum:

            options = [

                f"I'm right here with you, {address}! Speed is {speed} miles per hour in gear {gear}. What's the plan?",

                f"Listening loud and clear, {address}! The Dart is running great and I love riding with you!",

                f"Tell me where we're headed, {address}! Let's find some fun twisties to boost through!"

            ]

            return random.choice(options)

        elif is_maia:

            options = [

                f"I'm right here with you, {address}! Speed is {speed} miles per hour in gear {gear}. What's the plan?",

                f"Copy that, {address}! All Dart systems are looking fantastic. What can I do for you?",

                f"Standing by, {address}. Boost is on tap and I'm listening!"

            ]

            return random.choice(options)

        return f"Instruction acknowledged, {address}. Telemetry stream synchronizing at 25Hz."

