"""Arcade meta layer: XP, levels, badges.

Operates ONLY on scored result cards (norms.score_session output) and
session summaries. Never touches stimuli, staircases, or timing, so
thresholds stay comparable. Persistence lives in
visual_test/data/game_<participant>.json, separate from session JSON so
norms stay pure.
"""
import json
import os
from datetime import datetime, timezone

try:
    from .datalogger import safe_name
except ImportError:
    from datalogger import safe_name  # type: ignore[no-redef]

XP_PER_TEST = 100
XP_PER_LEVEL = 500
MAX_LEVEL = 10

BADGES = {
    "top10": "Top 10% finish",
    "sharpshooter": "Sharpshooter (clean bias)",
    "steady": "Steady (stable reversals)",
    "marathon": "Marathon (full battery)",
    "calibrated": "Calibrated rig",
}


def level_for_xp(xp):
    lvl = int(max(0, xp or 0)) // XP_PER_LEVEL
    return min(MAX_LEVEL, lvl)


def xp_into_level(xp):
    xp = int(max(0, xp or 0))
    lvl = level_for_xp(xp)
    base = lvl * XP_PER_LEVEL
    return lvl, xp - base, XP_PER_LEVEL


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def xp_for_card(card):
    """XP for one norms score card. Pure function, no I/O."""
    c = card or {}
    s = c.get("summary") or {}
    if s.get("aborted") or s.get("truncated"):
        return 0
    if c.get("display") is None or c.get("value") is None:
        return 0
    xp = XP_PER_TEST
    pct = _num(c.get("percentile"))
    if pct is not None:
        xp += int(max(0, min(100, pct)))
        band = (c.get("band") or "")
        if band == "Top 10%":
            xp += 50
        elif band == "Above average":
            xp += 25
    z = _num(c.get("z"))
    if z is not None and z > 0:
        xp += min(50, int(z * 10))
    fa = _num(s.get("fa_rate"))
    if fa is not None and fa > 0.3:
        xp //= 2
    return int(max(0, xp))


def badges_for_session(cards, calibrated=False):
    """Badge ids earned by this session's cards."""
    out = []
    cards = [c for c in (cards or []) if isinstance(c, dict)]
    scored = [c for c in cards if c.get("display")]
    if any((c.get("percentile") or 0) >= 90 for c in scored):
        out.append("top10")
    for c in scored:
        s = c.get("summary") or {}
        hr = _num(s.get("hit_rate"))
        fa = _num(s.get("fa_rate"))
        if hr is not None and fa is not None and hr >= 0.8 and fa <= 0.1:
            out.append("sharpshooter")
            break
    for c in scored:
        sd = _num((c.get("summary") or {}).get("reversal_sd"))
        if sd is not None and sd < 0.15:
            out.append("steady")
            break
    if len(scored) >= 13:
        out.append("marathon")
    if calibrated:
        out.append("calibrated")
    seen = set()
    uniq = []
    for b in out:
        if b not in seen:
            seen.add(b)
            uniq.append(b)
    return uniq


def summarize_rewards(cards, calibrated=False):
    total = sum(xp_for_card(c) for c in (cards or []))
    badges = badges_for_session(cards, calibrated=calibrated)
    return {"xp": int(total), "badges": badges}


def profile_path(participant, data_dir):
    base_dir = os.path.dirname(os.path.abspath(data_dir))
    return os.path.join(base_dir, f"game_{safe_name(participant)}.json")


def load_profile(participant, data_dir):
    path = profile_path(participant, data_dir)
    try:
        with open(path) as f:
            doc = json.load(f)
        if isinstance(doc, dict):
            doc.setdefault("participant", safe_name(participant))
            doc.setdefault("xp", 0)
            doc.setdefault("badges", [])
            doc.setdefault("sessions", 0)
            return doc
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


_STREAKS = {}


def reset_streak(handle):
    try:
        _STREAKS[id(handle)] = 0
    except Exception:
        pass


def note_result(handle, ok):
    key = id(handle)
    if ok:
        _STREAKS[key] = int(_STREAKS.get(key, 0)) + 1
    else:
        _STREAKS[key] = 0
    return int(_STREAKS.get(key, 0))


def streak_of(handle):
    return int(_STREAKS.get(id(handle), 0))


def points_for(ok, streak):
    if not ok:
        return 0
    return 100 + min(200, max(0, int(streak - 1)) * 25)


def add_session(participant, data_dir, cards, session_id=None, calibrated=False):
    """Persist one session's rewards. Returns (profile, gained, new_badges, leveled_up)."""
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
