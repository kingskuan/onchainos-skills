"""Pluggable LLM client (OpenAI-compatible chat completions).

Works with any OpenAI-compatible endpoint — DeepSeek (default, cheap), OpenAI,
Together, Groq, local Ollama, etc. — via three env vars:

  LLM_API_KEY    provider API key (required to enable the judgment layer)
  LLM_BASE_URL   default https://api.deepseek.com
  LLM_MODEL      default deepseek-chat

No key → the judgment layer degrades to {"available": false} so the free data
layer keeps working.
"""
from __future__ import annotations

import os
from typing import Any

import httpx


def config() -> dict[str, str]:
    return {
        "api_key": os.getenv("LLM_API_KEY", ""),
        "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "model": os.getenv("LLM_MODEL", "deepseek-chat"),
    }


def configured() -> bool:
    return bool(config()["api_key"])


async def chat(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 1100,
) -> str:
    c = config()
    if not c["api_key"]:
        raise RuntimeError("LLM_API_KEY not set")
    r = await client.post(
        f"{c['base_url']}/v1/chat/completions",
        headers={"Authorization": f"Bearer {c['api_key']}", "Content-Type": "application/json"},
        json={
            "model": c["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=90,
    )
    r.raise_for_status()
    data: dict[str, Any] = r.json()
    return data["choices"][0]["message"]["content"]
