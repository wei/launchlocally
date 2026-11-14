# Daytona / Hyperframes renderer

`launchlocal.compose.build_baseline(run_dir, pack)` writes an offline HTML composition.
`launchlocal.render.render(run_dir, cut=1)` renders through the Daytona Python SDK,
downloads artifacts, and hosts a mobile-sized player in the sandbox. No API keys
are sent to the sandbox. Credentials load through `common.load_env()`.

## Ready sandbox

- Sandbox: `c3437016-a5c1-4fc5-980c-5164a0a7bc03`
- Image: `daytonaio/sandbox:0.6.0-slim`; Debian 13, Node 22.14.0.
- Resources: 4 vCPU, 8 GiB RAM, 10 GiB disk (account accepted the maximum requested).
- Create-to-ready API call: **27.55 seconds**, excluding one-time package/browser setup.
- Warm state and current preview directory: `docs/daytona-render.json`.
- Auto-stop explicitly disabled (`auto_stop_interval=0`); sandbox remains billable.
- Each render uploads a gzip archive to its own sandbox directory; the CLI and
  Chrome installation stay cached between renders. No snapshot build is needed.

Setup commands actually run in the sandbox:

```sh
sudo -n apt-get update -qq
sudo -n apt-get install -y -qq ffmpeg fonts-noto-cjk libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1 libasound2t64
npx --yes hyperframes@0.9.43 browser ensure
```

An initial `npm install -g hyperframes@0.9.43` failed with EACCES under the image's
Node prefix. The implementation uses pinned `npx --yes hyperframes@0.9.43`, cached
under the Daytona user's npm directory. No global npm permissions changes.

The trial network restriction was checked rather than assumed: npm, Debian apt,
and the Chrome Headless Shell download from `storage.googleapis.com` all worked
on this account. The downloaded browser is Chrome Headless Shell 152.0.7977.30.
Other accounts may have tighter allowlists; browser-install failure raises and
emits an error, rather than silently falling back to a local render.

## Verify

Run from `/Users/wei/Documents/Projects/Personal/launchlocal`:

```sh
.venv/bin/python -m launchlocal.compose fixture
.venv/bin/python -m launchlocal.render fixture
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of json runs/fixture/video.mp4
```

Expected: H.264 MP4, 1280 × 720, 30 fps. The original four-five-second fixture
rendered at exactly 20.000 seconds without audio. During parallel work, voice
workstream A populated all four WAV files and updated scene durations to
6.11 / 6.57 / 6.38 / 3.48 seconds. Recomposition and Daytona rendering then
produced **22.567 seconds with AAC narration** (frame-rounded from 22.54 seconds). `poster.png` was visually inspected: Japanese glyphs,
headlines, caption and source chip render correctly, without missing-glyph boxes.
A separate temporary two-second composition also passed an actual WAV-to-AAC
audio check; all four real voice tracks were then verified in the Daytona output.
The composer also passed repeat-build hash checks and unknown-fact filtering.

Exact sandbox render command (after upload and lint):

```sh
cd /home/daytona/launchlocal/<run-directory>/composition
npx --yes hyperframes@0.9.43 lint
npx --yes hyperframes@0.9.43 render --fps 30 --workers 4 --no-low-memory-mode --quality standard --strict -o ../video.mp4
ffmpeg -y -ss 1 -i ../video.mp4 -frames:v 1 ../poster.png
```

First measured Daytona fixture render: **8.86 seconds** around the SDK render
command, including command startup and log collection; Hyperframes itself reports
**6.7 seconds**. The subsequent 22.567-second voiced fixture took **11.25 seconds**
through the SDK (**8.3 seconds** in Hyperframes). Final verification after the
small hosting/logging cleanup took **11.30 seconds** through the SDK (**8.8 seconds**
in Hyperframes), with H.264 + AAC and working HTTP 206 byte ranges. Upload, lint, package installation and poster extraction are
outside `render_seconds`. Local experimental render: **13.1 seconds** reported by
Hyperframes. The composition uses flat backgrounds and no filters, masks, shadows
or expensive motion, following the [performance guide](https://hyperframes.heygen.com/guides/performance).
The under-90-second target is met at 30 fps without reducing resolution.

Explicit local fallback:

```sh
LAUNCHLOCAL_RENDER=local .venv/bin/python -m launchlocal.render fixture
```

This emits a visible fallback log, uses the same pinned CLI, and writes
`preview_url: null`, `sandbox_id: null`. It needs local Node, Chrome and FFmpeg.
Cut 2: `.venv/bin/python -m launchlocal.render fixture --cut 2` preserves the
existing first MP4 as `video.cut1.mp4` before writing the next cut.

## Preview and phone behavior

Public preview base:
`https://8000-c3437016-a5c1-4fc5-980c-5164a0a7bc03.daytonaproxy01.net/`.
Use `render.json.preview_url` for the latest run's player directory.

An HTTP request with an iPhone Safari user agent returned Daytona's warning HTML
instead of the player (HTTP 200). Adding
`X-Daytona-Skip-Preview-Warning: true` returned the player, and the MP4 returned
`video/mp4`. Byte-range playback was verified: `Range: bytes=0-100` returned
HTTP 206, `Content-Range: bytes 0-100/657953`, and exactly 101 bytes. This is an HTTP user-agent check, not a physical-phone test. A normal
phone browser cannot attach this header to navigation: the user must accept the
warning, or the controller must proxy the assets while attaching that header.
The MP4 itself is also downloaded locally, so the app can serve it directly.

`template/serve.py` supports HTTP byte ranges for mobile playback. It runs on
port 8000 with a recorded PID in `/tmp/launchlocal-server.pid`. Preview HTML uses
`controls`, `playsinline`, a poster, and responsive video width. The public server
contains only the uploaded compositions and their output, never project secrets.

## Editing and limitations

- All design rules and palette/font variables are in `composition/styles.css`.
  The reusable starting stylesheet is `template/styles.css`. Rebuilding the baseline
  replaces the entire generated composition; run the restyling agent afterward.
- Scene roots retain `data-scene`; sourced text retains `data-fact-id`.
- Noto Sans JP variable TTF and its OFL license are bundled in `template/fonts/`.
  GSAP 3.15.0 is vendored in `template/gsap.min.js`; no runtime CDN is needed.
- Only on-screen claims with known fact IDs survive; scenes without any known
  fact IDs retain their duration but contain no headline/caption claims.
  Headlines and narration inherit the first valid scene fact ID; this checks
  references, not whether a source semantically entails the authored sentence.
- Hyperframes lint passes with zero errors and five advisory warnings about
  splitting scene groups into sub-compositions. The flat scene structure is
  deliberate for quick restyling. `--strict` blocks actual lint errors.
- Generated outputs and events under runs/ are runtime artifacts. No commits made.

## Cleanup

Stop only the recorded server PID, then stop or delete the warm sandbox:

```python
from daytona import Daytona
from launchlocal.common import load_env, read_json
load_env()
daytona = Daytona()
sandbox = daytona.get(read_json('docs/daytona-render.json')['sandbox_id'])
sandbox.process.exec('test ! -f /tmp/launchlocal-server.pid || kill $(cat /tmp/launchlocal-server.pid)')
sandbox.stop()
# Or permanently remove it: daytona.delete(sandbox)
```

After deletion, remove `docs/daytona-render.json` so the next render creates a new
sandbox. Stop keeps installed dependencies and the renderer restarts it on demand.
To stop charging while retaining automatic idle shutdown, set
`sandbox.set_autostop_interval(15)`; rendering explicitly resets this to zero.
No processes were stopped with name matching or `pkill`.
