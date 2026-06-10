"""
Lime Studio — Band Performance Controller
Backend server: audio analysis, click track, cue system, DMX simulator
Run: python3 server.py
Open: http://localhost:4748
"""

import array
import asyncio
import json
import math
import os
import struct
import sys
import threading
import time
import uuid
import wave
from pathlib import Path

import dmx_output
import beat_detect
import midi_input
import mixer_osc


def resource_path(name=""):
    """Locate a bundled resource both from source and inside a PyInstaller app.

    When frozen, PyInstaller unpacks data files (index.html) under sys._MEIPASS;
    from source it's just this file's directory.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name) if name else base

# ── optional deps (graceful fallback if missing) ──────────────────────────────
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False

try:
    import sounddevice as sd
    HAS_SD = True
except Exception:          # missing lib OR no usable PortAudio on this box
    HAS_SD = False

try:
    from flask import Flask, jsonify, request, send_from_directory
    from flask_sock import Sock
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

# ── App setup ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(resource_path())   # frozen-safe (sys._MEIPASS when bundled)
app = Flask(__name__, static_folder=str(BASE_DIR))
sock = Sock(app)

# ── Shared state ──────────────────────────────────────────────────────────────
state = {
    "setlist": [],           # list of song dicts
    "active_song_idx": None, # index into setlist
    "click": {
        "running": False,
        "bpm": 120,
        "time_sig": 4,
        "beat": 0,
        "mode": "free",   # "free" metronome | "song" = walk the active song's bars
        "bar": 1,         # position within the song (song mode)
        "pending_song": None,   # song switch queued for the end of the current bar
    },
    "cue_queue": [],         # pending spoken cues
    "dmx": [0] * 512,        # DMX universe (simulator)
    "audio": {
        "running": False,
        "energy": {"bass": 0.0, "mid": 0.0, "high": 0.0},
        "bpm_detected": None,
        "bpm_confidence": 0.0,
        "autofollow": False,   # when True, the click chases the detected tempo
    },
    "lighting": {
        "scene": "reactive",  # reactive | chase | static | off
        "color": [255, 80, 0],
        "brightness": 255,
        "num_fixtures": 4,
        "fade": 0.5,          # default scene crossfade, seconds (0 = snap)
        # tempo-synced effect layered on top of the scene/look output
        "effect": {"type": "none", "rate": 1.0, "depth": 0.6},
        # grand master: output-level scaler applied after everything —
        # unlike `brightness`, it also dims looks (captured m values).
        "master": 255,
        # lights master switch: False = stage dark, scene/look config untouched.
        # THE blackout control (perf power button, MIDI blackout action).
        "on": True,
        # per-fixture paint: [r,g,b] or None per fixture index. Painted lights
        # keep their own colour in Static (and Chase); None = global colour.
        # Capture bakes paints into looks — this is how multicolour states
        # are authored.
        "static_map": [],
    },
    # Per-fixture patch: each fixture has a 1-indexed DMX base address + a
    # profile that defines its channel layout. Built/replaced via the UI.
    "patch": [],
    # User-built looks: named per-fixture states captured from the live render.
    # Referenced anywhere a scene name goes, as "look:<id>".
    "looks": [],   # [{id, name, fixtures: [{r,g,b,m,p,t}, ...], effect?}]
    # User-defined fixture profiles (the practical fixture library):
    # {name: {width, slots}} — same shape as PROFILES, builtins win on clash.
    "profiles": {},
    # XR18 mixer: connection config + named mix scenes (flat OSC param dicts).
    # Songs reference a scene by id; activation recalls it with a fader glide.
    "mixer": {
        "host": "",
        "scenes": [],          # [{id, name, params: {osc_address: value}}]
        "ch_names": ["Lead Vox", "Lead Gtr", "Bass", "Keys", "Drums",
                     "Rhythm Gtr", "Back Vox"],
        "bus_names": ["IEM Vox", "IEM Gtr", "IEM Bass", "IEM Keys", "IEM Drums", "Click"],
    },
}

mixer = mixer_osc.XR18Link()
mixer.channels = len(state["mixer"]["ch_names"])

ws_clients = set()

# ── Fixture profiles ──────────────────────────────────────────────────────────
# slots: r,g,b = colour; w = white LED; d = master dimmer; p/t = pan/tilt;
# pf/tf = pan/tilt fine (16-bit movement). Offsets are 0-based from the
# fixture's base address. Users can define their own layouts (save_profile) —
# that's the practical "fixture library" for rented/venue gear.
PROFILES = {
    "RGB":   {"width": 3, "slots": {"r": 0, "g": 1, "b": 2}},
    "RGBD":  {"width": 4, "slots": {"r": 0, "g": 1, "b": 2, "d": 3}},
    "RGBW":  {"width": 4, "slots": {"r": 0, "g": 1, "b": 2, "w": 3}},
    "RGBWD": {"width": 5, "slots": {"r": 0, "g": 1, "b": 2, "w": 3, "d": 4}},
    "DIM":   {"width": 1, "slots": {"d": 0}},
    # generic moving heads (8-bit and 16-bit movement)
    "MH-PTRGBD":   {"width": 6, "slots": {"p": 0, "t": 1, "r": 2, "g": 3, "b": 4, "d": 5}},
    "MH16-PTRGBD": {"width": 8, "slots": {"p": 0, "pf": 1, "t": 2, "tf": 3,
                                          "r": 4, "g": 5, "b": 6, "d": 7}},
}
DEFAULT_PROFILE = "RGBD"
SLOT_CODES = ("r", "g", "b", "w", "d", "p", "t", "pf", "tf", "-")


def _profiles_all():
    """Builtin + user-defined profiles, user names never shadow builtins."""
    out = dict(state.get("profiles") or {})
    out.update(PROFILES)
    return out


def _profile_has_pt(prof):
    s = prof.get("slots", {})
    return "p" in s or "t" in s


def _default_patch(n, profile=DEFAULT_PROFILE):
    """Lay n fixtures out back-to-back from DMX address 1."""
    w = _profiles_all().get(profile, PROFILES[DEFAULT_PROFILE])["width"]
    return [{"base": i * w + 1, "profile": profile, "pan": 128, "tilt": 128}
            for i in range(n)]


def _active_patch():
    if state["patch"]:
        return state["patch"]
    return _default_patch(state["lighting"]["num_fixtures"])


# ── Song timeline model ───────────────────────────────────────────────────────
# A song is a bar-based timeline:
#   tempo_map: [{bar, bpm, time_sig}, ...]  sorted, first entry pinned to bar 1
#   sections:  [{bar, label}, ...]          (Verse / Chorus / ...)
#   cues:      [{bar, label, text}, ...]    auto-spoken when the playhead hits the bar
#   length_bars: total bars
def _migrate_song(song):
    """Upgrade legacy single-BPM songs in place; keep bpm/time_sig as the
    derived bar-1 values so older code paths stay valid."""
    if not isinstance(song, dict):
        return song
    tm = song.get("tempo_map") or []
    if not tm:
        tm = [{"bar": 1, "bpm": song.get("bpm", 120), "time_sig": song.get("time_sig", 4)}]
    tm = sorted((dict(m) for m in tm), key=lambda m: int(m.get("bar", 1)))
    tm[0]["bar"] = 1
    for m in tm:
        m["bar"] = max(1, int(m.get("bar", 1)))
        m["bpm"] = max(20, min(300, int(m.get("bpm", 120))))
        m["time_sig"] = int(m.get("time_sig", 4)) or 4
    song["tempo_map"] = tm
    song.setdefault("sections", [])
    song.setdefault("length_bars", 32)
    song["length_bars"] = max(1, min(999, int(song.get("length_bars", 32))))
    for c in song.get("cues", []) or []:
        c.setdefault("bar", 1)
        c["bar"] = max(1, int(c.get("bar", 1)))
    # backing tracks: audio files pinned to a bar, played by the client engine
    trs = song.get("tracks") or []
    for t in trs:
        t["bar"] = max(1, int(t.get("bar", 1)))
        try:
            t["gain"] = max(0.0, min(2.0, float(t.get("gain", 1.0))))
        except (TypeError, ValueError):
            t["gain"] = 1.0
    song["tracks"] = trs
    # lighting lane: scene changes pinned to bars (applied by the click thread)
    lm = []
    for L in song.get("light_map") or []:
        sc = str(L.get("scene", "")).lower()
        if sc in ("reactive", "chase", "static", "off") or sc.startswith("look:"):
            try:
                fade = max(0.0, min(64.0, float(L.get("fade", 0) or 0)))
            except (TypeError, ValueError):
                fade = 0.0
            lm.append({"bar": max(1, int(L.get("bar", 1))), "scene": sc,
                       "fade": round(fade, 2)})
    song["light_map"] = sorted(lm, key=lambda L: L["bar"])
    # per-song mix: a dict of XR18 params, auto-saved as the song plays.
    # Legacy string values (old scene-id model) are resolved into params.
    mx = song.get("mix")
    if isinstance(mx, dict):
        song["mix"] = _clean_mix_params(mx)
    elif isinstance(mx, str) and mx:
        sc = _mix_scene_by_id(mx)
        song["mix"] = _clean_mix_params(sc["params"]) if sc else {}
    else:
        song["mix"] = {}
    song["bpm"] = tm[0]["bpm"]
    song["time_sig"] = tm[0]["time_sig"]
    return song


def _song_segment(song, bar):
    """The tempo-map entry in effect at `bar`."""
    seg = song["tempo_map"][0]
    for m in song["tempo_map"]:
        if m["bar"] <= bar:
            seg = m
        else:
            break
    return seg


def _song_section(song, bar):
    """The section label in effect at `bar` (or None)."""
    label = None
    for s in sorted(song.get("sections", []), key=lambda x: x.get("bar", 1)):
        if s.get("bar", 1) <= bar:
            label = s.get("label")
        else:
            break
    return label


# ── DMX hardware output (ENTTEC / Art-Net / simulator) ────────────────────────
output = dmx_output.OutputManager(get_universe=lambda: state["dmx"])

# ── Live tempo detection (v1.3) ───────────────────────────────────────────────
tempo = beat_detect.TempoTracker(fps=20.0)
_live_active = False   # True while the real mic thread is the audio source


def _detect_tempo(fps, frame):
    """Feed current energy into the tracker; broadcast + auto-follow ~2×/sec."""
    e = state["audio"]["energy"]
    tempo.push(e.get("bass", 0) + e.get("mid", 0) + e.get("high", 0))
    bpm, conf = tempo.estimate()
    state["audio"]["bpm_detected"] = bpm
    state["audio"]["bpm_confidence"] = conf
    if frame % max(1, int(fps * 0.5)) == 0:
        broadcast("tempo", {"bpm": bpm, "confidence": conf})
        if (state["audio"]["autofollow"] and state["click"]["running"]
                and bpm and conf >= 0.25):
            target = max(20, min(300, int(round(bpm))))
            if target != state["click"]["bpm"]:
                state["click"]["bpm"] = target
                broadcast("state", _full_state())


# ── Shared helpers ────────────────────────────────────────────────────────────
def _active_song():
    idx = state["active_song_idx"]
    if idx is not None and 0 <= idx < len(state["setlist"]):
        return state["setlist"][idx]
    return None


def _activate_song(idx):
    """Make song `idx` active. If a song is mid-playback, the switch is queued
    and lands musically — when the current bar completes."""
    c = state["click"]
    if (c["running"] and c["mode"] == "song" and idx is not None
            and idx != state["active_song_idx"]
            and 0 <= idx < len(state["setlist"])):
        c["pending_song"] = idx
        broadcast("state", _full_state())
        return
    c["pending_song"] = None
    _store_active_mix()                  # the outgoing song keeps its desk state
    state["active_song_idx"] = idx
    if idx is not None and 0 <= idx < len(state["setlist"]):
        song = _migrate_song(state["setlist"][idx])
        seg = _song_segment(song, 1)
        c.update({"mode": "song", "bar": 1, "beat": 0,
                  "bpm": seg["bpm"], "time_sig": seg["time_sig"]})
        # lighting deliberately untouched — the master switch + lane rule the stage
        _recall_song_mix(song)
    else:
        c.update({"mode": "free", "bar": 1, "beat": 0})
    broadcast("state", _full_state())


def _switch_pending():
    """Land a queued song switch (called at a bar boundary). True if switched."""
    idx = state["click"]["pending_song"]
    state["click"]["pending_song"] = None
    if idx is None or not (0 <= idx < len(state["setlist"])):
        return False
    _store_active_mix()                  # the outgoing song keeps its desk state
    state["active_song_idx"] = idx
    song = _migrate_song(state["setlist"][idx])
    seg = _song_segment(song, 1)
    state["click"].update({"mode": "song", "bar": 1, "beat": 0,
                           "bpm": seg["bpm"], "time_sig": seg["time_sig"]})
    _recall_song_mix(song)
    broadcast("state", _full_state())
    return True


def _clean_mix_params(params):
    """Filter a param dict to the managed (recall-safe) set — strips gain and
    any foreign addresses."""
    ok = set(mixer_osc.managed_addresses(16))
    out = {}
    for a, v in (params or {}).items():
        if a not in ok:
            continue
        try:
            out[a] = int(v) if a.endswith("/on") else max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            pass
    return out


def _clean_mix_scene(sc):
    """Sanitise one mixer preset from disk/import; None if unusable."""
    try:
        sid = str(sc.get("id", ""))[:16]
        params = _clean_mix_params(sc.get("params"))
        if not sid or not params:
            return None
        return {"id": sid, "name": (str(sc.get("name", "")).strip()[:32] or "Mix"),
                "params": params}
    except Exception:
        return None


def _store_active_mix():
    """The active song owns the desk: snapshot the current mixer state into
    it. Skipped mid-glide so a recall in flight can't half-save."""
    if mixer.gliding:
        return
    s = _active_song()
    if s is not None:
        s["mix"] = mixer.snapshot()


