"""Strategist, art director and buyer gate. See docs/CONTRACT.md."""
import asyncio
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

from launchlocal import llm
from launchlocal.common import emit, load_pack, read_json, run_dir as get_run_dir, write_json

ROLES = ["hook", "product", "proof", "cta"]
PASS = 0.7


# ---------- enforcement (code, not prompt) ----------

def _narration_ok(text: str, pack: dict) -> bool:
    if pack["language"] == "ja":
        return len(text) <= 45
    return len(text.split()) <= 18


def _limit_text(pack: dict) -> str:
    return "at most 45 Japanese characters" if pack["language"] == "ja" else "at most 18 words"


def _numbers(text: str) -> set[str]:
    text = unicodedata.normalize("NFKC", text or "")
    return {n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,.]*", text)}


def _numbers_ok(text: str, cited: list[dict], brand: dict) -> bool:
    allowed = _numbers(" ".join(f.get("claim_en", "") + " " + f.get("claim_local", "") + " " + f.get("excerpt", "") for f in cited))
    allowed |= _numbers(brand.get("name", ""))  # product names like "Foo3"
    return _numbers(text) <= allowed


def _pick_fallback(facts: list[dict], role: str, used: set[str]) -> str | None:
    want = "product" if role in ("product", "cta") else "market"
    ranked = sorted(facts, key=lambda f: (f.get("scope") != want, f["id"] in used))
    return ranked[0]["id"] if ranked else None


def enforce(script: dict, facts: list[dict], brand: dict, pack: dict, rd: Path) -> list[dict]:
    """Drop unsourced items and unsupported numbers in place. Returns lines that break the length rule."""
    by_id = {f["id"]: f for f in facts}
    used: set[str] = set()
    long_lines = []
    for sc in script["scenes"]:
        items = []
        for it in sc.get("on_screen", []):
            fid = it.get("fact_id")
            if fid not in by_id:
                emit(rd, "strategist", "log", f"dropped on-screen item without a valid fact id: {it.get('text_en', '')}")
                continue
            if not _numbers_ok(f"{it.get('text_local', '')} {it.get('text_en', '')}", [by_id[fid]], brand):
                emit(rd, "strategist", "log", f"dropped on-screen item with a number not in {fid}: {it.get('text_en', '')}")
                continue
            items.append({"text_local": it.get("text_local", ""), "text_en": it.get("text_en", ""), "fact_id": fid})
        sc["on_screen"] = items
        ids = [i for i in dict.fromkeys(sc.get("fact_ids", []) + [it["fact_id"] for it in items]) if i in by_id]
        if not ids:
            fb = _pick_fallback(facts, sc["role"], used)
            ids = [fb] if fb else []
            emit(rd, "strategist", "log", f"{sc['id']} had no valid fact ids; attached {fb}")
        sc["fact_ids"] = ids
        used |= set(ids)
        cited = [by_id[i] for i in ids]
        for key in ("headline", "narration"):
            if not _numbers_ok(f"{sc.get(key + '_local', '')} {sc.get(key + '_en', '')}", cited, brand):
                # replace with the cited claim itself rather than keep an invented number
                emit(rd, "strategist", "log", f"{sc['id']} {key} had a number not in its facts; replaced with sourced claim")
                sc[key + "_local"], sc[key + "_en"] = cited[0]["claim_local"], cited[0]["claim_en"]
        if not _narration_ok(sc.get("narration_local", ""), pack):
            long_lines.append(sc)
    script["changes"] = [
        {**c, "fact_ids": [i for i in c.get("fact_ids", []) if i in by_id]}
        for c in script.get("changes", []) if any(i in by_id for i in c.get("fact_ids", []))
    ]
    return long_lines


async def _fix_length(script, facts, brand, pack, rd):
    long_lines = enforce(script, facts, brand, pack, rd)
    if not long_lines:
        return
    emit(rd, "strategist", "log", f"shortening {len(long_lines)} narration line(s) to {_limit_text(pack)}")
    req = [{"id": s["id"], "narration_local": s["narration_local"]} for s in long_lines]
    try:
        out = await llm.chat_json(
            f"You shorten {pack['language_name']} video narration. Keep the meaning and tone, keep any numbers exactly. "
            f"Each line must be {_limit_text(pack)}.",
            json.dumps(req, ensure_ascii=False) + '\nReturn [{"id": ..., "narration_local": ..., "narration_en": ...}].',
            800,
        )
        fixed = {o["id"]: o for o in out if isinstance(o, dict)}
    except Exception as e:  # keep going with a hard cut
        emit(rd, "strategist", "log", f"shorten call failed ({e}); hard-cutting")
        fixed = {}
    for s in long_lines:
        new = fixed.get(s["id"], {})
        if new.get("narration_local") and _narration_ok(new["narration_local"], pack):
            s["narration_local"] = new["narration_local"]
            s["narration_en"] = new.get("narration_en") or s["narration_en"]
        else:
            s["narration_local"] = _hard_cut(s["narration_local"], pack)
    enforce(script, facts, brand, pack, rd)  # shortened text could carry a new number


