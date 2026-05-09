# FYmuse

A single-file music-theory + songwriting + audio-analysis tool. Open `index.html` in any modern browser. No build step.

## Run locally

- **Plain double-click `index.html`** — works for everything *except* the Splitter's ML (Demucs) mode, which needs cross-origin isolation.
- **For Splitter ML mode locally:** run `python3 server.py` and open `http://localhost:8765/`. The included server adds the `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy` headers that ONNX Runtime Web needs for multi-threaded WASM (~3–5 min per song instead of ~15–25 min single-threaded).

## Deploy to Cloudflare Pages

1. Push this repo to GitHub/GitLab.
2. In Cloudflare Pages, create a new project from the repo.
3. **Build command:** *(leave blank — no build step)*
4. **Output directory:** `/` (or leave blank).
5. Deploy.

The `_headers` file in the repo root sets COOP/COEP automatically, so the deployed site has full multi-threaded WASM out of the box — no server.py needed.

## Files

| File | Purpose |
|---|---|
| `index.html` | The whole app (HTML + CSS + JS, ~280 KB). |
| `logo.png` | Brand mark used in the header. |
| `server.py` | Tiny local dev server with COOP/COEP for ML mode. Not used in production. |
| `_headers` | Cloudflare Pages response-header config. |
| `MEMORY.md` | Engineering notes / architecture / change history. |

## Splitter ML mode notes

- First run downloads `htdemucs_embedded.onnx` (~172 MB) from Hugging Face's static hosting (treated as a CDN, not their inference API — your audio never leaves your browser).
- The model is cached by your browser's HTTP cache after the first download.
- Audio inference runs entirely in your browser via ONNX Runtime Web, with WebGPU when available, otherwise WASM.
