# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Lime Studio — Band Performance Controller.

Build:
    pip install -r requirements.txt pyinstaller
    pyinstaller --noconfirm LimeStudio.spec

Output:
    macOS    → dist/Lime Studio.app   (double-clickable bundle)
    Windows  → dist/Lime Studio/Lime Studio.exe
    Linux    → dist/Lime Studio/Lime Studio

NOTE: PyInstaller builds for the platform it runs on — build the macOS app on a
Mac, the Windows app on Windows. There is no cross-compilation.
"""

import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [("index.html", ".")]
binaries = []
hiddenimports = [
    "flask_sock",
    "serial", "serial.tools.list_ports",   # DMX (ENTTEC)
    "mido", "mido.backends.rtmidi", "rtmidi",  # MIDI
]

# pull in everything the GUI + MIDI backends need (data + dylibs + submodules)
for pkg in ("webview", "mido"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

ICON = "icon.icns" if sys.platform == "darwin" else ("icon.ico" if sys.platform == "win32" else None)

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
    name="LimeStudio",
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
    name="LimeStudio",
)

# macOS application bundle
app = BUNDLE(
    coll,
    name="Lime Studio.app",
    icon=ICON,
    bundle_identifier="com.fymuse.limestudio",
    info_plist={
        "CFBundleName": "Lime Studio",
        "CFBundleDisplayName": "Lime Studio",
        "CFBundleShortVersionString": "1.4.0",
        "CFBundleVersion": "1.4.0",
        "NSHighResolutionCapable": True,
        # macOS asks the user for mic access using this string when audio starts
        "NSMicrophoneUsageDescription":
            "Lime Studio listens to the stage mix to drive audio-reactive lighting and detect tempo.",
        "LSMinimumSystemVersion": "11.0",
    },
)
