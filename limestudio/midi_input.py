"""
Lime Studio — MIDI input (hands-free cue triggers)
==============================================
Lets a foot pedal or pad controller fire cues, toggle the click, blackout the
lights, jump songs, tap tempo, etc. — so nobody has to touch the laptop mid-song.

Design mirrors dmx_output.py: real hardware is optional (graceful fallback if
`mido` isn't installed), and everything routes through one manager. Incoming
messages are normalized to a tiny dict and matched against a user-editable
mapping. The resolver is a pure function so the note/CC → action logic can be
unit-tested, and `inject()` runs the exact same dispatch path with no hardware,
which is how the UI's "Test" button and the test suite exercise it.

A binding is:  {"trigger": {"type": "note"|"cc", "number": int},
                "action":  {"type": <action>, ...params}}

Press-edge only: note-on with velocity>0, or CC value>=64 — so releases don't
double-fire.
"""

import threading
import time

try:
    import mido
    HAS_MIDI = True
except Exception:
    HAS_MIDI = False


# Action types a binding may invoke (validated in server._perform_midi_action).
ACTION_TYPES = (
    "cue_index",        # fire the active song's Nth cue   (params: index)
    "cue_text",         # speak arbitrary text             (params: text)
    "click_toggle",     # start/stop the click
    "blackout",         # lights → off
    "scene",            # set a lighting scene             (params: scene)
    "next_song",        # activate next song in setlist
    "prev_song",        # activate previous song
    "chase_advance",    # step the chase one fixture
    "tap_tempo",        # each press is a tap
    "use_detected_tempo",  # snap click to detected BPM
)

DEFAULT_MAPPING = [
    {"trigger": {"type": "note", "number": 60}, "action": {"type": "cue_index", "index": 0}},
    {"trigger": {"type": "note", "number": 62}, "action": {"type": "cue_index", "index": 1}},
    {"trigger": {"type": "note", "number": 64}, "action": {"type": "cue_index", "index": 2}},
    {"trigger": {"type": "note", "number": 65}, "action": {"type": "cue_index", "index": 3}},
    {"trigger": {"type": "note", "number": 36}, "action": {"type": "click_toggle"}},
    {"trigger": {"type": "note", "number": 37}, "action": {"type": "blackout"}},
    {"trigger": {"type": "note", "number": 38}, "action": {"type": "tap_tempo"}},
    {"trigger": {"type": "note", "number": 39}, "action": {"type": "chase_advance"}},
    {"trigger": {"type": "note", "number": 43}, "action": {"type": "next_song"}},
    {"trigger": {"type": "note", "number": 45}, "action": {"type": "prev_song"}},
]


def normalize(msg):
    """mido message → {type:'note'|'cc', number, value, channel, edge} or None.

    `edge` is True for a press (note-on vel>0 / CC>=64), False for a release.
    Only note_on / note_off / control_change are kept.
    """
    t = getattr(msg, "type", None)
    ch = getattr(msg, "channel", 0)
    if t == "note_on":
        vel = getattr(msg, "velocity", 0)
        return {"type": "note", "number": msg.note, "value": vel, "channel": ch, "edge": vel > 0}
    if t == "note_off":
        return {"type": "note", "number": msg.note, "value": 0, "channel": ch, "edge": False}
    if t == "control_change":
        val = getattr(msg, "value", 0)
        return {"type": "cc", "number": msg.control, "value": val, "channel": ch, "edge": val >= 64}
    return None


def resolve(mapping, ev):
    """Return the action for a normalized event, or None.

    Only press-edge events match, so triggers fire once per press.
    """
    if not ev or not ev.get("edge"):
        return None
    for b in mapping:
        trig = b.get("trigger", {})
        if trig.get("type") == ev["type"] and int(trig.get("number", -1)) == ev["number"]:
            return b.get("action")
    return None


