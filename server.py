#!/usr/bin/env python3
"""
Tiny HTTP server for FYmuse. Serves the current folder with the
Cross-Origin-Opener-Policy + Cross-Origin-Embedder-Policy headers that
ONNX Runtime Web needs to enable SharedArrayBuffer (= multi-thread WASM).

Without those headers, the Splitter's ML mode falls back to slow
single-thread WASM (~15-25 min per song instead of ~3-5 min).

Usage:
    python3 server.py            # serves on http://localhost:8765
    python3 server.py 9000       # serves on http://localhost:9000
"""

import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class CrossOriginIsolatedHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Required for SharedArrayBuffer (ONNX Runtime multi-threaded WASM)
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        # Allow loading from third-party CDNs (jsdelivr, esm.sh, HuggingFace)
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        super().end_headers()


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
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
