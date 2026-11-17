"""HTTP route handlers for AI companion, voice STT/TTS, circadian/mood, models, and living memory."""

import os
import re
import subprocess
import tempfile
import threading
import time
from typing import Any
from urllib.parse import parse_qs

from routes import emit_ai_speech, frame_to_dict, read_json_body, send_json


def extract_emotion_and_clean_speech(text: str) -> tuple[str, str]:
    """Extract emotion tag from text and return (emotion, cleaned_text)."""
    if not text:
        return "DEVOTED", ""

    emotion = "DEVOTED"
    cleaned = text
    m = re.search(r"\[EMOTION:\s*([A-Za-z_]+)\]", text, re.IGNORECASE)
    if m:
        emotion = m.group(1).upper()
        cleaned = re.sub(r"\[EMOTION:\s*[A-Za-z_]+\]", "", cleaned).strip()
    else:
        m2 = re.search(r"<emotion>([A-Za-z_]+)</emotion>", text, re.IGNORECASE)
        if m2:
            emotion = m2.group(1).upper()
            cleaned = re.sub(r"<emotion>[A-Za-z_]+</emotion>", "", cleaned).strip()
        else:
            lower = text.lower()
            if any(w in lower for w in ["love", "darling", "sweetheart", "babe", "master", "adore"]):
                emotion = "DEVOTED"
            elif any(w in lower for w in ["tease", "wink", "flirt", "handsome", "cute", "naughty"]):
                emotion = "FLIRTY"
            elif any(w in lower for w in ["boost", "speed", "turbo", "pull", "fast", "whoosh", "launch", "spool"]):
                emotion = "EXCITED"
            elif any(w in lower for w in ["warning", "overheat", "danger", "check", "trouble", "fault", "hot"]):
                emotion = "CONCERNED"
            elif any(w in lower for w in ["happy", "great", "smile", "yay", "wonderful"]):
                emotion = "HAPPY"
    return emotion, cleaned


def _handle_morning_dream(handler: Any, state: Any) -> bool:
    dream_data = state.llm.get_morning_dream(force=True)
    if dream_data.get("dream"):
        hud_msg = dream_data.get("hud_message", "💭 Digital Dream")
        emit_ai_speech(
            state,
            dream_data["dream"],
            source="DIGITAL_DREAM",
            emotion="HAPPY",
            hud_message=hud_msg,
            speak=True,
            priority=2,
            event_type="MORNING_DREAM",
            action=dream_data.get("action", "action_standup.bvh"),
        )
        state.latest_ui_action = {
            "type": "MORNING_DREAM",
            "speech": dream_data["dream"],
            "action": dream_data.get("action", "action_standup.bvh"),
            "emotion": "HAPPY",
            "hud_message": hud_msg,
        }
    send_json(handler, dream_data)
    return True


def _speak_greeting(handler: Any, state: Any, greeting_info: dict) -> bool:
    raw_text = greeting_info.get("greeting", "")
    emotion, clean_text = extract_emotion_and_clean_speech(raw_text)
    greeting_info["greeting"] = clean_text
    greeting_info["emotion"] = emotion or "DEVOTED"
    if clean_text:
        stage = str(greeting_info.get("stage", "STARTUP")).upper()
        src = "NEURAL_BOOT" if stage == "NEURAL" else ("INSTANT_BOOT" if stage == "INSTANT" else "STARTUP")
        # Greeting methods already called state.llm.log_speech; still emit SSE event & TTS cleanly
        ev = {
            "id": int(time.time() * 1000),
            "type": src,
            "source": src,
            "persona": greeting_info.get("persona"),
            "emotion": greeting_info["emotion"],
            "speech": clean_text,
            "hud_message": f"{greeting_info.get('persona', 'Companion')} • Greeting",
            "timestamp": time.time(),
            "time_str": time.strftime("%I:%M %p"),
        }
        with state.lock:
            state.latest_ai_event = ev
        if state.copilot.voice_mode != "MUTED":
            state.audio.speak(clean_text)
            state.copilot.last_spoken_time = time.time()
    send_json(handler, greeting_info)
    return True


