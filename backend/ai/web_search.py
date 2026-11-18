"""
web_search.py - Zero-Key Live Web Search & Weather/News Grounding Engine for CarPi5

Uses clean public JSON/RSS APIs over whichever uplink Pi 5 has active (Wi-Fi or
Pi 3 Android USB Tether):
- Open-Meteo Geocoding & Forecast JSON (live weather/temperature/forecasts)
- DuckDuckGo Instant Answer JSON (quick facts & definitions)
- Wikipedia Search & Extract JSON API (with progressive keyword relaxation)
- Google News RSS XML (current events / latest news)

Never fabricates search results when offline.
"""

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

_EXPLICIT_WEB_PATTERNS = (
    r"\b(?:look\s+up|search(?:\s+for|\s+the\s+web|\s+online)?|google|find\s+out|check\s+online|web\s+search|search\s+internet)\b",
)

_WEATHER_PATTERNS = (
    r"\b(?:weather|forecast|temperature\s+(?:outside|in)|humidity|uv\s+index|rain(?:ing)?\s+in)\b",
)

_NEWS_PATTERNS = (
    r"\b(?:latest\s+news|news\s+about|headlines|current\s+news|what\s+happened\s+with)\b",
)

_OPEN_FACTUAL_STARTS = (
    "what is ",
    "what's ",
    "who is ",
    "who was ",
    "where is ",
    "when was ",
    "when did ",
    "how many ",
    "how tall ",
    "how much ",
    "how far ",
    "how does ",
    "why does ",
    "why is ",
    "define ",
    "tell me about ",
    "what torque ",
    "what size ",
)

_LOCAL_DOMAIN_BLOCKLIST = (
    "boost", "rpm", "coolant", "obd", "can bus", "telemetry", "how fast", "my speed",
    "gear", "check engine", "dtc", "dashcam", "odometer", "multiair ready", "your name",
    "who are you", "who made you", "who created you", "rem", "ram", "gluttony", "pip",
    "my dad", "my mom", "favorite", "remember", "diary", "bond tier", "play music",
    "volume", "next song", "navigate to", "fan speed", "balcony", "open maps", "open phone",
)

_EPHEMERAL_TOKENS = (
    "weather", "forecast", "rain", "temperature outside", "temperature in",
    "today's", "right now", "latest news", "headlines", "current price",
    "stock price", "score", "traffic", "time is it",
)


def _clean_search_query(raw: str) -> str:
    q = (raw or "").strip()
    q = re.sub(
        r"^(?:hey\s+)?(?:rum|r\.u\.m\.|maia|odin|assistant|please|can you|could you|will you)\s*,?\s*",
        "",
        q,
        flags=re.IGNORECASE,
    )
    q = re.sub(
        r"^(?:look\s+up|search(?:\s+online|\s+the\s+web)?(?:\s+for)?|google|check\s+online(?:\s+for)?|find\s+out(?:\s+about)?)\s+",
        "",
        q,
        flags=re.IGNORECASE,
    )
    return q.strip(" ?!.,\"'")


def is_ephemeral_query(query: str) -> bool:
    ql = (query or "").lower()
    return any(tok in ql for tok in _EPHEMERAL_TOKENS)


def should_search_web(user_message: str, lore_injection: str = "", rag_hits: int = 0) -> Tuple[bool, str]:
    """Decide whether a prompt benefits from a live web lookup and return normalized search terms."""
    msg = (user_message or "").strip()
    if len(msg) < 4:
        return False, ""
    ql = msg.lower()

    for pat in _EXPLICIT_WEB_PATTERNS:
        if re.search(pat, ql):
            cleaned = _clean_search_query(msg)
            return (len(cleaned) >= 2), cleaned

    if any(tok in ql for tok in _LOCAL_DOMAIN_BLOCKLIST):
        return False, ""

    for pat in (*_WEATHER_PATTERNS, *_NEWS_PATTERNS):
        if re.search(pat, ql):
            return True, _clean_search_query(msg)

    if not (lore_injection or "").strip() and rag_hits == 0:
        stripped = _clean_search_query(msg).lower()
        if any(ql.startswith(p) or stripped.startswith(p) for p in _OPEN_FACTUAL_STARTS):
            return True, _clean_search_query(msg)

    return False, ""


def _http_get_text(url: str, timeout: float = 3.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CarPi5-RUM/1.0 (https://github.com/NfgOdin/Pi5-MAIA)",
            "Accept": "application/json,application/xml,text/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _strip_html(raw: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", raw or "")
    txt = html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def _extract_location_for_weather(query: str) -> str:
    m = re.search(r"\b(?:in|for|at)\s+([A-Za-z0-9 ,.-]{2,45})", query, flags=re.IGNORECASE)
    loc = m.group(1) if m else query
    loc = re.sub(r"\b(?:right now|today|tonight|tomorrow|weather|forecast|temperature)\b", "", loc, flags=re.IGNORECASE)
    return re.sub(r"[, ]+$", "", loc).strip() or "Phoenix, AZ"


_US_STATE_NAMES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california",
    "co": "colorado", "ct": "connecticut", "de": "delaware", "fl": "florida", "ga": "georgia",
    "hi": "hawaii", "id": "idaho", "il": "illinois", "in": "indiana", "ia": "iowa",
    "ks": "kansas", "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada", "nh": "new hampshire",
    "nj": "new jersey", "nm": "new mexico", "ny": "new york", "nc": "north carolina",
    "nd": "north dakota", "oh": "ohio", "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania",
    "ri": "rhode island", "sc": "south carolina", "sd": "south dakota", "tn": "tennessee",
    "tx": "texas", "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington",
    "wv": "west virginia", "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
}


