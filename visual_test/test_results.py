import json

from . import norms as N
from . import results as R
from .datalogger import DataLogger


def _doc(*tests):
    return {"participant": "P", "session": "S", "tests": list(tests)}


def test_extract_staircase_kinds():
    assert N.extract("contrast", {"threshold_log": -1.0})["display"] == "10.0% contrast"
    got = N.extract("acuity", {"threshold_log": 0.0})
    assert got["display"].startswith("20/20")
    assert N.extract("static_rt", {"median_rt_s": 0.25})["value"] == 250.0
    assert N.extract("subitize", {"accuracy": 0.9})["higher_better"] is True
    assert N.extract("hueorder", {"mean_displacement": 0.5})["value"] == 0.5
    assert N.extract("sizematch", {"mean_bias": -0.05})["display"].startswith("-5.0%")
    assert N.extract("contrast", {"aborted": True}) is None
    assert N.extract("contrast", {}) is None
    assert N.extract("nope", {"threshold_log": 0.0}) is None


def test_rank_and_band():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert N.rank(0.5, vals, False) == 100.0
    assert N.rank(6.0, vals, False) == 0.0
    assert N.rank(3.0, vals, False) == 50.0
    assert N.rank(3.0, vals, True) == 50.0
    assert N.rank(1.0, [], False) is None
    assert R.TEST_INFO and N.band(95) == "Top 10%"
    assert N.band(80) == "Above average"
    assert N.band(50) == "Typical"
    assert N.band(20) == "Below average"
    assert N.band(5) == "Lower 10%"
    assert N.band(None) is None
    assert N.zscore(0.0, [1.0], False) is None
    assert N.zscore(3.0, [1.0, 2.0, 3.0], False) is not None


def _write_session(tmp_path, name, tests):
    p = tmp_path / name
    p.write_text(json.dumps({"participant": "P", "session": name, "tests": tests}))
    return str(p)


def test_collect_norms_skips_aborted_and_truncated(tmp_path):
    good = {"test": "Contrast 2IFC", "kind": "contrast", "threshold_log": -1.0, "n_trials": 10}
    _write_session(tmp_path, "a.json", [good])
    _write_session(tmp_path, "b.json", [{**good, "threshold_log": -0.7}])
    _write_session(tmp_path, "c.json", [{**good, "aborted": True}])
    _write_session(tmp_path, "d.json", [{**good, "truncated": True}])
    group = N.collect_norms(str(tmp_path))
    assert len(group["contrast"]) == 2


def test_score_session_gates_percentile_on_n(tmp_path):
    base = {"test": "Contrast 2IFC", "kind": "contrast", "threshold_log": -1.0}
    for i in range(4):
        _write_session(tmp_path, f"p{i}.json", [{**base, "threshold_log": -1.0 + i * 0.1}])
    group = N.collect_norms(str(tmp_path))
    cards = N.score_session(_doc(base), group)
    assert cards[0]["percentile"] is None
    assert cards[0]["n"] == 4
    _write_session(tmp_path, "p4.json", [{**base, "threshold_log": -0.5}])
    group = N.collect_norms(str(tmp_path))
    cards = N.score_session(_doc(base), group)
    assert cards[0]["percentile"] is not None
    assert cards[0]["band"] is not None


def test_score_session_falls_back_to_test_name(tmp_path):
    group = {}
    cards = N.score_session(_doc({"test": "Contrast 2IFC", "threshold_log": -1.0}), group)
    assert cards[0]["kind"] == "contrast"
    assert cards[0]["n"] == 0


def test_interpret_and_format_card():
    card = {
        "kind": "static_rt",
        "name": "Static Reaction Time",
        "value": 250.0,
        "display": "250 ms",
        "higher_better": False,
        "n": 6,
        "stats": N.describe([200, 220, 240, 260, 280, 300]),
        "percentile": 50.0,
        "band": "Typical",
        "z": 0.0,
        "summary": {},
    }
    text = R.format_card_text(card)
    assert "Simple reaction time" in text
    assert "250 ms" in text
    assert "not a clinical measure" in text
    flagged = R.flags_for({"truncated": True, "unreliable_bias": True, "clipped_levels": True})
    assert len(flagged) == 3
    assert R.flags_for({"aborted": True})[0].startswith("aborted")


def test_summarize_session_headline():
    cards = [
        {
            "kind": "static_rt",
            "name": "RT",
            "display": "250 ms",
            "percentile": 90.0,
            "band": "Top 10%",
            "n": 6,
            "title": "Simple reaction time",
            "what": "x",
            "unit": "ms",
            "good": "g",
            "checks": "c",
            "caveats": [],
            "z": 1.0,
            "summary": {},
        }
    ]
    head = R.summarize_session(cards)["headline"]
    assert "Strengths" in head
    assert R.summarize_session([])["headline"].startswith("No tests")
    assert (
        "No ranking yet"
        in R.summarize_session([{**cards[0], "percentile": None, "band": None}])["headline"]
    )


def test_kind_tags_present_in_summaries(tmp_path):
    from . import tests as T

    lg = DataLogger("K", data_dir=str(tmp_path))
    lg.end_test(test="X", kind="contrast", threshold_log=-1.0)
    lg.end_test(test="Y", kind="subitize", accuracy=0.9)
    assert lg.tests[0]["kind"] == "contrast"
    assert lg.tests[1]["kind"] == "subitize"
    assert T.ContrastDetection2IFC.kind == "contrast"
    assert T.Subitizing.kind == "subitize"


def test_export_commands(tmp_path, capsys):
    from . import export as E

    _write_session(
        tmp_path,
        "s.json",
        [{"test": "Contrast 2IFC", "kind": "contrast", "threshold_log": -1.0, "n_trials": 8}],
    )
    assert E.cmd_list(str(tmp_path)) == 0
    assert E.cmd_summary(str(tmp_path)) == 0
    out = str(tmp_path / "pooled.csv")
    assert E.cmd_pooled(str(tmp_path), out) == 0
    assert E.cmd_report(str(tmp_path), str(tmp_path / "s.json")) == 0
    assert E.main(["--data-dir", str(tmp_path), "--list"]) == 0
    assert E.main([]) == 2
