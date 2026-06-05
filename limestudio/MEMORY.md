# Lime Studio — Project Memory

A native desktop app a band runs on a laptop during live shows: audio-reactive
DMX lighting, click track to IEMs, spoken cues, and a setlist manager. "A
lightweight Ableton for bands who don't use Ableton." Python (Flask + WebSocket)
backend, single-file HTML frontend, shown in a real window via pywebview.

Canonical spec + run/protocol/patch docs: **`limestudio.md`**. This file is the
chronological change history — newest first.

## File structure

```
fymuse/limestudio/
├── server.py        backend — Flask + WS, scene engine, patching, click, cues
├── dmx_output.py    DMX transports — ENTTEC USB Pro (serial) + Art-Net (UDP) + sim
├── desktop.py       native-window launcher (pywebview)  ← run this
├── index.html       single-file frontend — 4 views (Setlist/Lighting/Performance + Song modal)
├── requirements.txt dependencies
├── limestudio.md       canonical spec
└── MEMORY.md        this file
```

## Run

- Desktop: `pip install -r requirements.txt && python3 desktop.py` (native window).
- Browser: `python3 server.py` → `http://localhost:4748`.
- Works with no NumPy/PyAudio/pyserial — falls back to an audio + DMX simulator.
  The frontend also has a self-contained local mode if it can't reach the backend.

---

## Recent change history

**Click routing backend: sounddevice preferred, pyaudio fallback.** User asked what's more solid than PyAudio. Answer recorded: DAWs talk to CoreAudio natively (C++); PortAudio is the industry cross-platform engine (Audacity); PyAudio is its stale binding needing brew+compile; **sounddevice** is the maintained binding whose macOS wheels bundle libportaudio (pure `pip install`, no brew). `ClickOutput` now tries `sd.RawOutputStream` (float32 mono, blocksize 512, no numpy needed) first, falls back to PyAudio, reports `backend` in state; mixing refactored into shared `_mix()` used by both callbacks; `/api/output/audio-devices` lists via sd.query_devices (max_output_channels>0, sd.default.device[1] marked default). `sounddevice>=0.4` added to core requirements.txt. Sandbox import fails with 'PortAudio library not found' (Linux wheel needs system ALSA) — guarded import handles it; works out-of-box on macOS.

**Roadmap #2 v1 — click routed to a dedicated output (IEMs).** New `ClickOutput` in server.py: PyAudio callback stream (44.1k float32 mono, 512-frame buffers) on a user-chosen output device; ticks are pure-python synthesized tones (1000/800 Hz, 50 ms, exp decay — no numpy) mixed in the callback from an `_active` list under a lock. `click_thread` calls `click_out.tick(downbeat)` on both song and free beat paths. `GET /api/output/audio-devices` lists playback devices (marks system default); WS `set_click_output {device|null}` starts/stops; device persisted in show.json (`click_out_device`) and re-opened on load; `_full_state` carries `click_out {device,error,available}`. Client: `clickRouted()` mutes the local click in BOTH paths (onBeat immediate + schedPump pre-scheduled; tracks/voice cues unaffected), header "Outputs" pill (headphones icon, `.live` while routed) opens a modal with a device select (default option = no routing) + availability/error hints. Headless-verified: graceful 404-style fallback without pyaudio, tone synthesis (2205 samples, peak .59), state + persistence shape. NOT verified with real hardware — needs the Mac + interface: device opens, click audible only on chosen output, latency feel vs in-browser click (server tick fires on beat broadcast, so routed click ≈ WS-jitter aligned, not sample-locked to the browser tracks — acceptable for IEM click, note for v2). Remaining for #2: per-channel routing, per-role outputs for tracks/cues.

**Metronome moves to Performance.** Header metronome cluster (transport, BPM input, mini dial, Tap) removed — header is brand + beat dots + Audio/MIDI/conn; Space still toggles. New circular metronome button (pyramid `metro` icon, two concentric solid rings via border+outline, fixed 54px so activation never shifts layout) pinned at the bottom of the perf setlist → `activateSong(null)` = free mode. Middle panel `#perf-freebox` swaps in for the timeline (same flex slot + margins so the bottom sections stay put): 240px concentric dial (rings enlarged r16.5/r14), display-only BPM in a 140px center circle (no input, dial/Tap only), sig pills 3/4·4/4·6/8 (`#free-sig` → update_click), Tap relocated. `.view` uses overflow-y: scroll (invisible-until-hover thumb) so scrollbar appearance can't shift the right edge. Perf header shows "Metronome" when no song. Also: lighting lane renders continuous per-scene bands (sections-style, label edits / lane adds) in its own palette (violet/magenta/teal/grey, `LIGHT_COLORS`), row-1 info block 148px with SCALE + BARS small-caps labels over lime values (select dropdown options forced to normal 13px), step arrows inline next to the number. UI named just "Metronome" (not "Free metronome").

