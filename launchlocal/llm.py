"""Async chat client with a provider chain. All providers are OpenAI-compatible.

Order: Nosana hosted inference -> our Nosana GPU deployment (docs/nosana-llm.json, when present)
-> Ollama Cloud as a fallback. Nosana's hosted catalog changes during the day (the chat model
disappeared at 15:52 JST on 2026-11-14), so the model is discovered on each attempt and a provider
that fails is skipped for 90 seconds. Every run logs which provider served it.
"""
import asyncio
import contextvars
import json
import os
import re
import sys
import time

from openai import AsyncOpenAI

from launchlocal.common import ROOT, emit, load_env

PREFERRED = "qwen/qwen3.8-27b"
RETRY_AFTER_S = 90
RUN_DIR: contextvars.ContextVar = contextvars.ContextVar("launchlocal_run_dir", default=None)  # set by callers, for the log

_clients: dict = {}        # (event loop id, provider id) -> AsyncOpenAI; clients are bound to one loop
_models: dict = {}         # provider id -> discovered model id
_down: dict = {}           # provider id -> time before which it is skipped
_noted: set = set()        # (run dir, provider id) already logged
last_latency: float = 0.0
last_provider: str = ""


def providers() -> list[dict]:
    load_env()
    out = []
    if os.environ.get("NOSANA_API_KEY"):
        out.append({"id": "nosana-hosted", "label": "Nosana hosted inference", "base_url": "https://inference.nosana.com/v1",
                    "key": os.environ["NOSANA_API_KEY"], "model": None, "timeout": 120, "qwen": True})
    gpu = ROOT / "docs" / "nosana-llm.json"
    if gpu.exists():
        d = json.loads(gpu.read_text())
        out.append({"id": "nosana-gpu", "label": "Nosana GPU deployment", "base_url": d["endpoint"].rstrip("/") + "/v1",
                    "key": d.get("api_key") or "none", "model": d["model"], "timeout": 120, "qwen": "qwen" in d["model"].lower()})
    if os.environ.get("OLLAMA_API_KEY"):
        out.append({"id": "ollama-cloud", "label": "Ollama Cloud (fallback)", "base_url": "https://ollama.com/v1",
                    "key": os.environ["OLLAMA_API_KEY"], "model": os.environ.get("LAUNCHLOCAL_FALLBACK_MODEL", "deepseek-v4.1-flash"),
                    "timeout": 90, "qwen": False})
    return out


def _client(p: dict) -> AsyncOpenAI:
    key = (id(asyncio.get_running_loop()), p["id"])
    if key not in _clients:
        _clients[key] = AsyncOpenAI(base_url=p["base_url"], api_key=p["key"], timeout=p["timeout"], max_retries=0)
    return _clients[key]


async def _model(p: dict, client: AsyncOpenAI) -> str:
    if p["model"]:
        return p["model"]
    if p["id"] not in _models:  # hosted catalog: never assume the model is still there
        ids = [m.id for m in (await client.models.list()).data]
        chat_ids = [i for i in ids if not any(x in i.lower() for x in ("embed", "whisper", "tts", "rerank"))]
        if not chat_ids:
            raise RuntimeError(f"{p['label']} lists no chat model right now ({', '.join(ids) or 'empty catalog'})")
        _models[p["id"]] = PREFERRED if PREFERRED in chat_ids else chat_ids[0]
    return _models[p["id"]]


def _note(p: dict, model: str, first: dict, why: str) -> None:
    rd = RUN_DIR.get()
    if rd is None or (str(rd), p["id"]) in _noted:
        return
    _noted.add((str(rd), p["id"]))
    if p is first:
        emit(rd, "system", "log", f"Language model: {p['label']} ({model})", provider=p["id"], model=model, fallback=False)
    else:
        emit(rd, "system", "log", f"{first['label']} unavailable ({why}); language calls use {p['label']} ({model})",
             provider=p["id"], model=model, fallback=True)


async def chat(system: str, user: str, max_tokens: int = 2000, temperature: float = 0.4) -> str:
    global last_latency, last_provider
    chain = providers()
    if not chain:
        raise RuntimeError("no language model provider configured (NOSANA_API_KEY or OLLAMA_API_KEY)")
    why, last_exc = "", None
    for p in chain:
        if _down.get(p["id"], 0) > time.time():
            why = why or _down.get(p["id"] + ":why", "recent failure")
            continue
        try:
            client = _client(p)
            model = await _model(p, client)
            t = time.time()
            r = await client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=temperature,
                **({"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}} if p["qwen"] else {}),
            )
            text = re.sub(r"<think>.*?</think>", "", r.choices[0].message.content or "", flags=re.S).strip()
            if not text:
                raise RuntimeError("empty completion")
            last_latency, last_provider = time.time() - t, p["id"]
            print(f"[llm] {p['id']} {model} {last_latency:.1f}s {r.usage.completion_tokens if r.usage else '?'} tok", file=sys.stderr)
            _note(p, model, chain[0], why)
            return text
        except Exception as e:  # any failure moves on to the next provider; exception text may hold headers, keep the class
            last_exc = e
            reason = str(e)[:120] if isinstance(e, RuntimeError) else type(e).__name__
            _down[p["id"]], _down[p["id"] + ":why"] = time.time() + RETRY_AFTER_S, reason
            _models.pop(p["id"], None)
            why = why or reason
            print(f"[llm] {p['id']} failed: {reason}", file=sys.stderr)
    raise RuntimeError(f"all language model providers failed: {why}") from last_exc


def parse_json(text: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # take the outermost {...} or [...] span
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in model output")
    s = min(starts)
    e = text.rfind("}" if text[s] == "{" else "]")
    return json.loads(text[s : e + 1])


async def chat_json(system: str, user: str, max_tokens: int = 2000) -> dict | list:
    sys_msg = system + "\n\nReply with one valid JSON value only. No markdown fences, no commentary."
    text = await chat(sys_msg, user, max_tokens, temperature=0.3)
    try:
        return parse_json(text)
    except ValueError:  # JSONDecodeError is a ValueError
        text = await chat(sys_msg, user + "\n\nYour previous reply was not valid JSON. Return only the JSON.", max_tokens, 0.1)
        return parse_json(text)


if __name__ == "__main__":
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure: [1, 2] done') == [1, 2]
    print(asyncio.run(chat_json("You are terse.", 'Return {"ok": true, "ja": "<a Japanese greeting>"}')), "via", last_provider)
