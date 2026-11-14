"""AgentField app "launchlocal": one reasoner per stage plus `launch`. See docs/agentfield-codeaf.md.

Start the agent node:  python -m launchlocal.agents            (needs `af server` on :8080)
Run without AgentField: python -m launchlocal.agents fallback <url> [market] [run_id]
"""
import asyncio
import os
import sys
import time
import uuid

import httpx

from . import common

NODE = "launchlocal"
SERVER = os.environ.get("AGENTFIELD_SERVER", "http://localhost:8080")
PORT = int(os.environ.get("LAUNCHLOCAL_AGENT_PORT", "8001"))
EXECUTE_URL = f"{SERVER}/api/v1/execute/async/{NODE}.launch"

# reasoner id -> (event agent, note shown in the workflow UI)
STAGES = {
    "scout_research": ("scout", "Scout: reading the official site, collecting sourced facts"),
    "market_research": ("market", "Market: local competitors, buyer concerns, conventions"),
    "strategist_script": ("strategist", "Strategist: writing the script and design brief"),
    "strategist_revise": ("strategist", "Strategist: applying the buyer gate's fixes"),
    "voice": ("voice", "Voice: synthesizing narration on Nosana"),
    "composer": ("art_director", "Composer: building the baseline Hyperframes composition"),
    "coder": ("coder", "Coder: CodeAF writes the brand theme (runs in parallel with script and voice)"),
    "renderer": ("renderer", "Renderer: rendering the video on Daytona"),
    "buyer_gate": ("gate", "Buyer gate: the local buyer persona reviews the cut"),
}
THEME_WAIT_S = float(os.environ.get("LAUNCHLOCAL_THEME_WAIT", "20"))  # how long a cut waits for the CodeAF theme


def _module(name: str, rd):
    """Lazy import of a stage module. With LAUNCHLOCAL_STUB=1 a missing module becomes a logged no-op."""
    import importlib
    if os.environ.get("LAUNCHLOCAL_STUB") == "all":  # graph smoke test: no stage does real work
        common.emit(rd, "system", "log", f"stub: launchlocal.{name} skipped (LAUNCHLOCAL_STUB=all)")
        return None
    try:
        return importlib.import_module(f"launchlocal.{name}")
    except ImportError as e:
        if os.environ.get("LAUNCHLOCAL_STUB") != "1":
            raise
        common.emit(rd, "system", "log", f"stub: launchlocal.{name} not importable ({e}); stage skipped")
        return None


async def run_stage(stage: str, run_id: str, market: str = "ja-JP", cut: int = 1) -> dict:
    """One pipeline stage. Shared by the AgentField reasoners and the no-AgentField fallback."""
    rd, pack = common.run_dir(run_id), common.load_pack(market)
    common.emit(rd, "system", "start", f"{stage} started", stage=stage, cut=cut)
    t0, out = time.time(), {}
    try:
        if stage == "scout_research":
            if m := _module("research", rd):
                # research.run_research fans out scout and market areas together
                await m.run_research(rd, common.read_json(rd / "input.json")["url"], pack)
        elif stage == "market_research":
            # shortcut: the contract exposes one run_research; this node reports its market facts.
            # Split when research.py exposes a separate market entry point.
            facts = common.read_json(rd / "facts.json") if (rd / "facts.json").exists() else []
            out = {"facts": len(facts), "market_facts": sum("market" in str(f.get("area", f.get("agent", ""))) for f in facts)}
        elif stage == "strategist_script":
            if m := _module("script", rd):
                await m.write_script(rd, pack)
        elif stage == "strategist_revise":
            if m := _module("script", rd):
                await m.revise_script(rd, pack, common.read_json(rd / "gate.json")["rounds"][-1])
        elif stage == "voice":
            if m := _module("voice", rd):
                await asyncio.to_thread(m.voice_scenes, rd, pack)
        elif stage == "composer":
            if m := _module("compose", rd):
                out = {"composition": str(await asyncio.to_thread(m.build_baseline, rd, pack))}
                if (rd / "theme.css").exists():  # CodeAF's theme was appended: lint it, drop it if it breaks the composition
                    from . import coder
                    if not await asyncio.to_thread(coder.theme_passes_lint, rd):
                        await asyncio.to_thread(m.build_baseline, rd, pack)
                out["themed"] = (rd / "theme.css").exists()
        elif stage == "coder":
            if m := _module("coder", rd):
                out = await asyncio.to_thread(m.build_theme, rd, pack)
        elif stage == "renderer":
            if m := _module("render", rd):
                out = await asyncio.to_thread(m.render, rd, cut)
        elif stage == "buyer_gate":
            if m := _module("script", rd):
                out = await m.buyer_gate(rd, pack, cut)
            else:  # stub gate rejects cut 1 so the revise loop is exercised
                out = {"cut": cut, "verdict": "reject" if cut == 1 else "approve", "stub": True}
        else:
            raise ValueError(f"unknown stage {stage}")
    except Exception as e:
        common.emit(rd, "system", "error", f"{stage} failed: {e}"[:400], stage=stage, cut=cut)
        raise
    out = {"stage": stage, "run_id": run_id, "cut": cut, "seconds": round(time.time() - t0, 1), **(out or {})}
    common.emit(rd, "system", "done", f"{stage} done in {out['seconds']}s", stage=stage, cut=cut)
    return out


