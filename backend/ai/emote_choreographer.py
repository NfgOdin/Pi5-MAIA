"""Autonomous 27-GoEmotions Emote Choreographer & Multi-Beat Speech Analyzer.

Maps LLM inline tags ([EMOTE:...] / [beat:...]), semantic cues, telemetry, and
active persona profiles onto verified BVH/VRMA motion clips and facial presets
without duplicating emotion logic across routes or frontend code.
"""

from collections import deque
import random
import re
import threading
from typing import Any, Dict, List, Optional, Tuple


# Canonical 27 GoEmotions categories mapped to HUD emotion, facial blend weights,
# and verified clip keys in models/bvh/emotions/*.bvh & VRMA_MOTION_FILES.
GOEMOTION_CATALOG: Dict[str, Dict[str, Any]] = {
    "admiration": {
        "hud_emotion": "DEVOTED",
        "facial": {"happy": 0.65, "relaxed": 0.35, "blush": 0.25, "smirk": 0.15},
        "clips": ["admiration", "admiration2", "admiration3", "pose_lean_in"],
        "keywords": ["amazing", "awesome", "incredible", "impressive", "best", "masterpiece", "genius", "wow"],
    },
    "amusement": {
        "hud_emotion": "HAPPY",
        "facial": {"happy": 0.85, "relaxed": 0.20, "blush": 0.15, "smirk": 0.35},
        "clips": ["amusement", "amusement2", "amusement3", "joy2"],
        "keywords": ["haha", "hehe", "funny", "hilarious", "joke", "giggle", "laugh", "silly", "lol"],
    },
    "anger": {
        "hud_emotion": "CONCERNED",
        "facial": {"angry": 0.85, "brow_tilt": -0.45, "smirk": 0.0},
        "clips": ["anger", "anger2", "anger3", "annoyance"],
        "keywords": ["furious", "mad", "angry", "outraged", "unacceptable", "destroy"],
    },
    "annoyance": {
        "hud_emotion": "CONCERNED",
        "facial": {"angry": 0.45, "brow_tilt": -0.30, "smirk": 0.20},
        "clips": ["annoyance", "annoyance1", "disapproval2"],
        "keywords": ["annoying", "hmph", "tch", "ugh", "seriously", "bother", "traffic", "slow"],
    },
    "approval": {
        "hud_emotion": "HAPPY_PROUD",
        "facial": {"happy": 0.55, "relaxed": 0.40, "smirk": 0.15},
        "clips": ["approval", "approval2", "approval3", "peace"],
        "keywords": ["nice", "clean", "approved", "solid", "good job", "spot on", "nailed", "rev-match", "perfect"],
    },
    "caring": {
        "hud_emotion": "DEVOTED",
        "facial": {"happy": 0.35, "relaxed": 0.55, "blush": 0.30, "brow_tilt": 0.20},
        "clips": ["caring", "caring1", "admiration2", "pose_lean_in"],
        "keywords": ["care", "warm", "safe", "watch out", "hydrated", "rest", "sweet", "buckle", "gentle"],
    },
    "confusion": {
        "hud_emotion": "THOUGHTFUL",
        "facial": {"surprised": 0.25, "brow_tilt": 0.45},
        "clips": ["confusion", "confusion2", "confusion3", "curiosity2"],
        "keywords": ["confused", "huh", "wait what", "unclear", "weird", "strange", "puzzling"],
    },
    "curiosity": {
        "hud_emotion": "THOUGHTFUL",
        "facial": {"surprised": 0.20, "relaxed": 0.25, "brow_tilt": 0.35},
        "clips": ["curiosity", "curiosity2", "curiosity3", "pose_side_glance"],
        "keywords": ["wonder", "curious", "what if", "why", "think", "shower thought", "hmm", "explore", "notice"],
    },
    "desire": {
        "hud_emotion": "FLIRTY",
        "facial": {"happy": 0.45, "relaxed": 0.35, "blush": 0.55, "smirk": 0.40},
        "clips": ["desire", "desire1", "desire2", "pose_lean_in"],
        "keywords": ["crave", "tease", "wink", "flirt", "tempt", "gorgeous", "handsome", "irresistible"],
    },
    "disappointment": {
        "hud_emotion": "CONCERNED",
        "facial": {"sad": 0.55, "relaxed": 0.15, "brow_tilt": 0.30},
        "clips": ["disappointment", "disappointment2", "sadness2"],
        "keywords": ["bummer", "pity", "unfortunately", "missed", "failed", "shame", "oh man"],
    },
    "disapproval": {
        "hud_emotion": "CONCERNED",
        "facial": {"angry": 0.35, "brow_tilt": -0.25},
        "clips": ["disapproval", "disapproval2", "annoyance1"],
        "keywords": ["nope", "bad idea", "don't do", "terrible", "wrong", "never"],
    },
    "disgust": {
        "hud_emotion": "CONCERNED",
        "facial": {"angry": 0.50, "sad": 0.20, "brow_tilt": -0.35},
        "clips": ["disgust", "disgust1", "disgust2"],
        "keywords": ["gross", "yuck", "ew", "nasty", "rust", "sludge"],
    },
    "embarrassment": {
        "hud_emotion": "FLIRTY",
        "facial": {"happy": 0.30, "blush": 0.85, "brow_tilt": 0.35},
        "clips": ["embarrassment", "pose_shy_wave", "nervousness2"],
        "keywords": ["blush", "embarrassed", "shy", "kyaa", "wah", "don't stare", "stammer", "b-baka"],
    },
    "excitement": {
        "hud_emotion": "EXCITED",
        "facial": {"happy": 0.75, "surprised": 0.45, "blush": 0.20},
        "clips": ["excitement", "excitement2", "excitement3", "joy"],
        "keywords": ["boost", "turbo", "spool", "launch", "pull", "fast", "zoom", "lets go", "let's go", "woohoo", "psi"],
    },
    "fear": {
        "hud_emotion": "CONCERNED",
        "facial": {"surprised": 0.70, "sad": 0.35, "brow_tilt": 0.55},
        "clips": ["fear", "fear2", "fear3", "nervousness"],
        "keywords": ["danger", "overheat", "critical", "warning", "hazard", "scary", "brake", "redline"],
    },
    "gratitude": {
        "hud_emotion": "DEVOTED",
        "facial": {"happy": 0.70, "relaxed": 0.40, "blush": 0.35},
        "clips": ["gratitude", "pose_lady_bow", "admiration3", "greeting"],
        "keywords": ["thank", "thanks", "grateful", "appreciate", "sugar", "fed", "treat", "kind"],
    },
    "grief": {
        "hud_emotion": "CONCERNED",
        "facial": {"sad": 0.90, "brow_tilt": 0.50},
        "clips": ["grief", "sadness", "sadness2"],
        "keywords": ["heartbroken", "grief", "devastated", "mourn"],
    },
    "joy": {
        "hud_emotion": "HAPPY",
        "facial": {"happy": 0.90, "relaxed": 0.30, "blush": 0.25},
        "clips": ["joy", "joy2", "joy3", "optimism", "greeting_wave_right"],
        "keywords": ["happy", "yay", "sparkling", "smile", "sunshine", "morning", "delighted", "cheerful", "fun"],
    },
    "love": {
        "hud_emotion": "DEVOTED",
        "facial": {"happy": 0.60, "relaxed": 0.50, "blush": 0.65},
        "clips": ["love", "love2", "love3", "caring", "admiration"],
        "keywords": ["love", "adore", "daddy", "dad", "master", "sweetheart", "forever", "devoted", "favorite", "heart"],
    },
    "nervousness": {
        "hud_emotion": "CONCERNED",
        "facial": {"surprised": 0.25, "sad": 0.25, "blush": 0.40, "brow_tilt": 0.40},
        "clips": ["nervousness", "nervousness2", "nervousness3", "embarrassment"],
        "keywords": ["nervous", "uh oh", "careful", "tense", "jittery", "yikes", "caution"],
    },
    "optimism": {
        "hud_emotion": "HAPPY",
        "facial": {"happy": 0.65, "relaxed": 0.45, "blush": 0.15},
        "clips": ["optimism", "approval2", "pose_hand_raised_high"],
        "keywords": ["ready", "bright", "smooth", "ahead", "cruise", "clear skies", "hopeful", "today"],
    },
    "pride": {
        "hud_emotion": "HAPPY_PROUD",
        "facial": {"happy": 0.70, "relaxed": 0.35, "smirk": 0.35},
        "clips": ["pride", "pride2", "idol_pose_showcase", "approval"],
        "keywords": ["proud", "victory", "record", "champ", "multi-air", "multiair", "dart", "flex"],
    },
    "realization": {
        "hud_emotion": "THOUGHTFUL",
        "facial": {"surprised": 0.55, "happy": 0.20, "brow_tilt": 0.30},
        "clips": ["realization", "curiosity3", "pose_hand_raised_high"],
        "keywords": ["aha", "wait", "realized", "just noticed", "discovered", "oh!", "bingo", "eureka"],
    },
    "relief": {
        "hud_emotion": "COZY",
        "facial": {"relaxed": 0.80, "happy": 0.40, "blush": 0.15},
        "clips": ["relief", "relief1", "caring1", "pose_angled_wave"],
        "keywords": ["phew", "cozy", "calm", "settled", "relaxed", "peaceful", "cool down", "easy", "night"],
    },
    "remorse": {
        "hud_emotion": "CONCERNED",
        "facial": {"sad": 0.65, "blush": 0.20, "brow_tilt": 0.40},
        "clips": ["remorse", "remorse2", "remorse3", "pose_shy_wave"],
        "keywords": ["sorry", "apologize", "my bad", "forgive", "oops", "fault"],
    },
    "sadness": {
        "hud_emotion": "CONCERNED",
        "facial": {"sad": 0.75, "brow_tilt": 0.35},
        "clips": ["sadness", "sadness2", "disappointment2"],
        "keywords": ["sad", "lonely", "miss you", "gloomy", "down", "hurt", "cold"],
    },
    "surprise": {
        "hud_emotion": "EXCITED",
        "facial": {"surprised": 0.90, "happy": 0.25, "blush": 0.20},
        "clips": ["surprise", "surprise2", "realization", "turn_and_wave_hello"],
        "keywords": ["whoa", "what?!", "surprise", "unexpected", "sudden", "shocked", "oh my"],
    },
}

