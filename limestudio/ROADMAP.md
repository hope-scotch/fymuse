# Lime Studio — Roadmap

**Status: v1 feature-complete, hardware-verified (June 2026).** Every item
below marked ✅ has been tested on the real rig by Shay. What remains is
improvement work to land over time, ordered by how much it matters for a
real show. Ableton Live was the original reference for the gap list.

---

## Shipped ✅

- **Backing-track playback** — audio files pinned to bars (start bar + gain),
  sample-locked to the click via the Web Audio lookahead scheduler, mid-file
  join on seek, survives tempo changes. `.limeshow` export bundles the audio
  so a bandmate's import is complete.
- **Sample-accurate click** — pre-scheduled clicks + tracks on one audio clock
  in song mode; drift-free absolute-deadline pacing on the server.
- **Click → in-ears routing** — Outputs button routes the click to any output
  device (server-rendered via sounddevice; pyaudio fallback); tracks + spoken
  cues stay on the default output for FOH.
- **MIDI clock out** — 24 ppq at the live tempo (tempo map included),
  Start/Stop with the transport. Measured 47.94 Hz @120 bpm, ~2.8 ms jitter.
- **Spoken counts on the click** — cue words rendered once with the macOS
  system voice, silence-trimmed, played as beat-locked buffers; TTS fallback.
- **Odd meters with feel** — 5/4 (3+2), 6/8 (two dotted pulses), 7/8 (2+2+3)
  via a three-level click voice, in the browser click, the scheduler and the
  routed IEM click alike.
- **Lighting automation** — per-bar lighting lane (scene bands on the song
  timeline, applied by the engine on each bar's 1, seek-safe) on top of the
  reactive/chase/static scenes, DMX out (ENTTEC / Art-Net) and patching.
- **Show recording** — REC pill in the header captures the default input to a
  timestamped WAV in `~/.limestudio/recordings`.
- **Performance cockpit** — setlist with drag-reorder + quantized song
  switching, big transport, tempo lock while a song runs, controller-style
  call pad (quantized spoken calls + blackout/lights toggle), tap-the-dial
  free metronome.
- **The rest of v1** — bar-based tempo maps, sections with auto-announce,
  cues, song editor with lane legend + per-beat grid, MIDI pedal triggers
  with Learn, BPM detect/follow, brand identity, packaged Mac app.

## Shipped since ✅

- **Lighting v2** — crossfades, looks, effects (9 types incl. movement),
  moving heads (16-bit) + custom profiles, grand master, mount flags, paint,
  mains switch, console UI + guided tour.
- **Mixer (XR18 remote)** — per-song mix scenes over OSC: capture the desk,
  assign to songs, auto-recall with fader glides on song load. Recall-safe
  (faders/mutes/IEM sends only). Works in sim without the desk.
  NEEDS first hardware test against the real XR18.

## Improvements (over time, in priority order)

1. **Production hardening** — the only remaining show-stopper class of risk:
   swap Flask's dev server for a production WSGI server, watchdog/crash
   recovery, soak-test a 3-hour "show". Do this before a paying gig.
2. **Routing v2** — per-channel routing within one interface (e.g. out 3/4 of
   an 8-out box) and per-role pickers (spoken cues to the IEM feed is the
   likely first ask).
3. **Tempo ramps** — gradual accel/rit curves between bars (stepwise today).
4. **Editor undo/history** — auto-save makes this more important, not less.
5. **Free-mode click pre-scheduling** — the song-mode click is sample-locked;
   the free metronome still plays per-event (fine in practice, tidy to unify).
6. **Lighting depth** — IN PROGRESS (promoted: lighting is the current focus).
   ✅ Scene crossfades everywhere (default fade in seconds, per-lane-entry
   fades in beats, blackout stays instant). ✅ Looks/palettes — capture the
   live stage state into named per-fixture looks ("look:<id>" works anywhere a
   scene name goes: manual, lane, MIDI; bundled in .limeshow). ✅ Effects
   engine — pulse/wave/strobe/rainbow layered on any scene or look, rate in
   beats locked to the click (free-runs between songs), captured into looks.
   ✅ Moving heads + fixture profiles — pan/tilt with 16-bit fine, per-fixture
   home positions, looks store positions and crossfades sweep heads between
   them; user-defined channel layouts (+ Profile) cover rented/venue gear.
   ✅ Musical reactivity v2 — Music effect (audio envelope drives any look's
   dimmer, palette-true) + Flash (beat-locked punch, no mic needed) + grand
   master (output-level fader that also dims looks).
   ✅ Mount flags (pan/tilt invert + axis swap, output-only so looks stay
   clean) · ✅ looks firable from MIDI pedals · ✅ Looks quick-switch row in
   the Performance view. Cue stacks intentionally skipped — the lighting lane
   IS the cue stack, musically. **Lighting v2: CODE-COMPLETE.** Next action:
   eye/ear test on the rig, then rebuild + ship to the band.

## Not planned

- **Ableton Link** — Lime Studio is the only software on stage (band
  decision); hardware syncs via MIDI clock. Revisit only if a Link-enabled
  app ever joins the rig.
- Plugins/instruments/effects, audio warping, multitrack recording/editing,
  automation lanes — that's a DAW. Lime Studio stays the band's *show
  controller*: click, cues, lights, setlist, with backing tracks as the
  ceiling.

---
*See MEMORY.md for the full engineering history. Next concrete action when
desired: `bash build.sh --public` → `bash package-for-band.sh` and hand the
app to the band — their rehearsal feedback reorders this list.*
