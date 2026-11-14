# LaunchLocally build contract

Paste a product URL, pick a target market. Agents research the product and the
market, then write, voice and render a launch video in the local language and
style, plus an interactive brief where every claim links to its source.
Default market: `ja-JP` (international company to Japan). Reverse: `en-US`.

Hackathon build. Deadline 17:30 JST today. Working beats complete.

## Layout and ownership

Each workstream edits ONLY its own files. Do not commit; the lead commits.

| Path | Owner | Purpose |
|------|-------|---------|
| `docs/CONTRACT.md`, `launchlocal/common.py`, `runs/fixture/` | lead | This contract, shared helpers, sample run |
| `launchlocal/voice.py`, `docs/nosana-voice.md` | A voice | Nosana GPU deployment for TTS, client |
| `launchlocal/compose.py`, `launchlocal/render.py`, `template/`, `docs/daytona-render.md` | B render | Baseline Hyperframes composition, Daytona render and hosting |
| `launchlocal/coder.py`, `launchlocal/agents.py`, `docs/agentfield-codeaf.md` | C agents | CodeAF wrapper, AgentField app that runs the pipeline |
| `launchlocal/research.py` | D research | Tavily scout and market research fan-out |
| `launchlocal/llm.py`, `launchlocal/script.py`, `packs/` | E script | Nosana hosted Qwen client, script, design brief, buyer gate, market packs |
| `launchlocal/server.py`, `web/` | F web | Controller API, waiting screen, interactive brief |

Environment: `.venv` (Python 3.12, uv). Run with
`/Users/wei/Documents/Projects/Personal/launchlocal/.venv/bin/python`.
Installed: tavily-python, daytona, openai, fastapi, uvicorn, httpx,
python-dotenv, agentfield. Need another package? `uv pip install --python
.venv/bin/python <pkg>` and name it in your final report.

Secrets: `.env` at the project root (a symlink). Variables: `TAVILY_API_KEY`,
`DAYTONA_API_KEY`, `NOSANA_API_KEY`, `OLLAMA_API_KEY`. Load with
`common.load_env()`. Never print, log or commit a key.

## Run directory: `runs/<run_id>/`

All stages communicate through files here. `runs/fixture/` is a hand-written
sample with the exact shapes. Its facts are placeholders, not real research.

| File | Written by | Shape |
|------|-----------|-------|
| `input.json` | server / agents | `{run_id, url, market}` |
| `events.jsonl` | everyone, via `common.emit` | one JSON object per line, see below |
| `brand.json` | research | brand profile from the official site |
| `assets/` | research | downloaded logo, images, screenshots referenced by `brand.json` |
| `facts.json` | research | list of sourced facts |
| `script.json` | script | scenes, narration, on-screen text, changes, design brief |
| `audio/<scene_id>.wav` | voice | narration per scene; voice also sets `duration_s` in `script.json` |
| `composition/` | compose, then coder | Hyperframes project |
| `video.mp4`, `poster.png` | render | final video and a still |
| `render.json` | render | `{video, poster, preview_url, sandbox_id, render_seconds, cut}` |
| `gate.json` | script | buyer gate rounds |

### events.jsonl

`common.emit(run_dir, agent, kind, msg, **data)` appends
`{"ts": float, "agent": str, "kind": str, "msg": str, "data": {}}`.

- `agent`: `system`, `scout.<area>`, `market.<area>`, `strategist`,
  `art_director`, `voice`, `coder`, `renderer`, `gate`.
- `kind`: `start`, `query` (data: `query`), `fact` (data: the fact object),
  `log`, `progress`, `artifact` (data: `path` relative to the run dir),
  `done`, `error`.
- Emit generously. The waiting screen is built from this stream and is the
  most watched part of the demo.

### Function signatures (import targets for the pipeline)

```python
# research.py   (Tavily)
async def run_research(run_dir: Path, url: str, pack: dict) -> None
    # writes brand.json, assets/, facts.json; fans out areas in parallel

# script.py     (Nosana hosted Qwen through llm.py)
async def write_script(run_dir: Path, pack: dict) -> None          # -> script.json
async def buyer_gate(run_dir: Path, pack: dict, cut: int) -> dict  # appends a round to gate.json, returns it
async def revise_script(run_dir: Path, pack: dict, round: dict) -> None  # applies the gate's fixes to script.json

# voice.py      (Nosana GPU deployment)
def synthesize(text: str, out_path: Path, pack: dict) -> float     # seconds of audio
def voice_scenes(run_dir: Path, pack: dict) -> None                # audio/*.wav, updates duration_s

# compose.py    (deterministic baseline)
def build_baseline(run_dir: Path, pack: dict) -> Path              # writes composition/ from script+brand+audio

# coder.py      (CodeAF)
def restyle_composition(run_dir: Path, pack: dict) -> dict         # CodeAF edits composition/ in place to match
                                                                   # brand + design brief; keeps baseline if checks fail

# render.py     (Daytona)
def render(run_dir: Path, cut: int = 1) -> dict                    # uploads composition/, renders, downloads video.mp4,
                                                                   # hosts it, writes render.json

# agents.py     (AgentField)
async def launch(url: str, market: str = "ja-JP", run_id: str | None = None) -> str
    # research -> script -> voice -> compose -> coder -> render -> gate
    # -> (reject: revise -> voice -> compose -> coder -> render -> gate) -> done
```

Until a module exists, import failures must not block you: test your part
against `runs/fixture/`.

### Rules that keep the demo honest

- A sentence enters the video only if it carries a `fact_id` that exists in
  `facts.json`. Unsourced lines are dropped, not invented.
- Numbers and prices are copied from sources, never generated.
- If something is served from cache or a fallback, emit a `log` event saying so.