# Coarse HUD / persona tags -> GoEmotion resolution
COARSE_TO_GOEMOTION: Dict[str, str] = {
    "DEVOTED": "love",
    "FLIRTY": "desire",
    "EXCITED": "excitement",
    "CONCERNED": "caring",
    "HAPPY": "joy",
    "COZY": "relief",
    "HAPPY_PROUD": "pride",
    "THOUGHTFUL": "curiosity",
    "SURPRISED": "surprise",
    "ANGRY": "anger",
    "SAD": "sadness",
    "PROUD": "pride",
    "SHY": "embarrassment",
    "PLAYFUL": "amusement",
    "TEASING": "amusement",
    "CALM": "relief",
    "NEUTRAL": "optimism",
}

_TAG_RE = re.compile(
    r"\[(?:EMOTE|EMOTION|BEAT)\s*:\s*([A-Za-z0-9_,\-\s]+)\]|<emotion>\s*([A-Za-z0-9_,\-\s]+)\s*</emotion>",
    re.IGNORECASE,
)

_HISTORY_LOCK = threading.Lock()
_RECENT_CLIPS: Dict[str, deque] = {}


def normalize_goemotion(label: Optional[str]) -> str:
    """Resolve any GoEmotion name, coarse emotion pill, or alias to one of the 27 GoEmotions."""
    if not label:
        return "love"
    token = str(label).strip().lower().replace("-", "_").split(",")[0].strip()
    if token in GOEMOTION_CATALOG:
        return token
    upper = token.upper()
    if upper in COARSE_TO_GOEMOTION:
        return COARSE_TO_GOEMOTION[upper]
    # Fuzzy prefix match (e.g. "excited" -> "excitement", "loving" -> "love")
    for k in GOEMOTION_CATALOG:
        if token.startswith(k[:4]) or k.startswith(token):
            return k
    return "joy"


