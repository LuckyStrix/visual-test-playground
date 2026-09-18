"""Session results viewer: HumanBenchmark-style cards with local norms.

Opens a scrollable window listing every historic session (newest first).
Picking one shows a card per test: plain-language title, your score, a
percentile bar against this machine's past sessions, and sanity-check
caveats. Nothing leaves the machine; no clinical claims are made.
"""

from . import norms as N
from . import results as R


def interpret_session(path, data_dir):
    try:
        if not isinstance(path, str) or not isinstance(data_dir, str):
            return None
        doc = N.load_session(path)
        if doc is None:
            return None
        group = N.collect_norms(data_dir, exclude=path)
        cards = R.summarize_session(N.score_session(doc, group))["cards"]
        return {"path": path, "doc": doc, "cards": cards}
    except Exception:
        return None


def session_report_text(path, data_dir):
    """Full plain-text report for one session JSON. Returns None if unreadable."""
    got = interpret_session(path, data_dir)
    if got is None:
        return None
    doc = got["doc"]
    participant, session = N.session_label(doc)
    parts = [f"{participant} — {session}"]
    parts.append(R.summarize_session(got["cards"])["headline"])
    parts.append("")
    for card in got["cards"]:
        parts.append(_card_text(card))
        parts.append("")
    parts.append(R.WOW_EXPERIMENTAL)
    return "\n".join(parts)


def _dirs_for(data_dir, include_archive):
    try:
        try:
            from .export import target_dirs
        except ImportError:
            from export import target_dirs  # type: ignore[no-redef]
        return target_dirs(data_dir, include_archive)
    except Exception:
        return [data_dir]


def _sessions_in(dirs):
    out = []
    for d in dirs:
        out.extend(N.list_sessions(d))
    out.sort(key=lambda s: s["mtime"], reverse=True)
    return out


def _entry_text(s):
    if not isinstance(s, dict):
        return "(unreadable session)"
    try:
        part = s.get("participant", "?")
        sess = s.get("session", "?")
        n = s.get("n_tests", "?")
        try:
            n = int(n)
        except (TypeError, ValueError, OverflowError):
            n = "?"
        base = f"{part} — {sess} ({n} tests)"
        if s.get("source") and s["source"] not in ("sessions",):
            base += f" [{s['source']}]"
        return base
    except Exception:
        return "(unreadable session)"


