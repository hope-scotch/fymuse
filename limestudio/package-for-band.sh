#!/usr/bin/env bash
# Package the built Lime Studio.app into a single file you can AirDrop / share.
# Run AFTER ./build.sh has produced dist/Lime Studio.app.
#
#   ./package-for-band.sh
#
# Produces Lime Studio-mac.zip — send that to your bandmates, then point them at
# BANDMATES-READ-ME.md for the (one-time) first-launch steps.
set -euo pipefail
cd "$(dirname "$0")"

APP="dist/Lime Studio.app"
OUT="Lime Studio-mac.zip"

if [[ ! -d "$APP" ]]; then
  echo "✗ $APP not found — build it first:  brew install portaudio && ./build.sh"
  exit 1
fi

echo "▸ Zipping $APP → $OUT"
rm -f "$OUT"
# ditto preserves the .app bundle correctly (a plain 'zip' can corrupt it)
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT"

SIZE=$(du -h "$OUT" | cut -f1)
echo "✓ $OUT  ($SIZE) — ready to AirDrop or drop in Google Drive."
echo "  Send it together with BANDMATES-READ-ME.md."
echo
echo "  Tip: AirDrop is the smoothest way to share within the band."
