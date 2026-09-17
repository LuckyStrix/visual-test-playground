"""Deterministic convergence + validation checks for Staircase."""
import math

import pytest

from .staircase import Staircase


def test_converges_near_target():
    thr_true = -1.0
    stair = Staircase(start_val=-0.2, step_sizes=[0.4, 0.2, 0.1, 0.05], n_reversals=6,
                      min_val=-4.0, max_val=0.0, rule='3D1U', n_trials_max=200)
    while True:
        p = 1.0 / (1.0 + math.exp(-8.0 * (stair.current - thr_true)))
        _, done = stair.respond(p > 0.5)
        if done:
            break
    assert abs(stair.threshold() - thr_true) < 0.4


def test_no_false_reversals_at_bound():
    s = Staircase(-1.0, [0.3], n_reversals=2, n_trials_max=5, min_val=-1.0, max_val=0.0)
    for _ in range(10):
        s.respond(True)
    assert s.reversals == []


@pytest.mark.parametrize("kwargs", [
    dict(rule='9D9U'),
    dict(step_sizes=[]),
    dict(step_sizes=[0.1, 0, -0.1]),
    dict(n_reversals=0),
    dict(n_trials_max=0),
])
def test_rejects_bad_params(kwargs):
    base = dict(start_val=0, step_sizes=[0.1])
    base.update(kwargs)
    with pytest.raises(ValueError):
        Staircase(**base)


def test_start_clamped_to_bounds():
    with pytest.warns(UserWarning, match="clamped"):
        s = Staircase(5.0, [0.3], min_val=-3, max_val=0.0)
    assert s.current == 0.0


def test_reset_clears_state():
    s = Staircase(0.0, [0.3], n_reversals=8, n_trials_max=20)
    s.respond(True)
    s.respond(False)
    s.reset()
    assert s.trial_num == 0 and s.reversals == [] and s.current == s.start_val


def test_reversal_trials_recorded():
    s = Staircase(0.0, [0.5, 0.25], n_reversals=8, n_trials_max=30, min_val=-3, max_val=3)
    for r in ([True] * 3 + [False] * 3) * 4:
        _, done = s.respond(r)
        if done:
            break
    assert len(s.reversal_trials) == len(s.reversals)
    assert all(1 <= t <= s.trial_num for t in s.reversal_trials)
