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
        start_val=s,
        step_sizes=[0.3, 0.2, 0.1],
        n_reversals=4,
        min_val=mn,
        max_val=mx,
        rule="3D1U",
    )


def test_staircase_plots_include_kind(tmp_path, monkeypatch):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    t = T.ContrastDetection2IFC(
        "C",
        lg,
        ppd=43.0,
        staircase_params=_sp(-1.0, -3.0, 0.0),
        n_trials=4,
        practice_trials=0,
        seed=7,
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


class _ShimNp:
    def __init__(self, vals=None, ints=None):
        self.vals = list(vals if vals is not None else [0.5])
        self.ints = list(ints if ints is not None else [7])

    def random(self, *a, **k):
        return self.vals.pop(0) if self.vals else 0.5

    def integers(self, high, *a, **k):
        return (self.ints.pop(0) if self.ints else 7) % high


def _bullseye(tmp_path, vals):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    t = T.StaticColorBullseye(
        "SB",
        lg,
        ppd=43.0,
        staircase_params=_sp(1.5, 0.5, 2.0),
        n_trials=2,
        practice_trials=0,
        seed=7,
    )
    t.np_rng = _ShimNp(vals=vals)
    return t


def test_bullseye_catch_ok_is_none(tmp_path, monkeypatch):
    t = _bullseye(tmp_path, [0.05])
    monkeypatch.setattr(T, "get_key", lambda w, valid, **k: ("r", 0.2))
    ok, _rt, extra = t.trial(DummyCanvas(), DummyWin(), 1.5, True)
    assert extra["catch"] is True
    assert ok is None


def test_static_color_logs_capped_delta(tmp_path, monkeypatch):
    t = _bullseye(tmp_path, [0.5, 0.5])
    monkeypatch.setattr(T, "get_key", lambda w, valid, **k: ("r", 0.2))
    ok, _rt, extra = t.trial(DummyCanvas(), DummyWin(), 2.0, True)
    assert extra["catch"] is False
    assert extra["delta"] == 45.0
    assert ok is not None


def test_masked_gabor_mask_seeded_and_logged(tmp_path, monkeypatch):
    def run(seed):
        lg = DataLogger("TEST", data_dir=str(tmp_path))
        t = T.MaskedGabor(
            "M",
            lg,
            ppd=43.0,
            staircase_params=_sp(-0.5, -3.0, 0.0),
            n_trials=2,
            practice_trials=0,
            seed=seed,
        )
        monkeypatch.setattr(T, "get_key", lambda w, valid, **k: ("y", 0.25))
        return t.trial(DummyCanvas(), DummyWin(), -0.5, True)

    _ok1, _, ex1 = run(11)
    _ok2, _, ex2 = run(11)
    assert "mask_seed" in ex1
    assert ex1["mask_seed"] == ex2["mask_seed"]
    _, _, ex3 = run(12)
    assert ex3["mask_seed"] != ex1["mask_seed"]


def test_game_xp_clamped_at_max(tmp_path):
    from . import game as G

    p = G.profile_path("P1", str(tmp_path))
    with open(p, "w") as f:
        json.dump({"xp": G.MAX_STORED_XP - 50, "sessions": 1, "badges": [], "history": []}, f)
    cards = [
        {
            "value": 1.0,
            "display": "1%",
            "percentile": 95.0,
            "band": "Top 10%",
            "z": 2.0,
            "summary": {},
        }
    ]
    prof, gained, _, _ = G.add_session("P1", str(tmp_path), cards, session_id="s1")
    assert gained > 50
    assert prof["xp"] == G.MAX_STORED_XP
