"""Local norms: compare a score against past sessions on this machine.

No cloud, no bundled population data. Norms are computed on the fly from
session JSON files in the data directory, so percentiles reflect whoever
has used this computer so far. A percentile rank is shown once at least
MIN_N_FOR_PERCENTILE comparable sessions exist; with fewer sessions the
score is shown without a rank.
"""

import glob
import json
import math
import os

import numpy as np

MIN_N_FOR_PERCENTILE = 5

HIGHER_BETTER = frozenset({"subitize"})

GUI_LABEL_TO_KIND = {
    "STATIC contrast: stripes there or not? (Y/N)": "static_contrast",
    "STATIC colour bullseye: center redder or bluer? (R/B)": "static_color",
    "STATIC reaction time: press SPACE when disc pops (no memory)": "static_rt",
    "Collinearity: are the two segments aligned? (Y/N)": "collinear",
    "Brightness match: same grey on dark vs light ring?": "brightness",
    "Vernier: lower bar left or right? (Left/Right)": "vernier",
    "How many dots? (1-9 keys)": "subitize",
    "Order 6 hues light->dark (click in order)": "hueorder",
    "Size match: adjust disc, Enter when equal (bias)": "sizematch",
    "Masked Gabor: stripes there? (Y/N, brief+mask)": "masked",
    "Contrast detection (2IFC Gabor, 3D1U)": "contrast",
    "Acuity (4AFC Landolt C, 3D1U)": "acuity",
    "Colour (2IFC isoluminant, 3D1U)": "color",
}

NAME_TO_KIND = {
    "Contrast 2IFC": "contrast",
    "Acuity 4AFC": "acuity",
    "Colour 2IFC": "color",
    "Static Contrast Y/N": "static_contrast",
    "Static Bullseye R/B": "static_color",
    "Static Reaction Time": "static_rt",
    "Collinearity Y/N": "collinear",
    "Brightness same/diff": "brightness",
    "Vernier L/R": "vernier",
    "Subitizing 1-9": "subitize",
    "Hue ordering": "hueorder",
    "Size match bias": "sizematch",
    "Masked Gabor Y/N": "masked",
}


def kind_of(name):
    return NAME_TO_KIND.get(name) or GUI_LABEL_TO_KIND.get(name, "")  # noqa


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def extract(kind, summary):
    """Pull a comparable score from one test summary.

    Returns {'value', 'display', 'higher_better'} or None when the summary
    holds no score (aborted run, missing metric). `value` is always a plain
    float suitable for ranking; `display` is the human-readable form.
    """
    s = summary or {}
    if s.get("aborted"):
        return None
    higher = kind in HIGHER_BETTER
    if kind in ("contrast", "static_contrast", "masked"):
        thr = _num(s.get("threshold_log"))
        if thr is None:
            return None
        pct = 10.0**thr * 100.0
        return {"value": pct, "display": f"{pct:.1f}% contrast", "higher_better": higher}
    if kind == "acuity":
        thr = _num(s.get("threshold_log"))
        if thr is None:
            return None
        denom = 20.0 * (10.0**thr)
        return {
            "value": thr,
            "display": f"20/{denom:.0f} (logMAR {thr:.2f})",
            "higher_better": higher,
        }
    if kind in ("color", "static_color"):
        thr = _num(s.get("threshold_log"))
        if thr is None:
            return None
        delta = 10.0**thr
        return {"value": delta, "display": f"{delta:.1f} device steps", "higher_better": higher}
    if kind in ("collinear", "vernier"):
        thr = _num(s.get("threshold_log"))
        if thr is None:
            return None
        arcmin = (10.0**thr) * 60.0
        return {"value": arcmin, "display": f"{arcmin:.1f} arcmin", "higher_better": higher}
    if kind == "brightness":
        thr = _num(s.get("threshold_log"))
        if thr is None:
            return None
        delta = 10.0**thr
        return {"value": delta, "display": f"{delta:.1f} gray steps", "higher_better": higher}
    if kind == "static_rt":
        med = _num(s.get("median_rt_s"))
        if med is None:
            return None
        return {"value": med * 1000.0, "display": f"{med * 1000.0:.0f} ms", "higher_better": higher}
    if kind == "subitize":
        acc = _num(s.get("accuracy"))
        if acc is None:
            return None
        return {
            "value": acc * 100.0,
            "display": f"{acc * 100.0:.0f}% correct",
            "higher_better": higher,
        }
    if kind == "hueorder":
        disp = _num(s.get("mean_displacement"))
        if disp is None:
            return None
        return {
            "value": disp,
            "display": f"{disp:.2f} mean displacement (0 = perfect)",
            "higher_better": higher,
        }
    if kind == "sizematch":
        bias = _num(s.get("mean_bias"))
        if bias is None:
            return None
        return {
            "value": abs(bias),
            "display": f"{bias * 100.0:+.1f}% bias (0 = veridical)",
            "higher_better": higher,
        }
    return None