def _infer_goemotion_from_text(text: str, fallback: str = "joy", persona_data: Optional[Dict[str, Any]] = None) -> str:
    lower = (text or "").lower()
    best_cat = fallback
    best_score = 0

    for cat, meta in GOEMOTION_CATALOG.items():
        score = 0
        for kw in meta.get("keywords", []):
            if kw in lower:
                score += 2 if " " in kw else 1
        if score > best_score:
            best_score = score
            best_cat = cat

    if best_score == 0:
        if "!" in text:
            best_cat = "excitement" if text.count("!") >= 2 else "joy"
        elif "?" in text:
            best_cat = "curiosity"
        elif persona_data and persona_data.get("emote_profile", {}).get("default_goemotion"):
            cand = str(persona_data["emote_profile"]["default_goemotion"]).lower()
            if cand in GOEMOTION_CATALOG:
                best_cat = cand

    # Respect child/wholesome personas or explicit clip exclusions
    p_profile = (persona_data or {}).get("emote_profile", {})
    remap = p_profile.get("remap", {})
    if best_cat in remap and remap[best_cat] in GOEMOTION_CATALOG:
        best_cat = remap[best_cat]
    return best_cat


def _pick_clip_for_goemotion(
    goemotion: str,
    persona_data: Optional[Dict[str, Any]] = None,
    explicit_action: Optional[str] = None,
) -> str:
    if explicit_action:
        cleaned = str(explicit_action).strip()
        if cleaned:
            return cleaned

    meta = GOEMOTION_CATALOG.get(goemotion, GOEMOTION_CATALOG["joy"])
    pool = list(meta.get("clips", ["joy"]))

    p_profile = (persona_data or {}).get("emote_profile", {})
    overrides = p_profile.get("clip_overrides", {})
    if goemotion in overrides and isinstance(overrides[goemotion], list) and overrides[goemotion]:
        pool = list(overrides[goemotion])
    else:
        banned = set(p_profile.get("excluded_clips", []))
        gender = str((persona_data or {}).get("gender", "")).lower()
        if gender == "male":
            banned.update({"pose_lady_bow", "pose_polish_nails", "pose_shy_wave"})
        else:
            banned.add("pose_gentlemen_bow")
        filtered = [c for c in pool if c not in banned]
        if filtered:
            pool = filtered

    with _HISTORY_LOCK:
        hist = _RECENT_CLIPS.setdefault(goemotion, deque(maxlen=max(1, len(pool) - 1)))
        fresh = [c for c in pool if c not in hist]
        chosen = random.choice(fresh or pool)
        hist.append(chosen)
    return chosen


