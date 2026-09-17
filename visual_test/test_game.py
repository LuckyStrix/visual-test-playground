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
                                     "reversal_sd": 0.1, "n_reversals": 8})]
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


def test_level_rejects_garbage():
    for bad in (None, "abc", float("inf"), float("nan"), -100):
        assert G.level_for_xp(bad) == 0
        assert G.xp_into_level(bad) == (0, 0, 500)
    assert G.level_for_xp("750") == 1


def test_xp_for_card_rejects_non_dict():
    for bad in (None, "str", 123, [], {"summary": "notadict"}):
        assert G.xp_for_card(bad) == 0


def test_badges_rejects_non_list():
    for bad in (None, "str", 123):
        assert G.badges_for_session(bad) == []
        assert G.badges_for_session(bad, calibrated=True) == []


def test_xp_band_derived_from_percentile_not_label():
    assert G.xp_for_card(card(pct=95.0, band="Typical")) == 100 + 95 + 50
    assert G.xp_for_card(card(pct=10.0, band="Top 10%")) == 100 + 10
    assert "top10" not in G.badges_for_session([card(pct=float("nan"))])


def test_viewer_bar_clamps_bad_input():
    from .viewer import _bar, _card_text
    assert "100% beat" in _bar(150.0, xp=100)
    assert "0% beat" in _bar(-20.0)
    assert "not enough past sessions" in _bar(float("nan"), xp=100)
    assert "not enough past sessions" in _bar(None)
    assert _card_text(None) == "(unreadable result card)"
    assert _card_text("str") == "(unreadable result card)"
    assert _card_text({"summary": "bad"}) == "(unreadable result card)"
    assert "(unranked, n=0)" in _card_text({"display": None, "percentile": 80.0})
    assert "+0 XP" not in _card_text({})


def test_assets_rewrite_corrupt(tmp_path, monkeypatch):
    from . import assets as A
    monkeypatch.setattr(A, "asset_dir", lambda: str(tmp_path))
    A.ensure_assets()
    p = A.sound_path("correct")
    assert p is not None
    with open(p, "wb") as f:
        f.write(b"garbage-not-a-wav-file-xx")
    A.ensure_assets()
    import wave
    with wave.open(p, "rb") as w:
        assert w.getnframes() > 0


def test_replay_same_session_id_no_double_count(tmp_path):
    cards = [card(pct=80.0, band="Above average")]
    prof, gained, _, _ = G.add_session("P1", str(tmp_path), cards, session_id="s1")
    assert gained > 0
    prof2, gained2, new2, leveled2 = G.add_session(
        "P1", str(tmp_path), cards, session_id="s1")
    assert gained2 == 0
    assert new2 == []
    assert leveled2 is False
    assert prof2["sessions"] == prof["sessions"] == 1
    assert prof2["xp"] == prof["xp"]


def test_badge_value_consistency_no_free_marathon():
    ghost = [{"display": "x", "value": None} for _ in range(13)]
    assert G.badges_for_session(ghost) == []
    assert G.xp_for_card({"display": "x", "value": None}) == 0


def test_steady_needs_reversals():
    thin = [card(pct=80.0, summary={"reversal_sd": 0.1})]
    assert "steady" not in G.badges_for_session(thin)
    solid = [card(pct=80.0, summary={"reversal_sd": 0.1, "n_reversals": 8})]
    assert "steady" in G.badges_for_session(solid)


def test_participant_sanitized_not_crash():
    import re
    p = G.profile_path(12345, "/tmp")
    assert p.endswith(".json")
    for bad in (["x"], None, 12345, b"bytes", object()):
        name = G.load_profile(bad, "/tmp")["participant"]
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name), name


def test_streak_none_safe():
    assert G.note_result(None, True) == 1
    assert G.streak_of(None) == 0
    G.reset_streak(None)


def test_save_profile_failure_returns_none(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(_json, "dump", lambda *a, **k: (_ for _ in ()).throw(
        TypeError("not serializable")))
    assert G.save_profile("P1", str(tmp_path), {"xp": 1}) is None


def test_sound_path_rejects_traversal(tmp_path, monkeypatch):
    from . import assets as A
    monkeypatch.setattr(A, "asset_dir", lambda: str(tmp_path))
    assert A.sound_path("../../etc/passwd") is None
    assert A.sound_path("correct;rm") is None
    assert A.sound_path(None) is None


def test_play_async_dedups_and_recovers(monkeypatch):
    import threading as _th
    from . import assets as A
    gate = _th.Event()
    calls = []
    def slow(path):
        calls.append(path)
        gate.wait(timeout=10)
        return True
    monkeypatch.setattr(A, "_play_sync", slow)
    monkeypatch.setattr(A, "_can_play", lambda: True)
    monkeypatch.setattr(A, "sound_path", lambda n: "/tmp/x.wav")
    t1 = A.play_async("correct")
    t2 = A.play_async("correct")
    assert t1 is not None
    assert t2 is None
    gate.set()
    if t1 is not None:
        t1.join(timeout=5)
    t3 = A.play_async("correct")
    assert t3 is not None
    if t3 is not None:
        t3.join(timeout=5)


def test_viewer_entry_and_caveats_guards():
    from .viewer import _entry_text, _card_text
    assert _entry_text({}) != ""
    assert _entry_text(None) == "(unreadable session)"
    assert "(unranked, n=0)" in _card_text({"display": None, "percentile": 80.0})
    c = {"kind": "static_rt", "value": 1.0, "display": "1%",
         "percentile": None, "n": 0, "summary": {"d_prime": 1.5},
         "caveats": "bad"}
    text = _card_text(dict(c))
    assert "bias: hit" in text
    assert "! b" not in text


def test_norms_malformed_tests_and_self_exclusion(tmp_path):
    import json as _json
    from . import norms as N
    bad = tmp_path / "bad.json"
    bad.write_text(_json.dumps({"participant": "p", "session": "s",
                                "tests": {"not": "a list"}}))
    assert N.list_sessions(str(tmp_path))
    assert N.collect_norms(str(tmp_path)) == {}
    good = tmp_path / "good.json"
    good.write_text(_json.dumps({
        "participant": "p", "session": "s2",
        "tests": [{"test": "Static Reaction Time", "kind": "static_rt",
                   "median_rt_s": 0.25, "n_trials": 10}]}))
    rel = str(good)
    abs_p = str(good.resolve())
    assert N.collect_norms(str(tmp_path), exclude=rel) == {}
    assert N.collect_norms(str(tmp_path), exclude=abs_p) == {}


def test_audio_falls_back_when_no_player(tmp_path, monkeypatch):
    from . import assets as A
    monkeypatch.setattr(A, "asset_dir", lambda: str(tmp_path))
    A.ensure_assets()
    monkeypatch.setattr(A, "_find_player", lambda: [])
    called = []
    class W:
        def bell(self):
            called.append(1)
    assert A.play_async("correct", widget=W()) is None
    assert called == [1]
