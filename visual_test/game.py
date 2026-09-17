"""Arcade meta layer: XP, levels, badges.

Operates ONLY on scored result cards (norms.score_session output) and
session summaries. Never touches stimuli, staircases, or timing, so
thresholds stay comparable. Persistence lives in
visual_test/data/game_<participant>.json, separate from session JSON so
norms stay pure.
"""
import json
import math
import os
from datetime import datetime, timezone

try:
    from .datalogger import safe_name
except ImportError:
    from datalogger import safe_name  # type: ignore[no-redef]

XP_PER_TEST = 100
XP_PER_LEVEL = 500
MAX_LEVEL = 10
FULL_BATTERY_N = 13

BADGES = {
    "top10": "Top 10% finish",
    "sharpshooter": "Sharpshooter (clean bias)",
    "steady": "Steady (stable reversals)",
    "marathon": "Marathon (full battery)",
    "calibrated": "Calibrated rig",
}


def _safe_xp(xp):
    n = _num(xp)
    if n is None:
        return 0
    return max(0, min(int(n), 10 ** 12))


def level_for_xp(xp):
    lvl = _safe_xp(xp) // XP_PER_LEVEL
    return min(MAX_LEVEL, lvl)


def xp_into_level(xp):
    xp = _safe_xp(xp)
    lvl = level_for_xp(xp)
    if lvl >= MAX_LEVEL:
        return lvl, 0, 0
    base = lvl * XP_PER_LEVEL
    return lvl, xp - base, XP_PER_LEVEL


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def xp_for_card(card):
    """XP for one norms score card. Pure function, no I/O."""
    if not isinstance(card, dict):
        return 0
    c = card
    s = c.get("summary")
    if not isinstance(s, dict):
        s = {}
    if s.get("aborted") or s.get("truncated"):
        return 0
    if c.get("display") is None or c.get("value") is None:
        return 0
    xp = XP_PER_TEST
    pct = _num(c.get("percentile"))
    if pct is not None:
        xp += int(max(0, min(100, pct)))
        if pct >= 90:
            xp += 50
        elif pct >= 75:
            xp += 25
    z = _num(c.get("z"))
    if z is not None and z > 0:
        xp += min(50, int(z * 10))
    fa = _num(s.get("fa_rate"))
    if fa is not None and fa > 0.3:
        xp //= 2
    return int(max(0, xp))


def _card_summary(card):
    s = card.get("summary")
    return s if isinstance(s, dict) else {}


def badges_for_session(cards, calibrated=False):
    """Badge ids earned by this session's cards."""
    out = []
    try:
        items = list(cards or [])
    except TypeError:
        items = []
    cards = [c for c in items if isinstance(c, dict)]
    scored = [c for c in cards if c.get("display")]
    try:
        calibrated = bool(calibrated)
    except Exception:
        calibrated = False
    def _pct(card):
        p = _num(card.get("percentile"))
        return p if p is not None else -1
    if any(_pct(c) >= 90 for c in scored):
        out.append("top10")
    for c in scored:
        s = _card_summary(c)
        hr = _num(s.get("hit_rate"))
        fa = _num(s.get("fa_rate"))
        if hr is not None and fa is not None and hr >= 0.8 and fa <= 0.1:
            out.append("sharpshooter")
            break
    for c in scored:
        sd = _num(_card_summary(c).get("reversal_sd"))
        if sd is not None and sd < 0.15:
            out.append("steady")
            break
    if len(scored) >= FULL_BATTERY_N:
        out.append("marathon")
    if calibrated and scored:
        out.append("calibrated")
    seen = set()
    uniq = []
    for b in out:
        if b not in seen:
            seen.add(b)
            uniq.append(b)
    return uniq


def summarize_rewards(cards, calibrated=False):
    try:
        items = list(cards or [])
    except TypeError:
        items = []
    total = sum(xp_for_card(c) for c in items)
    badges = badges_for_session(items, calibrated=calibrated)
    return {"xp": int(total), "badges": badges}


def profile_path(participant, data_dir):
    root = os.path.abspath(data_dir)
    if os.path.basename(os.path.normpath(root)) == "sessions":
        root = os.path.dirname(root)
    return os.path.join(root, f"game_{safe_name(participant)}.json")