def _hard_cut(text: str, pack: dict) -> str:
    # shortcut: crude cut at the last clause mark, a real fix needs another model pass
    if pack["language"] != "ja":
        return " ".join(text.split()[:18]).rstrip(",;") + ("." if not text.endswith(".") else "")
    cut = text[:44]
    k = max(cut.rfind("、"), cut.rfind("。"))
    return (cut[:k] if k > 10 else cut) + "。"


# ---------- prompts ----------

def _facts_block(facts):
    return json.dumps(
        [{"id": f["id"], "scope": f.get("scope"), "area": f.get("area"), "claim_en": f["claim_en"],
          "claim_local": f.get("claim_local", ""), "source": f.get("source_title", "")} for f in facts],
        ensure_ascii=False, indent=1)


SCENE_SHAPE = """{
 "title_local": str, "title_en": str,
 "scenes": [ // exactly 4, ids s1..s4, roles hook, product, proof, cta in that order
  {"id": "s1", "role": "hook", "headline_local": str, "headline_en": str,
   "narration_local": str, "narration_en": str,
   "on_screen": [{"text_local": str, "text_en": str, "fact_id": str}],  // 1 to 3 items
   "fact_ids": [str], "visual": str /* English, what the scene shows */}
 ],
 "cta_local": str, "cta_en": str,
 "changes": [{"what_en": str, "what_local": str, "why_en": str, "fact_ids": [str]}]  // 2 to 4
}"""


def _strategist_system(pack, brand):
    return f"""You are a launch strategist adapting {brand.get('name')} for this market: {pack['direction']} ({pack['label']}).
Write a four-scene launch video script in {pack['language_name']}, with English versions of every text field.

Copy rules:
{chr(10).join('- ' + r for r in pack['copy_rules'])}
Style rules:
{chr(10).join('- ' + r for r in pack['style_rules'])}
Typical calls to action: {', '.join(pack['cta_examples'])}

Hard rules:
- Every on-screen item and every scene cites fact ids from the facts list. Never invent a fact, customer, number or price.
- A number or price may appear only if it is in the cited fact.
- Each narration_local line is {_limit_text(pack)}.
- Hook and proof scenes prefer facts with scope "market"; the product scene uses scope "product" facts.
- "changes" explains what you changed versus how the product presents itself at home, and why, citing facts.
- The buyer is: {pack['buyer_persona']['title_en']}. They care about: {'; '.join(pack['buyer_persona']['cares_about'])}."""


# ---------- stages ----------

async def _design_brief(rd, pack, brand, facts):
    emit(rd, "art_director", "start", "Combining the brand's look with local conventions")
    style_facts = [f for f in facts if f.get("area") == "style"] or facts[:3]
    try:
        brief = await llm.chat_json(
            "You are an art director. Write a design brief that a coding agent will use to restyle an HTML launch video "
            "(1920x1080, four scenes: headline, short supporting points, source chips, logo).",
            f"Brand: {json.dumps({k: brand.get(k) for k in ('name', 'colors', 'fonts', 'tone', 'tagline')}, ensure_ascii=False)}\n"
            f"Market fonts: {json.dumps(pack['fonts'])}\nMarket style rules: {json.dumps(pack['style_rules'], ensure_ascii=False)}\n"
            f"Sourced style facts: {_facts_block(style_facts)}\n"
            'Return {"density": "high"|"medium"|"low", "palette": str (name hex values from the brand), '
            '"typography": str (font families, weights, sizes in px), "motion": str (timing in ms, easing), '
            '"layout": str, "notes": [str] (4 to 6 concrete, checkable instructions)}. English.',
            1200,
        )
    except Exception as e:
        emit(rd, "art_director", "error", f"brief failed ({e}); using pack defaults")
        brief = {"density": "medium", "palette": "brand colors from brand.json",
                 "typography": f"{pack['fonts']['heading']} 700 headlines, {pack['fonts']['body']} 500 body",
                 "motion": "calm", "notes": pack["style_rules"]}
    emit(rd, "art_director", "done", brief.get("typography", ""), brief=brief)
    return brief