def load_session(path):
    try:
        with open(path) as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def session_label(doc):
    """(participant, session) handling legacy key names too."""
    doc = doc or {}
    participant = doc.get("participant", doc.get("participant_id", "?"))
    session = doc.get("session", doc.get("session_id", "?"))
    return participant, session


def list_sessions(data_dir):
    """Newest-first list of {'path','participant','session','n_tests','source'}."""
    out = []
    try:
        files = glob.glob(os.path.join(data_dir, "*.json"))
    except OSError:
        return out
    for path in files:
        doc = load_session(path)
        if doc is None:
            continue
        tests = doc.get("tests") or []
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        participant, session = session_label(doc)
        out.append(
            {
                "path": path,
                "participant": participant,
                "session": session,
                "n_tests": len(tests),
                "mtime": mtime,
                "source": os.path.basename(os.path.normpath(data_dir)),
            }
        )
    out.sort(key=lambda d: d["mtime"], reverse=True)
    return out


def collect_norms(data_dir, exclude=None):
    """Map kind -> list of past scores, skipping aborted/truncated runs."""
    norms = {}
    for info in list_sessions(data_dir):
        if info["path"] == exclude:
            continue
        doc = load_session(info["path"])
        if doc is None:
            continue
        for s in doc.get("tests") or []:
            if not isinstance(s, dict):
                continue
            if s.get("aborted") or s.get("truncated"):
                continue
            kind = s.get("kind") or kind_of(s.get("test", ""))
            if not kind:
                continue
            got = extract(kind, s)
            if got is None:
                continue
            norms.setdefault(kind, []).append(got["value"])
    return norms


def describe(values):
    vals = [float(v) for v in (values or []) if _num(v) is not None]
    if not vals:
        return None
    stats = {
        "n": len(vals),
        "mean": float(np.mean(vals)),
        "lo": float(np.min(vals)),
        "hi": float(np.max(vals)),
        "p10": float(np.percentile(vals, 10)),
        "p25": float(np.percentile(vals, 25)),
        "p50": float(np.percentile(vals, 50)),
        "p75": float(np.percentile(vals, 75)),
        "p90": float(np.percentile(vals, 90)),
    }
    stats["sd"] = float(np.std(vals, ddof=1)) if len(vals) >= 2 else None
    return stats


def rank(value, values, higher_better):
    """Percent of the norm group this score beats (ties split)."""
    vals = [float(v) for v in (values or []) if _num(v) is not None]
    if not vals:
        return None
    if higher_better:
        better = sum(1 for v in vals if v < value)
    else:
        better = sum(1 for v in vals if v > value)
    ties = sum(1 for v in vals if v == value)
    return round((better + 0.5 * ties) / len(vals) * 100.0, 1)


def zscore(value, values, higher_better):
    """Signed z: positive always means better than the norm mean."""
    vals = [float(v) for v in (values or []) if _num(v) is not None]
    if len(vals) < 2:
        return None
    sd = float(np.std(vals, ddof=1))
    if not sd:
        return None
    z = (value - float(np.mean(vals))) / sd
    return round(-z if not higher_better else z, 2)


def band(percentile):
    if percentile is None:
        return None
    if percentile >= 90:
        return "Top 10%"
    if percentile >= 75:
        return "Above average"
    if percentile > 25:
        return "Typical"
    if percentile > 10:
        return "Below average"
    return "Lower 10%"


def score_session(doc, norms):
    """Score every test in a session doc against norms.

    Returns a list of cards with keys kind/name/value/display/
    higher_better/n/stats/percentile/band/z/summary.
    """
    cards = []
    for s in (doc or {}).get("tests") or []:
        if not isinstance(s, dict):
            continue
        name = s.get("test", "?")
        kind = s.get("kind") or kind_of(name)
        got = extract(kind, s) if kind else None
        values = (norms or {}).get(kind, []) if kind else []
        stats = describe(values)
        n = stats["n"] if stats else 0
        pct = None
        if got is not None and n >= MIN_N_FOR_PERCENTILE:
            pct = rank(got["value"], values, got["higher_better"])
        cards.append(
            {
                "kind": kind or None,
                "name": name,
                "value": got["value"] if got else None,
                "display": got["display"] if got else None,
                "higher_better": got["higher_better"] if got else False,
                "n": n,
                "stats": stats,
                "percentile": pct,
                "band": band(pct),
                "z": (
                    zscore(got["value"], values, got["higher_better"])
                    if got is not None and n >= 2
                    else None
                ),
                "summary": s,
            }
        )
    return cards
