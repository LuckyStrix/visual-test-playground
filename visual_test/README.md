# visual_test

> **EXPERIMENTAL — NOT FOR REAL USE.** This is a personal playground for
> trying out new things with different AI models. Nothing here is
> validated, reviewed, or intended for clinical, diagnostic, screening, or
> any other real-world purpose. Do not rely on its outputs for anything.

Static single-display visual screening battery (Tkinter + Pillow).

## Run

```bash
pip install -r requirements.txt      # from repo root; pinned versions
# GUI needs Tkinter too: sudo apt install python3-tk  (Debian/Ubuntu)
# (also required to collect the test suite, which imports visual_test.main)
python3 -m visual_test.main       # GUI
python3 -m pytest visual_test/ -q # headless checks
```

## Tests

Forced-choice (2IFC/4AFC) staircases converge to 79.4% correct
(3D1U); yes/no tasks feed signal trials only, with catch trials excluded
from the staircase (hit/FA/d′ in the JSON summary).

- contrast / acuity / color / static_contrast / static_color / masked / brightness / vernier — transformed staircases
- static_rt / sizematch — fixed-trial probes

Tick checkboxes to pick which tests run in one session ("Select all" /
"Clear" helpers, "START SESSION" runs them in listed order into a single
CSV + JSON). Esc quits the current test and skips the rest of the
session; responses time out after 60 s. Pressing Esc on the final
"done" screen dismisses it without aborting the test.

Every test takes an optional `seed=`; the chosen seed is stored in the
JSON summary, along with `seed_base` / `seed_order` / interpreter
versions, stimulus seeds (`mask_seed`, `foil_seed`), and difficulty, so a
session can be replayed bit-exactly for staircase tests. Limits: reaction
time depends on a live human, Tkinter timing has ±10 ms jitter, and
blank-seed sessions use OS entropy (per-test seeds still logged
post-hoc). Simple-RT responses under 50 ms are
flagged `anticipatory` and retried as false starts.

## Data

One `PARTICIPANT_SESSION_trials.csv` + `PARTICIPANT_SESSION.json` per
session in `data/sessions/`, plus auto-saved `*_<kind>_staircase.png` /
`*_<kind>_psychometric.png` plots (fixed probes save `*_<kind>_fixed.png`)
in `data/sessions/plots/`. The JSON is rewritten
after every trial, so a crash or abort still leaves trial rows plus a
partial summary. `end_test` records ppd, rule, step sizes, reversals,
reversal trial indices, reversal SD, a `truncated` flag when the trial budget
expired before the reversal target, the `seed` plus `seed_base` /
`seed_order` / interpreter versions, `difficulty` (per-test
`difficulty_by_kind` in `meta`), `difficulty_adj`, `start_val`,
`start_val_orig`, `clipped_levels`, `target_p`, `threshold_n_discard`,
`hit_rate`, `fa_rate`, `d_prime`, trial counts (`n_trials` requested,
`n_completed`, `n_presented`, plus `n_attempts`/`n_retries` for RT), and the
Weibull fit (`weibull_alpha/beta/guess/lapse/fit_failed`).
Interrupted runs record `aborted: true` with an `abort_reason` instead
of vanishing. Practice trials are logged with `practice: true`
(`trial` keys `p1`, `p2`, …) and counted as `n_practice` in the summary.

Legacy exports from older schema versions live in
`data/legacy_archive/` (read-only reference; column names differ).
Zero-byte CSVs from sessions that never logged a trial are removed on
profile switch (see `set_participant`); `data/incomplete/` is kept for
legacy audit files only.

Yes/no tasks (static_contrast, static_color, masked,
brightness) exclude catch trials (absent signals, zero-delta colours,
same-patch brightness) from the staircase and report
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
- settings dialog: brightness %, ambient ("dark room", "dim room",
  "office", "daylight"), night-mode off?, free-text notes

Every `display_*` field lands in the session JSON `meta`; the pooled CSV
exports the main comparability subset (gamma, refresh Hz, ambient,
brightness %, night-mode). Use `comparability()` in
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

Set an optional integer seed in the GUI for exact replay (blank = random;
a non-integer seed warns, falls back to random, and is logged as
`seed_input_invalid`). Trials are clamped to 1-200 in the backend
(`max(1,min(200,n))`), though the GUI spinbox only allows 20-80.
Values outside 20-80 warn that the staircase may truncate before
converging. Session files over 10MB are skipped by the norms loader.
Display calibration is saved to `visual_test/data/display_profile.json` and
reloaded on start.

Headless exports:

```bash
python3 -m visual_test.export --list
python3 -m visual_test.export --summary
python3 -m visual_test.export --pooled pooled.csv
python3 -m visual_test.export --pooled pooled.csv --include-archive
python3 -m visual_test.export --report visual_test/data/sessions/<session>.json
```

The session list is scrollable; tick "Include legacy archive" to browse
read-only legacy sessions alongside current ones. Each session ranks
against its own directory (current vs current, legacy vs legacy), so
legacy schema differences can't skew current ranks. (`--summary
--include-archive` pools both dirs into one aggregate table; `--report`
always ranks against the session's own directory and warns if
`--data-dir` points elsewhere.)

All results are experimental playground estimates, not clinical measures.

## Dev

```bash
python3 -m pytest visual_test/ -q  # full suite (needs python3-tk installed; main.py imports Tkinter at collection)
python3 -m mypy visual_test/       # type check (config in pyproject.toml)
python3 -m ruff check visual_test/ # lint (config in pyproject.toml)
```
