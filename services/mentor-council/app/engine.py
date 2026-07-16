"""Advice engine — single mentor answers and the council roundtable/debate.

Council flow: a cheap router picks the 2-3 most relevant methodologies for the
question, each gives its take in parallel, then a synthesis weighs them into one
verdict (and surfaces where they disagree — the shareable part).
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from . import llm
from .personas import DISCLAIMER, PERSONAS, catalog, persona_system_prompt


def _not_configured() -> dict[str, Any]:
    return {"available": False, "reason": "LLM not configured — set LLM_API_KEY (OpenAI-compatible)."}


async def mentor(client: httpx.AsyncClient, key: str, question: str) -> dict[str, Any]:
    if key not in PERSONAS:
        return {"available": False, "reason": f"unknown mentor '{key}'", "mentors": list(PERSONAS)}
    if not llm.configured():
        return _not_configured()
    answer = await llm.chat(client, [
        {"role": "system", "content": persona_system_prompt(key)},
        {"role": "user", "content": question},
    ])
    return {
        "available": True,
        "mentor": PERSONAS[key]["brand"],
        "key": key,
        "answer": answer.strip(),
        "disclaimer": DISCLAIMER,
        "model": llm.config()["model"],
    }


def _extract_json(text: str):
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


async def _route(client: httpx.AsyncClient, question: str, k: int) -> list[str]:
    cat = catalog()
    listing = "\n".join(f"- {c['key']}: {c['brand']} — {c['domain']}" for c in cat)
    out = await llm.chat(client, [
        {"role": "system", "content": "You route a question to the most relevant advisory frameworks."},
        {"role": "user", "content": (
            f"Frameworks:\n{listing}\n\nQuestion: {question}\n\n"
            f"Pick the {k} most relevant keys. Return ONLY a JSON array of keys."
        )},
    ], temperature=0.1, max_tokens=80)
    picked = _extract_json(out) or []
    picked = [k_ for k_ in picked if k_ in PERSONAS]
    return picked[:k] if picked else [c["key"] for c in cat[:k]]


async def council(
    client: httpx.AsyncClient, question: str, k: int = 3, mentors: list[str] | None = None
) -> dict[str, Any]:
    if not llm.configured():
        return _not_configured()
    keys = [m for m in (mentors or []) if m in PERSONAS] or await _route(client, question, k)

    takes = await asyncio.gather(*[mentor(client, key, question) for key in keys])
    panel = [{"mentor": t["mentor"], "key": t["key"], "take": t["answer"]}
             for t in takes if t.get("available")]

    panel_text = "\n\n".join(f"[{p['mentor']}]\n{p['take']}" for p in panel)
    synth = await llm.chat(client, [
        {"role": "system", "content": (
            "You are the chair of an advisory roundtable. Weigh the panelists' distinct takes on "
            "the user's question. Be specific and useful, not diplomatic."
        )},
        {"role": "user", "content": (
            f"QUESTION: {question}\n\nPANEL:\n{panel_text}\n\n"
            "Return ONLY JSON with keys: "
            "synthesis (2-4 sentences with your combined recommendation), "
            "where_they_disagree (string — the key tension between the frameworks), "
            "action (1-2 concrete next steps as an array of strings)."
        )},
    ], temperature=0.3)
    verdict = _extract_json(synth) or {"synthesis": synth}

    return {
        "available": True,
        "question": question,
        "panelists": [p["mentor"] for p in panel],
        "panel": panel,
        "verdict": verdict,
        "disclaimer": DISCLAIMER,
        "model": llm.config()["model"],
    }
