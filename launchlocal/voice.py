"""Narration TTS on a Nosana GPU deployment (Kokoro-FastAPI), with a local CPU fallback.

See docs/nosana-voice.md for the deployment. CLI: python -m launchlocal.voice <run_id> [market]
"""
import os
import sys
import time
import wave
from pathlib import Path
from urllib.parse import urlparse

import httpx

from launchlocal import common

STATE = common.ROOT / "docs" / "nosana-voice.json"
RATE = 24000  # Kokoro outputs 24 kHz mono 16-bit PCM
MODELS = Path.home() / ".cache" / "kokoro-onnx"  # local fallback model files, outside the repo


def _state() -> dict:
    return common.read_json(STATE) if STATE.exists() else {}


def endpoint() -> str:
    common.load_env()
    return (os.environ.get("NOSANA_TTS_URL") or _state().get("endpoint", "")).rstrip("/")


def _write_wav(path: Path, pcm: bytes) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return len(pcm) / 2 / RATE


def _kokoro_lang(code: str | None) -> str | None:
    """Kokoro-FastAPI wants one letter ('j', 'a', 'b', ...); packs use 'ja', 'en-us'."""
    if not code:
        return None
    code = code.lower()
    return "b" if code in ("en-gb", "b") else "a" if code.startswith("en") else code[0]


def _nosana_pcm(text: str, v: dict) -> bytes:
    for attempt in range(3):  # a fresh node can answer 503 for a few seconds
        r = _post(text, v)
        if r.status_code < 500:
            break
        time.sleep(2)
    r.raise_for_status()
    if len(r.content) < RATE:  # under 0.5 s of audio means something went wrong
        raise RuntimeError(f"Nosana TTS returned only {len(r.content)} bytes")
    return r.content


def _post(text: str, v: dict) -> httpx.Response:
    return httpx.post(
        endpoint() + "/v1/audio/speech",
        json={
            "model": "kokoro",
            "input": text,
            "voice": v.get("voice", "jf_alpha"),
            "lang_code": _kokoro_lang(v.get("lang_code")),
            "speed": v.get("speed", 1.0),
            "response_format": "pcm",
            "stream": False,
        },
        timeout=60,
    )


_local = None


def _local_pcm(text: str, v: dict) -> bytes:
    """CPU fallback: kokoro-onnx; Japanese goes through misaki's phonemizer."""
    global _local
    import numpy as np
    from kokoro_onnx import Kokoro

    if _local is None:
        _local = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    lang = v.get("lang_code") or "en-us"
    if lang.startswith("j"):
        from misaki import ja

        phonemes, _ = ja.JAG2P()(text)
        samples, sr = _local.create(phonemes, voice=v.get("voice", "jf_alpha"), speed=v.get("speed", 1.0), is_phonemes=True)
    else:
        samples, sr = _local.create(text, voice=v.get("voice", "af_heart"), speed=v.get("speed", 1.0), lang="en-us")
    assert sr == RATE, sr
    return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()


def synthesize(text: str, out_path: Path, pack: dict) -> float:
    """Write narration WAV to out_path, return its duration in seconds. Raises if both paths fail."""
    v = pack.get("voice", {})
    try:
        pcm = _nosana_pcm(text, v)
        synthesize.backend = "nosana"
    except Exception as e:
        synthesize.error = f"{type(e).__name__}: {e}"[:300]
        pcm = _local_pcm(text, v)
        synthesize.backend = "local"
    return _write_wav(Path(out_path), pcm)


synthesize.backend = None
synthesize.error = None


def voice_scenes(run_dir: Path, pack: dict) -> None:
    run_dir = Path(run_dir)
    script_path = run_dir / "script.json"
    script = common.read_json(script_path)
    st = _state()
    host = urlparse(endpoint()).hostname
    where = {"deployment_id": st.get("deployment_id"), "endpoint_host": host, "gpu": st.get("market_name")}
    v = pack.get("voice", {})
    common.emit(run_dir, "voice", "start", f"Voicing {len(script['scenes'])} scenes with Kokoro ({v.get('voice')}) on a Nosana GPU", **where)
    warned = False
    for scene in script["scenes"]:
        text = scene.get("narration_local") or scene.get("narration_en") or ""
        rel = f"audio/{scene['id']}.wav"
        t0 = time.time()
        secs = synthesize(text, run_dir / rel, pack)
        took = round(time.time() - t0, 2)
        if synthesize.backend == "local" and not warned:
            warned = True
            common.emit(run_dir, "voice", "log",
                        f"Nosana TTS endpoint failed ({synthesize.error}); using the LOCAL CPU fallback (kokoro-onnx), not Nosana",
                        fallback=True, **where)
        scene["audio"] = rel
        scene["duration_s"] = round(secs + 0.6, 2)
        common.emit(run_dir, "voice", "progress", f"{scene['id']}: {secs:.1f}s of audio in {took}s",
                    scene_id=scene["id"], audio_s=round(secs, 2), synth_s=took, backend=synthesize.backend, **where)
        common.emit(run_dir, "voice", "artifact", rel, path=rel)
    common.write_json(script_path, script)
    common.emit(run_dir, "voice", "done", "Narration ready", total_s=round(sum(s["duration_s"] for s in script["scenes"]), 2), **where)


if __name__ == "__main__":
    common.load_env()
    run_id = sys.argv[1]
    market = sys.argv[2] if len(sys.argv) > 2 else common.read_json(common.run_dir(run_id) / "script.json").get("market", "ja-JP")
    voice_scenes(common.run_dir(run_id), common.load_pack(market))
