"""Calibrated stimulus rendering with Pillow + numpy.

All luminances in 0-255 sRGB gray, background 128. Sizes derived from
pixels-per-degree so results are comparable across displays.
"""

import math

import numpy as np
from PIL import Image

BG = 128


def gabor_patch(
    size_px, ppd, sf_cpd, contrast, orientation_deg=0.0, phase_deg=90.0, sigma_deg=0.8, bg=BG
):
    size_px = int(size_px)
    if size_px <= 0:
        raise ValueError(f"gabor_patch requires size_px >= 1, got {size_px}")
    try:
        ppd = float(ppd)
        sf_cpd = float(sf_cpd)
        contrast = float(contrast)
    except (TypeError, ValueError, OverflowError) as e:
        raise ValueError(f"gabor_patch requires numeric ppd/sf_cpd/contrast: {e}") from e
    if not math.isfinite(ppd) or ppd <= 0:
        raise ValueError(f"gabor_patch requires finite ppd > 0, got {ppd}")
    if not math.isfinite(sf_cpd) or sf_cpd < 0:
        raise ValueError(f"gabor_patch requires finite sf_cpd >= 0, got {sf_cpd}")
    if not math.isfinite(contrast) or contrast < 0:
        raise ValueError(f"gabor_patch requires finite contrast >= 0, got {contrast}")
    sf_cpp = sf_cpd / ppd
    sigma_px = max(2.0, sigma_deg * ppd)
    ax = np.arange(size_px) - (size_px - 1) / 2.0
    x, y = np.meshgrid(ax, ax)
    theta = math.radians(orientation_deg)
    xr = x * math.cos(theta) + y * math.sin(theta)
    yr = -x * math.sin(theta) + y * math.cos(theta)
    carrier = np.sin(2 * math.pi * sf_cpp * xr + math.radians(phase_deg))
    env = np.exp(-(xr**2 + yr**2) / (2 * sigma_px**2))
    lum = bg + contrast * (127.0) * carrier * env
    lum = np.clip(lum, 0, 255)
    arr = np.clip(np.round(lum), 0, 255).astype(np.uint8)
    return Image.fromarray(arr).convert("RGB")


def blank_patch(size_px, bg=BG):
    size_px = int(size_px)
    arr = np.full((size_px, size_px, 3), bg, dtype=np.uint8)
    return Image.fromarray(arr).convert("RGB")


def landolt_c(size_px, gap_dir_deg, stroke_px=None, fg=10, bg=235):
    """Landolt C: dark annulus on light ground with a wedge gap centred exactly
    at gap_dir_deg in standard math convention (0 = east/right, 90 = north/up).
    Matches Acuity4AFC key map: Right=0, Up=90, Left=180, Down=270."""
    s = int(size_px)
    stroke_px = stroke_px or max(2, int(round(s / 5)))
    r_out = s / 2 - 1
    r_in = max(1.0, r_out - stroke_px)
    gap_half = math.degrees(stroke_px / max(r_out, 1.0)) / 2.0
    yy, xx = np.mgrid[0:s, 0:s].astype(float)
    cx = cy = (s - 1) / 2.0
    dx = xx - cx
    dy = cy - yy
    r = np.hypot(dx, dy)
    ang = (np.degrees(np.arctan2(dy, dx)) + 360.0) % 360.0
    gap = ((gap_dir_deg % 360.0) + 360.0) % 360.0
    d_ang = np.abs((ang - gap + 180.0) % 360.0 - 180.0)
    ring = (r <= r_out) & (r >= r_in) & (d_ang >= gap_half)
    arr = np.full((s, s), bg, dtype=np.uint8)
    arr[ring] = fg
    return Image.fromarray(arr).convert("RGB")


def acuity_size_px(logmar, ppd):
    mar_arcmin = 10**logmar
    outer_diam_arcmin = 5 * mar_arcmin
    return max(7, outer_diam_arcmin / 60 * ppd)


def _clip(v):
    return int(max(0, min(255, round(v))))


