# FYmuse

A single-file music-theory + songwriting + audio-analysis tool. Open `index.html` in any modern browser. No build step.

## Run locally

- **Plain double-click `index.html`** — works for everything *except* the Splitter's ML mode and the URL feature for YouTube links.
- **For Splitter ML mode + YouTube URL load:** run `python3 server.py` and open `http://localhost:8765/`.
  - The server adds the `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy` headers that ONNX Runtime Web needs for multi-threaded WASM (~3–5 min per song instead of ~15–25 min single-threaded).
  - It also exposes `/api/yt?url=` and `/api/proxy?url=` so the Splitter's URL feature can pull from YouTube / SoundCloud / Bandcamp / direct audio hosts.
  - Requires `yt-dlp` for YouTube extraction: `brew install yt-dlp ffmpeg` (macOS) or `pip install --user yt-dlp` (any OS, plus install ffmpeg via your system package manager).

## Sharing with band members / collaborators (Phase 1)

The deployed site (`fymuse.pages.dev`) supports drag-drop and direct audio URLs for everyone — share the link freely. **YouTube / YT Music URLs only work in local mode** because Google blocks every known cloud datacenter IP from extracting audio.

For collaborators who want the full one-click "paste YT URL → split" flow, the simplest path is to have them run their own local copy. Each laptop is its own residential IP, so YouTube treats them as normal browsers:

```bash
# One-time setup (per collaborator, ~2 minutes)
brew install yt-dlp ffmpeg python    # macOS — use apt / choco on other OSes
git clone https://github.com/<your-username>/fymuse.git
cd fymuse

# Each session
python3 server.py
# Then open http://localhost:8765/ in the browser
```

Bookmark `http://localhost:8765/` and use it like a website. No shared cookies, no shared infrastructure, no per-user account setup. Each member's YT extractions go through their own residential connection.

If you want a "Phase 2" setup later — one always-on box that the whole band hits via a stable URL — see *Future ideas* in `MEMORY.md`.

## Deploy to Cloudflare Pages

1. Push this repo to GitHub/GitLab.
2. In Cloudflare Pages, create a new project from the repo.
3. **Build command:** *(leave blank — no build step)*
4. **Output directory:** `/` (or leave blank).
5. Deploy.

The `_headers` file sets COOP/COEP automatically so the deployed site has full multi-threaded WASM out of the box. The Pages Function in `functions/api/proxy.js` adds a same-origin CORS proxy for direct audio URLs.

**What works on the deployed site:**
- Drag-drop / Upload audio files (any format the browser can decode)
- URL load from direct audio links (mp3, wav, m4a, etc.) — including CORS-blocked hosts via `/api/proxy`
- Full Splitter pipeline (Demucs ML separation, key detection, per-stem chord/note analysis)
- All chord theory tools (Playground, Path Finder, Melody Mode, Songwriter, Listener)

**What doesn't work on the deployed site:**
- YouTube / YT Music / SoundCloud / Bandcamp URLs — these need yt-dlp running on a residential IP. YouTube blocks all known cloud datacenter IPs. Use local mode (`server.py`) for these.

## Files

| File | Purpose |
|---|---|
| `index.html` | The whole app (HTML + CSS + JS). |
| `logo.png` | Brand mark used in the header. |
| `server.py` | Tiny local dev server. COOP/COEP for ML mode + `/api/proxy` for direct URL CORS bypass + `/api/yt` for yt-dlp YouTube extraction. |
| `_headers` | Cloudflare Pages response-header config. |
| `functions/api/proxy.js` | CF Pages Function: same-origin proxy for direct audio URLs. |
| `MEMORY.md` | Engineering notes / architecture / change history. |

## Splitter ML mode notes

- First run downloads `htdemucs_embedded.onnx` (~172 MB) from Hugging Face's static hosting (treated as a CDN, not their inference API — your audio never leaves your browser).
- The model is cached by your browser's HTTP cache after the first download.
- Audio inference runs entirely in your browser via ONNX Runtime Web, with WebGPU when available, otherwise WASM.