async def _flow(run_id: str, market: str, step) -> dict:
    """research -> [CodeAF theme in parallel] -> script -> (buyer gate | voice -> compose -> render), one revise pass on reject."""
    rd = common.run_dir(run_id)

    async def theme():
        try:
            for _ in range(120):  # CodeAF needs only brand.json, which research writes within its first seconds
                if (rd / "brand.json").exists():
                    break
                await asyncio.sleep(0.5)
            return await step("coder", 1)
        except Exception as e:  # the theme is cosmetic: the baseline look is still there
            common.emit(rd, "system", "log", f"coder stage failed, baseline look kept: {e}"[:300])

    async def produce(cut: int) -> bool:
        """voice -> compose -> render. True when CodeAF's theme was in this render."""
        await step("voice", cut)
        if not theme_task.done():
            await asyncio.wait([theme_task], timeout=THEME_WAIT_S)
        themed = bool((await step("composer", cut) or {}).get("themed"))
        await step("renderer", cut)
        return themed

    theme_task = asyncio.ensure_future(theme())  # runs beside research, script and voice
    await step("scout_research", 1)
    await step("market_research", 1)
    gate, themed, cut = {}, False, 1
    for cut in (1, 2):
        await step("strategist_script" if cut == 1 else "strategist_revise", cut)
        # the gate reviews the script, so it runs while the cut is voiced and rendered
        gate, themed = await asyncio.gather(step("buyer_gate", cut), produce(cut))
        gate = gate or {}
        if gate.get("verdict") != "reject":
            break
    if not themed:
        if not theme_task.done():
            common.emit(rd, "system", "log", "cut rendered with the baseline look; waiting for CodeAF's theme to re-render")
        await theme_task
        if (rd / "theme.css").exists() and (await step("composer", cut) or {}).get("themed"):
            await step("renderer", cut)
    common.emit(rd, "system", "done", "run complete", run_id=run_id, verdict=gate.get("verdict"), cut=cut)
    return {"run_id": run_id, "verdict": gate.get("verdict"), "cut": cut}


def _init_run(url: str, market: str, run_id: str | None) -> str:
    run_id = run_id or time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    rd = common.run_dir(run_id)
    if not (rd / "input.json").exists():
        common.write_json(rd / "input.json", {"run_id": run_id, "url": url, "market": market})
    return run_id


def run_pipeline(url: str, market: str = "ja-JP", run_id: str | None = None) -> str:
    """Stage fallback: the same stages in the same order, without AgentField. Blocks until done."""
    common.load_env()
    run_id = _init_run(url, market, run_id)
    common.emit(common.run_dir(run_id), "system", "log", "fallback: pipeline running without AgentField")
    asyncio.run(_flow(run_id, market, lambda stage, cut: run_stage(stage, run_id, market, cut)))
    return run_id


async def launch(url: str, market: str = "ja-JP", run_id: str | None = None) -> str:
    """Trigger the `launch` reasoner on the AgentField control plane; returns the run id at once."""
    run_id = _init_run(url, market, run_id)
    rd = common.run_dir(run_id)
    common.emit(rd, "system", "start", f"launch {url} for {market}", url=url, market=market, run_id=run_id)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(EXECUTE_URL, json={"input": {"url": url, "market": market, "run_id": run_id}})
            r.raise_for_status()
            body = r.json()
        common.emit(rd, "system", "log", "AgentField execution started",
                    execution_id=body.get("execution_id"), workflow_id=body.get("workflow_id") or body.get("run_id"),
                    ui=f"{SERVER}/ui/")
    except Exception as e:
        common.emit(rd, "system", "log", f"AgentField unavailable ({e}); running the fallback pipeline"[:300])
        asyncio.get_running_loop().run_in_executor(None, run_pipeline, url, market, run_id)
    return run_id


def build_app():
    """The AgentField node. Built lazily so importing `launch` in the web server needs no control plane."""
    from agentfield import Agent

    common.load_env()
    app = Agent(node_id=NODE, agentfield_server=SERVER, version="0.1.0",
                description="LaunchLocal: localized launch video pipeline")

    def register(stage: str):
        async def reasoner(run_id: str, market: str = "ja-JP", cut: int = 1) -> dict:
            app.note(f"{STAGES[stage][1]} (cut {cut})", tags=[stage, run_id])
            out = await run_stage(stage, run_id, market, cut)
            app.note(f"{stage} done in {out['seconds']}s", tags=[stage, run_id, "done"])
            return out

        reasoner.__name__ = stage
        app.reasoner(name=stage, description=STAGES[stage][1])(reasoner)

    for stage in STAGES:
        register(stage)

    @app.reasoner(name="launch", description="Run the whole LaunchLocal flow for one product URL and market")
    async def launch_flow(url: str, market: str = "ja-JP", run_id: str | None = None) -> dict:
        run_id = _init_run(url, market, run_id)
        app.note(f"LaunchLocal run {run_id}: {url} -> {market}", tags=["launch", run_id])

        async def step(stage: str, cut: int) -> dict:
            # app.call goes through the control plane, so each stage is its own node in the workflow graph
            return await app.call(f"{NODE}.{stage}", run_id=run_id, market=market, cut=cut)

        out = await _flow(run_id, market, step)
        app.note(f"run {run_id} complete: {out['verdict']} at cut {out['cut']}", tags=["launch", run_id, "done"])
        return out

    return app


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "fallback":
        print(run_pipeline(*sys.argv[2:5]))
    else:
        build_app().run(port=PORT)
