"""Regenerate a run from research saved by an earlier run: no Tavily calls.

    python scripts/rerun_cached.py <source_run_id> <new_run_id> [market]

Copies facts.json, brand.json, assets/ and the research events, then launches the pipeline
through AgentField. The new run logs "CACHED RESEARCH".
"""
import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from launchlocal import agents, common  # noqa: E402

src, new = common.RUNS / sys.argv[1], common.RUNS / sys.argv[2]
inp = common.read_json(src / "input.json")
market = sys.argv[3] if len(sys.argv) > 3 else inp["market"]
if new.exists():
    sys.exit(f"{new} already exists")
new.mkdir(parents=True)
for name in ("facts.json", "brand.json"):
    shutil.copy2(src / name, new / name)
shutil.copytree(src / "assets", new / "assets")
research = [line for line in (src / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if json.loads(line)["agent"].startswith(("scout.", "market."))]
(new / "research_events.jsonl").write_text("\n".join(research) + "\n", encoding="utf-8")
print(asyncio.run(agents.launch(inp["url"], market, sys.argv[2])))