**Lighting lane + editor layout round 2.** New per-bar lighting automation: songs carry `light_map [{bar, scene}]` (migrated both sides; scenes validated against reactive/chase/static/off). Server `click_thread` applies the latest entry ≤ current bar on every bar's "1" (handles seeks/joins; broadcasts state + updates DMX) — live-verified headlessly (static@bar3, off@bar5 with 300bpm 2/4 walk). Editor grows a 5th lane (`.tl-light`, top 118 h 22; rows/inner now 140px tall): lane click → `tlPopLight` scene chips popover, chips colored per scene (`LIGHT_COLORS`), whole-song scene dropdown removed (song.scene remains the activation default). Layout: lane-name legend (Tempo/Sections/Bars/Cues/Lights) in a 60px left gutter (`opts.legend`, editor only — rows margin-left, usable width shrinks), instruction hint removed, Key+Length moved into a toolbar INSIDE the lime card (`.ed-tl-card` wraps toolbar + #ed-tl so re-renders don't destroy wired controls), Done sits beside the lime title (`.ed-top`). Right-edge clipping fixed via `scrollbar-gutter: stable` on .tlw (the styled classic scrollbar was eating layout width after first render); editor panel + views get hover-only scrollbars like #ed-tl. node --check + py_compile + live lane test clean; visuals not eyeballed (headless).

