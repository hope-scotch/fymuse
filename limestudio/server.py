"""
Lime Studio — Band Performance Controller
Backend server: audio analysis, click track, cue system, DMX simulator
Run: python3 server.py
Open: http://localhost:4748
"""

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
    },
    # Per-fixture patch: each fixture has a 1-indexed DMX base address + a
    # profile that defines its channel layout. Built/replaced via the UI.
    "patch": [],
}

ws_clients = set()

# ── Fixture profiles ──────────────────────────────────────────────────────────
# slots: r,g,b = colour; w = white LED; d = master dimmer. Offsets are 0-based
# from the fixture's base address.
PROFILES = {
    "RGB":   {"width": 3, "slots": {"r": 0, "g": 1, "b": 2}},
    "RGBD":  {"width": 4, "slots": {"r": 0, "g": 1, "b": 2, "d": 3}},
    "RGBW":  {"width": 4, "slots": {"r": 0, "g": 1, "b": 2, "w": 3}},
    "RGBWD": {"width": 5, "slots": {"r": 0, "g": 1, "b": 2, "w": 3, "d": 4}},
    "DIM":   {"width": 1, "slots": {"d": 0}},
}
DEFAULT_PROFILE = "RGBD"


def _default_patch(n, profile=DEFAULT_PROFILE):
    """Lay n fixtures out back-to-back from DMX address 1."""
    w = PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])["width"]
    return [{"base": i * w + 1, "profile": profile} for i in range(n)]


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
    state["active_song_idx"] = idx
    if idx is not None and 0 <= idx < len(state["setlist"]):
        song = _migrate_song(state["setlist"][idx])
        seg = _song_segment(song, 1)
        c.update({"mode": "song", "bar": 1, "beat": 0,
                  "bpm": seg["bpm"], "time_sig": seg["time_sig"]})
        state["lighting"]["scene"] = song.get("scene", "reactive")
    else:
        c.update({"mode": "free", "bar": 1, "beat": 0})
    broadcast("state", _full_state())


def _switch_pending():
    """Land a queued song switch (called at a bar boundary). True if switched."""
    idx = state["click"]["pending_song"]
    state["click"]["pending_song"] = None
    if idx is None or not (0 <= idx < len(state["setlist"])):
        return False
    state["active_song_idx"] = idx
    song = _migrate_song(state["setlist"][idx])
    seg = _song_segment(song, 1)
    state["click"].update({"mode": "song", "bar": 1, "beat": 0,
                           "bpm": seg["bpm"], "time_sig": seg["time_sig"]})
    state["lighting"]["scene"] = song.get("scene", "reactive")
    _update_dmx_from_lighting()
    broadcast("state", _full_state())
    return True


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
        state["lighting"]["scene"] = "off"
        _update_dmx_from_lighting()
        broadcast("state", _full_state())
    elif t == "scene":
        state["lighting"]["scene"] = action.get("scene", "reactive")
        _update_dmx_from_lighting()
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


# ── Show persistence ──────────────────────────────────────────────────────────
# Everything a band would hate to retype — setlist, fixture patch, lighting,
# MIDI mapping — auto-saves to ~/.limestudio/show.json and reloads on launch.
CONFIG_DIR = Path.home() / ".limestudio"
SHOW_FILE = CONFIG_DIR / "show.json"


