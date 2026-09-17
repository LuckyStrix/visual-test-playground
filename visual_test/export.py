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
            for s in doc.get("tests") or []:
                if not isinstance(s, dict):
                    continue
                kind = s.get("kind") or N.kind_of(s.get("test", ""))
                got = N.extract(kind, s) if kind else None
                if got is None:
                    continue
                rows.append(
                    {
                        "session_file": os.path.basename(path),
                        "participant": participant,
                        "session": session,
                        "kind": kind,
                    "test": s.get("test", ""),
                    "value": got["value"],
                    "display": got["display"],
                    "n_trials": s.get("n_trials", ""),
                    "aborted": bool(s.get("aborted", False)),
                    "truncated": bool(s.get("truncated", False)),
                    "hit_rate": s.get("hit_rate", ""),
                    "fa_rate": s.get("fa_rate", ""),
                    "d_prime": s.get("d_prime", ""),
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
        "aborted",
        "truncated",
        "hit_rate",
        "fa_rate",
        "d_prime",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out_path}")
    return 0


def cmd_summary(data_dir):
    group = N.collect_norms(data_dir)
    if not group:
        print("no scorable sessions in", data_dir)
        return 0
    for kind in sorted(group):
        d = N.describe(group[kind])
        info = R.TEST_INFO.get(kind, {})
        title = info.get("title", kind)
        print(
            f"{title} [{kind}]: n={d['n']} median={d['p50']:.3g} "
            f"p25={d['p25']:.3g} p75={d['p75']:.3g} range={d['lo']:.3g}..{d['hi']:.3g}"
        )
    return 0


def cmd_report(data_dir, session_path):
    text = session_report_text(session_path, os.path.dirname(os.path.abspath(session_path)))
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
    ap.add_argument("--include-archive", action="store_true",
                    help="include data/legacy_archive in --list/--pooled")
    args = ap.parse_args(argv)
    if args.list:
        return cmd_list(args.data_dir, args.include_archive)
    if args.pooled:
        return cmd_pooled(args.data_dir, args.pooled, args.include_archive)
    if args.summary:
        return cmd_summary(args.data_dir)
    if args.report:
        return cmd_report(args.data_dir, args.report)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
