"""
Lime Studio — Desktop launcher (native window)
============================================
Wraps the existing Flask backend (server.py) in a real desktop window using
pywebview. No browser, no Electron, no Node — pure Python.

Run:
    cd fymuse/limestudio
    pip install -r requirements.txt
    python3 desktop.py

What it does:
  1. Starts server.py's background workers (click track + audio sim).
  2. Runs the Flask app on 127.0.0.1:4748 in a daemon thread.
  3. Waits until the server answers, then opens a native window on it.
  4. Closing the window exits the process (daemon threads die with it).

Browser mode is unchanged — `python3 server.py` still works on its own.

Platform notes:
  - macOS:   works out of the box (`pip install pywebview` pulls pyobjc).
  - Windows: needs the Edge "WebView2" runtime (preinstalled on Win 11;
             otherwise: https://developer.microsoft.com/microsoft-edge/webview2/).
  - Linux:   needs a GUI backend — `pip install pywebview[qt]` (PyQt) or
             the GTK stack (`python3-gi`, `gir1.2-webkit2-4.0`).
"""

import os
import sys
import time
import threading
import urllib.request

HOST = "127.0.0.1"
PORT = 4748
URL = f"http://{HOST}:{PORT}"

# Headless mode: run the backend without opening a window (handy for running the
# packaged app as a server on a spare machine, and for CI smoke tests).
NO_WINDOW = os.environ.get("LIMESTUDIO_NO_WINDOW") == "1"

if not NO_WINDOW:
    try:
        import webview  # pywebview
    except ImportError:
        sys.exit(
            "pywebview is not installed.\n"
            "  pip install -r requirements.txt   (or: pip install pywebview)\n"
            "Linux also needs a backend, e.g.  pip install pywebview[qt]"
        )

import server  # reuses app, click_thread, audio_sim_thread, state


def start_backend():
    """Start the same workers server.py starts in its __main__ block,
    then run Flask. Kept here so `python3 server.py` is left untouched."""
    threading.Thread(target=server.click_thread, daemon=True).start()
    threading.Thread(target=server.audio_sim_thread, daemon=True).start()
    # use_reloader=False is mandatory: the reloader forks a second process,
    # which would double the workers and detach the window.
    server.app.run(
        host=HOST, port=PORT, debug=False,
        use_reloader=False, threaded=True,
    )


def wait_for_server(timeout=15.0):
    """Poll the REST API until the server is accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{URL}/api/capabilities", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def main():
    threading.Thread(target=start_backend, daemon=True).start()

    if not wait_for_server():
        sys.exit("Backend failed to start on " + URL)

    caps = {}
    try:
        with urllib.request.urlopen(f"{URL}/api/capabilities", timeout=2) as r:
            import json
            caps = json.loads(r.read())
    except Exception:
        pass

    print("━" * 50)
    print("  Lime Studio — desktop window")
    print(f"  backend: {URL}")
    print(f"  numpy={caps.get('numpy')}  pyaudio={caps.get('pyaudio')}")
    print("━" * 50)

    if NO_WINDOW:
        print("  (headless mode — serving without a window; Ctrl-C to quit)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    webview.create_window(
        "Lime Studio — Band Performance Controller",
        URL,
        width=1280, height=820,
        min_size=(960, 640),
        background_color="#0a0c10",
        text_select=False,
    )
    # gui=None lets pywebview pick the best backend for the platform.
    webview.start()


if __name__ == "__main__":
    main()
