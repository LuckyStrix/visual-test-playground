import numpy as np
import pytest

from .analysis import fit_weibull, plot_psychometric, plot_staircase
from .calibration import compute_geometry, nyquist_ok


def test_fit_weibull_recovers_threshold():
    rng = np.random.default_rng(0)
    levels = np.repeat([0.05, 0.1, 0.2, 0.4, 0.8], 20)
    p = 0.5 + 0.48 * (1 - np.exp(-((levels / 0.25) ** 2.5)))
    correct = (rng.random(len(levels)) < p).astype(float)
    fit = fit_weibull(levels, correct, guess=0.5)
    assert fit['alpha'] == pytest.approx(0.25, abs=0.15)
    assert len(fit['xs']) == 5


def test_fit_weibull_log_levels():
    rng = np.random.default_rng(1)
    log_levels = np.repeat([-1.3, -1.0, -0.7, -0.4], 25)
    lin = 10.0 ** log_levels
    p = 0.5 + 0.48 * (1 - np.exp(-((lin / 0.1) ** 2.0)))
    correct = (rng.random(len(lin)) < p).astype(float)
    fit = fit_weibull(log_levels, correct, guess=0.5, log_levels=True)
    assert fit['alpha'] == pytest.approx(0.1, rel=1.0)


def test_fit_weibull_empty_and_nan():
    bad = fit_weibull([], [])
    assert np.isnan(bad['alpha'])
    with pytest.raises(ValueError, match="no data points"):
        plot_psychometric(bad)
    bad2 = {'alpha': float('nan'), 'beta': 2.0, 'guess': 0.5, 'lapse': 0.02,
            'xs': [0.1, 0.2], 'ys': [0.6, 0.8]}
    with pytest.raises(ValueError, match="no valid threshold"):
        plot_psychometric(bad2)


def test_plot_staircase_uses_trial_indices(tmp_path):
    path = plot_staircase([0, 0, -0.5, -0.5, 0], [0, -0.5],
                          reversal_trials=[3, 5],
                          path=str(tmp_path / 's.png'))
    assert path.endswith('s.png')


def test_compute_geometry_sane():
    geo = compute_geometry(1920, 1080, 24.0, 60.0)
    assert 30 < geo.ppd < 80
    assert nyquist_ok(2.0, geo.ppd)
    assert not nyquist_ok(geo.ppd, geo.ppd)
    assert geo.deg_to_px(1.0) == pytest.approx(geo.ppd)


def test_compute_geometry_rejects_bad():
    with pytest.raises(ValueError):
        compute_geometry(0, 1080, 24.0, 60.0)
    with pytest.raises(ValueError):
        compute_geometry(1920, 1080, -1, 60.0)
    with pytest.raises(ValueError):
        compute_geometry(1920, 1080, 24.0, 0)
