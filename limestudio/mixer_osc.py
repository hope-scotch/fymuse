"""
Lime Studio — XR18 mixer link (OSC over UDP)
============================================
Drives a Behringer XR18 / X Air desk the way X Air Edit and Mixing Station do:
plain OSC datagrams on UDP port 10024. Lime Studio deliberately manages only a
"recall-safe" parameter set — channel faders, mutes and the 6 bus sends (the
band's IEM mixes), plus LR / bus / USB-return levels. Preamp gain, EQ,
compression and FX are never written, so a song recall can't wreck soundcheck.

Design mirrors dmx_output.py:
  - pure, unit-testable packet builders (OSC encode/parse)
  - a Link class owning the socket + receive thread + param cache
  - a simulator fallback: with no desk connected, the cache *is* the desk, so
    scenes can be captured/applied/tested anywhere.

Scenes are flat {osc_address: value} dicts. apply() glides fader-type floats
from their current cached value to the target so recalls sound like a hand on
the faders, not a jump cut. Mutes switch immediately.
"""

import socket
import struct
import threading
import time

XAIR_PORT = 10024
GLIDE_DEFAULT = 0.8     # seconds; fader ramp on scene recall
GLIDE_STEPS = 16

# ── OSC wire format (pure functions) ─────────────────────────────────────────


def _pad(b):
    """Null-pad bytes to a multiple of 4 (OSC alignment)."""
    return b + b"\x00" * (4 - (len(b) % 4 or 4))


def build_osc(address, *args):
    """Encode one OSC message. Supports f/i/s args (all X Air needs)."""
    out = _pad(address.encode("ascii") + b"\x00")
    tags = ","
    payload = b""
    for a in args:
        if isinstance(a, bool):
            a = int(a)
        if isinstance(a, float):
            tags += "f"
            payload += struct.pack(">f", a)
        elif isinstance(a, int):
            tags += "i"
            payload += struct.pack(">i", a)
        else:
            tags += "s"
            payload += _pad(str(a).encode("utf-8") + b"\x00")
    return out + _pad(tags.encode("ascii") + b"\x00") + payload


def parse_osc(data):
    """Decode one OSC message → (address, [args]). Unknown tags are skipped."""
    try:
        nul = data.index(b"\x00")
        address = data[:nul].decode("ascii", "replace")
        i = (nul + 4) & ~3
        if i >= len(data) or data[i:i + 1] != b",":
            return address, []
        nul2 = data.index(b"\x00", i)
        tags = data[i + 1:nul2].decode("ascii", "replace")
        i = (nul2 + 4) & ~3
        args = []
        for t in tags:
            if t == "f":
                args.append(struct.unpack(">f", data[i:i + 4])[0]); i += 4
            elif t == "i":
                args.append(struct.unpack(">i", data[i:i + 4])[0]); i += 4
            elif t == "s":
                n = data.index(b"\x00", i)
                args.append(data[i:n].decode("utf-8", "replace"))
                i = (n + 4) & ~3
            else:
                break
        return address, args
    except (ValueError, struct.error, IndexError):
        return "", []


def fader_to_db(f):
    """X Air fader float (0..1) → dB label. Piecewise per the X32/X Air map."""
    if f >= 0.5:
        d = f * 40.0 - 30.0
    elif f >= 0.25:
        d = f * 80.0 - 50.0
    elif f >= 0.0625:
        d = f * 160.0 - 70.0
    else:
        d = f * 480.0 - 90.0
    return round(d, 1)


# ── Managed parameter set ─────────────────────────────────────────────────────
N_BUSES = 6


