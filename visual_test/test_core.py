"""Headless verification for test classes (no display needed)."""
import pytest

from . import main as M
from . import tests as T
from .datalogger import DataLogger


class DummyCanvas:
    def __init__(self, w=800, h=600):
        self._w, self._h = w, h
    def delete(self, *a, **k): pass
    def create_line(self, *a, **k): pass
    def create_text(self, *a, **k): pass
    def create_image(self, *a, **k): pass
    def update_idletasks(self): pass
    def winfo_width(self): return self._w
    def winfo_height(self): return self._h
    def bind(self, *a, **k): pass
    def unbind(self, *a, **k): pass
    def update(self): pass


class DummyWin:
    def update(self): pass
    def bind(self, *a, **k): pass
    def unbind(self, *a, **k): pass
    def focus_force(self): pass
    def winfo_exists(self): return True


@pytest.fixture(autouse=True)
def headless(monkeypatch):
    monkeypatch.setattr(T, 'show_img', lambda *a, **k: None)
    monkeypatch.setattr(T, 'show_img_at', lambda *a, **k: None)
    monkeypatch.setattr(T, 'feedback', lambda *a, **k: None)
    monkeypatch.setattr(T, 'wait_ms', lambda *a, **k: 50.0)
    monkeypatch.setattr(T, 'wait_dismiss', lambda *a, **k: None)
    monkeypatch.setattr(T, 'center', lambda c: (400, 300))


class ScriptedRng:
    """Deterministic stand-in for random.Random: draws from scripted lists."""

    def __init__(self, choices=None, uniforms=None, shuffles=True, seed=123):
        self.choices = list(choices or [])
        self.uniforms = list(uniforms or [])
        self.shuffles = shuffles
        self.seed = seed

    def choice(self, seq):
        if self.choices:
            return self.choices.pop(0)
        return seq[0]

    def uniform(self, a, b):
        if self.uniforms:
            return self.uniforms.pop(0)
        return (a + b) / 2

    def shuffle(self, seq):
        if self.shuffles:
            seq.reverse()

    def randrange(self, n):
        return self.seed % n


class ScriptedNpRng:
    """Deterministic stand-in for numpy Generator.random()."""

    def __init__(self, vals):
        self.vals = list(vals)

    def random(self, *a, **k):
        if self.vals:
            return self.vals.pop(0)
        return 0.5


def drive_seed(t, choices=None, np_vals=None, uniforms=None):
    t.rng = ScriptedRng(choices=choices, uniforms=uniforms)
    if hasattr(t, 'np_rng'):
        t.np_rng = ScriptedNpRng(np_vals if np_vals is not None else [0.5])
    return t


def sp(s, mn, mx):
    return dict(start_val=s, step_sizes=[0.3, 0.2, 0.1],
                n_reversals=4, min_val=mn, max_val=mx, rule='3D1U')


def _row(cls, kw, keys, np_val):
    return (cls, kw, keys, np_val)


STAIR_SUITE = [
    _row(T.ContrastDetection2IFC, dict(name='C', ppd=43.0,
                                       staircase_params=sp(-1.0, -3.0, 0.0)), ['1', '2'], None),
    _row(T.Acuity4AFC, dict(name='A', ppd=43.0,
                             staircase_params=sp(0.3, -0.2, 1.0)),
         ['Up', 'Right', 'Down', 'Left'], None),
    _row(T.ColorDiscrimination2IFC, dict(name='CD', ppd=43.0,
                                         staircase_params=sp(1.3, 0.3, 2.0)), ['1', '2'], None),
    _row(T.StaticContrast, dict(name='SC', ppd=43.0,
                                staircase_params=sp(-1.0, -3.0, 0.0)), ['y', 'n'], 0.1),
    _row(T.StaticColorBullseye, dict(name='SB', ppd=43.0,
                                     staircase_params=sp(1.5, 0.5, 2.0)), ['r', 'b'], 0.9),
    _row(T.CollinearJudgment, dict(name='CJ', ppd=43.0,
                                   staircase_params=sp(-1.0, -3.0, 0.0)), ['y', 'n'], 0.3),
    _row(T.BrightnessMatch, dict(name='BM', ppd=43.0,
                                 staircase_params=sp(1.0, 0.0, 1.8)), ['y', 'n'], 0.7),
    _row(T.VernierJudgment, dict(name='V', ppd=43.0,
                                 staircase_params=sp(-1.3, -2.5, 0.0)), ['Left', 'Right'], None),
    _row(T.MaskedGabor, dict(name='M', ppd=43.0,
                             staircase_params=sp(-0.5, -3.0, 0.0)), ['y', 'n'], 0.1),
]


@pytest.mark.parametrize("cls,kw,keys,np_val", STAIR_SUITE,
                         ids=[c.__name__ for c, _, _, _ in STAIR_SUITE])