def _mix_scene_by_id(sid):
    for sc in state["mixer"]["scenes"]:
        if sc.get("id") == sid:
            return sc
    return None


def _recall_song_mix(song):
    """Every song owns a mix. Has one → glide the desk to it. First time
    activated → adopt whatever the desk sounds like right now."""
    mx = song.get("mix")
    if isinstance(mx, dict) and mx:
        mixer.apply(mx)
    else:
        song["mix"] = mixer.snapshot()


# ── Quantized cue firing ──────────────────────────────────────────────────────
# Live-triggered cues (buttons, MIDI) land on a bar's "1": fired immediately if
# we're right on/just after the 1, otherwise queued for the next bar start.
_pending_cues = []


def _queue_cue(text):
    if not text:
        return
    c = state["click"]
    # c["beat"] holds the NEXT beat to fire; % sig handles free mode's running counter
    just_after_one = (c["beat"] % max(1, c["time_sig"])) == 1
    if c["running"] and not just_after_one:   # mid-bar → wait for the next 1
        _pending_cues.append(text)
    else:                                      # idle, or right on/after the 1 → now
        broadcast("cue", {"text": text})


def _flush_pending_cues():
    while _pending_cues:
        broadcast("cue", {"text": _pending_cues.pop(0)})


# ── MIDI input (v1.4) — hands-free cue triggers ───────────────────────────────
_midi_taps = []


def _perform_midi_action(action, ev=None):
    """Execute a mapped MIDI action. Runs in the MIDI listener thread."""
    t = action.get("type")
    if t == "cue_index":
        song = _active_song()
        cues = song.get("cues", []) if song else []
        i = int(action.get("index", 0))
        if 0 <= i < len(cues):
            text = cues[i].get("text") or cues[i].get("label", "")
            if text:
                state["cue_queue"].append(text)
                _queue_cue(text)
    elif t == "cue_text":
        _queue_cue(action.get("text", ""))
    elif t == "click_toggle":
        state["click"]["beat"] = 0
        state["click"]["running"] = not state["click"]["running"]
        broadcast("state", _full_state())
    elif t == "blackout":
        # toggles the lights master switch (instant both ways)
        state["lighting"]["on"] = not state["lighting"].get("on", True)
        _update_dmx_from_lighting()
        broadcast("state", _full_state())
    elif t == "scene":
        _set_scene(action.get("scene", "reactive"))
        broadcast("state", _full_state())
    elif t in ("next_song", "prev_song"):
        n = len(state["setlist"])
        if n:
            cur = state["active_song_idx"]
            if cur is None:
                cur = -1 if t == "next_song" else n
            nxt = cur + 1 if t == "next_song" else cur - 1
            _activate_song(max(0, min(n - 1, nxt)))
    elif t == "chase_advance":
        global _chase_pos
        _chase_pos += 1
        _update_dmx_from_lighting()
    elif t == "tap_tempo":
        global _midi_taps
        now = time.time()
        if _midi_taps and now - _midi_taps[-1] > 2.0:
            _midi_taps = []
        _midi_taps.append(now)
        if len(_midi_taps) >= 2:
            gaps = [_midi_taps[i] - _midi_taps[i - 1] for i in range(1, len(_midi_taps))]
            avg = sum(gaps) / len(gaps)
            if avg > 0:
                state["click"]["bpm"] = max(20, min(300, int(round(60.0 / avg))))
                broadcast("state", _full_state())
        if len(_midi_taps) > 6:
            _midi_taps.pop(0)
    elif t == "use_detected_tempo":
        bpm = state["audio"].get("bpm_detected")
        if bpm:
            state["click"]["bpm"] = max(20, min(300, int(round(bpm))))
            broadcast("state", _full_state())


def _on_midi_activity(ev):
    # manager already stored `last`; just notify the UI (learn + activity dot)
    broadcast("midi_activity", ev)


def _on_midi_learned(idx):
    _save_show()
    broadcast("midi", midi.state())
    broadcast("state", _full_state())


midi = midi_input.MidiManager(
    on_action=_perform_midi_action,
    on_activity=_on_midi_activity,
    on_learned=_on_midi_learned,
)
midi_clock = midi_input.MidiClockOut(
    lambda: (state["click"]["running"], state["click"]["bpm"]))


# ── Show persistence ──────────────────────────────────────────────────────────
# Everything a band would hate to retype — setlist, fixture patch, lighting,
# MIDI mapping — auto-saves to ~/.limestudio/show.json and reloads on launch.
CONFIG_DIR = Path.home() / ".limestudio"
SHOW_FILE = CONFIG_DIR / "show.json"


# ── Click output routing ─────────────────────────────────────────────────────
# Renders the click on a dedicated output device (PyAudio callback stream) so
# it can feed e.g. the drummer's IEMs while backing tracks and spoken cues
# stay on the system default output. The browser mutes its local click while
# a device is selected.
class ClickOutput:
    RATE = 44100

    def __init__(self):
        self._pa = None
        self._stream = None
        self._lock = threading.Lock()
        self._active = []           # [waveform, position] of currently sounding ticks
        self.device = None
        self.channel = None         # 1-based output channel (None = mono/default)
        self._nch = 1               # channels the stream is opened with
        self.error = None
        self.backend = None
        self._w_down = self._tone(1000.0)
        self._w_mid = self._tone(890.0)
        self._w_beat = self._tone(800.0, vol=0.42)

    @staticmethod
    def _tone(freq, dur=0.05, vol=0.6):
        n = int(ClickOutput.RATE * dur)
        w = array.array("f", bytes(4 * n))
        for i in range(n):
            t = i / ClickOutput.RATE
            w[i] = vol * math.exp(-t / 0.012) * math.sin(2 * math.pi * freq * t)
        return w

    def state(self):
        return {"device": self.device, "channel": self.channel,
                "error": self.error,
                "available": HAS_SD or HAS_PYAUDIO,
                "backend": self.backend}

    def start(self, device_idx, channel=None):
        """channel: 1-based output channel on the device. None = plain mono
        (PortAudio puts it on ch 1). With e.g. channel=3 on the XR18's USB,
        the click rides its own desk channel while the browser's tracks keep
        USB 1/2 — per-source routing within one interface (Routing v2)."""
        self.stop()
        if device_idx is None:
            return True
        try:
            ch = max(1, min(32, int(channel))) if channel else None
        except (TypeError, ValueError):
            ch = None
        nch = ch if ch else 1
        if HAS_SD:                      # preferred: maintained, wheels bundle PortAudio
            try:
                self._stream = sd.RawOutputStream(
                    samplerate=self.RATE, blocksize=512, device=int(device_idx),
                    channels=nch, dtype="float32", callback=self._sd_cb)
                self._stream.start()
                self.backend = "sounddevice"
                self.device = int(device_idx)
                self.channel = ch
                self._nch = nch
                self.error = None
                return True
            except Exception as e:
                self.error = str(e)
                self._stream = None      # fall through to pyaudio if present
        if HAS_PYAUDIO:
            try:
                self._pa = pyaudio.PyAudio()
                self._stream = self._pa.open(
                    format=pyaudio.paFloat32, channels=nch, rate=self.RATE,
                    output=True, output_device_index=int(device_idx),
                    frames_per_buffer=512, stream_callback=self._cb)
                self._stream.start_stream()
                self.backend = "pyaudio"
                self.device = int(device_idx)
                self.channel = ch
                self._nch = nch
                self.error = None
                return True
            except Exception as e:
                self.error = str(e)
                self._teardown()
                return False
        if not (HAS_SD or HAS_PYAUDIO):
            self.error = "no audio backend — pip install sounddevice"
        return False

    def stop(self):
        self._teardown()
        self.device = None
        self.channel = None
        self._nch = 1
        self.backend = None

    def _teardown(self):
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        try:
            if self._pa:
                self._pa.terminate()
        except Exception:
            pass
        self._stream = None
        self._pa = None
        with self._lock:
            self._active = []

    def tick(self, accent):
        """accent: 2 = downbeat · 1 = group accent (5/4, 6/8, 7/8 feels) · 0 = tick"""
        if not self._stream:
            return
        lvl = 2 if accent is True else int(accent or 0)
        w = self._w_down if lvl == 2 else (self._w_mid if lvl == 1 else self._w_beat)
        with self._lock:
            self._active.append([w, 0])

    def _mix(self, frame_count):
        buf = array.array("f", bytes(4 * frame_count))
        with self._lock:
            keep = []
            for t in self._active:
                w, p = t[0], t[1]
                n = min(frame_count, len(w) - p)
                for i in range(n):
                    buf[i] += w[p + i]
                t[1] = p + n
                if t[1] < len(w):
                    keep.append(t)
            self._active = keep
        return buf

    def _render(self, frames):
        """Mono click, interleaved into the stream's channel layout — zeros on
        every channel except the chosen one, so other apps' audio on the same
        device (the browser's tracks on 1/2) mixes cleanly underneath."""
        mono = self._mix(frames)
        if self._nch == 1:
            return mono.tobytes()
        buf = array.array("f", bytes(4 * frames * self._nch))
        off = self._nch - 1            # the chosen channel is the last one opened
        step = self._nch
        for i in range(frames):
            buf[i * step + off] = mono[i]
        return buf.tobytes()

    def _sd_cb(self, outdata, frames, time_info, status_flags):
        outdata[:] = self._render(frames)

    def _cb(self, in_data, frame_count, time_info, status_flags):
        return (self._render(frame_count), pyaudio.paContinue)


