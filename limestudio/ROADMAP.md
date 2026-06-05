# Lime Studio — Roadmap & Known Gaps

A frank list of what Lime Studio does **not** do compared to a full live rig
(Ableton Live being the reference), kept as the long-term build list.
Parked here on purpose — revisit when v1 has had real stage time.

---

## Priority order (biggest unlock first)

### 1. Backing-track playback ★ — ✅ SHIPPED (v1: bar-pinned files, gain, mid-file seek join)
Play audio files (stems, pads, sampled count-ins, guide tracks) pinned to bars
of the song timeline, locked to the click. This is the main thing bands
actually run Ableton for live. Today Lime Studio plays zero audio besides the
click tick and TTS cues.
- Audio files attached to a song (start bar + gain per file)
- Sample-accurate start aligned to the bar grid
- Stop/duck on song stop · survive tempo changes (no warping in v1 — just
  bar-aligned triggering)

### 2. Multi-output audio routing — ✅ v1 SHIPPED (click → dedicated device)
Click → drummer's IEMs only (e.g. interface out 3/4); tracks → FOH (out 1/2).
- ✅ Click can be routed to any CoreAudio output device (Outputs button in the
  header): the server renders it via a PyAudio callback stream while tracks +
  spoken cues stay on the default output; browser mutes its local click.
- Remaining: per-CHANNEL routing within one interface, and per-role pickers
  for tracks / cues (cues to IEMs is a likely ask).

### 3. Sample-accurate click scheduling — ✅ LARGELY SHIPPED with #1 (Web Audio lookahead scheduler in song mode + drift-free server deadlines; free-mode click still event-driven)
The click is currently a Python thread (`time.sleep` per beat) → WebSocket →
Web Audio tick scheduled on arrival. A few ms of jitter per beat; fine for most
bands, audibly looser than Ableton's hardware-clock grid.
- Schedule clicks ahead-of-time in Web Audio against absolute timestamps
  (lookahead window), server sends bar/beat *plan*, not per-beat ticks
- Also fixes: webview throttling risk when the window is backgrounded

### 4. MIDI clock out / Ableton Link — ✅ clock out SHIPPED
- ✅ MIDI clock out (24 ppq) following the live tempo (tempo map included),
  Start/Stop with the transport — Clock out picker in the MIDI dialog,
  port persisted. Verified 47.94 Hz @120 bpm, ~2.8 ms pulse jitter.
- Ableton Link: NOT PLANNED — Lime Studio is the only software on stage
  (band decision); hardware syncs via MIDI clock. Revisit only if a
  Link-enabled app ever joins the rig.

---

## Smaller gaps (grab when convenient)

- **Tempo ramps** — changes are stepwise per-bar; no gradual accel/rit curves.
- **Meter depth** — ✅ SHIPPED: 5/4 and 7/8 added everywhere; accent patterns
  give the feel (5/4 = 3+2, 6/8 = two dotted pulses, 7/8 = 2+2+3) with a
  three-level click voice (down / group accent / tick) in browser + routed out.
- **Sampled count-ins / voices** — ✅ SHIPPED: server renders cue words once
  with the macOS system voice (`/api/voice`, silence-trimmed, cached), client
  plays them as Web Audio buffers locked to the click; TTS remains the fallback.
- **Editor undo/history** — no undo in the song editor; mistakes need manual
  fixes. (Auto-save makes this more important, not less.)
- **Show recording** — ✅ SHIPPED: REC button under the perf transport records
  the default input to a timestamped WAV in ~/.limestudio/recordings
  (sounddevice, pyaudio fallback).
- **Lighting depth** — 4 scenes vs real fixture libraries, cue stacks, chases
  with curves, per-section lighting automation. Per-section scene changes is
  the cheap first step.
- **Production hardening** — Flask dev server, no show-length soak tests, no
  crash recovery. Swap to a production WSGI server, add a watchdog, soak-test
  a 3-hour "show".

## Non-goals (for now)
Plugins/instruments/effects, audio warping, multitrack recording/editing,
automation lanes — that's a DAW. Lime Studio stays the band's *show
controller*: click, cues, lights, setlist, with backing tracks as the ceiling.

---
*Context: written after the v1 build (bar timelines, tempo maps, auto count-ins,
quantized switching, DMX/MIDI/BPM-detect, packaged desktop app). See MEMORY.md
for what exists; this file is what doesn't yet.*
