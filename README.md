# LaunchLocal

Paste a URL. Launch like a local. LaunchLocal takes a product URL and a target market, and returns a launch video in the local language plus an interactive brief where every claim opens its source.

![LaunchLocal architecture. A product URL and a market pack enter the AgentField control plane, which runs seven stages as separate nodes: research with Tavily and Nosana hosted Qwen, script with Nosana hosted Qwen, voice on a Nosana GPU deployment, a locally built baseline composition, restyling with CodeAF, rendering in a Daytona sandbox, and a buyer gate on Nosana hosted Qwen. A rejected cut loops back to the script as cut 2. The output is a launch video and an interactive brief.](site/architecture.svg)

- Demo (recorded runs replayed in the browser, labelled as cached): https://wei.github.io/launchlocal/
- Slides: https://wei.github.io/launchlocal/slides/
- Submission answers: [`docs/SUBMISSION.md`](docs/SUBMISSION.md)

## How it works

1. **Input.** You paste a product URL and pick a market. Japan (`ja-JP`) is the default. The reverse pack (`en-US`) launches a Japanese product globally in English.
2. **Research.** 12 agents run in parallel with Tavily: 5 read the official site (brand, product, pricing, customers, docs) and 7 search the target market using the areas and queries in the market pack. Nosana hosted Qwen turns the pages into facts. Each fact keeps its source URL.
3. **Script.** Nosana hosted Qwen writes a four-scene script (hook, product, proof, call to action) in the local language, plus a design brief. A sentence stays only if it cites a `fact_id` that exists in `facts.json`.
4. **Voice.** A Kokoro voice model on a Nosana GPU deployment narrates each scene.
5. **Compose.** Local code builds a baseline Hyperframes HTML composition from the script, the brand profile and the audio.
6. **Code.** CodeAF, run headless on an Ollama Cloud model, writes `theme.css`: a stylesheet that makes the video look like the official site, adapted to the market's style rules. It starts as soon as the brand profile exists and runs beside research, script and voice, so it does not add to the wait. The theme is used only if it passes the checks and the Hyperframes lint.
7. **Render.** A Daytona sandbox renders the composition to MP4 with headless Chrome and FFmpeg, and serves the result.
8. **Buyer gate.** A local buyer persona from the market pack scores the script of each cut while it is voiced and rendered. Three verdicts: `approve`; `reject`, when an unused sourced fact would fix the concern, in which case the script is revised and cut 2 is voiced and rendered; and `approve_with_gaps`, when the video already uses the evidence that exists and the rest is for the vendor to provide. The gaps are listed in the brief.
9. **Output.** The launch video and an interactive brief. Clicking a claim opens its source.

AgentField runs steps 2 to 8. Each stage is its own node in the workflow graph.

```mermaid
flowchart LR
  URL[Product URL] --> R
  PACK[Market pack JSON] -.-> R
  PACK -.-> S
  PACK -.-> V
  PACK -.-> G
  subgraph AF[AgentField control plane: one node per stage]
    R[Research: 12 agents<br/>Tavily + Nosana Qwen] --> S[Script<br/>Nosana Qwen]
    S --> V[Voice<br/>Nosana GPU, Kokoro]
    V --> C[Compose<br/>local code, Hyperframes]
    R -. brand profile .-> K[Code: brand theme<br/>CodeAF on Ollama Cloud]
    K -. theme.css .-> C
    C --> D[Render<br/>Daytona sandbox]
    S --> G{Buyer gate<br/>Nosana Qwen}
    G -- reject: cut 2 --> S
  end
  D --> OUT[Launch video + interactive brief]
  G -- approve, or approve with gaps --> OUT
```

## Innovation

- The video is reviewed by an agent that plays the local buyer, not by the author. For Japan the persona is the head of IT at a large enterprise. It scores four questions from the market pack; 0.7 is the pass mark (`buyer_gate` in [`launchlocal/script.py`](launchlocal/script.py)). The gate separates what the video can fix from what only the vendor can fix: missing local proof with no fact to cite becomes a listed gap, not an endless rejection.
- A rejection changes the product. The gate's reasons go to `revise_script`, and the pipeline produces cut 2 (`_flow` in [`launchlocal/agents.py`](launchlocal/agents.py)).
- A coding agent styles the video. CodeAF writes the theme stylesheet in a scratch copy of the composition, and the theme is applied only if it is CSS-only, has no network dependencies, hides nothing and passes the Hyperframes lint (`build_theme` and `theme_passes_lint` in [`launchlocal/coder.py`](launchlocal/coder.py)).

## Real-World Impact