async def write_script(run_dir: Path, pack: dict) -> None:
    rd = Path(run_dir)
    brand, facts = read_json(rd / "brand.json"), read_json(rd / "facts.json")
    emit(rd, "strategist", "start", f"Writing a {pack['language_name']} launch script from {len(facts)} sourced facts")
    user = f"Brand profile:\n{json.dumps(brand, ensure_ascii=False)}\n\nFacts:\n{_facts_block(facts)}\n\nReturn JSON shaped:\n{SCENE_SHAPE}"
    draft, brief = await asyncio.gather(
        llm.chat_json(_strategist_system(pack, brand), user, 3000),
        _design_brief(rd, pack, brand, facts),
    )
    script = _assemble(draft, pack, brand)
    await _fix_length(script, facts, brand, pack, rd)
    script["design_brief"] = brief
    write_json(rd / "script.json", script)
    for sc in script["scenes"]:
        emit(rd, "strategist", "progress", sc["headline_local"], scene=sc["id"], role=sc["role"], headline_en=sc["headline_en"], fact_ids=sc["fact_ids"])
    emit(rd, "strategist", "artifact", "script.json", path="script.json")
    emit(rd, "strategist", "done", script["title_local"], title_en=script["title_en"])


def _assemble(draft: dict, pack: dict, brand: dict, old: dict | None = None) -> dict:
    scenes = (draft.get("scenes") or [])[:4]
    if len(scenes) != 4:
        raise ValueError(f"model returned {len(scenes)} scenes")
    out = []
    for i, sc in enumerate(scenes):
        sid = f"s{i + 1}"
        prev = next((s for s in (old or {}).get("scenes", []) if s["id"] == sid), {})
        out.append({
            "id": sid, "role": ROLES[i],
            **{k: str(sc.get(k) or prev.get(k) or "") for k in ("headline_local", "headline_en", "narration_local", "narration_en", "visual")},
            "on_screen": sc.get("on_screen") or [], "fact_ids": sc.get("fact_ids") or [],
            "duration_s": prev.get("duration_s", 5.0), "audio": f"audio/{sid}.wav",
        })
    base = old or {}
    return {
        "market": pack["id"], "product": brand.get("name", ""),
        "title_local": draft.get("title_local") or base.get("title_local", ""),
        "title_en": draft.get("title_en") or base.get("title_en", ""),
        "scenes": out,
        "cta_local": draft.get("cta_local") or base.get("cta_local") or pack["cta_examples"][0],
        "cta_en": draft.get("cta_en") or base.get("cta_en", ""),
        "cta_url": brand.get("url", ""),
        "changes": base.get("changes", []) + (draft.get("changes") or []),
        "design_brief": base.get("design_brief", {}),
    }


async def buyer_gate(run_dir: Path, pack: dict, cut: int) -> dict:
    rd = Path(run_dir)
    script, facts = read_json(rd / "script.json"), read_json(rd / "facts.json")
    p = pack["buyer_persona"]
    emit(rd, "gate", "start", f"{p['gate_name']}: {p['title_local']} reviews cut {cut}")
    used = {i for s in script["scenes"] for i in s["fact_ids"]}
    unused = [f for f in facts if f["id"] not in used]
    view = {k: script[k] for k in ("title_local", "cta_local")} | {
        "scenes": [{k: s[k] for k in ("id", "role", "headline_local", "narration_local", "on_screen", "fact_ids")} for s in script["scenes"]]}
    qids = [q["id"] for q in p["questions"]]
    res = await llm.chat_json(
        f"You are {p['title_en']} ({p['title_local']}), reviewing a vendor's launch video script written for you in {pack['language_name']}. "
        f"You care about: {'; '.join(p['cares_about'])}. You are strict and honest: score what is actually on screen and in the narration, "
        "not what the vendor might have. A claim counts as evidence only if it cites a fact. Unnatural or translated-sounding "
        f"{pack['language_name']} lowers the tone score. Score each question from 0 to 1; 0.7 means you would forward it internally. "
        "Do not inflate scores to be nice and do not lower them to look tough.",
        f"Questions:\n{json.dumps(p['questions'], ensure_ascii=False)}\n\nScript:\n{json.dumps(view, ensure_ascii=False, indent=1)}\n\n"
        f"Facts the script cites or could cite (unused ones are candidates for fixes):\nUSED: {sorted(used)}\n{_facts_block(facts)}\n\n"
        'Return {"scores": {' + ", ".join(f'"{q}": float' for q in qids) + '}, '
        f'"reasons": [{{"local": str ({pack["language_name"]}), "en": str}}] (1 to 3, your main concerns or praise), '
        '"fixes": [{"scene": "s1".."s4", "instruction_en": str, "fact_ids": [ids of UNUSED facts that address it]}] (empty if nothing to fix)}',
        1500,
    )
    scores = {q: max(0.0, min(1.0, float((res.get("scores") or {}).get(q, 0)))) for q in qids}
    verdict = "approve" if all(v >= PASS for v in scores.values()) else "reject"
    unused_ids = {f["id"] for f in unused}
    fixes = [] if verdict == "approve" else [
        {"scene": f.get("scene"), "instruction_en": f.get("instruction_en", ""), "fact_ids": [i for i in f.get("fact_ids", []) if i in unused_ids]}
        for f in res.get("fixes") or [] if f.get("scene") in {s["id"] for s in script["scenes"]}]
    rnd = {"cut": cut, "verdict": verdict, "scores": scores,
           "reasons": [{"local": r.get("local", ""), "en": r.get("en", "")} for r in res.get("reasons") or []], "fixes": fixes}
    emit(rd, "gate", "progress", " ".join(f"{k} {v:.2f}" for k, v in scores.items()), scores=scores)
    gpath = rd / "gate.json"
    gate = read_json(gpath) if gpath.exists() else {}
    if gate.get("fixture") or "rounds" not in gate:
        gate = {"persona": {k: p[k] for k in ("title_local", "title_en", "gate_name")}, "rounds": []}
    gate["rounds"] = [r for r in gate["rounds"] if r["cut"] != cut] + [rnd]
    write_json(gpath, gate)
    emit(rd, "gate", "artifact", "gate.json", path="gate.json")
    emit(rd, "gate", "done", verdict, verdict=verdict, reasons=rnd["reasons"])
    return rnd


