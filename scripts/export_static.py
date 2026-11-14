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
    rounds = (state.get("gate") or {}).get("rounds") or []
    pack = state.get("pack") or {}
    return {"run_id": run_id, "product": brand.get("name", run_id), "url": inp.get("url", ""), "market": pack.get("label") or inp.get("market", ""),
            "facts": len(state.get("facts") or []), "cuts": len(rounds), "verdict": (rounds[-1]["verdict"] if rounds else "").replace("_", " "),
            "poster": (out / "poster.png").exists()}


DEMO_URL = "https://wei.github.io/launchlocally/demo/"


def index(entries: list[dict]) -> None:
    """Recorded-runs index, styled with the homepage stylesheet, with a QR code to this page."""
    import segno  # pure-Python QR generator

    demo = SITE / "demo"
    demo.mkdir(parents=True, exist_ok=True)
    segno.make(DEMO_URL, error="m").save(str(demo / "qr.svg"), scale=4, border=2, dark="#1c1a17", light="#fffcf5")
    e_ = html.escape
    cards = "\n".join(
        f'''<a class="card top run" href="{e_(e["run_id"])}/">
        {f'<img src="{e_(e["run_id"])}/poster.png" alt="First frame of the {e_(e["product"])} launch video" loading="lazy">' if e["poster"] else ""}
        <h3>{e_(e["product"])}</h3>
        <p>{e_(e["url"].replace("https://", "").rstrip("/"))} for {e_(e["market"])}</p>
        <p class="meta">{e["facts"]} sourced facts · {e["cuts"]} cut{"" if e["cuts"] == 1 else "s"} · buyer gate: {e_(e["verdict"] or "not reviewed")}</p>
      </a>'''
        for e in entries)
    (demo / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recorded runs: LaunchLocally</title>
<meta name="description" content="Recorded LaunchLocally runs: launch videos and sourced briefs made from one product URL each.">
<meta name="theme-color" content="#c5361d">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="../styles.css">
<style>
.runs-head {{ display: flex; gap: 32px; align-items: flex-start; justify-content: space-between; margin-bottom: 36px; }}
.runs-head .lede {{ margin-bottom: 0; }}
.qr {{ flex: none; text-align: center; font-size: 13px; color: var(--muted); }}
.qr img {{ display: block; width: 132px; height: 132px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); margin-bottom: 6px; }}
.runs {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
.run {{ display: block; color: inherit; text-decoration: none; padding: 0 0 18px; overflow: hidden; }}
.run:hover {{ border-color: var(--primary); }}
.run img {{ display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-bottom: 1px solid var(--line); margin-bottom: 16px; }}
.run h3, .run p {{ margin: 0 22px; }}
.run h3 {{ font-family: var(--serif); font-size: 1.5rem; }}
.run p {{ margin-top: 4px; }}
.run .meta {{ font-size: 14px; margin-top: 10px; }}
@media (max-width: 640px) {{ .runs-head {{ flex-direction: column-reverse; }} }}
</style>
</head>
<body>

<header class="site-header">
  <div class="wrap">
    <a class="brand" href="../"><img src="../logo.svg" alt="LaunchLocally logo" width="268" height="48"></a>
    <nav aria-label="Main">
      <a href="../#how">How it works</a>
      <a href="./" aria-current="page">Recorded runs</a>
      <a href="../docs/">Docs</a>
      <a href="../pricing/">Pricing</a>
      <a href="../slides/">Slides</a>
      <a href="{REPO}">GitHub</a>
    </nav>
  </div>
</header>

<main>
<section class="page">
  <div class="wrap">
    <div class="runs-head">
      <div>
        <p class="kicker">Recorded runs</p>
        <h1>One URL in. A launch video and a sourced brief out.</h1>
        <p class="lede">Each card is a real run of the pipeline, replayed in your browser: the research, the script, the local buyer's review, the video and every claim's source. Open one and press play.</p>
      </div>
      <div class="qr"><img src="qr.svg" alt="QR code for {DEMO_URL}">Scan to open this page</div>
    </div>
    <div class="runs">
{cards}
    </div>
  </div>
</section>
</main>

<footer class="site-footer">
  <div class="wrap">
    <p><a href="../">LaunchLocally</a> · <a href="../slides/">Slides</a> · <a href="{REPO}">GitHub repository</a> · Built at the Agent Forge AI Hackathon Tokyo, 14 November 2026.</p>
  </div>
</footer>

</body>
</html>
""", encoding="utf-8")


if __name__ == "__main__":
    index([export(r) for r in sys.argv[1:]])
    print("exported", sys.argv[1:], "to", SITE)
