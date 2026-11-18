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
    try:
        from ai.emote_choreographer import analyze_reply_choreography
    except ImportError:
        from backend.ai.emote_choreographer import analyze_reply_choreography
    res = analyze_reply_choreography(text)
    return res["hud_emotion"], res["speech"]


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
                "personality": state.llm.settings.get("personality") or (state.llm.get_default_persona_id() if hasattr(state.llm, "get_default_persona_id") else "COMPANION"),
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
            learned = state.llm.get_learned_facts() if hasattr(state.llm, "get_learned_facts") else []
            payload = {
                "status": "ok",
                "bond": state.rag.get_relationship_bond(),
                "diary": state.rag.get_recent_diary_entries(limit=10),
                "facts": state.rag.get_driver_facts(),
                "episodes": state.rag.get_recent_episodic_memories(limit=10),
                "learned_web": learned,
            }
        else:
            payload = {"status": "error", "message": "rag_unavailable"}
        send_json(handler, payload)
        return True

    if path == "/api/ai/memory/learned":
        learned = state.llm.get_learned_facts() if hasattr(state.llm, "get_learned_facts") else []
        send_json(handler, {"status": "ok", "learned_facts": learned})
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
        ev = None
        if text:
            ev = emit_ai_speech(
                state,
                text,
                source=source,
                emotion=emotion,
                speak=True,
                client_id=client_id,
            )
        send_json(
            handler,
            {
                "status": "ok",
                "spoken": ev["speech"] if ev else text,
                "emotion": ev["emotion"] if ev else emotion,
                "goemotion": ev.get("goemotion") if ev else None,
                "emote_clip": ev.get("emote_clip") if ev else None,
            },
        )
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
        qs = parse_qs(parsed.query)
        target_id = qs.get("id", [""])[0].strip().upper()
        if target_id:
            if target_id in state.llm.personas:
                send_json(handler, {"status": "ok", "persona": state.llm.personas[target_id]})
            else:
                send_json(handler, {"status": "error", "message": f"Persona '{target_id}' not found"}, status=404)
            return True
        send_json(handler, state.llm.personas)
        return True

    if path == "/api/ai/voices":
        base_dir = getattr(state, "base_dir", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        kokoro_voices = ["af_nicole", "af_bella", "af_heart", "af_sky", "af_nova", "am_adam", "am_michael", "bf_emma", "bm_george"]
        kokoro_inst = getattr(state.audio, "_kokoro_instance", None) if getattr(state, "audio", None) else None
        if kokoro_inst and hasattr(kokoro_inst, "get_voices"):
            try:
                live_voices = [str(v) for v in (kokoro_inst.get_voices() or []) if v]
                for v in live_voices:
                    if v not in kokoro_voices:
                        kokoro_voices.append(v)
            except Exception:
                pass
        piper_models = []
        models_dir = os.path.join(str(base_dir), "models")
        if os.path.exists(models_dir):
            for fn in sorted(os.listdir(models_dir)):
                if fn.endswith(".onnx") and "kokoro" not in fn.lower():
                    piper_models.append(fn)
        ack_folders = ["default"]
        ack_root = os.path.join(str(base_dir), "assets", "sounds", "acknowledgments")
        if os.path.exists(ack_root):
            for entry in sorted(os.listdir(ack_root)):
                if os.path.isdir(os.path.join(ack_root, entry)) and entry not in ack_folders:
                    ack_folders.append(entry)
        send_json(handler, {
            "status": "ok",
            "kokoro_voices": kokoro_voices,
            "piper_models": piper_models,
            "acknowledgments_folders": ack_folders,
        })
        return True

    if path == "/api/ai/history":
        with state.lock:
            if hasattr(state.llm, "reload_personas"):
                state.llm.reload_personas()
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
                        "age_spirit": v.get("age_spirit", ""),
                        "archetype": v.get("archetype", "Dedicated Cockpit AI"),
                        "driver_address_default": v.get("driver_address_default", "Driver"),
                        "avatar_image": v.get("avatar_image", "assets/pics/splash.png"),
                        "boot_splash_image": v.get("boot_splash_image", "assets/pics/splash.png"),
                        "boot_splash_video": v.get("boot_splash_video", ""),
                        "boot_splash_title": v.get("boot_splash_title", f"{v.get('name', k)} • CARPI5"),
                        "boot_splash_subtitle": v.get("boot_splash_subtitle", v.get("subtitle", v.get("archetype", "Cockpit AI Companion"))),
                        "voice_engine": v.get("voice_engine", "KOKORO"),
                        "kokoro_voice": v.get("kokoro_voice", "af_bella"),
                        "pitch_factor": v.get("pitch_factor", 1.12),
                        "tts_pitch": v.get("tts_pitch", v.get("pitch_factor", 1.12)),
                        "speech_speed": v.get("speech_speed", 1.00),
                        "elevenlabs_voice_id": v.get("elevenlabs_voice_id", ""),
                        "acknowledgments_folder": v.get("acknowledgments_folder", str(k).lower()),
                        "vrm_defaults": v.get("vrm_defaults", {}),
                        "ui_labels": v.get("ui_labels", {}),
                        "wake_words": v.get("wake_words", {}),
                        "greetings": {"first_chat_intro": (v.get("greetings") or {}).get("first_chat_intro", "")},
                        "system_events": v.get("system_events", {}),
                        "animation_lines": v.get("animation_lines", {}),
                        "proactive_care": v.get("proactive_care", {}),
                        "pip_reactions": v.get("pip_reactions", {}),
                        "emote_profile": v.get("emote_profile", {}),
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

    if path == "/api/ai/memory/learned/delete":
        req_data = read_json_body(handler)
        target_key = req_data.get("index") if req_data.get("index") is not None else req_data.get("keyword")
        ok = state.llm.delete_learned_fact(target_key) if (hasattr(state.llm, "delete_learned_fact") and target_key is not None) else False
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
                state.audio.play_acknowledgment(state.llm.settings.get("personality") or (state.llm.get_default_persona_id() if hasattr(state.llm, "get_default_persona_id") else "COMPANION"))
            else:
                state.listen_once_requested = False
                state.stop_current_listen()
        elif action == "start_once":
            state.listen_once_requested = True
            state.is_mic_listening = True
            state.audio.play_acknowledgment(state.llm.settings.get("personality") or (state.llm.get_default_persona_id() if hasattr(state.llm, "get_default_persona_id") else "COMPANION"))
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

    if path == "/api/ai/personas/save":
        req_data = read_json_body(handler)
        p_payload = req_data.get("persona") if isinstance(req_data.get("persona"), dict) else req_data
        set_active = bool(req_data.get("set_active", False))
        with state.lock:
            res = state.llm.save_persona(p_payload, set_active=set_active)
            if res.get("status") == "ok" and set_active:
                state.audio.configure_tts(state.llm.settings)
                if getattr(state, "copilot", None):
                    state.copilot.driver_name = state.llm.get_driver_address()
        send_json(handler, res, status=200 if res.get("status") == "ok" else 400)
        return True

    if path == "/api/ai/personas/delete":
        req_data = read_json_body(handler)
        p_id = str(req_data.get("id") or req_data.get("persona_id") or "").strip()
        with state.lock:
            res = state.llm.delete_persona(p_id)
            if res.get("status") == "ok":
                state.audio.configure_tts(state.llm.settings)
        send_json(handler, res, status=200 if res.get("status") == "ok" else 400)
        return True

    if path == "/api/ai/personas/autofill":
        req_data = read_json_body(handler)
        res = state.llm.autofill_persona_fields(req_data)
        send_json(handler, {"status": "ok", "fields": res})
        return True

    if path == "/api/ai/speak":
        req_data = read_json_body(handler)
        text = str(req_data.get("text", "")).strip()
        source = str(req_data.get("source", "UI_SPEECH")).strip()
        emotion = req_data.get("emotion", "DEVOTED")
        client_id = req_data.get("client_id")
        preview_eng = req_data.get("tts_engine")
        preview_voice = req_data.get("kokoro_voice")
        preview_pitch = req_data.get("tts_pitch")
        preview_speed = req_data.get("speech_speed")
        has_preview = any(x not in (None, "") for x in (preview_eng, preview_voice, preview_pitch, preview_speed))
        saved_audio = None
        if has_preview and getattr(state, "audio", None):
            saved_audio = (
                state.audio.tts_engine,
                state.audio.kokoro_voice,
                state.audio.pitch_factor,
                getattr(state.audio, "speech_speed", 1.00),
            )
            state.audio.configure_tts({
                "tts_engine": preview_eng or saved_audio[0],
                "kokoro_voice": preview_voice or saved_audio[1],
                "tts_pitch": preview_pitch if preview_pitch is not None else saved_audio[2],
                "speech_speed": preview_speed if preview_speed is not None else saved_audio[3],
            })
        ev = None
        try:
            if text:
                ev = emit_ai_speech(
                    state,
                    text,
                    source=source,
                    emotion=emotion,
                    speak=True,
                    client_id=client_id,
                )
        finally:
            if saved_audio and getattr(state, "audio", None):
                def _restore_audio(snap=saved_audio, delay=0.25):
                    if delay > 0:
                        time.sleep(delay)
                    state.audio.configure_tts({
                        "tts_engine": snap[0],
                        "kokoro_voice": snap[1],
                        "tts_pitch": snap[2],
                        "speech_speed": snap[3],
                    })
                if getattr(state.audio, "synthesis_queue", None) is None:
                    _restore_audio(saved_audio, 0.0)
                else:
                    threading.Thread(target=_restore_audio, args=(saved_audio, 0.25), daemon=True).start()
        send_json(
            handler,
            {
                "status": "ok",
                "spoken": ev["speech"] if ev else text,
                "emotion": ev["emotion"] if ev else emotion,
                "goemotion": ev.get("goemotion") if ev else None,
                "emote_clip": ev.get("emote_clip") if ev else None,
            },
        )
        return True

    if path == "/api/ai/interrupt":
        req_data = read_json_body(handler)
        reason = str(req_data.get("reason", "UI_TAP")).strip() or "UI_TAP"
        if hasattr(state, "interrupt_ai_turn"):
            res = state.interrupt_ai_turn(reason=reason)
        else:
            seq = state.audio.stop_speaking() if hasattr(state.audio, "stop_speaking") else 0
            res = {"status": "ok", "interrupt_seq": seq, "reason": reason}
        send_json(handler, res)
        return True

    if path == "/api/ai/chat":
        req_data = read_json_body(handler)
        user_msg = req_data.get("message", "").strip()
        if not user_msg:
            handler.send_response(400)
            handler.end_headers()
            return True

        # Cancel any prior in-flight reply before starting the new turn
        if hasattr(state, "interrupt_ai_turn"):
            state.interrupt_ai_turn(reason="NEW_CHAT_TURN")

        cancel_ev = threading.Event()
        stream_id = f"str_{int(time.time() * 1000)}"
        with state.lock:
            state._active_chat_cancel = cancel_ev
            state._active_stream_id = stream_id
            frame_dict = frame_to_dict(state.latest_frame)

        try:
            from ai.emote_choreographer import analyze_reply_choreography
        except ImportError:
            from backend.ai.emote_choreographer import analyze_reply_choreography
        persona = state.llm.get_active_persona() if hasattr(state.llm, "get_active_persona") else None

        clauses_spoken = []
        chunk_idx = 0
        first_clause_seen = threading.Event()

        def _emit_latency_filler() -> None:
            if cancel_ev.is_set() or first_clause_seen.is_set():
                return
            if not getattr(state.llm, "settings", {}).get("thinking_fillers_enabled", True):
                return
            if state.copilot.voice_mode == "MUTED":
                return
            fillers = (persona or {}).get("thinking_fillers") or []
            if not fillers:
                return
            import random
            addr = state.llm.get_driver_address() if hasattr(state.llm, "get_driver_address") else "Dad"
            cue = random.choice(fillers).replace("{driver_address}", addr)
            if cue and hasattr(state.audio, "speak"):
                state.audio.speak(cue, priority=1)

        filler_timer = threading.Timer(0.95, _emit_latency_filler)
        filler_timer.daemon = True
        filler_timer.start()

        def _handle_clause(clause_text: str) -> None:
            nonlocal chunk_idx
            if cancel_ev.is_set():
                return
            first_clause_seen.set()
            filler_timer.cancel()
            clause_choreo = analyze_reply_choreography(clause_text, persona_data=persona, telemetry=frame_dict)
            clean_chunk = clause_choreo["speech"]
            if not clean_chunk:
                return
            clauses_spoken.append(clean_chunk)
            with state.lock:
                state.latest_ai_stream = {
                    "id": int(time.time() * 1000) + chunk_idx,
                    "stream_id": stream_id,
                    "chunk_index": chunk_idx,
                    "chunk": clean_chunk,
                    "full_so_far": " ".join(clauses_spoken),
                    "persona": (persona or {}).get("display_short_name") or (persona or {}).get("name", "Companion"),
                    "emotion": clause_choreo["hud_emotion"],
                    "goemotion": clause_choreo["goemotion"],
                    "facial_preset": clause_choreo["facial_preset"],
                    "emote_clip": clause_choreo["emote_clip"],
                    "beats": clause_choreo["beats"],
                    "done": False,
                }
            chunk_idx += 1
            if state.copilot.voice_mode != "MUTED":
                state.audio.speak(clean_chunk)

        try:
            res = state.llm.chat_with_action(user_msg, live_telemetry=frame_dict, on_clause=_handle_clause, cancel_event=cancel_ev)
        except TypeError:
            res = state.llm.chat_with_action(user_msg, live_telemetry=frame_dict, on_clause=_handle_clause)
        finally:
            first_clause_seen.set()
            filler_timer.cancel()

        if cancel_ev.is_set():
            send_json(handler, {"status": "interrupted", "stream_id": stream_id, "user_message": user_msg, "reply": " ".join(clauses_spoken)})
            return True

        if res.get("action"):
            with state.lock:
                state.latest_ui_action = res["action"]
        raw_reply = res.get("reply", "")
        choreo = analyze_reply_choreography(raw_reply, persona_data=persona, telemetry=frame_dict)
        emotion = choreo["hud_emotion"]
        clean_reply = choreo["speech"]
        if getattr(state, "drive_buffer", None):
            state.drive_buffer.record_dialogue(user_msg, clean_reply or raw_reply)
        if not clauses_spoken and clean_reply and state.copilot.voice_mode != "MUTED":
            state.audio.speak(clean_reply)
        with state.lock:
            state.latest_ai_stream = {
                "id": int(time.time() * 1000) + chunk_idx + 1,
                "stream_id": stream_id,
                "chunk_index": chunk_idx,
                "full_so_far": clean_reply,
                "persona": (persona or {}).get("display_short_name") or (persona or {}).get("name", "Companion"),
                "emotion": emotion,
                "goemotion": choreo["goemotion"],
                "facial_preset": choreo["facial_preset"],
                "emote_clip": choreo["emote_clip"],
                "beats": choreo["beats"],
                "meta": res.get("meta") or {},
                "done": True,
            }
            if state._active_stream_id == stream_id:
                state._active_chat_cancel = None
                state._active_stream_id = None

        send_json(
            handler,
            {
                "status": "ok",
                "stream_id": stream_id,
                "user_message": user_msg,
                "reply": clean_reply,
                "emotion": emotion,
                "goemotion": choreo["goemotion"],
                "facial_preset": choreo["facial_preset"],
                "emote_clip": choreo["emote_clip"],
                "beats": choreo["beats"],
                "action": res.get("action"),
                "meta": res.get("meta") or {},
                "persona": res.get("persona", state.llm.settings.get("personality") or (state.llm.get_default_persona_id() if hasattr(state.llm, "get_default_persona_id") else "COMPANION")),
            },
        )
        return True

    if path == "/api/ai/wake_test":
        state.listen_once_requested = True
        state.is_mic_listening = True
        p_id = state.llm.settings.get("personality") or (state.llm.get_default_persona_id() if hasattr(state.llm, "get_default_persona_id") else "COMPANION")
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
