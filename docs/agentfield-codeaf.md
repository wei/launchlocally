# AgentField and CodeAF in LaunchLocal

AgentField orchestrates the pipeline (`launchlocal/agents.py`). CodeAF restyles
the video composition (`launchlocal/coder.py`).

## Installed

| Tool | Version | Path | How |
|------|---------|------|-----|
| AgentField control plane (`af`) | 0.1.145 | `~/.agentfield/bin/af` | `https://agentfield.ai/install.sh`, run with `--no-skill --no-tray` and `SKIP_PATH_CONFIG=1` |
| CodeAF (`codeaf`) | 0.8.2 | `~/.codeaf/bin/codeaf` | `https://agentfield.ai/get/codeaf`, run with `--no-modify-path --no-start` |
| `agentfield` Python SDK | 0.1.145 | `.venv` | already in the venv |

Neither installer edited the shell profile, so add the binaries to `PATH`:

```sh
export PATH="$HOME/.agentfield/bin:$HOME/.codeaf/bin:$PATH"
```

`coder.py` falls back to `~/.codeaf/bin/codeaf` when `codeaf` is not on `PATH`.

## Start

```sh
# 1. Control plane, port 8080 (local storage under ~/.agentfield)
af server --open=false

# 2. Agent node "launchlocal", port 8001 (LAUNCHLOCAL_AGENT_PORT overrides)
cd /Users/wei/Documents/Projects/Personal/launchlocal
.venv/bin/python -m launchlocal.agents
```

Running on wei-15 since 2026-11-14: `af server` PID 83151, agent PID 92006.
Stop them with `kill <pid>`.

| What | URL |
|------|-----|
| Control plane UI | http://localhost:8080/ui/ |
| Workflow graph for a run | http://localhost:8080/ui/ then Workflows, open the run (`run_...` id) |
| Workflow DAG as JSON | `GET http://localhost:8080/api/ui/v1/workflows/<workflow_id>/dag` |
| Registered nodes | `GET http://localhost:8080/api/v1/nodes` |
| Agent node | http://localhost:8001 |

## Execute endpoint

```sh
curl -s -X POST http://localhost:8080/api/v1/execute/async/launchlocal.launch \
  -H 'Content-Type: application/json' \
  -d '{"input": {"url": "https://www.daytona.io", "market": "ja-JP", "run_id": "demo-1"}}'
# -> {"execution_id": "exec_...", "run_id": "run_...", ...}   run_id here is the workflow id
```

`/api/v1/execute/launchlocal.launch` (no `async`) blocks until the run ends.
From Python, `await launchlocal.agents.launch(url, market, run_id)` posts to the
async endpoint and returns the LaunchLocal run id at once. The AgentField
execution and workflow ids land in `events.jsonl` as a `system` `log` event.

## Reasoners

`launch` calls each stage with `app.call("launchlocal.<stage>")`, so every stage
is its own node in the workflow graph, and each stage attaches `app.note` lines.

`scout_research`, `market_research`, `strategist_script`, `voice`, `composer`,
`coder`, `renderer`, `buyer_gate`, and `strategist_revise` for the second pass.
If the gate rejects cut 1 the flow runs revise, voice, composer, coder, renderer
and gate again with cut 2. A full two-pass run shows 15 nodes.

`research.run_research` is one function in the contract, so `scout_research`
runs it and `market_research` only reports fact counts from `facts.json`.

A coder failure does not stop the run: the baseline composition is rendered.

## Fallback without AgentField

```sh
.venv/bin/python -m launchlocal.agents fallback https://www.daytona.io ja-JP demo-1
```

`run_pipeline(url, market, run_id)` runs the same stages in process.
`launch()` uses it by itself when the control plane or agent is unreachable,
and emits a `log` event saying so.

Smoke test without real stages: start the agent with `LAUNCHLOCAL_STUB=all`.
Every stage becomes a logged no-op and the stub gate rejects cut 1, so the
graph shows both passes. `LAUNCHLOCAL_STUB=1` stubs only modules that fail to
import.

## CodeAF on Ollama Cloud

CodeAF speaks the OpenAI wire format to any base URL. `coder.py` sets, for the
subprocess only:

```sh
CODEAF_BASE_URL=https://ollama.com/v1
OPENAI_API_KEY=$OLLAMA_API_KEY      # read from .env, never written anywhere
# OPENROUTER_API_KEY is removed from the child env, because it would win
```

Model: `glm-5.3` (`LAUNCHLOCAL_CODEAF_MODEL` overrides). Other coding models on
Ollama Cloud on 2026-11-14: `deepseek-v4-pro:0813`, `kimi-k3.1-pro`,
`kimi-k2.7-code`, `minimax-m3`, and the `-flash` variants.

Headless command that `coder.py` runs (brief on stdin):

```sh
codeaf exec - --dir runs/<id>/composition --model glm-5.3 \
  --timeout 240s --max-turns 30 --json --debug
```

The child also gets `GIT_DIR=/nonexistent-launchlocal`. In testing CodeAF ran
`git commit` on its own edits in the project repo; with this, every git command
it tries fails. A restyle of the fixture took 92 s (one run failed lint after
175 s and the baseline was kept).

`--json` prints one result object at exit, not a stream. Live steps come from
`--debug`, which writes one file per model call to
`~/.codeaf/logs/trace/<run>/calls/`. `coder.py` tails that folder and emits a
`coder` `progress` event per tool call (`edit <file>`, `write <file>`, `$ <cmd>`).

Restyle on its own:

```sh
.venv/bin/python -m launchlocal.coder <run_id> [market]
```

It copies `composition/` to `composition.baseline/`, runs CodeAF, then keeps the
result only if all three hold: CodeAF exited ok, the `data-scene` /
`data-fact-id` attributes and visible text are identical to the baseline, and
`npx hyperframes lint` passes. Otherwise it restores the baseline and emits
`baseline kept: <reason>`.

## app.harness

The SDK ships a CodeAF harness provider (`app.harness(prompt, provider="codeaf",
cwd=...)`, which also runs `codeaf exec --json --dir`). The coder stage keeps
the direct subprocess because it needs the `--debug` trace for live events and
the baseline restore around the run.
