"""Deterministic, offline Hyperframes baseline. Restyle composition/styles.css."""
from pathlib import Path
import html
import json
import re
import shutil
from . import common


def build_baseline(run_dir: Path, pack: dict) -> Path:
    run_dir = Path(run_dir).resolve()
    script = common.read_json(run_dir / 'script.json')
    brand = common.read_json(run_dir / 'brand.json')
    facts = {f['id']: f for f in common.read_json(run_dir / 'facts.json')}
    out = run_dir / 'composition'
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    assets = out / 'assets'
    assets.mkdir(exist_ok=True)
    source = common.ROOT / 'template'
    shutil.copytree(source / 'fonts', assets / 'fonts', dirs_exist_ok=True)
    shutil.copy2(source / 'gsap.min.js', assets / 'gsap.min.js')
    e = lambda s: html.escape(str(s), quote=True)
    logo = ''
    logo_local = (brand.get('logo') or {}).get('local')
    if logo_local:
        path = (run_dir / logo_local).resolve()
        if path.is_relative_to(run_dir) and path.is_file():
            name = 'logo' + path.suffix
            shutil.copy2(path, assets / name)
            logo = f'<img class="logo" src="assets/{e(name)}" alt="{e(brand.get("name", ""))}">'
    segments = []
    start = 0.0
    for i, scene in enumerate(script['scenes']):
        sid = str(scene['id'])
        if not re.fullmatch(r'[\w-]+', sid):
            raise ValueError('Scene ids must contain only letters, numbers, underscores or hyphens')
        duration = float(scene['duration_s'])
        if duration <= 0:
            raise ValueError('Scene durations must be positive')
        valid = [fid for fid in scene.get('fact_ids', []) if fid in facts]
        claims = [c for c in scene.get('on_screen', []) if c.get('fact_id') in facts]
        valid = list(dict.fromkeys(valid + [c['fact_id'] for c in claims]))
        body = []
        # A scene without a known source keeps its timing, but displays no claims.
        if valid:
            body.append(f'<h1 data-fact-id="{e(valid[0])}">{e(scene.get("headline_local", ""))}</h1>')
            for j, claim in enumerate(claims):
                reveal = min(0.65 + j * 0.75, duration * 0.6)
                fid = claim['fact_id']
                body.append(f'<div id="claim-{e(sid)}-{j}" class="claim clip" data-fact-id="{e(fid)}" data-start="{start + reveal:.4f}" data-duration="{duration - reveal:.4f}"><span class="claim-text">{e(claim.get("text_local", ""))}</span><span class="source-chip">{e(facts[fid].get("source_title", fid))}</span></div>')
            body.append(f'<p class="caption" data-fact-id="{e(valid[0])}">{e(scene.get("narration_local", ""))}</p>')
        audio = run_dir / 'audio' / f'{sid}.wav'
        if audio.is_file():
            shutil.copy2(audio, assets / f'{sid}.wav')
            body.append(f'<audio id="audio-{e(sid)}" src="assets/{e(sid)}.wav" data-start="{start:.4f}" data-duration="{duration:.4f}" data-track-index="1"></audio>')
        segments.append(f'<section id="scene-{e(sid)}" class="scene clip" data-scene="{e(sid)}" data-start="{start:.4f}" data-duration="{duration:.4f}" data-track-index="0"><header>{logo}<span class="brand-name">{e(brand.get("name", script.get("product", "")))}</span><span class="scene-number">{i+1:02d} / {len(script["scenes"]):02d}</span></header><main>{"".join(body)}</main><div class="rule"></div></section>')
        start += duration
    fonts = pack.get('fonts') or {}
    if isinstance(fonts, list):
        fonts = {'heading': fonts[0], 'body': fonts[-1]} if fonts else {}
    palette = {'background':'#0a0a0a','surface':'#161616','text':'#ffffff','muted':'#a1a1aa','primary':'#2ecc71','accent':'#3b82f6'}
    palette.update({k:v for k,v in brand.get('colors', {}).items() if k in palette and isinstance(v,str) and re.fullmatch(r'#[0-9a-fA-F]{3,8}',v)})
    variables = ';'.join(f'--{k}:{v}' for k,v in palette.items())
    variables += ';--font-heading:' + json.dumps(fonts.get('heading','Noto Sans JP')) + ',"Noto Sans JP",sans-serif'
    variables += ';--font-body:' + json.dumps(fonts.get('body','Noto Sans JP')) + ',"Noto Sans JP",sans-serif'
    (out / 'styles.css').write_text(':root{' + variables + '}\n' + (source / 'styles.css').read_text(), encoding='utf-8')
    document = f'''<!doctype html>
<html lang="{e(script.get('market','ja-JP').split('-')[0])}"><head><meta charset="UTF-8"><meta name="viewport" content="width=1280,height=720"><link rel="stylesheet" href="styles.css"><script src="assets/gsap.min.js"></script></head>
<body><div id="root" data-composition-id="main" data-width="1280" data-height="720" data-fps="30" data-start="0" data-duration="{start:.4f}">{''.join(segments)}</div>
<script>window.__timelines = window.__timelines || {{}}; const tl = gsap.timeline({{paused:true}}); tl.to({{}}, {{duration:{start:.4f}}}); window.__timelines.main = tl;</script></body></html>'''
    (out / 'index.html').write_text(document, encoding='utf-8')
    common.write_json(out / 'hyperframes.json', {'$schema':'https://hyperframes.heygen.com/schema/hyperframes.json','paths':{'assets':'assets'}})
    common.emit(run_dir, 'renderer', 'log', 'Built deterministic Hyperframes baseline', scenes=len(segments), duration_s=start)
    return out


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('run_id', nargs='?', default='fixture')
    args = parser.parse_args()
    directory = common.run_dir(args.run_id)
    script = common.read_json(directory / 'script.json')
    print(build_baseline(directory, common.load_pack(script.get('market','ja-JP'))))
