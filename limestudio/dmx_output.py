"""
Lime Studio — DMX output backends
=============================
Turns the 512-channel DMX universe computed by the scene engine into real light
output over one of three transports:

  - "sim"     no hardware — UI preview only (default)
  - "enttec"  ENTTEC DMX USB Pro via pyserial (USB → XLR)
  - "artnet"  Art-Net (ArtDMX) over UDP, for venues with network DMX nodes

The OutputManager owns a steady refresh thread that retransmits the latest
universe at a fixed frame rate (DMX wants continuous refresh, not change-only),
decoupled from the scene compute. Connecting/disconnecting is safe at any time;
closing a transport sends one blackout frame first so fixtures don't latch on.

Packet builders are pure functions so they can be unit-tested without hardware.
"""

import socket
import struct
import threading
import time

try:
    import serial
    from serial.tools import list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


# ── Wire formats ─────────────────────────────────────────────────────────────
ENTTEC_START = 0x7E
ENTTEC_END = 0xE7
ENTTEC_LABEL_SEND_DMX = 6          # "Output Only Send DMX Packet Request"
ARTNET_PORT = 6454
ARTNET_OPCODE_DMX = 0x5000         # OpOutput / ArtDMX
ARTNET_PROTO_VER = 14


def _normalize_512(channels):
    """Coerce any sequence to exactly 512 ints in [0,255]."""
    out = bytearray(512)
    n = min(512, len(channels))
    for i in range(n):
        v = int(channels[i])
        out[i] = 0 if v < 0 else 255 if v > 255 else v
    return out


def build_enttec_packet(channels):
    """ENTTEC Pro 'send DMX' frame.

    [0x7E][label=6][len_lo][len_hi][DMX start code 0x00 + 512 channels][0xE7]
    The payload length is 513 (start code + 512 slots).
    """
    body = _normalize_512(channels)
    payload = bytes([0x00]) + bytes(body)      # 0x00 = DMX start code
    n = len(payload)                            # 513
    pkt = bytearray([ENTTEC_START, ENTTEC_LABEL_SEND_DMX, n & 0xFF, (n >> 8) & 0xFF])
    pkt += payload
    pkt.append(ENTTEC_END)
    return bytes(pkt)


def build_artnet_packet(channels, universe=0, sequence=0):
    """ArtDMX packet for one universe.

    'Art-Net\\0' | OpCode(LE) | ProtVer(BE) | Seq | Physical |
    SubUni | Net | Length(BE) | 512 data bytes
    """
    body = _normalize_512(channels)
    hdr = bytearray()
    hdr += b"Art-Net\x00"
    hdr += struct.pack("<H", ARTNET_OPCODE_DMX)   # opcode, little-endian
    hdr += struct.pack(">H", ARTNET_PROTO_VER)    # protocol version, big-endian
    hdr.append(sequence & 0xFF)
    hdr.append(0)                                 # physical port (informational)
    hdr.append(universe & 0xFF)                   # SubUni (low 8 bits)
    hdr.append((universe >> 8) & 0x7F)            # Net (high 7 bits)
    hdr += struct.pack(">H", 512)                 # data length, big-endian
    return bytes(hdr) + bytes(body)


# ── Backends ─────────────────────────────────────────────────────────────────
class SimOutput:
    mode = "sim"
    def connect(self): return True
    def send(self, channels): pass
    def close(self): pass
    def describe(self): return "Simulator — no hardware output"


class EnttecOutput:
    mode = "enttec"
    def __init__(self, port, baud=57600):
        self.port = port
        self.baud = baud
        self.ser = None

    def connect(self):
        if not HAS_SERIAL:
            raise RuntimeError("pyserial is not installed (pip install pyserial)")
        self.ser = serial.Serial(self.port, self.baud, timeout=1)
        return True

    def send(self, channels):
        if self.ser:
            self.ser.write(build_enttec_packet(channels))

    def close(self):
        try:
            if self.ser:
                self.ser.write(build_enttec_packet([0] * 512))  # blackout
                self.ser.flush()
                self.ser.close()
        finally:
            self.ser = None

    def describe(self):
        return f"ENTTEC DMX USB Pro — {self.port}"


class ArtNetOutput:
    mode = "artnet"
    def __init__(self, host, universe=0, port=ARTNET_PORT):
        self.host = host
        self.universe = int(universe)
        self.port = int(port)
        self.sock = None
        self.seq = 1

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        return True

    def send(self, channels):
        if self.sock:
            pkt = build_artnet_packet(channels, self.universe, self.seq)
            self.sock.sendto(pkt, (self.host, self.port))
            self.seq = self.seq % 255 + 1   # 1..255, wraps

    def close(self):
        try:
            if self.sock:
                blk = build_artnet_packet([0] * 512, self.universe, 0)
                self.sock.sendto(blk, (self.host, self.port))   # blackout
                self.sock.close()
        finally:
            self.sock = None

    def describe(self):
        return f"Art-Net — {self.host} · universe {self.universe}"


# ── Manager ──────────────────────────────────────────────────────────────────
class OutputManager:
    """Owns the active backend + a fixed-rate refresh loop.

    `get_universe` is a zero-arg callable returning the current 512-channel list.
    """
    def __init__(self, get_universe):
        self.get_universe = get_universe
        self.backend = SimOutput()
        self.mode = "sim"
        self.connected = True          # sim is always "connected"
        self.status = "Simulator — no hardware output"
        self.error = None
        self.fps = 40
        # last-used config (echoed back to the UI)
        self.port = ""
        self.host = "2.0.0.1"
        self.universe = 0
        self._run = False
        self._thread = None

    # -- discovery --
    def list_ports(self):
        if not HAS_SERIAL:
            return []
        out = []
        for p in list_ports.comports():
            out.append({"device": p.device, "desc": (p.description or "").strip()})
        return out

    # -- connection --
    def connect(self, mode, port="", host="", universe=0, fps=None):
        self.disconnect(silent=True)
        if fps:
            self.fps = max(1, min(60, int(fps)))
        try:
            if mode == "enttec":
                self.port = port
                self.backend = EnttecOutput(port)
            elif mode == "artnet":
                self.host = host or self.host
                self.universe = int(universe or 0)
                self.backend = ArtNetOutput(self.host, self.universe)
            else:
                mode = "sim"
                self.backend = SimOutput()

            self.backend.connect()
            self.mode = mode
            self.connected = True
            self.error = None
            self.status = self.backend.describe()
            if mode != "sim":
                self._start_loop()
            return self.state()
        except Exception as e:
            self.backend = SimOutput()
            self.mode = "sim"
            self.connected = False
            self.error = str(e)
            self.status = "Error: " + str(e)
            return self.state()

    def disconnect(self, silent=False):
        self._run = False
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.0)
        self._thread = None
        try:
            if self.backend:
                self.backend.close()
        except Exception:
            pass
        self.backend = SimOutput()
        self.mode = "sim"
        self.connected = True
        if not silent:
            self.error = None
            self.status = "Simulator — no hardware output"
        return self.state()

    # -- refresh loop --
    def _start_loop(self):
        self._run = True
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._run:
            try:
                self.backend.send(self.get_universe())
            except Exception as e:
                self.error = str(e)
                self.status = "Output error: " + str(e)
                self.connected = False
                self._run = False
                break
            time.sleep(1.0 / max(1, self.fps))

    def state(self):
        return {
            "mode": self.mode,
            "connected": bool(self.connected),
            "status": self.status,
            "error": self.error,
            "fps": self.fps,
            "port": self.port,
            "host": self.host,
            "universe": self.universe,
            "has_serial": HAS_SERIAL,
        }
