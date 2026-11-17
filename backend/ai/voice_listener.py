"""Continuous PipeWire USB microphone wake-word and live conversation listener."""

from collections import deque
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
from typing import Any


PHONETIC_RUM_PREFIXES = (
    "hey rum", "hi rum", "hello rum", "okay rum", "ok rum", "yo rum",
    "hey ram", "hi ram", "hello ram", "okay ram", "ok ram",
    "hey rem", "hi rem", "hello rem", "okay rem", "ok rem",
    "hey ron", "hi ron", "hello ron", "okay ron", "ok ron",
    "hey run", "hi run", "hello run", "okay run", "ok run",
    "hey rob", "hi rob", "hello rob", "okay rob", "ok rob",
    "hey rome", "hi rome", "hello rome", "okay rome",
    "hey room", "hi room", "hello room", "okay room",
    "hey drum", "hi drum", "hello drum",
    "hey rung", "r.u.m.", "r.u.m",
)

STANDALONE_RUM_WORDS = {
    "rum", "r.u.m.", "r.u.m", "rem", "ram", "ron", "run", "rob", "rome", "room", "drum",
}

VOSK_WAKE_GRAMMAR = json.dumps([
    "hey rum", "hi rum", "hello rum", "okay rum", "ok rum", "yo rum",
    "hey ram", "hi ram", "hello ram", "okay ram", "ok ram",
    "hey rem", "hi rem", "hello rem", "okay rem", "ok rem",
    "hey ron", "hi ron", "hello ron", "okay ron", "ok ron",
    "hey run", "hi run", "hello run", "okay run", "ok run",
    "hey rob", "hi rob", "hello rob", "okay rob", "ok rob",
    "hey rome", "hi rome", "hello rome", "okay rome",
    "hey room", "hi room", "hello room", "okay room",
    "hey drum", "hi drum", "hello drum",
    "rum", "rem", "ram", "ron", "run", "rob", "rome", "room", "drum",
    "speed", "boost", "temperature", "coolant", "map", "maps", "navigation", "nav",
    "where", "location", "drag", "launch", "home", "gauges",
    "hey", "hi", "hello",
    "[unk]",
])


def _ensure_vosk_model(state: Any, base_dir: Path) -> Any:
    """Lazy-load and cache the local small Vosk acoustic model on server state."""
    if getattr(state, "_vosk_model", None) is not None:
        return state._vosk_model
    model_path = str(base_dir / "models" / "vosk-model-small-en-us-0.15")
    if os.path.exists(model_path):
        import vosk

        state._vosk_model = vosk.Model(model_path)
    return getattr(state, "_vosk_model", None)


def normalize_wake_transcript(heard: str) -> tuple[str, bool]:
    """Normalize phonetic wake variants to 'Hey Rum...' and return (text, is_wake_match)."""
    h_low = heard.lower().strip(" .,!?")
    for pref in PHONETIC_RUM_PREFIXES:
        if h_low == pref:
            return "Hey Rum", True
        if h_low.startswith(pref + " ") or h_low.startswith(pref + ","):
            rest = heard[len(pref):].lstrip(" ,.!?")
            return (f"Hey Rum, {rest}" if rest else "Hey Rum"), True

    if h_low in STANDALONE_RUM_WORDS:
        return "Hey Rum", True
    return heard, False


