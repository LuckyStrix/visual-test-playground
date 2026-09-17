"""Weibull psychometric fits + staircase plots (matplotlib, Agg)."""
import warnings
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.optimize import OptimizeWarning, curve_fit


def weibull(x, alpha, beta, gamma, lam):
    x = np.asarray(x, float)
    alpha = float(alpha)
    if not np.isfinite(alpha) or alpha <= 0:
        return np.full_like(x, np.nan, dtype=float)
    with np.errstate(invalid='ignore', divide='ignore'):
        return gamma + (1 - gamma - lam) * (1 - np.exp(-((x / alpha) ** beta)))


def fit_weibull(levels, correct, guess=0.5, lapse=0.02, log_levels=False):
    """Fit a Weibull psychometric function.

    Set log_levels=True when levels are log10 units (e.g. log contrast):
    fitting is done on 10**levels and the returned alpha/xs are in linear
    units. Default False fits levels as given. On failure returns
    alpha=median(binned linear levels).
    """
    levels = np.asarray(levels, float).ravel()
    correct = np.asarray(correct, float).ravel()
    if levels.size == 0 or correct.size == 0 or levels.shape != correct.shape:
        return {'alpha': float('nan'), 'beta': float('nan'),
                'guess': guess, 'lapse': lapse, 'xs': [], 'ys': []}
    if not np.all(np.isfinite(levels)):
        return {'alpha': float('nan'), 'beta': float('nan'),
                'guess': guess, 'lapse': lapse, 'xs': [], 'ys': []}
    lin = 10.0 ** levels if log_levels else levels
    ux = np.unique(lin)
    xm, ym, n = [], [], []
    for u in ux:
        m = lin == u
        xm.append(u)
        ym.append(correct[m].mean())
        n.append(m.sum())
    xm, ym = np.array(xm), np.array(ym)
    n = np.array(n, dtype=float)
    sigma = 1.0 / np.sqrt(np.maximum(n, 1))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', OptimizeWarning)
            popt, _ = curve_fit(lambda x, a, b: weibull(x, a, b, guess, lapse),
                                xm, ym, p0=[max(np.median(xm), 1e-3), 2.0],
                                bounds=([1e-4, 0.5], [np.inf, 8.0]), maxfev=5000,
                                sigma=sigma)
        return {'alpha': float(popt[0]), 'beta': float(popt[1]),
                'guess': guess, 'lapse': lapse, 'xs': xm.tolist(), 'ys': ym.tolist()}
    except Exception:
        med = float(np.median(xm))
        return {'alpha': med, 'beta': float('nan'),
                'guess': guess, 'lapse': lapse, 'xs': xm.tolist(), 'ys': ym.tolist()}


def plot_staircase(levels, reversals, reversal_trials=None, title='', path='staircase.png'):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(range(1, len(levels) + 1), levels, 'o-', ms=4)
    if reversal_trials is not None:
        for t in reversal_trials:
            if 1 <= t <= len(levels):
                ax.plot(t, levels[t - 1], 'ro', ms=7, mfc='none')
    else:
        used = [False] * len(levels)
        for r in reversals:
            idx = next((i for i, (v, u) in enumerate(zip(levels, used))
                        if not u and abs(v - r) < 1e-9), None)
            if idx is not None:
                used[idx] = True
                ax.plot(idx + 1, r, 'ro', ms=7, mfc='none')
    ax.set_xlabel('Trial')
    ax.set_ylabel('Level (log10 units)')
    ax.set_title(title)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def plot_psychometric(fit, title='', path='psychometric.png'):
    xs = np.array(fit['xs']); ys = np.array(fit['ys'])
    if xs.size == 0:
        raise ValueError("fit contains no data points")
    alpha = fit.get('alpha', float('nan'))
    if not np.isfinite(alpha):
        raise ValueError("fit has no valid threshold (alpha is NaN)")
    xmin = float(np.min(xs))
    xmax = float(np.max(xs))
    if not np.isfinite(xmin) or not np.isfinite(xmax):
        raise ValueError("fit contains non-finite levels")
    if xmin == xmax:
        xmin, xmax = xmin - 1.0, xmax + 1.0
    if xmin > 0:
        lo, hi = max(xmin * 0.5, 1e-3), xmax * 1.5
    else:
        span = xmax - xmin or 1.0
        lo, hi = xmin - 0.1 * span, xmax + 0.1 * span
    xg = np.linspace(lo, hi, 200)
    yg = weibull(xg, alpha, fit['beta'], fit['guess'], fit['lapse'])
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, 'ko')
    ax.plot(xg, yg, 'b-')
    ax.axvline(alpha, color='r', ls='--', label=f"alpha={alpha:.3f}")
    ax.set_xlabel('Stimulus level')
    ax.set_ylabel('P(correct)')
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
