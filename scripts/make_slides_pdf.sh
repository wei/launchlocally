#!/usr/bin/env bash
# Regenerate site/slides/launchlocally-slides.pdf from site/slides/index.html.
# Uses the Chrome Headless Shell cached by the Hyperframes CLI (override with CHROME=...).
set -euo pipefail
cd "$(dirname "$0")/.."
CHROME="${CHROME:-$(ls -d "$HOME"/.cache/hyperframes/chrome/chrome-headless-shell/*/chrome-headless-shell-*/chrome-headless-shell 2>/dev/null | sort | tail -1)}"
[ -x "$CHROME" ] || { echo "chrome-headless-shell not found; set CHROME=/path/to/chrome" >&2; exit 1; }
OUT="$PWD/site/slides/launchlocally-slides.pdf"
# virtual-time budget lets the web font and images load before printing
"$CHROME" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf-no-header \
  --virtual-time-budget=10000 --print-to-pdf="$OUT" "file://$PWD/site/slides/index.html" 2>/dev/null
echo "wrote $OUT"
