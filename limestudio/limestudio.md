# Lime Studio — Band Performance Controller

## What this is

A native desktop app (Python backend + single-file HTML frontend, shown in a real window via pywebview) that a band runs on a laptop during live shows. It replaces the need for Ableton for bands who just need:

- Audio-reactive stage lighting (DMX)
- Click track routed to IEMs
- Spoken cue system (count-ins, section callouts)
- Setlist manager with per-song settings

Think of it as a lightweight Ableton for bands who don't use Ableton.

---

## How to run

### Quick start — run it on your Mac (native window)

Open **Terminal** and paste this once (it sets up an isolated virtualenv, so it
won't hit Homebrew's PEP 668 "externally-managed-environment" error or a corporate
pip mirror):

```bash
cd ~/fymuse/limestudio
python3 -m venv .venv
source .venv/bin/activate
PIP_INDEX_URL=https://pypi.org/simple pip install -r requirements.txt
python3 desktop.py
```

The Lime Studio window opens. **Every time after that**, it's just:

```bash
cd ~/fymuse/limestudio
source .venv/bin/activate && python3 desktop.py
```

Quit the window (or Ctrl-C in Terminal) to stop it. For the live mic
(reactive lights + BPM detect) also run `brew install portaudio` then
`pip install -r requirements-optional.txt` inside the activated venv.

> `PIP_INDEX_URL=https://pypi.org/simple` is only needed if your global pip is
> pointed at an unreachable mirror (e.g. a company Artifactory while off-VPN).
> On a normal setup you can drop it.

`desktop.py` boots the Flask backend and opens it in a native window via pywebview — no browser, no Electron, no Node.

**Platform notes:**
- **macOS** — works out of the box (`pywebview` pulls in pyobjc).
- **Windows** — needs the Edge **WebView2** runtime (preinstalled on Win 11; otherwise grab it from Microsoft).
- **Linux** — also install a GUI backend: `pip install "pywebview[qt]"` (PyQt) or the GTK stack (`python3-gi`, `gir1.2-webkit2-4.0`).

### Browser mode (no window deps)

```bash
cd fymuse/limestudio
pip install flask flask-sock numpy pyaudio
python3 server.py
# Open http://localhost:4748
```

Either way, it works without PyAudio/NumPy — the app falls back to a built-in audio/lighting simulator, so you can build and test the whole UI with no hardware. The frontend also degrades to a self-contained local mode if it can't reach the backend at all.

### Packaged desktop app (double-clickable)

Build a standalone app with PyInstaller — no Python needed on the target machine:

```bash
cd fymuse/limestudio
./build.sh           # macOS / Linux   (Windows: build.bat)
```

Output:
- **macOS** → `dist/Lime Studio.app` (`open dist/Lime Studio.app`). It's unsigned, so first launch is right-click → **Open** to clear Gatekeeper. The bundle declares a mic-usage string, so macOS prompts for microphone access when you turn Audio on.
- **Windows** → `dist/Lime Studio/Lime Studio.exe`
- **Linux** → `dist/Lime Studio/Lime Studio`

**Build on the target OS** — PyInstaller doesn't cross-compile, so the macOS app must be built on a Mac. `build.sh` does everything inside a throwaway **virtualenv** (`.venv/`), so it works with Homebrew/managed Python and never hits the PEP 668 "externally-managed-environment" error or touches system pip. It installs core deps, best-effort-installs the optional mic libs (`requirements-optional.txt` — `numpy`/`pyaudio`, which need PortAudio; the build continues and ships simulator mode if they're absent), regenerates the icon, and runs `LimeStudio.spec`. The spec bundles `index.html` as data and pulls in the DMX (`pyserial`), MIDI (`mido`+`rtmidi`), and window (`pywebview`) backends. Set `LIMESTUDIO_NO_WINDOW=1` to run the packaged app (or `desktop.py`) as a headless server with no window.

---

## Project files

```
fymuse/limestudio/
├── server.py         backend — Flask + WebSocket, audio analysis, click, DMX sim
├── desktop.py        native-window launcher (pywebview)  ← run this
├── index.html        single-file frontend (4 views)
├── requirements.txt  dependencies
└── limestudio.md        this file
```

---

## Hardware (future — not needed to build yet)

### To connect to production's rig at a venue:
- **ENTTEC DMX USB Pro** (~$100) — USB to DMX adapter, plug into your laptop
- Ask production for: a DMX feed (XLR out) + their fixture channel map

### For your own rehearsal rig (~$400 total):
- ENTTEC DMX USB Pro (~$100)
- 4–6x Chauvet DJ SlimPAR Pro or ADJ 5P Hex (~$50–80 each)
- Standard 3-pin XLR DMX cables

