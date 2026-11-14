"""Async client for Nosana hosted inference (OpenAI-compatible)."""
import asyncio
import json
import os
import re
import sys
import time

from openai import AsyncOpenAI

from launchlocal.common import load_env

BASE_URL = "https://inference.nosana.com/v1"
PREFERRED = "qwen/qwen3.8-27b"

_client: AsyncOpenAI | None = None
_model: str | None = None
_lock: "asyncio.Lock | None" = None
_loop = None
last_latency: float = 0.0


async def _get() -> tuple[AsyncOpenAI, str]:
    global _client, _model, _lock, _loop
    loop = asyncio.get_running_loop()
    if _loop is not loop:  # httpx clients and locks are bound to one event loop; callers may asyncio.run per stage
        load_env()
        _client = AsyncOpenAI(base_url=BASE_URL, api_key=os.environ["NOSANA_API_KEY"], timeout=180)
        _lock, _loop = asyncio.Lock(), loop
    async with _lock:  # parallel first calls wait for model discovery
        if _model is None:
            ids = [m.id for m in (await _client.models.list()).data]
            chat_ids = [i for i in ids if "embed" not in i]
            _model = PREFERRED if PREFERRED in ids else (chat_ids or ids)[0]
    return _client, _model


async def chat(system: str, user: str, max_tokens: int = 2000, temperature: float = 0.4) -> str:
    global last_latency
    client, model = await _get()
    t = time.time()
    r = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    last_latency = time.time() - t
    print(f"[llm] {model} {last_latency:.1f}s {r.usage.completion_tokens if r.usage else '?'} tok", file=sys.stderr)
    text = r.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


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
    print(asyncio.run(chat_json("You are terse.", 'Return {"ok": true, "ja": "<a Japanese greeting>"}')))
