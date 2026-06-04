#!/usr/bin/env bash
# Build the Lime Studio desktop app (macOS / Linux).
# Uses a self-contained virtualenv, so it works with Homebrew/managed Python
# (no PEP 668 "externally-managed-environment" error, nothing touches system pip).
#
#   macOS  → dist/Lime Studio.app
#   Linux  → dist/LimeStudio/LimeStudio
#
# Network: tries your configured pip index first; if it can't connect (e.g. a
# corporate Artifactory mirror while you're off-VPN), it falls back to public
# PyPI automatically. Force public with --public  or  LIMESTUDIO_PUBLIC_PYPI=1.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
VENV=".venv"
PUBLIC_INDEX="https://pypi.org/simple"
FORCE_PUBLIC=""
[[ "${1:-}" == "--public" || "${LIMESTUDIO_PUBLIC_PYPI:-}" == "1" ]] && FORCE_PUBLIC=1

# pip install that tolerates an unreachable corporate mirror.
pipi() {
  if [[ -n "$FORCE_PUBLIC" ]]; then
    python -m pip install --index-url "$PUBLIC_INDEX" "$@"
    return $?
  fi
  # try the configured index, but fail fast instead of hanging for ~75s
  if python -m pip install --retries 2 --timeout 12 "$@"; then
    return 0
  fi
  echo "  ⚠  Configured pip index unreachable — falling back to public PyPI…"
  python -m pip install --index-url "$PUBLIC_INDEX" "$@"
}

echo "▸ Setting up build virtualenv ($VENV)…"
"$PY" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
[[ -n "$FORCE_PUBLIC" ]] && echo "▸ Forcing public PyPI ($PUBLIC_INDEX)"
pipi --upgrade pip >/dev/null 2>&1 || true

echo "▸ Installing core dependencies…"
pipi -r requirements.txt pyinstaller pillow   # pillow is used by generate_icon.py

echo "▸ Installing optional mic features (numpy, pyaudio)…"
if ! pipi -r requirements-optional.txt; then
  echo "  ⚠  Optional audio deps didn't install (usually missing PortAudio)."
  echo "     The app will still build and run in SIMULATOR mode."
  echo "     To enable the live mic (reactive lights + BPM detect):"
  echo "       macOS:  brew install portaudio  &&  ./build.sh"
  echo "       Debian: sudo apt install portaudio19-dev  &&  ./build.sh"
fi

echo "▸ Generating icon…"
python generate_icon.py || echo "  (couldn't regenerate icon — using the existing icon.icns/.ico)"

echo "▸ Building with PyInstaller…"
python -m PyInstaller --noconfirm --clean LimeStudio.spec

echo
if [[ "$(uname)" == "Darwin" ]]; then
  echo "✓ Built dist/Lime Studio.app"
  echo "    open 'dist/Lime Studio.app'"
  echo "    First launch: right-click → Open to clear Gatekeeper (it's unsigned)."
else
  echo "✓ Built dist/LimeStudio/LimeStudio"
fi
