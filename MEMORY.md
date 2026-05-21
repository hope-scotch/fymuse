# FYMuse — Project Memory

A single-file music theory + songwriting + audio-analysis tool. Explore chord progressions across genres, compose with rhythm subdivisions, write song sections with lyrics, find connections between any two chords, listen to live audio for real-time chord detection, and split full songs into stems with per-stem chord/note analysis.

Open `index.html` directly in any modern browser for everything except the Splitter's ML mode (which needs cross-origin isolation — see Local dev / Deploy below).

---

## File structure

```
FYMuse/
├── index.html    # The whole app — single HTML file (~340KB)
├── logo.png      # FYmuse brand mark (cropped FYMUSE wordmark, orange)
├── server.py     # Tiny local dev server (sets COOP/COEP for ML mode)
├── _headers      # Cloudflare Pages response headers (auto-applied on deploy)
├── README.md     # User-facing readme: run/deploy instructions
├── MEMORY.md     # This file
└── docs/
    └── CUSTOM_OTHER_SPLITTER.md  # Design doc: custom guitar/keys splitter (parked)
```

The HTML file contains everything: HTML structure, CSS, JS, music theory engine, audio synthesis, UI rendering, DSP pipelines (HPSS, FFT, STFT, HPS, Krumhansl-Schmuckler), and ML-mode loaders. External dependencies are loaded from CDNs.

## Local dev / deploy

- **Most features work from `file://`** — open `index.html` directly.
- **Splitter ML mode** needs SharedArrayBuffer = COOP/COEP headers. For local dev: `python3 server.py` then open `http://localhost:4747/`. For production: Cloudflare Pages picks up the `_headers` file automatically — no build step, just push the repo.

---

## External dependencies (CDN-loaded)

- **Inter** + **JetBrains Mono** + **Space Grotesk** fonts → `fonts.googleapis.com`
- **Phosphor Icons** (duotone style) → `unpkg.com/@phosphor-icons/web@2.1.1`
- **Tone.js v14.8.49** → `cdnjs.cloudflare.com`
- **Salamander piano samples** (only when "Piano" instrument selected) → `tonejs.github.io/audio/salamander/`

Internet required on first load; thereafter the page works offline if cached.

---

## Top-level layout

```
┌─ HEADER ─────────────────────────────────────────────────────────────────────┐
│ [logo.png] │ [Playground][Path Finder][Melody Mode][Custom Chord]         │
│            │ [Listener][Splitter][Songwriter][Sidebar] │ Key │ Sound      │
│ Tempo Loop Metronome │ Genre pills (Pop, Rock, …)                         │
├─ MAIN ────────────────────────────────────────────────┬─ INFO SIDEBAR ──────┤
│  GRAPH PANEL or PLAYGROUND VIEW                       │  Mood filter        │
│  (main panel — does NOT shrink when side panels open) │  Signature progs    │
│                                                       │  Chord detail       │
│                                                       │  Substitutions      │
├──────────── BUILDER DRAWER (right edge moves to 460px ┴──────────────┬──────┤
│             when a side panel is open) ──────────────────────────────│      │
└──────────────────────────────────────────────────────────────────────┴──────┘
```

Three overlay panels (sit on top of the main layout, fixed-position):
- **Songwriter shutter** slides down from below the header (top overlay)
- **Path Finder**, **Melody Mode**, and **Custom Chord** slide in from the right edge as 460px-wide overlays — **mutually exclusive** (only one open at a time). They overlay the right side without shrinking the main panel.

Main view modes (mutually exclusive — they swap children of `#graph-panel`):
- **Genre graph** (default) — chord nodes + transition arrows for the selected genre
- **Playground** — every musically useful chord in the current key, by category
- **Listener** — real-time mic chord detection + suggestions, OR uploaded audio file (full-width, no info-sidebar)
- **Splitter** — upload a song, split into stems, multi-track playback + per-stem chord/note analysis (full-width, no info-sidebar)

Toggleable layout columns:
- **Info Sidebar** (right column, inline) — hidden/shown via the "Sidebar" header button. When hidden, main panel reflows wider.
- **Builder Drawer** (bottom, fixed) — collapsed (40px tab) → expanded (320px) → fullscreen (75vh). When a side panel is open, the builder's right edge shrinks to 460px so the side panel and builder don't overlap.

