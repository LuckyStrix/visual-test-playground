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


def test_practice_trial_keys(tmp_path):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    lg.log_trial(
        test="t",
        trial="p1",
        practice_trial=1,
        level=-1.0,
        correct=True,
        rt_s=0.3,
        practice=True,
    )
    rows = list(__import__("csv").DictReader(open(lg.csv_path)))
    assert rows[0]["trial"] == "p1"
    assert rows[0]["practice_trial"] == "1"


def test_rt_retries_dont_inflate_trial_no(tmp_path, monkeypatch):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    rt = T.StaticReactionTime("RT", lg, n_trials=2, ppd=43.0, seed=1)
    seq = iter([0.02, 0.30, 0.25])
    monkeypatch.setattr(T, "await_space", lambda w, t0, **k: next(seq))
    rt.run_gui(DummyCanvas(), DummyWin())
    s = lg.tests[-1]
    assert s["n_completed"] == 2
    assert s["n_completed"] <= s["n_trials"]
    assert s["n_attempts"] == 3
    assert s["n_retries"] == 1
    retries = [r for r in lg.trials if r.get("retry") in (True, "True")]
    assert len(retries) == 1


def test_base_abort_schema_parity(tmp_path, monkeypatch):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    t = T.ContrastDetection2IFC(
        "C",
        lg,
        ppd=43.0,
        staircase_params=_sp(-1.0, -3.0, 0.0),
        n_trials=4,
        practice_trials=0,
        seed=3,
    )
    calls = {"n": 0}

    def flaky(w, valid, **k):
        calls["n"] += 1
        if calls["n"] > 2:
            raise T.QuitExperiment("Participant pressed Escape")
        return ("1", 0.2)

    monkeypatch.setattr(T, "get_key", flaky)
    with pytest.raises(T.QuitExperiment):
        t.run_gui(DummyCanvas(), DummyWin())
    s = lg.tests[-1]
    assert s["aborted"] is True
    for key in (
        "rule",
        "target_p",
        "step_sizes",
        "threshold_n_discard",
        "truncated",
        "n_completed",
        "n_presented",
        "clipped_levels",
    ):
        assert key in s, key


def test_vernier_offset_logged_as_int(tmp_path, monkeypatch):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    t = T.VernierJudgment(
        "V",
        lg,
        ppd=43.0,
        staircase_params=_sp(-1.3, -2.5, 0.0),
        n_trials=2,
        practice_trials=0,
        seed=2,
    )
    monkeypatch.setattr(T, "get_key", lambda w, valid, **k: ("Left", 0.2))
    t.run_gui(DummyCanvas(), DummyWin())
    for r in lg.trials:
        assert isinstance(r["offset_px"], int)


def test_unidentified_sessions_each_earn_xp(tmp_path):
    from . import game as G

    def cards():
        return [
            {
                "value": 1.0,
                "display": "1%",
                "percentile": 80.0,
                "band": "Above average",
                "z": 0.5,
                "summary": {},
            }
        ]

    _, g1, _, _ = G.add_session("PX", str(tmp_path), cards(), session_id=None)
    _, g2, _, _ = G.add_session("PX", str(tmp_path), cards(), session_id=None)
    assert g1 > 0 and g2 > 0


def test_corrupt_profile_backed_up(tmp_path):
    from . import game as G

    p = G.profile_path("PX2", str(tmp_path))
    with open(p, "w") as f:
        f.write("{not json")
    with pytest.warns(UserWarning):
        prof = G.load_profile("PX2", str(tmp_path))
    assert prof["xp"] == 0
    assert os.path.exists(p + ".corrupt")


def test_json_failure_warns_not_silent(tmp_path):
    import visual_test.datalogger as DL

    lg = DataLogger("TEST", data_dir=str(tmp_path))
    lg.log_trial(test="t", trial=1, level=0.0, correct=True)

    def boom(*a, **k):
        raise OSError("disk full")

    old = DL.json.dump
    DL.json.dump = boom
    try:
        with pytest.warns(UserWarning, match="JSON snapshot failed"):
            lg.log_trial(test="t", trial=2, level=0.0, correct=True)
    finally:
        DL.json.dump = old


def test_gabor_rejects_bad_params():
    from . import calibration as C
    from . import stimuli as S

    with pytest.raises(ValueError):
        S.gabor_patch(0, 43.0, 2.0, 0.5)
    with pytest.raises(ValueError):
        S.gabor_patch(64, 43.0, 2.0, float("nan"))
    with pytest.raises(ValueError):
        S.gabor_patch(64, 0.0, 2.0, 0.5)
    with pytest.raises(ValueError):
        C.compute_geometry(1920, 1080, float("inf"), 60.0)
    with pytest.raises(ValueError):
        C.compute_geometry(1920, 1080, 24.0, float("nan"))


def test_report_warns_on_foreign_data_dir(tmp_path, capsys):
    from . import export as E

    sess = tmp_path / "sessions"
    sess.mkdir()
    doc = {
        "participant": "P",
        "session": "S",
        "tests": [{"test": "X", "kind": "contrast", "threshold_log": -1.0, "n_trials": 8}],
    }
    p = sess / "s.json"
    p.write_text(json.dumps(doc))
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert E.cmd_report(str(other), str(p)) == 0
    assert "ignoring --data-dir" in capsys.readouterr().err