click_out = ClickOutput()


# ── Show recorder ─────────────────────────────────────────────────────────────
# One-button room capture: default input device -> timestamped WAV in
# ~/.limestudio/recordings. For post-gig review, not multitracking.
class ShowRecorder:
    RATE = 44100

    def __init__(self):
        self._stream = None
        self._wav = None
        self._lock = threading.Lock()
        self.path = None
        self.started_at = None
        self.error = None
        # recording source: None = default input (room mic). With the XR18
        # as the input device and the channel pair carrying its USB return of
        # the main LR, REC captures the actual live board mix.
        self.device = None
        self.channel = None        # 1-based first channel of the stereo pair
        self._nch = 2              # channels the stream is opened with
        self._pair0 = 0            # 0-based offset of the recorded pair

    def configure(self, device=None, channel=None):
        try:
            self.device = int(device) if device is not None else None
        except (TypeError, ValueError):
            self.device = None
        try:
            self.channel = max(1, min(31, int(channel))) if channel else None
        except (TypeError, ValueError):
            self.channel = None

    def state(self):
        return {
            "active": self._stream is not None,
            "file": (self.path.name if self.path else None),
            "seconds": round(time.time() - self.started_at, 1) if (self._stream and self.started_at) else 0,
            "available": HAS_SD or HAS_PYAUDIO,
            "device": self.device,
            "channel": self.channel,
            "error": self.error,
        }

    def start(self):
        self.stop()
        if not (HAS_SD or HAS_PYAUDIO):
            self.error = "no audio backend — pip install sounddevice"
            return False
        folder = CONFIG_DIR / "recordings"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (time.strftime("show %Y-%m-%d %H.%M.%S") + ".wav")
            # open enough channels to reach the chosen pair; write only 2
            open_ch = (self.channel + 1) if self.channel else 2
            self._pair0 = (self.channel - 1) if self.channel else 0
            if HAS_SD:
                try:
                    di = (sd.query_devices(self.device) if self.device is not None
                          else sd.query_devices(kind="input"))
                    maxch = int(di.get("max_input_channels", 1))
                except Exception:
                    maxch = 2
                open_ch = max(1, min(open_ch, maxch))
            self._nch = open_ch
            if self._pair0 + 2 > open_ch:               # pair doesn't fit → top pair
                self._pair0 = max(0, open_ch - 2)
            wav_ch = min(2, open_ch)
            self._wav = wave.open(str(path), "wb")
            self._wav.setnchannels(wav_ch)
            self._wav.setsampwidth(2)
            self._wav.setframerate(self.RATE)
            if HAS_SD:
                self._stream = sd.RawInputStream(
                    samplerate=self.RATE, channels=open_ch, dtype="int16",
                    device=self.device, blocksize=2048, callback=self._sd_cb)
                self._stream.start()
            else:
                self._pa = pyaudio.PyAudio()
                self._stream = self._pa.open(
                    format=pyaudio.paInt16, channels=open_ch, rate=self.RATE,
                    input=True, input_device_index=self.device,
                    frames_per_buffer=2048, stream_callback=self._pa_cb)
                self._stream.start_stream()
            self.path = path
            self.started_at = time.time()
            self.error = None
            return True
        except Exception as e:
            self.error = str(e)
            self._close_wav()
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass
            self._stream = None
            return False

    def stop(self):
        st = self._stream
        self._stream = None
        try:
            if st:
                st.stop() if HAS_SD else st.stop_stream()
                st.close()
        except Exception:
            pass
        try:
            if getattr(self, "_pa", None):
                self._pa.terminate()
                self._pa = None
        except Exception:
            pass
        self._close_wav()
        p = self.path
        self.started_at = None
        return p

    def _close_wav(self):
        with self._lock:
            try:
                if self._wav:
                    self._wav.close()
            except Exception:
                pass
            self._wav = None

    def _write(self, data):
        # extract the chosen stereo pair from the interleaved capture
        if self._nch > 2 or self._pair0 > 0:
            src = array.array("h")
            src.frombytes(data)
            out = array.array("h")
            step = self._nch
            for i in range(0, len(src) - step + 1, step):
                out.append(src[i + self._pair0])
                out.append(src[i + self._pair0 + 1])
            data = out.tobytes()
        with self._lock:
            if self._wav:
                try:
                    self._wav.writeframes(data)
                except Exception:
                    pass

    def _sd_cb(self, indata, frames, time_info, status_flags):
        self._write(bytes(indata))

    def _pa_cb(self, in_data, frame_count, time_info, status_flags):
        self._write(in_data)
        return (None, pyaudio.paContinue)


recorder = ShowRecorder()


def _save_show():
    try:
        _store_active_mix()       # desk-side tweaks ride along with every save
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "setlist": state["setlist"],
            "patch": state["patch"],
            "looks": state["looks"],
            "profiles": state["profiles"],
            "mixer": state["mixer"],
            "lighting": {k: state["lighting"][k]
                         for k in ("scene", "color", "brightness", "num_fixtures",
                                   "fade", "effect", "master", "on", "static_map")},
            "midi_mapping": midi.mapping,
            "click_out_device": click_out.device,
            "click_out_channel": click_out.channel,
            "rec_device": recorder.device,
            "rec_channel": recorder.channel,
            "midi_clock_port": midi_clock.port_name,
        }
        tmp = SHOW_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(SHOW_FILE)
    except Exception:
        pass   # persistence must never take the show down


def _load_show():
    try:
        if not SHOW_FILE.exists():
            return
        d = json.loads(SHOW_FILE.read_text())
        # mixer presets load FIRST: song migration may resolve legacy
        # scene-id mixes into embedded params
        mx0 = d.get("mixer") or {}
        state["mixer"]["scenes"] = [s for s in (_clean_mix_scene(x) for x in (mx0.get("scenes") or [])) if s]
        state["setlist"] = [_migrate_song(s) for s in (d.get("setlist", []) or [])]
        state["patch"] = d.get("patch", []) or []
        state["looks"] = [c for c in (_clean_look(lk) for lk in (d.get("looks") or [])) if c]
        mx = d.get("mixer") or {}
        state["mixer"]["host"] = str(mx.get("host", ""))[:64]
        if mx.get("ch_names"):
            loaded = [str(n)[:16] for n in mx["ch_names"]][:16]
            # saved shows from before Back Vox existed: extend, don't clamp
            default = state["mixer"]["ch_names"]
            if loaded == default[:len(loaded)] and len(loaded) < len(default):
                loaded = list(default)
            state["mixer"]["ch_names"] = loaded
        if mx.get("bus_names"):
            state["mixer"]["bus_names"] = [str(n)[:16] for n in mx["bus_names"]][:6]
        mixer.channels = max(1, min(16, len(state["mixer"]["ch_names"])))
        # NOTE: deliberately NO auto-connect. Connecting is a hands-on act —
        # the saved host only prefills the Connect prompt. (Auto-connect plus
        # song auto-select used to push a sim-built mix onto the real desk at
        # app launch.)
        profs = d.get("profiles") or {}
        state["profiles"] = {
            str(k)[:16]: {"width": max(1, min(32, int(v.get("width", 1)))),
                          "slots": {str(s).lower(): int(off) for s, off in (v.get("slots") or {}).items()
                                    if str(s).lower() in SLOT_CODES and 0 <= int(off) < 32}}
            for k, v in profs.items()
            if isinstance(v, dict) and str(k) not in PROFILES and (v.get("slots") or {})
        }
        if state["patch"]:
            state["lighting"]["num_fixtures"] = len(state["patch"])
        lit = d.get("lighting") or {}
        state["lighting"].update({k: v for k, v in lit.items() if k in state["lighting"]})
        state["lighting"]["effect"] = _clean_effect(state["lighting"].get("effect"))
        state["lighting"]["static_map"] = _clean_static_map(state["lighting"].get("static_map"))
        if d.get("midi_mapping"):
            midi.set_mapping(d["midi_mapping"])
        if d.get("click_out_device") is not None:
            click_out.start(d["click_out_device"], d.get("click_out_channel"))
        recorder.configure(d.get("rec_device"), d.get("rec_channel"))
        if d.get("midi_clock_port"):
            midi_clock.start(d["midi_clock_port"])
    except Exception:
        pass


_load_show()

# ── WebSocket broadcast ───────────────────────────────────────────────────────
def broadcast(event: str, data: dict):
    dead = set()
    msg = json.dumps({"event": event, "data": data})
    # Iterate a snapshot: clients connect/disconnect from other threads, and
    # mutating ws_clients mid-iteration would raise RuntimeError and (fatally)
    # kill the click thread mid-show. The snapshot makes broadcast race-safe.
    for ws in list(ws_clients):
        try:
            ws.send(msg)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


@sock.route("/ws")
def websocket(ws):
    ws_clients.add(ws)
    # Send current state on connect
    ws.send(json.dumps({"event": "state", "data": _full_state()}))
    try:
        while True:
            msg = ws.receive(timeout=30)
            if msg is None:
                break
            try:
                payload = json.loads(msg)
                handle_ws_message(payload, ws)
            except Exception as e:
                ws.send(json.dumps({"event": "error", "data": str(e)}))
    except Exception:
        pass
    finally:
        ws_clients.discard(ws)


