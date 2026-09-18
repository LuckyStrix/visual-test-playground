"""Regression tests for audit-fix sweep: kind-suffixed plots, fixed-probe
parity + plots, export provenance, summary archive guard, all-miss RT flag,
norms size guard, avatar slots."""

import glob
import json
import os

import pytest

from . import tests as T
from .datalogger import DataLogger


class DummyCanvas:
    def delete(self, *a, **k):
        pass

    def create_line(self, *a, **k):
        pass

    def create_text(self, *a, **k):
        pass

    def create_image(self, *a, **k):
        pass

    def update_idletasks(self):
        pass

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600

    def update(self):
        pass


class DummyWin:
    def update(self):
        pass

    def bind(self, *a, **k):
        pass

    def unbind(self, *a, **k):
        pass

    def focus_force(self):
        pass

    def winfo_exists(self):
        return True


@pytest.fixture(autouse=True)
def headless(monkeypatch):
    monkeypatch.setattr(T, "show_img", lambda *a, **k: None)
    monkeypatch.setattr(T, "show_img_at", lambda *a, **k: None)
    monkeypatch.setattr(T, "feedback", lambda *a, **k: None)
    monkeypatch.setattr(T, "arcade_feedback", lambda *a, **k: (0, 0))
    monkeypatch.setattr(T, "arcade_toast", lambda *a, **k: None)
    monkeypatch.setattr(T, "wait_ms", lambda *a, **k: 50.0)
    monkeypatch.setattr(T, "wait_dismiss", lambda *a, **k: None)
    monkeypatch.setattr(T, "center", lambda c: (400, 300))


def _sp(s, mn, mx):
    return dict(
        start_val=s, step_sizes=[0.3, 0.2, 0.1], n_reversals=4, min_val=mn, max_val=mx,
        rule="3D1U",
    )


def test_staircase_plots_include_kind(tmp_path, monkeypatch):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    t = T.ContrastDetection2IFC(
        "C", lg, ppd=43.0, staircase_params=_sp(-1.0, -3.0, 0.0),
        n_trials=4, practice_trials=0, seed=7,
    )
    monkeypatch.setattr(T, "get_key", lambda w, valid, **k: ("1", 0.25))
    t.run_gui(DummyCanvas(), DummyWin())
    plots = glob.glob(os.path.join(str(tmp_path), "plots", "*.png"))
    assert any(p.endswith("_contrast_staircase.png") for p in plots)
    assert any(p.endswith("_contrast_psychometric.png") for p in plots)


def test_sizematch_parity_and_plot(tmp_path, monkeypatch):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    sm = T.SizeMatch("SM", lg, n_trials=2, seed=9)
    keys = ["Return", "Return", "Return"]
    monkeypatch.setattr(
        T, "get_key", lambda w, valid, **k: (keys.pop(0) if keys else valid[0], 0.1)
    )
    sm.run_gui(DummyCanvas(), DummyWin())
    s = lg.tests[-1]
    assert s["n_completed"] == 2
    assert s["n_practice"] == 0
    assert s["truncated"] is False
    assert glob.glob(os.path.join(str(tmp_path), "plots", "*_sizematch_fixed.png"))


def test_rt_parity_plot_and_all_miss_flag(tmp_path, monkeypatch):
    from . import results as R

    lg = DataLogger("TEST", data_dir=str(tmp_path))
    rt = T.StaticReactionTime("RT", lg, n_trials=2, ppd=43.0, seed=1)
    monkeypatch.setattr(T, "await_space", lambda w, t0, **k: 0.25)
    rt.run_gui(DummyCanvas(), DummyWin())
    s = lg.tests[-1]
    assert s["n_completed"] == 2
    assert s["n_practice"] == 0
    assert s["truncated"] is False
    assert glob.glob(os.path.join(str(tmp_path), "plots", "*_static_rt_fixed.png"))
    assert any("no hits" in f for f in R.flags_for({"median_rt_s": None}))


def test_export_provenance_and_summary_archive(tmp_path):
    from . import export as E

    sess = tmp_path / "sessions"
    sess.mkdir()
    doc = {
        "participant": "P",
        "session": "S",
        "meta": {
            "display_gamma_estimate": 2.2,
            "display_refresh_hz": 60.0,
            "display_ambient": "dim room",
            "display_brightness_pct": 100,
            "display_night_mode_off": True,
        },
        "tests": [
            {
                "test": "Contrast 2IFC",
                "kind": "contrast",
                "threshold_log": -1.0,
                "n_trials": 8,
                "ppd": 43.0,
                "seed": 7,
                "difficulty": "hard",
                "difficulty_adj": 1.0,
            }
        ],
    }
    (sess / "s.json").write_text(json.dumps(doc))
    rows = E.pooled_rows(str(sess))
    assert rows and rows[0]["display_gamma"] == 2.2
    assert rows[0]["difficulty"] == "hard"
    assert rows[0]["ppd"] == 43.0
    assert E.cmd_summary(str(sess)) == 0
    arch = tmp_path / "legacy_archive"
    arch.mkdir()
    (arch / "old.json").write_text(json.dumps(doc))
    assert len(E.pooled_rows(str(sess), include_archive=True)) == 2
    assert E.cmd_summary(str(sess), include_archive=True) == 0


def test_norms_size_guard(tmp_path, monkeypatch):
    from . import norms as N

    p = tmp_path / "s.json"
    p.write_text(json.dumps({"participant": "P", "session": "S", "tests": []}))
    monkeypatch.setattr("os.path.getsize", lambda q: 11 * 1024 * 1024)
    assert N.load_session(str(p)) is None


def test_avatar_all_slots(tmp_path, monkeypatch):
    from . import assets as A

    monkeypatch.setattr(A, "asset_dir", lambda: str(tmp_path))
    A.ensure_assets()
    for i in range(len(A._AVATAR_COLORS)):
        assert A.avatar_path(i) is not None