def test_staircase_classes_headless(tmp_path, monkeypatch, cls, kw, keys, np_val):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(cls(logger=lg, n_trials=4, practice_trials=1, seed=7, **kw),
                   np_vals=[np_val] * 60 if np_val is not None else [0.5] * 60)
    pool = list(keys) * 40
    monkeypatch.setattr(T, 'get_key',
                        lambda w, valid, **k: (pool.pop(0) if pool else valid[0], 0.25))
    th, levels, corrects, reversals = t.run_gui(DummyCanvas(), DummyWin())
    assert len(levels) == 4
    assert len(corrects) == 4
    assert lg.tests[-1]['seed'] == 7


def test_truncation_flagged(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(T.ContrastDetection2IFC('C', lg, ppd=43.0,
                                           staircase_params=sp(-1.0, -3.0, 0.0),
                                           n_trials=4, practice_trials=0, seed=3),
                   choices=[True] * 20, np_vals=[0.5] * 20)
    monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('1', 0.25))
    t.run_gui(DummyCanvas(), DummyWin())
    assert lg.tests[-1]['truncated'] is True
    assert lg.tests[-1]['ppd'] == 43.0
    assert lg.tests[-1]['rule'] == '3D1U'


def test_catch_trials_excluded_from_staircase(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(T.StaticContrast('SC', lg, ppd=43.0,
                                    staircase_params=sp(-1.0, -3.0, 0.0),
                                    n_trials=4, practice_trials=0, seed=5),
                   np_vals=[0.1, 0.9] * 20)
    monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('y', 0.25))
    th, levels, corrects, reversals = t.run_gui(DummyCanvas(), DummyWin())
    assert len(levels) == 4
    assert lg.tests[-1]['n_catch'] >= 1
    assert all(c == '' or c is True or c is False for c in [r.get('correct') for r in lg.trials])
    catches = [r for r in lg.trials if r.get('catch') in (True, 'True')]
    assert all(r['correct'] == '' for r in catches)


def test_subitizing_balanced(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    sub = T.Subitizing('S', lg, n_trials=18)
    monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('3', 0.2))
    sub.run_gui(DummyCanvas(), DummyWin())
    counts = [r['n_dots'] for r in lg.trials]
    assert sorted(counts) == sorted((list(range(1, 10)) * 2))


def test_sizematch(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    sm = T.SizeMatch('SM', lg, n_trials=2, seed=9)
    keys = ['Up', 'Return', 'Down', 'Return', 'Return']
    monkeypatch.setattr(T, 'get_key',
                        lambda w, valid, **k: (keys.pop(0) if keys else valid[0], 0.1))
    bias, biases = sm.run_gui(DummyCanvas(), DummyWin())
    assert len(biases) == 2


def test_same_seed_reproduces_trial_sequence(tmp_path, monkeypatch):
    def run(seed):
        lg = DataLogger('TEST', data_dir=str(tmp_path))
        t = T.CollinearJudgment('CJ', lg, ppd=43.0,
                                staircase_params=sp(-1.0, -3.0, 0.0),
                                n_trials=6, practice_trials=0, seed=seed)
        monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('y', 0.25))
        t.run_gui(DummyCanvas(), DummyWin())
        return [(r['offset_px'], r.get('catch')) for r in lg.trials]
    assert run(42) == run(42)
    assert run(42) != run(43)


