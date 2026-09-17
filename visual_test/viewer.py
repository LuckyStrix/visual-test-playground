"""Session results viewer: HumanBenchmark-style cards with local norms.

Opens a scrollable window listing every historic session (newest first).
Picking one shows a card per test: plain-language title, your score, a
percentile bar against this machine's past sessions, and sanity-check
caveats. Nothing leaves the machine; no clinical claims are made.
"""

from . import norms as N
from . import results as R


def interpret_session(path, data_dir):
    doc = N.load_session(path)
    if doc is None:
        return None
    group = N.collect_norms(data_dir, exclude=path)
    cards = R.summarize_session(N.score_session(doc, group))["cards"]
    return {"path": path, "doc": doc, "cards": cards}


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
    import os

    dirs = [data_dir]
    if include_archive:
        arch = os.path.join(os.path.dirname(os.path.abspath(data_dir)), "legacy_archive")
        if os.path.isdir(arch) and os.path.abspath(arch) != os.path.abspath(data_dir):
            dirs.append(arch)
    return dirs


def _sessions_in(dirs):
    out = []
    for d in dirs:
        out.extend(N.list_sessions(d))
    out.sort(key=lambda s: s["mtime"], reverse=True)
    return out


def _entry_text(s):
    base = f"{s['participant']} — {s['session']} ({s['n_tests']} tests)"
    if s.get("source") and s["source"] not in ("sessions",):
        base += f" [{s['source']}]"
    return base


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
    tk_mod.Checkbutton(ctrl, text="Include legacy archive", variable=include_archive,
                       command=lambda: refresh()).pack(side="left")
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
        info = sessions[idx]
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


def _bar(percentile, width=20):
    if percentile is None:
        return "(not enough past sessions to rank)"
    fill = int(round(percentile / 100.0 * width))
    return "[" + "#" * fill + "-" * (width - fill) + f"] {percentile:.0f}% beat"


def _card_text(card):
    c = R.interpret(dict(card))
    lines = [f"-- {c['title']} --", c["what"]]
    if c.get("display"):
        lines.append(f"Your result: {c['display']}")
    else:
        lines.append("No score (aborted or incomplete).")
    if c.get("percentile") is not None:
        lines.append(_bar(c["percentile"]) + f"  ({c['band']}, n={c['n']})")
    elif c.get("n", 0) > 0:
        lines.append(f"(only {c['n']} past session(s); need a few more to rank)")
    else:
        lines.append("(no past sessions to compare against yet)")
    for caveat in c.get("caveats", []):
        lines.append(f"! {caveat}")
    if "d_prime" in (c.get("summary") or {}):
        s = c["summary"]
        lines.append(
            f"bias: hit {s.get('hit_rate')} / FA {s.get('fa_rate')} / d' {s.get('d_prime')}"
        )
    return "\n".join(lines)
