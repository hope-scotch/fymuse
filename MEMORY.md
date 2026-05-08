# FYMuse — Project Memory

A single-file music theory and songwriting tool. Helps you explore chord progressions across genres, compose with rhythm subdivisions, write song sections with lyrics, and find connections between any two chords.

Open `index.html` in any modern browser. No build step.

---

## File structure

```
FYMuse/
├── index.html    # The whole app — single HTML file (~180KB)
└── MEMORY.md     # This file
```

The HTML file contains everything: HTML structure, CSS, JS, music theory engine, audio synthesis, UI rendering. External dependencies are loaded from CDNs.

---

## External dependencies (CDN-loaded)

- **Inter** + **JetBrains Mono** fonts → `fonts.googleapis.com`
- **Phosphor Icons** (duotone style) → `unpkg.com/@phosphor-icons/web@2.1.1`
- **Tone.js v14.8.49** → `cdnjs.cloudflare.com`
- **Salamander piano samples** (only when "Piano" instrument selected) → `tonejs.github.io/audio/salamander/`

Internet required on first load; thereafter the page works offline if cached.

---

## Top-level layout

```
┌─ HEADER ─────────────────────────────────────────────────────────────────────┐
│ Title │ [Playground][Path Finder][Melody Mode][Songwriter][Sidebar] │ Key │ Sound │
│ Tempo Loop Metronome │ Genre pills (Pop, Rock, …)                          │
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
- **Path Finder** and **Melody Mode** slide in from the right edge as 460px-wide overlays — **mutually exclusive** (only one open at a time). They overlay the right side without shrinking the main panel.

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

### Custom Chord (right-side overlay panel)
- Toggled from the header button (mutually exclusive with Path Finder and Melody Mode)
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
| Synth (triangle) | `PolySynth(Synth)` triangle oscillator |
| Piano (sampled) | `Sampler` with Salamander piano samples |
| Electric Piano | `PolySynth(FMSynth)` bell-like envelope |
| Acoustic Guitar | `PolySynth(Synth)` fatsawtooth + filter + light reverb (synth pluck simulation) |
| Clean Electric Guitar | synth → light overdrive → cab filter → EQ → chorus → spring reverb |
| Strings (ensemble) | 4 detuned saws → filter → chorus → hall reverb |
| Organ | `PolySynth(Synth)` sine + sustained envelope |
| Distorted Guitar (Muse/LP) | synth → heavy distortion → HP → cab sim → smile-curve EQ → compressor → plate reverb → limiter |

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

- **Keyboard shortcuts on every Playground chord card**. Each card gets a key from `1234567890qwertyuiopasdfghjklzxcvbnm` shown as a bottom-left monospace badge. Pressing the key plays the chord and flashes the card orange. Listener gates on `state.genre.isPlayground` and ignores text-input focus + modifier keys. `playgroundKeyMap` rebuilds on each `renderPlayground()`.
- **Stop button moved into Builder controls** alongside Play / Rest / Clear. Removed standalone Stop buttons from playground header and genre-graph header (Walk-the-graph stays in graph header).
- **Drag-and-drop chords onto Path Finder**. Playground chord cards and graph chord nodes (SVG `<g>`) are now `draggable="true"`. Drop on `#path-from` or `#path-to` to set From/To. Drop target highlights with `.drop-target` class (orange border + glow). If the dropped numeral isn't already in the dropdown options, it's appended on the fly. Both selects listen for `dragover` / `dragleave` / `drop`.
- **Custom Chord side panel** (header tool button + 460px right overlay). Pill-button rows for Root / Triad / 7th / 9th / 11th / 13th compose chords like `Cm7add9add11`. Live preview of name + notes. Play and Add-to-Builder. Mutually exclusive with Path Finder and Melody Mode.
- **New queue item type**: `{chord, rhythm}` for custom absolute chords. `playProgression`'s `resolve` returns `item.chord` directly. Builder chips show `(custom)` suffix to distinguish from Roman numeral entries.
- **Builder Clear now also re-renders Playground** so chord cards' in-builder ✓ badges and cyan tints clear too.
- **Metronome button is icon-only** — removed the "Metronome" / "Stop" text label. Tooltip + active class indicate state.
- **Project moved to `~/fymuse/`** with main file renamed to `index.html` (was `chord_progression_finder.html`). Page title: "FYMuse — Chord Progression Finder". Header brand: "FY" (white) + "Muse" (orange) with subtle "· chord progression finder" subtitle.
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

- **No persistence** — everything in-memory per session. No save/load to disk or localStorage.
- **No undo/redo** — destructive actions (Clear, Delete) are immediate.
- **No MIDI export** — would be valuable for getting progressions into a DAW.
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