def isoluminant_pair(delta, axis="rg", lum=128):
    if axis == "rg":
        c1 = (_clip(lum + delta), _clip(lum - delta * 0.5), _clip(lum))
        c2 = (_clip(lum - delta), _clip(lum + delta * 0.5), _clip(lum))
    elif axis == "by":
        c1 = (_clip(lum), _clip(lum), _clip(lum + delta))
        c2 = (_clip(lum), _clip(lum), _clip(lum - delta))
    else:
        c1 = (_clip(lum + delta), _clip(lum), _clip(lum))
        c2 = (_clip(lum - delta), _clip(lum), _clip(lum))
    return c1, c2


def solid_patch(size_px, rgb):
    arr = np.zeros((int(size_px), int(size_px), 3), dtype=np.uint8)
    arr[:, :] = rgb
    return Image.fromarray(arr)


def bullseye(size_px, center_rgb, surround_rgb, center_frac=0.5):
    """Static concentric discs: center vs surround colour judgment."""
    s = int(size_px)
    yy, xx = np.mgrid[0:s, 0:s].astype(float)
    c = (s - 1) / 2.0
    r = np.hypot(xx - c, yy - c) / (s / 2.0)
    arr = np.zeros((s, s, 3), dtype=np.uint8)
    arr[:, :] = surround_rgb
    arr[r <= center_frac] = center_rgb
    return Image.fromarray(arr)


def red_blue_pair(delta, rng=None):
    """Center/surround colours differing along red-blue axis at fixed luminance.
    Returns (center, surround, center_is_redder: bool or None for catch).
    Isoluminance (0.299R+0.587G+0.114B) holds exactly before 0-255 clipping;
    delta is capped at 45.0 to stay in gamut at lum=128. Clipped extremes
    are only approximate.
    Pass a numpy Generator as rng for reproducible polarity; rng=None falls
    back to the global RNG and is NOT replayable — pass an explicit rng."""
    import warnings

    lum, b = 128, 128
    delta = min(delta, 45.0)
    if delta <= 0:
        grey = (_clip(lum), _clip(lum), _clip(b))
        return grey, grey, None
    k = 0.299 / 0.114
    if rng is None:
        warnings.warn("red_blue_pair called without rng; polarity not replayable", stacklevel=2)
    flip = rng.random() < 0.5 if rng is not None else np.random.rand() < 0.5
    if flip:
        center = (_clip(lum + delta), _clip(lum), _clip(b - delta * k))
        surround = (_clip(lum - delta), _clip(lum), _clip(b + delta * k))
        return center, surround, True
    center = (_clip(lum - delta), _clip(lum), _clip(b + delta * k))
    surround = (_clip(lum + delta), _clip(lum), _clip(b - delta * k))
    return center, surround, False


def bright_disc(size_px, lum=255, bg=BG):
    s = int(size_px)
    yy, xx = np.mgrid[0:s, 0:s].astype(float)
    c = (s - 1) / 2.0
    r = np.hypot(xx - c, yy - c) / (s / 2.0)
    arr = np.full((s, s, 3), bg, dtype=np.uint8)
    arr[r <= 1.0] = (_clip(lum), _clip(lum), _clip(lum))
    return Image.fromarray(arr)


def brightness_pair(size_px, patch=128, patch_right=None, dark_ring=40, light_ring=220):
    """Two grey patches, one on a dark ring, one on light ring.
    Left patch uses `patch`, right uses `patch_right` (defaults to `patch`
    for backwards compatibility). Judge: same brightness (Y) or different (N)?"""
    if patch_right is None:
        patch_right = patch
    s = int(size_px)
    yy, xx = np.mgrid[0:s, 0:s].astype(float)
    c = (s - 1) / 2.0
    arr = np.full((s, s, 3), 128, dtype=np.uint8)
    for cx, ring, p in ((s * 0.25, dark_ring, patch), (s * 0.75, light_ring, patch_right)):
        rr = np.hypot(xx - cx, yy - c) / (s * 0.20)
        arr[rr <= 1.2] = (ring,) * 3
        arr[rr <= 0.6] = (_clip(p),) * 3
    return Image.fromarray(arr)


