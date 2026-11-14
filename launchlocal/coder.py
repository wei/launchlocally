"""CodeAF restyles the Hyperframes composition. See docs/agentfield-codeaf.md.

CLI: python -m launchlocal.coder <run_id> [market]
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

from . import common

# Ollama Cloud slug. Measured on the theme task: kimi-k2.7-code 62s, deepseek-v4.1-flash 82s, glm-5.3-flash 149s, glm-5.3 172s.
MODEL = os.environ.get("LAUNCHLOCAL_CODEAF_MODEL", "kimi-k2.7-code")
BASE_URL = "https://ollama.com/v1"
CAP_S = 240  # hard wall for the CodeAF run
_SKIP = {"node_modules", ".git", ".codeaf"}  # .codeaf is CodeAF's own scratch


def _codeaf_bin() -> str:
    return shutil.which("codeaf") or str(Path.home() / ".codeaf" / "bin" / "codeaf")


def build_brief(run_dir: Path, pack: dict) -> str:
    brand = common.read_json(run_dir / "brand.json")
    design = common.read_json(run_dir / "script.json").get("design_brief", {})
    rules = "\n".join(f"- {r}" for r in pack.get("style_rules", []))
    return f"""Restyle this Hyperframes video composition (HTML, CSS, GSAP) in place so it looks like
the official website of {brand.get('name', 'the product')} ({brand.get('url', '')}), adapted to the
conventions of the {pack.get('label', pack.get('id', 'target'))} market.

Brand colors: {json.dumps(brand.get('colors', {}), ensure_ascii=False)}
Brand fonts: {json.dumps(brand.get('fonts', {}), ensure_ascii=False)}
Brand tone: {brand.get('tone', '')}
Design brief: {json.dumps(design, ensure_ascii=False)}
Market style rules:
{rules}

Hard rules:
- Edit styling and motion only: CSS, inline styles, class names, GSAP timings and easings.
- Keep every data-scene and data-fact-id attribute exactly as it is.
- Keep all text content unchanged. Do not add, remove, translate or reword any text.
- Do not add network dependencies: no CDN links, no remote fonts, images or scripts.
  Use only files already in this directory.
- Do not rename or delete files. Do not change scene durations or audio references.
- Read the existing files first, then make focused edits. Finish with a two-line summary.
- Never run git: no add, commit, stash or checkout.
- Do not install packages, start a browser, render, or run npm/npx. A lint runs after you finish.
  Work only inside this directory; aim to finish within about 12 tool calls.
