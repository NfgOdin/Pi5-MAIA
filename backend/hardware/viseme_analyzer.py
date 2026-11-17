"""Real-Time Audio RMS Envelope & Vowel Viseme Extractor for VRM Lip-Sync.

Extracts compact 25 Hz amplitude envelopes and aligned 5-vowel viseme codes
('0'=closed, 'a'=aa, 'i'=ih, 'u'=ou, 'e'=ee, 'o'=oh) directly from rendered
TTS WAV bytes + spoken text using Python stdlib only.
"""

import io
import math
import re
import struct
import wave
from typing import Any, Dict, List


_VOWEL_TOKEN_RE = re.compile(
    r"(oo|ou|ow|ee|ea|ai|ay|ie|oa|oi|m|b|p|[aeiouy])",
    re.IGNORECASE,
)


def text_to_viseme_stream(spoken_text: str) -> List[str]:
    """Convert English text orthography into a compact sequence of VRM viseme codes."""
    text = str(spoken_text or "").lower()
    seq: List[str] = []
    for word in re.findall(r"[a-z']+", text):
        tokens = _VOWEL_TOKEN_RE.findall(word)
        if not tokens:
            seq.append("a")
            continue
        for tok in tokens:
            if tok in ("m", "b", "p"):
                # Brief bilabial mouth closure before vowel release
                if not seq or seq[-1] != "0":
                    seq.append("0")
            elif tok in ("oo", "ou", "u"):
                seq.append("u")
            elif tok in ("oa", "ow", "o"):
                seq.append("o")
            elif tok in ("ee", "ea", "e"):
                seq.append("e")
            elif tok in ("ai", "ay", "ie", "i", "y"):
                seq.append("i")
            else:
                seq.append("a")
    return seq or ["a"]


def extract_wav_viseme_timeline(
    wav_bytes: bytes,
    spoken_text: str = "",
    fps: int = 25,
) -> Dict[str, Any]:
    """Extract a synchronized 25 Hz amplitude + viseme timeline from WAV PCM bytes.

    Returns:
        {
            "fps": 25,
            "duration_ms": int,
            "amps": [0..15],        # normalized acoustic loudness per frame
            "visemes": "0aaiiuo...",# single-char code per frame
        }
    """
    fps = max(10, min(50, int(fps or 25)))
    raw_amps: List[float] = []
    duration_ms = 0

    if wav_bytes and wav_bytes[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                n_channels = max(1, wf.getnchannels())
                sampwidth = wf.getsampwidth()
                framerate = max(8000, wf.getframerate())
                n_frames = wf.getnframes()
                duration_ms = int((n_frames / framerate) * 1000)
                pcm_bytes = wf.readframes(n_frames)

            step_samples = max(1, int(framerate / fps))
            total_frames_pcm = len(pcm_bytes) // max(1, sampwidth * n_channels)

            if sampwidth == 2 and total_frames_pcm > 0:
                samples = struct.unpack(f"<{total_frames_pcm * n_channels}h", pcm_bytes[: total_frames_pcm * sampwidth * n_channels])
                for start in range(0, len(samples), step_samples * n_channels):
                    chunk = samples[start : start + step_samples * n_channels : n_channels]
                    if not chunk:
                        continue
                    rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) / 32768.0
                    raw_amps.append(rms)
            elif sampwidth == 1 and total_frames_pcm > 0:
                for start in range(0, total_frames_pcm, step_samples):
                    end = min(total_frames_pcm, start + step_samples)
                    sq = 0.0
                    cnt = 0
                    for idx in range(start, end):
                        v = (pcm_bytes[idx * n_channels] - 128) / 128.0
                        sq += v * v
                        cnt += 1
                    raw_amps.append(math.sqrt(sq / max(1, cnt)))
        except Exception:
            raw_amps = []

    if not raw_amps:
        # Clean synthetic cadence fallback (non-WAV MP3 edge case or unit test)
        phonemes = text_to_viseme_stream(spoken_text)
        est_ms = max(1200, int((len(spoken_text or "") / 10.5) * 1000))
        frame_count = max(1, int((est_ms / 1000.0) * fps))
        vis_chars: List[str] = []
        amps_q: List[int] = []
        for fi in range(frame_count):
            pct = fi / max(1, frame_count - 1)
            pi = min(len(phonemes) - 1, int(pct * len(phonemes)))
            code = phonemes[pi]
            vis_chars.append(code)
            amps_q.append(0 if code == "0" else 9)
        return {
            "fps": fps,
            "duration_ms": est_ms,
            "amps": amps_q,
            "visemes": "".join(vis_chars),
        }

    # Normalize amplitude dynamically by 95th percentile so soft & loud TTS voices animate cleanly
    sorted_vals = sorted(raw_amps)
    peak_ref = max(0.025, sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * 0.95))])
    amps_q = [min(15, max(0, int(round(min(1.0, (a / peak_ref) ** 0.72) * 15)))) for a in raw_amps]

    # Map text phonemes cleanly across voiced frames only (pauses stay '0')
    phonemes = text_to_viseme_stream(spoken_text)
    voiced_indices = [i for i, q in enumerate(amps_q) if q >= 2]
    vis_chars = ["0"] * len(amps_q)
    if voiced_indices:
        n_v = len(voiced_indices)
        n_p = len(phonemes)
        for vi, frame_idx in enumerate(voiced_indices):
            p_idx = min(n_p - 1, int((vi / max(1, n_v)) * n_p))
            vis_chars[frame_idx] = phonemes[p_idx]

    return {
        "fps": fps,
        "duration_ms": duration_ms or int((len(amps_q) / fps) * 1000),
        "amps": amps_q,
        "visemes": "".join(vis_chars),
    }
