#!/usr/bin/env python3
"""
Tiny HTTP server for FYmuse. Serves the current folder with the
Cross-Origin-Opener-Policy + Cross-Origin-Embedder-Policy headers that
ONNX Runtime Web needs to enable SharedArrayBuffer (= multi-thread WASM).

Without those headers, the Splitter's ML mode falls back to slow
single-thread WASM (~15-25 min per song instead of ~3-5 min).

Also exposes /api/proxy?url=<encoded-url> — fetches the given URL
server-side and re-streams the bytes back. Lets the Splitter's "Load
from URL" feature bypass browser CORS for arbitrary audio hosts.

Usage:
    python3 server.py            # serves on http://localhost:8765
    python3 server.py 9000       # serves on http://localhost:9000
"""

import sys
import urllib.parse
import urllib.request
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler


PROXY_MAX_BYTES = 200 * 1024 * 1024  # 200 MB hard cap


class CrossOriginIsolatedHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Required for SharedArrayBuffer (ONNX Runtime multi-threaded WASM)
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        # Allow loading from third-party CDNs (jsdelivr, esm.sh, HuggingFace)
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/api/proxy"):
            return self._handle_proxy()
        return super().do_GET()

    def _handle_proxy(self):
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            url = (params.get("url") or [""])[0]
            if not url or not url.lower().startswith(("http://", "https://")):
                self._send_text(400, "missing or non-http(s) ?url=")
                return
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "FYmuse-proxy/1.0",
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as upstream:
                ctype = upstream.headers.get("Content-Type", "application/octet-stream")
                clen = upstream.headers.get("Content-Length")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                if clen:
                    self.send_header("Content-Length", clen)
                # send_header → end_headers chain emits the COOP/COEP/CORP headers too
                self.end_headers()
                read_total = 0
                while True:
                    chunk = upstream.read(64 * 1024)
                    if not chunk:
                        break
                    read_total += len(chunk)
                    if read_total > PROXY_MAX_BYTES:
                        # Terminate the connection — too big.
                        return
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
        except urllib.error.HTTPError as e:
            self._send_text(502, f"upstream HTTP {e.code} {e.reason}")
        except Exception as e:
            self._send_text(502, f"proxy error: {e}")

    def _send_text(self, status, body):
        body_bytes = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        try:
            self.wfile.write(body_bytes)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    port = 8765
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)
    server = HTTPServer(("127.0.0.1", port), CrossOriginIsolatedHandler)
    print(f"FYmuse running at http://localhost:{port}/")
    print("Cross-origin isolation is on — Splitter ML mode will use multi-thread WASM.")
    print("URL proxy endpoint available at /api/proxy?url=<encoded-url>.")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
