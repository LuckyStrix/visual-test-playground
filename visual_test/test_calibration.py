"""Headless checks for display calibration (no Tk needed)."""
import json

import pytest

from . import calwizard as W
from .calibration import (DisplayProfile, gamma_from_halftone_match,
                          measure_refresh_hz, pooling_flags,
                          summarize_frame_intervals)
from .datalogger import DataLogger
from .stimuli import (DARK_STEPS, LIGHT_STEPS, halftone_patch, match_pair,
                      step_row)


def test_gamma_match_known_values():
    assert gamma_from_halftone_match(186) == pytest.approx(2.2, abs=0.05)
    assert gamma_from_halftone_match(128) == pytest.approx(1.0, abs=0.05)
    with pytest.raises(ValueError):
        gamma_from_halftone_match(0)
    with pytest.raises(ValueError):
        gamma_from_halftone_match(255)


def test_median_gamma_and_level_steps():
    assert W.median_gamma([186, 186, 186]) == pytest.approx(2.2, abs=0.05)
    assert W.adjust_level(128, 'Up') == 129
    assert W.adjust_level(128, 'Right') == 138
    assert W.adjust_level(5, 'Left') == W.SOLID_MIN
    assert W.adjust_level(250, 'Right') == W.SOLID_MAX
    assert W.adjust_level(128, 'Return') == 128


def test_dimmest_step_mapping():
    assert W.dimmest_visible_step('0', DARK_STEPS) is None
    assert W.dimmest_visible_step('1', DARK_STEPS) == DARK_STEPS[-1]
    assert W.dimmest_visible_step('9', DARK_STEPS) == DARK_STEPS[0]
    assert W.dimmest_visible_step('2', LIGHT_STEPS) == LIGHT_STEPS[-2]
    with pytest.raises(ValueError):
        W.parse_count_key('10')


def test_refresh_summary_flags_dropped_frames():
    iv = [16.7] * 50 + [50.0] * 5
    s = summarize_frame_intervals(iv, 60.0)
    assert s['p50'] == pytest.approx(16.7, abs=0.1)
    assert s['missed_pct'] == pytest.approx(9.1, abs=0.5)
    empty = summarize_frame_intervals([])
    assert empty['n_frames'] == 0 and empty['p50'] is None


def test_measure_refresh_counts_frames():
    state = {'n': 0}

    def upd():
        state['n'] += 1

    ticks = iter([i * 0.0167 for i in range(200)])

    import time as _t
    real = _t.perf_counter
    _t.perf_counter = lambda: next(ticks)
    try:
        hz, iv = measure_refresh_hz(upd, lambda: True, n_frames=20)
    finally:
        _t.perf_counter = real
    assert hz == pytest.approx(60.0, abs=1.0)
    assert len(iv) == 19
    with pytest.raises(RuntimeError):
        measure_refresh_hz(lambda: None, lambda: False, n_frames=120)


def test_profile_meta_and_comparability():
    a = DisplayProfile(gamma_estimate=2.2, refresh_hz=60.0, ambient='dim room',
                       black_step_visible=3, white_step_visible=2)
    meta = a.as_meta()
    assert meta['display_gamma_estimate'] == 2.2
    assert meta['display_refresh_hz'] == 60.0
    b = DisplayProfile(gamma_estimate=1.6, refresh_hz=144.0, ambient='office',
                       black_step_visible=5, white_step_visible=2)
    flags = a.comparability(b)
    assert any('gamma' in f for f in flags)
    assert any('refresh' in f for f in flags)
    assert a.comparability(DisplayProfile(**{k: v for k, v in
        {'gamma_estimate': 2.2, 'refresh_hz': 60.0, 'ambient': 'dim room',
         'black_step_visible': 3, 'white_step_visible': 2}.items()})) == ['comparable']
    assert a.comparability(None) != ['comparable']