async def revise_script(run_dir: Path, pack: dict, round: dict) -> None:
    rd = Path(run_dir)
    old, brand, facts = read_json(rd / "script.json"), read_json(rd / "brand.json"), read_json(rd / "facts.json")
    emit(rd, "strategist", "start", f"Revising after the buyer's review of cut {round['cut']}")
    p = pack["buyer_persona"]
    current = {k: old[k] for k in ("title_local", "title_en", "cta_local", "cta_en", "scenes")}
    draft = await llm.chat_json(
        _strategist_system(pack, brand),
        f"Facts:\n{_facts_block(facts)}\n\nCurrent script:\n{json.dumps(current, ensure_ascii=False)}\n\n"
        f"The buyer ({p['title_en']}) rejected it. Reasons: {json.dumps(round['reasons'], ensure_ascii=False)}\n"
        f"Requested fixes: {json.dumps(round['fixes'], ensure_ascii=False)}\n\n"
        "Apply the fixes using the suggested facts. Keep scene ids and roles. Change only what the fixes need. "
        "In \"changes\" list only the new changes, each saying what the buyer asked for and what you did.\n"
        f"Return JSON shaped:\n{SCENE_SHAPE}",
        3000,
    )
    script = _assemble(draft, pack, brand, old)
    await _fix_length(script, facts, brand, pack, rd)
    write_json(rd / "script.json", script)
    for sc in script["scenes"]:
        emit(rd, "strategist", "progress", sc["headline_local"], scene=sc["id"], role=sc["role"], headline_en=sc["headline_en"], fact_ids=sc["fact_ids"])
    emit(rd, "strategist", "artifact", "script.json", path="script.json")
    emit(rd, "strategist", "done", f"Cut {round['cut'] + 1} script ready")


async def _main(run_id: str, market: str):
    rd, pack = get_run_dir(run_id), load_pack(market)
    t = time.time()
    await write_script(rd, pack)
    print(f"write_script {time.time() - t:.1f}s", file=sys.stderr)
    t = time.time()
    rnd = await buyer_gate(rd, pack, 1)
    print(f"gate cut 1 {time.time() - t:.1f}s -> {rnd['verdict']} {rnd['scores']}", file=sys.stderr)
    if rnd["verdict"] == "reject":
        t = time.time()
        await revise_script(rd, pack, rnd)
        print(f"revise {time.time() - t:.1f}s", file=sys.stderr)
        t = time.time()
        rnd = await buyer_gate(rd, pack, 2)
        print(f"gate cut 2 {time.time() - t:.1f}s -> {rnd['verdict']} {rnd['scores']}", file=sys.stderr)


if __name__ == "__main__":
    assert _numbers("料金は１，０００円") == {"1000"}
    asyncio.run(_main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "ja-JP"))