def _coerce_int(v):
    try:
        return max(0, int(float(v)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _coerce_profile(doc, participant):
    if not isinstance(doc, dict):
        doc = {}
    doc["participant"] = safe_name(participant)
    doc["xp"] = _coerce_int(doc.get("xp", 0))
    doc["sessions"] = _coerce_int(doc.get("sessions", 0))
    badges = doc.get("badges")
    if not isinstance(badges, list):
        badges = []
    doc["badges"] = sorted({b for b in badges if isinstance(b, str) and b in BADGES})
    hist = doc.get("history")
    if not isinstance(hist, list):
        hist = []
    clean = []
    for h in hist:
        if isinstance(h, dict):
            clean.append({"session": h.get("session"),
                          "xp": _coerce_int(h.get("xp", 0)),
                          "utc": h.get("utc")})
    doc["history"] = clean[-50:]
    if not isinstance(doc.get("last_session_utc"), str):
        doc["last_session_utc"] = None
    return doc


def load_profile(participant, data_dir):
    path = profile_path(participant, data_dir)
    try:
        with open(path) as f:
            doc = json.load(f)
        if isinstance(doc, dict):
            return _coerce_profile(doc, participant)
    except (OSError, ValueError):
        pass
    return {"participant": safe_name(participant), "xp": 0, "badges": [],
            "sessions": 0, "last_session_utc": None, "history": []}


def save_profile(participant, data_dir, profile):
    path = profile_path(participant, data_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(profile, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass
    return path


_FALLBACK_STREAKS: dict = {}
_FALLBACK_HOLD: dict = {}


def _fallback_hold(k, handle):
    _FALLBACK_HOLD[k] = handle
    if len(_FALLBACK_HOLD) > 1024:
        try:
            oldest = next(iter(_FALLBACK_HOLD))
            _FALLBACK_HOLD.pop(oldest, None)
            _FALLBACK_STREAKS.pop(oldest, None)
        except Exception:
            pass


def reset_streak(handle):
    try:
        handle._arcade_streak = 0
        return
    except Exception:
        pass
    try:
        k = id(handle)
        _FALLBACK_STREAKS[k] = 0
        _fallback_hold(k, handle)
    except Exception:
        pass


def note_result(handle, ok):
    try:
        cur = getattr(handle, "_arcade_streak", None)
        if isinstance(cur, int):
            nxt = cur + 1 if ok else 0
            handle._arcade_streak = nxt
            return nxt
    except Exception:
        pass
    try:
        k = id(handle)
        if ok:
            _FALLBACK_STREAKS[k] = int(_FALLBACK_STREAKS.get(k, 0)) + 1
        else:
            _FALLBACK_STREAKS[k] = 0
        _fallback_hold(k, handle)
        return int(_FALLBACK_STREAKS.get(k, 0))
    except Exception:
        return 1 if ok else 0


def streak_of(handle):
    try:
        cur = getattr(handle, "_arcade_streak", None)
        if isinstance(cur, int):
            return int(cur)
    except Exception:
        pass
    try:
        return int(_FALLBACK_STREAKS.get(id(handle), 0))
    except Exception:
        return 0


def points_for(ok, streak):
    if not ok:
        return 0
    try:
        s = int(float(streak))
    except (TypeError, ValueError, OverflowError):
        return 100
    return 100 + min(200, max(0, s - 1) * 25)


def add_session(participant, data_dir, cards, session_id=None, calibrated=False):
    """Persist one session's rewards. Returns (profile, gained, new_badges, leveled_up)."""
    cards = [c for c in (cards or []) if isinstance(c, dict) and c.get("display")]
    if not cards:
        raise ValueError("no scored tests; skipping XP")
    prof = load_profile(participant, data_dir)
    old_level = level_for_xp(prof.get("xp", 0))
    old_badges = set(prof.get("badges") or [])
    rewards = summarize_rewards(cards, calibrated=calibrated)
    gained = int(rewards["xp"])
    prof["xp"] = int(prof.get("xp", 0)) + gained
    prof["sessions"] = int(prof.get("sessions", 0)) + 1
    prof["last_session_utc"] = datetime.now(timezone.utc).isoformat()
    new_badges = [b for b in rewards["badges"] if b not in old_badges]
    prof["badges"] = sorted(old_badges | set(rewards["badges"]))
    hist = prof.get("history") or []
    hist.append({"session": session_id, "xp": gained,
                 "utc": prof["last_session_utc"]})
    prof["history"] = hist[-50:]
    save_profile(participant, data_dir, prof)
    new_level = level_for_xp(prof["xp"])
    return prof, gained, new_badges, new_level > old_level