def handle_ws_message(payload: dict, ws):
    action = payload.get("action")
    data = payload.get("data", {})

    if action == "ping":
        ws.send(json.dumps({"event": "pong"}))

    elif action == "set_setlist":
        state["setlist"] = [_migrate_song(s) for s in data.get("setlist", [])]
        _save_show()
        broadcast("state", _full_state())

    elif action == "activate_song":
        _activate_song(data.get("idx"))

    elif action == "click_start":
        song = _active_song()
        if song is not None:
            # song mode: resume from where it's paused; an explicit bar (a
            # seek-and-play) jumps there and starts that bar clean
            _migrate_song(song)
            explicit = "bar" in data
            bar = max(1, min(song["length_bars"], int(data.get("bar", state["click"].get("bar", 1)))))
            seg = _song_segment(song, bar)
            beat = 0 if explicit else state["click"].get("beat", 0)
            state["click"].update({"mode": "song", "bar": bar, "beat": beat,
                                   "bpm": seg["bpm"], "time_sig": seg["time_sig"]})
        else:
            state["click"]["mode"] = "free"
            state["click"]["bpm"] = data.get("bpm", state["click"]["bpm"])
            state["click"]["time_sig"] = data.get("time_sig", state["click"]["time_sig"])
            state["click"]["beat"] = 0
        state["click"]["running"] = True
        broadcast("state", _full_state())

    elif action == "click_stop":
        # PAUSE in place — bar/beat are kept so the next play resumes from here.
        # (Re-activate the song or seek to bar 1 to rewind.)
        state["click"]["running"] = False
        state["click"]["pending_song"] = None
        _pending_cues.clear()
        broadcast("state", _full_state())

    elif action == "seek":
        song = _active_song()
        if song is not None:
            _migrate_song(song)
            bar = max(1, min(song["length_bars"], int(data.get("bar", 1))))
            seg = _song_segment(song, bar)
            state["click"].update({"mode": "song", "bar": bar, "beat": 0,
                                   "bpm": seg["bpm"], "time_sig": seg["time_sig"]})
            broadcast("state", _full_state())

    elif action == "update_click":
        state["click"]["bpm"] = data.get("bpm", state["click"]["bpm"])
        state["click"]["time_sig"] = data.get("time_sig", state["click"]["time_sig"])
        broadcast("state", _full_state())

    elif action == "trigger_cue":
        text = data.get("text", "")
        if text:
            state["cue_queue"].append(text)
            _queue_cue(text)   # quantized to the bar's "1" while playing

    elif action == "use_detected_tempo":
        bpm = state["audio"].get("bpm_detected")
        if bpm:
            state["click"]["bpm"] = max(20, min(300, int(round(bpm))))
            broadcast("state", _full_state())

    elif action == "set_autofollow":
        state["audio"]["autofollow"] = bool(data.get("on", False))
        broadcast("state", _full_state())

    elif action == "set_lighting":
        sc = data.pop("scene", None)       # scene changes go through the fader
        rebuild = "num_fixtures" in data and data["num_fixtures"] != state["lighting"]["num_fixtures"]
        state["lighting"].update({k: v for k, v in data.items()
                                  if k in state["lighting"]})
        try:                               # sanitise the default fade (seconds)
            state["lighting"]["fade"] = max(0.0, min(30.0, float(state["lighting"].get("fade", 0.5))))
        except (TypeError, ValueError):
            state["lighting"]["fade"] = 0.5
        state["lighting"]["effect"] = _clean_effect(state["lighting"].get("effect"))
        try:
            state["lighting"]["master"] = _clamp8(state["lighting"].get("master", 255))
        except (TypeError, ValueError):
            state["lighting"]["master"] = 255
        state["lighting"]["on"] = bool(state["lighting"].get("on", True))
        state["lighting"]["static_map"] = _clean_static_map(state["lighting"].get("static_map"))
        if sc:
            _set_scene(sc)
        if rebuild:
            # changing the fixture count re-lays a tidy sequential patch,
            # keeping whatever profile fixture 1 currently uses.
            prof = (state["patch"][0]["profile"] if state["patch"] else DEFAULT_PROFILE)
            state["patch"] = _default_patch(state["lighting"]["num_fixtures"], prof)
        _update_dmx_from_lighting()
        _save_show()
        broadcast("state", _full_state())

    elif action == "record_start":
        recorder.start()                  # failure shows up in state.recorder.error
        broadcast("state", _full_state())

    elif action == "record_stop":
        recorder.stop()
        broadcast("state", _full_state())

    elif action == "set_midi_clock":
        port = data.get("port") or None
        if port is None:
            midi_clock.stop()
        else:
            midi_clock.start(port)
        _save_show()
        broadcast("state", _full_state())

    elif action == "click_test":
        # three audible ticks on the routed output — verify routing without
        # running the transport
        def _ticks():
            for i in range(3):
                click_out.tick(2 if i == 0 else 0)
                time.sleep(0.35)
        if click_out._stream:
            threading.Thread(target=_ticks, daemon=True).start()
        broadcast("state", _full_state())

    elif action == "set_rec_input":
        # where REC records from: device + 1-based first channel of the pair.
        # XR18 + the pair carrying its USB main-LR return = board-mix recording.
        recorder.configure(data.get("device"), data.get("channel"))
        _save_show()
        broadcast("state", _full_state())

    elif action == "set_click_output":
        dev = data.get("device", None)
        if dev is None:
            click_out.stop()
        else:
            click_out.start(dev, data.get("channel"))
        _save_show()
        broadcast("state", _full_state())

    elif action == "set_scene":
        # optional "fade" (seconds) overrides the default; 0 = snap
        _set_scene(data.get("scene", "reactive"), data.get("fade"))
        broadcast("state", _full_state())

    elif action == "mixer_connect":
        host = str(data.get("host", "")).strip()[:64]
        state["mixer"]["host"] = host
        if host:
            mixer.connect(host)
        else:
            mixer.disconnect()
        _save_show()
        broadcast("state", _full_state())

    elif action == "mixer_disconnect":
        # drop the link; the saved host stays for the next Connect prompt
        mixer.disconnect()
        broadcast("state", _full_state())

    elif action == "mixer_set":
        # live console move — straight to the desk (or the sim cache).
        # control set = scene params + preamp gains (gain is live-only).
        a = str(data.get("address", ""))
        if a in mixer_osc.control_addresses(mixer.channels):
            mixer.set(a, data.get("value", 0))
            # every console move writes through to the active song's mix
            # (gain isn't in the managed set, so it never lands in a song)
            if a in mixer_osc.managed_addresses(mixer.channels):
                s = _active_song()
                if s is not None and isinstance(s.get("mix"), dict):
                    s["mix"][a] = mixer.get(a)
        # no full-state broadcast: dragging a fader must not rebuild the UI

    elif action == "mixer_query":
        # the Mixer tab asks for current values when it opens
        snap = {a: mixer.get(a) for a in mixer_osc.control_addresses(mixer.channels)}
        ws.send(json.dumps({"event": "mixer_levels", "data": {"cache": snap}}))

    elif action == "mixer_capture":
        name = (str(data.get("name", "")).strip()[:32]
                or "Mix %d" % (len(state["mixer"]["scenes"]) + 1))
        params = mixer.capture()
        state["mixer"]["scenes"].append(
            {"id": uuid.uuid4().hex[:8], "name": name, "params": params})
        _save_show()
        broadcast("state", _full_state())

    elif action == "mixer_apply":
        # load a preset: the desk glides there and it becomes the active
        # song's mix (auto-save semantics)
        sc = _mix_scene_by_id(str(data.get("id", "")))
        if sc:
            mixer.apply(sc.get("params") or {})
            s = _active_song()
            if s is not None:
                s["mix"] = dict(sc.get("params") or {})
            _save_show()
        broadcast("state", _full_state())

    elif action == "mixer_name":
        # rename an IN (kind "ch") or OUT bus (kind "bus") — user-owned, ≤10 chars
        i = int(data.get("idx", -1))
        nm = str(data.get("name", "")).strip()[:10]
        key = "bus_names" if data.get("kind") == "bus" else "ch_names"
        if 0 <= i < len(state["mixer"][key]) and nm:
            state["mixer"][key][i] = nm
            _save_show()
        broadcast("state", _full_state())

    elif action == "mixer_rename":
        sc = _mix_scene_by_id(str(data.get("id", "")))
        nm = str(data.get("name", "")).strip()[:32]
        if sc and nm:
            sc["name"] = nm
            _save_show()
        broadcast("state", _full_state())

    elif action == "mixer_delete":
        sid = str(data.get("id", ""))
        state["mixer"]["scenes"] = [s for s in state["mixer"]["scenes"]
                                    if s.get("id") != sid]
        _save_show()
        broadcast("state", _full_state())

    elif action == "set_fixture_color":
        # paint one light. color [r,g,b] sets it; null clears back to global.
        i = int(data.get("idx", -1))
        if 0 <= i < 64:
            sm = _clean_static_map(state["lighting"].get("static_map"))
            while len(sm) <= i:
                sm.append(None)
            c = data.get("color")
            sm[i] = [_clamp8(c[0]), _clamp8(c[1]), _clamp8(c[2])] if c else None
            state["lighting"]["static_map"] = sm
            # paints live on the static layer — switch there so it shows
            if state["lighting"]["scene"] != "static":
                _set_scene("static")
            _update_dmx_from_lighting()
            _save_show()
        broadcast("state", _full_state())

    elif action == "set_position":
        # fires continuously while a slider drags: render only — no save, no
        # full-state broadcast (that rebuilt the slider mid-drag and killed
        # the gesture). The release commits via set_patch, which persists.
        i = int(data.get("idx", -1))
        if 0 <= i < len(state["patch"]):
            fx = state["patch"][i]
            try:
                fx["pan"] = max(0.0, min(255.0, float(data.get("pan", fx.get("pan", 128)))))
                fx["tilt"] = max(0.0, min(255.0, float(data.get("tilt", fx.get("tilt", 128)))))
            except (TypeError, ValueError):
                pass
            _update_dmx_from_lighting()

    elif action == "save_profile":
        name = str(data.get("name", "")).strip()[:16].upper()
        codes = data.get("slots")
        if isinstance(codes, str):
            codes = [c.strip() for c in codes.split(",") if c.strip()]
        ok = (name and name not in PROFILES and isinstance(codes, list)
              and 1 <= len(codes) <= 32
              and all(str(c).lower() in SLOT_CODES for c in codes))
        if ok:
            slots = {}
            for off, c in enumerate(codes):
                c = str(c).lower()
                if c != "-" and c not in slots:    # first occurrence wins
                    slots[c] = off
            if slots:
                state["profiles"][name] = {"width": len(codes), "slots": slots}
                _save_show()
        broadcast("state", _full_state())

    elif action == "delete_profile":
        name = str(data.get("name", ""))
        in_use = any(fx.get("profile") == name for fx in state["patch"])
        if name in state["profiles"] and not in_use:
            del state["profiles"][name]
            _save_show()
        broadcast("state", _full_state())

    elif action == "set_effect":
        state["lighting"]["effect"] = _clean_effect(data)
        _update_dmx_from_lighting()
        _save_show()
        broadcast("state", _full_state())

    elif action == "save_look":
        # Capture the live rendered output — whatever is on stage right now.
        if not _last_fixtures:
            _update_dmx_from_lighting()
        # un-scale the grand master so a dimmed capture isn't baked into the look
        gm = max(1, _clamp8(state["lighting"].get("master", 255)))
        fixtures = [{"r": f["r"], "g": f["g"], "b": f["b"],
                     "m": min(255, f["m"] * 255 // gm),
                     "p": f.get("p", 128.0), "t": f.get("t", 128.0)}
                    for f in _last_fixtures]
        if fixtures:
            name = (str(data.get("name", "")).strip()[:32]
                    or "Look %d" % (len(state["looks"]) + 1))
            state["looks"].append({"id": uuid.uuid4().hex[:8], "name": name,
                                   "fixtures": fixtures,
                                   "effect": dict(state["lighting"]["effect"])})
            _save_show()
        broadcast("state", _full_state())

    elif action == "rename_look":
        lk = _look_by_id(str(data.get("id", "")))
        nm = str(data.get("name", "")).strip()[:32]
        if lk and nm:
            lk["name"] = nm
            _save_show()
        broadcast("state", _full_state())

    elif action == "delete_look":
        lid = str(data.get("id", ""))
        state["looks"] = [l for l in state["looks"] if l.get("id") != lid]
        if state["lighting"]["scene"] == "look:" + lid:
            _set_scene("static", 0)        # deleted the active look → stay lit
        _save_show()
        broadcast("state", _full_state())

    elif action == "set_patch":
        patch = data.get("patch", [])
        # sanitise: clamp base into 1..512, validate profile, keep positions
        clean = []
        for fx in patch:
            base = max(1, min(512, int(fx.get("base", 1))))
            prof = fx.get("profile", DEFAULT_PROFILE)
            if prof not in _profiles_all():
                prof = DEFAULT_PROFILE
            try:
                pan = max(0.0, min(255.0, float(fx.get("pan", 128))))
                tilt = max(0.0, min(255.0, float(fx.get("tilt", 128))))
            except (TypeError, ValueError):
                pan, tilt = 128.0, 128.0
            entry = {"base": base, "profile": prof, "pan": pan, "tilt": tilt}
            for flag in ("inv_p", "inv_t", "swap"):    # mounting corrections
                if fx.get(flag):
                    entry[flag] = True
            clean.append(entry)
        state["patch"] = clean
        state["lighting"]["num_fixtures"] = len(clean)
        _update_dmx_from_lighting()
        _save_show()
        broadcast("state", _full_state())

    elif action == "auto_patch":
        n = max(1, min(64, int(data.get("count", state["lighting"]["num_fixtures"]))))
        prof = data.get("profile", DEFAULT_PROFILE)
        if prof not in _profiles_all():
            prof = DEFAULT_PROFILE
        state["patch"] = _default_patch(n, prof)
        state["lighting"]["num_fixtures"] = n
        _update_dmx_from_lighting()
        _save_show()
        broadcast("state", _full_state())

    elif action == "list_ports":
        ws.send(json.dumps({"event": "ports", "data": {"ports": output.list_ports()}}))

    elif action == "connect_output":
        output.connect(
            data.get("mode", "sim"),
            port=data.get("port", ""),
            host=data.get("host", ""),
            universe=data.get("universe", 0),
            fps=data.get("fps"),
        )
        _update_dmx_from_lighting()
        broadcast("state", _full_state())
        broadcast("output", output.state())

    elif action == "disconnect_output":
        output.disconnect()
        broadcast("state", _full_state())
        broadcast("output", output.state())

    elif action == "midi_list_ports":
        ws.send(json.dumps({"event": "midi_ports",
                            "data": {"ports": midi.list_ports(), "has_midi": midi_input.HAS_MIDI}}))

    elif action == "midi_connect":
        midi.connect(data.get("port", ""))
        broadcast("midi", midi.state())
        broadcast("state", _full_state())

    elif action == "midi_disconnect":
        midi.disconnect()
        broadcast("midi", midi.state())
        broadcast("state", _full_state())

    elif action == "midi_set_mapping":
        midi.set_mapping(data.get("mapping", []))
        _save_show()
        broadcast("midi", midi.state())
        broadcast("state", _full_state())

    elif action == "midi_learn":
        midi.set_learn(data.get("index"))   # None cancels
        broadcast("midi", midi.state())

    elif action == "midi_sim":
        # Inject a message with no hardware — drives the UI "Test" button + tests.
        ev = {"type": data.get("type", "note"),
              "number": int(data.get("number", 0)),
              "value": int(data.get("value", 127)),
              "channel": int(data.get("channel", 0))}
        ev["edge"] = (ev["value"] > 0) if ev["type"] == "note" else (ev["value"] >= 64)
        midi.inject(ev)


def _full_state():
    return {
        "setlist": state["setlist"],
        "active_song_idx": state["active_song_idx"],
        "click": state["click"],
        "audio": state["audio"],
        "lighting": state["lighting"],
        "looks": state["looks"],
        "mixer": dict(mixer.state(),
                      saved_host=state["mixer"]["host"],   # prefills Connect
                      scenes=[{"id": s["id"], "name": s["name"]}
                              for s in state["mixer"]["scenes"]],
                      # in-app names are user-owned (editable, ≤8 chars);
                      # the desk's scribble strips no longer override them
                      ch_names=list(state["mixer"]["ch_names"]),
                      bus_names=list(state["mixer"]["bus_names"])),
        "patch": _active_patch(),
        "dmx_preview": state["dmx"][:32],  # first 32 channels for UI
        "output": output.state(),
        "profiles": {k: {"width": v["width"], "pt": _profile_has_pt(v)}
                     for k, v in _profiles_all().items()},
        "midi": midi.state(),
        "click_out": click_out.state(),
        "midi_clock": midi_clock.state(),
        "recorder": recorder.state(),
    }


# Live three-way sync: the desk broadcasts every change to all subscribed
# remotes (Mixing Station, X Air Edit, us). Desk-side moves land in the link's
# cache via on_update; we coalesce them and push to our own UI a few times a
# second (a fader sweep fires hundreds of OSC msgs — no per-message broadcast).
_mixer_dirty = threading.Event()


def _mixer_param_changed(address, args):
    if address in mixer_osc.managed_addresses(mixer.channels):
        s = _active_song()
        if s is not None and isinstance(s.get("mix"), dict) and not mixer.gliding:
            s["mix"][address] = mixer.get(address)   # desk edits ride into the song too
    _mixer_dirty.set()


def _mixer_push_loop():
    while True:
        _mixer_dirty.wait()
        time.sleep(0.12)                  # coalesce a burst of desk messages
        _mixer_dirty.clear()
        if mixer.connected:
            snap = {a: mixer.get(a) for a in mixer_osc.control_addresses(mixer.channels)}
            broadcast("mixer_levels", {"cache": snap})


mixer.on_update = _mixer_param_changed
threading.Thread(target=_mixer_push_loop, daemon=True).start()


def _mixer_status_changed():
    if mixer.connected:
        def adopt():
            time.sleep(1.2)            # let the query replies fill the cache
            _store_active_mix()
        threading.Thread(target=adopt, daemon=True).start()
    broadcast("state", _full_state())


mixer.on_status = _mixer_status_changed


# ── Click track engine ────────────────────────────────────────────────────────
# Secondary accents give odd/compound meters their feel:
# 5/4 = 3+2 · 6/8 = two dotted pulses · 7/8 = 2+2+3
SIG_ACCENTS = {5: (3,), 6: (3,), 7: (2, 4)}


def _beat_accent(beat, sig):
    p = beat % (sig or 4)
    if p == 0:
        return 2
    return 1 if p in SIG_ACCENTS.get(sig, ()) else 0


def _beat_sleep(next_t, interval):
    """Drift-free beat pacing: sleep to an absolute deadline instead of a
    relative interval, so per-beat scheduling error doesn't accumulate into
    the tempo. Resets the deadline if we fall badly behind (system stall)."""
    now = time.monotonic()
    if next_t is None:
        next_t = now
    next_t += interval
    delay = next_t - now
    if delay > 0:
        time.sleep(delay)
    elif delay < -0.25:
        next_t = time.monotonic()
    return next_t


def click_thread():
    """Runs in background. Fires beat events via WebSocket.

    Two modes: "free" is a plain metronome; "song" walks the active song's bar
    timeline — tempo/time-signature change live wherever the tempo map says,
    cues auto-fire when their bar arrives, and playback stops at the last bar.
    """
    global _chase_pos
    next_t = None
    while True:
        if not state["click"]["running"]:
            next_t = None
            time.sleep(0.05)
            continue

        song = _active_song() if state["click"]["mode"] == "song" else None

        if song is not None:
            _migrate_song(song)
            bar = state["click"]["bar"]
            beat = state["click"]["beat"]

            if bar > song["length_bars"]:               # end of song
                if _switch_pending():                   # queued song flows straight in
                    continue
                state["click"].update({"running": False, "bar": 1, "beat": 0})
                broadcast("state", _full_state())
                continue

            seg = _song_segment(song, bar)              # live tempo/sig from the map
            bpm = max(20, min(300, seg["bpm"]))
            time_sig = seg["time_sig"]
            state["click"]["bpm"] = bpm
            state["click"]["time_sig"] = time_sig

            if beat == 0:                               # bar start ("the 1")
                _flush_pending_cues()                   # quantized live cues land here
                bar_cues = [c for c in song.get("cues", [])
                            if int(c.get("bar", 0)) == bar]
                for c in bar_cues:
                    text = c.get("text") or c.get("label", "")
                    if text:
                        broadcast("cue", {"text": text})
                # auto-announce the NEXT section one bar early: "Verse, 2, 3, 4"
                # (skipped if the band placed their own cue on this bar)
                if not bar_cues:
                    nxt = next((s for s in song.get("sections", [])
                                if int(s.get("bar", 0)) == bar + 1 and s.get("label")), None)
                    if nxt:
                        counts = ", ".join(str(i) for i in range(2, time_sig + 1))
                        broadcast("cue", {"text": nxt["label"] + (", " + counts if counts else "")})
                # lighting lane: the latest scene change at/before this bar wins
                # (covers normal playback, seeks and mid-song joins alike)
                lm = song.get("light_map") or []
                if lm:
                    cur = None
                    for L in lm:
                        if L["bar"] <= bar:
                            cur = L
                        else:
                            break
                    if cur and cur["scene"] != state["lighting"]["scene"]:
                        # fade is authored in beats — convert at the live tempo
                        fade_beats = float(cur.get("fade", 0) or 0)
                        _set_scene(cur["scene"], fade_beats * 60.0 / bpm)
                        broadcast("state", _full_state())

            broadcast("beat", {
                "beat": beat, "bar": bar,
                "bpm": bpm, "time_sig": time_sig,
                "downbeat": beat == 0,
                "accent": _beat_accent(beat, time_sig),
                "section": _song_section(song, bar),
                "length_bars": song["length_bars"],
            })
            click_out.tick(_beat_accent(beat, time_sig))
            _tick_beat_clock(bpm)

            if state["lighting"]["scene"] == "chase":
                _chase_pos += 1
                _update_dmx_from_lighting()

            beat += 1
            if beat >= time_sig:
                beat = 0
                bar += 1
            state["click"]["beat"] = beat
            state["click"]["bar"] = bar
            # a queued song switch lands exactly on the bar boundary
            if beat == 0 and state["click"]["pending_song"] is not None:
                next_t = _beat_sleep(next_t, 60.0 / bpm)
                _switch_pending()
                continue
            next_t = _beat_sleep(next_t, 60.0 / bpm)

        else:                                            # free metronome
            bpm = max(20, min(300, state["click"]["bpm"]))
            time_sig = state["click"]["time_sig"]
            beat = state["click"]["beat"]
            if beat % time_sig == 0:
                _flush_pending_cues()
            broadcast("beat", {
                "beat": beat, "bpm": bpm, "time_sig": time_sig,
                "downbeat": (beat % time_sig == 0),
                "accent": _beat_accent(beat, time_sig),
            })
            click_out.tick(_beat_accent(beat, time_sig))
            _tick_beat_clock(bpm)
            if state["lighting"]["scene"] == "chase":
                _chase_pos += 1
                _update_dmx_from_lighting()
            state["click"]["beat"] = (beat + 1) % (time_sig * 16)
            next_t = _beat_sleep(next_t, 60.0 / bpm)


# ── Audio analysis (simulated when PyAudio unavailable) ──────────────────────
def audio_sim_thread():
    """Simulates audio energy for testing without a mic."""
    t = 0.0
    frame = 0
    was_running = False
    while True:
        t += 0.05
        # A simulated kick on the beat grid so tempo detection has something
        # musical to lock onto when there's no real mic.
        bpm = state["click"]["bpm"] if state["click"]["running"] else 120
        beat_phase = (t % (60.0 / bpm)) / (60.0 / bpm)
        kick = max(0.0, 1.0 - beat_phase * 6.0)   # sharp decay after each beat
        bass = min(1.0, 0.25 + 0.55 * abs(math.sin(t * 1.8)) + 0.5 * kick)
        mid = 0.3 + 0.5 * abs(math.sin(t * 2.3 + 1))
        high = 0.2 + 0.4 * abs(math.sin(t * 4.1 + 2))
        state["audio"]["energy"] = {
            "bass": round(bass, 3),
            "mid": round(mid, 3),
            "high": round(high, 3),
        }
        _update_dmx_from_lighting()
        broadcast("audio", state["audio"]["energy"])

        # Tempo detection — only when audio input is on and the mic isn't driving.
        if state["audio"]["running"] and not _live_active:
            if not was_running:
                tempo.configure(20.0); was_running = True
            _detect_tempo(20.0, frame)
            frame += 1
        else:
            was_running = False

        time.sleep(0.05)


def audio_live_thread():
    """Real audio capture + FFT analysis."""
    global _live_active
    pa = pyaudio.PyAudio()
    CHUNK = 1024
    RATE = 44100
    stream = pa.open(format=pyaudio.paFloat32, channels=1,
                     rate=RATE, input=True, frames_per_buffer=CHUNK)
    # ~43 frames/sec at 1024-sample chunks @ 44.1 kHz
    live_fps = RATE / CHUNK
    tempo.configure(live_fps)
    _live_active = True
    frame = 0

    def fft_energy(data, lo_hz, hi_hz):
        n = len(data)
        freqs = np.fft.rfftfreq(n, d=1.0/RATE)
        mag = np.abs(np.fft.rfft(data))
        mask = (freqs >= lo_hz) & (freqs < hi_hz)
        return float(np.mean(mag[mask])) if mask.any() else 0.0

    while state["audio"]["running"]:
        try:
            raw = stream.read(CHUNK, exception_on_overflow=False)
            data = np.frombuffer(raw, dtype=np.float32)
            win = data * np.hanning(len(data))
            total = np.max(np.abs(win)) + 1e-9
            bass = min(1.0, fft_energy(win, 20, 200) / (total * 80))
            mid = min(1.0, fft_energy(win, 200, 4000) / (total * 800))
            high = min(1.0, fft_energy(win, 4000, 16000) / (total * 400))
            state["audio"]["energy"] = {
                "bass": round(bass, 3),
                "mid": round(mid, 3),
                "high": round(high, 3),
            }
            _update_dmx_from_lighting()
            broadcast("audio", state["audio"]["energy"])
            _detect_tempo(live_fps, frame)
            frame += 1
        except Exception:
            break

    _live_active = False
    stream.stop_stream()
    stream.close()
    pa.terminate()
    state["audio"]["running"] = False


# ── Scene engine + DMX render ─────────────────────────────────────────────────
SCENES = ("reactive", "chase", "static", "off")
_chase_pos = 0


# ── Effects — tempo-synced modulators on top of the scene/look output ────────
EFFECTS = ("none", "pulse", "wave", "strobe", "rainbow", "music", "flash",
           "orbit", "sweep")   # orbit/sweep are MOVEMENT effects (pan/tilt)

# "music" envelope: fast attack / slow release over the bass band, so any look
# becomes audio-reactive in its own palette instead of the raw RGB spectrum map.
_music_env = 0.0


def _music_envelope():
    global _music_env
    bass = float(state["audio"]["energy"].get("bass", 0) or 0)
    if bass >= _music_env:
        _music_env = bass                      # instant attack
    else:
        _music_env = _music_env * 0.85 + bass * 0.15   # ~release over a few ticks
    return max(0.0, min(1.0, _music_env))

# Beat clock: ticked by the click thread on every beat; the effect phase
# extrapolates between ticks (and free-runs at the last tempo when stopped,
# so the stage keeps moving between songs).
_beat_clock = {"t": 0.0, "beats": 0.0, "bpm": 120.0}


def _tick_beat_clock(bpm):
    _beat_clock["t"] = time.monotonic()
    _beat_clock["beats"] += 1.0
    _beat_clock["bpm"] = float(bpm)


def _effect_phase():
    """Continuous beat position. Integer values land exactly on click beats."""
    now = time.monotonic()
    if _beat_clock["t"] == 0.0:
        return now * _beat_clock["bpm"] / 60.0      # never ticked yet: free-run
    return _beat_clock["beats"] + (now - _beat_clock["t"]) * _beat_clock["bpm"] / 60.0


def _clean_effect(e):
    try:
        et = str((e or {}).get("type", "none")).lower()
        if et not in EFFECTS:
            et = "none"
        return {"type": et,
                "rate": max(0.25, min(16.0, float((e or {}).get("rate", 1) or 1))),
                "depth": max(0.0, min(1.0, float((e or {}).get("depth", 0.6))))}
    except Exception:
        return {"type": "none", "rate": 1.0, "depth": 0.6}


def _hsv_to_rgb(h, s, v):
    """h/s/v in 0..1 → r/g/b in 0..255."""
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))[i]
    return int(r * 255), int(g * 255), int(b * 255)


