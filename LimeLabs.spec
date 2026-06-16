# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Lime Labs — desktop app.
Mirrors Lime Studio's spec; adapted for the http.server backend + yt-dlp.

Build:
    pip install -r requirements.txt pyinstaller
    pyinstaller --noconfirm --clean LimeLabs.spec

Output:
    macOS    → dist/Lime Labs.app   (double-clickable bundle)
    Windows  → dist/Lime Labs/Lime Labs.exe
    Linux    → dist/Lime Labs/Lime Labs

NOTE: PyInstaller builds for the platform it runs on — build the macOS app on a
Mac, the Windows app on Windows. There is no cross-compilation.
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all

# --- UI + assets bundled into the app ------------------------------------
# Only local asset index.html references is logo.png; ONNX models/WASM and JS
# libs load from CDNs at runtime (first Splitter use needs network).
datas = [("index.html", "."), ("logo.png", ".")]
binaries = []
hiddenimports = []

# Vendored extractor binaries (yt-dlp, ffmpeg). build.sh downloads these into
# ./vendor for the frozen app; desktop.py prepends ./vendor to PATH at launch.
# Bundle verbatim as data so they aren't dependency-scanned. Optional: the build
# still succeeds for a UI-only prototype if vendor/ is empty.
if os.path.isdir("vendor"):
    for name in os.listdir("vendor"):
        datas.append((os.path.join("vendor", name), "vendor"))

# yt_dlp Python package as a fallback path (importable in-process if the binary
# is ever missing). Belt-and-braces.
try:
    d, b, h = collect_all("yt_dlp")
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

# pywebview's platform backend (pyobjc on macOS, etc.)
for pkg in ("webview",):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

ICON = None
if sys.platform == "darwin" and os.path.exists("icon.icns"):
    ICON = "icon.icns"
elif sys.platform == "win32" and os.path.exists("icon.ico"):
    ICON = "icon.ico"

block_cipher = None

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="LimeLabs",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # windowed app, no terminal
    disable_windowed_traceback=False,
    icon=ICON,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name="LimeLabs",
)

# macOS application bundle
app = BUNDLE(
    coll,
    name="Lime Labs.app",
    icon=ICON,
    bundle_identifier="com.limelabs.app",
    info_plist={
        "CFBundleName": "Lime Labs",
        "CFBundleDisplayName": "Lime Labs",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "NSHighResolutionCapable": True,
        # macOS asks for mic access with this string when the Listener / Singer
        # / live chord-detection features start the microphone.
        "NSMicrophoneUsageDescription":
            "Lime Labs uses the microphone for live chord detection, ear training, and vocal analysis.",
        "LSMinimumSystemVersion": "11.0",
    },
)
