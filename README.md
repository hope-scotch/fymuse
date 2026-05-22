# FYmuse

A single-file music-theory + songwriting + audio-analysis tool. Open `index.html` in any modern browser. No build step.

## Run locally

- **Plain double-click `index.html`** — works for everything *except* the Splitter's ML mode and the URL feature for YouTube links.
- **For Splitter ML mode + YouTube URL load:** run `python3 server.py` and open `http://localhost:4747/`.
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
# Then open http://localhost:4747/ in the browser
```

Bookmark `http://localhost:4747/` and use it like a website. No shared cookies, no shared infrastructure, no per-user account setup. Each member's YT extractions go through their own residential connection.

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
- **Singing — full 5-phase Bollywood-aware vocal training** (see section below)

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
| `CLAUDE.md` | Project orientation for future Claude sessions — where things live, conventions, gotchas. |
| `SINGING_SPEC.md` | Canonical spec for the Singing feature — methodology, analysis engine, scoring rubric, exercise bank, prescription engine, v1/v2/v3 phasing. |

## Splitter ML mode notes

- First run downloads `htdemucs_embedded.onnx` (~172 MB) from Hugging Face's static hosting (treated as a CDN, not their inference API — your audio never leaves your browser).
- The model is cached by your browser's HTTP cache after the first download.
- Audio inference runs entirely in your browser via ONNX Runtime Web, with WebGPU when available, otherwise WASM.

## Singing — Bollywood-aware vocal training

A complete 5-phase practice tool for Bollywood pop singers preparing for live performance. Click the **Singing** button in the header to enter.

### Recommended workflow

The drill tab needs the reference vocal stem to score against, so the recommended entry is:

1. Open **Splitter**, upload your song, run separation.
2. Once stems are ready, click **Practice singing this →** at the top of the Splitter view.
3. Singing opens with the instrumental as backing and the vocal stem as the pitch reference.

For songs without Splitter handoff, the Singing tab still accepts direct audio file uploads — you lose reference-based scoring (drill mode disabled, in-key scoring falls back to scale-based) but Warm-up, Full Take, Stamina, and the prescription engine all still work.

### Five phase tabs

**Warm-up.** Pick a routine (Quick 5min · Standard 10min · Full 15min). Each runs a sequence of Tone.js-cued exercises — lip trills, sargam in the active raga, palta sequences, aakar, ornament drills, projection drills. After each exercise, a scorecard shows which target notes you hit cleanly. At end of routine, a baseline card captures your clean range + strain zones — this feeds the range-scoring penalty in Full Take and Stamina takes.

**Drill.** Auto-extracted phrases from the reference vocal, sorted by difficulty descending. Click a phrase to loop it with optional vocal guide. Record an attempt, get per-attempt octave-flexible pitch scoring (sing the phrase in your own register, not forced to match the reference singer's range). Mark phrases clean as you nail them.

**Full Take.** 4-beat count-in, then sing the whole song. Don't stop mid-phrase. After stop, the evaluation panel runs the analysis pipeline and shows: composite score (0-100), seven sub-scores (pitch / ornament / vibrato / timing / dynamics / projection / range) each clickable to expand the detail, pitch-contour SVG overlay (reference vs your take), onset-offset histogram, take audio playback + download.

**Stamina.** Single song × 3 or × 5 with 60-second forced rest between takes. After the final take, the decay analysis shows how each sub-score trended across takes — pitch dropping by take 3, projection collapsing by take 4, etc. The killer feature for live-set prep.

**Review.** Session summary + the **prescription engine**: top 3 weaknesses from the latest take, each with a specific drill protocol (reps, tempo, technique focus) and linked exercises that load directly into next session's Warm-up. This is the bridge between sessions — what makes compounding improvement possible.

### Bollywood-aware analysis

Built specifically for Bollywood pop rather than ported from a Western-pop scorer. Key differences:

- **Raga-aware pitch scoring** — five Bollywood-prominent ragas (Bhairavi, Yaman, Kafi, Khamaj, Bhairav) plus Major/Minor, each with cents-offset tuning tables that match Hindustani performance practice. A komal Re in Bhairavi sits 90¢ flat of equal-tempered Db — Western scorers mark this as off-pitch; this scorer credits it as on-target.
- **Five ornament detectors** — meend (glide), harkat (grace note), murki (turn), taan (fast scale run), khatka (mordent). Ornaments are *credited*, not penalized; pitch frames inside detected ornaments are excluded from the strict pitch denominator so a clean glide doesn't dock your pitch score for "off-target" intermediate frames.
- **Vibrato in the Bollywood band** — 4.5-7.5 Hz rate, 80-200¢ extent; delayed-onset vibrato (starting straight, introducing vibrato 150ms+ into a note) is rewarded as a stylistic positive.
- **Style-aware timing** — ±60ms tolerance (vs Western pop's ±30ms), aalap section detection for free-time intros (zero timing weight in those zones), rubato vs sloppy distinction (high variance with centered median = intentional flexibility).

### Sing along practice

The metronome row in the Singing header provides click-track support for the sargam / paltas / taan-builder warm-up exercises and for slow-tempo drill loops. It auto-syncs BPM to the song's detected tempo when you load via Splitter handoff. Subdivision picker covers 1/4, 1/8, triplets, 1/16; bar-length covers 2/4 through 16-beat (teentaal feel). Not needed while singing along to the full backing track — the track itself is your pulse.

### Web Worker analysis

Take analysis (FFT + pitch extraction across thousands of frames) runs in a Web Worker by default so the UI stays responsive while you wait for evaluation. Falls back to main-thread analysis automatically if the worker fails for any reason (CSP, OOM, etc).

### Spec + change log

The full design lives at `SINGING_SPEC.md` — methodology, analysis engine architecture, all 7 sub-score formulas, the 25-exercise bank, the 16 prescription rules, and v1/v2/v3 phasing. Engineering decisions and milestone-by-milestone progress live in `MEMORY.md` (newest entries at the top).