def _query_wttr_weather(query: str, timeout: float = 3.0) -> List[Dict[str, str]]:
    """Query wttr.in single-hop JSON endpoint for fast real-time weather without API keys."""
    loc = _extract_location_for_weather(query)
    url = f"https://wttr.in/{urllib.parse.quote(loc)}?format=j1"
    data = json.loads(_http_get_text(url, timeout=timeout))
    cur = (data.get("current_condition") or [{}])[0]
    area = (data.get("nearest_area") or [{}])[0]
    day0 = (data.get("weather") or [{}])[0]
    temp_f = cur.get("temp_F")
    if temp_f is None:
        return []
    feels_f = cur.get("FeelsLikeF")
    desc = ((cur.get("weatherDesc") or [{}])[0].get("value") or "").strip()
    hum = cur.get("humidity")
    wind_mph = cur.get("windspeedMiles")
    wind_dir = cur.get("winddir16Point") or ""
    area_name = ((area.get("areaName") or [{}])[0].get("value") or loc).strip()
    region = ((area.get("region") or [{}])[0].get("value") or "").strip()
    place_label = f"{area_name}, {region}".strip(", ")
    hi = day0.get("maxtempF")
    lo = day0.get("mintempF")
    cond_part = f"{desc}, " if desc else ""
    feels_part = f" (feels like {feels_f}°F)" if feels_f is not None else ""
    snip = f"Current weather in {place_label}: {cond_part}{temp_f}°F{feels_part}, humidity {hum}%, wind {wind_mph} mph {wind_dir}".strip() + "."
    if hi is not None and lo is not None:
        snip += f" Today's high {hi}°F / low {lo}°F."
    return [{"title": f"Weather — {place_label}", "snippet": snip, "url": f"https://wttr.in/{urllib.parse.quote(loc)}"}]


def _query_open_meteo_weather(query: str, timeout: float = 3.0) -> List[Dict[str, str]]:
    """Query Open-Meteo geocoding + forecast APIs for exact real-time weather without API keys."""
    loc = _extract_location_for_weather(query)
    state_hint = ""
    loc_city = loc.strip()
    m_state = re.match(r"^(.*?)[,\s]+([A-Za-z]{2})$", loc_city)
    if m_state and m_state.group(2).lower() in _US_STATE_NAMES:
        loc_city = m_state.group(1).strip().rstrip(",")
        state_hint = _US_STATE_NAMES[m_state.group(2).lower()]
    elif "," in loc_city:
        parts = [p.strip() for p in loc_city.split(",") if p.strip()]
        loc_city = parts[0]
        if len(parts) > 1:
            state_hint = parts[1].lower()
    geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({
        "name": loc_city,
        "count": "8" if state_hint else "3",
        "language": "en",
        "format": "json",
    })
    geo = json.loads(_http_get_text(geo_url, timeout=timeout))
    results = geo.get("results") or []
    if not results:
        return []
    # Prefer matching state/region when supplied (e.g. "Payson AZ" -> Payson, Arizona)
    chosen = results[0]
    if state_hint:
        for r in results:
            admin1 = str(r.get("admin1", "")).lower()
            country = str(r.get("country_code", "")).lower()
            if state_hint in admin1 or (country == "us" and state_hint == admin1):
                chosen = r
                break

    lat, lon = chosen["latitude"], chosen["longitude"]
    place_label = f"{chosen.get('name', loc_city)}, {chosen.get('admin1', '')}".strip(", ")
    fc_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto",
        "forecast_days": "1",
    })
    fc = json.loads(_http_get_text(fc_url, timeout=timeout))
    cur = fc.get("current") or {}
    daily = fc.get("daily") or {}
    temp = cur.get("temperature_2m")
    hum = cur.get("relative_humidity_2m")
    wind = cur.get("wind_speed_10m")
    hi = (daily.get("temperature_2m_max") or [None])[0]
    lo = (daily.get("temperature_2m_min") or [None])[0]
    snip = f"Current temperature in {place_label}: {temp}°F, humidity {hum}%, wind {wind} mph."
    if hi is not None and lo is not None:
        snip += f" Today's high {hi}°F / low {lo}°F."
    return [{"title": f"Weather — {place_label}", "snippet": snip, "url": "https://open-meteo.com"}]


