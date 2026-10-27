"""Gemini client: model fallback chains, JSON output, a disk cache keyed by the exact request, and a token ledger.

Two tiers. "bulk" is for extraction (many calls, small tasks). "strong" is for the comparison steps, where a wrong
answer is expensive. On the free tier the Pro model has no quota, so the strong chain falls back to the best Flash model
and every result records which model actually produced it.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "llm_cache"
LEDGER = ROOT / "data" / "llm_ledger.json"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

CHAINS = {
    "bulk": ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"],
    "strong": ["gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
}


class LLMError(RuntimeError):
    pass


def _key() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"].strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    raise LLMError("GEMINI_API_KEY is not set (put it in .env)")


def _record(model: str, usage: dict, cached: bool) -> None:
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    row = ledger.setdefault(model, {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0})
    if cached:
        row["cache_hits"] += 1
    else:
        row["calls"] += 1
        row["input_tokens"] += usage.get("promptTokenCount", 0)
        row["output_tokens"] += usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
    LEDGER.write_text(json.dumps(ledger, indent=1))


def _post(model: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(API.format(model=model), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": _key()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def ask(prompt: str, tier: str = "bulk", system: str | None = None, schema: dict | None = None,
        temperature: float = 0.0, timeout: float = 180, chain: list[str] | None = None) -> dict:
    """Run a prompt. Returns {"data": parsed JSON or text, "model": model that answered, "cached": bool}.

    With `schema` the model is asked for JSON in that shape. Models are tried in order; quota (429), overload (503)
    and unknown-model (404) errors move on to the next one, other errors raise.
    """
    models = chain or CHAINS[tier]
    body: dict = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": temperature}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if schema:
        body["generationConfig"].update(responseMimeType="application/json", responseSchema=schema)
    digest = hashlib.sha256(json.dumps([body, tier], sort_keys=True).encode()).hexdigest()[:32]
    path = CACHE / f"{digest}.json"
    if path.exists():
        hit = json.loads(path.read_text())
        _record(hit["model"], {}, True)
        return {**hit, "cached": True}
    last = "no model tried"
    for rnd in range(4):  # if every model is overloaded, wait and go round again
        if rnd:
            time.sleep(45 * rnd)
        out = _try(models, body, schema, timeout)
        if isinstance(out, dict):
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"data": out["data"], "model": out["model"]}))
            _record(out["model"], out["usage"], False)
            return {"data": out["data"], "model": out["model"], "cached": False}
        last = out
        if "HTTP 503" not in last and "HTTP 429" not in last:
            break
    raise LLMError(f"all models failed; last: {last}")


def _try(models, body, schema, timeout):
    """One pass down the chain. Returns the answer dict, or the last error as a string."""
    last = "no model tried"
    for model in models:
        for attempt in range(3):
            try:
                r = _post(model, body, timeout)
            except urllib.error.HTTPError as err:
                detail = err.read().decode()[:200].replace("\n", " ")
                last = f"{model}: HTTP {err.code} {detail}"
                if err.code == 503 and attempt < 2:
                    time.sleep(8 * (attempt + 1))
                    continue
                if err.code in (429, 503, 404):
                    break
                raise LLMError(last) from None
            except (urllib.error.URLError, TimeoutError) as err:
                last = f"{model}: {err}"
                if attempt < 2:
                    time.sleep(5)
                    continue
                break
            cand = (r.get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
            if not text:
                last = f"{model}: empty answer (finish: {cand.get('finishReason')})"
                break
            try:
                data = json.loads(text) if schema else text
            except json.JSONDecodeError:
                last = f"{model}: invalid JSON"
                break
            return {"data": data, "model": model, "usage": r.get("usageMetadata", {})}
    return last


def ledger() -> dict:
    return json.loads(LEDGER.read_text()) if LEDGER.exists() else {}


def publish_ledger() -> None:
    """Copy the token ledger next to the app so the Watch tab can show it."""
    dest = ROOT / "app" / "data" / "ledger.json"
    dest.write_text(json.dumps(ledger(), indent=1))