def _apply_effect(i, n, r, g, b, m, eff, phase):
    """Modulate one fixture's post-fade output. phase is in beats."""
    et = eff.get("type", "none")
    if et == "none" or m == 0:               # no effect on blackout
        return r, g, b, m
    rate = max(0.25, min(16.0, float(eff.get("rate", 1) or 1)))
    depth = max(0.0, min(1.0, float(eff.get("depth", 0.6))))
    cyc = phase / rate                       # one cycle per `rate` beats
    if et == "pulse":                        # dimmer breathes; peak ON the beat
        k = 1.0 - depth * (0.5 - 0.5 * math.cos(2 * math.pi * cyc))
        return r, g, b, int(m * k)
    if et == "wave":                         # the pulse travels across the rig
        k = 1.0 - depth * (0.5 - 0.5 * math.cos(2 * math.pi * (cyc - i / max(1, n))))
        return r, g, b, int(m * k)
    if et == "strobe":                       # short flash at each cycle start
        if (cyc % 1.0) < 0.12:
            return r, g, b, m
        return r, g, b, int(m * (1.0 - depth))
    if et == "rainbow":                      # hue rotation, spread over fixtures
        hr, hg, hb = _hsv_to_rgb((cyc + i / max(1, n)) % 1.0, 1.0, 1.0)
        return (int(r + (hr - r) * depth), int(g + (hg - g) * depth),
                int(b + (hb - b) * depth), m)
    if et == "music":                        # audio energy drives the dimmer
        k = 1.0 - depth * (1.0 - _music_envelope())
        return r, g, b, int(m * k)
    if et == "flash":                        # punch on the beat, natural decay
        k = (1.0 - depth) + depth * math.exp(-4.0 * (cyc % 1.0))
        return r, g, b, int(m * k)
    return r, g, b, m