def test_anticipatory_rt_retries_and_flags(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    rt = T.StaticReactionTime('RT', lg, n_trials=1, ppd=43.0, seed=1)
    seq = iter([0.05, 0.30])
    monkeypatch.setattr(T, 'await_space', lambda w, t0, **k: next(seq))
    med, rts, misses, fas = rt.run_gui(DummyCanvas(), DummyWin())
    assert fas >= 1
    assert any(r.get('anticipatory') in (True, 'True') for r in lg.trials)
    assert rts and rts[0] >= T.MIN_RT_S


def test_dismiss_does_not_abort(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(T.VernierJudgment('V', lg, ppd=43.0,
                                     staircase_params=sp(-1.3, -2.5, 0.0),
                                     n_trials=2, practice_trials=0, seed=2),
                   np_vals=[0.6, 0.4, 0.6, 0.4])
    monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('Left', 0.2))
    out = t.run_gui(DummyCanvas(), DummyWin())
    assert len(out[1]) == 2


def test_practice_trials_logged(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(T.ContrastDetection2IFC('C', lg, ppd=43.0,
                                           staircase_params=sp(-1.0, -3.0, 0.0),
                                           n_trials=2, practice_trials=2, seed=3),
                   choices=[True] * 20, np_vals=[0.5] * 20)
    monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('1', 0.25))
    th, levels, corrects, reversals = t.run_gui(DummyCanvas(), DummyWin())
    assert len(levels) == 2
    practice_rows = [r for r in lg.trials if str(r.get('practice')) in ('True', '1')]
    assert len(practice_rows) == 2
    assert lg.tests[-1]['n_practice'] == 2


def test_bullseye_reports_bias(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(T.StaticColorBullseye('SB', lg, ppd=43.0,
                                         staircase_params=sp(1.5, 0.5, 2.0),
                                         n_trials=4, practice_trials=0, seed=7),
                   np_vals=[0.9, 0.1, 0.2, 0.05] * 20)
    monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('r', 0.25))
    t.run_gui(DummyCanvas(), DummyWin())
    summary = lg.tests[-1]
    assert 'hit_rate' in summary and 'fa_rate' in summary and 'd_prime' in summary


def test_abort_records_partial_summary(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(T.Subitizing('S', lg, n_trials=6, seed=9))
    calls = {'n': 0}

    def flaky(w, valid, **k):
        calls['n'] += 1
        if calls['n'] > 2:
            raise T.QuitExperiment("Participant pressed Escape")
        return ('3', 0.2)
    monkeypatch.setattr(T, 'get_key', flaky)
    import pytest as _pt
    with _pt.raises(T.QuitExperiment):
        t.run_gui(DummyCanvas(), DummyWin())
    assert lg.tests and lg.tests[-1].get('aborted') is True
    assert len(lg.trials) == 2


def test_vernier_clipping_flagged(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(T.VernierJudgment('V', lg, ppd=43.0,
                                     staircase_params=sp(-2.5, -2.5, 0.0),
                                     n_trials=4, practice_trials=0, seed=2),
                   np_vals=[0.6, 0.4, 0.6, 0.4])
    monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('Left', 0.2))
    t.run_gui(DummyCanvas(), DummyWin())
    assert lg.tests[-1]['clipped_levels'] is True
    assert any(r.get('offset_clipped') in (True, 'True') for r in lg.trials)


def test_dprime_uses_loglinear_correction():
    s = T.YesNoStats()
    for _ in range(10):
        s.note(True, True)
    for _ in range(10):
        s.note(False, False)
    summ = s.summary()
    assert summ['hit_rate'] == 1.0
    assert summ['fa_rate'] == 0.0
    import math
    assert math.isfinite(summ['d_prime'])


def test_staircase_summary_includes_reversal_sd(tmp_path, monkeypatch):
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(T.ContrastDetection2IFC('C', lg, ppd=43.0,
                                           staircase_params=sp(-1.0, -3.0, 0.0),
                                           n_trials=6, practice_trials=0, seed=3),
                   choices=[True] * 20, np_vals=[0.5] * 20)
    monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('1', 0.25))
    t.run_gui(DummyCanvas(), DummyWin())
    assert 'reversal_sd' in lg.tests[-1]


def test_gamma_starts_vary_per_reference(monkeypatch):
    from . import calwizard as Wmod
    from .calibration import DisplayProfile, HALFTONE_LEVELS
    monkeypatch.setattr(Wmod, 'pil_to_tk', lambda img: object())
    monkeypatch.setattr(Wmod, 'center', lambda c: (400, 300))
    keys = ['Return'] * 3
    monkeypatch.setattr(Wmod, 'get_key', lambda w, valid, **k: (keys.pop(0), 0.1))
    orig = Wmod.match_pair
    starts = []

    def spy(total, patch_px, level, **k):
        starts.append(level)
        return orig(total, patch_px, level, **k)
    monkeypatch.setattr(Wmod, 'match_pair', spy)
    Wmod.stage_gamma(DummyCanvas(), DummyWin(), DisplayProfile())
    assert starts == [min(max(int(round(r)), 1), 254) for r in HALFTONE_LEVELS]
    assert len(set(starts)) == 3


def test_session_registry_consistent():
    kinds = [v for _, v in M.TEST_ORDER]
    assert len(kinds) == len(set(kinds))
    assert set(kinds) == set(M.INSTR)
    for k in kinds:
        assert k in M.STAIR_DEFAULTS or k in M.FIXED_TRIAL_KINDS


def test_json_written_per_trial(tmp_path, monkeypatch):
    import json
    lg = DataLogger('TEST', data_dir=str(tmp_path))
    t = drive_seed(T.VernierJudgment('V', lg, ppd=43.0,
                                     staircase_params=sp(-1.3, -2.5, 0.0),
                                     n_trials=2, practice_trials=0, seed=2),
                   np_vals=[0.6, 0.4, 0.6, 0.4])
    monkeypatch.setattr(T, 'get_key', lambda w, valid, **k: ('Left', 0.2))
    t.run_gui(DummyCanvas(), DummyWin())
    saved = json.load(open(lg.json_path))
    assert saved.get('schema') == 2
    assert saved.get('trials_logged') == len(lg.trials)
