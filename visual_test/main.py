import time
import tkinter as tk
import traceback
from datetime import datetime, timezone
from tkinter import messagebox

try:
    from . import assets as A
    from . import game as G
    from .calibration import DisplayProfile, compute_geometry, nyquist_ok, pooling_flags
    from .datalogger import DataLogger
    from .tests import (
        Acuity4AFC,
        BrightnessMatch,
        ColorDiscrimination2IFC,
        ContrastDetection2IFC,
        MaskedGabor,
        QuitExperiment,
        SizeMatch,
        StaticColorBullseye,
        StaticContrast,
        StaticReactionTime,
        VernierJudgment,
    )
except ImportError:
    import assets as A  # type: ignore[no-redef]
    import game as G  # type: ignore[no-redef]
    from calibration import DisplayProfile, compute_geometry, nyquist_ok, pooling_flags
    from datalogger import DataLogger
    from tests import (
        Acuity4AFC,
        BrightnessMatch,
        ColorDiscrimination2IFC,
        ContrastDetection2IFC,
        MaskedGabor,
        QuitExperiment,
        SizeMatch,
        StaticColorBullseye,
        StaticContrast,
        StaticReactionTime,
        VernierJudgment,
    )


STAIR_DEFAULTS = {
    "brightness": dict(
        start_val=1.0,
        step_sizes=[0.3, 0.2, 0.1],
        n_reversals=8,
        min_val=0.0,
        max_val=1.8,
        rule="3D1U",
    ),
    "vernier": dict(
        start_val=-1.3,
        step_sizes=[0.3, 0.2, 0.1],
        n_reversals=8,
        min_val=-2.5,
        max_val=0.0,
        rule="3D1U",
    ),
    "masked": dict(
        start_val=-0.5,
        step_sizes=[0.3, 0.2, 0.1, 0.05],
        n_reversals=8,
        min_val=-3.0,
        max_val=0.0,
        rule="3D1U",
    ),
    "static_contrast": dict(
        start_val=-1.0,
        step_sizes=[0.3, 0.2, 0.1, 0.05],
        n_reversals=8,
        min_val=-3.0,
        max_val=0.0,
        rule="3D1U",
    ),
    "static_color": dict(
        start_val=1.5,
        step_sizes=[0.3, 0.2, 0.1],
        n_reversals=8,
        min_val=0.5,
        max_val=2.0,
        rule="3D1U",
    ),
    "contrast": dict(
        start_val=-1.0,
        step_sizes=[0.3, 0.2, 0.1, 0.05],
        n_reversals=8,
        min_val=-3.0,
        max_val=0.0,
        rule="3D1U",
    ),
    "acuity": dict(
        start_val=0.3,
        step_sizes=[0.2, 0.1, 0.05],
        n_reversals=8,
        min_val=-0.2,
        max_val=1.0,
        rule="3D1U",
    ),
    "color": dict(
        start_val=1.3,
        step_sizes=[0.3, 0.2, 0.1],
        n_reversals=8,
        min_val=0.3,
        max_val=2.0,
        rule="3D1U",
    ),
}

FIXED_TRIAL_KINDS = ("sizematch", "static_rt")

TEST_ORDER = [
    ("STATIC contrast: stripes there or not? (Y/N)", "static_contrast"),
    ("STATIC colour bullseye: center redder or bluer? (R/B)", "static_color"),
    ("STATIC reaction time: press SPACE when disc pops (no memory)", "static_rt"),
    ("Brightness match: same grey on dark vs light ring?", "brightness"),
    ("Vernier: lower bar left or right? (Left/Right)", "vernier"),
    ("Size match: adjust disc, Enter when equal (bias)", "sizematch"),
    ("Masked Gabor: stripes there? (Y/N, brief+mask)", "masked"),
    ("Contrast detection (2IFC Gabor, 3D1U)", "contrast"),
    ("Acuity (4AFC Landolt C, 3D1U)", "acuity"),
    ("Colour (2IFC isoluminant, 3D1U)", "color"),
]

INSTR = {
    "static_contrast": "STATIC: stripes on screen now?\nKeys: Y = yes, N = no",
    "static_color": (
        "STATIC: is the CENTER redder or bluer than the ring?\nKeys: R = redder, B = bluer"
    ),
    "static_rt": (
        "STATIC: wait, then press SPACE the instant the disc pops up.\nNo memory, just react."
    ),
    "brightness": "STATIC: are the two grey patches the SAME grey?\nKeys: Y = same, N = different",
    "vernier": "STATIC: is the LOWER bar LEFT or RIGHT of the upper?\nKeys: Left / Right arrows",
    "sizematch": "STATIC: Up/Down resizes right disc, Enter when it equals left.",
    "masked": "STATIC: brief flash then noise — stripes there?\nKeys: Y = yes, N = no",
    "contrast": "Which interval had the striped patch?\nKeys: 1 = first, 2 = second",
    "acuity": "Which way does the C gap point?\nKeys: Up / Right / Down / Left arrows",
    "color": "Which interval had the DIFFERENT colours?\nKeys: 1 = first, 2 = second",
}


class VisualTestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Visual Test (EXPERIMENTAL - not for real use)")
        self.root.geometry("1000x1200")
        self.root.resizable(True, True)
        self.logger = DataLogger(participant_id="guest")
        self.ppd_var = None
        self.display_profile = DisplayProfile()
        self._session_running = False
        self.name_var = tk.StringVar(value=self.logger.participant_id)
        self.load_profile()
        self.build()
        self.refresh_cal_label()

    def profile_path(self):
        import os

        return os.path.join(os.path.dirname(self.logger.data_dir), "display_profile.json")

    def load_profile(self):
        import json
        import os

        try:
            path = self.profile_path()
            if os.path.exists(path):
                if os.path.getsize(path) > 1024 * 1024:
                    return
                with open(path, encoding="utf-8") as f:
                    doc = json.load(f)
                self.display_profile = DisplayProfile.from_meta(doc)
        except (OSError, ValueError):
            pass

    def save_profile(self):
        import json
        import os

        try:
            path = self.profile_path()
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.display_profile.as_meta(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except (OSError, ValueError, TypeError) as e:
            self.log(f"Profile save failed: {e}")

    def refresh_cal_label(self):
        s = self.display_profile.summary()
        if s == "not calibrated":
            self.cal_lbl.set("Not calibrated — run before comparing across computers")
        else:
            self.cal_lbl.set(f"Calibrated (saved): {s}")

    def build(self):
        tk.Label(self.root, text="👁 VISION ARCADE", font=("Arial", 20, "bold")).pack(pady=(8, 0))
        tk.Label(
            self.root,
            text="Experimental playground — lab-grade stimuli, arcade shell.\n"
            "Setup: dim room, 60cm viewing distance, fullscreen stimulus window.",
            justify="center",
        ).pack()
        self.game_hdr = tk.Frame(self.root)
        self.game_hdr.pack(fill="x", padx=16, pady=(6, 0))
        self.avatar_lbl = tk.Label(self.game_hdr)
        self.avatar_lbl.pack(side="left", padx=(0, 8))
        self.avatar_img = None
        self.game_lbl = tk.StringVar(value="Level 0 — 0 XP")
        tk.Label(self.game_hdr, textvariable=self.game_lbl, font=("Arial", 12, "bold")).pack(
            side="left"
        )
        self.badge_lbl = tk.StringVar(value="")
        tk.Label(self.game_hdr, textvariable=self.badge_lbl, fg="#b8860b", font=("Arial", 10)).pack(
            side="left", padx=8
        )
        pf = tk.Frame(self.root)
        pf.pack(fill="x", padx=16, pady=4)

        # Player info frame
        player_info = tk.Frame(pf)
        player_info.pack(fill="x")
        tk.Label(player_info, text="Player:", font=("Arial", 11, "bold")).pack(side="left")
        tk.Entry(player_info, textvariable=self.name_var, width=22).pack(side="left", padx=6)
        tk.Button(player_info, text="Use profile", command=self.switch_profile).pack(side="left")

        # Difficulty frame
        difficulty_frame = tk.Frame(pf)
        difficulty_frame.pack(fill="x", pady=(4, 0))
        label = tk.Label(difficulty_frame, text="Difficulty:", font=("Arial", 11, "bold"))
        label.pack(side="left", padx=(0, 10))
        self.difficulty_var = tk.StringVar(value="normal")
        difficulties = [
            ("Easy", "easy"),
            ("Normal", "normal"),
            ("Hard", "hard"),
            ("Extreme", "extreme"),
        ]
        for text, value in difficulties:
            rb = tk.Radiobutton(
                difficulty_frame, text=text, variable=self.difficulty_var, value=value
            )
            rb.pack(side="left", padx=2)

        self.profile_lbl = tk.StringVar(value=f"Saving to: {self.logger.csv_path}")
        tk.Label(self.root, textvariable=self.profile_lbl, fg="#555").pack()
        try:
            A.ensure_assets()
        except Exception:
            pass
        self.refresh_game_header()
        gf = tk.LabelFrame(self.root, text="Display geometry (for pixels-per-degree)")
        gf.pack(fill="x", padx=16, pady=4)
        self.diag_var = tk.DoubleVar(value=24.0)
        self.dist_var = tk.DoubleVar(value=60.0)
        self.ppd_var = tk.DoubleVar(value=43.0)
        tk.Label(gf, text="Diagonal (in):").grid(row=0, column=0, sticky="e")
        tk.Spinbox(
            gf,
            from_=10,
            to=50,
            increment=0.5,
            textvariable=self.diag_var,
            width=6,
            command=self.update_ppd,
        ).grid(row=0, column=1)
        tk.Label(gf, text="Distance (cm):").grid(row=0, column=2, sticky="e")
        tk.Spinbox(
            gf,
            from_=20,
            to=200,
            increment=5,
            textvariable=self.dist_var,
            width=6,
            command=self.update_ppd,
        ).grid(row=0, column=3)
        tk.Label(gf, text="ppd:").grid(row=0, column=4, sticky="e")
        tk.Label(gf, textvariable=self.ppd_var, font=("Arial", 10, "bold")).grid(
            row=0, column=5, sticky="w"
        )
        self.ppd_note = tk.StringVar(value="")
        tk.Label(gf, textvariable=self.ppd_note, fg="#a00").grid(
            row=1, column=0, columnspan=6, sticky="w"
        )
        tk.Label(
            gf,
            text="Resolution is read from the primary monitor only; "
            "run the stimulus on that display or verify ppd manually.",
            fg="#555",
        ).grid(row=2, column=0, columnspan=6, sticky="w")
        self.diag_var.trace_add("write", lambda *a: self.update_ppd())
        self.dist_var.trace_add("write", lambda *a: self.update_ppd())
        self.update_ppd()
        cf = tk.LabelFrame(self.root, text="Display calibration (no photometer; estimates only)")
        cf.pack(fill="x", padx=16, pady=4)
        self.cal_lbl = tk.StringVar(value="Not calibrated — run before comparing across computers")
        tk.Label(cf, textvariable=self.cal_lbl, fg="#555", justify="left", wraplength=640).pack(
            anchor="w", padx=6
        )
        tk.Button(cf, text="Run display calibration (~1 min)", command=self.run_calibration).pack(
            anchor="w", padx=6, pady=4
        )
        tk.Button(cf, text="Check session pooling", command=self.check_pooling).pack(
            anchor="w", padx=6, pady=(0, 4)
        )
        tk.Button(cf, text="View results vs past sessions", command=self.open_results).pack(
            anchor="w", padx=6, pady=(0, 4)
        )
        self.pool_lbl = tk.StringVar(value="")
        tk.Label(cf, textvariable=self.pool_lbl, fg="#555", justify="left", wraplength=640).pack(
            anchor="w", padx=6
        )
        f = tk.Frame(self.root)
        f.pack(pady=8, fill="x", padx=16)
        tk.Label(f, text="Test:").grid(row=0, column=0, sticky="w")
        self.build_tests(f)

    def switch_profile(self):
        name = self.name_var.get().strip() or "guest"
        self.logger.set_participant(name)
        self.profile_lbl.set(f"Saving to: {self.logger.csv_path}")
        self.log(f"Profile: {self.logger.participant_id} -> {self.logger.csv_path}")
        self.refresh_game_header()

    def refresh_game_header(self):
        try:
            prof = G.load_profile(self.logger.participant_id, self.logger.data_dir)
            xp = int(prof.get("xp", 0))
            lvl, into, need = G.xp_into_level(xp)
            if need:
                lvl_txt = f"Lv {lvl} {self.logger.participant_id} — {xp} XP ({into}/{need} to next)"
            else:
                lvl_txt = f"Lv {lvl} {self.logger.participant_id} — {xp} XP (MAX)"
            self.game_lbl.set(lvl_txt)
            badges = prof.get("badges") or []
            if badges:
                names = [G.BADGES.get(b, b) for b in badges[:4]]
                more = f" +{len(badges) - 4}" if len(badges) > 4 else ""
                self.badge_lbl.set("🏅 " + " · ".join(names) + more)
            else:
                self.badge_lbl.set("No badges yet — play a mission!")
            try:
                import hashlib

                digest = hashlib.md5(self.logger.participant_id.encode("utf-8")).hexdigest()
                ap = A.avatar_path(int(digest, 16) % 4)
                if ap:
                    self.avatar_img = A.photo_image(ap, size=(40, 40))
                    if self.avatar_img is not None:
                        self.avatar_lbl.configure(image=self.avatar_img)
            except Exception:
                pass
        except Exception:
            pass

    def best_ranks(self):
        try:
            from . import norms as N
        except ImportError:
            import norms as N  # type: ignore[no-redef]
        best = {}
        try:
            infos = N.list_sessions(self.logger.data_dir)
            docs = []
            for info in infos:
                try:
                    doc = N.load_session(info["path"])
                except Exception:
                    continue
                if doc is None:
                    continue
                docs.append((info, doc))
            values_by_kind = {}
            kinds_by_doc = []
            for info, doc in docs:
                per_doc = {}
                try:
                    tests = doc.get("tests") or []
                except Exception:
                    tests = []
                for s in tests:
                    if not isinstance(s, dict):
                        continue
                    if s.get("aborted") or s.get("truncated"):
                        continue
                    kind = s.get("kind") or N.kind_of(s.get("test", ""))
                    if not kind:
                        continue
                    try:
                        got = N.extract(kind, s)
                    except Exception:
                        continue
                    if got is None:
                        continue
                    values_by_kind.setdefault(kind, []).append(got["value"])
                    per_doc.setdefault(kind, []).append(got["value"])
                kinds_by_doc.append((info, doc, per_doc))
            for _info, doc, per_doc in kinds_by_doc:
                try:
                    group = {}
                    for kind, vals in values_by_kind.items():
                        own = per_doc.get(kind, [])
                        if own:
                            remaining = list(vals)
                            for v in own:
                                try:
                                    remaining.remove(v)
                                except ValueError:
                                    pass
                            group[kind] = remaining
                        else:
                            group[kind] = vals
                    for card in N.score_session(doc, group):
                        pct = card.get("percentile")
                        if pct is None:
                            continue
                        k = card.get("kind")
                        if k and pct > best.get(k, -1):
                            best[k] = pct
                except Exception:
                    continue
        except Exception:
            pass
        return best

    def update_ppd(self):
        try:
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
            geo = compute_geometry(w, h, float(self.diag_var.get()), float(self.dist_var.get()))
            self.ppd_var.set(round(geo.ppd, 1))
            ok = nyquist_ok(2.0, geo.ppd)
            self.ppd_note.set("" if ok else "Warning: ppd too low for 2 cpd Gabor (aliasing risk)")
        except Exception as e:
            self.ppd_note.set(f"Geometry error: {e}")

    @property
    def ppd(self):
        try:
            return max(1.0, float(self.ppd_var.get()))
        except Exception:
            return 43.0

    def build_tests(self, f):
        self.test_vars = {}
        best = self.best_ranks()
        tk.Label(f, text="MISSIONS — pick your run", font=("Arial", 11, "bold")).grid(
            row=1, column=0, sticky="w"
        )
        for i, (_title, v) in enumerate(TEST_ORDER):
            var = tk.BooleanVar(value=(v == "static_contrast"))
            self.test_vars[v] = var
            icon, title, tag = A.mission_meta(v)
            pct = best.get(v)
            rank = f"  [best {pct:.0f}%]" if pct is not None else ""
            tk.Checkbutton(f, text=f"{icon} {title}{rank} — {tag}", variable=var).grid(
                row=i + 2, column=0, sticky="w"
            )
        tk.Label(f, text="Trials (max):").grid(row=0, column=1, sticky="e")
        self.n_var = tk.IntVar(value=40)
        tk.Spinbox(f, from_=20, to=80, textvariable=self.n_var, width=5).grid(row=1, column=1)
        self.fb_var = tk.BooleanVar(value=True)
        tk.Checkbutton(f, text="Feedback", variable=self.fb_var).grid(row=2, column=1, sticky="w")
        self.fs_var = tk.BooleanVar(value=True)
        tk.Checkbutton(f, text="Fullscreen stimulus", variable=self.fs_var).grid(
            row=3, column=1, sticky="w"
        )
        tk.Label(f, text="Seed (blank=random):").grid(row=15, column=0, sticky="w")
        self.seed_var = tk.StringVar(value="")
        tk.Entry(f, textvariable=self.seed_var, width=14).grid(row=15, column=1, sticky="w")
        btns = tk.Frame(self.root)
        btns.pack(pady=8)
        tk.Button(btns, text="Select all", command=self.select_all).pack(side="left", padx=4)
        tk.Button(btns, text="Clear", command=self.select_none).pack(side="left", padx=4)
        tk.Button(
            btns,
            text="START SESSION",
            font=("Arial", 12, "bold"),
            bg="#2e7d32",
            fg="white",
            command=self.start_session,
        ).pack(side="left", padx=8)
        self.status = tk.StringVar(value="Ready")
        tk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w").pack(
            side="bottom", fill="x"
        )
        self.logbox = tk.Text(self.root, height=10, state="disabled")
        self.logbox.pack(fill="both", expand=True, padx=12, pady=6)

    def log(self, m):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", m + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")
        self.status.set(m)
        self.root.update_idletasks()

    def run_calibration(self):
        win = tk.Toplevel(self.root)
        win.title("Display calibration - Esc quits")
        win.geometry("800x600")
        if self.fs_var.get():
            try:
                win.attributes("-fullscreen", True)
            except Exception:
                pass
        canvas = tk.Canvas(win, width=800, height=600, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        win.update()
        try:
            try:
                from .calwizard import run_wizard
            except ImportError:
                from calwizard import run_wizard
            run_wizard(canvas, win, self.display_profile)
            self.ask_display_settings()
            self.display_profile.calibrated_utc = datetime.now(timezone.utc).isoformat()
            self.save_profile()
            self.refresh_cal_label()
            self.logger.meta.update(self.display_profile.as_meta())
            try:
                self.logger.save()
            except Exception:
                pass
            self.cal_lbl.set(f"Calibrated: {self.display_profile.summary()}")
            self.log(f"Display calibration: {self.display_profile.summary()}")
        except QuitExperiment as e:
            self.log(f"Calibration aborted: {e}")
        except (TimeoutError, RuntimeError) as e:
            self.log(f"Calibration stopped: {e}")
            try:
                messagebox.showwarning("Calibration stopped", str(e))
            except Exception:
                pass
        except Exception as e:
            traceback.print_exc()
            try:
                messagebox.showerror("Calibration error", str(e))
            except Exception:
                pass
        finally:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass

    def check_pooling(self):
        import glob
        import json
        import os

        if self.display_profile.summary() == "not calibrated":
            self.pool_lbl.set("Calibrate this display first — nothing to compare yet.")
            self.log(self.pool_lbl.get())
            return
        sessions = {}
        for path in glob.glob(os.path.join(self.logger.data_dir, "*.json")):
            if os.path.abspath(path) == os.path.abspath(self.logger.json_path):
                continue
            try:
                with open(path) as f:
                    doc = json.load(f)
                prof = DisplayProfile.from_meta(doc.get("meta", {}))
                if prof.summary() == "not calibrated":
                    continue
                sessions[os.path.basename(path)] = prof
            except Exception:
                continue
        flags = pooling_flags(self.display_profile, sessions)
        if not sessions:
            self.pool_lbl.set("No prior calibrated sessions to compare.")
        elif not flags:
            self.pool_lbl.set(f"{len(sessions)} session(s): comparable.")
        else:
            lines = [f"{k}: {', '.join(v)}" for k, v in list(flags.items())[:5]]
            more = f" (+{len(flags) - 5} more)" if len(flags) > 5 else ""
            self.pool_lbl.set(f"{len(flags)}/{len(sessions)} differ: " + "; ".join(lines) + more)
        self.log(self.pool_lbl.get())

    def ask_display_settings(self):
        d = tk.Toplevel(self.root)
        d.title("Display settings")
        d.transient(self.root)
        d.grab_set()
        bright = tk.IntVar(value=self.display_profile.brightness_pct or 100)
        amb = tk.StringVar(value=self.display_profile.ambient or "dim room")
        night_off = tk.BooleanVar(
            value=self.display_profile.night_mode_off
            if self.display_profile.night_mode_off is not None
            else True
        )
        notes = tk.StringVar(value=self.display_profile.notes or "")
        tk.Label(d, text="Screen brightness setting (%) — from the OS/display OSD:").pack(
            anchor="w", padx=10, pady=(8, 0)
        )
        tk.Spinbox(d, from_=0, to=100, textvariable=bright, width=6).pack(anchor="w", padx=10)
        tk.Label(d, text="Ambient light:").pack(anchor="w", padx=10, pady=(8, 0))
        tk.OptionMenu(d, amb, "dark room", "dim room", "office", "daylight").pack(
            anchor="w", padx=10
        )
        tk.Checkbutton(d, text="Night mode / blue-light filter is OFF", variable=night_off).pack(
            anchor="w", padx=10, pady=4
        )
        tk.Label(d, text="Notes (display model, etc.):").pack(anchor="w", padx=10)
        tk.Entry(d, textvariable=notes, width=40).pack(anchor="w", padx=10)
        done = []

        def _save():
            done.append(1)
            try:
                d.destroy()
            except Exception:
                pass

        def _cancel():
            try:
                d.destroy()
            except Exception:
                pass

        btns = tk.Frame(d)
        btns.pack(pady=10)
        tk.Button(btns, text="Save", command=_save).pack(side="left", padx=6)
        tk.Button(btns, text="Cancel", command=_cancel).pack(side="left", padx=6)
        d.protocol("WM_DELETE_WINDOW", _cancel)
        d.wait_window()
        if done:
            self.display_profile.brightness_pct = max(0, min(100, int(bright.get())))
            self.display_profile.ambient = amb.get()
            self.display_profile.night_mode_off = bool(night_off.get())
            self.display_profile.notes = notes.get().strip()

    def open_results(self):
        try:
            try:
                from .viewer import open_viewer
            except ImportError:
                from viewer import open_viewer
            open_viewer(self.root, self.logger.data_dir)
        except Exception as e:
            self.log(f"Results viewer failed: {e}")

    def session_seed(self):
        raw = (self.seed_var.get() or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            self.log(f"Bad seed {raw!r}; using random.")
            try:
                messagebox.showwarning("Bad seed", f"{raw!r} is not an integer; using random.")
            except Exception:
                pass
            return None

    def get_difficulty_adjustment(self):
        """Get adjustment for test difficulty based on user selection - modifies start_val"""
        difficulty = self.difficulty_var.get()
        if difficulty == "easy":
            return -1.0  # Easier: start with stronger stimulus (higher start_val)
        elif difficulty == "normal":
            return 0.0  # Normal: no adjustment
        elif difficulty == "hard":
            return 1.0  # Harder: start with weaker stimulus (lower start_val)
        elif difficulty == "extreme":
            return 2.0  # Extreme: start with much weaker stimulus
        else:
            return 0.0  # Default to normal

    def make_test(self, kind, n, fb, seed=None):
        ppd = self.ppd
        try:
            diag = float(self.diag_var.get())
        except Exception:
            diag = 24.0
        try:
            dist = float(self.dist_var.get())
        except Exception:
            dist = 60.0
        self.logger.meta.update(
            display_ppd=round(ppd, 1),
            display_diag_in=diag,
            display_dist_cm=dist,
            screen_px=(self.root.winfo_screenwidth(), self.root.winfo_screenheight()),
            **self.display_profile.as_meta(),
        )

        base = dict(n_trials=n, feedback=fb, practice_trials=3, seed=seed)
        sp = STAIR_DEFAULTS.get(kind)
        if sp:
            # Create a copy to avoid modifying the original
            adjusted_sp = sp.copy()
            # Apply difficulty adjustment to start_val
            difficulty_adj = self.get_difficulty_adjustment()
            original_start = adjusted_sp["start_val"]
            # Subtract because: easier = higher start_val
            new_start = original_start - difficulty_adj

            # Clamp to reasonable bounds (but respect the original min/max)
            min_bound = adjusted_sp.get("min_val", -10.0)
            max_bound = adjusted_sp.get("max_val", 10.0)
            new_start = max(min_bound, min(max_bound, new_start))

            adjusted_sp["start_val"] = new_start
        else:
            adjusted_sp = sp

        if kind == "brightness":
            return BrightnessMatch(
                "Brightness same/diff", self.logger, ppd, dict(adjusted_sp), **base
            )
        if kind == "vernier":
            return VernierJudgment("Vernier L/R", self.logger, ppd, dict(adjusted_sp), **base)
        if kind == "sizematch":
            return SizeMatch(
                "Size match bias", self.logger, n_trials=n, ppd=ppd, seed=seed, feedback=fb
            )
        if kind == "masked":
            return MaskedGabor("Masked Gabor Y/N", self.logger, ppd, dict(adjusted_sp), **base)
        if kind == "static_contrast":
            return StaticContrast(
                "Static Contrast Y/N", self.logger, ppd, dict(adjusted_sp), **base
            )
        if kind == "static_color":
            return StaticColorBullseye(
                "Static Bullseye R/B", self.logger, ppd, dict(adjusted_sp), **base
            )
        if kind == "static_rt":
            return StaticReactionTime(
                "Static Reaction Time", self.logger, n_trials=n, ppd=ppd, seed=seed, feedback=fb
            )
        if kind == "contrast":
            return ContrastDetection2IFC(
                "Contrast 2IFC", self.logger, ppd, dict(adjusted_sp), **base
            )
        if kind == "acuity":
            return Acuity4AFC("Acuity 4AFC", self.logger, ppd, dict(adjusted_sp), **base)
        return ColorDiscrimination2IFC("Colour 2IFC", self.logger, ppd, dict(adjusted_sp), **base)

    def selected_kinds(self):
        return [v for _, v in TEST_ORDER if self.test_vars[v].get()]

    def select_all(self):
        for var in self.test_vars.values():
            var.set(True)

    def select_none(self):
        for var in self.test_vars.values():
            var.set(False)

    def briefing(self, canvas, win, kind, i, total, feedback=True):
        try:
            from .tests import wait_ms
        except ImportError:
            from tests import wait_ms  # type: ignore[no-redef]
        try:
            total = max(1, int(total))
        except (TypeError, ValueError, OverflowError):
            total = 1
        try:
            i = max(0, min(int(i), total - 1))
        except (TypeError, ValueError, OverflowError):
            i = 0
        icon, title, tag = A.mission_meta(kind)
        if feedback:
            try:
                A.play_async("click", widget=win)
            except Exception:
                pass
        w = canvas.winfo_width() or 800
        bar_w = int(w * 0.6)
        x0 = (w - bar_w) // 2
        canvas.delete("all")
        canvas.create_text(
            w // 2,
            200,
            text=f"{icon}  MISSION {i + 1}/{total}",
            font=("Arial", 26, "bold"),
            fill="white",
        )
        canvas.create_text(w // 2, 250, text=f"{title} — {tag}", font=("Arial", 16), fill="gold")
        canvas.create_text(w // 2, 275, text="(any key skips)", font=("Arial", 11), fill="#999")
        canvas.create_rectangle(x0, 300, x0 + bar_w, 322, outline="white")
        fill = int(bar_w * i / total)
        if fill:
            canvas.create_rectangle(x0, 300, x0 + fill, 322, fill="#2e7d32", outline="")
        win.update()
        skip, gone = [], []

        def _brief_key(e):
            skip.append(1)

        win.bind("<KeyPress>", _brief_key)
        win.focus_force()
        try:
            for n in ("3", "2", "1", "GO!"):
                if skip:
                    break
                canvas.delete("count")
                canvas.create_text(
                    w // 2, 380, text=n, font=("Arial", 40, "bold"), fill="yellow", tags="count"
                )
                win.update()
                try:
                    wait_ms(win, 350 if n != "GO!" else 500)
                except RuntimeError:
                    gone.append(1)
                    break
                if skip:
                    break
        finally:
            try:
                if win.winfo_exists():
                    win.unbind("<KeyPress>")
            except Exception:
                pass
        if gone:
            raise RuntimeError("Stimulus window closed")

    def start_session(self):
        if self._session_running:
            self.log("A session is already running — finish it first.")
            return
        want = (self.name_var.get() or "").strip()
        if want and want != self.logger.participant_id:
            self.switch_profile()
        kinds = self.selected_kinds()
        if not kinds:
            self.log("No tests selected — tick at least one checkbox.")
            try:
                messagebox.showwarning("No tests selected", "Tick at least one test first.")
            except Exception:
                pass
            return
        try:
            n = int(self.n_var.get())
        except Exception:
            self.log("Bad trial count; using 40.")
            n = 40
        n = max(1, min(200, n))
        try:
            fb = bool(self.fb_var.get())
        except Exception:
            fb = True
        self._session_running = True
        seed_base = self.session_seed()
        for kind in kinds:
            if kind not in FIXED_TRIAL_KINDS:
                need = STAIR_DEFAULTS[kind]["n_reversals"]
                if n < need * 3:
                    self.log(
                        f"Warning: {n} trials thin for {need} reversals; suggest >= {need * 3}"
                    )
        win = tk.Toplevel(self.root)
        win.title("Stimulus - press keys as instructed (Esc quits)")
        win.geometry("800x600")
        if self.fs_var.get():
            try:
                win.attributes("-fullscreen", True)
            except Exception:
                pass
        canvas = tk.Canvas(win, width=800, height=600, bg="gray", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        win.update()
        done_kinds = []
        try:
            for i, kind in enumerate(kinds):
                seed = None if seed_base is None else seed_base + i
                test = self.make_test(kind, n, fb, seed=seed)
                self.log(f"Starting {test.name} ({i + 1}/{len(kinds)})")
                try:
                    self.briefing(canvas, win, kind, i, len(kinds), feedback=fb)
                except Exception:
                    pass
                instr = INSTR[kind]
                instr += f"\n\nTest {i + 1} of {len(kinds)}."
                if kind not in FIXED_TRIAL_KINDS:
                    instr += "\n3 easy practice trials first."
                instr += "\nPress any key to begin (Esc skips the rest)."
                canvas.delete("all")
                canvas.create_text(400, 300, text=instr, font=("Arial", 16), justify="center")
                win.update()
                try:
                    self.wait_key(win)
                except QuitExperiment:
                    self.log(f"Session stopped before {test.name}; {len(done_kinds)} done.")
                    break
                canvas.delete("all")
                win.update()
                try:
                    out = test.run_gui(canvas, win)
                except QuitExperiment as e:
                    self.log(f"Aborted by participant during {test.name}: {e}")
                    break
                self.log_results(kind, test, out)
                done_kinds.append(kind)
            self.log(f"Session done: {len(done_kinds)}/{len(kinds)} tests completed.")
        except (TimeoutError, RuntimeError) as e:
            self.log(f"Stopped: {e}")
            try:
                messagebox.showwarning("Stopped", str(e))
            except Exception:
                pass
        except Exception as e:
            traceback.print_exc()
            try:
                messagebox.showerror("Error", str(e))
            except Exception:
                pass
        finally:
            try:
                self._session_running = False
            except Exception:
                pass
            try:
                self.logger.save()
                self.log(f"Saved to {self.logger.csv_path}")
                self.show_session_report()
            except Exception as e:
                self.log(f"Save failed: {e}")
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass

    def show_session_report(self):
        try:
            try:
                from .viewer import interpret_session, session_report_text
            except ImportError:
                from viewer import interpret_session, session_report_text  # type: ignore[no-redef]
            text = session_report_text(self.logger.json_path, self.logger.data_dir)
            if not text:
                return
            self.log(text)
            xp_line = ""
            try:
                got = interpret_session(self.logger.json_path, self.logger.data_dir)
                cards = got["cards"] if got else []
                if not any(isinstance(c, dict) and c.get("display") for c in cards):
                    raise ValueError("no scored tests; skipping XP")
                calibrated = self.display_profile.summary() != "not calibrated"
                prof, gained, new_badges, leveled = G.add_session(
                    self.logger.participant_id,
                    self.logger.data_dir,
                    cards,
                    session_id=self.logger.session_id,
                    calibrated=calibrated,
                )
                lvl = G.level_for_xp(prof.get("xp", 0))
                self.logger.meta.update(
                    game_xp=gained, game_level=lvl, game_badges=list(prof.get("badges") or [])
                )
                try:
                    self.logger.save()
                except Exception:
                    pass
                self.refresh_game_header()
                bits = [f"+{gained} XP  (Lv {lvl}, {prof.get('xp', 0)} total)"]
                if new_badges:
                    bits.append("New badges: " + ", ".join(G.BADGES.get(b, b) for b in new_badges))
                if leveled:
                    bits.append(f"LEVEL UP! Now Lv {lvl}")
                    try:
                        A.play_async("levelup", widget=self.root)
                    except Exception:
                        pass
                xp_line = " | ".join(bits)
                self.log("Arcade: " + xp_line)
            except Exception as e:
                self.log(f"XP skipped: {e}")
            rep = tk.Toplevel(self.root)
            rep.title("Session results (experimental, not clinical)")
            rep.geometry("680x560")
            body = tk.Text(rep, wrap="word")
            body.pack(fill="both", expand=True, padx=10, pady=10)
            if xp_line:
                body.insert("end", "🎮 " + xp_line + "\n\n")
            body.insert("end", text)
            body.configure(state="disabled")
            tk.Button(rep, text="Close", command=rep.destroy).pack(pady=(0, 10))
            rep.bind("<Escape>", lambda _e: rep.destroy())
        except Exception as e:
            self.log(f"Report skipped: {e}")

    def log_results(self, kind, test, out):
        if kind == "static_rt":
            med, rts, misses, fas = out
            med_txt = f"{med * 1000:.0f} ms" if rts else "no hits"
            self.log(
                f"Done. Median RT={med_txt} over {len(rts)} hits, "
                f"{misses} misses, {fas} false starts"
            )
            messagebox.showinfo(
                "Done",
                f"{test.name}\nMedian RT: {med_txt}\n"
                f"Hits: {len(rts)} Misses: {misses}\nFalse starts: {fas}",
            )
        elif kind == "sizematch":
            score, per_trial = out
            detail = f" over {len(per_trial)} trials" if per_trial else ""
            self.log(f"Done. {test.name} score={score:.3f}{detail}")
            messagebox.showinfo("Done", f"{test.name}\nScore: {score:.3f}{detail}")
        else:
            thresh, levels, corrects, reversals = out
            self.log(f"Done. Threshold={thresh:.3f} log units over {len(levels)} trials")
            messagebox.showinfo(
                "Done", f"{test.name}\nThreshold: {thresh:.3f} log units\nTrials: {len(levels)}"
            )

    def wait_key(self, win):
        done, quit_ = [], []

        def h(e):
            if e.keysym == "Escape":
                quit_.append(1)
            else:
                done.append(1)

        win.bind("<KeyPress>", h)
        win.focus_force()
        try:
            while not done and not quit_:
                try:
                    if not win.winfo_exists():
                        raise RuntimeError("Stimulus window closed")
                    win.update()
                except RuntimeError:
                    raise
                except Exception as e:
                    raise RuntimeError(f"Stimulus window lost: {e}") from e
                time.sleep(0.02)
        finally:
            try:
                if win.winfo_exists():
                    win.unbind("<KeyPress>")
            except Exception:
                pass
        if quit_:
            raise QuitExperiment("Cancelled before start")


def main():
    r = tk.Tk()
    VisualTestApp(r)
    r.mainloop()


if __name__ == "__main__":
    main()