def test_best_ranks_tie_safe():
    import inspect

    from . import main as M

    src = inspect.getsource(M.VisualTestApp.best_ranks)
    assert ".remove(v)" not in src


def test_full_battery_count_synced():
    from . import game as G
    from . import main as M

    assert G.FULL_BATTERY_N == len(M.TEST_ORDER)


def test_sizematch_abort_records_partial(tmp_path, monkeypatch):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    sm = T.SizeMatch("SM", lg, n_trials=4, seed=9)
    calls = {"n": 0}

    def flaky(w, valid, **k):
        calls["n"] += 1
        if calls["n"] > 1:
            raise T.QuitExperiment("Participant pressed Escape")
        return ("Return", 0.1)

    monkeypatch.setattr(T, "get_key", flaky)
    with pytest.raises(T.QuitExperiment):
        sm.run_gui(DummyCanvas(), DummyWin())
    s = lg.tests[-1]
    assert s["aborted"] is True
    assert s["n_completed"] == 1
    assert s["truncated"] is True


def test_rt_abort_records_partial(tmp_path, monkeypatch):
    lg = DataLogger("TEST", data_dir=str(tmp_path))
    rt = T.StaticReactionTime("RT", lg, n_trials=4, ppd=43.0, seed=1)
    monkeypatch.setattr(
        T, "await_space", lambda w, t0, **k: (_ for _ in ()).throw(T.QuitExperiment("esc"))
    )
    with pytest.raises(T.QuitExperiment):
        rt.run_gui(DummyCanvas(), DummyWin())
    s = lg.tests[-1]
    assert s["aborted"] is True
    assert s["truncated"] is True


def test_stimuli_smoke_and_determinism():
    from . import stimuli as S

    g1 = S.gabor_patch(64, 43.0, 2.0, 0.5)
    assert g1.size == (64, 64) and g1.mode == "RGB"
    assert S.blank_patch(32).size == (32, 32)
    assert S.landolt_c(64, 0).size == (64, 64)
    assert S.bullseye(64, (200, 128, 128), (56, 128, 128)).size == (64, 64)
    assert S.solid_patch(16, (1, 2, 3)).size == (16, 16)
    assert S.bright_disc(48).size == (48, 48)
    assert S.vernier_bars(96, 2.0).size == (96, 96)
    assert S.size_pair(200, 100.0, 110.0).size == (200, 200)
    c1, c2 = S.isoluminant_pair(10.0)
    assert c1 != c2
    n1 = S.noise_mask(32, seed=5)
    n2 = S.noise_mask(32, seed=5)
    assert n1.tobytes() == n2.tobytes()
    r1 = S.red_blue_pair(10.0, rng=__import__("numpy").random.default_rng(3))
    r2 = S.red_blue_pair(10.0, rng=__import__("numpy").random.default_rng(3))
    assert r1 == r2
    assert S.acuity_size_px(0.0, 43.0) > 0


def test_calibration_pure_fns():
    from . import calibration as C

    geo = C.compute_geometry(1920, 1080, 24.0, 60.0)
    assert geo.px_to_deg(geo.ppd) == pytest.approx(1.0)
    assert C.gamma_from_halftone_match(186) == pytest.approx(2.2, abs=0.05)
    s = C.summarize_frame_intervals([16.7] * 60, refresh_hz=60.0)
    assert s["n_frames"] == 61
    assert s["missed_pct"] == 0.0


def test_interpret_and_kind_of_direct():
    from . import norms as N
    from . import results as R

    card = {
        "kind": "contrast",
        "name": "Contrast 2IFC",
        "value": 10.0,
        "display": "10.0% contrast",
        "higher_better": False,
        "n": 6,
        "percentile": 50.0,
        "band": "Typical",
        "z": 0.0,
        "summary": {},
    }
    out = R.interpret(dict(card))
    assert out["title"] == "Contrast detection (2IFC)"
    assert out["disclaimer"].startswith("Experimental playground")
    assert N.kind_of("Contrast 2IFC") == "contrast"
    assert N.kind_of("Static Reaction Time") == "static_rt"


def test_export_cli_pooled_summary_report(tmp_path, capsys):
    from . import export as E

    sess = tmp_path / "s2"
    sess.mkdir()
    doc = {
        "participant": "P",
        "session": "S",
        "tests": [{"test": "X", "kind": "contrast", "threshold_log": -1.0, "n_trials": 8}],
    }
    p = sess / "s.json"
    p.write_text(json.dumps(doc))
    out = str(sess / "pooled.csv")
    assert E.main(["--data-dir", str(sess), "--pooled", out]) == 0
    assert os.path.exists(out)
    assert E.main(["--data-dir", str(sess), "--summary"]) == 0
    assert E.main(["--data-dir", str(sess), "--report", str(p)]) == 0
    assert E.main(["--data-dir", str(sess)]) == 2
    assert E.default_data_dir().endswith(os.path.join("visual_test", "data", "sessions"))
