#!/usr/bin/env python3
"""
Tiny yt-dlp HTTP service. Designed to run on Fly.io as a sidecar to
the main FYmuse Cloudflare Pages app.

When YouTube blocks Cloudflare's datacenter IPs (which it does often
and aggressively), the CF Pages Function at /api/yt falls back to
this service. Fly's residential-ish IPs hit YouTube's bot detection
much less than Cloudflare's do.

Endpoints:
  GET /healthz
      200 OK plaintext. Used by Fly's auto-start health checks.

  GET /?url=<encoded-url>
      Spawns yt-dlp -f bestaudio -o - <url> and streams the audio
      bytes back as the response body. 200 MB cap.

Environment:
  PORT           HTTP port to listen on. Default 8080.
  ALLOW_ORIGIN   Value for Access-Control-Allow-Origin. Default "*".
                 Tighten to your CF Pages origin in production.
"""
import os
import shutil
import subprocess
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler


MAX_BYTES = 200 * 1024 * 1024  # 200 MB hard cap
PORT = int(os.environ.get("PORT", 8080))
ALLOW_ORIGIN = os.environ.get("ALLOW_ORIGIN", "*")


class YtHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Keep the log quiet — Fly captures stderr separately.
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        if self.path.startswith("/healthz"):
            self._send_text(200, "ok")
            return
        return self._handle_yt()

    def _handle_yt(self):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        url = (params.get("url") or [""])[0]
        if not url or not url.lower().startswith(("http://", "https://")):
            self._send_text(400, "missing or non-http(s) ?url=")
            return
        ytdlp = shutil.which("yt-dlp")
        if not ytdlp:
            self._send_text(503, "yt-dlp not in PATH (image misbuilt)")
            return
        cmd = [
            ytdlp,
            "-f", "bestaudio",
            "-o", "-",
            "--no-playlist",
            "--no-warnings",
            "--quiet",
            url,
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except Exception as e:
            self._send_text(502, "spawn failed: %s" % e)
            return

        self.send_response(200)
        self.send_header("Content-Type", "audio/*")
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        total = 0
        try:
            while True:
                chunk = proc.stdout.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    proc.kill()
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    proc.kill()
                    break
        finally:
            try:
                proc.stderr.read()
            except Exception:
                pass
            try:
                proc.wait(timeout=3)
            except Exception:
                pass

    def _send_text(self, status, body):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.end_headers()
        try:
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    server = HTTPServer(("0.0.0.0", PORT), YtHandler)
    print("yt-dlp service listening on :%d" % PORT, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutting down", flush=True)


if __name__ == "__main__":
    main()