def open_viewer(root, data_dir, tk_mod=None):
    import os

    if tk_mod is None:
        import tkinter as tk_mod

    win = tk_mod.Toplevel(root)
    win.title("Results vs past sessions (experimental, not clinical)")
    win.geometry("720x640")
    top = tk_mod.Frame(win)
    top.pack(fill="x", padx=10, pady=6)
    tk_mod.Label(top, text="Session:", font=("Arial", 11, "bold")).pack(side="left")
    include_archive = tk_mod.BooleanVar(value=False)
    sessions = _sessions_in(_dirs_for(data_dir, False))
    names = [_entry_text(s) for s in sessions]
    list_frame = tk_mod.Frame(top)
    list_frame.pack(side="left", fill="x", expand=True, padx=6)
    scroll = tk_mod.Scrollbar(list_frame, orient="vertical")
    box = tk_mod.Listbox(list_frame, height=8, yscrollcommand=scroll.set, exportselection=False)
    scroll.config(command=box.yview)
    scroll.pack(side="right", fill="y")
    for n in names:
        box.insert("end", n)
    box.pack(side="left", fill="x", expand=True)

    ctrl = tk_mod.Frame(win)
    ctrl.pack(fill="x", padx=10)
    tk_mod.Checkbutton(
        ctrl, text="Include legacy archive", variable=include_archive, command=lambda: refresh()
    ).pack(side="left")
    tk_mod.Button(ctrl, text="Refresh", command=lambda: refresh()).pack(side="left", padx=6)

    body = tk_mod.Text(win, wrap="word", state="disabled")
    body.pack(fill="both", expand=True, padx=10, pady=6)

    def render(text):
        body.configure(state="normal")
        body.delete("1.0", "end")
        body.insert("end", text)
        body.configure(state="disabled")

    def show(idx):
        if not sessions or idx is None:
            render("No sessions recorded yet. Run a session first.")
            return
        try:
            i = int(idx)
        except (TypeError, ValueError, OverflowError):
            render("No sessions recorded yet. Run a session first.")
            return
        if i < 0 or i >= len(sessions):
            render("That session is no longer listed — press Refresh.")
            return
        info = sessions[i]
        own_dir = os.path.dirname(info["path"])
        got = interpret_session(info["path"], own_dir)
        if got is None:
            render(f"Could not read {info['path']}.")
            return
        parts = [_entry_text(info)]
        head = R.summarize_session(got["cards"])["headline"]
        parts.append(head)
        parts.append("")
        for card in got["cards"]:
            parts.append(_card_text(card))
            parts.append("")
        parts.append(R.WOW_EXPERIMENTAL)
        render("\n".join(parts))

    def on_pick(_e=None):
        cur = box.curselection()
        show(cur[0] if cur else None)

    box.bind("<<ListboxSelect>>", on_pick)

    def refresh():
        nonlocal sessions, names
        sessions = _sessions_in(_dirs_for(data_dir, include_archive.get()))
        names = [_entry_text(s) for s in sessions]
        box.delete(0, "end")
        for n in names:
            box.insert("end", n)
        if sessions:
            box.selection_set(0)
            show(0)
        else:
            render("No sessions recorded yet. Run a session first.")

    if sessions:
        box.selection_set(0)
        show(0)
    else:
        render("No sessions recorded yet. Run a session first.")
    win.bind("<Escape>", lambda _e: win.destroy())


def _bar(percentile, width=20, xp=None):
    try:
        pct = float(percentile)
    except (TypeError, ValueError, OverflowError):
        pct = None
    import math as _math

    if pct is None or not _math.isfinite(pct):
        if xp:
            return f"(+{xp} XP; not enough past sessions to rank)"
        return "(not enough past sessions to rank)"
    pct = max(0.0, min(100.0, pct))
    fill = max(0, min(int(width), int(round(pct / 100.0 * width))))
    base = "[" + "★" * fill + "·" * (width - fill) + f"] {pct:.0f}% beat"
    if xp:
        base += f"  +{xp} XP"
    return base


def _card_text(card):
    if not isinstance(card, dict):
        return "(unreadable result card)"
    try:
        c = R.interpret(dict(card))
    except Exception:
        return "(unreadable result card)"
    try:
        try:
            from . import game as _G
        except ImportError:
            import game as _G  # type: ignore[no-redef]
        xp = _G.xp_for_card(card)
    except Exception:
        xp = 0
    xp_txt = f"  +{xp} XP" if xp else ""
    lines = [f"-- {c.get('title', '?')} --", c.get("what", "A visual judgment task.")]
    if c.get("display"):
        lines.append(f"Your result: {c['display']}{xp_txt}")
    else:
        lines.append("No score (aborted or incomplete).")
    try:
        n = int(c.get("n", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        n = 0
    band = c.get("band") or "unranked"
    if c.get("percentile") is not None:
        lines.append(_bar(c["percentile"], xp=xp if xp else None) + f"  ({band}, n={n})")
    elif n > 0:
        lines.append(f"(only {n} past session(s); need a few more to rank){xp_txt}")
    else:
        lines.append(f"(no past sessions to compare against yet){xp_txt}")
    caveats = c.get("caveats", [])
    if isinstance(caveats, str):
        caveats = [caveats]
    try:
        items = list(caveats or [])
    except TypeError:
        items = []
    for caveat in items:
        lines.append(f"! {caveat}")
    summary = c.get("summary")
    if isinstance(summary, dict) and "d_prime" in summary:
        lines.append(
            f"bias: hit {summary.get('hit_rate')} / FA {summary.get('fa_rate')} / "
            f"d' {summary.get('d_prime')}"
        )
    return "\n".join(lines)
