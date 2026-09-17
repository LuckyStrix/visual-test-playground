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
