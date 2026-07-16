"""Deterministic review analysis — no LLM, free and reproducible.

Turns a list of reviews into: rating distribution, sentiment split, the themes
users love vs complain about (keyword extraction), extracted bugs/issues and
feature requests, a recency trend, and representative sample reviews.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

_STOP = set(
    """
a an the and or but if then else for to of in on at by with from as is are was were be been being
this that these those it its it's i you he she they we me my your our their them his her about into
over under again more most some any all no not only just very so too can could will would should
have has had do does did done get got getting go going make made use used using really much many
app apps application phone android ios iphone ipad update updated version download downloaded star
stars rating ratings review reviews please thank thanks thankyou need needs want wanted like likes
one two three four five time times day days now new old good great nice love loved best awesome
bad worst hate ok okay yes yeah also even still back way things thing lot little bit pretty
""".split()
)

_ISSUE_RE = re.compile(
    r"\b(crash|crashes|crashing|crashed|bug|bugs|buggy|freeze|frozen|froze|glitch|lag|laggy|slow|"
    r"error|errors|broken|won't|wont|can't|cant|cannot|doesn't work|does not work|not working|"
    r"stopped working|force close|force closes|black screen|won't open|keeps closing)\b",
    re.I,
)
_REQUEST_RE = re.compile(
    r"\b(please add|would be nice|i wish|wish it|should add|add a|add an|feature request|"
    r"hope (?:you|they) add|needs a|need a|would love|can you add|why can't we|allow us to|"
    r"there should be|it would help)\b",
    re.I,
)

_WORD_RE = re.compile(r"[a-z][a-z']+")


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if len(w) >= 3 and w not in _STOP]


def _keywords(reviews: list[dict[str, Any]], top: int = 12) -> list[dict[str, Any]]:
    uni: Counter = Counter()
    bi: Counter = Counter()
    for r in reviews:
        toks = _tokens(f"{r.get('title','')} {r.get('content','')}")
        uni.update(toks)
        bi.update(f"{a} {b}" for a, b in zip(toks, toks[1:]))
    # prefer informative bigrams, then fill with unigrams
    terms: list[tuple[str, int]] = []
    for phrase, c in bi.most_common(top):
        if c >= 2:
            terms.append((phrase, c))
    for w, c in uni.most_common(top * 2):
        if len(terms) >= top:
            break
        if not any(w in p for p, _ in terms):
            terms.append((w, c))
    return [{"term": t, "count": c} for t, c in terms[:top]]


def _extract(reviews: list[dict[str, Any]], pattern: re.Pattern, limit: int = 8) -> list[dict[str, Any]]:
    hits = []
    for r in reviews:
        text = f"{r.get('title','')} {r.get('content','')}".strip()
        m = pattern.search(text)
        if m:
            snippet = text if len(text) <= 220 else text[:217] + "..."
            hits.append({"rating": r.get("rating"), "keyword": m.group(0).lower(), "review": snippet})
    hits.sort(key=lambda h: (h["rating"] or 5))  # worst-rated first
    return hits[:limit]


def _trend(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    # reviews arrive newest-first; compare newer half vs older half
    rated = [r["rating"] for r in reviews if isinstance(r.get("rating"), int)]
    if len(rated) < 6:
        return {"available": False}
    half = len(rated) // 2
    newer = rated[:half]
    older = rated[half:]
    avg = lambda xs: round(sum(xs) / len(xs), 2)  # noqa: E731
    delta = round(avg(newer) - avg(older), 2)
    return {
        "available": True,
        "recent_avg": avg(newer),
        "older_avg": avg(older),
        "delta": delta,
        "direction": "improving" if delta > 0.1 else "declining" if delta < -0.1 else "stable",
    }


def analyze(app_meta: dict[str, Any], reviews: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(reviews)
    dist = {str(i): 0 for i in range(1, 6)}
    for r in reviews:
        k = str(r.get("rating"))
        if k in dist:
            dist[k] += 1
    rated = [r for r in reviews if isinstance(r.get("rating"), int)]
    sample_avg = round(sum(r["rating"] for r in rated) / len(rated), 2) if rated else None

    pos = [r for r in rated if r["rating"] >= 4]
    neu = [r for r in rated if r["rating"] == 3]
    neg = [r for r in rated if r["rating"] <= 2]

    def pct(x):
        return round(100 * len(x) / len(rated), 1) if rated else None

    def samples(revs, k=3):
        out = []
        for r in revs[:k]:
            text = (r.get("content") or r.get("title") or "").strip()
            out.append(
                {
                    "rating": r.get("rating"),
                    "title": r.get("title", ""),
                    "review": text if len(text) <= 240 else text[:237] + "...",
                }
            )
        return out

    return {
        "app": app_meta,
        "sample_size": n,
        "sample_avg_rating": sample_avg,
        "overall_rating": app_meta.get("avg_rating"),
        "overall_rating_count": app_meta.get("rating_count"),
        "rating_distribution": dist,
        "sentiment": {
            "positive": {"count": len(pos), "pct": pct(pos)},
            "neutral": {"count": len(neu), "pct": pct(neu)},
            "negative": {"count": len(neg), "pct": pct(neg)},
        },
        "loved_themes": _keywords(pos),
        "complaint_themes": _keywords(neg),
        "top_issues": _extract(neg + neu, _ISSUE_RE),
        "feature_requests": _extract(reviews, _REQUEST_RE),
        "rating_trend": _trend(reviews),
        "sample_positive": samples(pos),
        "sample_negative": samples(neg),
        "disclaimer": (
            "Analysis of public app-store reviews for research/product insight. "
            "Read-only; no reviews are posted or altered."
        ),
    }
