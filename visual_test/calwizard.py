"""Fullscreen display-calibration wizard (subjective, no photometer).

Stages: measured refresh rate, halftone gamma match at 3 levels, black-step
and white-step visibility counts. Mutates the passed DisplayProfile so an
abort keeps partial results. Settings like brightness/ambient are collected
in the main-window dialog afterwards, not here."""

try:
    from .calibration import (
        HALFTONE_LEVELS,
        DisplayProfile,
        gamma_from_halftone_match,
        measure_refresh_hz,
        summarize_frame_intervals,
    )
    from .stimuli import DARK_STEPS, LIGHT_STEPS, match_pair, step_row
    from .tests import center, get_key, pil_to_tk, wait_dismiss, wait_ms
except ImportError:
    from calibration import (
        HALFTONE_LEVELS,
        DisplayProfile,
        gamma_from_halftone_match,
        measure_refresh_hz,
        summarize_frame_intervals,
    )
    from stimuli import DARK_STEPS, LIGHT_STEPS, match_pair, step_row
    from tests import center, get_key, pil_to_tk, wait_dismiss, wait_ms

import statistics

SOLID_START = 128
SOLID_MIN = 1
SOLID_MAX = 254


def clamp_solid(v):
    return max(SOLID_MIN, min(SOLID_MAX, int(round(v))))


def adjust_level(level, key):
    if key == "Up":
        return clamp_solid(level + 1)
    if key == "Down":
        return clamp_solid(level - 1)
    if key == "Right":
        return clamp_solid(level + 10)
    if key == "Left":
        return clamp_solid(level - 10)
    return level


def median_gamma(matched_levels):
    gammas = [gamma_from_halftone_match(lv) for lv in matched_levels]
    return round(float(statistics.median(gammas)), 3)


def parse_count_key(key):
    try:
        k = int(key)
    except (TypeError, ValueError):
        raise ValueError("count must be an integer")
    if k < 0 or k > 9:
        raise ValueError("count must be 0..9")
    return k


def dimmest_visible_step(count, steps):
    k = parse_count_key(count)
    steps = list(steps)
    if k <= 0:
        return None
    if k >= len(steps):
        return int(steps[0])
    return int(steps[len(steps) - k])


def canvas_size(canvas, fallback=(800, 600)):
    try:
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w > 50 and h > 50:
            return w, h
    except Exception:
        pass
    return fallback


def show_centered(canvas, cx, cy, img):
    t = pil_to_tk(img)
    canvas.img = t
    canvas.create_image(cx, cy, image=t)


def stage_refresh(canvas, win, profile, n_frames=120):
    cx, cy = center(canvas)
    canvas.delete("all")
    canvas.create_text(
        cx,
        cy,
        text="⚡ VISOR TUNING 1/3 — sensing refresh...",
        fill="gold",
        font=("Arial", 18, "bold"),
    )
    win.update()
    try:
        hz, intervals = measure_refresh_hz(win.update, win.winfo_exists, n_frames=n_frames)
    except Exception as e:
        raise RuntimeError(f"Refresh measurement failed: {e}") from e
    if hz is None or not isinstance(hz, (int, float)) or hz <= 0:
        raise RuntimeError("Refresh measurement returned invalid Hz")
    summ = summarize_frame_intervals(intervals, hz)
    profile.refresh_hz = hz
    profile.refresh_n_frames = summ["n_frames"]
    profile.frame_interval_ms_p50 = summ["p50"]
    profile.frame_interval_ms_p95 = summ["p95"]
    profile.frame_jitter_ms = summ["jitter"]
    profile.missed_frames_pct = summ["missed_pct"]
    canvas.delete("all")
    canvas.create_text(
        cx, cy, text=f"⚡ Visor tuned: {hz} Hz", fill="gold", font=("Arial", 18, "bold")
    )
    win.update()
    wait_ms(win, 900)
    return hz


def stage_gamma(canvas, win, profile):
    w, h = canvas_size(canvas)
    patch_px = max(120, int(min(w, h) * 0.26))
    matched = []
    for i, ref in enumerate(HALFTONE_LEVELS):
        level = clamp_solid(ref)
        while True:
            cx, cy = center(canvas)
            canvas.delete("all")
            show_centered(canvas, cx, cy - 40, match_pair(0, patch_px, level))
            canvas.create_text(
                cx,
                cy + patch_px // 2 + 60,
                fill="white",
                font=("Arial", 14),
                justify="center",
                text=(
                    "🎨 VISOR TUNING 2/3 — match the RIGHT patch to the halftone LEFT.\n"
                    f"Reference {i + 1}/{len(HALFTONE_LEVELS)} — start {ref}, now {level}\n"
                    "Hold still, squint if needed.\n"
                    "Up/Down = fine, Left/Right = coarse, Enter = match"
                ),
            )
            win.update()
            r, _ = get_key(win, ["Up", "Down", "Left", "Right", "Return"])
            if r == "Return":
                break
            level = adjust_level(level, r)
        matched.append(level)
    profile.gamma_matched_level = int(round(float(statistics.median(matched))))
    profile.gamma_estimate = median_gamma(matched)
    return matched


def stage_steps(canvas, win, profile):
    w, h = canvas_size(canvas)
    patch_px = max(24, int(min(w, h) * 0.075))
    cx, cy = center(canvas)
    canvas.delete("all")
    show_centered(canvas, cx, cy - 30, step_row(patch_px, DARK_STEPS, 0))
    canvas.create_text(
        cx,
        cy + 120,
        fill="white",
        font=("Arial", 14),
        justify="center",
        text=(
            "🌑 VISOR TUNING 3/3 — black steps on black: HOW MANY patches?\nPress 0-9 (Esc quits)"
        ),
    )
    win.update()
    r, _ = get_key(win, [str(i) for i in range(10)])
    profile.black_step_visible = dimmest_visible_step(r, DARK_STEPS)
    cx, cy = center(canvas)
    canvas.delete("all")
    show_centered(canvas, cx, cy - 30, step_row(patch_px, LIGHT_STEPS, 255))
    canvas.create_text(
        cx,
        cy + 120,
        fill="white",
        font=("Arial", 14),
        justify="center",
        text=(
            "⬜ VISOR TUNING 3/3 — white steps on white: HOW MANY patches?\nPress 0-9 (Esc quits)"
        ),
    )
    win.update()
    r, _ = get_key(win, [str(i) for i in range(10)])
    profile.white_step_visible = dimmest_visible_step(r, LIGHT_STEPS)
    return profile.black_step_visible, profile.white_step_visible


def run_wizard(canvas, win, profile=None, n_refresh_frames=120):
    if profile is None:
        profile = DisplayProfile()
    stage_refresh(canvas, win, profile, n_frames=n_refresh_frames)
    stage_gamma(canvas, win, profile)
    stage_steps(canvas, win, profile)
    cx, cy = center(canvas)
    canvas.delete("all")
    canvas.create_text(
        cx,
        cy,
        text=f"Display: {profile.summary()}\nPress any key (Esc dismisses)",
        fill="white",
        font=("Arial", 16),
        justify="center",
    )
    win.update()
    wait_dismiss(win)
    return profile
