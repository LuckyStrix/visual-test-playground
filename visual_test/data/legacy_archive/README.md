# legacy_archive — read-only reference

Exports from older schema versions of the logger. Do not mix with
current `../sessions/` files:

- `timestamp,participant_id,session_id,test_name,trial_num,...` CSVs and
  `*_summary.json` files: earliest prototype schema.
- `test_name,trial_num,stimulus_params,response,...` CSVs and
  `{"test_name": ..., "threshold_estimate": ...}` JSONs: intermediate schema.
- `alice.*` / `bob.*`: single demo-trial fixtures.

Current schema (v2): `utc,participant,session,test,trial,level,correct,rt_s,...`
CSVs paired with `{"schema": 2, ...}` JSONs in `../sessions/`.
