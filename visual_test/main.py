import tkinter as tk
from tkinter import messagebox
import time
import traceback
from datetime import datetime, timezone
try:
    from .tests import (ContrastDetection2IFC, Acuity4AFC, ColorDiscrimination2IFC,
                        StaticContrast, StaticColorBullseye, StaticReactionTime,
                        CollinearJudgment, BrightnessMatch, VernierJudgment,
                        Subitizing, HueOrdering, SizeMatch, MaskedGabor,
                        QuitExperiment)
    from .datalogger import DataLogger
    from .calibration import compute_geometry, nyquist_ok, DisplayProfile, pooling_flags
except ImportError:
    from tests import (ContrastDetection2IFC, Acuity4AFC, ColorDiscrimination2IFC,
                       StaticContrast, StaticColorBullseye, StaticReactionTime,
                       CollinearJudgment, BrightnessMatch, VernierJudgment,
                       Subitizing, HueOrdering, SizeMatch, MaskedGabor,
                       QuitExperiment)
    from datalogger import DataLogger
    from calibration import compute_geometry, nyquist_ok, DisplayProfile, pooling_flags


STAIR_DEFAULTS = {
    'collinear': dict(start_val=-1.0, step_sizes=[0.3, 0.2, 0.1, 0.05],
                      n_reversals=8, min_val=-3.0, max_val=0.0, rule='3D1U'),
    'brightness': dict(start_val=1.0, step_sizes=[0.3, 0.2, 0.1],
                       n_reversals=8, min_val=0.0, max_val=1.8, rule='3D1U'),
    'vernier': dict(start_val=-1.3, step_sizes=[0.3, 0.2, 0.1],
                    n_reversals=8, min_val=-2.5, max_val=0.0, rule='3D1U'),
    'masked': dict(start_val=-0.5, step_sizes=[0.3, 0.2, 0.1, 0.05],
                   n_reversals=8, min_val=-3.0, max_val=0.0, rule='3D1U'),
    'static_contrast': dict(start_val=-1.0, step_sizes=[0.3, 0.2, 0.1, 0.05],
                            n_reversals=8, min_val=-3.0, max_val=0.0, rule='3D1U'),
    'static_color': dict(start_val=1.5, step_sizes=[0.3, 0.2, 0.1],
                         n_reversals=8, min_val=0.5, max_val=2.0, rule='3D1U'),
    'contrast': dict(start_val=-1.0, step_sizes=[0.3, 0.2, 0.1, 0.05],
                     n_reversals=8, min_val=-3.0, max_val=0.0, rule='3D1U'),
    'acuity': dict(start_val=0.3, step_sizes=[0.2, 0.1, 0.05],
                   n_reversals=8, min_val=-0.2, max_val=1.0, rule='3D1U'),
    'color': dict(start_val=1.3, step_sizes=[0.3, 0.2, 0.1],
                   n_reversals=8, min_val=0.3, max_val=2.0, rule='3D1U'),
}

FIXED_TRIAL_KINDS = ('subitize', 'hueorder', 'sizematch', 'static_rt')

TEST_ORDER = [
    ('STATIC contrast: stripes there or not? (Y/N)', 'static_contrast'),
    ('STATIC colour bullseye: center redder or bluer? (R/B)', 'static_color'),
    ('STATIC reaction time: press SPACE when disc pops (no memory)', 'static_rt'),
    ('Collinearity: are the two segments aligned? (Y/N)', 'collinear'),
    ('Brightness match: same grey on dark vs light ring?', 'brightness'),
    ('Vernier: lower bar left or right? (Left/Right)', 'vernier'),
    ('How many dots? (1-9 keys)', 'subitize'),
    ('Order 6 hues light->dark (click in order)', 'hueorder'),
    ('Size match: adjust disc, Enter when equal (bias)', 'sizematch'),
    ('Masked Gabor: stripes there? (Y/N, brief+mask)', 'masked'),
    ('Contrast detection (2IFC Gabor, 3D1U)', 'contrast'),
    ('Acuity (4AFC Landolt C, 3D1U)', 'acuity'),
    ('Colour (2IFC isoluminant, 3D1U)', 'color')]

