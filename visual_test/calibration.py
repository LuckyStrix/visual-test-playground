"""Viewing-geometry + subjective display calibration (non-invasive).

No photometer required: records a display "fingerprint" (gamma match,
black/white visibility steps, measured refresh rate, brightness setting,
ambient) so sessions from different computers can be flagged as
comparable or not. Absolute cd/m^2 is NOT measured; values are estimates
and settings, not photometry."""
import math
import statistics
import time
from dataclasses import asdict, dataclass


@dataclass
class DisplayGeometry:
    screen_width_px: int
    screen_height_px: int
    screen_diag_in: float
    viewing_dist_cm: float
    ppd: float
    screen_width_cm: float
    screen_width_deg: float

    def deg_to_px(self, deg):
        return deg * self.ppd

    def px_to_deg(self, px):
        return px / self.ppd


def compute_geometry(screen_width_px, screen_height_px, diag_in, viewing_dist_cm):
    if screen_width_px <= 0 or screen_height_px <= 0:
        raise ValueError("screen resolution must be positive")
    if diag_in <= 0:
        raise ValueError("diagonal must be positive")
    if viewing_dist_cm <= 0:
        raise ValueError("viewing distance must be positive")
    diag_cm = diag_in * 2.54
    aspect = screen_width_px / max(1, screen_height_px)
    h_cm = diag_cm / math.sqrt(1 + aspect ** 2)
    w_cm = h_cm * aspect
    width_deg = 2 * math.degrees(math.atan(w_cm / (2 * viewing_dist_cm)))
    ppd = screen_width_px / width_deg
    return DisplayGeometry(screen_width_px, screen_height_px, diag_in,
                           viewing_dist_cm, ppd, w_cm, width_deg)


def sf_cycles_per_px(sf_cpd, ppd):
    return sf_cpd / ppd


def nyquist_ok(sf_cpd, ppd):
    return sf_cpd < ppd / 2


HALFTONE_LEVELS = (106, 128, 150)


@dataclass
class DisplayProfile:
    gamma_estimate: float | None = None
    gamma_matched_level: int | None = None
    black_step_visible: int | None = None
    white_step_visible: int | None = None
    refresh_hz: float | None = None
    refresh_n_frames: int = 0
    frame_interval_ms_p50: float | None = None
    frame_interval_ms_p95: float | None = None
    frame_jitter_ms: float | None = None
    missed_frames_pct: float | None = None
    brightness_pct: int | None = None
    ambient: str | None = None
    night_mode_off: bool | None = None
    notes: str = ''
    calibrated_utc: str | None = None

    def as_meta(self):
        d = {k: v for k, v in asdict(self).items() if v is not None}
        return {f'display_{k}': v for k, v in d.items()}

    @classmethod
    def from_meta(cls, meta):
        kwargs = {}
        for f in cls.__dataclass_fields__:
            v = (meta or {}).get(f'display_{f}', None)
            if v is not None:
                kwargs[f] = v
        return cls(**kwargs)

    def summary(self):
        bits = []
        if self.gamma_estimate is not None:
            bits.append(f'gamma~{self.gamma_estimate:.2f}')
        if self.refresh_hz is not None:
            bits.append(f'{self.refresh_hz:.0f}Hz')
        if self.black_step_visible is not None:
            bits.append(f'black+{self.black_step_visible}')
        if self.white_step_visible is not None:
            bits.append(f'white-{self.white_step_visible}')
        return ', '.join(bits) if bits else 'not calibrated'

    def comparability(self, other):
        if not isinstance(other, DisplayProfile):
            return ['no reference profile to compare against']
        flags = []
        g1, g2 = self.gamma_estimate, other.gamma_estimate
        if g1 is not None and g2 is not None and abs(g1 - g2) > 0.3:
            flags.append(f'gamma differs ({g1:.2f} vs {g2:.2f})')
        r1, r2 = self.refresh_hz, other.refresh_hz
        if r1 is not None and r2 is not None and abs(r1 - r2) > 5:
            flags.append(f'refresh differs ({r1:.0f} vs {r2:.0f} Hz)')
        if self.ambient != other.ambient:
            flags.append(f'ambient differs ({self.ambient} vs {other.ambient})')
        b1, b2 = self.black_step_visible, other.black_step_visible
        if b1 is not None and b2 is not None and b1 != b2:
            flags.append(f'black point differs (step {b1} vs {b2})')
        w1, w2 = self.white_step_visible, other.white_step_visible
        if w1 is not None and w2 is not None and w1 != w2:
            flags.append(f'white point differs (step {w1} vs {w2})')
        n1, n2 = self.night_mode_off, other.night_mode_off
        if n1 is not None and n2 is not None and n1 != n2:
            flags.append(f'night-mode differs ({n1} vs {n2})')
        br1, br2 = self.brightness_pct, other.brightness_pct
        if br1 is not None and br2 is not None and abs(br1 - br2) > 20:
            flags.append(f'brightness differs ({br1}% vs {br2}%)')
        return flags or ['comparable']


def pooling_flags(reference, sessions):
    flags = {}
    for key, prof in (sessions or {}).items():
        if not isinstance(prof, DisplayProfile):
            try:
                prof = DisplayProfile.from_meta(prof or {})
            except Exception:
                continue
        f = reference.comparability(prof)
        if f != ['comparable']:
            flags[key] = f
    return flags


def gamma_from_halftone_match(matched_level):
    if matched_level is None or matched_level <= 0 or matched_level >= 255:
        raise ValueError('matched_level must be a mid-gray 1..254')
    v = matched_level / 255.0
    return round(float(math.log(0.5) / math.log(v)), 3)


def summarize_frame_intervals(intervals_ms, refresh_hz=None):
    iv = [float(x) for x in intervals_ms if x and math.isfinite(x)]
    if not iv:
        return dict(n_frames=0, p50=None, p95=None, jitter=None, missed_pct=None)
    iv.sort()
    p50 = float(statistics.median(iv))
    p95 = float(iv[min(len(iv) - 1, int(len(iv) * 0.95))])
    jitter = float(statistics.pstdev(iv)) if len(iv) > 1 else 0.0
    expected = 1000.0 / refresh_hz if refresh_hz and refresh_hz > 0 else p50
    missed = sum(1 for x in iv if x > expected * 1.5) / len(iv) * 100.0
    return dict(n_frames=len(iv) + 1, p50=round(p50, 2), p95=round(p95, 2),
                jitter=round(jitter, 2), missed_pct=round(missed, 1))


def measure_refresh_hz(update_fn, exists_fn, n_frames=120, timeout_s=10.0):
    stamps = []
    t_start = time.perf_counter()
    while len(stamps) < n_frames:
        if not exists_fn():
            raise RuntimeError('calibration window closed')
        try:
            update_fn()
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f'refresh measurement failed: {e}')
        now = time.perf_counter()
        if now - t_start > timeout_s:
            break
        stamps.append(now)
    if len(stamps) < 10:
        raise RuntimeError('too few frames to estimate refresh rate')
    intervals = [(b - a) * 1000.0 for a, b in zip(stamps, stamps[1:])]
    med = statistics.median(intervals)
    hz = 1000.0 / med if med > 0 else None
    return round(float(hz), 1) if hz else None, intervals
