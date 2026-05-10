# FYmuse

A single-file music-theory + songwriting + audio-analysis tool. Open `index.html` in any modern browser. No build step.

## Run locally

- **Plain double-click `index.html`** — works for everything *except* the Splitter's ML (Demucs) mode, which needs cross-origin isolation.
- **For Splitter ML mode locally:** run `python3 server.py` and open `http://localhost:8765/`. The included server adds the `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy` headers that ONNX Runtime Web needs for multi-threaded WASM (~3–5 min per song instead of ~15–25 min single-threaded).
- **For "Load from URL" with YouTube links locally:** install yt-dlp (`pip install --user yt-dlp` and `brew install ffmpeg` if you're on macOS), then run `server.py`. It exposes `/api/yt?url=` which spawns yt-dlp under the hood.

## Deploy to Cloudflare Pages

1. Push this repo to GitHub/GitLab.
2. In Cloudflare Pages, create a new project from the repo.
3. **Build command:** `npm install`
4. **Output directory:** `/` (or leave blank).
5. **Compatibility flags** (Settings → Functions → Compatibility flags): add `nodejs_compat`. The `wrangler.toml` in this repo already declares it, so manual configuration is only a fallback.
6. Deploy.

The `_headers` file sets COOP/COEP automatically so multi-threaded WASM works out of the box. The Pages Functions in `functions/api/` add:

- `/api/proxy?url=<encoded>` — generic CORS proxy for direct audio file URLs.
- `/api/yt?url=<encoded>` — YouTube extractor (uses [`youtubei.js`](https://github.com/LuanRT/YouTube.js); pure JS, no subprocess). YouTube Music URLs work; other extractor-needed sites do not — those need yt-dlp on a real container.

## Files

| File | Purpose |
|---|---|
| `index.html` | The whole app (HTML + CSS + JS). |
| `logo.png` | Brand mark used in the header. |
| `server.py` | Tiny local dev server (COOP/COEP + `/api/proxy` + `/api/yt` via yt-dlp). |
| `_headers` | Cloudflare Pages response-header config. |
| `wrangler.toml` | CF Pages Functions runtime config (`nodejs_compat`). |
| `package.json` | Declares `youtubei.js` dependency for the deployed `/api/yt` endpoint. |
| `functions/api/proxy.js` | CF Pages Function: same-origin proxy for direct audio URLs. |
| `functions/api/yt.js` | CF Pages Function: YouTube audio extractor via youtubei.js. |
| `MEMORY.md` | Engineering notes / architecture / change history. |

## Splitter ML mode notes

- First run downloads `htdemucs_embedded.onnx` (~172 MB) from Hugging Face's static hosting (treated as a CDN, not their inference API — your audio never leaves your browser).
- The model is cached by your browser's HTTP cache after the first download.
- Audio inference runs entirely in your browser via ONNX Runtime Web, with WebGPU when available, otherwise WASM.