def usb_mic_listener_loop(state: Any, base_dir: Path) -> None:
    """Run continuous zero-gap hardware USB microphone capture for 'Hey Rum' and live conversation."""
    if not sys.platform.startswith("linux"):
        return

    print("[VOICE MIC] Starting Continuous Hardware USB Microphone Listener (DGM20 / PipeWire --raw)...", flush=True)
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else "/run/user/1000"

    try:
        subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "0"], env=env, timeout=2)
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SOURCE@", "1.4"], env=env, timeout=2)
    except Exception:
        pass

    def normalize_and_recognize(raw_pcm: bytes, is_convo: bool, current_noise_rms: float) -> None:
        try:
            ns = len(raw_pcm) // 2
            if ns < 1600:
                return
            samples = struct.unpack(f"<{ns}h", raw_pcm[:ns * 2])
            mean_val = int(sum(samples) / ns)
            centered = [s - mean_val for s in samples]
            peak = max(abs(s) for s in centered) if centered else 1
            rms = math.sqrt(sum(s * s for s in centered) / ns) if centered else 0.0

            if rms < max(180.0, current_noise_rms * 1.5):
                return
            gain = min(6.0, 24500.0 / max(3500, peak))
            norm_samples = [max(-32767, min(32767, int(s * gain))) for s in centered]
            norm_bytes = struct.pack(f"<{ns}h", *norm_samples)

            import speech_recognition as sr

            recognizer = sr.Recognizer()
            audio_data = sr.AudioData(norm_bytes, 16000, 2)
            heard = ""
            if not is_convo:
                try:
                    import vosk

                    model = _ensure_vosk_model(state, base_dir)
                    if model is not None:
                        if getattr(state, "_vosk_wake_rec", None) is None:
                            state._vosk_wake_rec = vosk.KaldiRecognizer(model, 16000, VOSK_WAKE_GRAMMAR)
                        rec = state._vosk_wake_rec
                        rec.AcceptWaveform(norm_bytes)
                        heard = json.loads(rec.FinalResult()).get("text", "").strip()
                except Exception as ex:
                    print(f"[VOICE MIC WAKE] Local spotter note: {ex}", flush=True)
            else:
                try:
                    heard = recognizer.recognize_google(audio_data).strip()
                except Exception:
                    pass
                if not heard:
                    try:
                        import vosk

                        model = _ensure_vosk_model(state, base_dir)
                        if model is not None:
                            rec = vosk.KaldiRecognizer(model, 16000)
                            rec.AcceptWaveform(norm_bytes)
                            heard = json.loads(rec.FinalResult()).get("text", "").strip()
                    except Exception as vosk_err:
                        print(f"[VOICE MIC] Vosk offline STT note: {vosk_err}", flush=True)

            if not heard:
                return

            print(
                f"[VOICE MIC] Heard ({'CONVO' if is_convo else 'WAKE'}): '{heard}' "
                f"(raw RMS={rms:.0f}, Peak={peak}, Gain={gain:.1f}x)",
                flush=True,
            )
            normalized_text, is_wake_match = normalize_wake_transcript(heard)

            if not is_convo and not is_wake_match:
                print(f"[VOICE MIC] Discarded non-wake speech in standby: '{heard}'", flush=True)
                return

            with state.lock:
                state.pending_voice_transcripts.append({
                    "text": normalized_text,
                    "mode": "convo" if is_convo else "wake",
                    "timestamp": time.time(),
                })
            if not is_convo and normalized_text.lower().strip(" !?.") == "hey rum":
                state.listen_once_requested = True
                try:
                    state.audio.play_acknowledgment(state.llm.settings.get("personality", "RUM"))
                except Exception as ack_err:
                    print(f"[VOICE MIC] Ack play note: {ack_err}", flush=True)
            elif state.listen_once_requested and not state.live_convo_mode:
                state.listen_once_requested = False
        except Exception as stt_err:
            if type(stt_err).__name__ != "UnknownValueError":
                print(f"[VOICE MIC] STT note: {type(stt_err).__name__}: {stt_err}", flush=True)

    last_spoke_end = 0.0
    while state.running:
        proc = None
        try:
            proc = subprocess.Popen(
                ["pw-record", "--raw", "--rate", "16000", "--channels", "1", "--format", "s16", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            state._active_rec_proc = proc

            pre_roll: deque = deque(maxlen=6)
            speech_chunks = []
            in_speech = False
            silence_frames = 0
            noise_rms = 95.0

            while state.running and proc.poll() is None:
                chunk = proc.stdout.read(3200)
                if not chunk or len(chunk) < 3200:
                    break

                if getattr(state.audio, "is_speaking", False):
                    last_spoke_end = time.time()
                    in_speech = False
                    speech_chunks.clear()
                    pre_roll.clear()
                    state.is_mic_listening = False
                    continue

                if (time.time() - last_spoke_end) < 0.40:
                    in_speech = False
                    speech_chunks.clear()
                    pre_roll.clear()
                    continue

                is_convo = state.live_convo_mode or state.listen_once_requested
                if not is_convo and not state.wake_word_enabled:
                    state.is_mic_listening = False
                    continue

                samples = struct.unpack("<1600h", chunk)
                rms = math.sqrt(sum(s * s for s in samples) / 1600)
                peak = max(abs(s) for s in samples)

                if not in_speech:
                    if rms < 900.0:
                        noise_rms = (noise_rms * 0.94) + (rms * 0.06)
                    noise_rms = max(45.0, min(750.0, noise_rms))
                trig_rms = max(75.0, noise_rms * (1.30 if is_convo else 1.40))
                trig_peak = max(340, int(noise_rms * 3.0))

                if not in_speech:
                    pre_roll.append(chunk)
                    if rms >= trig_rms or peak >= trig_peak:
                        in_speech = True
                        silence_frames = 0
                        speech_chunks = list(pre_roll)
                        state.is_mic_listening = True
                    else:
                        state.is_mic_listening = is_convo
                else:
                    speech_chunks.append(chunk)
                    if rms < max(65.0, noise_rms * 1.25) and peak < trig_peak:
                        silence_frames += 1
                    else:
                        silence_frames = 0

                    max_silence = 9 if is_convo else 7
                    if silence_frames >= max_silence or len(speech_chunks) >= 52:
                        full_pcm = b"".join(speech_chunks)
                        in_speech = False
                        speech_chunks = []
                        pre_roll.clear()
                        state.is_mic_listening = is_convo
                        if len(full_pcm) >= 9600:
                            threading.Thread(
                                target=normalize_and_recognize,
                                args=(full_pcm, is_convo, noise_rms),
                                daemon=True,
                            ).start()
        except Exception as loop_err:
            print(f"[VOICE MIC] Stream restart note: {loop_err}", flush=True)
            time.sleep(0.5)
        finally:
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass


def start_voice_listener(state: Any, base_dir: Path) -> threading.Thread:
    """Spawn the background USB microphone listener thread."""
    t_mic = threading.Thread(
        target=usb_mic_listener_loop,
        args=(state, base_dir),
        daemon=True,
        name="UsbMicListener",
    )
    t_mic.start()
    return t_mic
