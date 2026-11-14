"""Deterministic, offline Hyperframes baseline. Restyle composition/styles.css."""
from pathlib import Path
import html
import json
import re
import shutil
from . import common

FADE = 0.4  # seconds a scene stays under the next one, so the next can cross-fade in on top
IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.webp'}


def _lum(color):
    h = color.lstrip('#')
    if len(h) in (3, 4):
        h = ''.join(c * 2 for c in h)
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _readable(background):
    return max(('#111111', '#ffffff'), key=lambda c: _contrast(c, background))


def _len_class(text):
    # Length bucket; the stylesheet maps it to a font size so long headlines never overflow.
    n = len(str(text))
    return 'len-s' if n <= 12 else 'len-m' if n <= 20 else 'len-l' if n <= 32 else 'len-xl'


def _local_file(run_dir, relative, types=None):
    if not relative or not isinstance(relative, str):
        return None
    path = (run_dir / relative).resolve()
    if path.is_relative_to(run_dir) and path.is_file() and (types is None or path.suffix.lower() in types):
        return path
    return None


def _product_image(run_dir, brand):
    """Official-site screenshot first, then hero images, then anything in a capture folder."""
    entries = list(brand.get('screenshots') or []) + list(brand.get('images') or [])
    candidates = [x.get('local') if isinstance(x, dict) else x for x in entries]
    for folder in ('capture/screenshots', 'assets/capture/screenshots'):
        candidates += sorted(str(p.relative_to(run_dir)) for p in (run_dir / folder).glob('*') if p.is_file())
    for candidate in candidates:
        path = _local_file(run_dir, candidate, IMAGE_TYPES)
        if path:
            return path
    return None


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
    name = brand.get('name') or script.get('product', '')
    logo_src = ''
    path = _local_file(run_dir, (brand.get('logo') or {}).get('local'))
    if path:
        logo_src = 'assets/logo' + path.suffix
        shutil.copy2(path, out / logo_src)
    # The logo sits in the corner of every scene; the brand name stands in when there is no logo file.
    mark = lambda cls: (f'<img class="{cls}" src="{e(logo_src)}" alt="{e(name)}">' if logo_src
                        else f'<span class="{cls} brand-name">{e(name)}</span>')
    visual = ''
    path = _product_image(run_dir, brand)
    if path:
        shutil.copy2(path, assets / ('product' + path.suffix.lower()))
        site = re.sub(r'^https?://|/$', '', str(brand.get('url') or script.get('cta_url') or ''))
        visual = (f'<figure class="visual anim"><div class="browser-bar"><i></i><i></i><i></i><span class="browser-url">{e(site)}</span></div>'
                  f'<div class="visual-frame"><img class="visual-image" src="assets/product{e(path.suffix.lower())}" alt=""></div></figure>')
    cta_url = re.sub(r'^https?://|/$', '', str(script.get('cta_url') or brand.get('url') or ''))
    segments = []
    start = 0.0
    scenes = script['scenes']
    for i, scene in enumerate(scenes):
        sid = str(scene['id'])
        if not re.fullmatch(r'[\w-]+', sid):
            raise ValueError('Scene ids must contain only letters, numbers, underscores or hyphens')
        duration = float(scene['duration_s'])
        if duration <= 0:
            raise ValueError('Scene durations must be positive')
        role = scene.get('role') if scene.get('role') in ('hook', 'product', 'proof', 'cta') else 'product'
        valid = [fid for fid in scene.get('fact_ids', []) if fid in facts]
        claims = [c for c in scene.get('on_screen', []) if c.get('fact_id') in facts]
        valid = list(dict.fromkeys(valid + [c['fact_id'] for c in claims]))
        if role == 'cta' and valid and not claims and script.get('cta_local'):
            claims = [{'text_local': script['cta_local'], 'fact_id': valid[0]}]  # the button is always a sourced claim
        copy = []
        caption = ''
        # A scene without a known source keeps its timing, but displays no claims.
        if valid:
            headline = scene.get('headline_local', '')
            copy.append(f'<h1 class="headline {_len_class(headline)} anim" data-fact-id="{e(valid[0])}">{e(headline)}</h1>')
            items = []
            for j, claim in enumerate(claims):
                fid = claim['fact_id']
                items.append(f'<div id="claim-{e(sid)}-{j}" class="claim anim" data-fact-id="{e(fid)}"><span class="claim-index">{j+1:02d}</span><span class="claim-text">{e(claim.get("text_local", ""))}</span><span class="source-chip">{e(facts[fid].get("source_title", fid))}</span></div>')
            if items:
                copy.append(f'<div class="claims count-{len(items)}">{"".join(items)}</div>')
            caption = f'<p class="caption anim" data-fact-id="{e(valid[0])}">{e(scene.get("narration_local", ""))}</p>'
        if role == 'cta':
            copy.insert(0, mark('cta-logo anim'))
            if cta_url:
                copy.append(f'<div class="cta-url anim">{e(cta_url)}</div>')
        show_visual = visual if role == 'product' else ''
        audio_tag = ''
        audio = run_dir / 'audio' / f'{sid}.wav'
        if audio.is_file():
            shutil.copy2(audio, assets / f'{sid}.wav')
            audio_tag = f'<audio id="audio-{e(sid)}" src="assets/{e(sid)}.wav" data-start="{start:.4f}" data-duration="{duration:.4f}" data-track-index="2"></audio>'
        last = i == len(scenes) - 1
        classes = f'scene scene-{role} clip' + (' has-visual' if show_visual else '')
        segments.append(
            f'<section id="scene-{e(sid)}" class="{classes}" data-scene="{e(sid)}" data-role="{role}" data-start="{start:.4f}" data-duration="{duration + (0 if last else FADE):.4f}" data-track-index="{i % 2}">'
            f'<header>{mark("logo")}<span class="scene-number">{i+1:02d} / {len(scenes):02d}</span></header>'
            f'<main><div class="copy">{"".join(copy)}</div>{show_visual}</main>{caption}<div class="rule"></div>{audio_tag}</section>')
        start += duration
    fonts = pack.get('fonts') or {}
    if isinstance(fonts, list):
        fonts = {'heading': fonts[0], 'body': fonts[-1]} if fonts else {}
    palette = {'background':'#0a0a0a','surface':'#161616','text':'#ffffff','muted':'#a1a1aa','primary':'#2ecc71','accent':'#3b82f6'}
    palette.update({k:v for k,v in brand.get('colors', {}).items() if k in palette and isinstance(v,str) and re.fullmatch(r'#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})',v)})
    # Readable on light and dark brands alike: fall back when the brand's own pairs are too close.
    if _contrast(palette['text'], palette['background']) < 4.5:
        palette['text'] = _readable(palette['background'])
    if _contrast(palette['muted'], palette['background']) < 3:
        palette['muted'] = palette['text']
    palette['on-primary'] = _readable(palette['primary'])
    theme = 'light' if _lum(palette['background']) > 0.4 else 'dark'
    # The brand's heading font is used only when a file for it is bundled in template/fonts.
    font_face = ''
    heading = fonts.get('heading', 'Noto Sans JP')
    wanted = re.sub(r'[^a-z0-9]', '', str((brand.get('fonts') or {}).get('heading', '')).lower())
    for font in sorted((source / 'fonts').glob('*')):
        if wanted and font.suffix.lower() in ('.ttf', '.otf', '.woff2') and re.sub(r'[^a-z0-9]', '', font.stem.lower()) == wanted:
            heading = brand['fonts']['heading']
            font_face = f'@font-face{{font-family:{json.dumps(heading)};src:url("assets/fonts/{font.name}");font-weight:100 900;font-display:block}}\n'
            break
    variables = ';'.join(f'--{k}:{v}' for k,v in palette.items())
    variables += ';--font-heading:' + json.dumps(heading) + ',"Noto Sans JP",sans-serif'
    variables += ';--font-body:' + json.dumps(fonts.get('body','Noto Sans JP')) + ',"Noto Sans JP",sans-serif'
    css = font_face + ':root{' + variables + '}\n' + (source / 'styles.css').read_text(encoding='utf-8')
    override = run_dir / 'theme.css'
    if override.is_file():
        css += '\n/* theme.css (coding agent override) */\n' + override.read_text(encoding='utf-8')
    (out / 'styles.css').write_text(css, encoding='utf-8')
    document = f'''<!doctype html>
<html lang="{e(script.get('market','ja-JP').split('-')[0])}" data-theme="{theme}"><head><meta charset="UTF-8"><meta name="viewport" content="width=1280,height=720"><link rel="stylesheet" href="styles.css"><script src="assets/gsap.min.js"></script></head>
<body><div id="root" data-composition-id="main" data-width="1280" data-height="720" data-fps="30" data-start="0" data-duration="{start:.4f}">{''.join(segments)}</div>
<script>{(source / 'timeline.js').read_text(encoding='utf-8').replace('__TOTAL__', f'{start:.4f}').replace('__FADE__', str(FADE))}</script></body></html>'''
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
