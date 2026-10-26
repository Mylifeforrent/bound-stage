#!/usr/bin/env python3
"""Optional DeepSeek connectivity check.

This does NOT change the product's AI path.  M0-M3 `llm_factory.invoke()` is a
deterministic stub: A1 parsing, A2 rule clustering and Copilot read-only answers
work without a vendor key, and the UI shows the "AI degraded" banner by design.

Use this only to verify that a DeepSeek key/network is usable before deciding
whether to invest in a real model adapter (a product change, not a QA change).

Usage:
    backend/qa/full_flow/qa.sh ai-check
or:
    backend/.venv/bin/python backend/qa/full_flow/scripts/ai_check.py

The key is read from .env.qa (DEEPSEEK_API_KEY) or the process environment and
is never printed.
"""

from __future__ import annotations

import asyncio
import sys

import httpx
from _qa_env import load_qa_env


async def main() -> int:
    env = load_qa_env()
    key = (env.get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        print("[skip] DEEPSEEK_API_KEY is empty in .env.qa")
        print("       This is expected: the current product AI path is a stub.")
        print("       To check a key, add DEEPSEEK_API_KEY to .env.qa and rerun.")
        return 2

    base = (env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model = env.get("DEEPSEEK_MODEL") or "deepseek-chat"
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Reply with exactly: HUNTAI_AI_OK"},
        ],
        "max_tokens": 8,
        "temperature": 0,
    }
    print(f"[run] POST {base} (model={model}); key is not printed")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        print(f"[fail] network error: {type(exc).__name__}")
        return 1

    if response.status_code != 200:
        print(f"[fail] HTTP {response.status_code}")
        print(f"       body: {response.text[:300]}")
        return 1

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except KeyError, IndexError, TypeError:
        print("[fail] unexpected response shape")
        return 1
    print(f"[ok] DeepSeek replied: {str(content).strip()[:80]}")
    print("     Reminder: this does not wire DeepSeek into the product.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