class MidiManager:
    """Owns the input port + dispatches resolved actions.

    Callbacks (all optional):
      on_action(action, ev)   — a binding matched; perform it
      on_activity(ev)         — any message arrived (for the UI indicator / learn)
    """
    def __init__(self, on_action=None, on_activity=None, on_learned=None):
        self.on_action = on_action
        self.on_activity = on_activity
        self.on_learned = on_learned
        self.mapping = [dict(b) for b in DEFAULT_MAPPING]
        self.connected = False
        self.port_name = ""
        self.error = None
        self.learning = None          # binding index awaiting a trigger capture
        self.last = None              # last normalized event (for the UI)
        self._port = None
        self._thread = None
        self._run = False

    # -- discovery --
    def list_ports(self):
        if not HAS_MIDI:
            return []
        try:
            return list(mido.get_input_names())
        except Exception as e:
            self.error = str(e)
            return []

    # -- config --
    def set_mapping(self, mapping):
        self.mapping = [dict(b) for b in (mapping or [])]

    def set_learn(self, index):
        """Arm learn mode for binding `index` (or None to cancel)."""
        self.learning = index

    # -- connection --
    def connect(self, port_name):
        self.disconnect(silent=True)
        if not HAS_MIDI:
            self.error = "python-mido not installed (pip install mido python-rtmidi)"
            self.connected = False
            return self.state()
        try:
            self._port = mido.open_input(port_name)
            self.port_name = port_name
            self.connected = True
            self.error = None
            self._run = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        except Exception as e:
            self.error = str(e)
            self.connected = False
            self._port = None
        return self.state()

    def disconnect(self, silent=False):
        self._run = False
        try:
            if self._port:
                self._port.close()
        except Exception:
            pass
        self._port = None
        self.connected = False
        if not silent:
            self.error = None
        return self.state()

    def _loop(self):
        try:
            for msg in self._iter():
                if not self._run:
                    break
                self._dispatch(normalize(msg))
        except Exception as e:
            self.error = str(e)
            self.connected = False

    def _iter(self):
        # mido ports are iterable and block until a message arrives
        return self._port

    # -- the one dispatch path (real messages AND inject() go through here) --
    def inject(self, ev):
        """Feed a normalized event directly — no hardware. Returns the action
        that fired (or None). Used by the UI 'Test' button and tests."""
        return self._dispatch(ev)

    def _dispatch(self, ev):
        if not ev:
            return None
        self.last = ev
        if self.on_activity:
            try: self.on_activity(ev)
            except Exception: pass

        # Learn mode: the next press captures the trigger for the armed binding.
        if self.learning is not None and ev.get("edge"):
            idx = self.learning
            if 0 <= idx < len(self.mapping):
                self.mapping[idx]["trigger"] = {"type": ev["type"], "number": ev["number"]}
            self.learning = None
            if self.on_learned:
                try: self.on_learned(idx)
                except Exception: pass
            return {"_learned": idx}

        action = resolve(self.mapping, ev)
        if action and self.on_action:
            try: self.on_action(action, ev)
            except Exception: pass
        return action

    def state(self):
        return {
            "connected": bool(self.connected),
            "port": self.port_name,
            "error": self.error,
            "learning": self.learning,
            "mapping": self.mapping,
            "last": self.last,
            "has_midi": HAS_MIDI,
            "action_types": list(ACTION_TYPES),
        }


class MidiClockOut:
    """Sends MIDI clock (24 ppq) plus Start/Stop so delay pedals, drum machines
    and arps follow Lime Studio's tempo. BPM is read live from a callable, so
    mid-song tempo-map changes propagate within one pulse."""

    def __init__(self, get_state):
        # get_state() -> (running: bool, bpm: float)
        self._get_state = get_state
        self._port = None
        self.port_name = None
        self.error = None
        self._thread = None
        self._stop_flag = threading.Event()

    def list_ports(self):
        if not HAS_MIDI:
            return []
        try:
            return list(mido.get_output_names())
        except Exception:
            return []

    def start(self, port_name):
        self.stop()
        if not port_name:
            return True
        if not HAS_MIDI:
            self.error = "python-mido not installed"
            return False
        try:
            self._port = mido.open_output(port_name)
            self.port_name = port_name
            self.error = None
            self._stop_flag.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="midi-clock")
            self._thread.start()
            return True
        except Exception as e:
            self.error = str(e)
            self._port = None
            return False

    def stop(self):
        self._stop_flag.set()
        t = self._thread
        self._thread = None
        if t:
            t.join(timeout=0.5)
        if self._port:
            try:
                self._port.send(mido.Message("stop"))
                self._port.close()
            except Exception:
                pass
        self._port = None
        self.port_name = None

    def state(self):
        return {"port": self.port_name, "error": self.error, "available": HAS_MIDI}

    def _run(self):
        was_running = False
        next_t = None
        while not self._stop_flag.is_set():
            running, bpm = self._get_state()
            if not running:
                if was_running:
                    try:
                        self._port.send(mido.Message("stop"))
                    except Exception:
                        pass
                    was_running = False
                next_t = None
                time.sleep(0.03)
                continue
            if not was_running:
                try:
                    self._port.send(mido.Message("start"))
                except Exception:
                    pass
                was_running = True
                next_t = None
            try:
                self._port.send(mido.Message("clock"))
            except Exception as e:
                self.error = str(e)
                time.sleep(0.2)
                continue
            # absolute deadlines — pulse-train tempo stays drift-free
            interval = 60.0 / max(20.0, min(300.0, float(bpm or 120))) / 24.0
            now = time.monotonic()
            next_t = (now if next_t is None else next_t) + interval
            delay = next_t - now
            if delay > 0:
                time.sleep(delay)
            elif delay < -0.25:
                next_t = now