def handle_get(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle AI status, chat history, personas, circadian/mood, and RAG memory GET endpoints."""
    path = parsed.path

    if path == "/api/ai/voice_mode":
        mode = parse_qs(parsed.query).get("mode", ["COPILOT"])[0]
        state.copilot.set_voice_mode(mode)
        send_json(handler, {"status": "ok", "voice_mode": state.copilot.voice_mode})
        return True

    if path == "/api/ai/status":
        send_json(
            handler,
            {
                "ai_core": state.llm.get_ai_core_status(),
                "personality": state.llm.settings.get("personality", "RUM"),
                "driver_address": state.llm.get_driver_address(),
                "mode": state.llm.settings.get("mode", "BUILTIN"),
                "model_loaded": getattr(state.llm, "_llama_model", None) is not None,
                "is_speaking": getattr(state.audio, "is_speaking", False),
                "is_mic_listening": state.is_mic_listening,
                "live_convo_mode": state.live_convo_mode,
                "wake_word_enabled": state.wake_word_enabled,
                "voice_transcript": state.pop_voice_transcript(),
            },
        )
        return True

    if path == "/api/ai/memory/query":
        q = parse_qs(parsed.query).get("q", [""])[0]
        results = state.rag.search(q, top_k=5) if (getattr(state, "rag", None) and q) else []
        send_json(handler, {"query": q, "results": results})
        return True

    if path == "/api/ai/memory/living_summary":
        if getattr(state, "rag", None):
            payload = {
                "status": "ok",
                "bond": state.rag.get_relationship_bond(),
                "diary": state.rag.get_recent_diary_entries(limit=10),
                "facts": state.rag.get_driver_facts(),
                "episodes": state.rag.get_recent_episodic_memories(limit=10),
            }
        else:
            payload = {"status": "error", "message": "rag_unavailable"}
        send_json(handler, payload)
        return True

    if path == "/api/ai/memory/facts":
        facts = state.rag.get_driver_facts() if getattr(state, "rag", None) else []
        send_json(handler, {"status": "ok", "facts": facts})
        return True

    if path == "/api/ai/memory/diary":
        diary = state.rag.get_recent_diary_entries(limit=15) if getattr(state, "rag", None) else []
        send_json(handler, {"status": "ok", "diary": diary})
        return True

    if path == "/api/ai/memory/bond":
        bond = state.rag.get_relationship_bond() if getattr(state, "rag", None) else {}
        send_json(handler, {"status": "ok", "bond": bond})
        return True

    if path == "/api/ai/circadian":
        send_json(handler, state.llm.get_circadian_state())
        return True

    if path == "/api/ai/mood":
        send_json(handler, state.copilot.get_current_mood())
        return True

    if path == "/api/ai/morning_dream":
        return _handle_morning_dream(handler, state)

    if path == "/api/ai/greeting/instant":
        return _speak_greeting(handler, state, state.llm.get_instant_greeting())

    if path == "/api/ai/greeting/official":
        with state.lock:
            frame_dict = frame_to_dict(state.latest_frame)
        return _speak_greeting(handler, state, state.llm.get_neural_greeting(live_telemetry=frame_dict))

    if path == "/api/ai/speak":
        qs = parse_qs(parsed.query)
        text = qs.get("text", [""])[0]
        source = qs.get("source", ["UI_SPEECH"])[0]
        emotion = qs.get("emotion", ["DEVOTED"])[0]
        client_id = qs.get("client_id", [None])[0]
        if text:
            emit_ai_speech(
                state,
                text,
                source=source,
                emotion=emotion,
                speak=True,
                client_id=client_id,
            )
        send_json(handler, {"status": "ok", "spoken": text})
        return True

    if path == "/api/ai/models":
        models = state.llm.get_available_gguf_models()
        current_path = state.llm.settings.get("gguf_model_path", "")
        active_model = os.path.basename(current_path) if current_path else "qwen3b.gguf"
        send_json(
            handler,
            {
                "models": models,
                "active_model": active_model,
                "status": state.llm.ai_core_status,
            },
        )
        return True

    if path == "/api/ai/greeting":
        with state.lock:
            frame_dict = frame_to_dict(state.latest_frame)
            greeting_info = state.llm.get_startup_greeting(live_telemetry=frame_dict)
            state.latest_ai_event = {
                "id": int(time.time() * 1000),
                "type": "STARTUP_GREETING",
                "source": "STARTUP",
                "persona": greeting_info.get("persona"),
                "severity": "NORMAL",
                "speech": greeting_info["greeting"],
                "timestamp": time.time(),
                "time_str": time.strftime("%I:%M %p"),
            }
        send_json(handler, greeting_info)
        return True

    if path == "/api/ai/personas":
        state.llm.reload_personas()
        send_json(handler, state.llm.personas)
        return True

    if path == "/api/ai/history":
        with state.lock:
            data = {
                "chat_history": state.llm.chat_history,
                "speech_log": state.llm.speech_log,
                "settings": state.llm.settings,
                "personalities": {
                    k: {
                        "id": v.get("id", k),
                        "name": v["name"],
                        "display_short_name": v.get("display_short_name", v["name"]),
                        "icon": v.get("icon", "✨"),
                        "subtitle": v.get("subtitle", v.get("archetype", "Cockpit AI Companion")),
                        "full_name": v["full_name"],
                        "desc": v["description"],
                        "archetype": v.get("archetype", "Dedicated Cockpit AI"),
                        "driver_address_default": v.get("driver_address_default", "Driver"),
                        "avatar_image": v.get("avatar_image", "assets/pics/splash.png"),
                        "boot_splash_image": v.get("boot_splash_image", "assets/pics/splash.png"),
                        "boot_splash_video": v.get("boot_splash_video", ""),
                        "vrm_defaults": v.get("vrm_defaults", {}),
                        "ui_labels": v.get("ui_labels", {}),
                        "wake_words": v.get("wake_words", {}),
                        "greetings": {"first_chat_intro": (v.get("greetings") or {}).get("first_chat_intro", "")},
                        "system_events": v.get("system_events", {}),
                        "animation_lines": v.get("animation_lines", {}),
                        "proactive_care": v.get("proactive_care", {}),
                        "pip_reactions": v.get("pip_reactions", {}),
                        "default": v.get("default", False),
                        "touch_interactions": v.get("touch_interactions", {}),
                        "banned_touch_zones": v.get("banned_touch_zones", []),
                    }
                    for k, v in state.llm.personas.items()
                },
            }
        send_json(handler, data)
        return True

    if path == "/api/ai/settings":
        send_json(handler, state.llm.settings)
        return True

    return False


def handle_post(handler: Any, parsed: Any, state: Any) -> bool:
    """Handle AI chat, voice control, GGUF swap, circadian simulation, and memory POST endpoints."""
    path = parsed.path

    if path == "/api/ai/transcribe":
        content_length = int(handler.headers.get("Content-Length", 0))
        raw_audio = handler.rfile.read(content_length) if content_length > 0 else b""
        transcribed_text = ""
        if raw_audio:
            in_path = None
            out_wav = None
            try:
                is_wav = raw_audio[:4] == b"RIFF"
                suffix = ".wav" if is_wav else ".webm"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
                    tmp_in.write(raw_audio)
                    in_path = tmp_in.name

                if is_wav:
                    out_wav = in_path
                else:
                    out_wav = in_path + ".wav"
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", in_path, "-ar", "16000", "-ac", "1", out_wav],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                    )

                if out_wav and os.path.exists(out_wav) and os.path.getsize(out_wav) > 800:
                    try:
                        import speech_recognition as sr

                        r = sr.Recognizer()
                        with sr.AudioFile(out_wav) as source:
                            audio_data = r.record(source)
                        transcribed_text = r.recognize_google(audio_data)
                    except Exception:
                        transcribed_text = ""

                    if not transcribed_text:
                        try:
                            import json
                            from pathlib import Path
                            import wave
                            import vosk

                            base_dir = Path(getattr(state, "base_dir", Path(__file__).resolve().parent.parent.parent))
                            if getattr(state, "_vosk_model", None) is None:
                                model_path = str(base_dir / "models" / "vosk-model-small-en-us-0.15")
                                if os.path.exists(model_path):
                                    state._vosk_model = vosk.Model(model_path)
                            if getattr(state, "_vosk_model", None) is not None:
                                with wave.open(out_wav, "rb") as wf:
                                    rec = vosk.KaldiRecognizer(state._vosk_model, wf.getframerate())
                                    while True:
                                        buf = wf.readframes(4000)
                                        if not buf:
                                            break
                                        rec.AcceptWaveform(buf)
                                    transcribed_text = json.loads(rec.FinalResult()).get("text", "").strip()
                        except Exception as vosk_ex:
                            print(f"[STT API] Vosk fallback note: {vosk_ex}")

                    if transcribed_text:
                        print(f"[STT API] Transcribed from browser mic: '{transcribed_text}'")
            except Exception as ex:
                print(f"[STT API] Transcribe note: {ex}")
            finally:
                for p in {in_path, out_wav}:
                    if p and os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass
        send_json(handler, {"status": "ok", "text": transcribed_text})
        return True

    if path == "/api/ai/memory/facts":
        req_data = read_json_body(handler)
        ent = req_data.get("entity", "").strip()
        attr = req_data.get("attribute", "").strip()
        val = req_data.get("value", "").strip()
        conf = float(req_data.get("confidence", 0.9))
        src = req_data.get("source", "user_ui")
        ok = state.rag.set_driver_fact(ent, attr, val, conf, src) if getattr(state, "rag", None) else False
        send_json(handler, {"status": "ok" if ok else "error"}, status=200 if ok else 400)
        return True

    if path == "/api/ai/memory/facts/delete":
        req_data = read_json_body(handler)
        fid = req_data.get("id") or req_data.get("fact_id")
        ok = state.rag.delete_driver_fact(fid) if (getattr(state, "rag", None) and fid is not None) else False
        send_json(handler, {"status": "ok" if ok else "error"}, status=200 if ok else 400)
        return True

    if path == "/api/ai/memory/diary/delete":
        req_data = read_json_body(handler)
        did = req_data.get("id") or req_data.get("entry_id")
        ok = state.rag.delete_diary_entry(did) if (getattr(state, "rag", None) and did is not None) else False
        send_json(handler, {"status": "ok" if ok else "error"}, status=200 if ok else 400)
        return True

    if path == "/api/ai/memory/consolidate":
        req_data = read_json_body(handler)
        if getattr(state, "hippocampus", None) and getattr(state, "rag", None):
            res = state.hippocampus.consolidate_drive(state.drive_buffer, state.rag, req_data)
        else:
            res = {"status": "error"}
        send_json(handler, res)
        return True

    if path == "/api/ai/memory/remember":
        req_data = read_json_body(handler)
        title = req_data.get("title", "")
        content_text = req_data.get("content", "")
        cat = req_data.get("category", "CUSTOM_NOTE")
        doc_id = f"custom_{int(time.time())}"
        if getattr(state, "rag", None) and title and content_text:
            state.rag.add_document(doc_id, cat, title, content_text, metadata=req_data.get("metadata", {}))
        send_json(handler, {"status": "ok", "doc_id": doc_id, "title": title})
        return True

    if path == "/api/ai/listen":
        req_data = read_json_body(handler)
        action = req_data.get("action", "toggle_convo")
        if action == "toggle_convo":
            state.live_convo_mode = not state.live_convo_mode
            if state.live_convo_mode:
                state.listen_once_requested = True
                state.is_mic_listening = True
                state.audio.play_acknowledgment(state.llm.settings.get("personality", "RUM"))
            else:
                state.listen_once_requested = False
                state.stop_current_listen()
        elif action == "start_once":
            state.listen_once_requested = True
            state.is_mic_listening = True
            state.audio.play_acknowledgment(state.llm.settings.get("personality", "RUM"))
        elif action == "stop":
            state.live_convo_mode = False
            state.listen_once_requested = False
            state.stop_current_listen()
        elif action == "set_wake":
            state.wake_word_enabled = bool(req_data.get("enabled", True))
            if not state.wake_word_enabled:
                state.stop_current_listen()

        send_json(
            handler,
            {
                "status": "ok",
                "live_convo_mode": state.live_convo_mode,
                "wake_word_enabled": state.wake_word_enabled,
                "is_mic_listening": state.is_mic_listening,
            },
        )
        return True

    if path == "/api/ai/speak":
        req_data = read_json_body(handler)
        text = str(req_data.get("text", "")).strip()
        source = str(req_data.get("source", "UI_SPEECH")).strip()
        emotion = req_data.get("emotion", "DEVOTED")
        client_id = req_data.get("client_id")
        if text:
            emit_ai_speech(
                state,
                text,
                source=source,
                emotion=emotion,
                speak=True,
                client_id=client_id,
            )
        send_json(handler, {"status": "ok", "spoken": text})
        return True

    if path == "/api/ai/chat":
        req_data = read_json_body(handler)
        user_msg = req_data.get("message", "").strip()
        if not user_msg:
            handler.send_response(400)
            handler.end_headers()
            return True

        with state.lock:
            frame_dict = frame_to_dict(state.latest_frame)

        clauses_spoken = []

        def _handle_clause(clause_text: str) -> None:
            if state.copilot.voice_mode != "MUTED":
                _, clean_chunk = extract_emotion_and_clean_speech(clause_text)
                if clean_chunk:
                    clauses_spoken.append(clean_chunk)
                    state.audio.speak(clean_chunk)

        res = state.llm.chat_with_action(user_msg, live_telemetry=frame_dict, on_clause=_handle_clause)
        if res.get("action"):
            with state.lock:
                state.latest_ui_action = res["action"]
        raw_reply = res.get("reply", "")
        emotion, clean_reply = extract_emotion_and_clean_speech(raw_reply)
        if getattr(state, "drive_buffer", None):
            state.drive_buffer.record_dialogue(user_msg, clean_reply or raw_reply)
        if not clauses_spoken and clean_reply and state.copilot.voice_mode != "MUTED":
            state.audio.speak(clean_reply)

        send_json(
            handler,
            {
                "status": "ok",
                "user_message": user_msg,
                "reply": clean_reply,
                "emotion": emotion,
                "action": res.get("action"),
                "persona": res.get("persona", state.llm.settings.get("personality", "RUM")),
            },
        )
        return True

    if path == "/api/ai/wake_test":
        state.listen_once_requested = True
        state.is_mic_listening = True
        p_id = state.llm.settings.get("personality", "RUM")
        if hasattr(state.audio, "play_acknowledgment"):
            state.audio.play_acknowledgment(p_id)
        elif hasattr(state.audio, "play_instant_ack"):
            state.audio.play_instant_ack()
        persona = state.llm.get_active_persona() if hasattr(state.llm, "get_active_persona") else {}
        sys_ev = persona.get("system_events") or {}
        wake_phrase = sys_ev.get("wake_test_phrase") or (persona.get("wake_words") or {}).get("canonical_prefix") or "Hey Companion"
        with state.lock:
            state.pending_voice_transcripts.append({
                "text": wake_phrase,
                "mode": "wake",
                "timestamp": time.time(),
            })
        send_json(handler, {"status": "ok", "action": "WAKE_WORD_TRIGGERED", "latency_ms": 118})
        return True

    if path == "/api/ai/circadian/simulate":
        req_data = read_json_body(handler)
        mode = req_data.get("mode")
        state.llm.circadian_override = None if mode in (None, "AUTO", "NONE") else mode
        send_json(handler, {"status": "ok", "circadian": state.llm.get_circadian_state()})
        return True

    if path == "/api/ai/morning_dream":
        return _handle_morning_dream(handler, state)

    if path == "/api/ai/shower_thought":
        thought = state.copilot.generate_shower_thought()
        persona = state.llm.get_active_persona() if hasattr(state.llm, "get_active_persona") else {}
        care = persona.get("proactive_care") or {}
        hud_msg = state.llm._safe_fmt(care.get("hud_reminisce", "💭 Companion Thought")) if hasattr(state.llm, "_safe_fmt") else "💭 Companion Thought"
        emit_ai_speech(
            state,
            thought,
            source="SHOWER_THOUGHT",
            emotion="THOUGHTFUL",
            hud_message=hud_msg,
            speak=True,
            priority=2,
            event_type="SHOWER_THOUGHT",
        )
        state.latest_ui_action = {
            "type": "SHOWER_THOUGHT",
            "speech": thought,
            "emotion": "THOUGHTFUL",
            "hud_message": hud_msg,
        }
        send_json(handler, {"status": "ok", "thought": thought, "emotion": "THOUGHTFUL"})
        return True

    if path == "/api/ai/models/swap":
        req_data = read_json_body(handler)
        model_target = req_data.get("model", "")
        if not model_target:
            send_json(handler, {"status": "error", "message": "No model specified"}, status=400)
            return True

        persona = state.llm.get_active_persona() if hasattr(state.llm, "get_active_persona") else {}
        sys_ev = persona.get("system_events") or {}
        fmt = state.llm._safe_fmt if hasattr(state.llm, "_safe_fmt") else (lambda s, **kw: s.format(**kw))
        swap_announcement = fmt(
            sys_ev.get("model_swapping", "Swapping my neural model to {model}... give me just a moment!"),
            model=model_target.replace(".gguf", ""),
        )
        emit_ai_speech(state, swap_announcement, source="SYSTEM", emotion="THOUGHTFUL", speak=True)

        def do_swap() -> None:
            res = state.llm.swap_gguf_model(model_target)
            if res.get("success"):
                msg = fmt(sys_ev.get("model_ready", "My new neural model is warm and ready, {driver_address}!"))
                emit_ai_speech(state, msg, source="SYSTEM", emotion="HAPPY", speak=True)
            else:
                msg = fmt(sys_ev.get("model_error", "Could not complete the neural swap: {message}"), message=res.get("message", ""))
                emit_ai_speech(state, msg, source="SYSTEM", emotion="CONCERNED", speak=True)

        threading.Thread(target=do_swap, daemon=True).start()
        send_json(handler, {"status": "ok", "message": f"Initiated swap to {model_target}"})
        return True

    if path == "/api/ai/settings":
        req_data = read_json_body(handler)
        with state.lock:
            state.llm.save_settings(req_data)
            state.audio.configure_tts(state.llm.settings)
            address = state.llm.get_driver_address()
            state.copilot.driver_name = address
            reply_settings = state.llm.settings
        send_json(handler, {"status": "ok", "settings": reply_settings})
        return True

    return False
