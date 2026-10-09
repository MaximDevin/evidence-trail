"""Evidence collectors: free, key-less public data sources.

Primary sources (all no-signup, no-key):
  * Binance public REST   - 24h tickers and OHLCV candles
  * CoinGecko public API  - independent spot price cross-check
  * RSS via rss2json       - CoinDesk / Decrypt headlines
  * HN Algolia            - developer-community mentions

Every collector records {url, fetched_at, payload} so the exact bytes are
re-fetchable. If the network is unavailable the collector falls back to the
captured fixtures in ``fixtures/`` (same URLs, real data, marked offline).
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from .evidence import Evidence, content_id

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(ROOT, "fixtures")

UA = {"User-Agent": "EvidenceTrail/1.0 (research bot; +https://dorahacks.io)"}
TIMEOUT = 20


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_json(url: str, offline_ok: bool = True) -> tuple[dict, str, bool]:
    """Returns (payload, url, offline). Raises if neither live nor fixture works."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8")), url, False
    except Exception:
        if not offline_ok:
            raise
        return _fixture(url), url, True


def _fixture_key(url: str) -> str:
    return content_id({"url": url})[:16]


def _fixture(url: str) -> dict:
    path = os.path.join(FIXTURES, _fixture_key(url) + ".json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_fixture(url: str, payload: dict) -> None:
    os.makedirs(FIXTURES, exist_ok=True)
    path = os.path.join(FIXTURES, _fixture_key(url) + ".json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)


# ---------------------------------------------------------------- sources
BINANCE = "https://api.binance.com/api/v3"
COINGECKO = "https://api.coingecko.com/api/v3"
RSS2JSON = "https://api.rss2json.com/v1/api.json"
HN = "https://hn.algolia.com/api/v1/search"

NEWS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Decrypt", "https://decrypt.co/feed"),
]


def fetch_ticker(symbol: str) -> tuple[dict, str, bool]:
    return http_json(f"{BINANCE}/ticker/24hr?symbol={urllib.parse.quote(symbol)}")


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 120) -> tuple[dict, str, bool]:
    url = f"{BINANCE}/klines?symbol={urllib.parse.quote(symbol)}&interval={interval}&limit={limit}"
    payload, u, off = http_json(url)
    # normalize: list -> {"rows": [...]}
    if isinstance(payload, list):
        payload = {"rows": payload}
    return payload, u, off


def fetch_spot(ids: list[str]) -> tuple[dict, str, bool]:
    url = f"{COINGECKO}/simple/price?ids={','.join(ids)}&vs_currencies=usd&include_24hr_change=true"
    return http_json(url)


def fetch_news(limit: int = 10) -> tuple[dict, str, bool]:
    """rss2json free tier caps count at 10 - keep requests inside that."""
    limit = max(1, min(limit, 10))
    items, urls = [], []
    live_ok = False
    for name, feed in NEWS_FEEDS:
        url = f"{RSS2JSON}?rss_url={urllib.parse.quote(feed, safe='')}&count={limit}"
        payload = None
        for _attempt in range(2):
            try:
                payload, u, off = http_json(url)
                if not off:
                    save_fixture(u, payload)
                    live_ok = True
                break
            except Exception:
                payload = None
        if payload is None:
            continue
        urls.append(url)
        for it in (payload.get("items") or [])[:limit]:
            title = (it.get("title") or "").strip()
            if not title:
                continue
            items.append({"feed": name, "title": title,
                          "link": it.get("link") or "", "published": it.get("pubDate") or ""})
    if not items:
        # last resort: any captured fixture for these feeds
        for name, feed in NEWS_FEEDS:
            url = f"{RSS2JSON}?rss_url={urllib.parse.quote(feed, safe='')}&count={limit}"
            try:
                payload = _fixture(url)
            except Exception:
                continue
            for it in (payload.get("items") or [])[:limit]:
                title = (it.get("title") or "").strip()
                if title:
                    items.append({"feed": name, "title": title,
                                  "link": it.get("link") or "",
                                  "published": it.get("pubDate") or ""})
            urls.append(url)
    return {"items": items, "urls": urls}, " | ".join(urls), not live_ok


def fetch_hn(query: str = "crypto", limit: int = 8) -> tuple[dict, str, bool]:
    url = f"{HN}?query={urllib.parse.quote(query)}&hitsPerPage={limit}"
    payload, u, off = http_json(url)
    hits = [{"title": h.get("title"), "url": h.get("url"),
             "points": h.get("points"), "created_at": h.get("created_at")}
            for h in (payload.get("hits") or [])]
    return {"items": hits}, u, off


# ---------------------------------------------------------------- bundle
def collect(watchlist: list[str], cg_ids: list[str]) -> list[dict]:
    """Fetch every source once and return a list of Evidence dicts."""
    out: list[Evidence] = []
    meta = {"offline": []}

    for sym in watchlist:
        try:
            payload, url, off = fetch_ticker(sym)
            if not off:
                save_fixture(url, payload)
            out.append(Evidence.make("market.24h", "Binance public REST", url, utcnow(), {
                "symbol": sym,
                "last_price": float(payload.get("lastPrice") or 0),
                "change_pct_24h": float(payload.get("priceChangePercent") or 0),
                "quote_volume_24h": float(payload.get("quoteVolume") or 0),
                "high_24h": float(payload.get("highPrice") or 0),
                "low_24h": float(payload.get("lowPrice") or 0),
            }))
        except Exception as e:
            meta["offline"].append(f"ticker:{sym}:{e}")

    for sym in watchlist:
        try:
            payload, url, off = fetch_klines(sym, "1h", 120)
            if not off:
                save_fixture(url, payload)
            out.append(Evidence.make("candles.1h", "Binance public REST", url, utcnow(),
                                     {"symbol": sym, "interval": "1h", "rows": payload["rows"]}))
        except Exception as e:
            meta["offline"].append(f"klines:{sym}:{e}")

    try:
        payload, url, off = fetch_spot(cg_ids)
        if not off:
            save_fixture(url, payload)
        for cid, vals in payload.items():
            out.append(Evidence.make("spot.coingecko", "CoinGecko public API", url, utcnow(),
                                     {"id": cid, "usd": vals.get("usd"),
                                      "usd_change_24h": vals.get("usd_24h_change")}))
    except Exception as e:
        meta["offline"].append(f"spot:{e}")

    try:
        payload, url, off = fetch_news()
        for i, item in enumerate(payload.get("items", [])):
            out.append(Evidence.make("news.headline", item["feed"], item.get("link", url),
                                     utcnow(), {"index": i, **item}))
    except Exception as e:
        meta["offline"].append(f"news:{e}")

    try:
        payload, url, off = fetch_hn()
        for item in payload.get("items", []):
            if item.get("title"):
                out.append(Evidence.make("community.hn", "HN Algolia", url, utcnow(), item))
    except Exception as e:
        meta["offline"].append(f"hn:{e}")

    return out