def _strip_tags_and_collect_beats(raw_text: str) -> Tuple[str, List[Tuple[float, str]]]:
    """Strip inline [EMOTE]/[EMOTION]/[beat] tags and return (clean_text, [(char_pos_pct, tag)])."""
    raw = str(raw_text or "").strip()
    if not raw:
        return "", []

    segments: List[str] = []
    markers: List[Tuple[int, str]] = []
    clean_len = 0
    last_idx = 0

    for m in _TAG_RE.finditer(raw):
        chunk = raw[last_idx:m.start()]
        if chunk:
            segments.append(chunk)
            clean_len += len(chunk)
        tag_val = (m.group(1) or m.group(2) or "").strip()
        if tag_val:
            markers.append((clean_len, tag_val))
        last_idx = m.end()

    tail = raw[last_idx:]
    if tail:
        segments.append(tail)
        clean_len += len(tail)

    clean_text = re.sub(r"\s{2,}", " ", "".join(segments)).strip()
    total = max(1, len(clean_text))
    normalized_markers = [(round(min(0.95, pos / total), 3), tag) for pos, tag in markers]
    return clean_text, normalized_markers


def analyze_reply_choreography(
    raw_text: str,
    explicit_emotion: Optional[str] = None,
    explicit_action: Optional[str] = None,
    persona_data: Optional[Dict[str, Any]] = None,
    telemetry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Parse or infer primary emotion, facial preset, primary clip, and multi-beat emote sequence.

    Always strips prompt/emotion tags safely so spoken text enters chat & TTS cleanly.
    """
    clean_text, raw_markers = _strip_tags_and_collect_beats(raw_text)
    if not clean_text:
        return {
            "speech": "",
            "hud_emotion": explicit_emotion or "DEVOTED",
            "goemotion": normalize_goemotion(explicit_emotion),
            "facial_preset": GOEMOTION_CATALOG[normalize_goemotion(explicit_emotion)]["facial"],
            "emote_clip": explicit_action or "neutral_idle",
            "beats": [],
        }

    p_profile = (persona_data or {}).get("emote_profile", {})
    remap = p_profile.get("remap", {})

    # 1. Determine primary GoEmotion
    primary_go = None
    if raw_markers:
        primary_go = normalize_goemotion(raw_markers[0][1])
    elif explicit_emotion:
        # Honor explicit non-default emotions; otherwise let text refine DEVOTED/HAPPY into richer GoEmotions
        upper_exp = str(explicit_emotion).upper().strip()
        if upper_exp not in ("DEVOTED", "HAPPY", "NEUTRAL", ""):
            primary_go = normalize_goemotion(upper_exp)
        else:
            fallback = normalize_goemotion(upper_exp)
            primary_go = _infer_goemotion_from_text(clean_text, fallback=fallback, persona_data=persona_data)
    else:
        primary_go = _infer_goemotion_from_text(clean_text, fallback="joy", persona_data=persona_data)

    # Telemetry boost/thermal accent override when relevant
    if telemetry:
        coolant = telemetry.get("coolant_temp_f") or 0
        boost = telemetry.get("boost_psi") or 0
        if coolant >= 220 and primary_go in ("joy", "love", "optimism"):
            primary_go = "nervousness"
        elif boost >= 14 and primary_go in ("joy", "optimism"):
            primary_go = "excitement"

    if primary_go in remap and remap[primary_go] in GOEMOTION_CATALOG:
        primary_go = remap[primary_go]

    meta = GOEMOTION_CATALOG.get(primary_go, GOEMOTION_CATALOG["joy"])
    hud_emotion = explicit_emotion if (explicit_emotion and str(explicit_emotion).upper() != "DEVOTED") else meta["hud_emotion"]
    primary_clip = _pick_clip_for_goemotion(primary_go, persona_data=persona_data, explicit_action=explicit_action)

    # 2. Build multi-beat timeline for natural mid-speech expression & gesture transitions
    beats: List[Dict[str, Any]] = [
        {
            "offset_pct": 0.0,
            "goemotion": primary_go,
            "hud_emotion": meta["hud_emotion"],
            "facial": dict(meta["facial"]),
            "clip": primary_clip,
            "upper_body": True,
        }
    ]

    if len(raw_markers) > 1:
        for pct, raw_tag in raw_markers[1:4]:
            b_go = normalize_goemotion(raw_tag)
            if b_go in remap and remap[b_go] in GOEMOTION_CATALOG:
                b_go = remap[b_go]
            if b_go != beats[-1]["goemotion"] and pct >= 0.15:
                b_meta = GOEMOTION_CATALOG.get(b_go, meta)
                beats.append({
                    "offset_pct": pct,
                    "goemotion": b_go,
                    "hud_emotion": b_meta["hud_emotion"],
                    "facial": dict(b_meta["facial"]),
                    "clip": _pick_clip_for_goemotion(b_go, persona_data=persona_data),
                    "upper_body": True,
                })
    else:
        # Synthesize a secondary expressive beat for multi-sentence responses so she doesn't freeze in one pose
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_text) if len(s.strip()) > 6]
        if len(sentences) >= 2 and not explicit_action:
            second_go = _infer_goemotion_from_text(sentences[-1], fallback=primary_go, persona_data=persona_data)
            if second_go != primary_go or len(clean_text) >= 65:
                s_meta = GOEMOTION_CATALOG.get(second_go, meta)
                beats.append({
                    "offset_pct": 0.52,
                    "goemotion": second_go,
                    "hud_emotion": s_meta["hud_emotion"],
                    "facial": dict(s_meta["facial"]),
                    "clip": _pick_clip_for_goemotion(second_go, persona_data=persona_data),
                    "upper_body": True,
                })

    return {
        "speech": clean_text,
        "hud_emotion": hud_emotion,
        "goemotion": primary_go,
        "facial_preset": dict(meta["facial"]),
        "emote_clip": primary_clip,
        "beats": beats,
    }