def _apply_move(i, n, eff, phase, pan, tilt):
    """Movement effects: auto pan/tilt around the home position, tempo-synced
    and phase-spread across the rig. Only meaningful on mover profiles."""
    et = eff.get("type", "none")
    if et not in ("orbit", "sweep"):
        return pan, tilt
    rate = max(0.25, min(16.0, float(eff.get("rate", 1) or 1)))
    depth = max(0.0, min(1.0, float(eff.get("depth", 0.6))))
    cyc = 2.0 * math.pi * (phase / rate)
    off = i / max(1, n) * 2.0 * math.pi
    cl = lambda v: max(0.0, min(255.0, v))
    if et == "orbit":                        # circles around home
        return (cl(pan + math.sin(cyc + off) * 110 * depth),
                cl(tilt + math.cos(cyc + off) * 70 * depth))
    if et == "sweep":                        # side-to-side pan wave
        return cl(pan + math.sin(cyc + off) * 120 * depth), tilt
    return pan, tilt


# ── Looks — user-built named per-fixture states ──────────────────────────────
def _look_by_id(lid):
    for lk in state["looks"]:
        if lk.get("id") == lid:
            return lk
    return None


def _scene_ok(sc):
    """A scene value is a builtin name or a look reference. Look existence is
    checked at render time (lane entries may reference looks that arrive
    later, e.g. on import) — a missing look renders as static, not blackout."""
    return sc in SCENES or (isinstance(sc, str) and sc.startswith("look:"))


def _clean_look(lk):
    """Sanitise one look from disk/import; None if unusable."""
    try:
        lid = str(lk.get("id", ""))[:16]
        fixtures = []
        for f in (lk.get("fixtures") or [])[:64]:
            fd = {"r": _clamp8(f.get("r", 0)), "g": _clamp8(f.get("g", 0)),
                  "b": _clamp8(f.get("b", 0)), "m": _clamp8(f.get("m", 255))}
            for src, dst in (("p", "p"), ("t", "t")):
                if f.get(src) is not None:
                    fd[dst] = max(0.0, min(255.0, float(f[src])))
            fixtures.append(fd)
        if not lid or not fixtures:
            return None
        out = {"id": lid, "name": (str(lk.get("name", "")).strip()[:32] or "Look"),
               "fixtures": fixtures}
        if lk.get("effect"):
            out["effect"] = _clean_effect(lk["effect"])
        return out
    except Exception:
        return None

# ── Crossfades ────────────────────────────────────────────────────────────────
# A scene change with fade > 0 captures the last *rendered* per-fixture output
# and blends it into the live-rendered target on every render tick (the 20 Hz
# audio loop is the heartbeat; output refresh is independent at up to 40 fps).
# Snapshotting rendered values means chained fades depart from wherever the
# previous fade actually was — never a visual jump.
_fade = {"active": False, "from": [], "start": 0.0, "dur": 0.0}
_last_fixtures = []


