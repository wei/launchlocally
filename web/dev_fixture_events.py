"""Generate a realistic runs/fixture/events.jsonl for building the web page.

  .venv/bin/python web/dev_fixture_events.py            # events for runs/fixture
  .venv/bin/python web/dev_fixture_events.py --video    # also runs/fixture-video with a test MP4 (needs ffmpeg)

The fixture's facts are placeholders, and the first event says so on screen.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "runs" / "fixture"


def build() -> list[dict]:
    facts = json.loads((FIX / "facts.json").read_text())
    script = json.loads((FIX / "script.json").read_text())
    gate = json.loads((FIX / "gate.json").read_text())
    brand = json.loads((FIX / "brand.json").read_text())
    pack = json.loads((ROOT / "packs" / "ja-JP.json").read_text())
    scenes = [s["id"] for s in script["scenes"]]
    ev: list[tuple[float, str, str, str, dict]] = []

    def e(t, agent, kind, msg="", **data):
        ev.append((t, agent, kind, msg, data))

    e(0, "system", "start", "Launching daytona.io in ja-JP", url="https://www.daytona.io", market="ja-JP")
    e(0.2, "system", "log", "Fixture run: placeholder facts, not real research", fixture=True)

    # research: one lane per area, all in parallel
    scout = {
        "product": ["site:daytona.io product overview", "Daytona AI code sandbox features"],
        "docs": ["site:daytona.io/docs API sandbox", "Daytona SDK execute command files git"],
        "pricing": ["site:daytona.io pricing", "Daytona free trial credits"],
    }
    market = {
        a["id"]: [q.format(product=brand["name"], category="AIコード実行サンドボックス") for q in a["queries"]]
        for a in pack["research_areas"]
    }
    lanes = [(f"scout.{k}", k, v) for k, v in scout.items()] + [(f"market.{k}", k, v) for k, v in market.items()]
    end_research = 0.0
    for i, (agent, area, queries) in enumerate(lanes):
        t = 0.6 + i * 0.35
        e(t, agent, "start", f"Researching {area.replace('_', ' ')}")
        for j, q in enumerate(queries):
            t += 1.6 + (i % 3) * 0.5
            e(t, agent, "query", q, query=q)
            t += 1.2 + (j + i) % 3 * 0.6
            urls = [f"https://example.com/fixture-{area}-{j}-{n}" for n in range(3 + (i + j) % 3)]
            e(t, agent, "log", f"{len(urls)} results", urls=urls)
        for f in [f for f in facts if f["area"] == area]:
            t += 1.1
            e(t, agent, "fact", f["claim_en"], **f)
        t += 0.8
        e(t, agent, "done", f"{area.replace('_', ' ')} done")
        end_research = max(end_research, t)
    e(3.0, "scout.product", "artifact", "Brand profile extracted from the official site", path="brand.json")
    t = end_research + 0.6
    e(t, "system", "artifact", f"{len(facts)} sourced facts", path="facts.json")

    def pipeline(t, cut):
        if cut == 1:
            t += 0.8; e(t, "strategist", "start", "Writing the launch script on Nosana hosted Qwen")
            t += 3.5; e(t, "strategist", "log", "Dropped 2 lines with no fact_id")
            for sc in script["scenes"]:  # same shape script.py emits
                t += 0.7; e(t, "strategist", "progress", sc["headline_local"], scene=sc["id"], role=sc["role"], headline_en=sc["headline_en"], fact_ids=sc["fact_ids"])
            t += 1.0; e(t, "strategist", "artifact", "Script: 4 scenes, every line sourced", path="script.json", cut=cut)
            t += 1.0; e(t, "art_director", "log", "Design brief: high density, Noto Sans JP, calm motion")
            t += 0.6; e(t, "art_director", "done", "Design brief ready")
        else:
            t += 1.0; e(t, "strategist", "start", "Revising scene s3 from the buyer's objections", cut=cut)
            t += 3.0; e(t, "strategist", "artifact", "Script revised: added f04 and f05 to s3", path="script.json", cut=cut)
        t += 0.6; e(t, "voice", "start", "Nosana GPU: kokoro voice jf_alpha", cut=cut)
        for s in scenes if cut == 1 else ["s3"]:
            t += 0.5; e(t, "voice", "progress", f"Synthesizing {s}", scene=s, status="voicing")
            t += 1.6; e(t, "voice", "artifact", f"{s}: 5.0 s of audio", path=f"audio/{s}.wav", scene=s, status="voiced", duration_s=5.0)
        t += 0.4; e(t, "voice", "done", "Narration ready")
        t += 0.8; e(t, "compose", "start", "Building the baseline Hyperframes composition")
        t += 1.6; e(t, "compose", "artifact", "Baseline composition written", path="composition/index.html")
        t += 0.6; e(t, "coder", "start", "CodeAF restyling the composition to the brand and design brief", cut=cut)
        for msg in ["edit composition/styles.css: brand palette #2ecc71 on #0a0a0a",
                    "edit composition/scenes/s2.html: stagger proof points",
                    "edit composition/scenes/s3.html: two-column comparison with source chips",
                    "check: composition lints clean, 4 scenes, 20.0 s"]:
            t += 1.5; e(t, "coder", "log", msg)
        t += 0.6; e(t, "coder", "done", "Restyle kept (checks passed)")
        t += 0.6; e(t, "renderer", "start", "Creating Daytona sandbox", cut=cut)
        t += 1.8; e(t, "renderer", "log", "Sandbox ready", sandbox_id="fx-7c1e9a42-sandbox")
        t += 1.0; e(t, "renderer", "log", "Uploaded composition/ (14 files)")
        for fr in (120, 240, 360, 480, 600):
            t += 1.4; e(t, "renderer", "progress", f"hyperframes render: frame {fr}/600", frame=fr, total=600)
        t += 1.0; e(t, "renderer", "log", "ffmpeg mux: video + 4 narration tracks")
        t += 0.8; e(t, "renderer", "artifact", f"Cut {cut} rendered", path="video.mp4", cut=cut)
        t += 0.3; e(t, "renderer", "done", f"Cut {cut} ready in 11.4 s", render_seconds=11.4, cut=cut)
        rnd = gate["rounds"][cut - 1]
        t += 0.8; e(t, "gate", "start", f"{gate['persona']['title_en']} reviews cut {cut}", cut=cut)
        for qid in rnd["scores"]:
            t += 1.0; e(t, "gate", "progress", f"Scoring {qid}", question=qid)
        t += 1.0; e(t, "gate", "done", f"Cut {cut}: {rnd['verdict']}", **rnd)
        return t

    t = pipeline(t, 1)
    t = pipeline(t, 2)
    e(t + 1.0, "system", "done", "run complete", run_id="fixture", verdict="approve", cut=2)

    ev.sort(key=lambda x: x[0])
    base = time.time() - 3600
    return [{"ts": round(base + t, 3), "agent": a, "kind": k, "msg": m, "data": d} for t, a, k, m, d in ev]


def write(run: Path, events: list[dict]) -> None:
    with open(run / "events.jsonl", "w", encoding="utf-8") as f:
        for rec in events:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"{run / 'events.jsonl'}: {len(events)} events, {events[-1]['ts'] - events[0]['ts']:.0f} s")


if __name__ == "__main__":
    events = build()
    kinds = {x["kind"] for x in events}
    assert {"start", "query", "fact", "log", "progress", "artifact", "done"} <= kinds, kinds
    assert events[-1]["agent"] == "system" and events[-1]["kind"] == "done"
    write(FIX, events)
    if "--video" in sys.argv:
        # a copy of the fixture with a test MP4, to exercise the player and range requests
        vid = ROOT / "runs" / "fixture-video"
        vid.mkdir(exist_ok=True)
        for name in ("brand", "facts", "script", "gate"):
            shutil.copy(FIX / f"{name}.json", vid / f"{name}.json")
        (vid / "input.json").write_text(json.dumps({"run_id": "fixture-video", "url": "https://www.daytona.io", "market": "ja-JP"}))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                        "-f", "lavfi", "-i", "sine=frequency=330", "-t", "20", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(vid / "video.mp4")], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vid / "video.mp4"), "-frames:v", "1",
                        str(vid / "poster.png")], check=True)
        (vid / "render.json").write_text(json.dumps({"video": "video.mp4", "poster": "poster.png", "preview_url": "",
                                                      "sandbox_id": "fx-7c1e9a42-sandbox", "render_seconds": 11.4, "cut": 2}))
        write(vid, events)
