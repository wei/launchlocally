"""Shared helpers. See docs/CONTRACT.md."""
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
PACKS = ROOT / "packs"


def load_env() -> None:
    """Load KEY=VALUE lines from the project .env into os.environ (existing values win)."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic, so the web server never reads a half-written file


def load_pack(market: str = "ja-JP") -> dict:
    return read_json(PACKS / f"{market}.json")


def run_dir(run_id: str) -> Path:
    path = RUNS / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def emit(run_dir: Path, agent: str, kind: str, msg: str = "", **data) -> dict:
    """Append one progress event to runs/<id>/events.jsonl."""
    rec = {"ts": time.time(), "agent": agent, "kind": kind, "msg": msg, "data": data}
    with open(Path(run_dir) / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


if __name__ == "__main__":
    import tempfile

    d = Path(tempfile.mkdtemp())
    emit(d, "system", "start", "hello", n=1)
    write_json(d / "a.json", {"x": "日本語"})
    assert read_json(d / "a.json")["x"] == "日本語"
    assert json.loads((d / "events.jsonl").read_text())["data"]["n"] == 1
    print("ok")