def _set_scene(scene, fade=None):
    """Switch the lighting scene with a crossfade in seconds.

    fade=None uses the default from lighting state; fade=0 snaps (legacy
    behaviour). Callers still broadcast state themselves.
    """
    if not _scene_ok(scene) or scene == state["lighting"]["scene"]:
        return
    if fade is None:
        fade = state["lighting"].get("fade", 0.0)
    try:
        fade = max(0.0, min(60.0, float(fade)))
    except (TypeError, ValueError):
        fade = 0.0
    if fade > 0 and _last_fixtures:
        _fade.update({
            "active": True,
            "from": [(f["r"], f["g"], f["b"], f["m"],
                      f.get("p", 128.0), f.get("t", 128.0)) for f in _last_fixtures],
            "start": time.monotonic(),
            "dur": fade,
        })
    else:
        _fade["active"] = False
    state["lighting"]["scene"] = scene
    # A look carries its effect AND head positions: applying "Chorus blast"
    # restores static-red + wave + where the heads point, as one thing.
    # Positions are copied into the patch (the live truth) so the crossfade
    # sweeps to them and the Position sliders stay in command afterwards.
    if scene.startswith("look:"):
        lk = _look_by_id(scene[5:])
        if lk and lk.get("effect"):
            state["lighting"]["effect"] = _clean_effect(lk["effect"])
        if lk and lk.get("fixtures"):
            lf = lk["fixtures"]
            for i, fx in enumerate(state["patch"]):
                f = lf[i % len(lf)]
                if f.get("p") is not None:
                    fx["pan"] = float(f["p"])
                if f.get("t") is not None:
                    fx["tilt"] = float(f["t"])
    _update_dmx_from_lighting()


def _clamp8(v):
    v = int(v)
    return 0 if v < 0 else 255 if v > 255 else v


def _fixture_color(i, n, scene, energy, color, brightness):
    """Return (r, g, b, master) for fixture i — colour 0-255 + master dimmer 0-255."""
    if scene == "off":
        return 0, 0, 0, 0
    if isinstance(scene, str) and scene.startswith("look:"):
        lk = _look_by_id(scene[5:])
        if lk and lk.get("fixtures"):
            f = lk["fixtures"][i % len(lk["fixtures"])]   # tile across larger rigs
            return (_clamp8(f.get("r", 0)), _clamp8(f.get("g", 0)),
                    _clamp8(f.get("b", 0)), _clamp8(f.get("m", 255)))
        scene = "static"   # missing look → lights stay on, not blackout
    if scene == "static":
        c = _paint_color(i) or color
        return _clamp8(c[0]), _clamp8(c[1]), _clamp8(c[2]), _clamp8(brightness)
    return _fixture_color_dynamic(i, n, scene, energy, color, brightness)


def _paint_color(i):
    """Per-fixture painted colour, or None for the global colour."""
    sm = state["lighting"].get("static_map") or []
    if i < len(sm) and sm[i]:
        return sm[i]
    return None


def _clean_static_map(sm):
    out = []
    for v in (sm or [])[:64]:
        try:
            out.append([_clamp8(v[0]), _clamp8(v[1]), _clamp8(v[2])] if v else None)
        except (TypeError, ValueError, IndexError):
            out.append(None)
    return out


def _fixture_pt(i, fx, scene):
    """Pan/tilt for fixture i. The patch entry is the single live truth —
    applying a look COPIES its stored positions into the patch (see
    _set_scene), so the Position sliders always move the heads, and a look
    restores its positions on apply rather than silently overriding."""
    try:
        return float(fx.get("pan", 128)), float(fx.get("tilt", 128))
    except (TypeError, ValueError):
        return 128.0, 128.0


def _mount_pt(fx, pan, tilt):
    """Physical mounting correction, applied only at DMX write time — looks,
    fades and the UI all stay in logical space, so one upside-down or sideways
    fixture never corrupts captured positions."""
    if fx.get("swap"):
        pan, tilt = tilt, pan
    if fx.get("inv_p"):
        pan = 255.0 - pan
    if fx.get("inv_t"):
        tilt = 255.0 - tilt
    return pan, tilt


def _fixture_color_dynamic(i, n, scene, energy, color, brightness):
    if scene == "reactive":
        bass = energy.get("bass", 0); mid = energy.get("mid", 0); high = energy.get("high", 0)
        # bass→red, mid→green, high→blue; the colour itself carries the pulse.
        return (_clamp8(bass * 255 * 1.2), _clamp8(mid * 180), _clamp8(high * 255),
                _clamp8(brightness))
    if scene == "chase":
        active = (i == (_chase_pos % max(1, n)))
        if active:
            c = _paint_color(i) or color   # painted lights chase in their own colour
            return _clamp8(c[0]), _clamp8(c[1]), _clamp8(c[2]), _clamp8(brightness)
        return 0, 0, 0, 0
    return 0, 0, 0, 0


def _write_fixture(dmx, base0, profile, r, g, b, master, pan=128.0, tilt=128.0):
    """Write one fixture into the 512-channel universe per its profile.

    Fixtures WITH a dimmer slot get raw colour + master on the dimmer.
    Fixtures WITHOUT one get colour pre-scaled by master (master baked in).
    Pan/tilt arrive as floats (mid-fade positions are fractional) and are
    rendered 16-bit: coarse on p/t, remainder on pf/tf where the profile has
    fine channels — that's what makes slow look-to-look sweeps glide.
    """
    prof = _profiles_all().get(profile, PROFILES[DEFAULT_PROFILE])
    slots = prof["slots"]
    if "d" in slots:
        er, eg, eb = r, g, b
    else:
        er, eg, eb = r * master // 255, g * master // 255, b * master // 255
    p16 = int(round(max(0.0, min(255.0, float(pan))) * 257))
    t16 = int(round(max(0.0, min(255.0, float(tilt))) * 257))
    vals = {"r": er, "g": eg, "b": eb, "w": min(er, eg, eb), "d": master,
            "p": p16 >> 8, "pf": p16 & 0xFF, "t": t16 >> 8, "tf": t16 & 0xFF}
    for slot, off in slots.items():
        idx = base0 + off
        if 0 <= idx < 512:
            dmx[idx] = _clamp8(vals.get(slot, 0))


def _update_dmx_from_lighting():
    global _last_fixtures
    L = state["lighting"]
    scene = L["scene"]; energy = state["audio"]["energy"]
    color = L["color"]; brightness = L["brightness"]
    patch = _active_patch()
    n = len(patch)

    # Crossfade progress: smoothstep eases both ends; cleared once complete.
    mix = None
    if _fade["active"]:
        t = (time.monotonic() - _fade["start"]) / max(0.001, _fade["dur"])
        if t >= 1.0:
            _fade["active"] = False
        else:
            mix = t * t * (3.0 - 2.0 * t)

    eff = L.get("effect") or {}
    phase = _effect_phase() if eff.get("type", "none") != "none" else 0.0
    gm = _clamp8(L.get("master", 255))
    if not L.get("on", True):
        gm = 0      # master switch off → dark, config keeps rendering underneath

    dmx = [0] * 512
    fixtures = []
    for i, fx in enumerate(patch):
        r, g, b, master = _fixture_color(i, n, scene, energy, color, brightness)
        pan, tilt = _fixture_pt(i, fx, scene)
        if mix is not None:
            fr = _fade["from"][i] if i < len(_fade["from"]) else (0, 0, 0, 0, 128.0, 128.0)
            r = round(fr[0] + (r - fr[0]) * mix)
            g = round(fr[1] + (g - fr[1]) * mix)
            b = round(fr[2] + (b - fr[2]) * mix)
            master = round(fr[3] + (master - fr[3]) * mix)
            if len(fr) >= 6:                  # heads sweep through the crossfade
                pan = fr[4] + (pan - fr[4]) * mix
                tilt = fr[5] + (tilt - fr[5]) * mix
        # effects ride on top of the (possibly mid-fade) output
        r, g, b, master = _apply_effect(i, n, r, g, b, master, eff, phase)
        pan, tilt = _apply_move(i, n, eff, phase, pan, tilt)
        master = master * gm // 255            # grand master scales EVERYTHING
        mp, mt = _mount_pt(fx, pan, tilt)    # physical correction at output only
        # preview carries both: p/t logical (capture reads these), mp/mt as
        # the fixture physically points — so mount flags are visible in sim
        fixtures.append({"r": r, "g": g, "b": b, "m": master,
                         "p": round(pan, 1), "t": round(tilt, 1),
                         "mp": round(mp, 1), "mt": round(mt, 1)})
        base0 = int(fx.get("base", 1)) - 1   # 1-indexed address → 0-indexed slot
        _write_fixture(dmx, base0, fx.get("profile", DEFAULT_PROFILE),
                       r, g, b, master, mp, mt)

    _last_fixtures = fixtures
    state["dmx"] = dmx   # atomic swap; the output refresh loop reads this
    # Preview: enough raw channels for the UI plus a tidy per-fixture summary.
    broadcast("dmx", {"channels": dmx[:max(32, n * 5)], "fixtures": fixtures})


# ── REST API ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/api/state")
def api_state():
    return jsonify(_full_state())


@app.route("/api/audio/devices")
def api_audio_devices():
    if not HAS_PYAUDIO:
        return jsonify({"devices": [], "sim": True})
    pa = pyaudio.PyAudio()
    devices = []
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if d["maxInputChannels"] > 0:
            devices.append({"idx": i, "name": d["name"]})
    pa.terminate()
    return jsonify({"devices": devices, "sim": False})


@app.route("/api/input/audio-devices")
def api_input_audio_devices():
    """Capture devices REC can record from (incl. the XR18's USB return)."""
    devices = []
    if HAS_SD:
        try:
            if not (click_out._stream or recorder._stream):
                sd._terminate()
                sd._initialize()
        except Exception:
            pass
        try:
            default_in = sd.default.device[0]
        except Exception:
            default_in = None
        try:
            for i, d in enumerate(sd.query_devices()):
                if d.get("max_input_channels", 0) > 0:
                    devices.append({"idx": i, "name": d["name"], "default": i == default_in,
                                    "channels": int(d.get("max_input_channels", 2))})
        except Exception:
            pass
        return jsonify({"devices": devices, "available": True})
    if not HAS_PYAUDIO:
        return jsonify({"devices": [], "available": False})
    pa = pyaudio.PyAudio()
    try:
        try:
            default_idx = pa.get_default_input_device_info().get("index")
        except Exception:
            default_idx = None
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            if d.get("maxInputChannels", 0) > 0:
                devices.append({"idx": i, "name": d["name"], "default": i == default_idx,
                                "channels": int(d.get("maxInputChannels", 2))})
    finally:
        pa.terminate()
    return jsonify({"devices": devices, "available": True})


