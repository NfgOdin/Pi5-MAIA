"""
web_search.py - Zero-Key Live Web Search & Learned-Knowledge Trigger Engine for CarPi5

Uses DuckDuckGo Instant Answer, Wikipedia Search, and DuckDuckGo HTML fallback over
whichever uplink Pi 5 has active (Wi-Fi or Pi 3 Android USB Tether).
Never fabricates search results when offline.
"""

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

_EXPLICIT_WEB_PATTERNS = (
    r"\b(?:look\s+up|search(?:\s+for|\s+the\s+web|\s+online)?|google|find\s+out|check\s+online|web\s+search|search\s+internet)\b",
)

_LIVE_REALTIME_PATTERNS = (
    r"\b(?:weather|forecast|rain|temperature\s+(?:outside|in)|humidity|uv\s+index)\b",
    r"\b(?:latest\s+news|news\s+about|current\s+price|stock\s+price|score\s+of|who\s+won|exchange\s+rate)\b",
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
    "weather", "forecast", "rain", "temperature outside", "today's", "right now",
    "latest news", "current price", "stock price", "score", "traffic", "time is it",
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

    for pat in _LIVE_REALTIME_PATTERNS:
        if re.search(pat, ql):
            return True, _clean_search_query(msg)

    # Open general-knowledge questions when local lorebooks & RAG didn't already answer
    if not (lore_injection or "").strip() and rag_hits == 0:
        stripped = _clean_search_query(msg).lower()
        if any(ql.startswith(p) or stripped.startswith(p) for p in _OPEN_FACTUAL_STARTS):
            return True, _clean_search_query(msg)

    return False, ""


def _http_get_text(url: str, timeout: float = 4.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CarPi5-RUM/1.0 (+https://github.com/NfgOdin/Pi5-MAIA)",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _strip_html(raw: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", raw or "")
    txt = html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def _query_ddg_instant(query: str, timeout: float = 3.5) -> Tuple[List[Dict[str, str]], bool]:
    """Query DuckDuckGo Instant Answer API. Returns (sources, network_ok)."""
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    })
    raw = _http_get_text(url, timeout=timeout)
    data = json.loads(raw)
    sources: List[Dict[str, str]] = []
    answer = (data.get("Answer") or "").strip()
    abstract = (data.get("AbstractText") or "").strip()
    heading = (data.get("Heading") or query).strip()
    abs_url = (data.get("AbstractURL") or "").strip()

    if answer:
        sources.append({"title": heading, "snippet": answer, "url": abs_url})
    if abstract:
        sources.append({"title": heading, "snippet": abstract, "url": abs_url})

    for topic in (data.get("RelatedTopics") or [])[:4]:
        if isinstance(topic, dict) and topic.get("Text"):
            sources.append({
                "title": topic.get("FirstURL", "").rsplit("/", 1)[-1].replace("_", " ") or heading,
                "snippet": str(topic["Text"]).strip(),
                "url": str(topic.get("FirstURL") or ""),
            })
    return sources, True


def _query_wikipedia(query: str, timeout: float = 3.5) -> List[Dict[str, str]]:
    """Fallback factual summary search via Wikipedia API."""
    search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": query,
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
        # Fetch crisp 2-sentence extract for top hit
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


def _query_ddg_html(query: str, timeout: float = 4.5, max_results: int = 3) -> List[Dict[str, str]]:
    """HTML snippet search via DuckDuckGo lite endpoint for live/current queries."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    body = _http_get_text(url, timeout=timeout)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|div|span)>', body, flags=re.IGNORECASE | re.DOTALL)
    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', body, flags=re.IGNORECASE | re.DOTALL)
    out: List[Dict[str, str]] = []
    for idx, snip_raw in enumerate(snippets[:max_results]):
        snip = _strip_html(snip_raw)
        title = _strip_html(titles[idx]) if idx < len(titles) else query
        if snip:
            out.append({"title": title, "snippet": snip, "url": ""})
    return out


def search_web_snippets(query: str, timeout: float = 4.5, max_results: int = 3) -> Dict[str, Any]:
    """Execute live multi-engine web search cleanly, returning offline/empty states honestly."""
    clean_q = _clean_search_query(query) or (query or "").strip()
    if not clean_q:
        return {"status": "empty", "query": "", "summary": "", "sources": [], "error": None}

    sources: List[Dict[str, str]] = []
    net_error: Optional[str] = None

    try:
        sources, _ = _query_ddg_instant(clean_q, timeout=min(3.5, timeout))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        net_error = str(exc)
    except Exception:
        pass

    if not sources and net_error is None:
        try:
            sources = _query_ddg_html(clean_q, timeout=timeout, max_results=max_results)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            net_error = str(exc)
        except Exception:
            pass

    if not sources and net_error is None:
        try:
            sources = _query_wikipedia(clean_q, timeout=min(3.5, timeout))
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