Layout precedence: side panels (Path Finder / Melody Mode) > info sidebar > main panel > builder. Side panels keep their fixed 460px regardless. Main panel never shrinks because of side panels (they're overlays). Builder defers to side panels.

---

## Features

### Genre Graph (default)
10 genres: **Pop, Rock, Blues, Jazz, R&B/Soul, Country, EDM/House, Lo-fi/Hip-Hop, Bossa Nova, Gospel**.

Each genre has:
- **Chord nodes** positioned by harmonic function (tonic = orange, subdominant = cyan, dominant = red, borrowed = purple, passing/dim = grey)
- **Weighted transition arrows** (thicker = more common move in this genre)
- **Signature progressions** with example songs and mood tags
- **Substitutions / modal interchange tips**

Hover any chord → its outgoing arrows highlight orange, incoming cyan, unrelated arrows dim. Click → locks the focus and opens the chord detail panel in the right sidebar. Click empty space to unlock.

"Walk the graph" button does a weighted random walk through 8 chords ending on tonic.

### Playground (own header button — not a genre)
Every musically useful chord in the current key, organized by category:
- **Diatonic Triads / Diatonic 7ths / Extensions (9th-13th) / Suspended (sus2-sus4)**
- **Borrowed from Parallel Minor** (or **Parallel Major** + **Harmonic Minor Color** if in minor mode)
- **Secondary Dominants** (each labeled with its target chord)
- **Chromatic / Advanced** (tritone subs, passing diminished)

Mode-aware: switching to a minor key (e.g. "A minor") changes the diatonic categories to use natural-minor numerals (`i`, `ii°`, `III`, `iv`, `v`, `VI`, `VII`).

Each card has a quick-add **+** button on hover that pushes the chord to the Builder without opening the detail panel.

**Keyboard shortcuts**: every card gets a key from the pool `1234567890qwertyuiopasdfghjklzxcvbnm` (~36 keys, covers all chords). Shown as a small badge in the card's bottom-left corner. Pressing the key plays that chord and flashes the card orange. Shortcuts fire only when Playground is the active view, ignored when focus is in an input/textarea/select or any modifier key (Cmd/Ctrl/Alt) is held. Mapping rebuilds on every `renderPlayground()` so it stays in sync with key/mode changes. State: `playgroundKeyMap` (key char → `{numeral, chord, card}`).

### Builder (bottom drawer)
- Queue of chord chips with **rhythm subdivisions** (whole, dotted half, half, dotted quarter, quarter, dotted 8th, 8th, triplet 8th, 16th, triplet 16th)
- Each chip has a rhythm dropdown that sets the chord's duration
- **Drawer body controls**: **Play / Stop / Rest / Clear** in one row (Stop and the others all live here now — moved out of the playground/graph headers)
- **Rest button** inserts a silent gap with the same rhythm options
- **Drag chips left/right** to reorder
- **× to remove**
- Three drawer states: **collapsed** (40px tab) → **expanded** (320px) → **fullscreen** (75vh)
- Tab summary shows queue preview, audio status, and quick-Play button

### Songwriter (top shutter)
- Slides down from below the header (cubic-bezier 0.32s)
- **+ Save current Builder as section** auto-names ("Verse 1", "Chorus", "Verse 2", "Chorus", "Bridge", …)
- **+ Empty section** for blank slate
- Each section has:
  - Editable name input
  - Chord progression display (chord names + rhythm in parens if non-default)
  - **▶** play, **+ Append** Builder queue, **↑ Load** into Builder, **× Delete** buttons
  - **Lyrics textarea** with `[ChordName]` markup
  - **Live preview** showing chords above words (chord markers parsed via `romanToChord` so `[ii7]` in C major shows as `Dm7`)
- Backdrop dimmer behind it, ESC / X / backdrop click closes

### Path Finder (right-side overlay panel)
- Toggled from the header button (mutually exclusive with Melody Mode and Custom Chord)
- 460px fixed-position overlay sliding from the right
- Pick chord A and chord B from dropdowns — **OR drag any chord card / graph node onto the From/To dropdown** (drop target highlights orange when hovering with a drag)
- If the dragged chord's numeral isn't in the static dropdown list, it's added as a new option on the fly via `romanToChord` lookup
- Returns 6 path templates between them:
  1. **Direct** — A → B
  2. **V7 setup** — A → V7-of-B → B
  3. **ii–V approach** — A → ii-of-B → V7-of-B → B
  4. **Tritone substitution** — A → ♭II7-of-B → B
  5. **Chromatic mediant** — A → major-third-up-of-A → B
  6. **Diminished passing** — A → ♯IVdim7-of-B → B
- Each card has Play / + Builder buttons
- Adding to Builder converts each concrete chord back to a Roman numeral relative to the current key+mode (via `findRomanForChord`) so the queue retransposes if you change keys

### Melody Mode (right-side overlay panel)
- Toggled from the header button (mutually exclusive with Path Finder and Custom Chord)
- 460px fixed-position overlay sliding from the right
- Type space-separated melody notes (e.g. `C D A B`)
- For each note, get up to 7 chord candidates ranked by:
  - **Diatonic-fit** (chord whose root is in the current scale scores higher)
  - **Voice leading** (shared notes with the previously picked chord)
  - **Chord type** (triads/7ths preferred over diminished)
- Pick chords sequentially; finalize pushes them all to the Builder

### Listener (full main view — like Playground)
- Toggled from the header "Listener" tool button. Like Playground, it's modeled as a special "genre" (`GENRES.listener`, `isListener:true`) that takes over `#graph-panel`. When active: `state.genreKey === 'listener'`, `body.view-listener` class is set, the info-sidebar is hidden via CSS, and `#graph-panel` reflows to full width.
- **Two-column layout** (`.listener-grid`, `5fr | 7fr`, collapses to single column under 1100px): left column = detection (big detected chord, alternates, live chroma), right column = suggested next chords + tips.
- Mutually exclusive with the chord graph + Playground (clicking any genre pill or the Playground button switches `state.genreKey` and renderAll exits Listener). Side panels (Path Finder / Melody Mode / Custom Chord) can still open over the top.
- **Real-time chord detection from the mic** + suggestions for the next chord
- "Start listening" button kicks off `getUserMedia({ audio: {echoCancellation:false, noiseSuppression:false, autoGainControl:false} })`. Mic is **never connected to destination** — no monitoring, no feedback risk.
- Audio path: `MediaStreamSource → AnalyserNode (FFT 8192, smoothing 0.4)` and a parallel `AnalyserNode (time-domain, 2048)` for an RMS level meter. Reuses Tone's audio context if available (`Tone.context.rawContext`), else creates its own.
- **Chroma extraction (CQT-style)**: built via precomputed log-frequency note kernels (`buildListenerNoteKernels()` runs once at start). One kernel per MIDI note from C2 to C6 = 49 kernels. Each is a list of `(binIndex, weight)` pairs with a triangular profile centered on the note's frequency, ±50 cents half-width. Per frame: sum FFT magnitudes weighted by each kernel into per-note energies, then aggregate into 12 PC bins. This gives semitone-resolution log-frequency chroma using the existing FFT — no DSP rewrite. Replaces the old simple bin→PC mapping which under-resolved low pitches.
- **Median + low-pass smoothing**: raw chroma goes through a 3-frame element-wise median (kills transient spikes from cymbals, sibilance, room noise) before an EMA low-pass (alpha=0.55) into the smoothed chroma used for matching.
- **Bass detection**: same kernel pass also accumulates a separate low-band chroma (kernels with center freq ≤ 180 Hz). Argmax = bass pitch class, dropped if not clearly ahead of 2nd strongest in band. Used for slash-chord display + inversion labels + a 1.15× score boost for candidates whose root matches the bass (`LISTENER_BASS_BOOST`).
- **Adaptive noise floor**: EMA tracks ambient RMS during quiet frames; the silence threshold is `noiseFloorEma + 6 dB`. Floor is bounded between –90 dB and –45 dB so it can never get pinned high by sustained loud input. Slow drift up vs fast drift down (alpha 0.001 vs 0.015). Replaces the previous hard-coded –60 dB threshold.
- **Tuning offset estimate (informational only — NOT applied)**: per-frame magnitude-weighted average of cents-deviation from equal temperament, fed into a slow EMA (alpha=0.04). Capped at ±50 cents and only computed after 30+ confident frames. Surfaced in the UI as `input ±N¢` when |offset| ≥ 12¢. Auto-correction was deliberately disabled — the kernel-PC shift was a step function (no-op below 50¢, full semitone jump above) which caused over-correction. Continuous correction would require per-frame kernel rebuilds and is still risky on detuned instruments / vibrato.
- **Onset detection**: spectral flux (sum of positive frame-to-frame magnitude deltas) tracked against an EMA baseline (`fluxAvg`). When `flux > 2.5× baseline` (and an absolute floor), the rolling vote + locked key are reset so a newly-struck chord locks in within ~4 frames instead of fighting the previous one for the full HISTORY_SIZE.
- **Chord matching**: 12 root candidates × 10 quality templates (`'', m, 7, maj7, m7, sus4, sus2, dim, aug, m7b5`). Each template is built from a **harmonic series profile** (`LISTENER_HARMONIC_PROFILE` — h1/h2/h4/h8 octaves, h3/h6 fifths, h5 maj3, h7 m7) summed at every chord tone, so the templates "expect" realistic overtone bleed. Score = cosine similarity × per-template prior weight × bass-bias (if applicable). Top results sorted by score.
- **Smoothing + hysteresis**: rolling history of last 14 top-1 frames, weighted majority vote per `root:quality` key. Once a chord is locked, a new candidate must beat the locked one's tally by 10% to take over (`LISTENER_HYSTERESIS = 1.10`). Below the adaptive silence threshold, frames count as silence and bleed history without pushing.
- **Honest confidence display** (`listenerState.topGap`): replaces the old "X% match" (which was just the top score normalized to itself, meaningless). Confidence label is derived from the gap between top-1 and top-2 scores: **locked in** (≥15%, green), **stable** (5–15%, orange), **ambiguous** (<5%, red). The actual gap percentage is shown alongside.
- UI elements: live level meter (RMS dB) — only visible while listening (`#listener-view.is-listening` class); big detected chord name with slash-chord notation when bass differs from root, Roman numeral in the current key, honest confidence label + gap %, optional `input ±N¢` tuning readout; top-3 alternates with proper percentage bars (`display:block` + gradient fill); live 12-bin chroma bar chart; "Suggested next chord" grid.
- **Suggestion engine** (`suggestNextChords(detectedChord)`):
  1. Genre transitions — if `state.genre.transitions` exists and the detected chord's Roman numeral matches a `from`, every matching `[from, to, weight]` row contributes a suggestion at weight `0.5 + 0.5·w`.
  2. Universal moves — `LISTENER_UNIVERSAL_MOVES` table mapping common Roman numerals to canonical destinations (V→I, ii→V, IV→I, vi→IV, i→iv/V/VI/VII, ♭VII→IV, etc.) with theory-based reasons.
  3. **V7 of detected** — synthesizes a dominant 7 a fifth above the detected chord, for "set up returning to X" moves even when the detected chord is non-diatonic.
  4. **IV of detected** — plagal predecessor.
  Suggestions deduped by chord name, sorted by weight, top 6 returned.
- **Suggestion cards** rendered as a responsive grid (`auto-fill, minmax(230px, 1fr)`, gap 10px). Each tile: from→to flow ("C → G", suggested chord at 24 px font-weight 700), Roman-numeral badge in the corner, chord notes (`G · B · D`), the reason in body text, and three labeled action buttons — **Play** (orange-accent primary, plays just the suggestion), **Pair** (plays detected → suggestion preview), **Add** (auto-prepends detected if not already last, then appends suggestion to Builder). Hover lifts the tile by 1px with a soft shadow.
- **Click any chord card → opens chord detail panel** (existing info-sidebar machinery). `openListenerChordDetail(chord)` derives the Roman numeral via `findRomanForChord`, sets `state.selectedChord`, adds `body.has-chord-detail`, calls `renderChordDetail()`. Click the same card again to close (toggle), or click another to swap. CSS shows the info-sidebar in listener mode only when `.has-chord-detail` is set, and hides every section except `#chord-detail-panel`. Active card gets an orange highlight (`is-active-detail`). An **X close button** sits at the top-right of `#chord-detail-panel` (only shown in listener view) for explicit close. Non-diatonic chords flash an inline tip ("change Key to see voicings") instead of opening an empty detail. Highlights synced via `syncListenerActiveCard()`.
- Mic auto-stops on: leaving Listener view (any other genre pill / Playground / etc — handled inside `renderAll` by checking `listenerState.active && !state.genre.isListener`) and on tab hide (`visibilitychange`).
- View skeleton is built lazily on first activation by `buildListenerViewSkeleton(root)`, which inserts a `<div id="listener-view">` inside `#graph-panel`. `showListenerView()` mirrors `showPlaygroundView()` — toggles sibling `#graph-panel` children to `display:none` while the listener view is active. `renderListener()` (called from `renderAll`) restores any prior detection if the user toggles in/out.
- **Audio file upload mode** — alternative to live mic. "Upload audio" button + hidden `<input type="file" accept="audio/*">` + drag-drop on the listener view. `listenerLoadFile(file)` decodes via `AudioContext.decodeAudioData` and creates a `BufferSource` that feeds the same FFT/time analysers AND `ctx.destination` (so the user hears it). A small file player UI under the level meter — play/pause / filename / progress bar / time / X close. Mic and file are mutually exclusive: uploading auto-stops the mic; mic toggle is disabled while a file is loaded. Same chord-detection chain runs unchanged.
- State: `listenerState` — `{active, audioCtx, micStream, source, fftAnalyser, timeAnalyser, fftBuffer, timeBuffer, rafId, smoothChroma, history, lastShown, mode, fileBuffer, fileSource, filePlaying, fileStartCtxTime, fileOffset, …}`.

### Splitter (full main view — like Listener / Playground)
Upload a song, split it into stems, multi-track playback with per-stem volume / mute / solo + scrolling notation. Modeled like Playground (`GENRES.splitter` with `isSplitter:true`); takes over `#graph-panel` via `showSplitterView()` + lazy `buildSplitterViewSkeleton()`.

**Quality modes** (toggle in the header):
- **Fast (DSP)** — default. On-device HPSS-based pseudo-separation. ~30s for a 3-min song. 4 stems: original / harmonic / bass / drums. Approximate quality — drums vs harmonic separates well; isolating individual instruments out of the harmonic bucket isn't possible with DSP alone.
- **Accurate (ML — Demucs)** — lazy-loads ONNX Runtime Web from jsdelivr (~3 MB) + the `demucs-web` ES module from esm.sh, then fetches the 172 MB `htdemucs_embedded.onnx` from Hugging Face's static hosting (one-time, browser-cached). Inference runs entirely in the browser (WebGPU when available, WASM otherwise). 5 stems: original / vocals / drums / bass / other. ~3-5 min per 3-min song with multi-thread WASM (needs COOP/COEP via `server.py` or `_headers`); ~15-25 min single-thread fallback.

An auto-detected environment warning explains exactly which speed tier the user will get (file:// vs HTTP-with-COOP/COEP vs WebGPU).

**DSP separation pipeline** (`splitterProcess`):
1. Mix to mono.
2. **HPSS pass 1** via `splitterHPSSFloat` — Driedger-Müller harmonic/percussive source separation. STFT (2048-pt, 512 hop) → magnitude spectrogram → median filter along time (kernel 31 → harmonic ref) and along frequency (kernel 31 → percussive ref) → soft Wiener masks `H = h^p / (h^p + p^p)` with p=3 → apply masks to magnitudes, iSTFT each → harmonic₁ + percussive₁.
3. **HPSS pass 2** runs on percussive₁: any sustained content that leaked into the percussive bucket gets recovered as pass-2 harmonic and merged back into the final harmonic stem. Final percussive = pass 2 percussive (a tighter drum stem).
4. **Bass extraction**: lowpass the original mix at 280 Hz (BiquadFilter via `OfflineAudioContext`), then HPSS on that low band → take the harmonic output. So Bass = harmonic content of the bass band, not lowpass-of-harmonic — kicks get caught by HPSS percussive instead of leaking through.

**ML separation pipeline** (`splitterProcessML`):
- `splitterEnsureMLLibsLoaded` injects ORT via `<script>` tag (UMD) and ES-imports `demucs-web` from esm.sh. Configures `ort.env.wasm.numThreads` based on SharedArrayBuffer availability. Tries WebGPU adapter first, falls back to WASM execution provider.
- `DemucsProcessor.separate(left, right)` returns `{drums, bass, other, vocals}` as L/R Float32Array pairs.
- Progress callbacks map cleanly to the existing progress bar (download phase 5–15%, model load 16–19%, inference 20–98%).
- Each output becomes a stereo `AudioBuffer` and feeds the same mixer as DSP mode.

**Multi-track mixer + transport**:
- Each stem has a `BufferSource` + `GainNode`. All sources start at the same `ctx.currentTime` so they're sample-aligned.
- Mute / solo / volume per stem update each gain instantaneously. Solo logic: any stem soloed → only soloed (non-muted) stems play.
- Master transport: play/pause/stop, filename, gradient progress bar, current/total time, X close.
- **Click-to-seek** on the master bar AND on every stem timeline. `splitterSeek(targetSec)` stops sources, sets `pausedAt`, resumes from new offset (if was playing) or just updates UI.
- Space bar = play/pause when Splitter view is active and a song is loaded (ignored when typing in inputs/textareas/contenteditable).

**Per-stem timeline strip** (under each track's controls row):
- 44 px tall. Three layers:
  1. **Waveform** — 400 buckets of normalized peak amplitude rendered as SVG rects at 20% opacity in `--accent-2`, bumped to 28% `--accent` when soloed.
  2. **Click-to-seek** — clicking anywhere = seek the global playhead to that time. `stopPropagation` so it doesn't open the notes modal.
  3. **Cursor** — animated 2px orange line synced to playback via `splitterUpdateStemCursors()` in the RAF tick.
- Inline event labels (chord/note names) are deliberately NOT rendered on the strip — the strip stays clean. Click the stem to open the notes modal where every event is visible.

**Click any stem → notes modal** (a true piano roll):
- Vertical axis = MIDI pitch (lower notes lower on screen, higher notes higher), horizontal axis = time.
- **Sticky-left keyboard column** (64 px) labels every MIDI row. Black-key rows are darker; C rows highlighted bold so octaves are easy to count. Stays put during horizontal scroll.
- Each detected event = a horizontal bar at its MIDI row spanning [start, end] in time. Hover lifts and brightens; the event the playhead is currently inside fills solid orange (`is-current`). Click an event → seek there.
- For chord events (no single pitch), the chord's root letter+accidental is parsed via `splitterChordRootMidi()` and the bar lands at that root in octave 4 — so different roots stay correctly ordered vertically.
- **Horizontal-stretch slider** (10–2000 px/sec) + `−` / `+` buttons + percentage readout. Single source of truth: `splitterSetModalZoom`.
- **Pinch-zoom**: 2-finger touch on touchscreens, OR Ctrl/Cmd+wheel on trackpads (macOS pinches naturally fire wheel events with `ctrlKey:true`). Both anchor zoom to the focal point (touch midpoint or cursor X) so the time under the user's focus stays put while everything else stretches around it. `splitterZoomAround(newPxPerSec, anchorScreenX)`.
- **Auto-scroll** during playback keeps the cursor about 1/3 from the left edge of the visible window.
- **Time axis** below the events with ticks snapped to a "nice" interval (0.5 / 1 / 2 / 5 / 10 / 15 / 30 / 60 sec) chosen based on zoom.
- **Notation toggle** — three-way segmented control: `ABC` (Western, default) | `Sa Re` (Hindustani sargam, Latin) | `सा रे` (sargam, Devanagari). Affects keyboard column + monophonic event bar labels (chord names stay Western — chords aren't a sargam concept). Tooltip on each bar still shows the original Western label so the user can cross-reference.
- **`Sa = ?` dropdown** appears when notation is non-Western. 12 options C..B. Auto-set from the song's detected key on first open per song; an `AUTO` cyan badge appears next to the dropdown until the user manually overrides.

**Per-stem analysis pipeline** (`splitterAnalyzeStems`):
- After processing finishes, runs three phases with status updates:
  1. Waveform peaks (cheap, ~1 s).
  2. **Song key detection** via `splitterDetectSongKey(originalBuffer)` — Krumhansl-Schmuckler key finding. 2048-pt FFT @ 50% overlap, per-frame chroma normalized then accumulated, Pearson correlation against the 24 canonical key templates (12 major + 12 minor probe-tone profiles, Krumhansl 1990). Returns `{root, mode, confidence}`. Stored on `splitterState.detectedKey`. Synthetic test: C/G/F♯/Am/Dm all detect at 0.91-0.95 confidence.
  3. **Per-stem event detection**, dispatched by stem id:
     - `harmonic` / `other` / `original` → `splitterDetectChords`. 4096-pt FFT, 0.5 s hop. Kernel chroma → `listenerScoreChroma`. **2-frame stability filter**: a chord candidate has to win two frames in a row before it's committed (suppresses single-frame mis-detections). Min event 0.7 s.
     - `vocals` → `splitterDetectMonophonicNotes` with **aggressive** settings: 0.06 s hop (~16 fps), no smoothing (`smoothFrames: 1`), 30 ms min event. Catches fast runs.
     - `bass` → same engine with **conservative** settings: 0.20 s hop, 8192 FFT (better low-pitch resolution), 5-frame median, 180 ms min event.
     - `drums` / `percussive` → skipped (no chord/note semantic).

**Monophonic pitch detection — Harmonic Product Spectrum** (`splitterDetectMonophonicNotes`):
- Per frame: forward FFT → magnitude spectrum → for each candidate fundamental bin `b` in `[minHz, maxHz]`, compute the HPS product `mag[b] * mag[2b] * mag[3b] * mag[4b] * ...`. The product peaks at the true fundamental because all its harmonics line up there. Standard fix for vocal pitch tracking — vastly more reliable than raw spectrum argmax which can lock onto octave harmonics.
- **Parabolic peak interpolation** in log-magnitude around the best bin gives sub-bin (cents-accurate) frequency precision before quantizing to nearest semitone.
- **Adaptive silence/unvoiced gate**: per-song HPS-peak-strength median × 0.15 = strength threshold. Frames below that are dropped (silence, breath, unvoiced consonants like "s/f/t" with no clear pitch). Adapts to recording level automatically.
- Optional N-frame median smoothing (skips silence in window). Bass uses 5; vocals use 1 (off) to preserve every fast pitch change.

**State**: `splitterState` — `{audioCtx, fileBuffer, fileName, stems, processing, status, playing, startCtxTime, pausedAt, duration, rafId, mode ('dsp'|'ml'), mlReady, mlProcessor, mlModelLoaded, detectedKey, …}`. `splitterModalState` — `{open, stemId, pxPerSec, rafId, notation ('western'|'sargam'|'devanagari'), sa, saAutoDetected}`.

### Custom Chord (right-side overlay panel)
- Toggled from the header button (mutually exclusive with Path Finder, Melody Mode)
- 460px fixed-position overlay sliding from the right
- Stack any combination of triad + 7th + 9th + 11th + 13th to build a chord like `Cm7add9add11`
- Pill-button rows for: Root (12 notes), Triad (maj/min/dim/aug/sus2/sus4), 7th (none/dom7/maj7), 9th (none/9/♭9/♯9), 11th (none/11/♯11), 13th (none/13/♭13)
- Live result panel shows the built chord name and the actual notes
- **Play chord** auditions it through the current instrument
- **+ Add to Builder** pushes it into the Builder queue as a concrete chord (`{chord, rhythm}` queue item — stays absolute, doesn't retranspose with key changes; that's intentional for hand-built chords)
- Implementation uses `TRIAD_INTERVALS`, `SEVENTH_INTERVAL`, `NINTH_INTERVAL`, `ELEVENTH_INTERVAL`, `THIRTEENTH_INTERVAL` lookup tables plus `customChordState` and `buildCustomChord()`

### Info Sidebar (right-side inline column, toggleable)
- Toggled from the "Sidebar" header button (visible by default)
- Contains: Mood Filter (genre views only) → Signature Progressions / Common Templates → Chord Detail (when a chord is selected) → Substitutions & Modal Interchange
- When hidden via toggle, `main > aside:not(.side-panel).collapsed` collapses to `flex-basis: 0`, animated, and the main panel reflows to fill the freed space
- Independent from Path Finder / Melody Mode — they can all be visible simultaneously (side panels overlay on top of the sidebar in that case; toggle the sidebar off to see only the side panel)

### Sound (8 instruments)
| Name | Implementation |
|------|----------------|
| Poly Synth | `PolySynth(MonoSynth)` fattriangle (count 2, spread 12) → lowpass with filter envelope (movement) → chorus → reverb |
| Piano (sampled) | `Sampler` with Salamander piano samples (untouched — sounds great) |
| Electric Piano | `PolySynth(FMSynth)` harmonicity 1.999 (octave-up modulator = metallic tine), modulationIndex 6, sharp percussive envelope → tremolo (4.5 Hz) → chorus → EQ → room reverb |
| Acoustic Guitar | `PolySynth(MonoSynth)` fatsawtooth + strong filter envelope (lowpass sweeps high→low fast = pluck attack) → body resonance peaking filters at 220 Hz + 1.5 kHz → highpass → EQ → reverb |
| Clean Electric Guitar | `PolySynth(Synth)` sawtooth → light overdrive → cab filter → EQ → chorus → spring reverb (untouched — sounds great) |
| Strings (ensemble) | `PolySynth(Synth)` fatsawtooth (count 4, spread 50), slow attack 0.9s → vibrato (5.5 Hz) → highpass → lowpass → deep chorus (0.7 Hz, depth 0.7, 50% wet) → 4s hall reverb at 40% wet |
| Organ | `PolySynth(FMSynth)` harmonicity 2 (octave-up drawbar) additive timbre → vibrato (rotor pitch) + tremolo (rotor amp) Leslie sim → EQ → plate reverb |
| Distorted Guitar (Muse/LP) | synth → pre-EQ mid-bump (Tube-Screamer "honk") → heavy distortion → HP → cab sim → smile-curve EQ (3/-3/2) → compressor → ping-pong delay (32n, 12% feedback) stereo widener → plate reverb → limiter |

Each factory disposes its own effect chain on instrument switch.

### Transport (header)
- **Tempo slider** 50–200 BPM (orange accent)
- **Loop checkbox**
- **Metronome button** with pulse indicator (red dot on downbeat / orange on other beats; high pitch C5 on beat 1, low pitch G4 on beats 2-3-4)

### Metronome sync
When the metronome is running and you hit Play (anywhere — Builder, signature progression card, song section, path finder card, walk-the-graph), playback waits for the metronome's next downbeat (the "1") so the progression locks to the click. If the metronome is off, playback starts immediately (Tone.now() + 100ms).

Implementation: `metronomeState.startTime` records the Tone clock time at which the metronome's first beat fired; `nextDownbeatToneTime()` computes the next multiple-of-4 beat from there; `playProgression` uses it as `startTime` if no explicit `startAt` option is provided.

---

## Music theory engine

### Constants
```js
NOTES_SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
NOTES_FLAT  = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B']
MAJOR_INTERVALS = [0,2,4,5,7,9,11]
MINOR_INTERVALS = [0,2,3,5,7,8,10]   // natural minor
```

### Chord types
`CHORD_TYPES` map: '', 'm', 'dim', 'aug', '7', 'maj7', 'm7', 'm7b5', 'dim7', 'sus2', 'sus4', '7sus4', '9', 'maj9', 'm9', '13', '7alt' — each with `intervals` (semitones from root) and `label`.

### Roman numeral parsing
- `parseRoman(numeral)` → `{ degree, accidental, quality }`
  - Handles `♭`/`b` and `♯`/`#` prefixes (multi-character supported)
  - Roman match: `I`, `II`, `III`, `IV`, `V`, `VI`, `VII` (uppercase = major default, lowercase = minor default)
  - Suffix patterns: `°`, `dim`, `dim7`, `°7`, `ø`, `m7b5`, `maj7`, `maj9`, `m7`, `m9`, `13`, `9`, `7sus4`, `7alt`, `7`, `sus2`, `sus4`
- `romanToChord(numeral, key, mode)` → `{ root, quality, type, notes, name, numeral }`
  - Picks `MAJOR_INTERVALS` or `MINOR_INTERVALS` based on `mode` (defaults to `state.mode`)
  - Adds parsed accidental
  - Resolves to absolute root note
  - `shouldUseFlats(key, mode)` decides accidental spelling per key signature
- `findRomanForChord(chord, key, mode)` reverse-engineers a numeral string from a concrete chord (used when adding Path Finder / Melody Mode chords to the Builder so they retranspose when key changes)

### Voicings
- **Piano**: `pianoVoicings(chord)` returns array of `{ name, notes: [midi] }`. Variants: root position, 1st inv, 2nd inv, open/spread (with bass an octave below), shell (R-3-7) for chords with a 7th, rootless (3-5-7-9) for 5-note chords, power chord (R-5-R)
- **Guitar**: `guitarVoicings(chord)` uses CAGED-style shape library `GUITAR_SHAPES` keyed by chord quality. Shapes have `refRoot` + `pattern` (6 frets, low E to high e). Transposed via `transposeShape(shape, targetRoot)` which adds the offset. Power chord shapes always appended to output.
- **Guitar diagram orientation**: horizontal flip — nut on the right, low E on top, frets count right-to-left (player's-eye view of own neck)

---

## State

### `state` (top-level UI state)
- `genreKey`: 'pop' | 'rock' | … | 'playground'
- `genre`: reference to GENRES[genreKey]
- `key`: 'C' | 'C#' | 'D' | … | 'B'
- `mode`: 'major' | 'minor'
- `selectedChord`: numeral string or null (for chord detail / graph focus)
- `selectedMoods`: Set of mood tag strings
- `voicingMode`: 'piano' | 'guitar'
- `voicingIndex`: 0..N (which voicing variant is shown)

### Layout state (DOM-driven, not in a JS object)
- `body.side-panel-open` class — set when any `.side-panel` has the `.open` class. Controls builder shrinking via CSS.
- `#info-sidebar.collapsed` class — set when user clicks the Sidebar header button. Triggers `flex-basis: 0` collapse.
- `.side-panel.open` class — set per-panel when opened. CSS uses this for the slide-in transform.
- Helper: `syncBodyPanelState()` reads any `.side-panel.open` and toggles the body class accordingly. Called from open/close/toggle paths.

### `builderState`
- `queue`: array of `{ numeral, rhythm }` (Roman numeral) | `{ rest: true, rhythm }` (silent gap) | `{ chord, rhythm }` (custom absolute chord, e.g. from Custom Chord panel)
- `bpm`: number (50..200)
- `loop`: boolean
- `playing`: boolean (set during active playback)
- `clickMode`: legacy field (always 'inspect' now — mode toggle was removed)

### `customChordState`
- `root`: 'C' | 'C#' | … | 'B'
- `triad`: 'maj' | 'min' | 'dim' | 'aug' | 'sus2' | 'sus4'
- `seventh`: 'none' | 'dom7' | 'maj7'
- `ninth`: 'none' | '9' | 'b9' | '#9'
- `eleventh`: 'none' | '11' | '#11'
- `thirteenth`: 'none' | '13' | 'b13'

### `songState`
- `sections`: array of `{ id, name, chords: [...same as builder queue], lyrics: string }`
- `nextId`: incrementing section ID

### `listenerState`
- `active`: boolean — whether mic + RAF loop are running
- `audioCtx`: AudioContext (reuses Tone's `context.rawContext` if available, else fresh)
- `micStream`: MediaStream from getUserMedia
- `source`: MediaStreamAudioSourceNode
- `fftAnalyser`: AnalyserNode (fftSize 8192, smoothing 0.4) — chroma source
- `timeAnalyser`: AnalyserNode (fftSize 2048, smoothing 0) — RMS / level meter
- `fftBuffer`: Float32Array of frequency-bin dB
- `timeBuffer`: Float32Array of time-domain samples
- `rafId`: requestAnimationFrame handle for the analysis loop
- `smoothChroma`: Float32Array(12), low-passed pitch-class energies
- `rawChromaHistory`: last 3 raw chroma frames (for median smoothing)
- `prevSpectrum`: Float32Array of last frame's linear-magnitude spectrum (for spectral flux)
- `fluxAvg`: EMA of spectral flux — onset detection baseline
- `bassPc`: currently detected bass pitch class (or -1 if ambiguous/silent)
- `lockedKey`: 'root:quality' of the currently locked chord (for hysteresis)
- `noteKernels`: precomputed log-frequency CQT-style kernels (per MIDI note from C2-C6); built once via `buildListenerNoteKernels()` on listener start
- `noiseFloorEma`: adaptive RMS noise floor in dB (EMA, capped between -90 and -45)
- `tuningOffsetCents`: estimated global tuning offset (cents) — surfaced in UI but **not** auto-applied to chord matching
- `tuningEma`, `tuningSamples`: EMA + sample counter for the tuning estimate
- `topGap`: last frame's top-1 vs top-2 score gap (0..1) — drives the honest confidence label
- `history`: rolling array of last N top-1 detection frames `{root, quality, score}`
- `HISTORY_SIZE`: 14
- `lastShown`: last stable chord pushed to UI `{root, quality, name, chord, score, since}`
- `lastBuilt`, `lastSuggestUpdate`: timestamp gates so the alternates list / suggestions don't rebuild every frame

### `metronomeState`
- `active`: boolean
- `intervalId`: setInterval handle
- `click`: Tone.MembraneSynth instance
- `beat`: counter
- `startTime`: Tone clock time of first beat (used for sync)

### `melodyState`
- `notes`: array of note name strings
- `selections`: array of chord objects (one per note, null until picked)

---

## Audio architecture

`playProgression(items, key, bpm, options)` is the central audio function.
- `items` accepts: array of Roman numeral strings, queue items `{numeral, rhythm}` / `{rest, rhythm}` / `{chord, rhythm}` (custom), concrete chord objects (from Path Finder), or any mix
- Resolves each via `resolve(item)` to a chord object
- Schedules audio with `Tone.now() + offset` for sample-accurate timing (cumulative `loopOffset`)
- Schedules highlight callbacks via `setTimeout` (real time, NOT cumulative — each iteration's setTimeout is from its call time)
- `options.startAt` overrides start time (used for metronome sync)
- `options.loop` reschedules a new iteration when the cycle ends
- `activeEvents` tracks all setTimeout IDs for cancellation via `stopAllAudio()`

### Per-chord rhythm
`RHYTHMS` map defines beat-duration per rhythm key:
- `whole` (4 beats), `dot_half` (3), `half` (2), `dot_qtr` (1.5), `quarter` (1), `dot_8th` (0.75), `8th` (0.5), `trip_8th` (1/3), `16th` (0.25), `trip_16` (1/6)

A chord's audio scheduling: `dur = rhythm.beats * beatSec`, plays once at `startTime + cumOffset` for `dur * 0.95` (slight gap for articulation).

---

## Render functions

| Function | Purpose |
|----------|---------|
| `renderAll()` | Full re-render — called on most state changes. Cascades to all sub-renders. |
| `renderGenrePicker()` | Header pills (skips 'playground') |
| `renderKeyPicker()` | 24 entries: 12 keys × {major, minor} |
| `renderInstrumentPicker()` | Sound dropdown |
| `syncHeaderButtonStates()` | Toggle .active on Playground button |
| `renderGraph()` | SVG chord graph for current genre |
| `renderPlayground()` | Chord palette categories |
| `renderMoods()` / `renderProgressions()` / `renderChordDetail()` / `renderSubstitutions()` | Sidebar sections |
| `renderBuilder()` | Bottom drawer queue chips |
| `renderSongwriter()` | Songwriter shutter sections |
| `renderPathList()` / `renderMelodySteps()` | Side panel content |

---

## One-time setup functions (called at init)

```
renderAll();
setupDrawer();             // bottom drawer toggle/expand/fullscreen
setupMelodyMode();         // generate-button + finalize-button handlers
setupSongwriter();         // shutter open/close + section action wiring
setupMetronome();          // metronome button click handler
setupCustomChordPanel();   // pill rendering + play/add handlers for Custom Chord panel
setupCollapsibles();       // any .collapsible-section (currently unused after refactor)
setupHeaderButtons();      // playground button + side panel toggles + ESC handler
bindModeButtons();         // legacy no-op
```

---

## Recent change history (newest first)

- **Preset matcher uses BPM as primary cross-song discriminator + measurement fingerprint visible inline**. The real problem the user was hitting: 4 different songs all picked the same preset because Demucs's "other" stem produces remarkably similar spectral fingerprints across genres (vocals/drums/bass are stripped, leaving similar residual keys/guitar/pads in the 1100-1700 Hz centroid range across most pop/rock). Spectral measurements alone can't discriminate when they're objectively similar across songs.
  - **Fix**: pass `songContext.bpm` (already detected via `splitterState.detectedTempo`) into `rulesPickNuxFactoryPreset` and `rulesPickModxKeysPerf`. BPM doesn't converge across genres the way spectrum does.
  - **`rulesBpmExpectedTones(bpm)`** returns the genre-appropriate tone families for a given tempo: <75 BPM → ambient/clean, <100 → clean/mid-gain/acoustic, <130 → mid-gain/crunch/overdrive, <160 → hard-rock/hi-gain/lead, ≥160 → metal/hi-gain.
  - **NUX scoring rebalanced**: centroid weight dropped from 0.40 → 0.10 (since it converges across demucs-other stems anyway), tilt 0.25, gain 0.30, **BPM-tone match 0.30**. Plus a BPM nudge on `targetGain` (fast tempos imply more saturation in the original guitar even when the "other" stem's crest factor looks medium).
  - **MODX similarly**: explicit BPM gates for ballad (<75 BPM → Piano/Vintage or Pad/Warm) and dance (>130 BPM + low crest → Syn Lead / Dance). Plus the within-category index calculation now mixes in BPM, so songs in the same category but different tempos get different specific Performance names.
  - **Visible measurement fingerprint** added to each gear-section body — a thin monospace pill showing `cen 1400 Hz · tilt 0.5 dB/oct · crest 9.5 dB · RT60 0.9 s · 140 BPM`. Lets the user see at a glance whether their 4 songs actually measure differently or genuinely converge (and what the picker is reading).
  - **Smoke test**: same spectral fingerprint at 4 different BPMs (70 / 110 / 140 / 175) now produces 4 distinct NUX presets (Flanger / Plexi / Shimmer Verb / Friedman) AND 4 distinct MODX Performances (CP 1979 / FM MotionSeq Ld DA / FM Sync / FM Syn Lead 2).
- **Preset-matcher recalibration: NUX always-picks-08D + MODX always-cycles-same fixed**. Two related bugs in the rules engine, both stemming from preset/category thresholds being calibrated for ISOLATED instrument recordings instead of demucs's "other" stem (which is what we actually feed in).
  - **Symptom on NUX**: every real song picked `08D · Lo-Fi/Utility` regardless of genre. Cause: preset `centroidHz` values were sized for isolated-guitar centroids (1500-3200 Hz), but demucs's "other" stem — vocals/drums/bass removed — typically lands 700-2000 Hz across pop/rock. 08D happened to sit at the bottom of the isolated range (cen 1500), which made it the closest match to most real measurements regardless of genre. Fix: multiplied every `NUX_MG30_PRESETS.centroidHz` by 0.65 to shift the whole preset range into the demucs-other-stem range. After: pop clean → 05B Phaser 90, rock crunch → 03A JCM800, djent → 04C Diezel, synth-lead → 01C AC30 across 4 scenarios.
  - **Symptom on MODX**: mostly the same Performance names cycled across songs. Two causes:
    1. Category thresholds (`cen < 1200`, `cen < 1500`, etc.) were also tuned for isolated content — most real measurements fell into the first 1-2 categories. Fix: halved the centroid thresholds.
    2. Within each chosen category, the picker always returned `picks[0]`. Fix: derive an index from a secondary measurement (`Math.floor(rt60 * 3 + crest * 0.3) % picks.length`) so different windows in the same category get different specific Performance names.
  - **MODX FX block labels** now suffixed with `(fine-tune)` to mirror the NUX layout — "Insertion FX · Compressor (fine-tune)", "System FX · Reverb (fine-tune)", etc. Visually consistent: the loaded Performance is the headline; the FX tweaks are optional refinements below.
- **Tone Recipe UI: full-width gear-first sections with refine-diff highlighting**. Three structural shifts on top of the rules-v4 preset-first output:
  1. **Layout flipped from grid → vertical stack.** The previous responsive 320-px-min grid is gone. Now there's one full-width section per gear, in fixed order: NUX MG-30 → Yamaha MODX 6 → Roland kit. Each section can span as much vertical space as it needs (preset block + amp + drive + cab + comp + EQ + mod + reverb + expandable measurements all live in one column). Driven by a new `.tr-sections` flex-column container; the per-section element is `.tr-gear-section`.
  2. **Sections are collapsible.** Click the header (gear name + caret) to toggle. State persisted across window changes via `splitterToneRecipeState.collapsedGears: Set<string>` so the user's choice survives scrubbing through the song. Measurements expander inside each section also persists (`measExpandedGears: Set<string>`).
  3. **Refine diff visually marks what Claude changed.** When a window has a cached refinement, the renderer passes the rules baseline alongside the refined recipe and the gear-section renderer compares block-by-block / param-by-param: changed `setting` → `.is-changed` background + "changed" badge + "was: <old>" line; added block → `.is-added` green-tinted background + "added" badge; changed param value → individual `.tr-param-changed` highlight. Block matching is name-first with a prefix fallback so "Amp (fine-tune)" still maps to "Amp" if Claude relabelled it.
  4. **Refactored data model.** `TONE_GEAR_SECTIONS` constant declares which stem each gear reads from (NUX + MODX both read 'other', Roland reads 'drums'). The window-renderer iterates this map gear-first, calls the rules engine once per stem (cached cheaply), then pulls each gear's entry from `gear_recipes[]`. Old per-stem card renderer (`splitterRenderToneRecipeCard`) is gone — replaced by `splitterRenderGearSection`.
  5. **Refine re-render simplified.** After successful refinement, instead of patching individual cards, we just call `splitterRenderToneRecipeForWindow(idx)` again — the gear-first renderer reads the new `refineCache` entries and applies diff highlighting automatically.
- **Rules v4: preset-first recipes (load this slot, then optionally fine-tune)**. Big shift in how the rules engine talks to the user. Previously each recipe was a chain of individual blocks ("set Amp to Brit 800, Drive to T Scream, Cab to V412, ..."). Now the headline recommendation is a single factory preset to load on the device, with block-level details kept as optional fine-tuning.
  - **NUX MG-30 factory presets baked in** (`NUX_MG30_PRESETS` — 32 entries × 8 banks). Each entry has `slot`, `name`, `tone` family, expected `gain` (0-9), `centroidHz`, `tilt` (dB/oct), `amp` (the underlying NUX amp model), and `notes`. Source: user-provided factory map (Banks 01-08: Clean / Crunch / Overdrive / Metal / Pop+Modulation / Lead / Ambient / Bass+Special).
  - **`rulesPickNuxFactoryPreset(m, stemId)`**: scores every preset against the measured tonal fingerprint and returns the best match. Scoring = 0.40·dCentroid + 0.25·dTilt + 0.25·dGain + bankPenalty (the bank penalty discourages ambient-bank picks unless RT60 is genuinely long, otherwise wet-clean presets beat plain clean presets unfairly on similar-gain ties). Output: `block: "Preset (load this)"` with `setting: "03A · JCM800"` so the user can find the preset by slot ID directly on their device.
  - **`MODX_PERFORMANCES` parsed from the official Yamaha Data List PDF**. User uploaded `modx_en_dl_d0.pdf` (16 pages, 30 MB); pdftotext + column-aware regex parser extracted 2195 canonical entries across 28 main+sub categories. The map keeps 4 representative Performance names per category (e.g. `Piano / Acoustic`: "Full Concert Grand", "Mellow Grand Piano", "Glasgow", "Romantic Piano"). Earlier MODX preset names (best-known training-data guesses) are gone — these are authoritative.
  - **`rulesPickModxKeysPerf` rewritten**: picks a Performance *category* by measured spectral character (centroid, RT60, crest), then names the first canonical preset in that category. The recipe's `params` carry `engine` (AWM2/FM-X), `category` (e.g. "Pad/Choir / Warm"), and `alternates` (a comma-separated list of sibling preset names from the same category — useful when the picked one doesn't quite fit).
  - **Block-level details kept as "fine-tune" rows**: Amp / Drive / Cab / EQ / Comp / Modulation / Reverb still emit specific NUX-named settings (`Brit 800`, `T Scream`, `V412`, etc.) — but they're labelled "Amp (fine-tune)" etc. so the user knows the preset is the main thing and these are optional tweaks beyond it.
  - **Smoke-tested in Node**: pop ballad → `01B · JC-120 Clean`. 80s rock crunch → `03A · JCM800`. Djent → `04A · Dual Rectifier`. Synth pad → `01D · Acoustic Sim` (NUX) + `FM Cloud Sine Pad` (MODX). All matches return as "strong" confidence under the new scoring.
  - **`RULES_VERSION` bumped to 4**. IndexedDB measurements cache is unaffected; recipes regenerate cheaply at render time.
- **AI auto-fallback: same-origin probe → `http://localhost:4747`**. Bug fix on top of the previous "kill the settings UI" commit. Refine button auto-detection now tries SAME-ORIGIN first (`/api/recipe-health` — works when opened via `http://localhost:4747`), then falls back to `http://localhost:4747` directly when same-origin returns 404 / errors (covers the case where the user is on the deployed `https://fymuse.pages.dev` and has server.py running on their laptop). Skips the fallback if the page itself is already on localhost (no point retrying). Resolved base URL is stored on `aiState.localBase` and used by `aiCallClaudeOnce` for the actual recipe POST. The user gets Refine working from BOTH locations without any settings UI — drop the song, click Refine, it just works as long as `server.py` is running (and `FYMUSE_TOKEN` is unset, since the browser doesn't send a token). Safari caveat (HTTPS→`http://localhost` blocked) is surfaced in the failure-mode tooltip.
- **AI Settings UI is gone. Refine button now auto-probes the local proxy.** The whole AI Settings popover (Mode picker, API key, gear notes, proxy URL/token, cache controls) and its gear icon in the Tone Recipe header have been deleted entirely. Gear inventory is fixed (NUX MG-30 + Roland kit + MODX 6) and named directly in the AI prompt template — no per-user editing UI.
  - **`aiState` collapsed** to just `{probed, localHealth}` — no mode, no key, no gear notes, no proxy URL/token, no localStorage state. The whole `aiLoadFromStorage` / save-key / save-gear / save-proxy / save-token chain is gone. ~430 lines of AI module code became ~270.
  - **Refine button auto-probes on first availability**: when windowed analysis finishes, `splitterUpdateRefineButtonState` checks `aiState.probed`. If not yet probed, it shows "Checking local proxy…" and fires `aiProbeLocalProxy()` against same-origin `/api/recipe-health`. Probe result is cached for the session. If probe succeeds → button enables as "Refine with Claude". If fails → "Refine unavailable" with the error in the tooltip.
  - **Only the local-proxy transport remains** (`aiCallClaudeOnce` always POSTs to same-origin `/api/recipe`). The API-mode path (`aiCallClaudeAPI`, `AI_MODEL`, pricing constants, BYOK validation) is deleted. If you ever want API mode back, the easiest revert is just reviving those functions from git.
  - **`server.py` CORS / PNA / token-gate code is INTACT** — preserved for the future "open the deployed Pages site, point at my localhost" mode. The browser doesn't currently send a token or use cross-origin URLs, so anyone running the server must NOT set `FYMUSE_TOKEN` (the gate would block our token-less requests). The startup banner still mentions both states.
  - **Net effect**: drop a song → Analyze → click Refine. Three buttons in the Tone Recipe header, zero configuration UI. AI either works or it tells you exactly why it doesn't.
- **Local-proxy AI works from the deployed Pages site (CORS + PNA + shared-token auth)**. Previously local mode only worked when FYmuse was served by `server.py` itself (same-origin `/api/recipe`). Now the deployed `https://fymuse.pages.dev` can reach back to `http://localhost:4747` on the user's laptop and use the local Claude CLI, no separate API key, while running.
  - **`server.py`**: new `ALLOWED_ORIGINS = {"https://fymuse.pages.dev", "http://localhost:4747", "http://127.0.0.1:4747"}`. When `Origin` matches, the server emits `Access-Control-Allow-Origin: <origin>` + `Access-Control-Allow-Methods: GET, POST, OPTIONS` + `Access-Control-Allow-Headers: content-type, x-fymuse-token` + **`Access-Control-Allow-Private-Network: true`** (Chrome's PNA policy needs this for public→localhost) + `Vary: Origin`. New `do_OPTIONS` handler returns 204 with these headers for preflight. Disallowed origins still get a 204 but no CORS headers, so the browser blocks the call.
  - **Shared-token auth** (optional but recommended in prod→local mode): set `FYMUSE_TOKEN=…` env var when starting `server.py`. `/api/recipe` then requires `X-Fymuse-Token: <value>` matching. Prevents random sites that find your localhost from burning your Claude subscription. `/api/recipe-health` always callable (no token gate) so the browser can probe — health response now includes `token_required: true/false` so the UI knows whether to prompt.
  - **Browser**: two new fields in the AI Settings popover under Local mode — **Proxy URL** (empty = same-origin, set to `http://localhost:4747` from the deployed site) and **Shared token** (masked input, persisted to localStorage as `fymuse-ai-local-{url,token}`). `aiCallClaudeLocalProxy` now prepends the configured base URL and attaches `x-fymuse-token` header. `aiProbeLocalProxy` probes the configured URL and surfaces clearer error messages when reaching across origins ("Safari blocks HTTPS→localhost").
  - **Browser-security caveat documented in the UI**: Safari refuses HTTPS→`http://localhost` requests regardless of CORS — anyone using Safari on the deployed site can't use Local mode and must use API mode. Chrome, Firefox, Edge all work because they treat `http://localhost` as "potentially trustworthy" per the W3C spec.
  - **End-to-end verified**: CORS preflights from allowed origins emit the right headers; disallowed origins get no Allow-Origin (browser blocks); POST without token → 403; POST with correct token → CLI invoked; health endpoint reports token_required state.
- **Tone Recipe UX: Refine is a button now, Analyze gets a real progress bar**. Two related improvements:
  1. **Refine checkbox → button.** Previously a toggle that fired auto-refinement on every new window the playhead crossed (potentially hundreds of background Claude calls). Now it's an imperative button: click to refine the current moment's stems explicitly. State `splitterToneRecipeState.refine` is gone. The async per-window auto-fire loop is gone. New helpers: `splitterRefineCurrentWindow` (the click handler) + `splitterUpdateRefineButtonState` (called whenever the active window changes, to update the button label between "Refine with Claude" / "Re-refine" / disabled). Visited windows that have cached refinements still render the refined version automatically (no rules-baseline regression on scrub-back).
  2. **Analyze progress bar.** `splitterSetToneRecipeStatus(state, msg, progress)` now renders a filled progress bar inside the status pill (matching the visual style of the Demucs Split processing modal — accent-coloured fill + percentage on the right + spinning icon). `splitterAnalyseSongWindowed` feeds it `(i + 1) / total` per window so the bar smoothly fills as analysis progresses. Status text reads "Analysing window N / T · m:ss → m:ss" with proper time-formatted ranges.
- **Rules v3: drop bass from Tone Recipe (user's NUX is guitar-only, MODX is keys-only)**. Added `'bass'` to `TONE_EXCLUDED_STEMS` so the bass card disappears from the Tone Recipe panel — same exclusion pattern vocals already use. Reverted `rulesStemNotApplicableReason` so NUX MG-30 and MODX 6 both mark bass as not-applicable with config-aware reasons ("Configured as guitar-only — bass goes through a separate chain not in this inventory" / similar for keyboard-only MODX). The bass-amp/cab/perf picker functions (`rulesPickNuxBassAmp`, `rulesPickNuxBassCab`, `rulesPickModxBassPerf`) stay in the file as dead code — flagged with comments — so re-enabling bass through either device is a one-line gate change if the user's config evolves. Tone Recipe panel now renders 2 cards (drums + other) instead of 3. Per-stem spectral measurements for bass remain available via the notes-modal "Spectral detail" tab.
- **Rules engine v2: real on-device preset names (NUX MG-30 was previously misnamed "MG 300")**. Two fixes in one pass:
  1. **Gear rename**: user's guitar processor is the NUX MG-30 (not the MG-300, which I'd been writing). Bulk-renamed every reference across `index.html` + `MEMORY.md` + the AI prompt template + gear-icon mapping + rules-engine reason strings + gear-notes UI label. Zero residual "MG 300" / "MG-300" / "MG300" hits.
  2. **Authoritative preset names baked into the rules engine**. Source: NUX MG-30 firmware 3.2.3 official model list (Aria Guitars JP distributor PDF + community-verified mirror). The picker functions now select from named-constant arrays (`NUX_GUITAR_AMPS`, `NUX_BASS_AMPS`, `NUX_GUITAR_CABS`, `NUX_BASS_CABS`, `NUX_DRIVES`, `NUX_MODS`, `NUX_DELAYS`, `NUX_REVERBS`, `NUX_COMPS`) where each key is the EXACT on-device label (e.g. `Brit 800`, `Twin Rvb`, `Plexi 45`, `Class A 30`, `Dual Rect`, `T Scream`, `Eat Dist`, `Muff Fuzz`, `V412`, `GB412`, `TR212`, `CE-1`, `St. Chorus`, `Tape Echo`, `Plate`, `Shimmer`) and the value names the modelled hardware. The user can scroll to these names on their device and find them directly.
  3. **NUX MG-30 is now applicable to BASS too** — the MG-30 has 4 dedicated bass amps (Bassguy, Mld, Dglass, Starlift) + 7 bass IRs (Ampeg SV810/410/212, Mark Bass, Trace Elliot, Eden, Bassman 4x10). Previous version (assuming MG-300) had marked bass as not-applicable through NUX. Added `rulesPickNuxBassAmp` / `rulesPickNuxBassCab` and routed bass stems through them inside `rulesRecipeNux`.
  4. **MODX 6 best-known Performance names** — the 223-page Yamaha Data List PDF couldn't be reliably scraped through the sandbox (network blocks, Google Docs viewer too-large refusal, browser fetch timeouts), so the MODX preset arrays (`MODX_PIANOS`, `MODX_EPS`, `MODX_ORGANS`, `MODX_PADS`, `MODX_LEADS`, `MODX_BASSES`) use confident family-level names (CFX Concert, Suit Case EP, B3 Vintage, Strings Hall, Saw Lead, Fingered Bass, Synth Bass DX, etc.) with an explicit code comment noting these are best-known examples — specific factory numbering may vary by firmware, and the AI refinement layer is well-positioned to correct any preset that's slightly off for the user's actual unit. Each MODX recipe now also names the category (e.g. "Piano / Acoustic", "Synth Lead / Analog") so the user can navigate the Performance bank quickly.
  5. **`RULES_VERSION` bumped to 2**. Recipe outputs change for every existing song; the IndexedDB measurements cache is unaffected (recipes regenerate from cached measurements at render time).
- **Tone Recipe: windowed analysis + live playhead-follow**. Previous version had number-input start/end region selectors (ugly spinner arrows, mechanical UX) and analysed one fixed region. New flow: click **Analyze song** once → DSP runs in 4 s sliding windows every 2 s across the whole song for each non-vocal stem → cards now auto-update to show the recipe at *wherever the playhead currently is*. Pause anywhere → see the recipe for that moment. Play → cards morph as the song progresses.
  - Tunable constants: `TONE_WINDOW_SEC = 4.0`, `TONE_HOP_SEC = 2.0`. ~90 windows for a 3-minute song; total DSP ~10-20 s after stems load. Yields between windows so the UI / playhead RAF stay responsive.
  - **Vocals excluded** from the Tone Recipe panel entirely (`TONE_EXCLUDED_STEMS = new Set(['vocals'])`). NUX doesn't carry vocals, MODX is a non-answer, the DAW-chain note wasn't useful. Three cards instead of four. The rest of the Splitter still processes vocals (sheet view, pitch tracking, chord chart) — only this panel hides them.
  - **New timeline strip** above the cards. Coloured ticks at window boundaries where any stem's primary block (amp / drive / kit / performance / reverb) changes setting from the previous window — so you visually see "amp model switches here at 1:24, reverb gets bigger at 2:08." Live playhead cursor scrubs across it. Click anywhere on the strip to seek.
  - **"Now" pill in the panel header** shows the current window's midpoint timestamp + window index (e.g. `1:24 · window 38/87`).
  - **AI refinement is per-window now**: when the Refine toggle is on, each window's recipe gets its own Claude refinement cached in `refineCache` keyed by `${stemId}:${windowIdx}`. Pre-refined windows render instantly when scrubbing through the song; only newly-visited windows trigger a Claude call.
  - **Measurements cached** to IndexedDB (`fymuse-ai-cache` DB, new `tone_windows` object store) keyed by `${songHash}::win${win}::hop${hop}`. Re-opening the same song bypasses the windowed DSP entirely and restores from cache. Recipes regenerate cheaply from cached measurements at render time, so bumping `RULES_VERSION` does NOT invalidate this heavy cache.
  - **Hooked into the playhead RAF**: `splitterUpdateStemCursors` (called from the existing splitter RAF tick) now also calls `splitterUpdateToneRecipeForPlayhead`. The window-change detection is cheap (compares `currentIdx` against the new nearest-midpoint index, only re-renders if it changed).
  - **Number inputs / spinner arrows are gone**. No more typing region bounds.
- **Full UI redesign: Tone Recipe is now a first-class Splitter panel; rules engine is the default; AI is opt-in refinement**. Previously gear recipes were buried 5 clicks deep inside a per-stem notes-modal tab, AI was the only way to generate them, and the AI Settings lived in a header-tool side panel disconnected from where recipes appeared. All three problems fixed in this redesign.
  - **New deterministic rules engine** (`rulesGenerateRecipe`): pure-JS functions that map measurements → gear recipes for all 4 stems × 3 gear pieces (NUX MG-30, Roland kit, MODX 6). Output uses the same JSON schema as the AI path so the renderer is shared. Block pickers are reusable across gear (`rulesPickReverbBlock`, `rulesPickCompressorBlock`, `rulesPickModulationBlock`, `rulesPickEQBlock`) plus gear-specific generators (`rulesPickGuitarAmp/Drive/Cab`, `rulesPickDrumKit`, `rulesPickDrumLowEnd`, `rulesPickModxBassPerf`, `rulesPickModxKeysPerf`, `rulesPickModxVocalFX`). Versioned via `RULES_VERSION` for cache invalidation. Deterministic, free, instant, works offline, works on the deployed Pages site.
  - **New Tone Recipe panel** in the Splitter view, between the mixer and the chord chart. Single region selector at the top (`Region [start]s → [end]s`) drives all four stems together. Each stem renders as a card: name + confidence badge + plain-English summary + per-gear tiles with block / setting / params / why rows + an expandable "Measurements" section that surfaces the raw spectral / dynamics / stereo / reverb cards. Auto-runs on stem analysis completion (fresh load + cache restore both trigger it).
  - **AI is now a refinement layer, not the primary path**. The Tone Recipe panel always shows rules baselines first (instant). A "Refine with Claude" toggle, when on and AI is configured, sends each rules recipe through `splitterRefineRecipeWithAI` — Claude receives the rules baseline + measurements + song context and returns the same JSON schema (potentially with changed block settings) plus a top-level `context_note` field explaining the musical reasoning. Refined cards get a "refined" badge + a callout box showing Claude's reasoning. Falls back silently to rules if AI errors or isn't configured.
  - **AI Settings moved to a popover** anchored to a gear icon in the Tone Recipe panel header. Removed the standalone "AI" header tool button entirely + its side panel + its PANEL_TO_BTN registry entry. Click-outside-to-close on the popover. Same internal logic (`setupAISettingsPanel`, mode picker, key/local probe, gear notes, cache clear) — just renders into the popover DOM now. `setupAISettingsPanel` is called from `buildSplitterViewSkeleton` after `root.innerHTML` is set, since the popover lives in the splitter view template.
  - **Notes-modal tab renamed** from "Tone Match" to "Spectral detail". Becomes a per-stem deep-dive for raw measurements; gear recipes are no longer offered there. The "Recreate on my gear" button hidden (kept in the DOM so legacy references don't NPE).
  - **Visible cleanup**: header tools row now has 8 buttons instead of 9, no more sparkle ✦ competing with Playground / Splitter / etc. The single "AI" entry point is now contextually located next to the feature it powers.
- **AI panel: Local-proxy mode** (use Claude.ai subscription instead of paid API). The AI panel now has a three-way mode picker (`Off` / `Local · Claude subscription` / `API · paid key`) instead of a binary enable toggle. Local mode routes recipe generation through `/api/recipe` on the same origin, served by `server.py`, which shells out to the `claude` CLI in headless mode. Uses the user's local Claude Code authentication (subscription auth) so no Anthropic API billing is involved — recipes count against the subscription's usage allowance, same as chat. Only works when `python3 server.py` is running locally; the deployed Cloudflare Pages site still needs API mode.
  - **server.py additions**: `GET /api/recipe-health` (probe — checks for `claude` on PATH, returns version) and `POST /api/recipe` (accepts `{systemPrompt, userMessage, model}`, spawns `claude -p ... --append-system-prompt ... --output-format json --model ...` with stdin=DEVNULL so the CLI doesn't wait 3 s for piped input, parses the JSON envelope, returns `{ok, text, usage, cost_usd}` to the browser). Non-zero CLI exit codes still parse the envelope first (Claude CLI exits 1 on auth/API errors but emits valid JSON containing the human-readable message in `result`).
  - **Browser additions**: `aiProbeLocalProxy()` does the health probe and stores result on `aiState.localHealth`. `aiCallClaudeOnce(messages)` is the new transport-agnostic call layer — branches between `aiCallClaudeAPI` (current direct browser → Anthropic) and `aiCallClaudeLocalProxy` (POST to `/api/recipe`). The retry-on-malformed-JSON loop in `aiGenerateGearRecipe` now wraps `aiCallClaudeOnce` so both transports inherit identical retry behaviour. Local mode collapses multi-turn into a single annotated user message since `claude -p` is one-shot.
  - **Panel UX**: `Local` and `API` sub-sections show/hide based on the selected mode. Local section has a status pill + Re-check button that surfaces probe results clearly ("Connected. claude CLI 2.x.x reachable." or the specific error). Auto-probe on panel open if mode is already local. Tone Match's "Recreate on my gear" button is enabled when the active mode is ready.
- **Tone Match Phase 2: BYOK Claude → gear-specific recipes**. The DSP measurements from Phase 1 now feed an AI translation layer that turns "centroid 2.3 kHz, tilt +1.4 dB/oct, RT60 0.8 s, crest 8 dB" into "NUX MG-30: Amp Brit 800 gain 4.5, bass 6, mid 7, treble 5; Cab 4x12 V30; Plate reverb decay 1.8 s, mix 25%."
  - **New header tool: "AI"** (sparkle icon) opens a side panel mirroring Path Finder / Custom Chord. Contents: master enable toggle, Anthropic API key input with Validate button (1-token call to `claude-haiku-4-5` to confirm), three gear-notes textareas (NUX MG-30, Roland kit, MODX 6), Clear-key + Clear-cache buttons. All state persisted in `localStorage` as `fymuse-anthropic-key` + `fymuse-gear-{nux,roland,modx}-notes` + `fymuse-ai-enabled`. Key field masked to last 4 chars when blurred; reveals on focus.
  - **`aiGenerateGearRecipe(measurements, stemId, songContext)`** — pure async wrapper around `fetch('https://api.anthropic.com/v1/messages')` with the `anthropic-dangerous-direct-browser-access: true` header. Model: `claude-sonnet-4-6`, max 2000 tokens. System prompt defines a strict JSON schema (stem / summary / confidence / caveats / gear_recipes[{gear, applicable, reason_if_not, blocks[{block, setting, params, why}]}]). User message includes the measurements + gear notes + song name/BPM/key. Validates response shape with `aiValidateRecipe`; on malformed JSON or schema mismatch, retries once with the validation error appended (Claude self-corrects reliably). `aiExtractJSON` strips markdown fences when present.
  - **Tone Match "Recreate on my gear" button** added below the section selector, hidden when AI is not enabled / no valid key. Click runs the wrapper, renders the result as a styled card stack: top summary card (one-line description + confidence badge + caveats), one card per gear with its blocks as stat rows (block name on the left, setting on the right, params + why text below). Stale recipe wrap clears when the region or stem changes.
  - **Cost readout** under each recipe: token in/out + ~USD using `claude-sonnet-4-6` pricing ($3/MTok input, $15/MTok output). Cached recipes show "served from cache · no new charge."
  - **Recipe cache (IndexedDB, separate from the splitter cache)**: store `fymuse-ai-cache` / `recipes`, keyed by `{songHash, stemId, startSec, endSec, gearProfileHash}`. Gear profile hash is FNV-like over the concatenated gear notes — editing gear notes invalidates stale recipes automatically. Helpers: `aiCacheOpenDB`, `aiCacheGet`, `aiCacheSave`, `aiCacheClearAll`.
  - **Browser CORS note**: Anthropic supports direct browser calls with the opt-in `anthropic-dangerous-direct-browser-access: true` header. Intended for prototypes / small-scale tools; for a band-sized user base we're well within spirit. Watch for policy changes upstream.
- **Design doc parked: custom guitar/keys splitter** (`docs/CUSTOM_OTHER_SPLITTER.md`). We discussed building our own ML model that takes htdemucs's `other` stem and splits it into `guitar` + `keys`. Decided against using Meta's `htdemucs_6s` (no public browser-ready ONNX, weak piano stem) in favour of training a specialized MDX-Net-style spectrogram U-Net (~15-30M params) as a post-Demucs second pass. The doc captures: architecture choice + rationale, three-tier data plan (MedleyDB + Cambridge-MT + Slakh + heavy synthetic augmentation from solo recordings), three-phase training (pre-train on Slakh → main train on real data → optional fine-tune on our music), evaluation via `museval` (target: beat htdemucs_6s by ≥1 dB SDR on guitar), deployment as a second ONNX inference pass after the existing Demucs run. Realistic timeline: 6-8 weeks full-time, ~$150-300 GPU rental. Not in active development — pick up later when we want to push past the current `other`-as-soup limitation in Tone Match for guitar+keys-heavy songs.
- **Tone Match: Phase 1 of the "Music Copier" feature** — per-stem acoustic characterisation. New third tab in the notes modal next to Piano Roll / Sheet. Lets the user pick a region of the stem and runs four pure-DSP measurements over it; no AI yet (that's Phase 2, BYOK Claude + user's gear inventory).
  - **Measurements** (`splitterMeasureTone` orchestrates):
    - `splitterToneSpectrum` — long-term average spectrum on a log frequency axis. 4096-point FFT, 50% hop overlap, average magnitudes across frames, aggregate into 32 log-spaced bands from 25 Hz to 16 kHz, convert to dB-relative-to-peak. Also returns spectral centroid (Hz) + tilt (dB/octave fit between 200 Hz and 8 kHz). Tilt interpretation: <−5 dark, <−2 warm, <+1 balanced, <+4 bright, ≥+4 aggressive.
    - `splitterToneDynamics` — peak / RMS / crest factor over the region + 300 ms-windowed RMS trace. Crest factor (dB) drives a compression-rating heuristic: >16 minimal, >12 light, >9 moderate, >6 heavy, else brick-wall.
    - `splitterToneStereoWidth` — mid/side decomposition done in the FFT domain (separate FFTs of M = (L+R)/2 and S = (L−R)/2), per-band width = |S|/(|M|+|S|). Returns the same 32 log bands + overall width. Width interpretation: <0.10 mono, <0.22 narrow, <0.35 natural, <0.48 wide, ≥0.48 very wide.
    - `splitterToneReverbEstimate` — envelope follower at 50 fps, find the loudest peak with ≥0.4 s of monotone-decreasing decay after it, linear-fit log(env) over the decay window, derive RT60 = −60 / slope_dB_per_sec. Returns null when no clean decay event exists in the region (e.g. busy sustained content with no clear tail).
  - **UI**: section selector (start/end seconds, default 0–10 s of the stem, clamped to stem duration) + "Re-analyze" button + responsive grid of cards. Each card is an SVG plot (frequency curve, RMS sparkline, stereo-width bars) plus stat rows + a one-line plain-English interpretation. Stereo card hidden for mono stems.
  - **Lazy execution**: tab content only renders on activation. Results cached on `splitterModalState.toneCache` keyed by `${stemId}:${start.toFixed(2)}:${end.toFixed(2)}`, so switching tabs / stems / regions doesn't re-run the FFTs unless the inputs change. First open of a stem auto-runs the analysis (defaults to first 10 s of that stem); subsequent opens of the same stem hit cache.
  - **Why these four measurements specifically**: they're the ones meaningfully extractable from a finished mix and the ones that translate directly to gear settings (EQ curve → amp/EQ; crest factor → compressor ratio + makeup gain; stereo width → chorus/widener; RT60 → reverb decay time). Mic position, exact plugin choice, console coloration etc. are *not* recoverable from audio alone — Phase 1 deliberately doesn't pretend otherwise.
- **Drums: cross-stem kick detection (fixes "everything is a snare")**. The old single-stem classifier (`splitterClassifyDrumOnsets`) tried to identify kicks from features inside the drums stem alone. That failed because Demucs (htdemucs_embedded) routinely steals the kick fundamental (40-90 Hz) into the bass stem — Bass and Kick share that band and the model has to assign the energy to one or the other. What's left in the drums stem for a kick is 150-400 Hz body resonance, which looks more like a snare than a kick. The classifier then either called kicks "snare" or missed them entirely.
  - **New path** (`splitterClassifyDrumOnsetsCrossStem`): build a dedicated "kick channel" by summing the ORIGINAL MIX with 0.5× the bass stem (mix has most of the kick fundamental; bass-stem mixin tops up the Demucs-stolen energy), then 2-pass 2nd-order Butterworth LP at 120 Hz (`splitterBiquadLPInPlace`) for a ~24 dB/oct rolloff. Every onset in that band is a kick, period — pop/rock kicks are by definition the dominant sub-120 Hz transient.
  - Dedicated kick-channel onset detector (`splitterDetectKickChannelOnsets`): spectral flux on bins ≤150 Hz only, 60 ms min separation (kicks rarely fire faster than 16ths at 240 BPM = 62 ms), threshold = max(p50 + 0.3·(p90-p50), 1.35·localMean).
  - Drums-stem onsets within ±30 ms of a kick onset are dropped — those are kick spill into the upper bands, not real snares or hats.
  - Remaining drums-stem onsets go through `splitterClassifyNonKickDrum`: a slimmed 4-class (snare/hat/hat_open/cymbal/tom) decision tree. Kick logic is gone entirely from this path. Added zero-crossing rate as a feature (`splitterZeroCrossingRate`): kicks ~0.005, snares ~0.05, hats ~0.15+ crossings/sample. ZCR is the key snare-vs-hat discriminator now.
  - Wired in via `splitterAnalyseStemEvents`: drums dispatch passes `splitterState.fileBuffer` (the original mix) and `splitterState.stems.bass.buffer`. Falls back to the old single-stem `splitterClassifyDrumOnsets` if the mix isn't available (legacy paths only).
  - Cached splits from before this fix retain the old (wrong) events on cache hit. Re-drop the file or "Clear all" in History to re-analyze.
- **Splitter: auto-detect song key → set Sa**. Krumhansl-Schmuckler against the 24 canonical major/minor probe-tone profiles. Aggregates chroma over the full song (per-frame normalized so loud sections don't dominate), Pearson-correlates against each profile rotated to all 12 roots, picks the best fit. Result `{root, mode, confidence}` lives on `splitterState.detectedKey`. The notes modal applies the detected root as the default Sa whenever the user hasn't manually overridden via the dropdown; a small `AUTO` badge near the Sa selector indicates auto-pick. Synthetic tests pass C/G/F♯/Am/Dm at 0.91-0.95 confidence.
- **Splitter: lower non-vocal sensitivity**. Bass: hop 0.15 → 0.20 s, smoothing 3 → 5 frames, min event 0.10 → 0.18 s. Chord detector (harmonic/other/original): added a 2-frame stability filter so single-frame mis-detections don't produce events; min event 0.4 → 0.7 s. Vocals untouched.
- **Splitter notes modal: Hindustani sargam toggle**. 3-way segmented control in the modal header (`ABC` / `Sa Re` / `सा रे`). When non-Western, a `Sa = ?` dropdown appears. 12 swaras with komal/sudh/tivra naming: `Sa, re, Re, ga, Ga, Ma, Ma♯, Pa, dha, Dha, ni, Ni` (Latin) or `सा, रे॒, रे, ग॒, ग, म, म॑, प, ध॒, ध, नि॒, नि` (Devanagari). Octave indicators: `'` per octave above middle, `,` per octave below. Affects the keyboard column + monophonic event labels; chord names stay Western.
- **Splitter notes modal: pinch-zoom + space-bar**. Two-finger touch (touchscreens) and Ctrl/Cmd+wheel (macOS trackpad pinch) zoom anchored to focal point. Space bar toggles play/pause when Splitter view is active and a song is loaded; ignored when typing in inputs/textareas.
- **Cloud-side YT extraction: tried, removed (Phase-1 architecture frozen)**. Spent a long arc trying to make the URL → YouTube path work on the deployed Cloudflare Pages site. Walked through, in order:
  1. **`/api/proxy` Pages Function** — generic CORS shim for direct audio URLs. Kept (still useful for non-YT hosts that block CORS).
  2. **`/api/yt` Pages Function with `youtubei.js`** — pure-JS InnerTube reimplementation. Required `nodejs_compat` flag, `package.json`, `wrangler.toml`. Failed because Cloudflare datacenter IPs hit YouTube's "Sign in to confirm you're not a bot" challenge on most YT Music tracks; cycling through 11 player clients (TV, IOS, ANDROID_MUSIC, WEB_MUSIC, MWEB, etc.) bypassed *some* videos but not enough.
  3. **Render sidecar (`yt-service/`)** — Docker container running real `yt-dlp` + ffmpeg, exposed via Render free tier, called by the Pages Function as a fallback through `YT_SERVICE_URL` env var. Same problem: Render's IPs got the same bot-check, and yt-dlp's stderr literally said `Sign in to confirm you're not a bot. Use --cookies-from-browser`.
  4. **Cookie injection on Render via Secret Files** + multiple `--extractor-args` clients. Worked technically but meant putting Shay's authenticated YouTube cookies on a third-party host where every band visitor's extractions would attribute to his Google account (watch-history pollution + account-flag risk).
  5. **Cloudflare Access (Zero Trust) ACL** to gate the URL feature to a hand-picked email allowlist + cookie injection. Working but heavy: requires per-user email-OTP login flow on every fresh session, requires Shay (or a burner Google account) to ship cookies that expire every 4-6 weeks, requires manual allowlist management. For 5 band members the ceremony outweighed the win.
  
  **Conclusion**: every cloud-IP architecture loses to YouTube's bot detection. Residential IPs don't have this problem, so the realistic answer is "run server.py locally on each user's machine." Walked all of the above back. What remains: deployed site = upload + direct-URL only. Local mode (server.py + yt-dlp) = full feature set including YT URLs.
  
  **Future ideas (not built):**
  - **Phase 2 — always-on box at home / rehearsal space.** Raspberry Pi 5 (~$35) or any old laptop, runs `server.py` 24/7. Expose to the band via Cloudflare Tunnel (free) → stable URL like `https://fymuse.your-band.com`. Residential IP, full feature set, one machine to maintain. The clean answer for sharing with collaborators without per-person setup.
  - **Phase 3 — desktop app.** Bundle `server.py` + `yt-dlp` + `ffmpeg` + a tiny WebView shell as Electron / Tauri. Each band member downloads `FYmuse.dmg` / `.exe`, opens it, no terminal required. Maximum UX, but real maintenance burden.
  - **Phase 4 (anti-pattern)** — paid residential proxy network + cookie-pool rotation, à la cobalt.tools. Costs real money, breaks weekly, requires part-time SRE attention. We deliberately don't go here.

- **Splitter: dedicated chord progression chart panel**. New section between transport and stem mixer that surfaces the song's harmony at a glance. Two pieces: (a) a big "Playing" display (36 px, accent color) showing the chord active at the playhead with its note names below, and (b) a horizontal scrollable strip of every detected chord as clickable pills with their start times. The active pill highlights orange and auto-scrolls into view during playback; click any pill to seek. Data comes from `splitterState.stems.other.events` (the Listener-grade chord detector) and renders as soon as the 'other' stem finishes analysis, again at end-of-analysis as a safety net, and on cache restore. Updates on every RAF tick via `splitterUpdateChordChartCursor` with a 50 ms linger past chord end so the highlight doesn't blip off between transitions. Slash chords (D/F#, C/G etc.) flow through unchanged from the slash post-pass.
- **Vocal note detector rewritten: pitch heatmap + 1/16th-note quantization**. The old per-frame HPS argmax was wobbly — every 40 ms frame picked the single strongest pitch independently, so micro-flickers became events. New `splitterDetectVocalNotesQuantized(buffer, tempo)`:
  1. Per-frame HPS energy for *every* MIDI candidate in the vocal range (D2 = 38 through F6 = 89), stored in `heat[frame][midi]`. 33 fps, 4096-pt FFT, 4-harmonic HPS product, pre-computed harmonic bin indices for speed.
  2. 1/16th-note slot grid derived from `splitterState.detectedTempo` (defaults to 120 BPM). At 120 BPM that's 125 ms slots; at 80 BPM 187 ms.
  3. Per slot: sum heatmap across all frames in the slot, pick the MIDI with highest summed energy. Drop slots that don't have ≥ 40 % voiced frames (adaptive RMS p15/p85 silence floor). Drop slots where the winner doesn't beat 2nd-best by ≥ 1.10× (kills octave-error ties).
  4. Merge consecutive same-pitch slots into single events — a held quarter note = 4 consecutive 1/16th slots collapsed into one event.
  5. Per-event velocity from event-window RMS, normalized p05/p95 → MIDI velocity [40, 127].
  
  Why it's better: brief HPS flickers contribute negligible energy to a slot vote; the real sustained pitch wins. Glide chromatics spread their energy across multiple MIDIs and never win a slot. Every note lands on a clean musical grid so the sheet view reads beautifully. Trade-off: notes faster than 1/16th can't separate (at 120 BPM = 125 ms, still fast enough for almost any sung note). Bass and 'other' stems untouched — they don't benefit from 1/16th quantization.
- **Splitter chord detection rewritten to mirror the Listener's pipeline**. The old `splitterDetectChords` was a stripped-down version (single-pass per-frame matching + 2-frame stability filter). Brought in the full Listener-grade pipeline:
  - Hop `0.25 s → 0.12 s` (~8 fps). Beat-level chord changes at 120 BPM (500 ms = 4 frames) are now detectable.
  - **Spectral-flux onset detection per frame.** When energy spikes > 2.5× the EMA baseline, rolling history wipes and locked-key clears so a new chord locks immediately instead of needing 6 frames to majority-vote.
  - **Separate sub-180 Hz bass chroma.** Dominant bass PC identified per frame, confidence-gated (must be > 30 % ahead of 2nd-strongest). Passed into `listenerScoreChroma` as bassPc so candidates whose root matches the bass get the 1.15× boost — this is what disambiguates same-PC chord shapes (F#dim vs rootless D7).
  - **3-frame median smoothing on raw chroma** + temporal low-pass (α = 0.55) — kills single-frame spikes from cymbal hits / vocal sibilance bleeding through.
  - **Rolling history of 6 frames (~720 ms) with weighted majority vote + 1.10× hysteresis.** Locked chord can't be unseated unless a new candidate beats its tallied score by 10%. Stops sus2 / major / dom7 flickering between each other on ambiguous chroma.
  - **Template set 10 → 20 qualities.** Added 6, m6, add9, madd9, mMaj7, dim7, 7sus4, 9, m9, maj9. `buildHarmonicTemplate` normalizes each so cosine matching stays well-defined with the bigger candidate pool.
  - **Slash chord post-pass `splitterAddSlashChords`**: walks chord events, looks up dominant bass pitch class from the bass-stem note track during each chord's first 1 s, appends `/X` if bass PC differs from chord root. Requires ≥ 200 ms of bass dominance so single walking-bass passing tones don't override. So 'D' becomes 'D/F#', 'C' becomes 'C/E', etc.
  - `minEventSec` 0.7 → 0.25 s. Half-beat chord passes survive; hysteresis already prevents flicker.
  - Stem analysis order changed to `drums → bass → other → vocals` so the chord detector has bass info ready for the slash post-pass.
- **Bass detection responsiveness bumped.** `hopSec` 0.20 → 0.08 (12.5 fps catches 1/8 + 1/16 notes), `smoothFrames` 5 → 2 (old 250 ms lag was making onsets missed), `stabilityFrames` 2 → 1 (commit every frame), `minEventSec` 0.18 → 0.06 (eighth notes at 200 BPM = 75 ms survive comfortably).
- **Chord-aware vocal scale filter — built, then reverted.** Experimental post-pass that filtered short off-scale vocal notes using the active chord's tones ∪ scale ∪ song-key root scale. Helpers (`splitterChordTones`, `splitterScaleForChord`, `splitterScaleForSongKey`, `splitterFilterVocalToScale`, `splitterParseChord`) remain in the codebase but aren't wired into the pipeline. Reason: when the chord detector mis-labels (which still happens often enough to matter on dense arrangements), the filter cascades mistakes by dropping legitimate vocal notes that ARE in the actual played chord. The helpers will be useful again if we add an opt-in "strict mode" toggle once chord detection is closer to perfect.
- **Notes modal sheet view + Hindustani vocal-only**:
  - Hindustani sargam toggle (`ABC` / `सा रे`) hidden for non-vocal stems. Drums / bass / other open in Western mode only; state forces back to Western on every modal open if a previous vocals session left it on Devanagari. The Sa selector also force-hides for non-vocals. Sargam doesn't apply to chord names or drum component letters.
  - Sheet view rebuilt as a learning-focused score (see entry below) with a vocal-specific "flowing" renderer (`splitterVocalFlowBarHTML`) that lays notes inside per-beat slots in time order, with **meend / slide markers** (`⌒` arc between consecutive close-pitch notes), **legato connectors** (dot between gently-connected notes), **kan-swar / grace notes** (small dashed-border variant for short ornaments before longer chromatic-adjacent notes), and **velocity-driven opacity** (loud notes pop, soft notes dim).
  - Glide chromatic passing tones are SUPPRESSED from the piano roll but VISIBLE in the sheet: the glide cleaner attaches `glideFromMidi` metadata to the surviving target note, and the vocal-flow renderer prints that chromatic as a tiny dim passing-tone inside the slide curve.
  - Modal-tab visibility bug fixed: `.modal-tab-content[hidden]` needed `!important` to win over `.modal-tab-content.sheet-content { display: flex; }` (same-specificity tie that previously resolved to source order, leaving the sheet pane visible after switching back to piano roll).
- **Vocal pitch pipeline iteration history (for posterity)**. Across this session the vocal detector evolved through several incarnations to balance "catch ornaments + fast runs" vs "no chromatic glide leakage":
  - `stabilityFrames: 2, minEventSec: 0.07` — glide-resistant but dropped fast-run notes.
  - `stabilityFrames: 1, minEventSec: 0.025` + post-cleaner — caught fast runs but with chromatic flicker the cleaner couldn't fully tame.
  - Final form: heatmap + 1/16th quantization (current). Replaces argmax+cleanup with vote-per-slot.
  - Glide cleaner (`splitterCleanGlideChromatics`) + adjacent-merge (`splitterMergeAdjacentSamePitch`) are still in the codebase for use by the old monophonic detector, but the vocal path now uses the heatmap detector exclusively.
- **Auto-detect tempo (BPM) from drums-stem onsets**. New `splitterDetectTempo(buffer)` runs in Phase 2b of analysis right after key detection. Pipeline: re-use `splitterDetectDrumOnsets` to get onsets, build a 5 ms-bin IOI histogram over 0.20-1.50 s with 1× / 2× / 3× foldings so onsets on subdivisions still vote for the beat period, triangular smoothing, peak pick, octave-snap into 60-180 BPM. Result cached on `splitterState.detectedTempo` and persisted in the IndexedDB cache. The notes modal's sheet tempo input auto-fills with the detected BPM via `splitterModalState.sheetTempoAuto` flag (becomes false on manual edit). The 1/16th-note slot grid in the vocal detector uses this same value.
- **Drum classifier hardening — dual-pass onset detection + transient-window features**. The original 300 ms feature window was dominated by hat/cymbal sustain ringing through, so kicks looked like snares and were classified wrong. Two fixes:
  1. **Two parallel spectral-flux passes**: broadband (all bins) catches snares/hats/cymbals; low-band (bins below 250 Hz only) catches kicks. The broadband flux barely moves when a kick fires alongside a ringing hat because it changes few bins out of 512+; the low-band flux sees only the bins that actually changed, so the kick spike is obvious. Onsets from both passes merge with 30 ms dedup. Each pass uses its own adaptive threshold (broadband `localMean × 1.45`, low-band `× 1.35`).
  2. **Decoupled spectral / decay windows**: 80 ms post-onset window for spectral features (transient region where the drum's identity lives) + 250 ms separate window for decay-ratio computation. The shorter spectral window is no longer polluted by sustained hat ringing.
  
  Classifier decision tree also reworked with kick-first ordering and `peakHz` (spectral peak frequency) as a primary discriminator — robust against bleed because even with hat ringing the loudest single bin is still the kick fundamental. Five OR-triggers for kick (peak < 200 Hz, OR sub > 0.15, OR lowE > 0.30 with low centroid, OR lowTotal > 0.45 with low centroid, OR lowTotal > 0.35 with low HF + low centroid). Open vs closed hat split by decay ratio. Then cymbal → hat → snare → tom → fallback. Known caveat (unfixed): the `sub > 0.15` kick trigger is too permissive — snares with even small Demucs kick bleed land in the kick bin, eating the snare lane. Slated for a future tightening pass.
- **Notes modal — sheet view rebuilt as a learning-focused score**. The old sheet was a flex-wrap of bar boxes; replaced with a per-line layout that fits exactly 2 bars per row (no wrapping), with a beat ruler at the bottom of every line. Ruler labels are subdivision-aware: `1 2 3 4` for quarters, `1 & 2 & 3 & 4 &` for 8ths, `1 e & a 2 e & a …` for 16ths, `1 t l 2 t l …` for triplets. Notes sit ABOVE the ruler at their exact subdivision positions. Sustained notes only print at the onset cell — they don't repeat across every subdivision — so the page reads like real sheet music: "this note fires here, holds for that long." Pitched stems (vocals/bass/other) get a single "Notes" row showing the actual note name (or chord name for `other`). Drum stems get one row per drum component that actually fired (cymbal/hat/snare/tom/kick), color-matched to the piano-roll grid, hits as `●` bullets at exact subdivision positions; empty lanes are skipped. Line header shows bar range, tempo / time-sig, and the detected song key on the first line. Cursor highlight retargeted to the new `.sheet-cell-note` class. CSS: paper-feel inset shadow on each `.sheet-line`, monospace cells, dashed border between row label and bars.
- **Notes modal — Hindustani toggle is vocals-only now**. Drums / bass / other open with the notation toggle hidden entirely; state forces back to Western on every modal open if a previous vocals session left it on Devanagari. The Sa selector also force-hides for non-vocals. Sargam doesn't apply to chord names or drum component letters — keeping the toggle visible was confusing.
- **Splitter: drum-component classifier (kick/snare/hat/tom/cymbal)**. The drums stem used to return `[]` from analysis; now it runs through a heuristic decision tree on per-onset spectral features. Pipeline:
  1. **Onset detection** via spectral flux on the drums stem. Adaptive threshold = p50 + 0.45 × (p90 − p50) plus a local-mean window; 50 ms minimum gap between onsets.
  2. **Two-window feature extraction.** Spectral features (6 power-band proportions: sub <80 Hz / bass 80-200 / lowMid 200-500 / mid 500-2k / high 2-5k / vhigh 5+ kHz; spectral centroid; spectral flatness in 1-10 kHz; spectral peak frequency `peakHz`) are computed over the **first 80 ms** of the onset only — using a longer window pollutes the spectrum with hat/cymbal sustain ringing through, which makes kicks look like snares. Decay ratio (late-RMS / early-RMS) uses a separate 250 ms window since 80 ms is too short to see meaningful decay difference between a closed hat and a cymbal.
  3. **Decision tree** with kick check first. Three independent kick triggers: `peakHz < 150 Hz` (the kick fundamental, robust against bleed because it's the loudest single bin) OR `sub > 0.25` with low centroid OR `(sub+bass) > 0.35` with low centroid + low flatness. Then tom (peak 100-400 Hz, low-mid dominant, tonal, longer decay) → cymbal (long decay + HF + noisy) → hi-hat (HF + high centroid; split open/closed by decay) → snare (mid + broadband + medium centroid). Centroid + peakHz fallback for the residual.
  4. **Output events** carry `{start, end, label: 'K'|'S'|'H'|'T'|'C', type, midi, pitches, velocity}`. `midi` is the General-MIDI drum note (kick=36, snare=38, closed hat=42, open hat=46, tom=45, crash=49). Velocity derived from peak amplitude in [40, 127]. Existing piano-roll / sheet / MIDI pipelines work without core changes.
- **Splitter: drum grid in the notes modal**. Drum stems no longer use the chromatic piano-roll layout (would have a sparse 36-49 MIDI range with empty rows). New `splitterRenderDrumGrid` lays out 6 fixed lanes (Cymbal / Hat-open / Hat / Tom / Snare / Kick top→bottom) with per-lane colors (cymbal yellow #d4a017, hat orange #f5a524, tom blue #6cc4ff, snare red #ff7f7f, kick purple #b388ff). Velocity drives bar opacity so loud hits visually pop.
- **Splitter: per-stem MIDI export uses GM channel 10 for drums**. `splitterEventsToMIDI` switches status bytes to `0x99/0x89` when the stem is `drums` or `percussive`, so any DAW interprets the file via the General MIDI drum kit instead of as pitched notes. Per-hit velocity now carried through from the classifier (was a fixed 96).
- **Processing modal: cooler animated UI + freeze on error**. The old static music-note glyph + emoji bullets (○ ⏳ ✓) replaced with: three pulsing concentric rings + a duotone waveform glyph at the center; a 2px marquee bar scrolling forever across the top edge of the panel; per-step bullets using phase-specific Phosphor duotone icons that swap between pending (faded) → spinning circle-notch when active → green check-circle when done; a tiny inline 4-bar equalizer beside the active step row; a live activity ticker below the title cycling through 18 flavor-text phrases ("computing spectrogram", "fitting probe-tone profiles", "tracing pitch contours", "reticulating splines" …) every 1.8 s with a fade transition. On error, every animated decoration freezes + dims, the hero glyph swaps to `ph-warning-circle` red, panel border tints red, progress row hides, ticker stops. Substep state is reset at the start of every fresh busy run (modal was hidden, now opening) and the inference fn defensively resets *later* phases to pending whenever it identifies a current active phase, so checklist can't show "future" steps as done.
- **Splitter: cache + history + URL load**. Every successful split is hashed (SHA-256 of the input bytes, with a size+sample fingerprint fallback) and stored in IndexedDB (`fymuse-splitter-cache` / `splits` store, keyed by hash). Re-dropping the same song hits cache instantly — no model run. New header buttons:
  - **History** — modal listing every past split (newest first) with name, size, key, sample-rate, age. Click to reload its stems. Per-row delete + "Clear all".
  - **URL** — paste a direct audio URL (must be CORS-allowed). `fetch()` the bytes, wrap in a synthetic `File`, run through the normal `splitterLoadFile` pipeline (so cache lookups still apply by content hash, not URL).
  Both modals close on overlay click + ESC. State helpers: `splitterOpenDB`, `splitterHashBytes`, `splitterCacheGet/Save/List/Delete/Clear`, `splitterLoadFromCache`, `splitterOpenHistoryModal`, `splitterReloadFromHistory`, `splitterOpenUrlModal`, `splitterLoadFromUrl`. Stems stored as `{channels: [Float32Array, …], sampleRate}` per stem (structured-cloned natively by IndexedDB) and rebuilt into AudioBuffers on restore.
- **Splitter UX refresh**: drop DSP entirely (always Demucs ML now), big full-space drop zone covering the whole splitter view when no song is loaded, and a **processing modal** that overlays during separation showing the live progress bar + percentage + step name. Removed the old inline status pill from the controls row.
- **Splitter: per-stem MIDI export** — every stem-track gets a "MIDI" button next to its mute/solo. Format-0 SMF: header chunk + single track with VLQ delta-times, NoteOn/NoteOff (and NoteOn velocity 0 between repeated pitches). Vocals export from the HPS-tracked pitch line; harmonic stems export from the chord/note grid by sampling each beat. Tempo defaults to 120, beats from the user's chosen `sheetBeatsPerBar`.
- **Splitter: Sheet notation tab** in the notes modal. New tabs at modal top — **Piano roll** | **Sheet**. Sheet view writes the detected events out as bar-by-bar ASCII tablature with configurable tempo / beats-per-bar / subdivision (eighth / sixteenth / triplet). For the vocal stem it shows pitch + sargam (when toggled); for harmonic stems it shows chord names. Renders as a `<pre>` block, copyable. State: `sheetTempo`, `sheetBeatsPerBar`, `sheetSubdiv` on `splitterModalState`.
- **Splitter: drop the Original stem** (it's already audible via master playback) — stem layout is now vocals/drums/bass/other only. Drums got the new `ph-drum` icon. Sargam toggle simplified to Devanagari only (the Latin "Sa Re Ga Ma" was redundant alongside the Devanagari script).
- **Splitter: vocal pitch stability filter**. Vocal HPS was catching every chromatic during glides and fast runs. New `stabilityFrames` rule: a detected pitch must hold for N consecutive frames before it's committed as a note onset. Eliminates portamento chromatics without dampening real fast runs (the held targets still satisfy the stability criterion).
- **Splitter: auto-detect song key → set Sa**. Krumhansl-Schmuckler probe-tone profiles (major + minor) correlated against the full-song chroma find the most likely tonic. The detected pitch class is stored as `splitterState.detectedKey` and pre-fills the Sa selector when the modal opens for the first time (`saAutoDetected` flag prevents overriding manual choice afterward).
- **Splitter: lower non-vocal sensitivity + Hindustani sargam toggle**. Drums/bass/other notes had been over-detecting transients. Tightened their thresholds. New notation toggle (Western ↔ Devanagari sargam) renders pitch names as स रे ग म प ध नि relative to the chosen Sa. Vocals only — sargam doesn't make sense for chord stems.
- **Splitter: pinch-zoom + space-bar play/pause** in the notes modal. Space toggles transport; pinch (`gesturechange` on Safari, two-finger wheel on others) zooms the timeline.
- **Splitter notes modal: horizontal-stretch slider**. Continuous range slider 10-2000 px/sec between the `−`/`+` buttons. Single source of truth (`splitterSetModalZoom`) keeps slider, buttons, percentage readout, and renderer in sync.
- **Splitter: HPS-based vocal pitch tracker** (`splitterDetectMonophonicNotes`). Generic monophonic detector tuned per stem. Vocals: 0.06 s hop (~16 fps, 6.5× denser than before), Harmonic Product Spectrum with 4 harmonics for true-fundamental selection (kills octave errors common in voice tracking), parabolic peak interpolation in log-magnitude for sub-bin frequency precision, smoothing OFF (preserves every fast pitch change), 30 ms min event. Bass: same engine with 0.15 s hop, 8192 FFT, 5-harmonic HPS, 3-frame median, 100 ms min event. Adaptive silence gate (HPS-peak-strength median × 0.15) drops unvoiced frames automatically.
- **Splitter notes modal: real piano roll**. Replaced the stack-style "auto-pack into rows by collision" layout with vertical position = MIDI pitch. Sticky-left keyboard column shows note labels per row (black-key rows shaded, C rows bold). Each event = horizontal bar at its MIDI row spanning [start, end]. Range auto-fits detected events ±2 semitones. For chord events, `splitterChordRootMidi()` parses the root letter+accidental from the label and places the bar at that root in octave 4.
- **Splitter notes modal: scrollable, zoomable timeline**. Click a stem (anywhere except interactive bits) opens a fullscreen overlay with a horizontally scrollable timeline. Time axis with ticks at "nice" intervals. Zoom buttons. Click an event to seek. Animated cursor follows playback; auto-scrolls to keep cursor visible. Closes on X / backdrop / ESC.
- **Splitter: per-stem timelines with waveform + click-to-seek**. Each stem-track is now a 2-row tile: controls + 44 px waveform strip. SVG rects rendered at low opacity (cyan 20% / orange 28% when soloed). Click anywhere on a timeline (or the master transport bar) to jump the global playhead. RAF-driven cursor on every timeline.
- **Cloudflare Pages**: added `_headers` (sets `Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy: require-corp`) so the deployed site is cross-origin isolated and ML mode runs at full multi-thread speed automatically. README updated with deploy steps.
- **Splitter: ML mode (Demucs ONNX)**. New Quality toggle: Fast (DSP) | Accurate (ML — Demucs). Lazy-loads ONNX Runtime Web from jsdelivr and the `demucs-web` ES module from esm.sh on first use. Fetches the 172 MB `htdemucs_embedded.onnx` from Hugging Face's static hosting (HF used as a CDN — audio never leaves the browser; inference is local via WebGPU/WASM). Stem layout switches to original/vocals/drums/bass/other. Environment-aware warn box explains expected speed: file:// → single-thread WASM (15-25 min/song); HTTP w/ COOP/COEP → multi-thread WASM (~3-5 min); WebGPU available → ~2-4 min. Added `server.py` for local dev with the right headers.
- **Splitter: tighter HPSS** — 2-pass + bigger kernels + bass-band HPSS. Median kernels 17→31 (sharper sustained-vs-transient discrimination). Mask power 2→3 (sharper Wiener masks). Pass 1 → harmonic₁ + percussive₁; pass 2 runs HPSS again on percussive₁, recovers any sustained content that leaked. Bass extraction now: lowpass mix at 280 Hz, then HPSS on that low band → harmonic — kicks get caught in pass 2 percussive instead of leaking through.
- **Splitter: progress bar + percentage during processing**. Splitter status pill now shows a colored gradient bar with percentage that walks: mix 2% → STFT 28% → median-h 52% → median-p 74% → soft masks 78% → iSTFT-h 90% → iSTFT-p 99% → bass 100%.
- **Header: tighter spacing + icon-only buttons on narrower viewports**. Compressed button padding/font/gap. At ≤1500 px viewport, button labels hide (icons only) and KEY/SOUND labels disappear so the whole header collapses onto one row.
- **Header: shrink logo to natural size** so tools sit on the same row as the logo. `flex: 0 0 auto` on H1, `height: 48px` + `width: auto` on the logo.
- **Splitter v0 scaffold + HPSS DSP separation**. New "Splitter" header tool button + full main view. Modeled like Listener (`GENRES.splitter` with `isSplitter:true`). Scaffold ships file upload, sync transport, 4-track mixer with per-stem mute/solo/volume. v0 commit had stub processing (all stems share original buffer); follow-up commit added real HPSS-based DSP separation with the Driedger-Müller algorithm — STFT → median-filter spectrogram horizontally (harmonic) and vertically (percussive) → soft Wiener masks → iSTFT each. Hand-rolled radix-2 FFT (~50 lines, no deps), STFT/iSTFT with Hann window + 75% overlap-add. Bass = lowpass(harmonic, 220Hz) via OfflineAudioContext.
- **Listener fix**: upload-button + drag-drop handlers were being wired in `setupListener()` (page init) but the elements live inside `buildListenerViewSkeleton` (lazy on first activation). Moved all dynamic-element wiring into the skeleton builder.
- **Listener: audio file upload mode** (alternative to live mic). Upload button + drag-drop. `decodeAudioData` → `BufferSource` → analysers + destination. Small file player UI with play/pause/progress/X close. Mic and file mutually exclusive.
- **Listener: removed the Voices section** (bass/chord/top tiles). Chroma loop simplified back to a single tight pass.
- **Listener tuning auto-correction disabled** (over-correction risk). The previous compensation used `Math.round(offsetSemis)` on the kernel PC mapping. Since the offset is capped at ±50 cents (= 0.5 semis), `Math.round` was effectively a step function: 0 below 50¢, ±1 whole semitone at the boundary — guaranteed wrong-note shift at the edge. Removed the PC shift entirely. The estimation logic stays and surfaces in the UI as a passive `input ±N¢` readout (only when |offset| ≥ 12¢) so the user can decide to retune their gear.
- **Instrument signal chains improved for 6 voices**. Piano + Clean Electric Guitar untouched (sounded good). Synth → "Poly Synth" with `PolySynth(MonoSynth)` + filter envelope + chorus + reverb. Electric Piano tuned to harmonicity 1.999 (metallic tine) with tremolo + chorus + room. Acoustic Guitar switched to `PolySynth(MonoSynth)` with strong filter envelope (true pluck) + body resonance peaks at 220 Hz / 1.5 kHz. Strings now have vibrato + deeper chorus + 4s hall + 100 Hz highpass. Organ switched to `PolySynth(FMSynth)` (harmonicity 2 = octave drawbar) + Leslie emulation (vibrato + tremolo). Distorted Guitar got a pre-distortion mid-boost (Tube-Screamer "honk") + ping-pong delay stereo widener.
- **Listener accuracy — Tier 2 + log-frequency CQT-style chroma (Tier 3 #8)**:
  1. **Log-frequency note-kernel chroma** — replaces flat FFT-bin→PC mapping. `buildListenerNoteKernels()` precomputes a triangular kernel (±50 cents) per MIDI note from C2 to C6, aggregating FFT bins into per-note energies before summing into 12 PC bins. Cleaner low-pitch resolution without a heavy DSP rewrite.
  2. **Adaptive noise floor** — EMA of RMS during quiet frames; silence threshold = floor + 6 dB. Capped between –90 and –45 dB. Slow drift up vs fast drift down.
  3. **Tuning offset estimate** — magnitude-weighted average of cents-deviation from equal temperament, slow EMA. Surfaced as info, *not* applied (see entry above).
  4. **Honest confidence** — replaced the misleading "X% match" (top score normalized to itself) with a label based on the top-1 vs top-2 gap: locked in (≥15%) / stable (5–15%) / ambiguous (<5%). Color-coded with the gap %.
- **Listener UI bug fixes**:
  - Alt confidence bars were rendering at zero height because `.listener-alt-bar-fill` was an inline `<span>`. Added `display: block` to both the bar and fill plus a `min-width: 2px` so 0% bars still show a sliver.
  - Chord-card toggle hardened. Refactored `openListenerChordDetail` into a clean open/close pair (`closeListenerChordDetail`) sharing a `syncListenerActiveCard` helper.
  - **X close button** added at top-right of `#chord-detail-panel` (only shown in listener view), explicitly closes the panel.
- **Click any chord card → opens chord detail** (info-sidebar's piano + guitar voicings, "where can I go from here", etc). Uses existing `renderChordDetail()` machinery. Body class `has-chord-detail` controls visibility; CSS hides every section except `#chord-detail-panel` so only voicings show. Toggle behavior on the card body, action buttons (Play/Pair/Add) `stopPropagation`. Active card highlighted.
- **Suggestion cards redesigned as a chord-tile grid** (`auto-fill, minmax(230px, 1fr)`, gap 10px). Each tile shows from→to flow ("C → G"), Roman numeral badge, chord notes, the reason, and three labeled buttons (Play / Pair / Add) with Play styled as the orange-accent primary. Hover lifts +1px with soft shadow.
- **Listener header restructured**: title + Start button on a single row (no more giant whitespace gap on wide viewports), description on a full-width row below. Bottom border under the header removed.
- **Listener mic status pill**: small colored dot prefix (grey when off, cyan pulsing when listening, red on error) instead of monospace "Mic off" text. Level meter row hidden when mic is off (`#listener-view.is-listening` class) — no more empty 8 px outline taking up space.
- **Logo / brand mark**: `logo.png` (cropped FYmuse wordmark) loaded as `<img>` and stretched to full available width in the H1 (max-height 96 px sanity cap). Replaces the previous text wordmark + Phosphor music-note icon. Tagline "chord progression finder" removed. Old `.brand-mark` gradient styles removed; Space Grotesk still loaded for any future use.
- **Listener accuracy upgrade — Tier 1**. Four orthogonal improvements bumped synthetic-test accuracy from 14/19 → 18/19 with much wider score margins:
  1. **Harmonic-aware templates** — chord templates are now built by summing the harmonic series profile (`LISTENER_HARMONIC_PROFILE` — h1/h2/h4/h8 octaves, h3/h6 fifths, h5 maj3, h7 m7) at every chord tone. Real audio's overtone bleed now matches the templates instead of working against them. Built by `buildHarmonicTemplate(intervals)`.
  2. **Bass-note detection** — a separate low-band chroma (70-180 Hz, computed in the same FFT pass) finds the dominant pitch class in the bass. Required to be clearly ahead of the second-strongest bass-band PC (>30% gap) or it's dropped as ambiguous. Used to (a) display slash-chord notation `C/E` when bass differs from root, (b) label inversion (1st / 2nd / 7th in bass / slash), (c) apply a `LISTENER_BASS_BOOST = 1.15` multiplier to candidates whose root matches the bass — disambiguates F#dim vs rootless D7 etc.
  3. **Median smoothing on raw chroma** — element-wise median over the last 3 raw chroma frames before the EMA low-pass. Kills transient spikes from cymbal hits, vocal sibilance, etc.
  4. **Onset detection + vote reset** — spectral flux (sum of positive frame-to-frame magnitude changes) tracked with an EMA baseline (`fluxAvg`). When this frame's flux exceeds 2.5× baseline (and an absolute floor), the rolling history + `lockedKey` are wiped so a newly-struck chord locks in fast instead of fighting the previous one.
  5. **Decision hysteresis** — once a chord is locked in (`listenerState.lockedKey`), a new candidate must beat the locked one's tallied score by `LISTENER_HYSTERESIS = 1.10` to take over. Stops sus2/major/dom7 from flickering between each other on stable input.

  Quality template weights also tuned: dim 0.78→0.86, aug 0.70→0.74, m7b5 0.74→0.78. New state fields on `listenerState`: `rawChromaHistory`, `bassPc`, `prevSpectrum`, `fluxAvg`, `lockedKey`. The chroma + bass + flux are computed in a single FFT-bin pass per frame for efficiency.

- **Listener promoted from side panel to a full main view** (mirrors Playground). New `GENRES.listener` entry with `isListener:true`; `renderAll()` branches to `showListenerView()` + `renderListener()`. View skeleton is built lazily by `buildListenerViewSkeleton()` into `#listener-view` inside `#graph-panel`. `body.view-listener` CSS class hides the info-sidebar so the section spans full width. Two-column grid (`5fr | 7fr`, collapses under 1100px). The old `<aside id="listener-panel">` side panel and its PANEL_TO_BTN entry are gone; the header Listener button now switches `state.genreKey` like Playground does. Mic auto-stops via the renderAll guard whenever Listener is no longer the active genre.
- **Listener — real-time chord detection from mic + next-chord suggestions** (originally added as a side panel; see above for the full-view promotion). `getUserMedia` audio runs through an FFT AnalyserNode, magnitudes are folded into a 12-bin chroma vector, and matched against 10 chord-quality templates × 12 roots via cosine similarity. Rolling-history majority vote stabilizes the call. Suggestions combine genre transition data + a universal moves table + synthetic V7/IV-of-detected. Mic never connects to destination (no feedback). Code: `listenerState`, `LISTENER_TEMPLATES`, `LISTENER_UNIVERSAL_MOVES`, `listenerStart/Stop/Loop`, `listenerScoreChroma`, `suggestNextChords`, render functions.
- **Keyboard shortcuts on every Playground chord card**. Each card gets a key from `1234567890qwertyuiopasdfghjklzxcvbnm` shown as a bottom-left monospace badge. Pressing the key plays the chord and flashes the card orange. Listener gates on `state.genre.isPlayground` and ignores text-input focus + modifier keys. `playgroundKeyMap` rebuilds on each `renderPlayground()`.
- **Stop button moved into Builder controls** alongside Play / Rest / Clear. Removed standalone Stop buttons from playground header and genre-graph header (Walk-the-graph stays in graph header).
- **Drag-and-drop chords onto Path Finder**. Playground chord cards and graph chord nodes (SVG `<g>`) are now `draggable="true"`. Drop on `#path-from` or `#path-to` to set From/To. Drop target highlights with `.drop-target` class (orange border + glow). If the dropped numeral isn't already in the dropdown options, it's appended on the fly. Both selects listen for `dragover` / `dragleave` / `drop`.
- **Custom Chord side panel** (header tool button + 460px right overlay). Pill-button rows for Root / Triad / 7th / 9th / 11th / 13th compose chords like `Cm7add9add11`. Live preview of name + notes. Play and Add-to-Builder. Mutually exclusive with Path Finder and Melody Mode.
- **New queue item type**: `{chord, rhythm}` for custom absolute chords. `playProgression`'s `resolve` returns `item.chord` directly. Builder chips show `(custom)` suffix to distinguish from Roman numeral entries.
- **Builder Clear now also re-renders Playground** so chord cards' in-builder ✓ badges and cyan tints clear too.
- **Metronome button is icon-only** — removed the "Metronome" / "Stop" text label. Tooltip + active class indicate state.
- **Project moved to `~/fymuse/`** with main file renamed to `index.html` (was `chord_progression_finder.html`). Page title: "FYMuse — Chord Progression Finder". Original header brand was "FY" (white) + "Muse" (orange); since replaced by `logo.png` (see entries above).
- **Layout precedence rules**: side panels take width preference; main panel never shrinks because of side panels (they overlay); builder drawer's right edge shifts to `right: 460px` when any side panel is open via `body.side-panel-open` CSS class managed by `syncBodyPanelState()`. Smooth 0.32s cubic-bezier transition.
- **Side panels reverted to fixed-position overlays** (briefly experimented with inline flex columns but the user wanted main untouched). Mutually exclusive — opening one closes the other via `closeAllSidePanels()` then `openSidePanel()`.
- **Info Sidebar is now toggleable** via a "Sidebar" header button (default visible). Uses `.collapsed` class on `#info-sidebar` to animate `flex-basis: 0`. Main panel reflows when sidebar collapses/expands.
- **Header tools group** consolidated: `[Playground][Path Finder][Melody Mode][Songwriter][Sidebar]` in a unified pill bar. Each toggles its respective panel/view.
- **CSS scope fix**: `aside` selector was matching both the info sidebar AND side panels (since they're all `<aside>` elements), giving them unwanted padding/border. Fixed by scoping to `main > aside:not(.side-panel)`.
- **No more backdrop on side panels** — main panel stays interactive while a side panel is open.
- Removed yellow focus banner that appeared on chord hover/click
- Playground extracted from genre picker into its own header tool button
- Path Finder + Melody Mode became right slide-in panels (mutually exclusive, with backdrop + ESC) — later removed backdrop
- Songwriter became a top shutter (was a bottom collapsible before)
- Builder drawer now has fullscreen mode (75vh) in addition to collapsed/expanded
- Tempo, Loop, Metronome moved from drawer to header transport bar
- Removed Add-to-Builder mode toggle (always inspect on click; use + button on cards or detail panel to add)
- Phosphor duotone icons replacing emojis throughout
- Inter (display) + JetBrains Mono (code) typography upgrade with refined color palette
- Custom thin scrollbars
- Per-chord rhythm subdivisions — each chord has duration in beats, not internal repeats
- Rest chip support — silent gaps with same rhythm options
- "+ Append" button per song section (multiple builder queues per section)
- Lyrics chord markers display as actual chord names (parsed via romanToChord)
- Drag-to-reorder chips in Builder
- Loop fix — sync timing was drifting due to cumulative setTimeout delays; setTimeouts are now per-iteration
- Metronome sync — Play waits for next downbeat when metronome is running
- Acoustic Guitar rebuilt without PluckSynth (which had compat issues in Tone v14)
- setInstrument volume override removed (each factory sets its own headroom)
- Minor key support — 12 minor keys + scale-aware roman numeral resolution
- Guitar fretboard horizontally flipped — nut on right, low E on top
- Path Finder + Melody Mode + Songwriter algorithms
- Build-your-own progression with quick-add and drag-reorder
- 8 instruments via Tone.js (synth + sampler + custom signal chains)
- Chord graph hover-focus (dim unrelated edges)
- 10 genres with full data (chords, transitions, progressions, substitutions, moods)

---

## Known limitations / future ideas

- **YouTube URL extraction is local-only.** YouTube blocks every known cloud datacenter IP from `yt-dlp` / `youtubei.js`-style extraction. The deployed site can't reliably do it; the local `server.py` (residential IP) can. See the "Cloud-side YT extraction: tried, removed" entry above for the full saga.
- **No persistence** — everything in-memory per session. No save/load to disk or localStorage.
- **No undo/redo** — destructive actions (Clear, Delete) are immediate.
- **Mobile not optimized** — works narrow but not ergonomic.
- **Single open side panel** — Path Finder and Melody Mode are mutually exclusive (opening one closes the other). Info Sidebar is independent.
- **Genre Graph in minor mode** is "best effort" — genres are authored with major-key Roman numerals, so switching to minor reinterprets degrees with minor scale spacing; some chord choices look unusual.
- **No tempo automation** — single BPM per progression.
- **Loop drift in non-4-beat progressions** — if the cycle's total duration isn't a multiple of 4 beats, looping won't stay locked to the metronome across iterations.

Reasonable next features:
- localStorage persistence of song sections + builder state
- MIDI export (`.mid` download)
- Light theme toggle
- Undo/redo stack
- Mobile responsive tuning
- Onboarding tour overlay
- Save/load `.fymuse` JSON project files

### Phase 2: shared YT extraction without cloud bot-detection pain

Right now Phase 1 = "deployed site for upload, local server.py for YT URLs." Each band member who wants the one-click YT flow runs their own `server.py`. To remove that per-user setup, the planned upgrades are:

- **Self-hosted always-on box (recommended next step).** A Raspberry Pi 5 ($35 one-time) or any old laptop running `server.py` 24/7 at someone's home or the rehearsal space. Expose to the band via **Cloudflare Tunnel** (free, no port-forwarding needed, no static IP needed) → a stable HTTPS URL like `https://fymuse.your-band.com`. Residential IP solves YouTube. One machine to maintain. Whole band uses it like a normal website. ~30 min setup once. Annual cost: ~$5 of electricity.
- **Desktop app distribution (further future).** Wrap `server.py + yt-dlp + ffmpeg + a WebView` shell as Electron or Tauri so each member downloads `FYmuse.dmg` / `FYmuse.exe`. No terminal, no Python install. Best UX, biggest maintenance lift.

### Anti-pattern: cloud-side YT scraping

Don't bother building this again. Tried Render free tier, Fly.io, Cloudflare Pages Functions with `youtubei.js`, multi-client fallback (TV / iOS / Android / Web / YT Music / Embedded), Cloudflare Access ACL gating, Render Secret Files for cookie injection — every variation loses to YouTube's bot detection within hours of going live. The only architectures that survive at scale are paid residential-proxy networks (~$50-200/month) or a fleet of rotating throwaway Google accounts; both involve part-time SRE attention. For a personal/band tool the math doesn't work.
