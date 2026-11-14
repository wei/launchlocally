"""Export finished runs as a static site (GitHub Pages): site/demo/<run_id>/ plus site/demo/index.html.

The exported page is the same run page, replaying the run's recorded events in the
browser, so it shows the CACHED RUN badge. Usage:
    python scripts/export_static.py <run_id> [<run_id> ...]
"""
import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from launchlocal import server  # noqa: E402  (reuses the live state builder)

SITE = ROOT / "site"
REPO = "https://github.com/wei/launchlocally"

# Replays events.jsonl client-side with the same interface the page expects from EventSource.
SHIM = """<script>
window.LL_STATIC = true;
class StaticES {
  constructor() { this.h = {}; this.closed = false; this.run(); }
  addEventListener(n, f) { this.h[n] = f; }
  close() { this.closed = true; }
  async run() {
    const speed = +(new URLSearchParams(location.search).get('speed') || 4);
    const lines = (await (await fetch('events.jsonl')).text()).split('\\n').filter(Boolean);
    let prev = null;
    for (const line of lines) {
      if (this.closed) return;
      let ts = null; try { ts = JSON.parse(line).ts; } catch (e) {}
      if (prev !== null && ts !== null) await new Promise(r => setTimeout(r, Math.min(Math.max(ts - prev, 0), 8) / speed * 1000));
      if (ts !== null) prev = ts;
      if (this.onmessage) this.onmessage({data: line});
    }
    if (this.h.end) this.h.end({});
  }
}
</script>
"""


def export(run_id: str) -> dict:
    src = ROOT / "runs" / run_id
    out = SITE / "demo" / run_id
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    state = server.state(run_id)
    state["public_base"] = ""
    (out / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    for name in ("events.jsonl", "video.mp4", "video.cut1.mp4", "poster.png"):
        if (src / name).exists():
            shutil.copy2(src / name, out / name)
    for folder in ("assets", "audio"):
        if (src / folder).is_dir():
            shutil.copytree(src / folder, out / folder, ignore=shutil.ignore_patterns("capture"))

    page = (ROOT / "web" / "run.html").read_text(encoding="utf-8")
    swaps = [  # each must match exactly once, so a change to run.html fails loudly here
        ("const runId = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop());", f"const runId = {json.dumps(run_id)};"),
        ("const replay = qs.get('replay') === '1', speed = qs.get('speed') || '1';", "const replay = true, speed = qs.get('speed') || '4';"),
        ("await fetch(`/api/runs/${encodeURIComponent(runId)}/state`)", "await fetch('state.json')"),
        ("new EventSource(`/api/runs/${encodeURIComponent(runId)}/events` + (replay ? `?replay=1&speed=${encodeURIComponent(speed)}` : ''))", "new StaticES()"),
        ("(S.public_base || location.origin) + '/run/' + encodeURIComponent(runId)", "location.href.split('?')[0]"),
        ('<a class="logo" href="/"', '<a class="logo" href="../"'),  # on the static site the logo goes to the recorded-runs index
    ]
    for old, new in swaps:
        assert page.count(old) == 1, f"run.html changed, expected exactly one: {old[:60]}"
        page = page.replace(old, new)
    page = page.replace("`/runs/${encodeURIComponent(runId)}/", "`./")
    assert "/runs/" not in page and "/api/" not in page, "unpatched server path left in static page"
    assert 'href="/' not in page and "href='/" not in page, "root-relative link left in static page (404 under /launchlocally/)"
    page = page.replace("<script>", SHIM + "<script>", 1)
    (out / "index.html").write_text(page, encoding="utf-8")
    brand, inp = state.get("brand") or {}, state.get("input") or {}
    return {"run_id": run_id, "product": brand.get("name", run_id), "url": inp.get("url", ""), "market": inp.get("market", ""),
            "facts": len(state.get("facts") or [])}


def index(entries: list[dict]) -> None:
    cards = "\n".join(
        f'<a class="card" href="{html.escape(e["run_id"])}/"><b>{html.escape(e["product"])}</b>'
        f'<span>{html.escape(e["url"])} to {html.escape(e["market"])}</span><span>{e["facts"]} sourced facts</span></a>'
        for e in entries)
    (SITE / "demo" / "index.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LaunchLocally recorded runs</title>
<style>
body{{margin:0;background:#0b0d10;color:#f2f4f7;font:18px/1.5 system-ui,-apple-system,"Noto Sans JP",sans-serif}}
main{{max-width:960px;margin:0 auto;padding:56px 20px}}
h1{{font-size:48px;margin:0}}h1 i{{font-style:normal;color:#2ecc71}}p{{color:#aab2bd;max-width:60ch}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin:28px 0}}
.card{{display:flex;flex-direction:column;gap:4px;padding:20px;border:1px solid #2a2f37;border-radius:12px;background:#14171c;color:inherit;text-decoration:none}}
.card:hover{{border-color:#2ecc71}}.card b{{font-size:24px}}.card span{{color:#aab2bd;font-size:15px}}
.links a{{color:#2ecc71;margin-right:20px}}img{{width:100%;border-radius:12px;margin-top:28px}}
.note{{font-size:15px}}
</style></head><body><main>
<h1>Launch<i>Locally</i> recorded runs</h1>
<p>Paste a URL. Launch like a local. Agents research a product and a target market, then write, voice and render a launch video in the local language and style, with an interactive brief where every claim opens its source.</p>
<p class="note">These are recorded runs replayed in your browser, so each page shows a CACHED RUN badge. The live app runs the same pipeline on demand.</p>
<div class="cards">
{cards}
</div>
<p class="links"><a href="../">LaunchLocally home</a><a href="../slides/">Slides</a><a href="{REPO}">GitHub repository</a></p>
<img src="../architecture.svg" alt="LaunchLocally architecture: AgentField runs research on Tavily, script and buyer gate on Nosana, voice on a Nosana GPU, CodeAF restyle, and render in a Daytona sandbox">
</main></body></html>
""", encoding="utf-8")


if __name__ == "__main__":
    index([export(r) for r in sys.argv[1:]])
    print("exported", sys.argv[1:], "to", SITE)
