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
import threading
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
    return max(0, min(int(n), MAX_STORED_XP))


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
    scored = [c for c in cards
              if c.get("display") is not None and c.get("value") is not None]
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
        s = _card_summary(c)
        sd = _num(s.get("reversal_sd"))
        try:
            nrev = int(s.get("n_reversals", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            nrev = 0
        if sd is not None and sd < 0.15 and nrev >= 4:
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
    return os.path.join(root, f"game_{_safe_participant(participant)}.json")


MAX_STORED_XP = 10 ** 12


def _coerce_int(v):
    try:
        return max(0, min(int(float(v)), MAX_STORED_XP))
    except (TypeError, ValueError, OverflowError):
        return 0


def _safe_participant(participant):
    try:
        if isinstance(participant, bytes):
            participant = participant.decode("utf-8", "replace")
        if not isinstance(participant, str):
            participant = str(participant)
        return safe_name(participant)
    except Exception:
        return "anon"


def _coerce_profile(doc, participant):
    if not isinstance(doc, dict):
        doc = {}
    doc["participant"] = _safe_participant(participant)
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
    name = _safe_participant(participant)
    try:
        path = profile_path(name, data_dir)
    except Exception:
        return {"participant": name, "xp": 0, "badges": [],
                "sessions": 0, "last_session_utc": None, "history": []}
    try:
        with open(path) as f:
            doc = json.load(f)
        if isinstance(doc, dict):
            return _coerce_profile(doc, name)
    except Exception:
        pass
    return {"participant": name, "xp": 0, "badges": [],
            "sessions": 0, "last_session_utc": None, "history": []}


def save_profile(participant, data_dir, profile):
    try:
        path = profile_path(participant, data_dir)
    except Exception:
        return None
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(profile, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return None
    return path


_FALLBACK_STREAKS: dict = {}
_FALLBACK_HOLD: dict = {}
_STREAK_LOCK = threading.Lock()


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
    if handle is None:
        return
    try:
        handle._arcade_streak = 0
        return
    except Exception:
        pass
    try:
        k = id(handle)
        with _STREAK_LOCK:
            _FALLBACK_STREAKS[k] = 0
            _fallback_hold(k, handle)
    except Exception:
        pass


def note_result(handle, ok):
    if handle is None:
        return 1 if ok else 0
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
        with _STREAK_LOCK:
            if ok:
                _FALLBACK_STREAKS[k] = int(_FALLBACK_STREAKS.get(k, 0)) + 1
            else:
                _FALLBACK_STREAKS[k] = 0
            _fallback_hold(k, handle)
            return int(_FALLBACK_STREAKS.get(k, 0))
    except Exception:
        return 1 if ok else 0


def streak_of(handle):
    if handle is None:
        return 0
    try:
        cur = getattr(handle, "_arcade_streak", None)
        if isinstance(cur, int):
            return int(cur)
    except Exception:
        pass
    try:
        with _STREAK_LOCK:
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
    try:
        items = list(cards or [])
    except TypeError:
        items = []
    cards = [c for c in items if isinstance(c, dict)
             and c.get("display") is not None and c.get("value") is not None]
    if not cards:
        raise ValueError("no scored tests; skipping XP")
    name = _safe_participant(participant)
    prof = load_profile(name, data_dir)
    seen = {h.get("session") for h in (prof.get("history") or [])
            if isinstance(h, dict)}
    if session_id is not None and session_id in seen:
        return prof, 0, [], False
    old_level = level_for_xp(prof.get("xp", 0))
    old_badges = set(prof.get("badges") or [])
    rewards = summarize_rewards(cards, calibrated=calibrated)
    gained = int(rewards["xp"])
    prof["xp"] = _safe_xp(prof.get("xp", 0)) + gained
    prof["sessions"] = _coerce_int(prof.get("sessions", 0)) + 1
    prof["last_session_utc"] = datetime.now(timezone.utc).isoformat()
    new_badges = [b for b in rewards["badges"] if b not in old_badges]
    prof["badges"] = sorted(old_badges | set(rewards["badges"]))
    try:
        sid = str(session_id)[:64] if session_id is not None else None
    except Exception:
        sid = None
    hist = prof.get("history") or []
    hist.append({"session": sid, "xp": gained,
                 "utc": prof["last_session_utc"]})
    prof["history"] = hist[-50:]
    save_profile(name, data_dir, prof)
    new_level = level_for_xp(prof["xp"])
    return prof, gained, new_badges, new_level > old_level
