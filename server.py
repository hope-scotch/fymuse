#!/usr/bin/env python3
"""
Tiny HTTP server for Lime Labs. Serves the current folder with the
Cross-Origin-Opener-Policy + Cross-Origin-Embedder-Policy headers that
ONNX Runtime Web needs to enable SharedArrayBuffer (= multi-thread WASM).

Without those headers, the Splitter's ML mode falls back to slow
single-thread WASM (~15-25 min per song instead of ~3-5 min).

Endpoints:
  /api/proxy?url=<encoded-url>
      Fetches the URL server-side and re-streams the bytes back.
      For direct audio file URLs (mp3/wav/m4a/etc) on hosts that
      block CORS.

  /api/yt?url=<encoded-url>
      For YouTube / YouTube Music / SoundCloud / Bandcamp / etc —
      anything that needs an extractor. Spawns yt-dlp -f bestaudio
      and pipes the audio bytes back. Requires `pip install yt-dlp`
      (and ffmpeg for some formats).

  /api/recipe-health   (GET)
      Lightweight probe the browser uses to detect "we're running
      under the local server AND the `claude` CLI is reachable."
      Returns {"ok": true, "model": "<default>"} if so.

  /api/recipe          (POST, JSON body)
      Calls the Claude Code CLI in headless print mode with the given
      system + user prompt. Uses the local Claude Code authentication
      (your subscription) so no API key is needed. Returns the
      assistant's text response. Body shape:
          {"systemPrompt": "...", "userMessage": "...", "model": "sonnet"}
      Response shape (success):
          {"ok": true, "text": "...", "usage": {...}, "cost_usd": 0.0123}
      Response shape (failure):
          {"ok": false, "error": "..."}

Usage:
    python3 server.py            # serves on http://localhost:4747
    python3 server.py 9000       # serves on http://localhost:9000
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler


PROXY_MAX_BYTES = 200 * 1024 * 1024  # 200 MB hard cap
RECIPE_TIMEOUT_SEC = 90              # Claude CLI invocation timeout
RECIPE_DEFAULT_MODEL = "sonnet"      # 'sonnet', 'opus', 'haiku', or full ID

# ---- Cross-origin from the deployed Pages site ---------------------------
# When the user has Lime Labs open on https://lime-labs.pages.dev (or another
# allowed origin) and wants to route AI refinement through THIS local
# server, the browser sends a CORS preflight. Whitelist known origins
# below — anything else gets no Access-Control headers and the browser
# silently blocks the call (which is what we want).
#
# Mixed-content note: HTTPS pages CAN reach http://localhost in Chrome /
# Firefox (localhost is "potentially trustworthy" per W3C spec). Safari
# blocks it — users on Safari can't use prod→local; they need API mode
# or to open the site directly via http://localhost:4747.
ALLOWED_ORIGINS = {
    "https://lime-labs.pages.dev",
    "http://localhost:4747",
    "http://127.0.0.1:4747",
}

# Optional shared-token auth: when LIME_TOKEN is set in the environment,
# /api/recipe requires an X-Lime-Token: <value> header that matches.
# Prevents random other tabs/sites from burning your subscription if they
# happen to find localhost while server.py is running.
RECIPE_SHARED_TOKEN = os.environ.get("LIME_TOKEN", "").strip()


class CrossOriginIsolatedHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Required for SharedArrayBuffer (ONNX Runtime multi-threaded WASM)
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        # Allow loading from third-party CDNs (jsdelivr, esm.sh, HuggingFace)
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        # Emit cross-origin (CORS + PNA) headers when the request came from
        # an allowed external origin — lets the deployed Pages site reach
        # back here for AI refinement.
        self._send_cors_headers()
        super().end_headers()

    def _send_cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "content-type, x-lime-token")
            # Private Network Access — Chrome flags public→private fetches
            # without this header. Required even when origin is on localhost.
            self.send_header("Access-Control-Allow-Private-Network", "true")
            # Echo Vary so caches don't merge responses across origins
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self):
        # Preflight: respond 204 with the CORS headers (added by end_headers).
        # No body required. Browsers cache preflights for the duration set
        # by Access-Control-Max-Age (we don't set it; default is 5s in Chrome).
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/proxy"):
            return self._handle_proxy()
        if self.path.startswith("/api/yt"):
            return self._handle_yt()
        if self.path.startswith("/api/recipe-health"):
            return self._handle_recipe_health()
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/recipe"):
            return self._handle_recipe()
        self._send_text(404, "not found")

    def _check_recipe_token(self):
        """Return True if a shared-token gate is enforced AND the
        request's X-Lime-Token header matches. Returns True
        immediately when no token is configured (open mode)."""
        if not RECIPE_SHARED_TOKEN:
            return True
        sent = (self.headers.get("X-Lime-Token") or "").strip()
        return sent == RECIPE_SHARED_TOKEN

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 4 * 1024 * 1024:  # 4 MB cap on POST bodies
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _send_json(self, status, obj):
        body_bytes = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        try:
            self.wfile.write(body_bytes)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _claude_cli_path(self):
        # Honour an explicit override so e.g. fnm/nvm-managed installs work
        # without polluting PATH for the python process.
        return (
            shutil.which("claude")
            or shutil.which("claude.cmd")
            or shutil.which("claude-code")
        )

    def _handle_recipe_health(self):
        # Health probe is callable without a token — the browser uses it
        # to verify connectivity before prompting the user for their token.
        # Response indicates whether a token is required.
        path = self._claude_cli_path()
        if not path:
            return self._send_json(503, {
                "ok": False,
                "error": "claude CLI not found on PATH. Install Claude Code "
                         "(https://docs.claude.com/en/docs/claude-code) and run "
                         "`claude login` to authenticate against your Claude subscription.",
            })
        # Probe `claude --version` to confirm it actually runs. Very fast.
        try:
            r = subprocess.run(
                [path, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            version = (r.stdout or r.stderr or "").strip().splitlines()[0] if (r.stdout or r.stderr) else "unknown"
            return self._send_json(200, {
                "ok": True,
                "claude_cli_path": path,
                "claude_cli_version": version,
                "default_model": RECIPE_DEFAULT_MODEL,
                "token_required": bool(RECIPE_SHARED_TOKEN),
            })
        except Exception as e:
            return self._send_json(503, {"ok": False, "error": f"claude --version failed: {e}"})

    def _handle_recipe(self):
        # Token gate (only when LIME_TOKEN env var is set)
        if not self._check_recipe_token():
            return self._send_json(403, {
                "ok": False,
                "error": "Missing or invalid X-Lime-Token. Set the matching token in the AI Settings popover.",
            })
        body = self._read_json_body()
        if not body or not isinstance(body, dict):
            return self._send_json(400, {"ok": False, "error": "request body must be JSON object"})
        user_message  = body.get("userMessage")  or ""
        system_prompt = body.get("systemPrompt") or ""
        model         = body.get("model") or RECIPE_DEFAULT_MODEL
        if not isinstance(user_message, str) or not user_message.strip():
            return self._send_json(400, {"ok": False, "error": "userMessage required"})
        if len(user_message) > 200_000 or len(system_prompt) > 200_000:
            return self._send_json(413, {"ok": False, "error": "prompt too large (max 200K chars each)"})

        cli = self._claude_cli_path()
        if not cli:
            return self._send_json(503, {
                "ok": False,
                "error": "claude CLI not found on PATH. Install Claude Code and run `claude login`.",
            })

        # Headless invocation. -p enters "print" mode (one-shot, exit after
        # response). --output-format json gives us a structured envelope
        # with the assistant text + usage stats so we don't have to scrape
        # stdout. --append-system-prompt tacks our schema onto Claude
        # Code's default system prompt rather than replacing it (which
        # would lose CC's tool/file context but we don't need those here).
        cmd = [cli, "-p", user_message, "--output-format", "json", "--model", model]
        if system_prompt.strip():
            cmd += ["--append-system-prompt", system_prompt]

        # Strip API-key-style auth from the subprocess environment so the
        # CLI uses the user's Claude.ai SUBSCRIPTION (OAuth) auth instead.
        # When ANTHROPIC_API_KEY is set the CLI prefers it — and if that
        # key has no credit balance you get "Credit balance is too low"
        # instead of the subscription quota you actually want to use.
        # Same for the older ANTHROPIC_AUTH_TOKEN variant.
        cli_env = os.environ.copy()
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            cli_env.pop(k, None)

        try:
            r = subprocess.run(
                cmd,
                capture_output=True, text=True,
                # Pass /dev/null on stdin or the CLI waits 3 s for piped input
                stdin=subprocess.DEVNULL,
                timeout=RECIPE_TIMEOUT_SEC,
                env=cli_env,
            )
        except subprocess.TimeoutExpired:
            return self._send_json(504, {"ok": False, "error": f"claude CLI timed out after {RECIPE_TIMEOUT_SEC} s"})
        except Exception as e:
            return self._send_json(500, {"ok": False, "error": f"claude CLI invocation failed: {e}"})

        # The --output-format json envelope is emitted to stdout EVEN on
        # error conditions (auth failures, rate limits) — the CLI exits
        # non-zero but the JSON contains the user-readable error message.
        # So we try to parse stdout regardless of return code, and only
        # fall back to "raw stderr" if parsing fails.
        env = None
        if r.stdout and r.stdout.strip():
            try:
                env = json.loads(r.stdout.strip())
            except Exception:
                env = None
        if env is None:
            if r.returncode != 0:
                err = (r.stderr or "").strip()[:1200]
                return self._send_json(500, {
                    "ok": False,
                    "error": f"claude CLI exited with status {r.returncode}: {err or '(no stderr)'}",
                })
            return self._send_json(500, {
                "ok": False,
                "error": f"claude CLI stdout was not valid JSON. stdout head: {(r.stdout or '')[:400]}",
            })

        # The --output-format json envelope has the shape:
        #   {"type": "result", "subtype": "success",
        #    "result": "<assistant text>",
        #    "usage": {"input_tokens": N, "output_tokens": M, ...},
        #    "total_cost_usd": 0.0123, "session_id": "...", ...}
        # We unwrap to the schema the browser already expects.
        if env.get("is_error") or env.get("subtype") == "error_during_execution":
            # `result` typically contains the human-readable error in this case
            # ("Not logged in · Please run /login", auth failures, rate limits)
            msg = env.get("result") or env.get("subtype") or "unknown error"
            hint = ""
            if isinstance(msg, str) and "log" in msg.lower() and "in" in msg.lower():
                hint = " — run `claude login` in your terminal to authenticate the CLI against your Claude subscription."
            return self._send_json(500, {
                "ok": False,
                "error": f"Claude CLI error: {msg}{hint}",
            })
        text = env.get("result")
        if not isinstance(text, str):
            return self._send_json(500, {
                "ok": False,
                "error": "claude CLI envelope did not include a string 'result' field.",
                "envelope": env,
            })
        return self._send_json(200, {
            "ok": True,
            "text": text,
            "usage": env.get("usage", {}),
            "cost_usd": env.get("total_cost_usd", 0.0),
            "model": env.get("model") or model,
            "session_id": env.get("session_id"),
        })

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
                    "User-Agent": "LimeLabs-proxy/1.0",
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

    def _handle_yt(self):
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            url = (params.get("url") or [""])[0]
            if not url or not url.lower().startswith(("http://", "https://")):
                self._send_text(400, "missing or non-http(s) ?url=")
                return
            ytdlp = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
            if not ytdlp:
                self._send_text(
                    503,
                    "yt-dlp not installed. Install it with: pip install --user yt-dlp\n"
                    "(also helpful: ffmpeg, e.g. 'brew install ffmpeg' on macOS)",
                )
                return
            # -f bestaudio: pick the highest-quality audio-only stream
            # -o -        : write to stdout
            # --no-playlist: only the single video, even if URL is a playlist
            # --quiet     : keep stderr minimal
            # Prefer M4A (universally browser-decodable) over Opus/WebM
            # which Safari can't decode. Same selector as yt-service/app.py.
            cmd = [
                ytdlp,
                "-f", "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio[acodec=aac]/bestaudio",
                "-o", "-",
                "--no-playlist",
                "--no-warnings",
                "--quiet",
                url,
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.send_response(200)
            # We don't know the container in advance; the browser will sniff.
            self.send_header("Content-Type", "audio/*")
            self.end_headers()
            read_total = 0
            try:
                while True:
                    chunk = proc.stdout.read(64 * 1024)
                    if not chunk:
                        break
                    read_total += len(chunk)
                    if read_total > PROXY_MAX_BYTES:
                        proc.kill()
                        return
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        proc.kill()
                        return
            finally:
                # Drain stderr so the process can exit cleanly.
                try:
                    proc.stderr.read()
                except Exception:
                    pass
                proc.wait(timeout=2)
        except Exception as e:
            # Headers may already be sent — best effort
            try:
                self._send_text(502, f"yt-dlp error: {e}")
            except Exception:
                pass

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
    port = 4747
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)
    server = HTTPServer(("127.0.0.1", port), CrossOriginIsolatedHandler)
    print(f"Lime Labs running at http://localhost:{port}/")
    print("Cross-origin isolation is on — Splitter ML mode will use multi-thread WASM.")
    print("URL proxy endpoint available at /api/proxy?url=<encoded-url>.")
    if shutil.which("yt-dlp") or shutil.which("yt-dlp.exe"):
        print("yt-dlp detected — /api/yt?url= will pull YouTube / SoundCloud audio.")
    else:
        print("yt-dlp NOT installed — YouTube / SoundCloud URLs will fail. "
              "Install with: pip install --user yt-dlp")
    if shutil.which("claude") or shutil.which("claude-code"):
        print("Claude Code CLI detected — /api/recipe will use your Claude subscription "
              "(no API key needed).")
    else:
        print("Claude Code CLI NOT installed — /api/recipe will return 503. "
              "Install from https://docs.claude.com/en/docs/claude-code and run `claude login`.")
    print("CORS allowed origins: " + ", ".join(sorted(ALLOWED_ORIGINS)))
    if RECIPE_SHARED_TOKEN:
        masked = RECIPE_SHARED_TOKEN[:4] + "…" + RECIPE_SHARED_TOKEN[-4:] if len(RECIPE_SHARED_TOKEN) > 8 else "***"
        print(f"Shared token enforced ({masked}) — set the same value in AI Settings.")
    else:
        print("No shared token (LIME_TOKEN env var not set) — anyone reaching localhost can call /api/recipe.")
        print("  To restrict: `LIME_TOKEN=$(openssl rand -hex 16) python3 server.py`")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
