"""Headless exports: pooled CSV, per-kind summary, or a session report.

Examples:
  python3 -m visual_test.export --list
  python3 -m visual_test.export --pooled out.csv
  python3 -m visual_test.export --summary
  python3 -m visual_test.export --report <session.json>
"""

import argparse
import csv
import glob
import os
import sys

try:
    from . import norms as N
    from . import results as R
    from .viewer import session_report_text
except ImportError:
    import norms as N
    import results as R
    from viewer import session_report_text


def default_data_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sessions")


def target_dirs(data_dir, include_archive=False):
    dirs = [data_dir]
    if include_archive:
        arch = os.path.join(os.path.dirname(os.path.abspath(data_dir)), "legacy_archive")
        if os.path.isdir(arch) and os.path.abspath(arch) != os.path.abspath(data_dir):
            dirs.append(arch)
    return dirs


def pooled_rows(data_dir, include_archive=False):
    rows = []
    for d in target_dirs(data_dir, include_archive):
        for path in sorted(glob.glob(os.path.join(d, "*.json"))):
            doc = N.load_session(path)
            if doc is None:
                continue
            participant, session = N.session_label(doc)
            meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
            for s in doc.get("tests") or []:
                if not isinstance(s, dict):
                    continue
                kind = s.get("kind") or N.kind_of(s.get("test", ""))
                got = N.extract(kind, s) if kind else None
                extraction_failed = got is None and kind is not None and not (s.get("aborted") or s.get("truncated"))
                if got is None and not (s.get("aborted") or s.get("truncated")):
                    continue
                rows.append(
                    {
                        "session_file": os.path.basename(path),
                        "participant": participant,
                        "session": session,
                        "kind": kind,
                        "test": s.get("test", ""),
                        "value": got["value"] if got else "",
                        "display": got["display"] if got else "",
                        "n_trials": s.get("n_trials", ""),
                        "n_reversals": s.get("n_reversals", ""),
                        "reversals": ";".join(str(v) for v in (s.get("reversals") or [])),
                        "reversal_trials": ";".join(
                            str(v) for v in (s.get("reversal_trials") or [])
                        ),
                        "reversal_sd": s.get("reversal_sd", ""),
                        "weibull_alpha": s.get("weibull_alpha", ""),
                        "weibull_beta": s.get("weibull_beta", ""),
                        "weibull_guess": s.get("weibull_guess", ""),
                        "weibull_lapse": s.get("weibull_lapse", ""),
                        "aborted": bool(s.get("aborted", False)),
                        "truncated": bool(s.get("truncated", "")),
                        "hit_rate": s.get("hit_rate", ""),
                        "fa_rate": s.get("fa_rate", ""),
                        "d_prime": s.get("d_prime", ""),
                        "ppd": s.get("ppd", meta.get("display_ppd", "")),
                        "seed": s.get("seed", ""),
                        "start_val": s.get("start_val", ""),
                        "start_val_orig": s.get("start_val_orig", ""),
                        "difficulty": s.get("difficulty", meta.get("difficulty", "")),
                        "difficulty_adj": s.get("difficulty_adj", meta.get("difficulty_adj", "")),
                        "display_gamma": meta.get("display_gamma_estimate", ""),
                        "display_refresh_hz": meta.get("display_refresh_hz", ""),
                        "display_ambient": meta.get("display_ambient", ""),
                        "display_brightness_pct": meta.get("display_brightness_pct", ""),
                        "display_night_mode_off": meta.get("display_night_mode_off", ""),
                        "n_completed": s.get("n_completed", ""),
                        "n_presented": s.get("n_presented", ""),
                        "n_attempts": s.get("n_attempts", ""),
                        "n_retries": s.get("n_retries", ""),
                        "extraction_failed": extraction_failed,
                    }
                )
    return rows


def cmd_list(data_dir, include_archive=False):
    infos = []
    for d in target_dirs(data_dir, include_archive):
        infos.extend(N.list_sessions(d))
    infos.sort(key=lambda s: s["mtime"], reverse=True)
    if not infos:
        print("no sessions found in", data_dir)
        return 0
    for s in infos:
        print(f"{s['participant']}  {s['session']}  {s['n_tests']} tests  {s['path']}")
    return 0


def cmd_pooled(data_dir, out_path, include_archive=False):
    rows = pooled_rows(data_dir, include_archive)
    fields = [
        "session_file",
        "participant",
        "session",
        "kind",
        "test",
        "value",
        "display",
        "n_trials",
        "n_reversals",
        "reversals",
        "reversal_trials",
        "reversal_sd",
        "weibull_alpha",
        "weibull_beta",
        "weibull_guess",
        "weibull_lapse",
        "aborted",
        "truncated",
        "hit_rate",
        "fa_rate",
        "d_prime",
        "ppd",
        "seed",
        "start_val",
        "start_val_orig",
        "difficulty",
        "difficulty_adj",
        "display_gamma",
        "display_refresh_hz",
        "display_ambient",
        "display_brightness_pct",
        "display_night_mode_off",
        "n_completed",
        "n_presented",
        "n_attempts",
        "n_retries",
        "extraction_failed",
    ]
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp_path, out_path)
    print(f"wrote {len(rows)} rows to {out_path}")
    return 0


def cmd_summary(data_dir, include_archive=False):
    group = {}
    for d in target_dirs(data_dir, include_archive):
        part = N.collect_norms(d)
        for kind, vals in part.items():
            group.setdefault(kind, []).extend(vals)
    if not group:
        print("no scorable sessions in", data_dir)
        return 0
    for kind in sorted(group):
        d = N.describe(group[kind])
        if not d:
            continue
        info = R.TEST_INFO.get(kind, {})
        title = info.get("title", kind)
        print(
            f"{title} [{kind}]: n={d['n']} median={d['p50']:.3g} "
            f"p25={d['p25']:.3g} p75={d['p75']:.3g} range={d['lo']:.3g}..{d['hi']:.3g}"
        )
    return 0


def cmd_report(data_dir, session_path):
    own_dir = os.path.dirname(os.path.abspath(session_path))
    if os.path.abspath(own_dir) != os.path.abspath(data_dir):
        print(
            f"note: norms use the session's own directory ({own_dir}), "
            f"ignoring --data-dir ({data_dir})",
            file=sys.stderr,
        )
    text = session_report_text(session_path, own_dir)
    if text is None:
        print(f"could not read {session_path}", file=sys.stderr)
        return 1
    print(text)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="visual_test headless exports")
    ap.add_argument("--data-dir", default=default_data_dir())
    ap.add_argument("--list", action="store_true", help="list sessions")
    ap.add_argument("--pooled", metavar="OUT.csv", help="write pooled per-test CSV")
    ap.add_argument("--summary", action="store_true", help="print per-kind norm summary")
    ap.add_argument("--report", metavar="SESSION.json", help="print a session report")
    ap.add_argument(
        "--include-archive",
        action="store_true",
        help="include data/legacy_archive in --list/--pooled/--summary",
    )
    args = ap.parse_args(argv)
    if args.list:
        return cmd_list(args.data_dir, args.include_archive)
    if args.pooled:
        return cmd_pooled(args.data_dir, args.pooled, args.include_archive)
    if args.summary:
        return cmd_summary(args.data_dir, args.include_archive)
    if args.report:
        return cmd_report(args.data_dir, args.report)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
