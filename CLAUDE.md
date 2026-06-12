# Lime Labs — Claude Orientation

Single-file HTML/JS/CSS music tool. ~15 K lines of `index.html`, no build step. Edit and reload.

## Run

- Most features: open `index.html` directly in any modern browser.
- Splitter ML mode (Demucs ONNX) + YouTube URL load: `python3 server.py` → `http://localhost:4747/`. The server sets COOP/COEP for SharedArrayBuffer and proxies yt-dlp.
- Production deploys to Cloudflare Pages — `_headers` and `functions/api/proxy.js` already wired.

## Architecture

Everything is inline in `index.html`: `<style>` block, then HTML body, then one giant `<script>` block at the bottom. No modules, no bundler. The script defines per-feature globals (state objects, helpers) and a `renderAll()` dispatcher that re-renders the active view.

Main views (mutually exclusive children of `#graph-panel`):

- **Genre graph** (default) — chord nodes + transition arrows
- **Playground** — every chord in the key, categorized
- **Path Finder / Melody Mode / Custom Chord** — right-side overlay panels (mutually exclusive)
- **Songwriter** — top-shutter overlay
- **Listener** — full-width mic + audio file chord detection
- **Splitter** — full-width upload + Demucs stem separation + per-stem analysis
- **Ear Training** — full-width drills
- **Singing** — full-width 5-phase Bollywood-aware vocal training (active development, see below)

The view-switch convention is consistent across all main views: a `GENRES.xxx` entry with an `isXxx: true` flag, a `showXxxView()` function that lazily builds skeleton + swaps `display`, a `buildXxxViewSkeleton(root)` helper, and a `renderXxx()` function called from `renderAll()`. Resources (mic, recorder, playback) are torn down in `renderAll()` when leaving a view.

## Naming convention

Per-feature prefixes. `listenerState`, `listenerStart()`, `listenerStop()`, `buildListenerViewSkeleton(...)` — and matching `splitter*`, `singer*`, `eartraining*`. Helpers shared across features are in the splitter or listener namespaces (e.g., `splitterFFT`, `splitterHannWindow`, `splitterMixToMono`, `splitterDetectMonophonicNotes`) because those features established them first.

## Singing — active development

Five-phase Bollywood-aware vocal training tool that lives alongside Listener/Splitter. The canonical spec is `SINGING_SPEC.md` — read it first if working on anything in the singing system.

Built across 12 milestones. Status:

