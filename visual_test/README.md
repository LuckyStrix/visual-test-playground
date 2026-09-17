# visual_test

> **EXPERIMENTAL — NOT FOR REAL USE.** This is a personal playground for
> trying out new things with different AI models. Nothing here is
> validated, reviewed, or intended for clinical, diagnostic, screening, or
> any other real-world purpose. Do not rely on its outputs for anything.

Static single-display visual screening battery (Tkinter + Pillow).

## Run

```bash
pip install -r requirements.txt      # from repo root; pinned versions
# or: pip install -e .[test]
python3 -m visual_test.main       # GUI
python3 -m pytest visual_test/ -q # headless checks
```

## Tests

Forced-choice (2IFC/4AFC) staircases converge to 70.7%/79.4% correct
(3D1U); yes/no tasks feed signal trials only, with no-signal trials as
catches (hit/FA/d′ in the JSON summary).

- contrast / acuity / color — transformed staircases
- static_contrast / static_color / masked — yes/no + d′
- collinear / brightness / vernier — hyperacuity/illusion staircases
- static_rt / subitize / hueorder / sizematch — fixed-trial probes

Tick checkboxes to pick which tests run in one session ("Select all" /
"Clear" helpers, "START SESSION" runs them in listed order into a single
CSV + JSON). Esc quits the current test and skips the rest of the
session; responses time out after 60 s. Pressing Esc on the final
"done" screen dismisses it without aborting the test.

Every test takes an optional `seed=`; the chosen seed is stored in the
JSON summary, so any session can be replayed exactly. Subitizing also
logs the per-trial dot seed. Simple-RT responses under 100 ms are
flagged `anticipatory` and retried as false starts.

## Data

One `PARTICIPANT_SESSION_trials.csv` + `PARTICIPANT_SESSION.json` per
session in `data/sessions/`, plus auto-saved `*_staircase.png` /
`*_psychometric.png` plots in `data/plots/`. The JSON is rewritten
after every trial, so a crash or abort still leaves trial rows plus a
partial summary. `end_test` records ppd, rule, step sizes, reversals,
reversal trial indices, a `truncated` flag when the trial budget
expired before the reversal target, and the `seed` for exact replay.
Interrupted runs record `aborted: true` with an `abort_reason` instead
of vanishing. Practice trials are logged with `practice: true` and
counted as `n_practice` in the summary.

Legacy exports from older schema versions live in
`data/legacy_archive/` (read-only reference; column names differ).
Zero-byte CSVs from aborted sessions are kept in
`data/incomplete/` for audit.

Yes/no tasks (static_contrast, static_color, masked, collinear,
brightness) exclude no-signal trials from the staircase and report
hit rate / false-alarm rate / d′ in the JSON summary, so response bias
is flagged instead of silently becoming a "threshold".

Set display diagonal + viewing distance in the GUI so pixels-per-degree
is calibrated; thresholds are meaningless otherwise. Resolution is
read from the primary monitor only — run the stimulus there or verify
ppd manually on multi-monitor setups.

## Display calibration

Run "Run display calibration (~1 min)" before testing a new computer.
No photometer needed; it records a display fingerprint so sessions stay
comparable across machines:

- measured refresh rate (frame count + p50/p95 interval, jitter, % missed)
- subjective gamma: match a solid patch to a halftone checkerboard at 3
  levels (Up/Down fine, Left/Right coarse, Enter confirms)
- black steps visible on black (0-9) + white steps visible on white (0-9)
- settings dialog: brightness %, ambient (dark/dim/office/daylight),
  night-mode off?, free-text notes (display model, etc.)

Every `display_*` field lands in the session JSON `meta` and so in all
later exports from that session. Use `comparability()` in
`calibration.py` to flag gamma / refresh / ambient / black-white
mismatches before pooling data. Values are estimates + settings, not
photometry — no absolute cd/m².

## Results vs past sessions

After each session a results window shows one card per test: what was
measured, your score in plain units (% contrast, 20/x, ms, arcmin), and a
percentile bar against this machine's past sessions (local only, nothing
uploaded). Ranks appear once 5+ comparable past sessions exist; aborted or
truncated runs are excluded from norms and flagged on the card. "View
results vs past sessions" reopens any historic session. Every test writes a
stable `kind` id into its JSON summary so scores stay comparable.

Set an optional integer seed in the GUI for exact replay (blank = random).
Display calibration is saved to `visual_test/data/display_profile.json` and
reloaded on start.

Headless exports:

```bash
python3 -m visual_test.export --list
python3 -m visual_test.export --summary
python3 -m visual_test.export --pooled pooled.csv
python3 -m visual_test.export --report visual_test/data/sessions/<session>.json
```

All results are experimental playground estimates, not clinical measures.

## Dev

```bash
python3 -m pytest visual_test/ -q  # full suite (headless; Tkinter not required)
python3 -m mypy visual_test/       # type check (config in pyproject.toml)
python3 -m ruff check visual_test/ # lint (config in pyproject.toml)
```
