"""Google Play client — reads public app metadata and reviews via the
`google-play-scraper` library (no official API exists). Read-only: metadata and
public reviews only. Runs the sync library in a thread so it doesn't block the
event loop.
"""
from __future__ import annotations

import asyncio
from typing import Any


def _search_sync(term: str, country: str, lang: str, limit: int) -> list[dict[str, Any]]:
    from google_play_scraper import search as gp_search

    res = gp_search(term, lang=lang, country=country, n_hits=limit)
    out = []
    for a in res:
        out.append(
            {
                "app_id": a.get("appId"),
                "name": a.get("title"),
                "developer": a.get("developer"),
                "avg_rating": a.get("score"),
                "genre": a.get("genre"),
                "url": f"https://play.google.com/store/apps/details?id={a.get('appId')}",
            }
        )
    return out


def _lookup_sync(app_id: str, country: str, lang: str) -> dict[str, Any] | None:
    from google_play_scraper import app as gp_app

    a = gp_app(app_id, lang=lang, country=country)
    if not a:
        return None
    return {
        "app_id": app_id,
        "name": a.get("title"),
        "developer": a.get("developer"),
        "avg_rating": a.get("score"),
        "rating_count": a.get("ratings"),
        "reviews_count": a.get("reviews"),
        "genre": a.get("genre"),
        "version": a.get("version"),
        "url": a.get("url"),
    }


def _reviews_sync(app_id: str, country: str, lang: str, count: int) -> list[dict[str, Any]]:
    from google_play_scraper import Sort, reviews as gp_reviews

    res, _ = gp_reviews(app_id, lang=lang, country=country, count=count, sort=Sort.NEWEST)
    out = []
    for x in res:
        out.append(
            {
                "rating": x.get("score"),
                "title": "",
                "content": x.get("content") or "",
                "author": x.get("userName", ""),
                "version": x.get("reviewCreatedVersion", "") or "",
                "updated": str(x.get("at", "")),
                "thumbs_up": x.get("thumbsUpCount", 0),
            }
        )
    return out


async def search(_client, term: str, country: str = "us", limit: int = 5) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_search_sync, term, country, "en", limit)


async def lookup(_client, app_id: str, country: str = "us") -> dict[str, Any] | None:
    return await asyncio.to_thread(_lookup_sync, app_id, country, "en")


async def reviews(_client, app_id: str, country: str = "us", pages: int = 5) -> list[dict[str, Any]]:
    # ~50 reviews per "page" to mirror Apple's paging semantics
    count = max(1, min(pages, 10)) * 50
    return await asyncio.to_thread(_reviews_sync, app_id, country, "en", count)