def _query_ddg_instant(query: str, timeout: float = 2.5) -> List[Dict[str, str]]:
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    })
    data = json.loads(_http_get_text(url, timeout=timeout))
    sources: List[Dict[str, str]] = []
    answer = (data.get("Answer") or "").strip()
    abstract = (data.get("AbstractText") or "").strip()
    heading = (data.get("Heading") or query).strip()
    abs_url = (data.get("AbstractURL") or "").strip()

    if answer:
        sources.append({"title": heading, "snippet": answer, "url": abs_url})
    if abstract:
        sources.append({"title": heading, "snippet": abstract, "url": abs_url})
    for topic in (data.get("RelatedTopics") or [])[:3]:
        if isinstance(topic, dict) and topic.get("Text"):
            sources.append({
                "title": topic.get("FirstURL", "").rsplit("/", 1)[-1].replace("_", " ") or heading,
                "snippet": str(topic["Text"]).strip(),
                "url": str(topic.get("FirstURL") or ""),
            })
    return sources


def _wiki_search_once(search_q: str, timeout: float = 3.0) -> List[Dict[str, str]]:
    search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": search_q,
        "srlimit": "2",
        "format": "json",
    })
    data = json.loads(_http_get_text(search_url, timeout=timeout))
    hits = (data.get("query") or {}).get("search") or []
    sources: List[Dict[str, str]] = []
    for h in hits[:2]:
        title = (h.get("title") or "").strip()
        snippet = _strip_html(h.get("snippet") or "")
        if not title:
            continue
        if not sources:
            try:
                ext_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
                    "action": "query",
                    "prop": "extracts",
                    "exintro": "1",
                    "explaintext": "1",
                    "exsentences": "2",
                    "titles": title,
                    "format": "json",
                })
                ext_data = json.loads(_http_get_text(ext_url, timeout=timeout))
                pages = (ext_data.get("query") or {}).get("pages") or {}
                for pg in pages.values():
                    extract = (pg.get("extract") or "").strip()
                    if extract:
                        snippet = extract
                        break
            except Exception:
                pass
        if snippet:
            sources.append({
                "title": title,
                "snippet": snippet,
                "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
            })
    return sources


def _query_wikipedia(query: str, timeout: float = 3.0) -> List[Dict[str, str]]:
    hits = _wiki_search_once(query, timeout=timeout)
    if hits:
        return hits
    # Progressive keyword relaxation for specific alphanumeric part codes
    words = [w for w in re.findall(r"[A-Za-z0-9-]+", query) if len(w) >= 3]
    if len(words) > 2:
        # Prefer alphabetic entity + core noun words
        alpha = [w for w in words if not any(c.isdigit() for c in w)]
        relaxed = " ".join(alpha[:3]) if alpha else " ".join(words[:2])
        if relaxed and relaxed.lower() != query.lower():
            return _wiki_search_once(relaxed, timeout=timeout)
    return []


def _query_google_news_rss(query: str, timeout: float = 3.0, max_results: int = 3) -> List[Dict[str, str]]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    xml_raw = _http_get_text(url, timeout=timeout)
    root = ET.fromstring(xml_raw)
    out: List[Dict[str, str]] = []
    for item in root.findall("./channel/item")[:max_results]:
        title = _strip_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        if title:
            out.append({"title": "News", "snippet": title, "url": link})
    return out


def search_web_snippets(query: str, timeout: float = 4.0, max_results: int = 3) -> Dict[str, Any]:
    """Execute live multi-API web search cleanly, returning offline/empty states honestly."""
    clean_q = _clean_search_query(query) or (query or "").strip()
    if not clean_q:
        return {"status": "empty", "query": "", "summary": "", "sources": [], "error": None}

    ql = clean_q.lower()
    sources: List[Dict[str, str]] = []
    net_error: Optional[str] = None

    if any(re.search(p, ql) for p in _WEATHER_PATTERNS):
        for fn in (_query_wttr_weather, _query_open_meteo_weather):
            try:
                sources = fn(clean_q, timeout=min(3.0, timeout))
                if sources:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                net_error = str(exc)
            except Exception:
                pass
    elif any(re.search(p, ql) for p in _NEWS_PATTERNS):
        try:
            sources = _query_google_news_rss(clean_q, timeout=min(3.5, timeout), max_results=max_results)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            net_error = str(exc)
        except Exception:
            pass

    if not sources:
        for fn in (
            lambda: _query_ddg_instant(clean_q, timeout=min(2.5, timeout)),
            lambda: _query_wikipedia(clean_q, timeout=min(3.0, timeout)),
            lambda: _query_google_news_rss(clean_q, timeout=min(3.0, timeout), max_results=max_results),
        ):
            try:
                sources = fn()
                if sources:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                net_error = str(exc)
            except Exception:
                pass

    if not sources:
        return {
            "status": "offline" if net_error else "empty",
            "query": clean_q,
            "summary": "",
            "sources": [],
            "error": net_error,
        }

    top_sources = sources[:max_results]
    summary_parts = []
    for s in top_sources:
        snip = s["snippet"]
        if len(snip) > 260:
            snip = snip[:257].rstrip() + "..."
        summary_parts.append(f"{s['title']}: {snip}")
    return {
        "status": "ok",
        "query": clean_q,
        "summary": " | ".join(summary_parts),
        "sources": top_sources,
        "error": None,
    }
