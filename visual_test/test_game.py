"""Arcade meta layer: XP, levels, badges, streaks. No display needed."""
import os

from . import game as G


def card(value=1.0, display="1%", pct=None, band=None, z=None, summary=None):
    return {"value": value, "display": display, "percentile": pct,
            "band": band, "z": z,
            "summary": summary if summary is not None else {}}


def test_xp_base_only_without_rank():
    assert G.xp_for_card(card()) == 100


def test_xp_zero_when_aborted_or_truncated():
    assert G.xp_for_card(card(summary={"aborted": True})) == 0
    assert G.xp_for_card(card(summary={"truncated": True})) == 0
    assert G.xp_for_card(card(value=None, display=None)) == 0


def test_xp_rank_bonus_and_band():
    xp = G.xp_for_card(card(pct=95.0, band="Top 10%", z=2.0))
    assert xp == 100 + 95 + 50 + 20


def test_xp_bias_halved():
    full = G.xp_for_card(card(pct=80.0, summary={"fa_rate": 0.1}))
    cut = G.xp_for_card(card(pct=80.0, summary={"fa_rate": 0.5}))
    assert cut == full // 2


def test_levels():
    assert G.level_for_xp(0) == 0
    assert G.level_for_xp(499) == 0
    assert G.level_for_xp(500) == 1
    assert G.level_for_xp(99999) == G.MAX_LEVEL
    lvl, into, need = G.xp_into_level(750)
    assert (lvl, into, need) == (1, 250, 500)


def test_streak_points():
    h = object()
    G.reset_streak(h)
    assert G.note_result(h, True) == 1
    assert G.note_result(h, True) == 2
    assert G.points_for(True, 2) == 125
    assert G.note_result(h, False) == 0
    assert G.points_for(False, 0) == 0


def test_badges():
    cards = [card(pct=95.0, summary={"hit_rate": 0.9, "fa_rate": 0.05,
                                     "reversal_sd": 0.1})]
    badges = G.badges_for_session(cards, calibrated=True)
    assert "top10" in badges
    assert "sharpshooter" in badges
    assert "steady" in badges
    assert "calibrated" in badges
    assert G.badges_for_session([card()] * 13) == ["marathon"]


def test_persistence_roundtrip(tmp_path):
    d = str(tmp_path)
    cards = [card(pct=80.0, band="Above average")]
    prof, gained, new_badges, leveled = G.add_session("P1", d, cards, session_id="s1")
    assert gained > 100
    assert prof["sessions"] == 1
    assert os.path.exists(G.profile_path("P1", d))
    prof2, _, _, _ = G.add_session("P1", d, [card()], session_id="s2")
    assert prof2["sessions"] == 2
    assert prof2["xp"] >= prof["xp"]


def test_assets_generate(tmp_path, monkeypatch):
    from . import assets as A
    monkeypatch.setattr(A, "asset_dir", lambda: str(tmp_path))
    d = A.ensure_assets()
    assert d == str(tmp_path)
    assert A.sound_path("correct") is not None
    assert A.mission_meta("acuity")[1] == "Gap Sniper"


def test_max_level_header():
    assert G.xp_into_level(5000) == (G.MAX_LEVEL, 0, 0)
    assert G.xp_into_level(99999) == (G.MAX_LEVEL, 0, 0)


def test_num_rejects_inf_nan():
    assert G._num(float("inf")) is None
    assert G._num(float("nan")) is None
    bad = card(pct=float("inf"), band="Top 10%", z=float("inf"))
    assert G.xp_for_card(bad) == 100


def test_streak_isolation():
    class H:
        pass
    a, b = H(), H()
    G.reset_streak(a)
    G.reset_streak(b)
    G.note_result(a, True)
    G.note_result(a, True)
    assert G.streak_of(a) == 2
    assert G.streak_of(b) == 0
    G.note_result(b, True)
    assert G.streak_of(a) == 2
    assert G.streak_of(b) == 1


def test_empty_session_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        G.add_session("P1", str(tmp_path), [], session_id="s0")
    assert G.badges_for_session([], calibrated=True) == []


def test_profile_stays_in_tmpdir(tmp_path):
    p = G.profile_path("P1", str(tmp_path))
    assert os.path.dirname(p) == str(tmp_path)


def test_profile_coerces_corrupt(tmp_path, monkeypatch):
    import json
    p = G.profile_path("P1", str(tmp_path))
    with open(p, "w") as f:
        json.dump({"xp": "oops", "sessions": "oops", "badges": "oops",
                   "history": "oops"}, f)
    prof = G.load_profile("P1", str(tmp_path))
    assert prof["xp"] == 0
    assert prof["sessions"] == 0
    assert prof["badges"] == []


def test_viewer_ranked_card_shows_xp():
    from .viewer import _card_text
    c = {"kind": "static_rt", "name": "x", "value": 250.0,
         "display": "250 ms", "percentile": 80.0, "band": "Above average",
         "z": 0.5, "n": 10, "summary": {}}
    text = _card_text(dict(c))
    assert "+210 XP" in text


def test_fixed_trial_classes_accept_feedback_flag():
    from . import tests as T
    import inspect
    for cls in (T.HueOrdering, T.SizeMatch, T.StaticReactionTime):
        assert "feedback" in inspect.signature(cls.__init__).parameters