def test_profile_persists_in_session_json(tmp_path):
    lg = DataLogger('CAL', data_dir=str(tmp_path))
    p = DisplayProfile(gamma_estimate=2.2, refresh_hz=60.0, ambient='dim room',
                       brightness_pct=80, night_mode_off=True)
    lg.meta.update(display_ppd=43.0, **p.as_meta())
    lg.log_trial(test='t', trial=1, level=0.0, correct=True)
    lg.end_test(test='t', threshold_log=0.0, n_trials=1)
    saved = json.load(open(lg.json_path))
    assert saved['meta']['display_gamma_estimate'] == 2.2
    assert saved['meta']['display_refresh_hz'] == 60.0


def test_calibration_stimuli_render():
    h = halftone_patch(64, check_px=2)
    assert h.size == (64, 64)
    px = h.load()
    assert px[0, 0] != px[2, 0]
    m = match_pair(0, 64, 128)
    assert m.size[0] > 64
    r = step_row(24, DARK_STEPS, 0)
    assert r.size[0] > 24


class _C:
    img = None

    def __init__(self, w=800, h=600):
        self._w, self._h = w, h

    def delete(self, *a, **k):
        pass

    def create_text(self, *a, **k):
        pass

    def create_image(self, *a, **k):
        pass

    def winfo_width(self):
        return self._w

    def winfo_height(self):
        return self._h


class _W:
    def update(self):
        pass

    def winfo_exists(self):
        return True


def test_comparability_flags_nightmode_and_brightness():
    a = DisplayProfile(gamma_estimate=2.2, refresh_hz=60.0, ambient='dim room',
                       black_step_visible=3, white_step_visible=2,
                       night_mode_off=True, brightness_pct=100)
    b = DisplayProfile(gamma_estimate=2.2, refresh_hz=60.0, ambient='dim room',
                       black_step_visible=3, white_step_visible=2,
                       night_mode_off=False, brightness_pct=50)
    flags = a.comparability(b)
    assert any('night-mode' in f for f in flags)
    assert any('brightness' in f for f in flags)
    assert a.comparability(a) == ['comparable']


def test_from_meta_roundtrip():
    p = DisplayProfile(gamma_estimate=2.2, refresh_hz=60.0, ambient='dim room',
                       brightness_pct=80, night_mode_off=True)
    q = DisplayProfile.from_meta(p.as_meta())
    assert q.gamma_estimate == 2.2
    assert q.brightness_pct == 80
    assert q.night_mode_off is True
    assert DisplayProfile.from_meta({}).summary() == 'not calibrated'


def test_pooling_flags_skips_comparable():
    ref = DisplayProfile(gamma_estimate=2.2, refresh_hz=60.0, ambient='dim room')
    same = DisplayProfile(gamma_estimate=2.2, refresh_hz=60.0, ambient='dim room')
    diff = DisplayProfile(gamma_estimate=1.6, refresh_hz=60.0, ambient='office')
    flags = pooling_flags(ref, {'same.json': same, 'diff.json': diff})
    assert 'same.json' not in flags
    assert 'diff.json' in flags
    assert pooling_flags(ref, {'raw.json': {'display_gamma_estimate': 1.0}}) != {}


def test_wizard_stages_headless(monkeypatch):
    from .calibration import DisplayProfile
    p = DisplayProfile()
    monkeypatch.setattr(W, 'pil_to_tk', lambda img: object())
    monkeypatch.setattr(W, 'center', lambda c: (400, 300))
    monkeypatch.setattr(W, 'wait_ms', lambda *a, **k: 0.0)
    monkeypatch.setattr(W, 'wait_dismiss', lambda *a, **k: None)
    monkeypatch.setattr(W, 'measure_refresh_hz', lambda *a, **k: (60.0, [16.7] * 119))
    keys = ['Up', 'Return'] * 3 + ['1', '2']
    monkeypatch.setattr(W, 'get_key', lambda w, valid, **k: (keys.pop(0), 0.1))
    out = W.run_wizard(_C(), _W(), p)
    assert out.refresh_hz == 60.0
    assert out.gamma_matched_level == 129
    assert out.gamma_estimate == pytest.approx(W.median_gamma([107, 129, 151]))
    assert out.black_step_visible == DARK_STEPS[-1]
    assert out.white_step_visible == LIGHT_STEPS[-2]