@app.route("/api/output/audio-devices")
def api_output_audio_devices():
    """Playback devices the click can be routed to (IEM feeds etc.).

    PortAudio snapshots the device list at init — devices plugged in AFTER
    launch (the XR18 over USB, typically) would never appear. Re-initialise
    before listing, but only while no stream is open (terminating PortAudio
    under an active stream is how apps crash)."""
    if HAS_SD:
        try:
            if not (click_out._stream or recorder._stream):
                sd._terminate()
                sd._initialize()
        except Exception:
            pass
        devices = []
        try:
            default_out = sd.default.device[1]
        except Exception:
            default_out = None
        try:
            for i, d in enumerate(sd.query_devices()):
                if d.get("max_output_channels", 0) > 0:
                    devices.append({"idx": i, "name": d["name"], "default": i == default_out,
                                    "channels": int(d.get("max_output_channels", 2))})
        except Exception:
            pass
        return jsonify({"devices": devices, "available": True})
    if not HAS_PYAUDIO:
        return jsonify({"devices": [], "available": False})
    pa = pyaudio.PyAudio()
    devices = []
    try:
        try:
            default_idx = pa.get_default_output_device_info().get("index")
        except Exception:
            default_idx = None
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            if d.get("maxOutputChannels", 0) > 0:
                devices.append({"idx": i, "name": d["name"], "default": i == default_idx,
                                "channels": int(d.get("maxOutputChannels", 2))})
    finally:
        pa.terminate()
    return jsonify({"devices": devices, "available": True})


@app.route("/api/audio/start", methods=["POST"])
def api_audio_start():
    if state["audio"]["running"]:
        return jsonify({"ok": True, "mode": "already_running"})
    state["audio"]["running"] = True
    if HAS_PYAUDIO and HAS_NUMPY:
        t = threading.Thread(target=audio_live_thread, daemon=True)
        t.start()
        return jsonify({"ok": True, "mode": "live"})
    else:
        return jsonify({"ok": True, "mode": "sim"})


@app.route("/api/audio/stop", methods=["POST"])
def api_audio_stop():
    state["audio"]["running"] = False
    state["audio"]["bpm_detected"] = None
    state["audio"]["bpm_confidence"] = 0.0
    tempo.reset()
    broadcast("tempo", {"bpm": None, "confidence": 0.0})
    return jsonify({"ok": True})


@app.route("/api/chase/advance", methods=["POST"])
def api_chase_advance():
    global _chase_pos
    _chase_pos += 1
    _update_dmx_from_lighting()
    return jsonify({"ok": True})


@app.route("/api/capabilities")
def api_capabilities():
    return jsonify({
        "numpy": HAS_NUMPY,
        "pyaudio": HAS_PYAUDIO,
        "flask": HAS_FLASK,
        "pyserial": dmx_output.HAS_SERIAL,
        "dmx_modes": ["sim", "enttec", "artnet"],
        "dmx_connected": output.connected and output.mode != "sim",
        "dmx_mode": output.mode,
        "midi": midi_input.HAS_MIDI,
        "midi_connected": midi.connected,
    })


@app.route("/api/dmx/ports")
def api_dmx_ports():
    return jsonify({"ports": output.list_ports(), "has_serial": dmx_output.HAS_SERIAL})


@app.route("/api/dmx/status")
def api_dmx_status():
    return jsonify(output.state())


@app.route("/api/midi/ports")
def api_midi_ports():
    return jsonify({"ports": midi.list_ports(), "has_midi": midi_input.HAS_MIDI})


@app.route("/api/midi/outports")
def api_midi_outports():
    return jsonify({"ports": midi_clock.list_ports(),
                    "available": midi_input.HAS_MIDI})


@app.route("/api/midi/status")
def api_midi_status():
    return jsonify(midi.state())


TRACKS_DIR = Path.home() / ".limestudio" / "tracks"
TRACK_EXTS = (".wav", ".mp3", ".m4a", ".aac", ".aif", ".aiff", ".ogg", ".flac")


@app.route("/api/tracks/upload", methods=["POST"])
def api_tracks_upload():
    """Store an uploaded audio file; the song references it by id."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "no file"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in TRACK_EXTS:
        return jsonify({"ok": False, "error": f"unsupported type {ext}"}), 400
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    tid = uuid.uuid4().hex + ext
    f.save(str(TRACKS_DIR / tid))
    return jsonify({"ok": True, "id": tid, "name": os.path.basename(f.filename)})


@app.route("/api/tracks/<tid>")
def api_tracks_get(tid):
    # ids are uuid4 hex + extension — anything else is rejected outright
    stem, ext = os.path.splitext(tid)
    if ("/" in tid or ".." in tid or len(stem) != 32
            or not all(c in "0123456789abcdef" for c in stem)
            or ext not in TRACK_EXTS):
        return ("bad track id", 400)
    return send_from_directory(str(TRACKS_DIR), tid)


# ── Voice samples ─────────────────────────────────────────────────────────────
# The browser's speechSynthesis has 100-300 ms of per-utterance startup latency,
# which makes spoken counts land late. Instead we render each cue word ONCE with
# the macOS system voice (`say`), trim the leading silence, cache the WAV, and
# the client plays it as a Web Audio buffer on the same clock as the click.
VOICE_DIR = Path.home() / ".limestudio" / "voice"
_VOICE_RE = __import__("re").compile(r"^[a-z0-9 '\-]{1,32}$")


def _trim_wav_silence(path, thresh=400):
    """Cut leading/trailing silence so playback onset == beat time."""
    import array
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    if params.sampwidth != 2:
        return
    samples = array.array("h", frames)
    ch = params.nchannels
    n = len(samples) // ch
    first, last = 0, n
    for i in range(n):
        if any(abs(samples[i * ch + c]) > thresh for c in range(ch)):
            first = i
            break
    for i in range(n - 1, -1, -1):
        if any(abs(samples[i * ch + c]) > thresh for c in range(ch)):
            last = i + 1
            break
    if last <= first:
        return
    first = max(0, first - int(params.framerate * 0.005))   # keep 5 ms attack
    last = min(n, last + int(params.framerate * 0.08))      # keep 80 ms tail
    with wave.open(str(path), "wb") as w:
        w.setparams(params)
        w.writeframes(samples[first * ch:last * ch].tobytes())


@app.route("/api/voice")
def api_voice():
    """Return (and lazily render) a spoken sample for a short cue text."""
    import hashlib
    import shutil as _shutil
    import subprocess
    text = (request.args.get("text") or "").strip().lower()
    if not _VOICE_RE.match(text):
        return ("bad text", 400)
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    fname = hashlib.sha1(text.encode()).hexdigest()[:20] + ".wav"
    path = VOICE_DIR / fname
    if not path.exists():
        if not _shutil.which("say"):
            return ("no system voice on this platform", 404)
        try:
            subprocess.run(
                ["say", "-o", str(path), "--file-format=WAVE",
                 "--data-format=LEI16@22050", text],
                check=True, timeout=15,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _trim_wav_silence(path)
        except Exception as e:
            try:
                path.unlink()
            except OSError:
                pass
            return (f"voice render failed: {e}", 500)
    return send_from_directory(str(VOICE_DIR), fname, mimetype="audio/wav")


@app.route("/api/setlist/export", methods=["POST"])
def api_setlist_export():
    """Write the set to the Desktop as a .limeshow bundle — the setlist JSON
    plus every backing-track audio file it references, so a bandmate's import
    is complete. Plain zip inside, custom extension to keep it double-click
    friendly later."""
    import zipfile
    try:
        folder = Path.home() / "Desktop"
        if not folder.is_dir():
            folder = Path.home()           # no Desktop? home dir works everywhere
        dest = folder / "Lime Studio set.limeshow"
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("setlist.json", json.dumps(
                {"setlist": state["setlist"], "looks": state["looks"],
                 "mixes": state["mixer"]["scenes"]}, indent=2))
            seen = set()
            for song in state["setlist"]:
                for t in song.get("tracks", []) or []:
                    tid = t.get("id")
                    if not tid or tid in seen:
                        continue
                    seen.add(tid)
                    p = TRACKS_DIR / tid
                    if p.is_file():
                        z.write(p, "tracks/" + tid)
        return jsonify({"ok": True, "path": str(dest)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/setlist/import", methods=["POST"])
def api_setlist_import():
    """Import a .limeshow bundle (zip: setlist.json + tracks/) or a legacy
    plain-JSON setlist. Audio lands in the local track library."""
    import io
    import zipfile
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "no file"}), 400
    raw = f.read()
    try:
        if raw[:2] == b"PK":                       # zip bundle
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                d = json.loads(z.read("setlist.json").decode("utf-8"))
                TRACKS_DIR.mkdir(parents=True, exist_ok=True)
                copied = 0
                for name in z.namelist():
                    if not name.startswith("tracks/") or name.endswith("/"):
                        continue
                    tid = os.path.basename(name)
                    stem, ext = os.path.splitext(tid)
                    if (len(stem) != 32 or not all(c in "0123456789abcdef" for c in stem)
                            or ext not in TRACK_EXTS):
                        continue                    # only well-formed library ids
                    p = TRACKS_DIR / tid
                    if not p.exists():
                        p.write_bytes(z.read(name))
                        copied += 1
        else:                                       # legacy plain JSON
            d = json.loads(raw.decode("utf-8"))
            copied = 0
        lst = d if isinstance(d, list) else d.get("setlist")
        if not isinstance(lst, list):
            return jsonify({"ok": False, "error": "not a Lime Studio setlist"}), 400
        state["setlist"] = [_migrate_song(s) for s in lst]
        state["active_song_idx"] = None
        state["click"]["pending_song"] = None
        # merge bundled looks so lane look-refs survive; never clobber existing ids
        have = {l["id"] for l in state["looks"]}
        looks_added = 0
        for lk in (d.get("looks") or []) if isinstance(d, dict) else []:
            c = _clean_look(lk)
            if c and c["id"] not in have:
                state["looks"].append(c)
                have.add(c["id"])
                looks_added += 1
        # bundled mixer scenes merge the same way — never clobber existing ids
        havem = {s["id"] for s in state["mixer"]["scenes"]}
        for mx in (d.get("mixes") or []) if isinstance(d, dict) else []:
            c = _clean_mix_scene(mx)
            if c and c["id"] not in havem:
                state["mixer"]["scenes"].append(c)
                havem.add(c["id"])
        _save_show()
        broadcast("state", _full_state())
        return jsonify({"ok": True, "songs": len(lst), "tracks_copied": copied,
                        "looks_added": looks_added})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ── Boot ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Start click track thread
    t_click = threading.Thread(target=click_thread, daemon=True)
    t_click.start()

    # Start audio sim thread (always, as fallback)
    t_sim = threading.Thread(target=audio_sim_thread, daemon=True)
    t_sim.start()

    print("━" * 50)
    print("  Lime Studio — Band Performance Controller")
    print("  http://localhost:4748")
    print("━" * 50)
    print(f"  NumPy:    {'✓' if HAS_NUMPY else '✗ (pip install numpy)'}")
    print(f"  PyAudio:  {'✓' if HAS_PYAUDIO else '✗ (pip install pyaudio)'}")
    print(f"  pyserial: {'✓' if dmx_output.HAS_SERIAL else '✗ (pip install pyserial)'}")
    print(f"  DMX out:  sim · ENTTEC USB Pro · Art-Net")
    print("━" * 50)

    app.run(host="0.0.0.0", port=4748, debug=False)
