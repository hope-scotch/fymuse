"""
Lime Studio — live tempo (BPM) detection
====================================
Estimates the song's tempo from the live audio energy the analysis thread is
already producing, so the click can auto-follow the band instead of being typed
in by hand.

Pipeline (deliberately lightweight, runs on the existing ~25 Hz energy frames):

  per-frame energy  →  positive flux (onset strength)  →  ring buffer
                    →  autocorrelation over musical lags  →  BPM + confidence

No NumPy required — plain Python over a deque, cheap enough at envelope rate.
`estimate_tempo` is a pure function so it can be unit-tested on synthetic
onset trains with a known tempo.
"""

from collections import deque


def estimate_tempo(env, fps, min_bpm=70.0, max_bpm=180.0):
    """Estimate BPM from an onset-strength envelope.

    env  : sequence of non-negative onset-strength samples (newest last)
    fps  : envelope sample rate (samples per second)
    returns (bpm, confidence) or (None, 0.0) if there isn't enough signal.
    confidence is the normalized autocorrelation peak height in [0,1].
    """
    n = len(env)
    if n < int(fps * 2):           # need at least ~2 s of history
        return None, 0.0

    # mean-remove so silence / DC doesn't dominate the correlation
    mean = sum(env) / n
    x = [v - mean for v in env]

    energy0 = sum(v * v for v in x)
    if energy0 <= 1e-9:            # essentially flat — no beat
        return None, 0.0

    # Search one lag past the musical range on each side so the peak we care
    # about always has both neighbours available for parabolic interpolation.
    lag_min = max(1, int(round(fps * 60.0 / max_bpm)) - 1)
    lag_max = min(n - 2, int(round(fps * 60.0 / min_bpm)) + 1)
    if lag_max <= lag_min + 1:
        return None, 0.0

    corr = {}
    for lag in range(lag_min, lag_max + 1):
        s = 0.0
        for i in range(n - lag):
            s += x[i] * x[i + lag]
        corr[lag] = s / (n - lag)   # normalize by overlap

    # pick the strongest lag strictly inside the musical band
    band_lo = max(lag_min + 1, int(round(fps * 60.0 / max_bpm)))
    band_hi = min(lag_max - 1, int(round(fps * 60.0 / min_bpm)))
    best_lag, best_corr = 0, -1.0
    for lag in range(band_lo, band_hi + 1):
        if corr[lag] > best_corr:
            best_corr = corr[lag]
            best_lag = lag
    if best_lag == 0 or best_corr <= 0:
        return None, 0.0

    # Parabolic interpolation around the peak → sub-sample lag (big accuracy win
    # at low lags, where one integer step can be several BPM).
    y1, y2, y3 = corr.get(best_lag - 1, best_corr), best_corr, corr.get(best_lag + 1, best_corr)
    denom = (y1 - 2 * y2 + y3)
    delta = 0.5 * (y1 - y3) / denom if abs(denom) > 1e-12 else 0.0
    delta = max(-0.5, min(0.5, delta))
    true_lag = best_lag + delta

    bpm = 60.0 * fps / true_lag
    while bpm < min_bpm:
        bpm *= 2
    while bpm > max_bpm:
        bpm /= 2

    conf = best_corr / (energy0 / n)     # peak height vs per-sample energy
    conf = max(0.0, min(1.0, conf))
    return round(bpm, 1), round(conf, 3)


class TempoTracker:
    """Accumulates onset strength from per-frame energy and estimates tempo.

    Feed it total energy each audio frame via `push`; call `estimate` whenever
    you want a reading (it rate-limits internally). `fps` is the frame rate of
    whatever's calling push (sim ≈ 20 Hz, live ≈ 25 Hz).
    """
    def __init__(self, fps=25.0, window_s=6.0, min_bpm=70.0, max_bpm=180.0):
        self.window_s = window_s
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        self.configure(fps)

    def configure(self, fps):
        """(Re)set the frame rate and clear history — call when the audio
        source (sim ≈20 Hz vs live ≈25 Hz) changes."""
        self.fps = float(fps)
        self.maxlen = max(1, int(self.fps * self.window_s))
        self.env = deque(maxlen=self.maxlen)
        self._prev = 0.0
        self._since_est = 0
        self.bpm = None
        self.confidence = 0.0

    def push(self, energy):
        """Add one frame. `energy` is a single scalar (e.g. bass+mid+high)."""
        flux = energy - self._prev
        self._prev = energy
        self.env.append(flux if flux > 0 else 0.0)   # half-wave rectify
        self._since_est += 1

    def estimate(self, every=None):
        """Recompute BPM at most every `every` frames (default ~0.4 s)."""
        if every is None:
            every = max(1, int(self.fps * 0.4))
        if self._since_est < every:
            return self.bpm, self.confidence
        self._since_est = 0
        bpm, conf = estimate_tempo(list(self.env), self.fps, self.min_bpm, self.max_bpm)
        if bpm is not None:
            self.bpm = bpm
            self.confidence = conf
        return self.bpm, self.confidence

    def reset(self):
        self.configure(self.fps)