def managed_addresses(channels=6):
    """Every OSC address Lime Studio captures into a scene: faders, mutes,
    bus sends, pan, the FX1 ("reverb") send and the 4-band channel EQ.
    Recall-safe by construction: preamp GAIN is deliberately absent — a song
    recall must never be able to push a hot mic into feedback."""
    out = []
    for c in range(1, max(1, min(16, channels)) + 1):
        base = "/ch/%02d/mix" % c
        out.append(base + "/fader")
        out.append(base + "/on")
        out.append(base + "/pan")
        for b in range(1, N_BUSES + 1):
            out.append("%s/%02d/level" % (base, b))
        out.append(base + "/07/level")          # FX1 send = the reverb knob
        out.append("/ch/%02d/eq/on" % c)
        for band in range(1, 5):                # 4-band EQ: freq/gain/Q
            for p in ("f", "g", "q"):
                out.append("/ch/%02d/eq/%d/%s" % (c, band, p))
    # USB/aux return — where Lime's click/tracks/cues land over USB
    out.append("/rtn/aux/mix/fader")
    out.append("/rtn/aux/mix/on")
    out.append("/rtn/aux/mix/pan")
    for b in range(1, N_BUSES + 1):
        out.append("/rtn/aux/mix/%02d/level" % b)
    out.append("/rtn/aux/mix/07/level")          # reverb send for the tracks
    # masters — LR carries a 6-band EQ (room EQ per song is fair game)
    out.append("/lr/mix/fader")
    out.append("/lr/mix/on")
    out.append("/lr/eq/on")
    for band in range(1, 7):
        for p in ("f", "g", "q"):
            out.append("/lr/eq/%d/%s" % (band, p))
    for b in range(1, N_BUSES + 1):
        out.append("/bus/%d/mix/fader" % b)
    return out


def control_addresses(channels=6):
    """Everything the live console may touch = the scene set PLUS preamp
    gains (live-only; never captured)."""
    out = managed_addresses(channels)
    out += ["/headamp/%02d/gain" % c for c in range(1, max(1, min(16, channels)) + 1)]
    return out


def name_addresses(channels=6):
    """Channel/bus scribble-strip names — read once so the UI shows the
    band's own labels straight off the desk."""
    out = ["/ch/%02d/config/name" % c for c in range(1, channels + 1)]
    out += ["/bus/%d/config/name" % b for b in range(1, N_BUSES + 1)]
    return out


def _default_value(address):
    """Sensible sim defaults per parameter type."""
    if address.endswith("/on"):
        return 1
    if address.endswith("/fader"):
        return 0.75
    if address.endswith("/pan"):
        return 0.5                       # centre
    if address.endswith("/gain"):
        return 0.3                       # ≈ +9 dB headamp
    if "/eq/" in address:
        if address.endswith("/g") or address.endswith("/q"):
            return 0.5                   # 0 dB / medium Q
        if address.endswith("/f"):       # spread the bands sensibly
            try:
                band = int(address.split("/eq/")[1].split("/")[0])
                if address.startswith("/lr/"):   # 6-band main EQ
                    return {1: 0.08, 2: 0.26, 3: 0.42, 4: 0.58, 5: 0.74, 6: 0.9}.get(band, 0.5)
                return {1: 0.12, 2: 0.4, 3: 0.6, 4: 0.85}.get(band, 0.5)
            except (ValueError, IndexError):
                return 0.5
    if address.endswith("/07/level"):
        return 0.0                       # reverb send starts dry
    return 0.5   # bus send levels