- **M1** ✓ Navigable shell — header button, GENRES.singer, view dispatch, 5 phase tabs (Warm-up · Drill · Full Take · Stamina · Review) with placeholders, mic/recorder plumbing, Splitter→Singer handoff
- **M2** ✓ Analysis engine — frame extractor (F0/RMS/voicing/centroid/tilt/rolloff/flux/HNR/H1-H2/singer's-formant per 20 ms frame), note + phrase aggregation, top-level `singerAnalyzeBuffer(buffer)`. Plus Singer-specific metronome (Tone.js) with auto-sync to Splitter's detected tempo.
- **M3** ✓ Raga-aware pitch scoring — cents-offset tuning tables for Bhairavi / Yaman / Kafi / Khamaj / Bhairav (+ major / minor), `singerNearestScaleTarget`, reference-vs-scale dispatcher.
- **M4** ✓ Composite v1 + Evaluation panel — `singerScoreDynamics` / `singerScoreRange` / `singerScoreProjection` real, ornament/vibrato/timing placeholder. `singerComputeComposite` with Bollywood weighting + stamina redistribution. Working Record/Stop in Full Take tab. Latest-take eval renders inline. Review tab live.
- **M5** ✓ Vibrato + five ornament detectors — per-note vibrato via DFT 3.5-12 Hz with rate/extent/regularity/onset-delay extraction and straight/vibrato/wobble/tremolo classification (Bollywood rubric: 4.5-7.5 Hz, 80-200¢). Five ornament detectors: meend (monotonic run within note), harkat (brief excursion + return, non-periodic), murki (≥3 alternating harkats in 250 ms), taan (≥4 distinct notes in 500 ms), khatka (small/slow mordent excluding harkat-claimed frames). Weighted ornamentation richness scoring with reference-relative and absolute modes.
- **M6** ✓ Style-aware timing — `singerDetectOnsets` peak-picks spectral flux; `singerDetectAalapSections` flags free-time intros from low-onset-density regions; `singerAlignOnsets` greedy-matches within ±200 ms; `singerScoreTiming` computes median/IQR, classifies rubato (high IQR + centered median → 75-floor bonus) vs sloppy (directional bias → penalty) vs tight. Reference / beat-grid / inconclusive modes. All seven sub-scores now real.
- **M7** ✓ Warm-up tab + 25-exercise bank — 5 families (foundations / sargam / aakar / ornaments / live-prep) with raga-aware pattern generators; 3 routine presets (Quick 5min / Standard 10min / Full 15min); Tone.js cue playback per exercise; per-exercise scorecard with hit/near/off/unvoiced cells; baseline capture (clean range, strain zones, baseline pitch %) → `singerState.warmupBaseline` → feeds M4's `singerScoreRange` strain-zone penalty.
- **M8** ✓ Drill tab — phrase auto-extraction from `referenceFeatures.phrases` (sorted by difficulty desc), loop playback (instrumental + optional vocal guide), per-attempt octave-flexible pitch scoring against the phrase's reference MIDI set, mark-clean promotion. Slow-tempo (SoundTouch) deferred to M8.1.
- **M9** ✓ Full Take polish — 4-beat count-in (Tone.js clicks at detected BPM, visual overlay), pitch-contour SVG overlay (reference + take F0, breaks on unvoiced gaps), onset-offset histogram (20 bins × 20ms over ±200ms, color-coded by Bollywood tolerance), expandable per-dimension detail rows, take audio playback + download.
- **M10** ✓ Stamina mode — single-song ×N (N=3 or 5) with 60s forced rest between takes, per-dimension linear-regression decay slope across takes, stamina session score = 100 + (mean negative slope × 10) clamped. Setlist mode (multi-song) deferred to M10.1.
- **M11** ✓ Review + prescription engine — `SINGER_PRESCRIPTION_RULES` (16 rules across all 7 dimensions) with `condition`/`severity`/`reason`/`prescription`/`exerciseIds` per rule. `singerComputePrescription` evaluates rules, sorts by severity desc, returns top 3. Review tab shows: session summary, prescription card with linked drill exercises, click-to-select takes list, notes textarea.
- **M12** ✓ Web Worker offloading — `_singerWorkerMain` (self-contained: own FFT, Hann window, frame extractor — no main-thread deps), stringified via `singerBuildWorkerSource`, lazy singleton from Blob URL. Frame extraction offloads to worker by default, main-thread fallback on any failure. README + MEMORY.md final wrap-up. **Singing build complete.**

Singer code lives near the bottom of the script. Key surfaces by line (approximate — shifts as edits land):

| Surface                            | Line   |
|------------------------------------|--------|
| `GENRES.singer`                    | ~2660  |
| `showSingerView()`                 | ~6319  |
| Singer comment header + `SINGER_PHASES` / `SINGER_RAGAS` / `singerState` | ~13930 |
| `buildSingerViewSkeleton`          | ~14010 |
| `wireSingerControls`               | ~14080 |
| `singerStartMic` / `singerStopMic` | ~14290 |
| `singerStartRecording` / `singerStopRecording` | ~14380 |
| `singerExtractFrames` (M2)         | ~14620 |
| `singerExtractNotes` (M2)          | ~14860 |
| `singerExtractPhrases` (M2)        | ~14965 |
| `singerAnalyzeBuffer` (M2)         | ~15010 |
| `singerMidiToNoteName` / `singerCentsFromTarget` | ~15075 |
| `SINGER_RAGA_TUNINGS` + pitch scorers (M3) | ~15110 |
| `singerScoreDynamics` / `singerScoreRange` / `singerScoreProjection` (M4) | ~15320 |
| `singerComputeComposite` / `singerScoreTake` (M4) | ~15450 |
| `singerRenderEvaluationPanel` (M4) | ~15510 |
| `singerRenderFullTakeTab` / `singerRenderReviewTab` (M4) | ~15600 |
| `singerDetectNoteVibrato` / `singerScoreVibrato` (M5) | ~15700 |
| 5 ornament detectors + `singerScoreOrnaments` (M5) | ~15900 |
| `singerDetectOnsets` / `singerScoreTiming` (M6) | ~16080 |
| `SINGER_EXERCISES` / `SINGER_ROUTINES` (M7) | ~16300 |
| `singerRenderWarmupTab` / `singerAnalyzeExerciseTake` / `singerComputeBaseline` (M7) | ~16700 |
| `singerScoreDrillAttempt` / `singerStartPhraseLoop` / `singerRenderDrillTab` (M8) | ~17500 |
| `singerRenderPitchContour` / `singerRenderOnsetHistogram` / count-in (M9) | ~16400 |
| `singerComputeStaminaDecay` / `singerRenderStaminaTab` (M10) | ~17800 |
| `SINGER_PRESCRIPTION_RULES` / `singerComputePrescription` (M11) | ~18300 |
| `singerRenderSessionSummary` / `singerRenderPrescriptionCard` (M11) | ~18800 |
| `_singerWorkerMain` / `singerExtractFramesViaWorker` (M12) | ~15470 |
| `singerMetronome` + control fns    | ~19200 |
| `singerInstallSplitterHandoffObserver` | ~15960 |
| `setupSinger` (init)               | ~15945 |

## Key reuses from existing code

The singing engine deliberately reuses pre-existing audio infrastructure from Splitter rather than reimplementing:

- `splitterFFT(re, im)` — in-place radix-2 Cooley-Tukey FFT over Float32Arrays
- `splitterHannWindow(n)` — returns the window
- `splitterMixToMono(buffer)` — channel mixdown
- `splitterYield()` — async yield to keep UI responsive during heavy loops
- `splitterDetectMonophonicNotes(buffer, opts)` — the existing HPS pitch tracker; the M2 frame extractor uses the same HPS+parabolic-interp approach

The Splitter's tempo detector (`splitterState.detectedTempo`) is consumed by the Singer metronome's "sync to song" button.

## Workflow gotchas

**Brace/paren counts are off in the JS.** Pre-existing — caused by string-literal braces inside the source. Don't try to "fix" it. Use `node --check` on the extracted script for real syntax verification:

```bash
python3 -c "import re; s=open('index.html').read(); print(re.search(r'<script>(.*?)</script>', s, re.DOTALL).group(1))" > /tmp/check.js
node --check /tmp/check.js
```

**Function declarations are reassignable in non-strict mode.** The singer code uses `let _orig = X; X = function(...) { _orig(...); extra() }` to extend `wireSingerControls` and `singerStopAll` without modifying the original definitions. This works because the file has no `'use strict'`. Don't add it.

**Line numbers shift on every edit.** When editing, locate anchors by `grep`/`Read` first; don't trust line numbers from previous turns or this doc verbatim. The "Surface | Line" table above is a guide, not gospel.

**Pure-function aggregators are Node-testable.** When adding analysis code, write the aggregator as a pure function over typed arrays so it can be smoke-tested in Node by extracting just that function. The M2 verification approach is the template.

**Git locks in the cowork sandbox: `mv`, don't `rm`.** The mount that exposes `/Users/sayantanbiswas/fymuse` to the cowork sandbox disallows file deletes but permits renames. When `git commit` fails with `cannot lock ref` or `Unable to create '.git/index.lock'`, the lock file is stuck because git's automatic cleanup tries to `unlink` it and that fails silently — leaving the lock in place. Workaround: `mv .git/index.lock .git/index.lock.del.$(date +%s)`. Same for `HEAD.lock`. The `.del.*` files accumulate harmlessly. Confirmed working pattern as of the Singing v1 commit (`f614a42`).

## Pointers

- **`SINGING_SPEC.md`** — canonical singing-feature spec (methodology, UI structure, analysis engine, raga tunings, exercise bank, prescription engine, v1/v2/v3 phasing)
- **`MEMORY.md`** — chronological engineering change history. Newest entries at the top of the "Recent change history" section. Style: one dense paragraph per change with the *why*, the symptom that motivated it, and the fix.
- **`README.md`** — user-facing run/deploy instructions
- **`docs/CUSTOM_OTHER_SPLITTER.md`** — parked design doc for a custom guitar/keys splitter