INSTR = {
    'static_contrast': 'STATIC: stripes on screen now?\nKeys: Y = yes, N = no',
    'static_color': ('STATIC: is the CENTER redder or bluer than the ring?\n'
                       'Keys: R = redder, B = bluer'),
    'static_rt': ('STATIC: wait, then press SPACE the instant the disc pops up.\n'
                  'No memory, just react.'),
    'collinear': 'STATIC: are the two white bars ALIGNED?\nKeys: Y = aligned, N = offset',
    'brightness': 'STATIC: are the two grey patches the SAME grey?\nKeys: Y = same, N = different',
    'vernier': 'STATIC: is the LOWER bar LEFT or RIGHT of the upper?\nKeys: Left / Right arrows',
    'subitize': 'STATIC: how many dots? Press 1-9.',
    'hueorder': 'STATIC: click the 6 colour chips LIGHTEST to DARKEST.',
    'sizematch': 'STATIC: Up/Down resizes right disc, Enter when it equals left.',
    'masked': 'STATIC: brief flash then noise — stripes there?\nKeys: Y = yes, N = no',
    'contrast': 'Which interval had the striped patch?\nKeys: 1 = first, 2 = second',
    'acuity': 'Which way does the C gap point?\nKeys: Up / Right / Down / Left arrows',
    'color': 'Which interval had the DIFFERENT colours?\nKeys: 1 = first, 2 = second'}


class VisualTestApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Visual Test (EXPERIMENTAL - not for real use)')
        self.root.geometry('700x900')
        self.logger = DataLogger(participant_id='guest')
        self.ppd_var = None
        self.display_profile = DisplayProfile()
        self.load_profile()
        self.build()
        self.refresh_cal_label()

    def profile_path(self):
        import os
        return os.path.join(os.path.dirname(self.logger.data_dir),
                            'display_profile.json')

    def load_profile(self):
        import json
        import os
        try:
            if os.path.exists(self.profile_path()):
                with open(self.profile_path()) as f:
                    doc = json.load(f)
                self.display_profile = DisplayProfile.from_meta(doc)
        except Exception:
            pass

    def save_profile(self):
        import json
        try:
            with open(self.profile_path(), 'w') as f:
                json.dump(self.display_profile.as_meta(), f, indent=2)
        except Exception as e:
            self.log(f'Profile save failed: {e}')

    def refresh_cal_label(self):
        s = self.display_profile.summary()
        if s == 'not calibrated':
            self.cal_lbl.set('Not calibrated — run before comparing across computers')
        else:
            self.cal_lbl.set(f'Calibrated (saved): {s}')

    def build(self):
        tk.Label(self.root, text='Visual System Test', font=('Arial', 18, 'bold')).pack(pady=8)
        tk.Label(self.root,
                 text='Setup: dim room, 60cm viewing distance, fullscreen stimulus window.\n'
                      'Non-invasive screening only.',
                 justify='center').pack()
        pf = tk.Frame(self.root)
        pf.pack(fill='x', padx=16, pady=4)
        tk.Label(pf, text='Profile name:', font=('Arial', 11, 'bold')).pack(side='left')
        self.name_var = tk.StringVar(value=self.logger.participant_id)
        tk.Entry(pf, textvariable=self.name_var, width=22).pack(side='left', padx=6)
        tk.Button(pf, text='Use profile', command=self.switch_profile).pack(side='left')
        self.profile_lbl = tk.StringVar(value=f"Saving to: {self.logger.csv_path}")
        tk.Label(self.root, textvariable=self.profile_lbl, fg='#555').pack()
        gf = tk.LabelFrame(self.root, text='Display geometry (for pixels-per-degree)')
        gf.pack(fill='x', padx=16, pady=4)
        self.diag_var = tk.DoubleVar(value=24.0)
        self.dist_var = tk.DoubleVar(value=60.0)
        self.ppd_var = tk.DoubleVar(value=43.0)
        tk.Label(gf, text='Diagonal (in):').grid(row=0, column=0, sticky='e')
        tk.Spinbox(gf, from_=10, to=50, increment=0.5, textvariable=self.diag_var, width=6,
                   command=self.update_ppd).grid(row=0, column=1)
        tk.Label(gf, text='Distance (cm):').grid(row=0, column=2, sticky='e')
        tk.Spinbox(gf, from_=20, to=200, increment=5, textvariable=self.dist_var, width=6,
                   command=self.update_ppd).grid(row=0, column=3)
        tk.Label(gf, text='ppd:').grid(row=0, column=4, sticky='e')
        tk.Label(gf, textvariable=self.ppd_var, font=('Arial', 10, 'bold')).grid(
            row=0, column=5, sticky='w')
        self.ppd_note = tk.StringVar(value='')
        tk.Label(gf, textvariable=self.ppd_note, fg='#a00').grid(
            row=1, column=0, columnspan=6, sticky='w')
        tk.Label(gf, text='Resolution is read from the primary monitor only; '
                 'run the stimulus on that display or verify ppd manually.',
                 fg='#555').grid(row=2, column=0, columnspan=6, sticky='w')
        self.diag_var.trace_add('write', lambda *a: self.update_ppd())
        self.dist_var.trace_add('write', lambda *a: self.update_ppd())
        self.update_ppd()
        cf = tk.LabelFrame(self.root, text='Display calibration (no photometer; estimates only)')
        cf.pack(fill='x', padx=16, pady=4)
        self.cal_lbl = tk.StringVar(value='Not calibrated — run before comparing across computers')
        tk.Label(cf, textvariable=self.cal_lbl, fg='#555', justify='left',
                 wraplength=640).pack(anchor='w', padx=6)
        tk.Button(cf, text='Run display calibration (~1 min)',
                  command=self.run_calibration).pack(anchor='w', padx=6, pady=4)
        tk.Button(cf, text='Check session pooling',
                  command=self.check_pooling).pack(anchor='w', padx=6, pady=(0, 4))
        tk.Button(cf, text='View results vs past sessions',
                  command=self.open_results).pack(anchor='w', padx=6, pady=(0, 4))
        self.pool_lbl = tk.StringVar(value='')
        tk.Label(cf, textvariable=self.pool_lbl, fg='#555', justify='left',
                 wraplength=640).pack(anchor='w', padx=6)
        f = tk.Frame(self.root)
        f.pack(pady=8, fill='x', padx=16)
        tk.Label(f, text='Test:').grid(row=0, column=0, sticky='w')
        self.build_tests(f)

    def switch_profile(self):
        name = self.name_var.get().strip() or 'guest'
        self.logger.set_participant(name)
        self.profile_lbl.set(f"Saving to: {self.logger.csv_path}")
        self.log(f'Profile: {self.logger.participant_id} -> {self.logger.csv_path}')

    def update_ppd(self):
        try:
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
            geo = compute_geometry(w, h, float(self.diag_var.get()), float(self.dist_var.get()))
            self.ppd_var.set(round(geo.ppd, 1))
            ok = nyquist_ok(2.0, geo.ppd)
            self.ppd_note.set('' if ok else 'Warning: ppd too low for 2 cpd Gabor (aliasing risk)')
        except Exception as e:
            self.ppd_note.set(f'Geometry error: {e}')

    @property
    def ppd(self):
        try:
            return max(1.0, float(self.ppd_var.get()))
        except Exception:
            return 43.0

    def build_tests(self, f):
        self.test_vars = {}
        for i, (t, v) in enumerate(TEST_ORDER):
            var = tk.BooleanVar(value=(v == 'static_contrast'))
            self.test_vars[v] = var
            tk.Checkbutton(f, text=t, variable=var).grid(row=i + 1, column=0, sticky='w')
        tk.Label(f, text='Trials (max):').grid(row=0, column=1, sticky='e')
        self.n_var = tk.IntVar(value=40)
        tk.Spinbox(f, from_=20, to=80, textvariable=self.n_var, width=5).grid(row=1, column=1)
        self.fb_var = tk.BooleanVar(value=True)
        tk.Checkbutton(f, text='Feedback', variable=self.fb_var).grid(row=2, column=1, sticky='w')
        self.fs_var = tk.BooleanVar(value=True)
        tk.Checkbutton(f, text='Fullscreen stimulus', variable=self.fs_var).grid(
            row=3, column=1, sticky='w')
        tk.Label(f, text='Seed (blank=random):').grid(row=4, column=0, sticky='w')
        self.seed_var = tk.StringVar(value='')
        tk.Entry(f, textvariable=self.seed_var, width=14).grid(row=4, column=1, sticky='w')
        btns = tk.Frame(self.root)
        btns.pack(pady=8)
        tk.Button(btns, text='Select all', command=self.select_all).pack(side='left', padx=4)
        tk.Button(btns, text='Clear', command=self.select_none).pack(side='left', padx=4)
        tk.Button(btns, text='START SESSION', font=('Arial', 12, 'bold'),
                  bg='#2e7d32', fg='white', command=self.start_session).pack(side='left', padx=8)
        self.status = tk.StringVar(value='Ready')
        tk.Label(self.root, textvariable=self.status, relief='sunken', anchor='w').pack(
            side='bottom', fill='x')
        self.logbox = tk.Text(self.root, height=10, state='disabled')
        self.logbox.pack(fill='both', expand=True, padx=12, pady=6)

    def log(self, m):
        self.logbox.configure(state='normal')
        self.logbox.insert('end', m + '\n')
        self.logbox.see('end')
        self.logbox.configure(state='disabled')
        self.status.set(m)
        self.root.update_idletasks()

    def run_calibration(self):
        win = tk.Toplevel(self.root)
        win.title('Display calibration - Esc quits')
        win.geometry('800x600')
        if self.fs_var.get():
            try:
                win.attributes('-fullscreen', True)
            except Exception:
                pass
        canvas = tk.Canvas(win, width=800, height=600, bg='black',
                           highlightthickness=0)
        canvas.pack(fill='both', expand=True)
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
            self.log(f'Display calibration: {self.display_profile.summary()}')
        except QuitExperiment as e:
            self.log(f'Calibration aborted: {e}')
        except (TimeoutError, RuntimeError) as e:
            self.log(f'Calibration stopped: {e}')
            try:
                messagebox.showwarning('Calibration stopped', str(e))
            except Exception:
                pass
        except Exception as e:
            traceback.print_exc()
            try:
                messagebox.showerror('Calibration error', str(e))
            except Exception:
                pass
        finally:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass

    def check_pooling(self):
        import json
        import os
        import glob
        if self.display_profile.summary() == 'not calibrated':
            self.pool_lbl.set('Calibrate this display first — nothing to compare yet.')
            self.log(self.pool_lbl.get())
            return
        sessions = {}
        for path in glob.glob(os.path.join(self.logger.data_dir, '*.json')):
            if os.path.abspath(path) == os.path.abspath(self.logger.json_path):
                continue
            try:
                with open(path) as f:
                    doc = json.load(f)
                prof = DisplayProfile.from_meta(doc.get('meta', {}))
                if prof.summary() == 'not calibrated':
                    continue
                sessions[os.path.basename(path)] = prof
            except Exception:
                continue
        flags = pooling_flags(self.display_profile, sessions)
        if not sessions:
            self.pool_lbl.set('No prior calibrated sessions to compare.')
        elif not flags:
            self.pool_lbl.set(f'{len(sessions)} session(s): comparable.')
        else:
            lines = [f'{k}: {", ".join(v)}' for k, v in list(flags.items())[:5]]
            more = f' (+{len(flags) - 5} more)' if len(flags) > 5 else ''
            self.pool_lbl.set(f'{len(flags)}/{len(sessions)} differ: ' + '; '.join(lines) + more)
        self.log(self.pool_lbl.get())

    def ask_display_settings(self):
        d = tk.Toplevel(self.root)
        d.title('Display settings')
        d.transient(self.root)
        d.grab_set()
        bright = tk.IntVar(value=self.display_profile.brightness_pct or 100)
        amb = tk.StringVar(value=self.display_profile.ambient or 'dim room')
        night_off = tk.BooleanVar(value=self.display_profile.night_mode_off
                                  if self.display_profile.night_mode_off is not None
                                  else True)
        notes = tk.StringVar(value=self.display_profile.notes or '')
        tk.Label(d, text='Screen brightness setting (%) — from the OS/display OSD:').pack(
            anchor='w', padx=10, pady=(8, 0))
        tk.Spinbox(d, from_=0, to=100, textvariable=bright, width=6).pack(
            anchor='w', padx=10)
        tk.Label(d, text='Ambient light:').pack(anchor='w', padx=10, pady=(8, 0))
        tk.OptionMenu(d, amb, 'dark room', 'dim room', 'office',
                      'daylight').pack(anchor='w', padx=10)
        tk.Checkbutton(d, text='Night mode / blue-light filter is OFF',
                       variable=night_off).pack(anchor='w', padx=10, pady=4)
        tk.Label(d, text='Notes (display model, etc.):').pack(anchor='w', padx=10)
        tk.Entry(d, textvariable=notes, width=40).pack(anchor='w', padx=10)
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
        tk.Button(btns, text='Save', command=_save).pack(side='left', padx=6)
        tk.Button(btns, text='Cancel', command=_cancel).pack(side='left', padx=6)
        d.protocol('WM_DELETE_WINDOW', _cancel)
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
            self.log(f'Results viewer failed: {e}')

    def session_seed(self):
        raw = (self.seed_var.get() or '').strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            self.log(f'Bad seed {raw!r}; using random.')
            try:
                messagebox.showwarning('Bad seed', f'{raw!r} is not an integer; using random.')
            except Exception:
                pass
            return None

    def make_test(self, kind, n, fb, seed=None):
        ppd = self.ppd
        self.logger.meta.update(display_ppd=round(ppd, 1),
                                display_diag_in=float(self.diag_var.get()),
                                display_dist_cm=float(self.dist_var.get()),
                                screen_px=(self.root.winfo_screenwidth(),
                                           self.root.winfo_screenheight()),
                                **self.display_profile.as_meta())
        base = dict(n_trials=n, feedback=fb, practice_trials=3, seed=seed)
        sp = STAIR_DEFAULTS.get(kind)
        if kind == 'collinear':
            return CollinearJudgment('Collinearity Y/N', self.logger, ppd, dict(sp), **base)
        if kind == 'brightness':
            return BrightnessMatch('Brightness same/diff', self.logger, ppd, dict(sp), **base)
        if kind == 'vernier':
            return VernierJudgment('Vernier L/R', self.logger, ppd, dict(sp), **base)
        if kind == 'subitize':
            return Subitizing('Subitizing 1-9', self.logger, n_trials=n, feedback=fb,
                              ppd=ppd, seed=seed)
        if kind == 'hueorder':
            return HueOrdering('Hue ordering', self.logger, n_trials=n, ppd=ppd, seed=seed)
        if kind == 'sizematch':
            return SizeMatch('Size match bias', self.logger, n_trials=n, ppd=ppd, seed=seed)
        if kind == 'masked':
            return MaskedGabor('Masked Gabor Y/N', self.logger, ppd, dict(sp), **base)
        if kind == 'static_contrast':
            return StaticContrast('Static Contrast Y/N', self.logger, ppd, dict(sp), **base)
        if kind == 'static_color':
            return StaticColorBullseye('Static Bullseye R/B', self.logger, ppd, dict(sp), **base)
        if kind == 'static_rt':
            return StaticReactionTime('Static Reaction Time', self.logger, n_trials=n,
                                      ppd=ppd, seed=seed)
        if kind == 'contrast':
            return ContrastDetection2IFC('Contrast 2IFC', self.logger, ppd, dict(sp), **base)
        if kind == 'acuity':
            return Acuity4AFC('Acuity 4AFC', self.logger, ppd, dict(sp), **base)
        return ColorDiscrimination2IFC('Colour 2IFC', self.logger, ppd, dict(sp), **base)

    def selected_kinds(self):
        return [v for _, v in TEST_ORDER if self.test_vars[v].get()]

    def select_all(self):
        for var in self.test_vars.values():
            var.set(True)

    def select_none(self):
        for var in self.test_vars.values():
            var.set(False)

    def start_session(self):
        want = (self.name_var.get() or '').strip()
        if want and want != self.logger.participant_id:
            self.switch_profile()
        kinds = self.selected_kinds()
        if not kinds:
            self.log('No tests selected — tick at least one checkbox.')
            try:
                messagebox.showwarning('No tests selected', 'Tick at least one test first.')
            except Exception:
                pass
            return
        n, fb = self.n_var.get(), self.fb_var.get()
        seed_base = self.session_seed()
        for kind in kinds:
            if kind not in FIXED_TRIAL_KINDS:
                need = STAIR_DEFAULTS[kind]['n_reversals']
                if n < need * 3:
                    self.log(f'Warning: {n} trials thin for {need} reversals; '
                             f'suggest >= {need * 3}')
        win = tk.Toplevel(self.root)
        win.title('Stimulus - press keys as instructed (Esc quits)')
        win.geometry('800x600')
        if self.fs_var.get():
            try:
                win.attributes('-fullscreen', True)
            except Exception:
                pass
        canvas = tk.Canvas(win, width=800, height=600, bg='gray', highlightthickness=0)
        canvas.pack(fill='both', expand=True)
        win.update()
        done_kinds = []
        try:
            for i, kind in enumerate(kinds):
                seed = None if seed_base is None else seed_base + i
                test = self.make_test(kind, n, fb, seed=seed)
                self.log(f'Starting {test.name} ({i + 1}/{len(kinds)})')
                instr = INSTR[kind]
                instr += f'\n\nTest {i + 1} of {len(kinds)}.'
                if kind not in FIXED_TRIAL_KINDS:
                    instr += '\n3 easy practice trials first.'
                instr += '\nPress any key to begin (Esc skips the rest).'
                canvas.delete('all')
                canvas.create_text(400, 300, text=instr, font=('Arial', 16), justify='center')
                win.update()
                try:
                    self.wait_key(win)
                except QuitExperiment:
                    self.log(f'Session stopped before {test.name}; {len(done_kinds)} done.')
                    break
                canvas.delete('all')
                win.update()
                try:
                    out = test.run_gui(canvas, win)
                except QuitExperiment as e:
                    self.log(f'Aborted by participant during {test.name}: {e}')
                    break
                self.log_results(kind, test, out)
                done_kinds.append(kind)
            self.log(f'Session done: {len(done_kinds)}/{len(kinds)} tests completed.')
        except (TimeoutError, RuntimeError) as e:
            self.log(f'Stopped: {e}')
            try:
                messagebox.showwarning('Stopped', str(e))
            except Exception:
                pass
        except Exception as e:
            traceback.print_exc()
            try:
                messagebox.showerror('Error', str(e))
            except Exception:
                pass
        finally:
            try:
                self.logger.save()
                self.log(f'Saved to {self.logger.csv_path}')
                self.show_session_report()
            except Exception as e:
                self.log(f'Save failed: {e}')
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass

    def show_session_report(self):
        try:
            try:
                from .viewer import session_report_text
            except ImportError:
                from viewer import session_report_text
            text = session_report_text(self.logger.json_path, self.logger.data_dir)
            if not text:
                return
            self.log(text)
            rep = tk.Toplevel(self.root)
            rep.title('Session results (experimental, not clinical)')
            rep.geometry('680x560')
            body = tk.Text(rep, wrap='word')
            body.pack(fill='both', expand=True, padx=10, pady=10)
            body.insert('end', text)
            body.configure(state='disabled')
            tk.Button(rep, text='Close', command=rep.destroy).pack(pady=(0, 10))
            rep.bind('<Escape>', lambda _e: rep.destroy())
        except Exception as e:
            self.log(f'Report skipped: {e}')

    def log_results(self, kind, test, out):
        if kind == 'static_rt':
            med, rts, misses, fas = out
            med_txt = f'{med * 1000:.0f} ms' if rts else 'no hits'
            self.log(f'Done. Median RT={med_txt} over {len(rts)} hits, '
                     f'{misses} misses, {fas} false starts')
            messagebox.showinfo('Done', f'{test.name}\nMedian RT: {med_txt}\n'
                                f'Hits: {len(rts)} Misses: {misses}\nFalse starts: {fas}')
        elif kind == 'subitize':
            acc, (hits, total) = out
            self.log(f'Done. {test.name} accuracy={acc:.3f} ({hits}/{total})')
            messagebox.showinfo('Done', f'{test.name}\nAccuracy: {acc:.3f} ({hits}/{total})')
        elif kind in ('hueorder', 'sizematch'):
            score, per_trial = out
            detail = f' over {len(per_trial)} trials' if per_trial else ''
            self.log(f'Done. {test.name} score={score:.3f}{detail}')
            messagebox.showinfo('Done', f'{test.name}\nScore: {score:.3f}{detail}')
        else:
            thresh, levels, corrects, reversals = out
            self.log(f'Done. Threshold={thresh:.3f} log units over {len(levels)} trials')
            messagebox.showinfo('Done', f'{test.name}\nThreshold: {thresh:.3f} log units\n'
                                f'Trials: {len(levels)}')

    def wait_key(self, win):
        done, quit_ = [], []

        def h(e):
            if e.keysym == 'Escape':
                quit_.append(1)
            else:
                done.append(1)
        win.bind('<KeyPress>', h)
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
                    raise RuntimeError(f"Stimulus window lost: {e}")
                time.sleep(0.02)
        finally:
            try:
                if win.winfo_exists():
                    win.unbind('<KeyPress>')
            except Exception:
                pass
        if quit_:
            raise QuitExperiment("Cancelled before start")


def main():
    r = tk.Tk()
    VisualTestApp(r)
    r.mainloop()


if __name__ == '__main__':
    main()
