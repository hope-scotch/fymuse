"""
Lime Labs — Desktop launcher (native window)
=============================================
Wraps the existing http.server backend (server.py) in a real desktop window
using pywebview. No browser, no Electron, no Node — pure Python. Same approach
as Lime Studio's desktop.py.

Run (dev):
    cd ~/limelabs
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python3 desktop.py

What it does:
  1. Starts server.py's CrossOriginIsolatedHandler on 127.0.0.1:4747 in a
     daemon thread (serving index.html + assets with COOP/COEP so the Splitter's
     multi-threaded WASM / SharedArrayBuffer path works).
  2. Waits until the server answers, then opens a native window on it.
  3. Closing the window exits the process (daemon thread dies with it).

Browser mode is unchanged — `python3 server.py` still works on its own.

Platform notes:
  - macOS:   works out of the box (`pip install pywebview` pulls pyobjc; the
             window is WKWebView, which honours COOP/COEP for SharedArrayBuffer).
  - Windows: needs the Edge "WebView2" runtime (preinstalled on Win 11; else
             https://developer.microsoft.com/microsoft-edge/webview2/).
  - Linux:   needs a GUI backend — `pip install "pywebview[qt]"` or the GTK
             stack (python3-gi, gir1.2-webkit2-4.0).
"""

import functools
import os
import sys
import threading
import time
import urllib.request
from http.server import HTTPServer

HOST = "127.0.0.1"
PORT = int(os.environ.get("LIMELABS_PORT", "4747"))
URL = f"http://{HOST}:{PORT}"

# Headless mode: run the backend without opening a window (handy for CI smoke
# tests and for running the packaged app as a plain local server).
NO_WINDOW = os.environ.get("LIMELABS_NO_WINDOW") == "1"

if not NO_WINDOW:
    try:
        import webview  # pywebview
    except ImportError:
        sys.exit(
            "pywebview is not installed.\n"
            "  pip install -r requirements.txt   (or: pip install pywebview)\n"
            "Linux also needs a backend, e.g.  pip install 'pywebview[qt]'"
        )

import server  # reuses CrossOriginIsolatedHandler; __main__ guard means import is side-effect-free


def resource_dir():
    """Directory that holds index.html + static assets.
    Frozen (PyInstaller) → the unpacked _MEIPASS temp dir.
    Dev → the folder this file lives in."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def ensure_bundled_tools_on_path():
    """When frozen, make a bundled yt-dlp / ffmpeg binary discoverable via
    shutil.which() — server.py looks them up on PATH. In dev they come from the
    venv (yt-dlp) and the system (ffmpeg), so this is a no-op there."""
    base = resource_dir()
    candidates = [base, os.path.join(base, "vendor")]
    extra = os.pathsep.join(p for p in candidates if os.path.isdir(p))
    if extra:
        os.environ["PATH"] = extra + os.pathsep + os.environ.get("PATH", "")


def start_backend():
    """Serve the bundled UI with the exact same handler browser mode uses.
    `directory=` pins SimpleHTTPRequestHandler to the resource dir so the frozen
    app serves index.html regardless of the working directory it launched from."""
    handler = functools.partial(server.CrossOriginIsolatedHandler, directory=resource_dir())
    httpd = HTTPServer((HOST, PORT), handler)
    httpd.serve_forever()


def wait_for_server(timeout=15.0):
    """Poll the server until it's accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL + "/", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def main():
    ensure_bundled_tools_on_path()
    threading.Thread(target=start_backend, daemon=True).start()

    if not wait_for_server():
        sys.exit("Backend failed to start on " + URL)

    import shutil
    has_yt = bool(shutil.which("yt-dlp") or shutil.which("yt-dlp.exe"))
    has_ffmpeg = bool(shutil.which("ffmpeg") or shutil.which("ffmpeg.exe"))
    print("─" * 50)
    print("  Lime Labs — desktop window")
    print(f"  backend: {URL}")
    print(f"  yt-dlp={'yes' if has_yt else 'NO'}  ffmpeg={'yes' if has_ffmpeg else 'NO'}")
    print("─" * 50)

    if NO_WINDOW:
        print("  (headless mode — serving without a window; Ctrl-C to quit)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    webview.create_window(
        "Lime Labs",
        URL,
        width=1320, height=860,
        min_size=(1024, 680),
        background_color="#0a0c10",
    )
    # gui=None lets pywebview pick the best backend for the platform.
    webview.start()


if __name__ == "__main__":
    main()
