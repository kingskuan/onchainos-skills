"""Apple App Store client — official, free, no API key.

Uses the public iTunes Search/Lookup APIs for app metadata and the App Store
RSS `customerreviews` feed for reviews. All endpoints are Apple-official and
free; this reads public review data only (no posting, no manipulation).
"""
from __future__ import annotations

from typing import Any

import httpx

UA = {"User-Agent": "app-review-agent/0.1"}
MAX_PAGES = 10  # Apple RSS caps customer reviews at 10 pages (~500 reviews)


async def search(client: httpx.AsyncClient, term: str, country: str = "us", limit: int = 5) -> list[dict[str, Any]]:
    r = await client.get(
        "https://itunes.apple.com/search",
        params={"term": term, "entity": "software", "country": country, "limit": limit},
        headers=UA,
        timeout=25,
    )
    r.raise_for_status()
    out = []
    for a in r.json().get("results", []):
        out.append(
            {
                "app_id": str(a.get("trackId")),
                "name": a.get("trackName"),
                "developer": a.get("artistName"),
                "avg_rating": a.get("averageUserRating"),
                "rating_count": a.get("userRatingCount"),
                "genre": a.get("primaryGenreName"),
                "version": a.get("version"),
                "url": a.get("trackViewUrl"),
            }
        )
    return out


async def lookup(client: httpx.AsyncClient, app_id: str, country: str = "us") -> dict[str, Any] | None:
    r = await client.get(
        "https://itunes.apple.com/lookup",
        params={"id": app_id, "country": country},
        headers=UA,
        timeout=25,
    )
    r.raise_for_status()
    res = r.json().get("results", [])
    if not res:
        return None
    a = res[0]
    return {
        "app_id": str(a.get("trackId")),
        "name": a.get("trackName"),
        "developer": a.get("artistName"),
        "avg_rating": a.get("averageUserRating"),
        "rating_count": a.get("userRatingCount"),
        "genre": a.get("primaryGenreName"),
        "version": a.get("version"),
        "release_notes": a.get("releaseNotes"),
        "url": a.get("trackViewUrl"),
    }


async def _reviews_page(client: httpx.AsyncClient, app_id: str, country: str, page: int) -> list[dict[str, Any]]:
    url = (
        f"https://itunes.apple.com/{country}/rss/customerreviews/"
        f"page={page}/id={app_id}/sortby=mostrecent/json"
    )
    r = await client.get(url, headers=UA, timeout=25)
    if r.status_code != 200:
        return []
    try:
        feed = r.json().get("feed", {})
    except Exception:  # noqa: BLE001
        return []
    entries = feed.get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    out = []
    for e in entries:
        if "im:rating" not in e:  # first entry is app metadata
            continue
        out.append(
            {
                "rating": int(e["im:rating"]["label"]),
                "title": e.get("title", {}).get("label", ""),
                "content": e.get("content", {}).get("label", ""),
                "author": e.get("author", {}).get("name", {}).get("label", ""),
                "version": e.get("im:version", {}).get("label", ""),
                "updated": e.get("updated", {}).get("label", ""),
            }
        )
    return out


async def reviews(client: httpx.AsyncClient, app_id: str, country: str = "us", pages: int = 5) -> list[dict[str, Any]]:
    pages = max(1, min(pages, MAX_PAGES))
    all_reviews: list[dict[str, Any]] = []
    for p in range(1, pages + 1):
        batch = await _reviews_page(client, app_id, country, p)
        if not batch:
            break
        all_reviews.extend(batch)
    return all_reviews