- The input is one URL. No brand guide, script or footage is needed. The brand colors, logo and images are read from the official site (`run_research` in [`launchlocal/research.py`](launchlocal/research.py)).
- Every sentence in the video carries a `fact_id` from `facts.json`. Unsourced sentences are dropped, and numbers must appear in the cited source (`enforce` and `_numbers_ok` in [`launchlocal/script.py`](launchlocal/script.py)).
- The brief lets a reviewer check each claim against its source before the video is used. A measured run (tavily.com for Japan, 2026-11-14) produced 43 sourced facts and took 101 seconds from URL to video. A run where the buyer gate rejects cut 1 takes about 160 seconds for both cuts.

## Technical Execution

- Stages communicate only through files in `runs/<run_id>/` with the shapes in [`docs/CONTRACT.md`](docs/CONTRACT.md). Each stage can be run alone from the command line against a run directory.
- Every stage appends to `events.jsonl`. The waiting screen is a live view of that stream over server-sent events (`events` in [`launchlocal/server.py`](launchlocal/server.py)).
- Each external dependency has a named fallback that logs when it is used. See "What is live and what is a fallback".

## Partner Tech Usage

| Partner | Job | Why the product breaks without it | Where in the code |
|---------|-----|-----------------------------------|-------------------|
| AgentField | Control plane. Runs each pipeline stage as its own node and shows the workflow graph. | No record of which agent did what, and no graph of the two passes. | [`launchlocal/agents.py`](launchlocal/agents.py): `build_app` registers one reasoner per stage; `launch_flow` calls each with `app.call`; `launch` posts to the control plane's execute endpoint. |
| CodeAF | Coding harness. Runs headless on an Ollama Cloud model and writes the theme stylesheet that makes the video look like the official site. | The video keeps the baseline look and does not match the official site. | [`launchlocal/coder.py`](launchlocal/coder.py): `_run_codeaf` runs `codeaf exec`; `build_theme` writes `theme.css` in a scratch copy and checks it; `theme_passes_lint` lints the real composition with the theme applied. [`launchlocal/compose.py`](launchlocal/compose.py) appends the theme. |
| Tavily | Map, extract and search for 12 parallel research agents: 5 on the official site, 7 on the target market. | No sourced facts, so the script has nothing it is allowed to say. | [`launchlocal/research.py`](launchlocal/research.py): `run_research` and its inner `call`, which invokes `map`, `extract` and `search` on `AsyncTavilyClient`. |
| Nosana (hosted inference) | Qwen extracts facts, writes the script and the design brief, and plays the buyer gate. | No facts, no script and no review. | [`launchlocal/llm.py`](launchlocal/llm.py): `chat`, `chat_json`. [`launchlocal/script.py`](launchlocal/script.py): `write_script`, `_design_brief`, `buyer_gate`, `revise_script`. [`launchlocal/research.py`](launchlocal/research.py): `_Model.ask`. |
| Nosana (GPU deployment) | Runs the Kokoro voice model that narrates each scene. | The video has no narration. | [`launchlocal/voice.py`](launchlocal/voice.py): `_post` sends `POST /v1/audio/speech` to the deployment; `synthesize` and `voice_scenes` use it. Deployment: [`docs/nosana-voice.md`](docs/nosana-voice.md). |
| Daytona | Sandbox that renders the Hyperframes HTML composition to MP4 with headless Chrome and FFmpeg, and serves the result. | Nowhere isolated to run agent-written code, and no hosted video. | [`launchlocal/render.py`](launchlocal/render.py): `_sandbox` creates or reuses the sandbox; `_remote` runs the render commands; `render` uploads, renders and downloads. Setup: [`docs/daytona-render.md`](docs/daytona-render.md). |

## Open source we build on

| Area | Project | What it does here |
|------|---------|-------------------|
| Agents | AgentField | Agent control plane: one node per pipeline stage, workflow graph |
| Agents | CodeAF | Coding harness that writes the video's brand theme |
| Video | Hyperframes | HTML compositions rendered to MP4; also captures the official site's screenshots and design tokens |
| Video | GSAP | Animation timeline inside the composition |
| Video | FFmpeg, Chrome Headless Shell | Encoding and frame capture inside the Daytona sandbox |
| Voice | Kokoro | Text-to-speech model, Japanese and English voices |
| Voice | Kokoro-FastAPI | The server image that runs Kokoro on the Nosana GPU |
| Voice | kokoro-onnx, misaki | Local CPU fallback and Japanese phonemizer |
| Type | Noto Sans JP | Japanese font bundled with the composition |
| App | FastAPI, Uvicorn, httpx | Web app, server-sent events, HTTP calls |
| App | OpenAI Python SDK | Client for the OpenAI-compatible model endpoints (Nosana, Ollama Cloud) |
| App | tavily-python, Daytona Python SDK, AgentField Python SDK | Partner SDKs |
| App | uv, qrcode.js | Python environment; QR code on the brief |
| Inspiration | /brag agent skill (latent-spaces/brag), LaunchCut | Project-to-launch-video as an agent task; LaunchLocal adds live market research, localization, a buyer review and sourced claims |

