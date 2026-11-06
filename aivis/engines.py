"""Ask a question of an AI assistant through its API and return the answer text plus
any source URLs it cites.

Questions are sent with no system prompt, the way a person would type them, so the
answers reflect what a buyer would see.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

from .config import EngineConfig

TIMEOUT = 90


@dataclass
class Answer:
    text: str
    citations: list[str] = field(default_factory=list)


class EngineError(RuntimeError):
    pass


def _post(url: str, json: dict, headers: dict, retries: int = 3) -> dict:
    for attempt in range(retries + 1):
        resp = requests.post(url, json=json, headers=headers, timeout=TIMEOUT)
        if resp.status_code in (429, 500, 502, 503, 529) and attempt < retries:
            time.sleep(float(resp.headers.get("retry-after", 2 ** (attempt + 1))))
            continue
        if resp.status_code >= 400:
            raise EngineError(f"{resp.status_code}: {resp.text[:300]}")
        return resp.json()
    raise EngineError("retries exhausted")


def ask_anthropic(cfg: EngineConfig, question: str) -> Answer:
    data = _post(
        "https://api.anthropic.com/v1/messages",
        {"model": cfg.model, "max_tokens": 1500, "messages": [{"role": "user", "content": question}]},
        {"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return Answer(text)


def _openai_style(url: str, cfg: EngineConfig, question: str) -> dict:
    return _post(
        url,
        {"model": cfg.model, "messages": [{"role": "user", "content": question}]},
        {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
    )


def ask_openai(cfg: EngineConfig, question: str) -> Answer:
    data = _openai_style("https://api.openai.com/v1/chat/completions", cfg, question)
    return Answer(data["choices"][0]["message"].get("content") or "")


def ask_perplexity(cfg: EngineConfig, question: str) -> Answer:
    data = _openai_style("https://api.perplexity.ai/chat/completions", cfg, question)
    cites = data.get("citations") or [r.get("url") for r in data.get("search_results", []) if r.get("url")]
    return Answer(data["choices"][0]["message"].get("content") or "", list(cites))


def ask_gemini(cfg: EngineConfig, question: str) -> Answer:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent"
    data = _post(url, {"contents": [{"parts": [{"text": question}]}]},
                 {"x-goog-api-key": cfg.api_key, "Content-Type": "application/json"})
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks", [])
    return Answer(text, [c["web"]["uri"] for c in chunks if c.get("web", {}).get("uri")])


PROVIDERS = {
    "anthropic": ask_anthropic,
    "openai": ask_openai,
    "perplexity": ask_perplexity,
    "gemini": ask_gemini,
}


def ask(cfg: EngineConfig, question: str) -> Answer:
    try:
        fn = PROVIDERS[cfg.provider]
    except KeyError:
        raise EngineError(f"Unknown provider '{cfg.provider}'. Options: {', '.join(PROVIDERS)}")
    return fn(cfg, question)