"""


class _Finger(HTMLParser):
    """Collects what CodeAF must not change: data-scene / data-fact-id attributes and visible text."""

    def __init__(self):
        super().__init__()
        self.attrs, self.text, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        self.attrs += [(k, v) for k, v in attrs if k in ("data-scene", "data-fact-id")]

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.text.append(" ".join(data.split()))


def _files(root: Path) -> dict[str, Path]:
    return {
        str(p.relative_to(root)): p
        for p in sorted(root.rglob("*"))
        if p.is_file() and not _SKIP & set(p.relative_to(root).parts)
    }


def fingerprint(comp: Path) -> tuple[list, list]:
    f = _Finger()
    for rel, p in _files(comp).items():
        if rel.endswith(".html"):
            f.feed(p.read_text(encoding="utf-8"))
    return sorted(f.attrs), sorted(f.text)


def _changed(base: Path, comp: Path) -> list[str]:
    a, b = _files(base), _files(comp)
    return sorted(r for r in a.keys() | b.keys() if r not in a or r not in b or a[r].read_bytes() != b[r].read_bytes())


def _emit_call(run_dir: Path, path: Path) -> bool:
    """Turn one CodeAF trace file (one model call) into events. False when the file is not complete yet."""
    try:
        call = json.loads(path.read_text(encoding="utf-8"))
        msg = call["response"]["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError):
        return False
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        tool = fn.get("name", "?")
        if tool in ("edit", "write"):
            text = f"{tool} {args.get('path', '')}"
        elif tool == "sh":
            cmd = str(args.get("cmd") or args.get("command") or next(iter(args.values()), ""))
            text = "$ " + re.sub(r"(?:cd\s+)?/\S*/theme_ws/composition/?\s*(?:&&\s*)?", "", cmd)[:160]  # hide the local workspace path
        else:
            text = f"{tool} {json.dumps(args, ensure_ascii=False)[:120]}"
        common.emit(run_dir, "coder", "progress", text, tool=tool, path=args.get("path", ""))
    if not msg.get("tool_calls") and (msg.get("content") or "").strip():
        common.emit(run_dir, "coder", "log", msg["content"].strip()[:300])
    return True


def _run_codeaf(run_dir: Path, comp: Path, brief: str) -> dict:
    """Run `codeaf exec` headless; stream its debug trace into events; return the --json envelope."""
    common.load_env()
    env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}  # it would win over the base URL
    env.update(CODEAF_BASE_URL=BASE_URL, OPENAI_API_KEY=os.environ["OLLAMA_API_KEY"],
               GIT_DIR="/nonexistent-launchlocal")  # CodeAF once committed to the project repo; git must fail for it
    cmd = [_codeaf_bin(), "exec", "-", "--dir", str(comp), "--model", MODEL,
           "--timeout", f"{CAP_S}s", "--max-turns", "30", "--json", "--debug"]
    trace: list[Path] = []
    t0 = time.time()

    def find_trace():
        # --debug writes <CODEAF_HOME>/logs/trace/<run>/ from the first call; its path is only printed at exit
        root = Path(os.environ.get("CODEAF_HOME", Path.home() / ".codeaf")) / "logs" / "trace"
        for d in root.iterdir() if root.is_dir() else []:
            try:
                if d.stat().st_mtime >= t0 - 2 and Path(json.loads((d / "run.json").read_text())["workspace"]).resolve() == comp.resolve():
                    trace.append(d)
                    return
            except (OSError, ValueError, KeyError):
                continue

    def read_stderr(stream):
        for line in stream:
            line = line.strip()
            if line.startswith("models:"):
                common.emit(run_dir, "coder", "log", line[:300])

    with tempfile.TemporaryFile("w+") as out:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=out, stderr=subprocess.PIPE, text=True, env=env)
        threading.Thread(target=read_stderr, args=(proc.stderr,), daemon=True).start()
        proc.stdin.write(brief)
        proc.stdin.close()
        seen: set[Path] = set()
        deadline = time.time() + CAP_S + 15
        while True:
            running = proc.poll() is None
            if not trace:
                find_trace()
            if trace:  # calls/<id>.json appears once per model call, in order
                for p in sorted((trace[0] / "calls").glob("*.json"), key=lambda p: p.stat().st_mtime):
                    if p not in seen and _emit_call(run_dir, p):
                        seen.add(p)
            if not running:
                break
            if time.time() > deadline:
                proc.kill()
                return {"ok": False, "stop": "deadline", "error": f"killed after {CAP_S}s"}
            time.sleep(0.5)
        out.seek(0)
        try:
            return json.loads(out.read())
        except ValueError:
            return {"ok": False, "stop": "error", "error": f"codeaf exit {proc.returncode}, no JSON on stdout"}


def _lint(comp: Path) -> tuple[bool, str]:
    try:
        r = subprocess.run(["npx", "--yes", "hyperframes", "lint", "--json"], cwd=comp, capture_output=True, text=True, timeout=120)
        rep = json.loads(r.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        return False, f"lint could not run: {e}"
    errors = [f"{f.get('code')}: {f.get('message')}" for f in rep.get("findings", []) if f.get("severity") == "error"]
    return rep.get("errorCount", 1) == 0, "; ".join(errors)[:400]


def restyle_composition(run_dir: Path, pack: dict) -> dict:
    run_dir = Path(run_dir)
    comp, base = run_dir / "composition", run_dir / "composition.baseline"
    if not comp.is_dir():
        common.emit(run_dir, "coder", "error", "composition/ missing, nothing to restyle")
        raise FileNotFoundError(comp)
    shutil.rmtree(base, ignore_errors=True)
    shutil.copytree(comp, base, symlinks=True)
    before = fingerprint(comp)
    common.emit(run_dir, "coder", "start", f"CodeAF restyling the composition with {MODEL} on Ollama Cloud", model=MODEL)
    t0 = time.time()

    problem = ""
    try:
        res = _run_codeaf(run_dir, comp, build_brief(run_dir, pack))
        if not res.get("ok"):
            problem = f"CodeAF did not finish ({res.get('stop')}): {res.get('error') or res.get('incomplete') or ''}"
    except Exception as e:  # any CodeAF failure means the baseline stays
        problem = f"CodeAF failed: {e}"
    shutil.rmtree(comp / ".codeaf", ignore_errors=True)
    changed = _changed(base, comp)
    if not problem and fingerprint(comp) != before:
        problem = "CodeAF changed text or data-scene / data-fact-id attributes"
    if not problem and changed:
        common.emit(run_dir, "coder", "log", "running hyperframes lint")
        ok, tail = _lint(comp)
        if not ok:
            problem = f"hyperframes lint failed: {tail}"

    kept = bool(problem)
    if kept:
        shutil.rmtree(comp)
        shutil.copytree(base, comp, symlinks=True)
        common.emit(run_dir, "coder", "log", f"baseline kept: {problem}"[:500], kept_baseline=True)
        changed = []
    for rel in changed:
        common.emit(run_dir, "coder", "artifact", f"restyled {rel}", path=f"composition/{rel}")
    out = {"changed_files": changed, "model": MODEL, "seconds": round(time.time() - t0, 1), "kept_baseline": kept}
    common.emit(run_dir, "coder", "done", f"{len(changed)} files restyled in {out['seconds']}s", **out)
    return out


def theme_brief(run_dir: Path, pack: dict) -> str:
    brand = common.read_json(run_dir / "brand.json")
    script = run_dir / "script.json"
    design = common.read_json(script).get("design_brief", {}) if script.exists() else {}
    rules = "\n".join(f"- {r}" for r in pack.get("style_rules", []))
    return f"""This directory is a Hyperframes video composition (index.html, styles.css, GSAP) for a product