### At a venue:
- You bring: laptop + ENTTEC dongle
- Production provides: fixtures, rigging, DMX patch sheet
- You plug your ENTTEC into their DMX feed, enter their channel addresses, and your software drives their lights

### ArtNet (modern venues):
- Some venues have ArtNet nodes (DMX over WiFi/ethernet) — no dongle needed, just send UDP packets over their network

---

## Architecture

```
Mic/Line-in → PyAudio → NumPy FFT
                              ↓
              Beat detector + 3-band energy (bass/mids/highs)
                              ↓
              Scene engine → DMX channel values
                              ↓
         pyserial → ENTTEC USB Pro → XLR cable → fixtures

Python Flask server ←→ WebSocket ←→ Browser UI
```

All real-time communication between backend and frontend is over WebSocket (`/ws`). REST endpoints handle one-off actions.

---

## Project structure

```
fymuse/limestudio/
├── server.py        ✓ DONE — backend: Flask + WS, scene engine, patching
├── dmx_output.py    ✓ DONE — DMX transports: ENTTEC USB Pro + Art-Net + sim
├── beat_detect.py   ✓ DONE — live tempo (BPM) detection
├── midi_input.py    ✓ DONE — MIDI cue triggers (foot pedal / pad controller)
├── desktop.py       ✓ DONE — pywebview native-window launcher (+ headless mode)
├── index.html       ✓ DONE — single-file frontend (4 views)
├── LimeStudio.spec     ✓ DONE — PyInstaller build spec
├── build.sh / .bat  ✓ DONE — one-command app build
├── generate_icon.py ✓ DONE — makes icon.icns / icon.ico / app_icon.png
├── requirements.txt ✓ DONE — dependencies
├── limestudio.md       this file (canonical spec)
├── MEMORY.md        chronological change history
└── ROADMAP.md       known gaps vs a full live rig + prioritized future work
```

---

## Backend (server.py) — DONE

**Port:** 4748

**WebSocket events (server → client):**

| Event   | Payload                                      | Description                        |
|---------|----------------------------------------------|------------------------------------|
| `state` | full state object                            | Full sync on connect or state change |
| `beat`  | `{beat, bpm, time_sig, downbeat}`            | Fires every beat when click running |
| `audio` | `{bass, mid, high}` (0.0–1.0 each)          | Audio energy, fires ~20x/sec       |
| `cue`   | `{text}`                                     | Spoken cue triggered               |
| `dmx`   | `{channels: [0..255, ...]}`                  | DMX channel values for UI preview  |

**WebSocket actions (client → server):**

| Action          | Data                                      | Description                        |
|-----------------|-------------------------------------------|------------------------------------|
| `set_setlist`   | `{setlist: [...]}`                        | Replace full setlist               |
| `activate_song` | `{idx: N}`                                | Set active song, load its BPM/scene |
| `click_start`   | `{bpm, time_sig}`                         | Start click track                  |
| `click_stop`    | `{}`                                      | Stop click track                   |
| `update_click`  | `{bpm, time_sig}`                         | Update BPM/time sig while running  |
| `trigger_cue`   | `{text: "3, 2, 1, Go!"}`                  | Speak a cue via TTS                |
| `set_lighting`  | `{scene, color, brightness, num_fixtures, fade}` | Update lighting settings (`fade` = default scene crossfade, seconds) |
| `set_scene`     | `{scene, fade?}`                          | Switch scene; optional `fade` (s) overrides the default, 0 snaps |
| `set_effect`    | `{type, rate, depth}`                     | Effect: none/pulse/wave/strobe/rainbow/music/flash; rate in beats/cycle, depth 0–1 |
| `set_position`  | `{idx, pan, tilt}`                        | Set a fixture's home pan/tilt (0–255) |
| `mixer_connect` | `{host}`                                  | Link to an XR18 over OSC (empty host disconnects) |
| `mixer_set`     | `{address, value}`                        | One live mixer param (recall-safe set only) |
| `mixer_query`   | `{}`                                      | → `mixer_levels` event with the param cache |
| `mixer_capture` | `{name}`                                  | Snapshot the desk as a named mix scene |
| `mixer_apply`   | `{id}`                                    | Recall a mix scene (fader glide)   |
| `mixer_rename`  | `{id, name}` / `mixer_delete` `{id}`      | Manage mix scenes                  |
| `save_profile`  | `{name, slots}`                           | Define a fixture layout: comma codes r,g,b,w,d,p,t,pf,tf,- |
| `delete_profile`| `{name}`                                  | Remove a user profile (blocked while patched) |
| `save_look`     | `{name}`                                  | Capture the live rendered fixture state (incl. effect) as a named look |
| `rename_look`   | `{id, name}`                              | Rename a look                      |
| `delete_look`   | `{id}`                                    | Delete a look (active → falls back to static) |
| `set_patch`     | `{patch: [{base, profile}, ...]}`         | Replace the fixture patch          |
| `auto_patch`    | `{count, profile}`                        | Auto-lay N fixtures from address 1 |
| `list_ports`    | `{}`                                      | Request serial ports (→ `ports` event) |
| `connect_output`| `{mode, port, host, universe, fps}`       | Connect a DMX transport            |
| `disconnect_output` | `{}`                                  | Blackout + disconnect (back to sim) |
| `use_detected_tempo` | `{}`                                 | Snap the click to the detected BPM |
| `set_autofollow`| `{on: bool}`                              | Click auto-follows detected tempo  |
| `midi_list_ports` | `{}`                                    | Request MIDI input devices (→ `midi_ports`) |
| `midi_connect`  | `{port}`                                  | Open a MIDI input device           |
| `midi_disconnect` | `{}`                                    | Close the MIDI device              |
| `midi_set_mapping` | `{mapping: [...]}`                     | Replace the trigger→action mapping |
| `midi_learn`    | `{index}` (or null)                       | Arm learn for a binding (next press captures it) |
| `midi_sim`      | `{type, number, value}`                   | Inject a MIDI message (Test / no hardware) |