def _save_show():
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "setlist": state["setlist"],
            "patch": state["patch"],
            "lighting": {k: state["lighting"][k]
                         for k in ("scene", "color", "brightness", "num_fixtures")},
            "midi_mapping": midi.mapping,
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
        state["setlist"] = [_migrate_song(s) for s in (d.get("setlist", []) or [])]
        state["patch"] = d.get("patch", []) or []
        if state["patch"]:
            state["lighting"]["num_fixtures"] = len(state["patch"])
        lit = d.get("lighting") or {}
        state["lighting"].update({k: v for k, v in lit.items() if k in state["lighting"]})
        if d.get("midi_mapping"):
            midi.set_mapping(d["midi_mapping"])
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
            # song mode: play the active song's bar timeline from the seek point
            _migrate_song(song)
            bar = max(1, min(song["length_bars"], int(data.get("bar", state["click"].get("bar", 1)))))
            seg = _song_segment(song, bar)
            state["click"].update({"mode": "song", "bar": bar, "beat": 0,
                                   "bpm": seg["bpm"], "time_sig": seg["time_sig"]})
        else:
            state["click"]["mode"] = "free"
            state["click"]["bpm"] = data.get("bpm", state["click"]["bpm"])
            state["click"]["time_sig"] = data.get("time_sig", state["click"]["time_sig"])
            state["click"]["beat"] = 0
        state["click"]["running"] = True
        broadcast("state", _full_state())

    elif action == "click_stop":
        state["click"]["running"] = False
        state["click"]["beat"] = 0
        state["click"]["bar"] = 1          # stop rewinds — next play starts clean
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
        rebuild = "num_fixtures" in data and data["num_fixtures"] != state["lighting"]["num_fixtures"]
        state["lighting"].update({k: v for k, v in data.items()
                                  if k in state["lighting"]})
        if rebuild:
            # changing the fixture count re-lays a tidy sequential patch,
            # keeping whatever profile fixture 1 currently uses.
            prof = (state["patch"][0]["profile"] if state["patch"] else DEFAULT_PROFILE)
            state["patch"] = _default_patch(state["lighting"]["num_fixtures"], prof)
        _update_dmx_from_lighting()
        _save_show()
        broadcast("state", _full_state())

    elif action == "set_scene":
        state["lighting"]["scene"] = data.get("scene", "reactive")
        _update_dmx_from_lighting()
        broadcast("state", _full_state())

    elif action == "set_patch":
        patch = data.get("patch", [])
        # sanitise: clamp base into 1..512, validate profile
        clean = []
        for fx in patch:
            base = max(1, min(512, int(fx.get("base", 1))))
            prof = fx.get("profile", DEFAULT_PROFILE)
            if prof not in PROFILES:
                prof = DEFAULT_PROFILE
            clean.append({"base": base, "profile": prof})
        state["patch"] = clean
        state["lighting"]["num_fixtures"] = len(clean)
        _update_dmx_from_lighting()
        _save_show()
        broadcast("state", _full_state())

    elif action == "auto_patch":
        n = max(1, min(64, int(data.get("count", state["lighting"]["num_fixtures"]))))
        prof = data.get("profile", DEFAULT_PROFILE)
        if prof not in PROFILES:
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
        "patch": _active_patch(),
        "dmx_preview": state["dmx"][:32],  # first 32 channels for UI
        "output": output.state(),
        "profiles": {k: v["width"] for k, v in PROFILES.items()},
        "midi": midi.state(),
    }


# ── Click track engine ────────────────────────────────────────────────────────
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

            broadcast("beat", {
                "beat": beat, "bar": bar,
                "bpm": bpm, "time_sig": time_sig,
                "downbeat": beat == 0,
                "section": _song_section(song, bar),
                "length_bars": song["length_bars"],
            })

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
            })
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


def _clamp8(v):
    v = int(v)
    return 0 if v < 0 else 255 if v > 255 else v


def _fixture_color(i, n, scene, energy, color, brightness):
    """Return (r, g, b, master) for fixture i — colour 0-255 + master dimmer 0-255."""
    if scene == "off":
        return 0, 0, 0, 0
    if scene == "static":
        return _clamp8(color[0]), _clamp8(color[1]), _clamp8(color[2]), _clamp8(brightness)
    if scene == "reactive":
        bass = energy.get("bass", 0); mid = energy.get("mid", 0); high = energy.get("high", 0)
        # bass→red, mid→green, high→blue; the colour itself carries the pulse.
        return (_clamp8(bass * 255 * 1.2), _clamp8(mid * 180), _clamp8(high * 255),
                _clamp8(brightness))
    if scene == "chase":
        active = (i == (_chase_pos % max(1, n)))
        if active:
            return _clamp8(color[0]), _clamp8(color[1]), _clamp8(color[2]), _clamp8(brightness)
        return 0, 0, 0, 0
    return 0, 0, 0, 0


def _write_fixture(dmx, base0, profile, r, g, b, master):
    """Write one fixture into the 512-channel universe per its profile.

    Fixtures WITH a dimmer slot get raw colour + master on the dimmer.
    Fixtures WITHOUT one get colour pre-scaled by master (master baked in).
    """
    prof = PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])
    slots = prof["slots"]
    if "d" in slots:
        er, eg, eb = r, g, b
    else:
        er, eg, eb = r * master // 255, g * master // 255, b * master // 255
    vals = {"r": er, "g": eg, "b": eb, "w": min(er, eg, eb), "d": master}
    for slot, off in slots.items():
        idx = base0 + off
        if 0 <= idx < 512:
            dmx[idx] = _clamp8(vals.get(slot, 0))


def _update_dmx_from_lighting():
    L = state["lighting"]
    scene = L["scene"]; energy = state["audio"]["energy"]
    color = L["color"]; brightness = L["brightness"]
    patch = _active_patch()
    n = len(patch)

    dmx = [0] * 512
    fixtures = []
    for i, fx in enumerate(patch):
        r, g, b, master = _fixture_color(i, n, scene, energy, color, brightness)
        fixtures.append({"r": r, "g": g, "b": b, "m": master})
        base0 = int(fx.get("base", 1)) - 1   # 1-indexed address → 0-indexed slot
        _write_fixture(dmx, base0, fx.get("profile", DEFAULT_PROFILE), r, g, b, master)

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
    """Write the setlist to the Desktop as a shareable JSON file."""
    try:
        folder = Path.home() / "Desktop"
        if not folder.is_dir():
            folder = Path.home()           # no Desktop? home dir works everywhere
        dest = folder / "Lime Studio setlist.json"
        dest.write_text(json.dumps({"setlist": state["setlist"]}, indent=2))
        return jsonify({"ok": True, "path": str(dest)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