def vernier_bars(size_px, offset_px, lum=235, bg=BG):
    """Upper bar fixed, lower bar shifted horizontally by offset_px.
    Judge: lower bar LEFT or RIGHT of upper? (hyperacuity)."""
    s = int(size_px)
    arr = np.full((s, s, 3), bg, dtype=np.uint8)
    yy, xx = np.mgrid[0:s, 0:s]
    c = s // 2
    w, h, gap = max(3, s // 50), s // 3, max(4, s // 40)
    upper = (np.abs(xx - c) <= w // 2) & (yy >= c - gap - h) & (yy <= c - gap)
    off = int(round(offset_px))
    lower = (np.abs(xx - (c + off)) <= w // 2) & (yy >= c + gap) & (yy <= c + gap + h)
    arr[upper] = (_clip(lum),) * 3
    arr[lower] = (_clip(lum),) * 3
    return Image.fromarray(arr)


def size_pair(size_px, ref_diam, cmp_diam, lum=235, bg=BG):
    """Reference disc (left) fixed, comparison disc (right) adjustable."""
    s = int(size_px)
    arr = np.full((s, s, 3), bg, dtype=np.uint8)
    yy, xx = np.mgrid[0:s, 0:s].astype(float)
    c = (s - 1) / 2.0
    for cx, d in ((s * 0.30, ref_diam), (s * 0.70, cmp_diam)):
        arr[np.hypot(xx - cx, yy - c) <= d / 2.0] = (_clip(lum),) * 3
    return Image.fromarray(arr)


def noise_mask(size_px, bg=BG, amp=90, seed=None):
    """White-noise mask shown right after a brief Gabor.

    seed=None uses OS entropy and is NOT replayable; trial code must pass
    an explicit seed (foil_seed / mask_seed) to keep sessions replayable."""
    import warnings

    if seed is None:
        warnings.warn("noise_mask called without seed; output not replayable", stacklevel=2)
    rng = np.random.default_rng(seed)
    s = int(size_px)
    arr = rng.integers(bg - amp, bg + amp + 1, (s, s)).clip(0, 255).astype(np.uint8)
    rgb = np.stack([arr] * 3, axis=-1)
    return Image.fromarray(rgb)


def halftone_patch(size_px, check_px=2, lo=0, hi=255):
    """1px-ish black/white checkerboard averaging to mid-gray in linear light.

    Used for subjective gamma matching: beside a solid gray patch, the
    match point estimates the display gamma (no photometer needed).
    lo/hi set the checker extremes; mean((lo+hi)/2) is the linear-light
    reference the solid patch is matched against."""
    s = int(size_px)
    check_px = max(1, int(check_px))
    yy, xx = np.mgrid[0:s, 0:s]
    on = ((xx // check_px) + (yy // check_px)) % 2 == 0
    arr = np.where(on, hi, lo).astype(np.uint8)
    return Image.fromarray(np.stack([arr] * 3, axis=-1))


def match_pair(total_w_px, patch_px, solid_level, check_px=2):
    """Side-by-side halftone reference (left) + adjustable solid (right).

    total_w_px is legacy and unused (canvas sizes from patch_px); kept so
    existing callers passing it positionally keep working.
    The halftone side is always a 0/255 checkerboard (one reference); callers
    vary the solid starting level across repetitions to reduce anchoring bias.
    """
    from PIL import Image as _I

    left = halftone_patch(patch_px, check_px=check_px)
    right = solid_patch(patch_px, (_clip(solid_level),) * 3)
    gap = max(8, patch_px // 8)
    canvas = _I.new("RGB", (patch_px * 2 + gap, patch_px), (128, 128, 128))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (patch_px + gap, 0))
    return canvas


DARK_STEPS = (2, 4, 6, 8, 12, 16, 24, 32, 48)
LIGHT_STEPS = (253, 251, 249, 247, 243, 239, 231, 223, 207)


def step_row(patch_px, levels, bg, n_cols=9):
    """Row of `levels` gray patches on `bg` for black/white visibility."""
    from PIL import Image as _I

    patch_px, n_cols = int(patch_px), int(n_cols)
    gap = max(6, patch_px // 6)
    w = n_cols * patch_px + (n_cols - 1) * gap
    canvas = _I.new("RGB", (w, patch_px), (bg, bg, bg))
    for i, lv in enumerate(list(levels)[:n_cols]):
        canvas.paste(solid_patch(patch_px, (_clip(lv),) * 3), (i * (patch_px + gap), 0))
    return canvas