**Editor + perf polish rounds (user-driven).** Perf setlist rows are drag-reorderable (same DnD as Setlist tab; active pointer follows). Editor head reworked: Audition button removed (transport plays from playhead), Lighting scene is a styled dropdown, Length gets custom lime ▲▼ steppers (native webkit spinner hidden; scrub still works), Done is input-height and bottom-aligned. KEYS now interleaves major+minor (C, Cm … B, Bm) for both key selects. The lime card frame sits on the **timeline** (#ed-tl: 12px padding, lime border/tint) — not the settings row; duplicate song-title heading removed, then reintroduced as the editable lime display-font header (`input.ed-title-h`, transparent, placeholder "Song name"). Timeline: per-beat hairline ticks per bar via repeating-linear-gradient sized BW/sig (uses songSegment per bar), wrapped rows stretch BW fractionally (usable = clientWidth − real padding − 2) so full rows end flush right, scrollbar hidden until #ed-tl hover. All `node --check` clean; not eyeballed (headless).

**Perf round 3 (user list).** (1) Header "Count in" quick-cue removed — calls live on the perf pad. (2) Big 66px round play/stop transport beside the perf BPM (`#perf-transport`, lime play ↔ red stop, wired to toggleClick, icon synced in syncTransport); small `.perf-stop` removed, perf-set top padding back to 16px. (3) Setlist row single-click now opens the Song editor (dblclick kept). (4) Section popover: when the clicked bar sits INSIDE an existing section (no marker at that exact bar), a "Delete ‹label›" button removes the covering section; title shows "· inside ‹label›". (5) Bar grid lines raised to rgba .10 (4-bar .22) + lime hover highlight per bar cell for precise seeking. (6) Blackout pad is now a toggle: scene≠off → "Blackout" (red, saves `_preBlackoutScene`); scene=off → "Lights on" (lime, restores saved or reactive); `.perf-cue .ico` gets 8px right margin. Headless-verified only (node --check).

**Six perf/editor UX fixes (user screenshots).** (1) Bar-1 timeline chips ("133 4/4") were half-clipped — `.tl-mark` centers via translateX(-50%); chips at bar 1 now pin left (transform none, left 2px) in both renderers. (2) New cue popover prefills label "Count in" / text "count in" (smart per-sig count) + hint explaining comma-list-per-beat; just Save for a default count-in. (3) `select` styled like inputs (appearance none + data-URI chevron) so Key matches Length. (4) Length-bars scrub stuck to the mouse after release: pointer capture now taken on pointerdown, pointermove bails when e.buttons===0, lostpointercapture also ends. (5) Tabs are full-height rectangular with 2px lime bottom border (glow blob + pill removed); perf "Exit" button removed — replaced by red "Stop" (same spot) that stops the song. (6) Tempo locked while a song drives the click: tempoLocked() guards setBpm/setBpmLive/dial drag/wheel, hdr-bpm disabled, dial dims (.locked), throttled toast "Tempo follows the song — press Stop to take it back"; Stop button visible only while running (syncTransport). NOT eyeballed in the running app (headless).

**Beat-locked counts — voice samples replace live TTS.** User: counts ("1, 2, 3…") still lagged the click. Root cause: speechSynthesis has 100–300 ms variable per-utterance startup, unfixable in-browser. Fix: new `GET /api/voice?text=` on the server renders each short cue text ONCE with the macOS system voice (`say --file-format=WAVE --data-format=LEI16@22050`), trims leading silence to ≤5 ms (`_trim_wav_silence`, keeps 5 ms attack / 80 ms tail), caches in `~/.limestudio/voice/` (filename = sha1(text)). Strict input: `^[a-z0-9 '\-]{1,32}$`; non-mac → 404. Client: `voiceBuffers` cache + `loadVoice`/`playVoiceAt`; `speakNow(text, rate, when)` prefers an AudioBuffer (scheduled at the exact pre-scheduled click time via new `sched.lastBeatT` when the lookahead engine owns audio, immediate otherwise) and falls back to TTS on miss while warming the cache. Prefetch: numbers 1–8 + PERF_CALLS on first pointerdown, song cues/section labels in `preloadSongTracks`, cue parts in `speakCue`. Verified headlessly: trimmer (150 ms lead → 5 ms), route 404/400 paths, traversal rejected, `node --check` clean. NOT verified audibly — needs an ear test on the Mac: count-on-click tightness in free and song mode, sample loudness vs click.

**Brand mark v2 — the real Brandmark lemon, vectorized.** User attached the Brandmark JSON as a file (`uploads/lemon-icon`), so the embedded 768px lemon-wedge PNG could be extracted byte-perfect. It was lime-tinted per the design's BlendColor filter (#B6FF3A, alpha preserved) and vectorized with potracer (trace fidelity IoU 0.995 in pixel space) into a single currentColor path → swapped into `<symbol id="ls-mark">` (all 6 uses update: header, welcome, boot splash, toasts, track loaders, empty state), the favicon data-URI, `brand/limestudio-mark.svg`, and `brand/limestudio-lockup.svg`. `generate_icon.py` now composites `brand/lemon-lime.png` (tinted trimmed bitmap) on the deep-stage tile with a lime halo; app_icon.png/icon.icns/icon.ico regenerated (older sets parked as `.trash_*`). Also: removed the "Band Control" sub/tag from header + welcome, header wordmark 14px, nav got symmetric 10px vertical padding so tab pills no longer touch the divider (user screenshot feedback).

**Lime brand identity — wheel mark + exact wordmark, everywhere.** User supplied the Brandmark logo (Space Age wordmark, lime fruit icon) as raw editor JSON. The wordmark was rebuilt as an exact vector SVG from the JSON's 10 glyph paths (per-glyph bbox verified against declared dims; LIME #B6FF3A / STUD #FFEEE2 / IO #FFF) → `brand/limestudio-wordmark.svg`, inlined as `<symbol id="ls-wordmark">` and used in the header and welcome `h2`. The fruit icon's embedded 45 KB base64 PNG could not be reproduced from pasted chat text (PNG CRC check caught corruption), so a clean single-color lime-wheel mark (rind ring + 8 wedges, currentColor) was designed instead → `brand/limestudio-mark.svg`, `<symbol id="ls-mark">`. The mark now lives everywhere: header + welcome logos (replacing the bar-chart placeholder), a new boot splash (`#boot`, spins via `.lime-spin`, hidden by `hideBoot()` on first `setConn` + 6 s failsafe), busy toasts (any message ending in `…` gets a spinning mark), track-buffer "loading…" rows, the setlist empty state, and the favicon (data-URI). `generate_icon.py` rewritten to draw the lime wheel on the deep-stage tile; `app_icon.png` / `icon.icns` / `icon.ico` regenerated (old ones parked as `.trash_*` — sandbox mount can't delete). `brand/limestudio-lockup.svg` combines mark + wordmark. NOT verified visually in the running app (headless sandbox) — needs an eye test: boot splash timing, header wordmark size (13 px tall), welcome h2 wordmark alignment.

### Roadmap #1 + #3 — backing tracks + sample-locked click engine
Songs can now carry **audio files pinned to bars** (`tracks: [{id,name,bar,gain}]`,
migrated/clamped server+client). Files upload via `POST /api/tracks/upload`
(uuid-named into `~/.limestudio/tracks/`, extension allow-list, strict id check
on `GET /api/tracks/<id>`) — works packaged, persists in show.json.

The client is now the **audio engine**: a Web Audio lookahead scheduler
(`sched`, 40 ms pump, ~220 ms window) pre-schedules click ticks AND track
starts on the same AudioContext clock, computed from the tempo map — click and
tracks are sample-locked and cannot drift apart. Seek/late-start joins a track
mid-file at the exact offset (`secondsBetweenBars`). The server stays the show
authority (cues/lights/MIDI/switching): its beats drive UI + a drift check —
first beat establishes a constant transport offset baseline; deviation > 70 ms
or an unscheduled bar (seek/switch) re-bases the scheduler. `syncAudioEngine`
on every state sync starts/stops/re-targets the engine; oscillators are pushed
into `sched.sources` so stop kills pending ticks too. Free-mode metronome is
unchanged (event-driven click).

Server clock fix: `_beat_sleep` paces beats against **absolute monotonic
deadlines** instead of accumulating `time.sleep(interval)` — removes the
systematic slow-down so re-bases stay rare. Editor gained a **Backing tracks**
panel (upload, start-bar, gain, remove, buffer status) and blue track markers
render on both timeline renderers (editable popover in the editor).

Verified: upload→fetch byte-identical; path traversal rejected; track metadata
survives server restart; JS/ids clean. NOT verified audibly (headless sandbox)
— needs an ear test: track start alignment, seek-join offset, re-base
behaviour under load. Known limits: setlist export JSON references track ids
but doesn't bundle the audio files; per-output routing (click vs tracks) is
roadmap #2.

### Full rename sweep → Lime Studio everywhere
Folder `fymuse/bandmate` → `fymuse/limestudio`; `limepro.md` → `limestudio.md`;
`Limepro.spec` → `LimeStudio.spec`; env vars `LIMEPRO_*` → `LIMESTUDIO_*`
(`LIMESTUDIO_NO_WINDOW`, `LIMESTUDIO_PUBLIC_PYPI`); every remaining
"Limepro"/"Bandmate" text reference replaced with "Lime Studio" across code,
scripts and docs. NOTE: renaming the folder invalidates an existing `.venv`
(virtualenvs hard-code absolute paths) — recreate it or rerun `./build.sh`.
`BANDMATES-READ-ME.md` keeps its name (it addresses the band members).

### Performance round 2 — smart count-ins, auto section announce, layout + scroll fixes
(1) "count in" is now a **smart cue**: `expandCue` client-side expands it at fire
time to one number per beat of the CURRENT signature (1-2-3-4 in 4/4, 1-2-3 in
3/4…); header quick-cues trimmed to a single "Count in" button; demo set +
editor placeholder use it. (2) **TTS latency** reduced: `speakNow` only cancels
when the engine is actually speaking (blanket `cancel()` on idle adds lag), and
the engine is pre-warmed with a muted utterance on first user gesture.
(3) **Auto section announce**: the click thread looks one bar ahead — if a
labelled section starts next bar and the band hasn't put their own cue on the
current bar, it speaks "{label}, 2, 3, …sig" so the section gets a spoken
count-in automatically. Verified: 3/4 song announced "Chorus, 2, 3" exactly at
the start of the bar before, and a user cue suppressed the auto one.
(4) **Perf layout**: compact header (smaller title/BPM, inline sig), Exit moved
top-LEFT (was overlapping the BPM), setlist rail padded below it, smaller beat
dots + cue buttons → ~3 timeline rows visible. (5) **Scroll stability**: perf
timeline only rebuilds when song structure/width changes (`_perfTlKey`),
preserves scrollTop across rebuilds, and wrap-mode autoscroll fires only when
the playhead ENTERS a new row (tracked via `_tl.lastRow`) instead of every beat.
(6) **Bars field scrubs**: drag up/down on the editor's Length(bars) input to
change it (typing still works; ns-resize cursor).

### Tempo-synced cue speech (musical count-ins)
Spoken cues now follow the click instead of reading at a fixed TTS speed.
`speakCue` splits comma-separated text into segments; while the click runs,
segments go into `cueSegQueue` and `onBeat` speaks exactly one per beat — so
"4, 3, 2, 1" lands on 1-2-3-4 of the bar at any tempo/signature (server fires
bar cues just before broadcasting the bar's first beat, so segment one hits the
1). Speech rate scales mildly with BPM (1.0–1.7 around bpm/105) and each
segment cancels the previous utterance — fast tempos clip rather than drift.
Single phrases ("Last chorus") still speak once, on the quantized 1. Queue is
cleared on stop (state handler + toggleClick) so a cancelled count-in doesn't
leak into the next take.

### Timeline UX — wrapped Performance view + lane-based seek/add interaction
Performance's timeline now uses the same wrapped multi-row layout as the editor
(`wrap:true`, barW 30, fills width, vertical scroll only; re-flows on resize).
Resolved the seek-vs-add-marker conflict with **lanes**: clicking the **bar
grid** moves the playhead (seek — crosshair cursor), while clicking empty space
in the **tempo / section / cue lanes** adds that kind of marker at that bar
(copy cursor + lane hover tint, editor only via `opts.onLane` →
`wireLaneClicks`); clicking an existing marker still edits it. Removed the old
3-button bar popover (`tlPopRoot`). Editor seek targets the song being edited:
if it isn't the active song it activates it first, then cues the bar — so
Audition plays from wherever you clicked. Perf grid click also updates the
local playhead + Bar N/len readout instantly.

### Performance polish — bar-quantized switching & cues, concentric dial, wrapping editor
Four refinements. (1) **Song switches land on bar boundaries**: `_activate_song`
queues `click.pending_song` when a song is mid-playback; the click thread lands
the switch exactly when the current bar completes (`_switch_pending`), and a
song that *ends* with a queued switch flows straight into the next one. The
perf setlist rail shows the queued song ("next…", orange) and the toast says
"switching after this bar". (2) **Live cues quantize to the 1**: `_queue_cue`
fires immediately only if idle or right on/after a bar's first beat, otherwise
holds the cue in `_pending_cues`, flushed at the next bar start in both song and
free modes (note `click.beat` stores the *next* beat to fire, hence the
`% time_sig == 1` check). Buttons + MIDI cue actions both route through it.
(3) **Dial rework**: concentric rings (outer arc + two inner rings), drag works
in any direction (dx+dy combined), ~2× more sensitive (0.9 bpm/px, Shift=0.15),
and the big BPM readout is now an editable input — `setHdrBpm` skips updates
while focused so beats don't fight typing. (4) **Editor fills the screen** and
the timeline got a wrapped mode (`renderTimelineWrapped`): bars flow into rows
sized to the available width, growing downward with vertical scroll only —
sections split across rows, markers land in their row, `tlSetPlayhead` handles
both modes, re-flows on window resize. Verified live: cue fired exactly between
beat 3 and the next beat 0; song A finished its bar before B started at its own
tempo; pending_song visible in state then cleared after landing.

### Song timelines — bar-based tempo maps, sections, auto-cues + Performance split view
Songs are no longer one BPM. New model: `tempo_map` `[{bar,bpm,time_sig},…]`
(first entry pinned to bar 1), `sections` `[{bar,label}]`, `cues` `[{bar,label,text}]`,
`length_bars`. `_migrate_song` upgrades legacy single-BPM songs in place (server:
on set_setlist/_load_show/activate; client mirror `migrateSong`), keeping
top-level `bpm`/`time_sig` as derived bar-1 values for old code paths.

`click_thread` now has two modes: **free** metronome (unchanged) and **song** —
it walks the active song's bars, pulling bpm/sig live from the tempo map (so
128→144 or 4/4→3/4 happen exactly at their bar), auto-firing each bar's cues at
beat 0, broadcasting beats with `{bar, beat, bpm, time_sig, section,
length_bars}`, and stopping + rewinding at the last bar. `click_start` arms song
mode when a song is active; new `seek {bar}` action; `click_stop` rewinds.
Verified live: 22-beat walk with tempo flip at bar 5, sig change, sections, both
cues fired, end-stop; legacy-song migration; seek→play from bar 30 of 32.

Frontend: shared `renderTimeline(song, mount, opts)` (tempo/sections/bars/cues
lanes + playhead; `tlSetPlayhead` with auto-scroll). Full-screen **Song editor**
(replaces the old modal everywhere): title/key/length/scene/notes header,
Audition button, and the editable timeline — click a bar → glass popover to add
a tempo change (BPM + tap + sig), section (label + quick chips) or cue (label +
spoken text + preview); click a marker to edit/remove; bar-1 tempo can't be
removed; everything auto-pushes (and the server auto-saves). **Performance** is
now a split view: setlist rail on the left (active song highlighted, click to
load), and on the right the live header (current **section** as the kicker,
title, live BPM), the song's timeline with a smooth lime playhead that follows
beat events and auto-scrolls, a `Bar N / total` readout, beat dots that rebuild
when the signature changes mid-song, cue buttons + blackout. Clicking a bar in
the performance timeline seeks. Setlist tab is just add/reorder/open-editor;
demo set rebuilt to showcase a mid-song speed-up and a 3/4→4/4 switch.

### Rebrand → "Lime Studio" + premium UI overhaul + in-app guides
Renamed the product to **Lime Studio** (window title, header brand + new bar-glyph
logo, app bundle `Lime Studio.app` / `LimeStudio` exe, Info.plist, banners,
build/package scripts, bandmates' guide). (Folder + file names were renamed in a later sweep — see below.)

Full visual upgrade of `index.html` to a "deep stage + lime glow" aesthetic while
keeping the existing palette: new design tokens (SF Pro display/text stack, glass
surface vars, lime-glow vars, premium cubic-bezier easings), an animated ambient
lime background, and a layered premium CSS section re-skinning header / tabs /
cards / modals / song rows / inputs / sliders / buttons as frosted glass with
soft glows, hover lift and smoother transitions. All **emojis removed**, replaced
by an inline SVG icon set (`ICONS`/`ICONS_FILLED` + `ic()` + `hydrateIcons()` for
`[data-ic]`). Class names/IDs preserved so existing JS wiring is intact.

Added all three **guide layers**: a first-run **welcome** card (localStorage
`limestudio.welcomed.v1`), a 6-step **spotlight tour** (lime ring via big
box-shadow cutout, repositions on resize), a slide-out **help drawer / cheatsheet**
(views, click track, shortcuts, hardware; opens via header `?` button or the `?`
key), and **contextual (?) help dots** on view titles + every lighting card
(hover/click → glass popover). Esc closes any of them.

Verified: extracted JS passes `node --check`; zero emojis remain; every `$("id")`
resolves and every `ic()`/`data-ic` name exists; page serves 200 (~129 KB) from
the headless backend. Actual visual look still needs eyeballing on a real display
(sandbox is headless) — run `python3 desktop.py`.

### Packaging — double-clickable desktop app (PyInstaller)
Turned the from-source pywebview launcher into a real distributable app.
`LimeStudio.spec` bundles `desktop.py` (entry) + `index.html` (data) and pulls in
the GUI/MIDI/DMX backends via `collect_all('webview')`, `collect_all('mido')`,
and hiddenimports (`flask_sock`, `serial`, `mido.backends.rtmidi`, `rtmidi`);
windowed (no console), platform icon, and a macOS `BUNDLE` → `Lime Studio.app` with
an Info.plist (mic-usage string for the audio prompt, hi-dpi, bundle id
`com.fymuse.limestudio`). `build.sh`/`build.bat` do install→icon→build in one shot.

`generate_icon.py` (Pillow) draws the app mark — a dark rounded tile with five
glowing "reactive light" bars in the bass/mid/high palette under the lime brand
dot — and exports `app_icon.png` (1024), `icon.icns`, `icon.ico`.

Packaging fix in `server.py`: new `resource_path()` honours `sys._MEIPASS` so
`index.html` resolves both from source and inside the frozen bundle (BASE_DIR
now derives from it). `desktop.py` gained `LIMESTUDIO_NO_WINDOW=1` headless mode
(run the packaged app as a server with no window) — also the CI/test hook.

Verified by an actual PyInstaller build **in the Linux sandbox**: build
completed, and the frozen binary run headless served the full `index.html`
(200, 95 KB) plus `/api/capabilities`, `/api/dmx/ports`, `/api/midi/ports` with
pyserial bundled — proving the spec, data bundling, and frozen path are correct.
The macOS `.app` uses the same spec; **PyInstaller can't cross-compile, so the
Mac build must run on a Mac** (and the unsigned app needs right-click→Open the
first time). Linux `build/` + `dist/` artifacts were moved aside and gitignored.

### v1.4 — MIDI cue triggers (hands-free)
A foot pedal / pad controller can now fire cues, toggle the click, blackout,
tap tempo, advance the chase, and jump songs — nobody touches the laptop mid-song.
New `midi_input.py` (mirrors dmx_output's shape: hardware optional via `mido` +
`python-rtmidi`, graceful `HAS_MIDI` fallback). Pure `normalize()` (mido msg →
`{type, number, value, channel, edge}`) and `resolve(mapping, ev)` — **press-edge
only** (note-on vel>0 / CC≥64) so releases don't double-fire — are unit-testable.
`MidiManager` runs the input port in a thread and routes both real messages and
`inject()` (hardware-free) through one `_dispatch`, with a learn mode that
captures the next press as a binding's trigger. Bindings are
`{trigger:{type,number}, action:{type,...}}`; ten action types incl. `cue_index`
(fires the active song's Nth cue), `tap_tempo`, `next/prev_song`, `blackout`,
`scene`, `chase_advance`.

`server.py`: `midi` manager + `_perform_midi_action` dispatch wired to existing
state/broadcasts; factored out `_active_song()` / `_activate_song()` (the old
inline activate logic now lives here and next/prev reuse it). Server-side tap
buffer for `tap_tempo`. New WS actions `midi_list_ports`/`midi_connect`/
`midi_disconnect`/`midi_set_mapping`/`midi_learn`/`midi_sim`; events `midi`,
`midi_ports`, `midi_activity`; REST `/api/midi/ports`+`/status`; capabilities
report midi.

Frontend: header **🎹 MIDI** button with a connection LED that flashes on every
incoming message, opening a mapping modal — device picker + connect, a per-binding
row (Note/CC + number, **Learn**, action dropdown with inline param for
cue#/text/scene, **Test**, remove), restore-defaults, and a live last-message
line. Fully usable without a controller: triggers can be typed by hand and Test
injects via `midi_sim`.

Verified: resolver unit-tested (note/CC press vs release, hits/misses, normalize
edges, inject + learn capture). Live E2E via `midi_sim` against the running
server — every action confirmed: cue_index fired the song's cues, release was
ignored, click toggled, blackout set scene off, next/prev navigated the setlist,
learn captured a new trigger and the relearned note fired, and tap_tempo computed
119/149/99 BPM from taps at 0.5/0.4/0.6 s. No physical controller in the sandbox
(mido absent → HAS_MIDI False), so the resolve/dispatch/learn path is fully proven
but reading a real device is still an on-hardware check.

### v1.3 — Live tempo (BPM) auto-detect
The click can now follow the band instead of being typed in. New `beat_detect.py`
(pure Python, no NumPy): per-frame energy → half-wave-rectified positive flux
(onset strength) → ring buffer → autocorrelation over musical lags →
**parabolic-interpolated** peak → BPM + confidence, with octave folding into
70–180. Parabolic interpolation was essential — at the ~20–43 Hz envelope rate,
integer-lag resolution near 120+ BPM is several BPM per step; sub-sample lag
fixes it. `estimate_tempo` is pure/unit-tested; `TempoTracker` wraps it with a
6 s window and `configure(fps)` to switch between sim (20 Hz) and live mic
(~43 Hz) sources.

`server.py`: module-level `tempo` tracker + `_detect_tempo(fps, frame)` fed from
both audio threads (gated on `audio.running`; `_live_active` flag stops the sim
from fighting the mic). Broadcasts a `tempo` event ~2×/sec with
`{bpm, confidence}`, stored in `state["audio"].bpm_detected/bpm_confidence`. New
WS actions `use_detected_tempo` (snap the click to the reading) and
`set_autofollow` (click chases detected tempo live when conf ≥ 0.25);
`/api/audio/stop` resets the tracker and clears the reading. The sim thread now
emits a sharp kick on the click grid so detection has something musical to lock
onto without a mic.

Frontend: a pulsing **♪ BPM · conf%** chip in the header (tap to apply) plus an
**↺ Follow** toggle, both shown only while audio input is on; driven by the
`tempo` event. Backend-only feature (needs the server's audio analysis) — the
chip stays hidden in file:// local mode.

Verified: `estimate_tempo` unit-tested at 75–170 BPM (±2.5 clean, ±4 with timing
jitter, octave cases, flat→None). Live E2E against the running server: drove the
sim at 100/132/145 BPM and the detector locked to 99.85 / 133 / 148.5 in steady
state after the window filled; confirmed `use_detected_tempo` snaps the click,
`set_autofollow` flips the flag, and stopping audio clears the reading.

### v1.1 + v1.2 — Real DMX output (ENTTEC + Art-Net) + patching
The whole lighting path went from a UI-only simulator to real hardware output.
New `dmx_output.py` defines three transports behind one `OutputManager`: `sim`
(no-op preview), `enttec` (ENTTEC DMX USB Pro via pyserial), and `artnet`
(ArtDMX over UDP :6454). The manager runs a dedicated refresh thread that
retransmits the full 512-channel universe at a fixed rate (default 40 fps,
10–44) — DMX wants continuous refresh, not change-only — decoupled from scene
compute via `get_universe=lambda: state["dmx"]`. Connect/disconnect is safe
mid-show; `close()` sends a blackout frame first so fixtures don't latch on.
Packet builders (`build_enttec_packet`, `build_artnet_packet`) are pure
functions: ENTTEC frame is `[0x7E][label 6][len_lo][len_hi][0x00 + 512 ch][0xE7]`
(payload 513); Art-Net is `"Art-Net\0"` + opcode 0x5000 (LE) + protver 14 (BE) +
seq + physical + SubUni/Net + length 512 (BE) + 512 bytes.

`server.py` scene engine rewritten around a **patch model**: `state["patch"]` is
a list of `{base (1-indexed DMX addr), profile}`. Profiles (`PROFILES`) define
channel layout: RGB(3) / RGBD(4, default) / RGBW(4) / RGBWD(5) / DIM(1).
Master-dimmer semantics in `_write_fixture`: fixtures *with* a `d` slot get raw
RGB + master on the dimmer; fixtures *without* get RGB pre-scaled by master;
white = min(R,G,B). `_update_dmx_from_lighting` renders the universe from the
patch and also broadcasts a per-fixture `fixtures:[{r,g,b,m}]` preview so the UI
doesn't need to know addressing. Chase now auto-advances one fixture per beat
inside `click_thread`. New WS actions: `set_scene`, `set_patch`, `auto_patch`,
`list_ports`, `connect_output`, `disconnect_output`; new events `ports`,
`output`; new REST `/api/dmx/ports`, `/api/dmx/status`; `/api/capabilities`
now reports pyserial + dmx mode.

Frontend (`index.html`) gained a **DMX Output** card (mode switch, serial-port
picker + rescan, Art-Net host/universe, refresh-rate, connect/disconnect with a
live status LED) and a **Patch** card (per-fixture base + profile, add/remove,
quick auto-patch from the count pills). Stage + perf-strip previews now render
from the per-fixture `fixtures` feed (color scaled by master), via
`fixtureDisplay`/`fixtureList`; local-mode mirrors the scene math in
`localRecomputeDMX`.

Verified hard, since this is hardware code: packet builders unit-tested vs
known-good bytes; a **real Art-Net UDP frame captured** off 127.0.0.1:6454 from
the running server (channels asserted); a **real ENTTEC serial frame captured
through a PTY** (`os.openpty()` → port name to pyserial) — both showed an RGBD
fixture as R=10 G=200 B=255 Dim=200 as patched. Smoke-tested auto_patch
(6×RGBWD → bases 1,6,11,16,21,26), port listing, fixtures preview, beat-synced
chase. No physical dongle/fixture available in the build sandbox, so the
wire-level path is proven but an on-hardware smoke test is still pending on a
real machine.

### v1.0.1 — Native desktop window (pywebview)
Chose pywebview over Electron: the backend is already Python, so wrapping it
needs one pure-Python dep and no Node/Chromium. New `desktop.py` starts
`server.py`'s workers (`click_thread`, `audio_sim_thread`) + Flask in a daemon
thread, polls `/api/capabilities` until up, then opens a native window on
`http://127.0.0.1:4748`. `use_reloader=False` is mandatory (the reloader forks a
second process that would double the workers and detach the window).
`python3 server.py` browser mode is left untouched. Platform notes in limestudio.md
(macOS works out of the box; Windows needs WebView2; Linux needs a qt/gtk
backend). Verified headlessly: the window can't render in the sandbox, but the
exact backend path the window loads serves the index, streams state/beats, and
survives connection churn.

### Bugfix — broadcast() race could kill the click thread mid-show
`broadcast()` iterated `ws_clients` while other threads added/removed clients on
connect/disconnect; hitting the race raised `RuntimeError: Set changed size
during iteration`, and because it fired inside `click_thread`, the **exception
killed the click thread for the rest of the session** (metronome goes silent).
Fix: iterate a snapshot — `for ws in list(ws_clients)`. Stress-tested with 240
rapid concurrent connects/disconnects; the click thread kept firing throughout.

### v1 — Frontend build (index.html)
Built the single-file dark-themed frontend against the existing `server.py` WS +
REST contract. Four views: **Setlist** (drag reorder, click-to-load, inline
add/remove/edit, demo set), **Song Settings** modal (BPM + tap tempo, key, time
sig, scene, notes, cue editor), **Lighting Simulator** (fixture grid, scene
buttons, color/brightness, live energy bars), **Performance Mode** (giant title
+ next, big BPM, downbeat-flashing beat dots, one-tap cues, blackout, light
strip). Always-on header transport: click play/stop, BPM nudge ±1/±5, tap tempo,
quick cues, audio toggle, beat dots, connection LED. Web Audio click + Web Speech
TTS cues fire off server `beat`/`cue` events. Keyboard: Space, ↑/↓ (Shift=±5),
1/2/3. Degrades to a self-contained local mode (client-side click + reactive sim
+ DMX math) when the backend is unreachable, then auto-reconnects. Verified:
extracted JS passes `node --check`; full WS round-trip against the live server
(state/beat/audio/dmx/cue) confirmed.