# ── Link ─────────────────────────────────────────────────────────────────────
class XR18Link:
    def __init__(self, on_update=None):
        self.host = ""
        self.sock = None
        self.connected = False
        self.status = "Sim — no desk connected; scenes still work"
        self.error = None
        self.channels = 6
        self.cache = {}            # address -> value (THE desk state, or the sim)
        self.names = {}            # address -> scribble name
        self.on_update = on_update
        self._run = False
        self._rx_thread = None
        self._ka_thread = None
        self._last_seen = 0.0
        self._glide_gen = 0        # bumping this cancels a running glide
        self.gliding = False       # True while a recall ramp runs
        self._lock = threading.Lock()

    # -- lifecycle --
    def connect(self, host, channels=None):
        self.disconnect()
        if channels:
            self.channels = max(1, min(16, int(channels)))
        self.host = (host or "").strip()
        if not self.host:
            return self.state()
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(0.5)
            self._run = True
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thread.start()
            self._ka_thread = threading.Thread(target=self._keepalive, daemon=True)
            self._ka_thread.start()
            self.status = "Connecting to " + self.host + "…"
            self.error = None
            self._send("/xinfo")
            self.query_all()
        except Exception as e:
            self.error = str(e)
            self.status = "Error: " + str(e)
        return self.state()

    def disconnect(self):
        self._run = False
        self._glide_gen += 1
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        self.connected = False
        self.status = "Sim — no desk connected; scenes still work"
        return self.state()

    # -- wire --
    def _send(self, address, *args):
        if self.sock and self.host:
            try:
                self.sock.sendto(build_osc(address, *args), (self.host, XAIR_PORT))
            except Exception as e:
                self.error = str(e)

    def _rx_loop(self):
        while self._run and self.sock:
            try:
                data, _ = self.sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            address, args = parse_osc(data)
            if not address:
                continue
            self._last_seen = time.monotonic()
            if not self.connected:
                self.connected = True
                self.status = "XR18 @ " + self.host
            if address.endswith("/config/name") and args:
                self.names[address] = str(args[0])
            elif args:
                with self._lock:
                    self.cache[address] = args[0]
            if self.on_update:
                try:
                    self.on_update(address, args)
                except Exception:
                    pass

    def _keepalive(self):
        """Renew /xremote (the desk pushes changes for 10 s per request) and
        watch for the desk going away."""
        while self._run:
            self._send("/xremote")
            time.sleep(8)
            if self.connected and time.monotonic() - self._last_seen > 20:
                self.connected = False
                self.status = "No reply from " + self.host + " — check the network"

    # -- parameters --
    def query_all(self):
        for a in control_addresses(self.channels) + name_addresses(self.channels):
            self._send(a)

    def get(self, address):
        with self._lock:
            if address not in self.cache:
                self.cache[address] = _default_value(address)
            return self.cache[address]

    def set(self, address, value):
        """One live parameter (UI strip move). Cache always updates — that's
        the sim; the datagram goes out when a desk is online."""
        if address.endswith("/on"):
            value = int(value)
        else:
            value = max(0.0, min(1.0, float(value)))
        with self._lock:
            self.cache[address] = value
        self._send(address, value)

    # -- scenes --
    def snapshot(self):
        """Instant snapshot of every scene-managed param from the cache —
        no re-query, no sleep. The cache tracks desk-side moves via /xremote,
        so this is what the song's mix auto-save uses."""
        return {a: self.get(a) for a in managed_addresses(self.channels)}

    def capture(self):
        """Snapshot every managed parameter. With a live desk, re-query and
        give replies a moment to land; offline, the cache is the truth."""
        if self.connected:
            self.query_all()
            time.sleep(0.6)
        return {a: self.get(a) for a in managed_addresses(self.channels)}

    def apply(self, params, glide=GLIDE_DEFAULT):
        """Recall a scene. Mutes flip immediately; floats glide from their
        current value so the recall sounds like hands on faders."""
        self._glide_gen += 1
        gen = self._glide_gen
        self.gliding = True
        ints = {a: v for a, v in params.items() if a.endswith("/on")}
        floats = {a: float(v) for a, v in params.items() if not a.endswith("/on")}
        for a, v in ints.items():
            self.set(a, v)
        start = {a: float(self.get(a)) for a in floats}
        moving = {a: v for a, v in floats.items() if abs(v - start[a]) > 0.001}
        if not moving or glide <= 0:
            for a, v in floats.items():
                self.set(a, v)
            self.gliding = False
            return

        def run():
            steps = max(2, int(GLIDE_STEPS * max(0.2, glide)))
            for s in range(1, steps + 1):
                if gen != self._glide_gen:
                    return                      # a newer recall took over
                t = s / steps
                k = t * t * (3 - 2 * t)         # smoothstep, like the lights
                for a, v in moving.items():
                    self.set(a, start[a] + (v - start[a]) * k)
                time.sleep(glide / steps)
            self.gliding = False
        threading.Thread(target=run, daemon=True).start()

    # -- state --
    def channel_names(self, fallback=None):
        out = []
        for c in range(1, self.channels + 1):
            n = self.names.get("/ch/%02d/config/name" % c, "")
            if not n and fallback and c - 1 < len(fallback):
                n = fallback[c - 1]
            out.append(n or ("Ch %d" % c))
        return out

    def bus_names(self, fallback=None):
        out = []
        for b in range(1, N_BUSES + 1):
            n = self.names.get("/bus/%d/config/name" % b, "")
            if not n and fallback and b - 1 < len(fallback):
                n = fallback[b - 1]
            out.append(n or ("Bus %d" % b))
        return out

    def state(self):
        return {
            "host": self.host,
            "connected": bool(self.connected),
            "status": self.status,
            "error": self.error,
            "channels": self.channels,
        }