Models: Kokoro for voice. Text generation uses Nosana hosted inference when its catalog lists a chat model, and otherwise DeepSeek V4.1 Flash on Ollama Cloud. CodeAF runs Kimi K2.7 Code on Ollama Cloud.

## Market packs

A market is one JSON file in [`packs/`](packs). The repo has [`packs/ja-JP.json`](packs/ja-JP.json) and [`packs/en-US.json`](packs/en-US.json). To add a market, copy one to `packs/<id>.json` and edit:

- `language`, `language_name`, `country`, `currency`
- `voice`: the Kokoro voice and language code
- `search`: country and local sites
- `research_areas`: the market research agents and their query templates
- `copy_rules`, `style_rules`, `cta_examples`: how the script and the video should read and look
- `buyer_persona`: who reviews the cut, what they care about, and the questions they score

The server lists every file in `packs/` (`GET /api/packs`), so the new market appears in the picker without code changes.

## Run it

Python 3.12 with uv. Put `TAVILY_API_KEY`, `DAYTONA_API_KEY`, `NOSANA_API_KEY` and `OLLAMA_API_KEY` in `.env` at the project root.

```sh
export PATH="$HOME/.agentfield/bin:$HOME/.codeaf/bin:$PATH"

# 1. AgentField control plane, port 8080
af server --open=false

# 2. LaunchLocal agent node, port 8001
.venv/bin/python -m launchlocal.agents

# 3. Web app, port 8787
.venv/bin/python -m launchlocal.server
```

Open http://127.0.0.1:8787, paste a URL and pick a market. The workflow graph is at http://localhost:8080/ui/ under Workflows.

Start a run without the web app:

```sh
curl -s -X POST http://localhost:8080/api/v1/execute/async/launchlocal.launch \
  -H 'Content-Type: application/json' \
  -d '{"input": {"url": "https://www.daytona.io", "market": "ja-JP", "run_id": "demo-1"}}'
```

Run single stages against a run directory:

```sh
.venv/bin/python -m launchlocal.voice <run_id> [market]
.venv/bin/python -m launchlocal.compose <run_id>
.venv/bin/python -m launchlocal.coder <run_id> [market] --theme
.venv/bin/python -m launchlocal.render <run_id>
```

Install notes for AgentField and CodeAF are in [`docs/agentfield-codeaf.md`](docs/agentfield-codeaf.md).

## What is live and what is a fallback

Live path: Tavily, Nosana hosted inference, the Nosana GPU voice deployment, CodeAF, Daytona and AgentField are all called during a run. Each fallback below writes a `log` event to `events.jsonl` when it is used.

| Fallback | When it is used | What happens |
|----------|-----------------|--------------|
| Language model chain | Nosana's hosted catalog lists no chat model, or a call fails | `llm.py` tries Nosana hosted inference, then the project's own Nosana GPU deployment when `docs/nosana-llm.json` exists, then Ollama Cloud. A failing provider is skipped for 90 seconds. Each run logs which provider served it, with `fallback: true` when it was not the first. This is not hypothetical: the hosted Qwen model left the catalog at 15:52 JST on the build day. |
| Local voice | The Nosana voice endpoint fails | `voice.py` runs the same Kokoro model on the local CPU and logs `fallback: true`. |
| Local render | `LAUNCHLOCAL_RENDER=local` is set | `render.py` renders with the same pinned Hyperframes CLI on the local machine. `render.json` has `preview_url: null` and `sandbox_id: null`. It is never chosen silently. |
| Baseline look | CodeAF fails or times out, its theme uses the network or hides elements, or the composition fails lint with the theme | `coder.py` sets the theme aside and logs `baseline look kept: <reason>`. The video renders with the baseline stylesheet and the run continues. |
| Pipeline without AgentField | The control plane or the agent node is unreachable | `launch` in `agents.py` runs the same stages in process with `run_pipeline` and logs it. |
| Cached-run replay | A recorded run is opened with `?replay=1` | The server replays the recorded `events.jsonl`. The page shows a "CACHED RUN" badge. |

## Limits

- The source check confirms that each sentence cites an existing fact and that its numbers appear in the source. It does not check that the source fully supports the wording.
- The buyer gate allows one revision. Cut 2 is final whether or not it is approved.
- The video has four scenes. Two market packs exist: `ja-JP` and `en-US`.
- The Nosana voice deployment has a job timeout and must be recreated after it ends. The Daytona sandbox is kept warm and stays billable until stopped.
- The Daytona preview URL shows a Daytona warning page in phone browsers. The MP4 is also downloaded to the run directory and served by the web app.
- The AgentField control plane runs locally in this build.
