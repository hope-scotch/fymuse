#!/usr/bin/env bash
# Build the Lime Labs desktop app (macOS / Linux).
# Self-contained virtualenv, so it works with Homebrew/managed Python
# (no PEP 668 "externally-managed-environment" error).
#
#   macOS  → dist/Lime Labs.app
#   Linux  → dist/LimeLabs/LimeLabs
#
# Steps: venv → deps → vendor yt-dlp (+ try ffmpeg) → icon → PyInstaller.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
VENV=".venv"
OS="$(uname -s)"

echo "▸ Setting up build virtualenv ($VENV)…"
"$PY" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null 2>&1 || true

echo "▸ Installing dependencies…"
pip install -r requirements.txt pyinstaller pillow

# --- Vendor the standalone yt-dlp binary so the frozen app extracts audio ----
echo "▸ Vendoring yt-dlp binary…"
mkdir -p vendor
case "$OS" in
  Darwin) YTDLP_URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos" ;;
  Linux)  YTDLP_URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp" ;;
  *)      YTDLP_URL="" ;;
esac
if [[ -n "$YTDLP_URL" ]]; then
  curl -fL --retry 3 -o vendor/yt-dlp "$YTDLP_URL" && chmod +x vendor/yt-dlp \
    && echo "  ✓ vendor/yt-dlp" \
    || echo "  ⚠  couldn't fetch yt-dlp — frozen app will fall back to the bundled yt_dlp module"
fi

# --- ffmpeg is heavier; vendor if a static build is available locally --------
# Easiest cross-platform source: the user drops a static ffmpeg at vendor/ffmpeg
# (download from https://evermeet.cx/ffmpeg/ on macOS or https://johnvansickle.com/ffmpeg/ on Linux).
if [[ ! -x vendor/ffmpeg ]]; then
  if command -v ffmpeg >/dev/null 2>&1; then
    cp "$(command -v ffmpeg)" vendor/ffmpeg && chmod +x vendor/ffmpeg \
      && echo "  ✓ vendored system ffmpeg" || true
  else
    echo "  ⚠  no ffmpeg found to vendor — some YouTube formats may fail."
    echo "     Drop a static binary at vendor/ffmpeg and re-run to include it."
  fi
fi

echo "▸ Generating app icon…"
python generate_icon.py || echo "  (icon step skipped — building without a custom icon)"

echo "▸ Building with PyInstaller…"
python -m PyInstaller --noconfirm --clean LimeLabs.spec

echo
if [[ "$OS" == "Darwin" ]]; then
  echo "✓ Built dist/Lime Labs.app"
  echo "    open 'dist/Lime Labs.app'"
  echo "    First launch: right-click → Open to clear Gatekeeper (it's unsigned for now)."
else
  echo "✓ Built dist/LimeLabs/LimeLabs"
fi