Extra server → client events: `ports` `{ports:[...]}`, `output` (output status), `tempo` `{bpm, confidence}` (~2×/sec while audio is on), `midi` (MIDI status + mapping), `midi_ports` `{ports:[...]}`, `midi_activity` (last message), and `dmx` now also carries `fixtures: [{r,g,b,m}, ...]`.

### MIDI cue triggers

`midi_input.py` reads a foot pedal / pad controller (via `mido` + `python-rtmidi`)
and maps each note/CC to an action. **Press-edge only** — note-on with velocity>0
or CC≥64 — so a pad fires once on press, not again on release. Bindings are
`{trigger:{type:"note"|"cc", number}, action:{type, ...}}`. Action types:
`cue_index` (fire the active song's Nth cue), `cue_text`, `click_toggle`,
`tap_tempo`, `use_detected_tempo`, `blackout`, `scene`, `chase_advance`,
`next_song`, `prev_song`. The **Learn** flow arms a binding so the next pad press
captures its trigger; **Test** injects a message with no hardware via `midi_sim`.
Default mapping: notes 60/62/64/65 → cues 1–4, 36 → click toggle, 37 → blackout,
38 → tap tempo, 39 → chase, 43/45 → next/prev song. New REST: `/api/midi/ports`,
`/api/midi/status`.

**REST endpoints:**

| Method | Path                  | Description                        |
|--------|-----------------------|------------------------------------|
| GET    | `/`                   | Serves index.html                  |
| GET    | `/api/state`          | Full state snapshot                |
| GET    | `/api/audio/devices`  | List input devices                 |
| POST   | `/api/audio/start`    | Start audio capture                |
| POST   | `/api/audio/stop`     | Stop audio capture                 |
| POST   | `/api/chase/advance`  | Advance chase scene one step       |
| GET    | `/api/capabilities`   | What's available (numpy, pyaudio, pyserial, dmx) |
| GET    | `/api/dmx/ports`      | List serial ports for ENTTEC       |
| GET    | `/api/dmx/status`     | Current DMX output status          |

**State object shape:**

```json
{
  "setlist": [
    {
      "title": "Song Name",
      "bpm": 120,
      "time_sig": 4,
      "key": "A",
      "scene": "reactive",
      "notes": "...",
      "cues": [
        { "label": "Count in", "text": "4, 3, 2, 1", "beat": 0 }
      ]
    }
  ],
  "active_song_idx": 0,
  "click": {
    "running": false,
    "bpm": 120,
    "time_sig": 4,
    "beat": 0
  },
  "audio": {
    "running": false,
    "energy": { "bass": 0.0, "mid": 0.0, "high": 0.0 }
  },
  "lighting": {
    "scene": "reactive",
    "color": [255, 80, 0],
    "brightness": 255,
    "num_fixtures": 4
  },
  "dmx_preview": [0, 0, 0, 0, ...]
}
```

**Lighting scenes:**

| Scene      | Behavior                                               |
|------------|--------------------------------------------------------|
| `reactive` | Bass→red, mid→green, high→blue, brightness from energy |
| `chase`    | One fixture lit at a time, rotates on `chase/advance`  |
| `static`   | Solid color at set brightness                          |
| `off`      | Blackout                                               |

**Looks (user palettes):** `state.looks` = `[{id, name, fixtures: [{r,g,b,m}]}]`.
A look is captured from the live render (Capture in the Lighting view) and is
valid anywhere a scene name goes — as the string `look:<id>` — in `set_scene`,
the song lighting lane, and MIDI scene actions. Looks tile across rigs with
more fixtures than the capture; a missing look renders as static (lights stay
on). Looks persist in show.json and travel inside `.limeshow` bundles
(imports merge by id, never overwrite).

**Mixer (XR18):** Lime Studio remote-controls a Behringer XR18 over OSC (UDP
10024) — no audio passes through the laptop. Scenes capture faders, mutes,
the 6 bus sends (IEM mixes), pan, the FX1 reverb send and the 4-band channel
EQ; **preamp gain is live-only** — editable in the console's channel detail
panel (click a strip name: gain/pan/reverb/EQ graph) but never captured or
recalled, so a song change can't push a hot mic into feedback. Workflow:
dial the desk in → **Capture** in the Mixer tab → assign the mix in the song
editor (`song.mix`) → activation recalls it with a smoothstep fader glide
(~0.8 s). With no desk connected everything runs against a simulator. Scenes
persist in show.json and travel in `.limeshow` bundles. The Mixer tab is also
a live surface: sends-on-faders strips per bus (Main + IEM 1-5 + Click).

**Mounting corrections:** patch entries may set `swap` (pan↔tilt axes),
`inv_p`, `inv_t` — applied only when writing DMX, so looks/fades/UI stay in
logical space. Toggles live on the Position rows. Looks can be fired live
from the Performance view's Looks row or any MIDI binding's "Set scene".

**Moving heads:** profiles may include `p/t` (pan/tilt) and `pf/tf` (16-bit
fine) slots — builtins `MH-PTRGBD` and `MH16-PTRGBD`, or define any layout
with `save_profile`. Each patched fixture has a home pan/tilt (Position
sliders); looks store positions per fixture, and because scene changes
crossfade, switching looks sweeps heads smoothly (fractional mid-fade
positions render on the fine channels). Effects never modulate position.

**Effects:** `lighting.effect {type, rate, depth}` modulates the rendered
output per fixture, synced to the click via a beat clock (integer phase = on
the beat; free-runs at the last tempo when stopped). `pulse` breathes the
dimmer (peaks on the beat), `wave` spreads the pulse across the rig, `strobe`
flashes at each cycle start, `rainbow` rotates hue across fixtures, `music`
drives the dimmer from a smoothed live-audio bass envelope (palette-true
reactivity for any look), `flash` punches brightness on the beat with a
natural decay (no mic required). Effects apply after crossfade blending and
never on blackout. A look stores its effect; applying the look restores both.

**Grand master:** `lighting.master` (0–255) scales the final output of
everything — including looks' captured intensities — after effects. Capturing
a look under a dimmed grand master stores un-dimmed values.

**Lights master switch:** `lighting.on` (bool). False = stage dark (output
zeroed) while the scene/look/lane configuration keeps running underneath;
True = instant restore. The perf view's icon-only power button and the MIDI
`blackout` action toggle it. Activating a song never touches lighting.

**Crossfades:** every scene change blends from the last rendered fixture values
into the live-rendered target (smoothstep easing) over a fade time — the
default lives in `lighting.fade` (seconds, Lighting view "Scene fade" slider),
`set_scene` takes a per-change override, and lighting-lane entries carry
`fade` in **beats** (`light_map: [{bar, scene, fade}]`, converted at the live
tempo when fired). Blackout (perf pad, MIDI) always snaps. Chained fades
depart from the blended mid-fade value — no jumps.

---

## Frontend (index.html) — DONE

Single dark-themed HTML file. Four views:

### 1. Setlist
- Ordered list of songs
- Drag to reorder
- Click to activate (highlights active song)
- Add / remove / edit songs inline
- Each song stores: title, BPM, time signature, key, scene, notes, cues[]

### 2. Song Settings (side panel or modal)
- Edit BPM (with tap tempo button)
- Time signature selector (3/4, 4/4, 6/8)
- Key selector
- Lighting scene picker
- Cue list editor — add spoken cues with label + text

### 3. Lighting Simulator
- Grid of fixture "lights" (colored circles) showing live DMX values
- Scene selector buttons (Reactive / Chase / Static / Off)
- Color picker for static/chase modes
- Brightness slider
- Audio energy bars (bass / mid / high) — live from WebSocket
- Fixture count selector

### 4. Performance Mode (full-screen)
- Large song title + next song
- Giant BPM display
- Beat indicator (flashes on downbeat)
- One-tap cue buttons (pre-loaded from active song's cue list)
- Blackout button
- Lighting sim strip along bottom

### Global controls (always visible header)
- Play/Stop click track
- BPM nudge (±1, ±5)
- Quick cue buttons: "4, 3, 2, 1" / "Last chorus" / "Last verse" / custom
- Audio input toggle

### TTS cues (browser-side)
Use the Web Speech API (`window.speechSynthesis`) — no server round-trip needed. On `cue` WebSocket event, speak the text.

```js
function speakCue(text) {
  const utt = new SpeechSynthesisUtterance(text);
  utt.rate = 1.1;
  utt.pitch = 1.0;
  window.speechSynthesis.speak(utt);
}
```

### Click track (browser-side)
Use Web Audio API for the actual click sound — precise timing, not affected by JS event loop jitter. The server fires `beat` events over WebSocket (for UI flash/sync), but the audio click itself should be generated in the browser for tightness.

```js
// On beat event from server, also trigger AudioContext click
function playClick(downbeat) {
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.connect(gain); gain.connect(audioCtx.destination);
  osc.frequency.value = downbeat ? 1000 : 800;
  gain.gain.setValueAtTime(0.8, audioCtx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.05);
  osc.start(); osc.stop(audioCtx.currentTime + 0.05);
}
```

---

## DMX output — DONE (v1.1 + v1.2)

Real light output lives in `dmx_output.py` and is driven by the scene engine in
`server.py`. Three transports, switchable live from the Lighting view's **DMX
Output** card:

| Mode      | Transport                          | Needs                        |
|-----------|------------------------------------|------------------------------|
| `sim`     | none — on-screen preview only      | nothing (default)            |
| `enttec`  | ENTTEC DMX USB Pro over USB serial  | `pyserial` + the dongle      |
| `artnet`  | Art-Net (ArtDMX) over UDP :6454     | nothing — just a node IP     |

A dedicated refresh thread retransmits the full 512-channel universe at a fixed
rate (default 40 fps, adjustable 10–44) — DMX wants continuous refresh, not
change-only. Connect/disconnect is safe mid-show; closing a transport sends one
**blackout frame** first so fixtures don't latch on.

**Wire formats** (both pure functions, unit-tested):
- ENTTEC: `[0x7E][label 6][len_lo][len_hi][0x00 start code + 512 ch][0xE7]`, payload length 513.
- Art-Net: `"Art-Net\0"` + OpCode `0x5000` (LE) + ProtVer 14 (BE) + seq + physical + SubUni/Net + length 512 (BE) + 512 data bytes.

### Fixture profiles

Each patched fixture has a **profile** defining its channel layout (offsets from
its base address):

| Profile | Width | Channels            |
|---------|-------|---------------------|
| `RGB`   | 3     | R · G · B           |
| `RGBD`  | 4     | R · G · B · Dimmer  | (default)
| `RGBW`  | 4     | R · G · B · White   |
| `RGBWD` | 5     | R · G · B · White · Dimmer |
| `DIM`   | 1     | Dimmer only         |

Master-dimmer semantics: fixtures **with** a dimmer slot get raw RGB on the
colour channels and the master on the dimmer; fixtures **without** one get the
master baked into RGB. White is derived as `min(R,G,B)`.

### Patch convention

Each fixture has a **1-indexed DMX base address** + a profile. The default patch
lays fixtures back-to-back from address 1 (fixture 1 → ch 1.., next fixture →
base + profile width). At a venue, get their channel sheet and set each
fixture's base address + profile in the **Patch** card; the engine writes each
fixture's channels at `base-1 + slot offset` in the universe.

---

## Milestones

- **v1** ✓ Simulator mode, all 4 UI views, click + cues + lighting
- **v1.0.1** ✓ Native desktop window via pywebview (`desktop.py`)
- **v1.1** ✓ ENTTEC USB Pro integration via pyserial (real DMX out)
- **v1.2** ✓ Art-Net output over UDP for modern venues
- **v1.2.1** ✓ Per-fixture patching + fixture profiles + beat-synced chase
- **v1.3** ✓ Beat detection from live audio (BPM auto-detect + auto-follow)
- **v1.4** ✓ MIDI input for cue triggers (foot pedal, pad controller)
- **v2** — Setlist export/import, show history, multiple DMX universes