launch video. Write ONE new file, theme.css: a CSS override stylesheet that is appended after styles.css, so the
video looks like the official website of {brand.get('name', 'the product')} ({brand.get('url', '')}), adapted to
the conventions of the {pack.get('label', pack.get('id', 'target'))} market.

Brand colors: {json.dumps(brand.get('colors', {}), ensure_ascii=False)}
Brand fonts: {json.dumps(brand.get('fonts', {}), ensure_ascii=False)}
Brand tone: {brand.get('tone', '')}
Design brief: {json.dumps(design, ensure_ascii=False)}
Market style rules:
{rules}

Hard rules:
- Read styles.css (its top comment lists the class names you may restyle) and index.html, then write theme.css.
- Create or edit theme.css only. Do not change any other file.
- Paint only: colors, backgrounds, gradients, borders, radii, shadows, font weights and letter spacing, on
  selectors that already exist in styles.css or index.html. Layout is fixed: font sizes, padding, margins, widths,
  display, position, flex and grid declarations are removed from your file afterwards, so do not spend effort on them.
- Make it clearly look like the brand: backgrounds, card surfaces, chips, the call-to-action button, the progress line.
- No @import, no url() pointing at the network, no new fonts. Use the CSS variables already defined in :root.
- Keep text readable: strong contrast between text and its background on every scene.
- Never run git, npm, npx or a browser. Aim to finish within 4 tool calls and end with a two-line summary.
"""


_DECORATIVE = ("claim-index", "scene-number", "rule", "browser-bar", "browser-url", "brand-name")  # safe to hide


def _theme_problem(css: str) -> str:
    """'' when the theme is safe to apply: no network use, and nothing hidden except decoration."""
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S).lower()  # comments may quote the rules
    if any(bad in bare for bad in ("@import", "http://", "https://")):
        return "theme.css uses the network"
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", bare):
        if re.search(r"(display\s*:\s*none|visibility\s*:\s*hidden)", body):
            for sel in selectors.split(","):
                last = re.findall(r"[.#]([\w-]+)", sel.strip())[-1:] or [""]
                if last[0] not in _DECORATIVE:
                    return f"theme.css hides content ({sel.strip()[:60]})"
    return ""


# A theme may change paint, never layout: sizes and positions are tuned to the 1280x720 frame.
_PAINT = ("color", "background", "border", "box-shadow", "text-shadow", "letter-spacing", "font-weight", "font-style",
          "outline", "text-decoration", "fill", "stroke", "accent-color", "caret-color", "--")
_LAYOUT_BORDER = ("border-width", "border-top-width", "border-right-width", "border-bottom-width", "border-left-width")


def sanitize_theme(css: str) -> tuple[str, int, int]:
    """Keep paint declarations only. Returns (css, kept, dropped)."""
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    bare = re.sub(r"@[^{};]+\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", bare)  # drop @media/@keyframes/@font-face blocks whole
    rules, kept, dropped = [], 0, 0
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", bare):
        decls = []
        for d in body.split(";"):
            prop = d.split(":", 1)[0].strip().lower()
            if not prop or ":" not in d:
                continue
            if prop.startswith(_PAINT) and prop not in _LAYOUT_BORDER:
                decls.append(d.strip())
                kept += 1
            else:
                dropped += 1
        if decls:
            rules.append(f"{selectors.strip()}{{{';'.join(decls)}}}")
    return "\n".join(rules) + "\n", kept, dropped


def build_theme(run_dir: Path, pack: dict) -> dict:
    """CodeAF writes run_dir/theme.css in a scratch copy of the composition.

    It needs only brand.json, so it runs in parallel with script and voice; compose.build_baseline appends
    theme.css when it exists. Nothing is written to the run dir unless every check passes.
    """
    from . import compose

    run_dir = Path(run_dir)
    ws = run_dir / "theme_ws"
    shutil.rmtree(ws, ignore_errors=True)
    ws.mkdir(parents=True)
    shutil.copy2(run_dir / "brand.json", ws / "brand.json")
    for name in ("script.json", "facts.json"):  # sample content; the theme depends on structure, not on text
        shutil.copy2(common.RUNS / "fixture" / name, ws / name)
    if (run_dir / "assets").is_dir():
        shutil.copytree(run_dir / "assets", ws / "assets", ignore=shutil.ignore_patterns("capture"))
    comp = compose.build_baseline(ws, pack)
    common.emit(run_dir, "coder", "start", f"CodeAF writing the brand theme with {MODEL} on Ollama Cloud", model=MODEL)
    t0 = time.time()
    problem, css = "", ""
    try:
        res = _run_codeaf(run_dir, comp, theme_brief(run_dir, pack))
        theme = comp / "theme.css"
        if theme.is_file():
            css = theme.read_text(encoding="utf-8")
        if not res.get("ok") and not css:
            problem = f"CodeAF did not finish ({res.get('stop')}): {res.get('error') or res.get('incomplete') or ''}"
        elif len(css.strip()) < 200 or "{" not in css:
            problem = "CodeAF wrote no usable theme.css"
        elif _theme_problem(css):
            problem = _theme_problem(css)
    except Exception as e:
        problem = f"CodeAF failed: {e}"
    seconds = round(time.time() - t0, 1)
    if not problem:
        css, kept, dropped = sanitize_theme(css)
        if kept < 5:
            problem = "CodeAF's theme had no usable paint rules"
        elif dropped:
            common.emit(run_dir, "coder", "log", f"kept {kept} paint declarations from CodeAF's theme, dropped {dropped} that would change layout")
    if problem:
        common.emit(run_dir, "coder", "log", f"baseline look kept: {problem}"[:500], kept_baseline=True)
    else:
        (run_dir / "theme.css").write_text(css, encoding="utf-8")
        common.emit(run_dir, "coder", "artifact", f"theme.css ({len(css.splitlines())} rules)", path="theme.css")
    out = {"changed_files": [] if problem else ["theme.css"], "model": MODEL, "seconds": seconds, "kept_baseline": bool(problem)}
    common.emit(run_dir, "coder", "done", f"brand theme {'kept baseline' if problem else 'written'} in {seconds}s", **out)
    return out


def theme_passes_lint(run_dir: Path) -> bool:
    """After compose applied theme.css: lint the real composition. On failure the theme is set aside."""
    run_dir = Path(run_dir)
    ok, tail = _lint(run_dir / "composition")
    if not ok:
        (run_dir / "theme.css").replace(run_dir / "theme.rejected.css")
        common.emit(run_dir, "coder", "log", f"baseline look kept: hyperframes lint failed with the theme: {tail}"[:500], kept_baseline=True)
    return ok


if __name__ == "__main__":
    rid = sys.argv[1]
    fn = build_theme if "--theme" in sys.argv else restyle_composition
    market = next((a for a in sys.argv[2:] if not a.startswith("--")), "ja-JP")
    print(json.dumps(fn(common.run_dir(rid), common.load_pack(market))))
