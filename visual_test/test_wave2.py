"""Second-wave regression tests: stimuli smoke, registry sync, export CLI."""

import json

from . import assets as A
from . import main as M
from . import norms as N
from . import results as R
from . import stimuli as S


def test_stimuli_render_smoke():
    assert S.gabor_patch(64, 43.0, 2.0, 0.5).size == (64, 64)
    assert S.blank_patch(32).size == (32, 32)
    c = S.landolt_c(64, 90)
    assert c.size == (64, 64) and c.mode == "RGB"
    assert S.acuity_size_px(0.0, 43.0) >= 7
    assert S.isoluminant_pair(10)[0] != S.isoluminant_pair(10)[1]
    assert S.solid_patch(16, (1, 2, 3)).size == (16, 16)
    assert S.bullseye(32, (255, 0, 0), (0, 0, 255)).size == (32, 32)
    ctr, sur, _ = S.red_blue_pair(10.0)
    assert ctr != sur
    grey = S.red_blue_pair(0.0)
    assert grey[0] == grey[1] and grey[2] is None
    assert S.bright_disc(32).size == (32, 32)
    assert S.brightness_pair(64).size == (64, 64)
    assert S.vernier_bars(64, 2.0).size == (64, 64)
    assert S.size_pair(64, 20.0, 22.0).size == (64, 64)
    px1 = S.noise_mask(16, seed=1).tobytes()
    px2 = S.noise_mask(16, seed=1).tobytes()
    assert px1 == px2
    assert S.halftone_patch(16).size == (16, 16)
    assert S.match_pair(0, 32, 128).size[0] > 32
    assert len(S.step_row(16, S.DARK_STEPS, 0).size) == 2


def test_registry_sync():
    kinds = {v for _, v in M.TEST_ORDER}
    assert set(N.GUI_LABEL_TO_KIND.values()) == kinds
    assert set(N.NAME_TO_KIND.values()) == kinds
    assert set(R.TEST_INFO) == kinds
    assert set(A.MISSION_META) == kinds
    assert len(M.TEST_ORDER) == len(kinds) == len(set(M.INSTR))


def test_export_cli_full(tmp_path, capsys):
    from . import export as E

    sess = tmp_path / "sessions"
    sess.mkdir()
    doc = {
        "participant": "P",
        "session": "S",
        "tests": [{"test": "Contrast 2IFC", "kind": "contrast", "threshold_log": -1.0}],
    }
    (sess / "s.json").write_text(json.dumps(doc))
    assert E.main(["--data-dir", str(sess), "--pooled", str(tmp_path / "p.csv")]) == 0
    assert (tmp_path / "p.csv").exists()
    assert E.main(["--data-dir", str(sess), "--summary"]) == 0
    assert E.main(["--data-dir", str(sess), "--report", str(sess / "s.json")]) == 0
    assert (
        E.main(["--data-dir", str(sess), "--pooled", str(tmp_path / "p2.csv"), "--include-archive"])
        == 0
    )
    assert E.default_data_dir().endswith("sessions")
