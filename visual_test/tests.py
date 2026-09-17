"""Static single-display tests: one scene on screen, judge what you see now.

Forced-choice tasks (2IFC/4AFC) feed every trial to the staircase.
Yes/no detection tasks (StaticContrast, MaskedGabor, CollinearJudgment,
BrightnessMatch) feed signal trials only; no-signal trials are logged as
catches and summarised as hit rate / false-alarm rate / d' so criterion
bias is flagged instead of silently becoming a "threshold".
"""
import time
import random
from statistics import NormalDist

import numpy as np

try:
    from PIL import ImageTk
except ImportError:
    ImageTk = None  # type: ignore[assignment]
try:
    from .staircase import Staircase
    from .stimuli import (gabor_patch, blank_patch, landolt_c, solid_patch, bullseye,
                          red_blue_pair, bright_disc, acuity_size_px, isoluminant_pair,
                          collinear_segments, brightness_pair, vernier_bars, dot_cloud,
                          hue_chips, size_pair, noise_mask, BG)
except ImportError:
    from staircase import Staircase
    from stimuli import (gabor_patch, blank_patch, landolt_c, solid_patch, bullseye,
                         red_blue_pair, bright_disc, acuity_size_px, isoluminant_pair,
                         collinear_segments, brightness_pair, vernier_bars, dot_cloud,
                         hue_chips, size_pair, noise_mask, BG)


class QuitExperiment(Exception):
    pass


RESPONSE_TIMEOUT_S = 60.0
MIN_RT_S = 0.1


class YesNoStats:
    """Hit / false-alarm bookkeeping for yes/no tasks.

    A transformed staircase is only valid on signal trials, so no-signal
    trials are excluded from it and reported here as FA rate + d'."""

    def __init__(self):
        self._said_yes_present = 0
        self._n_present = 0
        self._said_yes_absent = 0
        self._n_absent = 0

    def note(self, present, said_yes):
        if present:
            self._n_present += 1
            self._said_yes_present += bool(said_yes)
        else:
            self._n_absent += 1
            self._said_yes_absent += bool(said_yes)

    def summary(self):
        hr = self._said_yes_present / self._n_present if self._n_present else float('nan')
        far = self._said_yes_absent / self._n_absent if self._n_absent else float('nan')
        try:
            if self._n_present:
                hr_adj = (self._said_yes_present + 0.5) / (self._n_present + 1)
            else:
                hr_adj = float('nan')
            if self._n_absent:
                far_adj = (self._said_yes_absent + 0.5) / (self._n_absent + 1)
            else:
                far_adj = float('nan')
            dprime = NormalDist().inv_cdf(hr_adj) - NormalDist().inv_cdf(far_adj)
        except Exception:
            dprime = float('nan')

        def nz(v):
            return round(v, 3) if v == v else None
        return {'hit_rate': nz(hr), 'fa_rate': nz(far), 'd_prime': nz(dprime),
                'unreliable_bias': bool(far == far and far > 0.3)}


def attach_yesno_summary(logger, stats):
    if not logger.tests:
        logger.end_test(test='unknown', aborted=True, abort_reason='no summary to attach to')
    logger.tests[-1].update(stats.summary())
    logger.save()


def record_abort(logger, name, exc, kind=None, **partial):
    """Persist a partial summary when a run is aborted mid-test.

    Per-trial rows are already on disk; this ensures the JSON also records
    what happened instead of silently dropping the interrupted test."""
    try:
        logger.end_test(test=name, kind=kind, aborted=True,
                        abort_reason=f"{type(exc).__name__}: {exc}"[:200],
                        **partial)
    except Exception:
        pass
    try:
        logger.save()
    except Exception:
        pass


def pil_to_tk(img):
    if ImageTk is None:
        raise RuntimeError("Pillow ImageTk (tkinter) is required for GUI display")
    return ImageTk.PhotoImage(img)


def wait_ms(win, ms):
    """Pump the event loop for ~ms milliseconds. Returns actual elapsed ms.

    Note: Tkinter has no vsync; durations are approximate (expect ±10 ms
    jitter). For threshold work this is fine; do not use for TAC-grade
    temporal psychophysics without photodiode verification."""
    try:
        win.update()
    except Exception:
        raise RuntimeError("Stimulus window closed")
    t0 = time.perf_counter()
    while (time.perf_counter() - t0) * 1000 < ms:
        try:
            if not win.winfo_exists():
                raise RuntimeError("Stimulus window closed")
            win.update()
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Stimulus window lost: {e}")
        time.sleep(0.005)
    return (time.perf_counter() - t0) * 1000


END_KEYS = ['1', '2', 'Up', 'Down', 'Left', 'Right', 'space', 'Return',
            'y', 'Y', 'n', 'N', 'r', 'R', 'b', 'B', '3', '4', '5', '6',
            '7', '8', '9', 'Escape']


def center(canvas):
    canvas.update_idletasks()
    return canvas.winfo_width() / 2, canvas.winfo_height() / 2


def fixation(canvas, cx, cy):
    s = 12
    canvas.create_line(cx - s, cy, cx + s, cy, fill='white', width=2)
    canvas.create_line(cx, cy - s, cx, cy + s, fill='white', width=2)


def show_img(canvas, cx, cy, img):
    t = pil_to_tk(img)
    canvas.img = t
    canvas.create_image(cx, cy, image=t)


def show_img_at(canvas, x, y, img, slot='img'):
    t = pil_to_tk(img)
    setattr(canvas, slot, t)
    canvas.create_image(x, y, image=t)


def get_key(win, valid, timeout=RESPONSE_TIMEOUT_S):
    ans = []
    quit_ = []

    def h(e):
        if e.keysym == 'Escape':
            quit_.append(1)
        elif e.keysym in valid:
            ans.append(e.keysym)
    win.bind('<KeyPress>', h)
    win.focus_force()
    t0 = time.perf_counter()
    try:
        while not ans and not quit_:
            if not win.winfo_exists():
                raise RuntimeError("Stimulus window closed before response")
            if timeout is not None and (time.perf_counter() - t0) > timeout:
                raise TimeoutError(f"No response within {timeout:.0f}s")
            win.update()
            time.sleep(0.01)
    finally:
        try:
            if win.winfo_exists():
                win.unbind('<KeyPress>')
        except Exception:
            pass
    if quit_:
        raise QuitExperiment("Participant pressed Escape")
    return ans[0], time.perf_counter() - t0


def wait_dismiss(win, valid=None, timeout=None):
    """Dismiss a done/info screen. Esc dismisses without aborting the test."""
    ans = []
    done = []

    def h(e):
        if e.keysym == 'Escape':
            done.append('esc')
        elif valid is None or e.keysym in valid:
            ans.append(e.keysym)
            done.append('key')
    win.bind('<KeyPress>', h)
    win.focus_force()
    t0 = time.perf_counter()
    try:
        while not done:
            if not win.winfo_exists():
                raise RuntimeError("Stimulus window closed before response")
            if timeout is not None and (time.perf_counter() - t0) > timeout:
                raise TimeoutError(f"No response within {timeout:.0f}s")
            win.update()
            time.sleep(0.01)
    finally:
        try:
            if win.winfo_exists():
                win.unbind('<KeyPress>')
        except Exception:
            pass
    return ans[0] if ans else None


def feedback(canvas, cx, cy, ok, streak=0, points=0, win=None):
    canvas.delete('all')
    canvas.create_text(cx, cy, text='Correct' if ok else 'Wrong',
                       fill='green' if ok else 'red', font=('Arial', 28, 'bold'))
    if ok and streak >= 2:
        canvas.create_text(cx, cy + 48, text=f'{streak}x streak  +{points}',
                           fill='gold', font=('Arial', 16, 'bold'))
    elif ok and points:
        canvas.create_text(cx, cy + 48, text=f'+{points}',
                           fill='gold', font=('Arial', 16, 'bold'))
    canvas.update()
    try:
        try:
            from .assets import play_async
        except ImportError:
            from assets import play_async  # type: ignore[no-redef]
        if streak >= 3 and ok:
            play_async('streak', widget=win)
        else:
            play_async('correct' if ok else 'wrong', widget=win)
    except Exception:
        pass


def arcade_feedback(test_obj, canvas, win, cx, cy, ok):
    try:
        try:
            from . import game as _G
        except ImportError:
            import game as _G  # type: ignore[no-redef]
        streak = _G.note_result(test_obj, bool(ok))
        points = _G.points_for(bool(ok), streak)
    except Exception:
        streak, points = 0, 100 if ok else 0
    feedback(canvas, cx, cy, bool(ok), streak=streak, points=points, win=win)
    return streak, points


def _streak_reset(handle):
    try:
        try:
            from .game import reset_streak
        except ImportError:
            from game import reset_streak  # type: ignore[no-redef]
        reset_streak(handle)
    except Exception:
        pass


def arcade_toast(canvas, win, cx, cy, text, fill='yellow', size=18, sound=None):
    canvas.delete('all')
    canvas.create_text(cx, cy, text=text, fill=fill, font=('Arial', size, 'bold'))
    canvas.update()
    if sound:
        try:
            try:
                from .assets import play_async
            except ImportError:
                from assets import play_async  # type: ignore[no-redef]
            play_async(sound, widget=win)
        except Exception:
            pass


def await_space(win, t0, timeout_s=1.5):
    """Wait for SPACE after stimulus onset at t0. Returns RT in seconds,
    None on timeout, and raises QuitExperiment on Escape."""
    ans, quit_ = [], []

    def h(e):
        if e.keysym == 'Escape':
            quit_.append(1)
        elif e.keysym == 'space':
            ans.append(time.perf_counter() - t0)
    win.bind('<KeyPress>', h)
    win.focus_force()
    try:
        while not ans and not quit_ and (time.perf_counter() - t0) < timeout_s:
            win.update()
            time.sleep(0.005)
    finally:
        try:
            if win.winfo_exists():
                win.unbind('<KeyPress>')
        except Exception:
            pass
    if quit_:
        raise QuitExperiment("Participant pressed Escape")
    return ans[0] if ans else None


class Base:
    rule_default = '3D1U'
    required_keys = ('start_val', 'step_sizes', 'min_val', 'max_val')
    kind: str | None = None

    def __init__(self, name, logger, sp, n_trials=40, feedback=True, practice_trials=3,
                 seed=None):
        missing = [k for k in self.required_keys if k not in sp]
        if missing:
            raise ValueError(f"{name}: staircase_params missing {missing}")
        self.name = name
        self.logger = logger
        self.sp = sp
        self.n_trials = max(1, int(n_trials))
        self.feedback = feedback
        self.practice = max(0, int(practice_trials))
        self.seed = random.randrange(2 ** 31) if seed is None else int(seed)
        self.rng = random.Random(self.seed)
        self.np_rng = np.random.default_rng(self.seed)
        self.stair = Staircase(start_val=sp['start_val'], step_sizes=sp['step_sizes'],
                               n_reversals=sp.get('n_reversals', 8), n_trials_max=self.n_trials,
                               min_val=sp['min_val'], max_val=sp['max_val'],
                               rule=sp.get('rule', self.rule_default))

    def run_gui(self, canvas, win):
        _streak_reset(self)
        levels, corrects = [], []
        n_main = n_stair = n_catch = n_practice = 0
        max_total = self.practice + self.n_trials * 3
        t = 0
        try:
            while n_stair < self.n_trials and t < max_total:
                t += 1
                lvl = self.stair.current
                main = t > self.practice
                ok, rt, extra = self.trial(canvas, win, lvl, main)
                if not main:
                    n_practice += 1
                    self.logger.log_trial(test=self.name, trial=0, practice_trial=n_practice,
                                          level=lvl, correct=bool(ok), rt_s=round(rt, 3),
                                          practice=True,
                                          **{k: v for k, v in extra.items() if k != 'catch'})
                    _streak_reset(self)
                    continue
                n_main += 1
                if extra.get('catch'):
                    n_catch += 1
                    self.logger.log_trial(test=self.name, trial=n_main, level=lvl,
                                          correct='', rt_s=round(rt, 3), catch=True,
                                          **{k: v for k, v in extra.items() if k != 'catch'})
                    continue
                n_stair += 1
                levels.append(lvl)
                corrects.append(ok)
                _, done = self.stair.respond(ok)
                self.logger.log_trial(test=self.name, trial=n_main, level=lvl,
                                      correct=ok, rt_s=round(rt, 3), **extra)
                if done:
                    break
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt) as e:
            record_abort(self.logger, self.name, e, kind=self.kind,
                         n_trials=len(levels), n_catch=n_catch,
                         n_practice=n_practice,
                         n_reversals=len(self.stair.reversals),
                         reversals=[round(r, 3) for r in self.stair.reversals],
                         reversal_trials=list(self.stair.reversal_trials),
                         ppd=getattr(self, 'ppd', None), seed=self.seed)
            raise
        th = self.stair.threshold()
        truncated = len(self.stair.reversals) < self.stair.n_reversals
        clipped = bool(getattr(self, '_clipped_levels', []))
        rev_sd = self.stair.reversal_sd()
        self.logger.end_test(test=self.name, kind=self.kind,
                             threshold_log=round(th, 4),
                             n_trials=len(levels), n_catch=n_catch,
                             n_practice=n_practice,
                             clipped_levels=clipped,
                             n_reversals=len(self.stair.reversals),
                             reversals=[round(r, 3) for r in self.stair.reversals],
                             reversal_trials=list(self.stair.reversal_trials),
                             reversal_sd=round(rev_sd, 4) if rev_sd == rev_sd else None,
                             ppd=getattr(self, 'ppd', None),
                             rule=self.stair.rule, target_p=round(self.stair.target_p, 3),
                             step_sizes=list(self.stair.step_sizes),
                             threshold_n_discard=2, truncated=truncated,
                             seed=self.seed)
        self._save_plots(levels, corrects)
        cx, cy = center(canvas)
        canvas.delete('all')
        canvas.create_text(cx, cy, text=f'{self.name}\nThreshold {th:.3f} log units\nPress any key',
                           font=('Arial', 18), justify='center')
        win.update()
        wait_dismiss(win)
        return th, levels, corrects, list(self.stair.reversals)

    def _save_plots(self, levels, corrects):
        try:
            try:
                from .analysis import fit_weibull, plot_psychometric, plot_staircase
            except ImportError:
                from analysis import fit_weibull, plot_psychometric, plot_staircase
            import os
            import warnings
            stem = os.path.splitext(os.path.basename(self.logger.csv_path))[0]
            plot_dir = os.path.join(self.logger.data_dir, 'plots')
            os.makedirs(plot_dir, exist_ok=True)
            plot_staircase(list(levels), list(self.stair.reversals),
                           reversal_trials=list(self.stair.reversal_trials),
                           title=self.name, path=os.path.join(plot_dir, stem + '_staircase.png'))
            if levels and corrects:
                guess = getattr(self, 'fit_guess', None)
                if guess is None:
                    stats = getattr(self, 'stats', None)
                    if stats is not None:
                        s = stats.summary()
                        guess = s['fa_rate'] if s['fa_rate'] is not None else 0.0
                    else:
                        guess = 0.5
                log_like = getattr(self, 'fit_log_levels', True)
                fit = fit_weibull(levels, [bool(c) for c in corrects],
                                  guess=guess, log_levels=log_like)
                plot_psychometric(fit, title=self.name,
                                  path=os.path.join(plot_dir, stem + '_psychometric.png'))
                self.logger.tests[-1].update(
                    weibull_alpha=fit['alpha'], weibull_beta=fit['beta'])
                self.logger.save()
        except Exception as e:
            warnings.warn(f"{self.name}: plot/fit skipped ({e})")
            try:
                self.logger.tests[-1].update(plot_error=str(e)[:200])
                self.logger.save()
            except Exception:
                pass

    def trial(self, canvas, win, lvl, main):
        raise NotImplementedError


class ContrastDetection2IFC(Base):
    kind = 'contrast'
    fit_guess = 0.5
    fit_log_levels = True

    def __init__(self, name, logger, ppd, staircase_params, n_trials=40,
                 feedback=True, practice_trials=3,
                 seed=None):
        super().__init__(name, logger, staircase_params, n_trials, feedback, practice_trials,
                         seed=seed)
        self.ppd = ppd
        self.px = int(round(2.5 * ppd))

    def trial(self, canvas, win, lvl, main):
        contrast = 10 ** lvl
        first = self.rng.choice([True, False])
        cx, cy = center(canvas)
        for i, has in enumerate([first, not first]):
            canvas.delete('all')
            fixation(canvas, cx, cy)
            canvas.create_text(cx, cy - self.px, text=f'Interval {i + 1} of 2', fill='white')
            img = gabor_patch(self.px, self.ppd, 2.0, contrast) if has else blank_patch(self.px)
            show_img(canvas, cx, cy, img)
            win.update()
            wait_ms(win, 600)
            canvas.delete('all')
            fixation(canvas, cx, cy)
            win.update()
            wait_ms(win, 400)
        canvas.delete('all')
        canvas.create_text(cx, cy, text='1 = first   2 = second', fill='white', font=('Arial', 20))
        win.update()
        r, rt = get_key(win, ['1', '2'])
        ok = (r == '1') == first
        if self.feedback:
            arcade_feedback(self, canvas, win, cx, cy, ok)
            wait_ms(win, 400)
        return ok, rt, {'contrast': round(contrast, 5), 'target_first': first}


class Acuity4AFC(Base):
    kind = 'acuity'
    fit_guess = 0.25
    fit_log_levels = True

    def __init__(self, name, logger, ppd, staircase_params, n_trials=40,
                 feedback=True, practice_trials=3,
                 seed=None):
        super().__init__(name, logger, staircase_params, n_trials, feedback, practice_trials,
                         seed=seed)
        self.ppd = ppd
        self.map = {'Up': 90, 'Right': 0, 'Down': 270, 'Left': 180}

    def trial(self, canvas, win, lvl, main):
        if main:
            size_px = acuity_size_px(lvl, self.ppd)
        else:
            size_px = acuity_size_px(0.6, self.ppd)
        gap = self.rng.choice([0, 90, 180, 270])
        cx, cy = center(canvas)
        canvas.delete('all')
        fixation(canvas, cx, cy)
        show_img(canvas, cx, cy, landolt_c(int(size_px), gap))
        canvas.create_text(cx, cy + size_px, text='Arrow keys: gap direction', fill='white')
        win.update()
        r, rt = get_key(win, ['Up', 'Right', 'Down', 'Left'])
        ok = self.map[r] == gap
        if self.feedback:
            arcade_feedback(self, canvas, win, cx, cy, ok)
            wait_ms(win, 400)
        return ok, rt, {'logMAR': round(lvl, 3), 'gap_deg': gap, 'size_px': int(size_px)}


class ColorDiscrimination2IFC(Base):
    kind = 'color'
    fit_guess = 0.5
    fit_log_levels = True

    def __init__(self, name, logger, ppd, staircase_params, n_trials=40,
                 feedback=True, practice_trials=3,
                 seed=None):
        super().__init__(name, logger, staircase_params, n_trials, feedback, practice_trials,
                         seed=seed)
        self.ppd = ppd
        self.px = int(round(2.0 * ppd))

    def trial(self, canvas, win, lvl, main):
        delta = 10 ** lvl
        c1, c2 = isoluminant_pair(delta)
        first_diff = self.rng.choice([True, False])
        cx, cy = center(canvas)
        for i in range(2):
            diff_here = (i == 0) == first_diff
            canvas.delete('all')
            fixation(canvas, cx, cy)
            canvas.create_text(cx, cy - self.px, text=f'Interval {i + 1} of 2', fill='white')
            left = c1
            right = c1 if not diff_here else c2
            show_img(canvas, cx - self.px * 0.7, cy, solid_patch(self.px, left))
            show_img_at(canvas, cx + self.px * 0.7, cy, solid_patch(self.px, right), slot='img2')
            win.update()
            wait_ms(win, 800)
            canvas.delete('all')
            fixation(canvas, cx, cy)
            win.update()
            wait_ms(win, 400)
        canvas.delete('all')
        canvas.create_text(cx, cy, text='1 = first had different colours   2 = second',
                           fill='white', font=('Arial', 16))
        win.update()
        r, rt = get_key(win, ['1', '2'])
        ok = (r == '1') == first_diff
        if self.feedback:
            arcade_feedback(self, canvas, win, cx, cy, ok)
            wait_ms(win, 400)
        return ok, rt, {'delta': round(delta, 3), 'target_first': first_diff}


class StaticContrast(Base):
    """Static yes/no detection: Gabor present on 50% of trials.

    Absent trials are catches (excluded from the staircase); the summary
    reports hit rate, false-alarm rate and d' alongside the threshold.
    Keys: Y = yes I see stripes, N = no."""
    kind = 'static_contrast'
    fit_log_levels = True

    def __init__(self, name, logger, ppd, staircase_params, n_trials=40,
                 feedback=True, practice_trials=3,
                 seed=None):
        super().__init__(name, logger, staircase_params, n_trials, feedback, practice_trials,
                         seed=seed)
        self.ppd = ppd
        self.px = int(round(2.5 * ppd))
        self.stats = YesNoStats()

    def trial(self, canvas, win, lvl, main):
        contrast = 10 ** lvl
        if main:
            present = bool(self.np_rng.random() < 0.5)
        else:
            present = True
            contrast = max(contrast, 0.3)
        cx, cy = center(canvas)
        canvas.delete('all')
        fixation(canvas, cx, cy)
        show_img(canvas, cx, cy,
                 gabor_patch(self.px, self.ppd, 2.0, contrast) if present else blank_patch(self.px))
        canvas.create_text(cx, cy + self.px, text='Y = stripes there   N = nothing', fill='white')
        win.update()
        r, rt = get_key(win, ['y', 'Y', 'n', 'N'])
        said_yes = r.lower() == 'y'
        catch = main and not present
        if main:
            self.stats.note(present, said_yes)
        ok = said_yes == present
        if self.feedback and not catch:
            arcade_feedback(self, canvas, win, cx, cy, ok)
            wait_ms(win, 400)
        return ok, rt, {'contrast': round(contrast, 5), 'present': present,
                        'said_yes': said_yes, 'catch': catch}

    def run_gui(self, canvas, win):
        try:
            out = super().run_gui(canvas, win)
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt):
            attach_yesno_summary(self.logger, self.stats)
            raise
        attach_yesno_summary(self.logger, self.stats)
        return out


class StaticColorBullseye(Base):
    """Static concentric discs: is the CENTER redder or bluer than the surround?
    Keys: R = center redder, B = center bluer. Zero-delta trials are catches.

    Redder-center trials are treated as signal and bluer-center trials as
    noise, so the summary reports P(say redder | redder), P(say redder |
    bluer) and d' as a response-bias check."""
    kind = 'static_color'
    fit_guess = 0.5
    fit_log_levels = True

    def __init__(self, name, logger, ppd, staircase_params, n_trials=40,
                 feedback=True, practice_trials=3,
                 seed=None):
        super().__init__(name, logger, staircase_params, n_trials, feedback, practice_trials,
                         seed=seed)
        self.ppd = ppd
        self.px = int(round(2.5 * ppd))
        self.stats = YesNoStats()

    def trial(self, canvas, win, lvl, main):
        delta = 10 ** lvl
        if main and self.np_rng.random() < 0.15:
            cent_col, surr_col, truth = red_blue_pair(0, rng=self.np_rng)
            catch = True
        else:
            if not main:
                delta = max(delta, 40.0)
            cent_col, surr_col, truth = red_blue_pair(delta, rng=self.np_rng)
            catch = False
        cx, cy = center(canvas)
        canvas.delete('all')
        fixation(canvas, cx, cy)
        show_img(canvas, cx, cy, bullseye(self.px, cent_col, surr_col))
        canvas.create_text(cx, cy + self.px, text='R = center REDDER   B = center BLUER',
                           fill='white')
        win.update()
        r, rt = get_key(win, ['r', 'R', 'b', 'B'])
        said_redder = r.lower() == 'r'
        ok = (said_redder == truth) if truth is not None else False
        if main and not catch and truth is not None:
            self.stats.note(present=bool(truth), said_yes=said_redder)
        if self.feedback and not catch:
            arcade_feedback(self, canvas, win, cx, cy, ok)
            wait_ms(win, 400)
        return ok, rt, {'delta': round(delta, 2), 'center': cent_col, 'surround': surr_col,
                        'center_redder': truth, 'said_redder': said_redder, 'catch': catch}

    def run_gui(self, canvas, win):
        try:
            out = super().run_gui(canvas, win)
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt):
            attach_yesno_summary(self.logger, self.stats)
            raise
        attach_yesno_summary(self.logger, self.stats)
        return out


class CollinearJudgment(Base):
    """Two static bars — aligned (Y) or offset (N)?

    Aligned trials are catches (excluded from the staircase) that estimate
    the false-alarm rate; the staircase tracks offset trials only."""
    kind = 'collinear'

    def __init__(self, name, logger, ppd, staircase_params, n_trials=40,
                 feedback=True, practice_trials=3,
                 seed=None):
        super().__init__(name, logger, staircase_params, n_trials, feedback, practice_trials,
                         seed=seed)
        self.ppd = ppd
        self.px = int(round(4.0 * ppd))
        self.stats = YesNoStats()

    def trial(self, canvas, win, lvl, main):
        offset_px = 10 ** lvl * self.ppd if lvl > -3 else 0.0
        if main and self.np_rng.random() < 0.2:
            offset_px, catch = 0.0, True
        else:
            catch = False
            if not main:
                offset_px = max(offset_px, 0.15 * self.ppd)
            if self.np_rng.random() < 0.5:
                offset_px = -offset_px
        cx, cy = center(canvas)
        canvas.delete('all')
        fixation(canvas, cx, cy)
        show_img(canvas, cx, cy, collinear_segments(self.px, offset_px))
        canvas.create_text(cx, cy + self.px * 0.62, text='Y = aligned   N = offset', fill='white')
        win.update()
        r, rt = get_key(win, ['y', 'Y', 'n', 'N'])
        said_aligned = r.lower() == 'y'
        if main:
            self.stats.note(not catch, not said_aligned)
        ok = said_aligned == (abs(offset_px) < 0.5)
        if self.feedback and not catch:
            arcade_feedback(self, canvas, win, cx, cy, ok)
            wait_ms(win, 400)
        return ok, rt, {'offset_px': round(float(offset_px), 2), 'catch': catch,
                        'said_aligned': said_aligned}

    def run_gui(self, canvas, win):
        try:
            out = super().run_gui(canvas, win)
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt):
            attach_yesno_summary(self.logger, self.stats)
            raise
        attach_yesno_summary(self.logger, self.stats)
        return out


class BrightnessMatch(Base):
    """Identical grey patches on dark vs light rings — same (Y) or different (N)?

    Same-patch trials are catches (excluded from the staircase); the
    staircase tracks different-patch trials only, i.e. the luminance delta
    needed to overcome the simultaneous-contrast illusion."""
    kind = 'brightness'

    def __init__(self, name, logger, ppd, staircase_params, n_trials=40,
                 feedback=True, practice_trials=3,
                 seed=None):
        super().__init__(name, logger, staircase_params, n_trials, feedback, practice_trials,
                         seed=seed)
        self.ppd = ppd
        self.px = int(round(4.0 * ppd))
        self.stats = YesNoStats()

    def trial(self, canvas, win, lvl, main):
        delta = 10 ** lvl
        if not main:
            delta = max(delta, 30.0)
        same_trial = bool(self.np_rng.random() < 0.5) if main else False
        if same_trial:
            left_p, right_p = 128, 128
        else:
            shift = delta if self.np_rng.random() < 0.5 else -delta
            left_p, right_p = 128, int(np.clip(round(128 + shift), 20, 235))
        cx, cy = center(canvas)
        canvas.delete('all')
        fixation(canvas, cx, cy)
        show_img(canvas, cx, cy, brightness_pair(self.px, patch=left_p, patch_right=right_p))
        canvas.create_text(cx, cy + self.px * 0.62, text='Y = same grey   N = different',
                           fill='white')
        win.update()
        r, rt = get_key(win, ['y', 'Y', 'n', 'N'])
        said_same = r.lower() == 'y'
        catch = main and same_trial
        if main:
            self.stats.note(not same_trial, not said_same)
        ok = said_same == same_trial
        if self.feedback and not catch:
            arcade_feedback(self, canvas, win, cx, cy, ok)
            wait_ms(win, 400)
        return ok, rt, {'delta': round(float(delta), 2), 'patch_left': left_p,
                        'patch_right': right_p, 'same_trial': same_trial,
                        'said_same': said_same, 'catch': catch}

    def run_gui(self, canvas, win):
        try:
            out = super().run_gui(canvas, win)
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt):
            attach_yesno_summary(self.logger, self.stats)
            raise
        attach_yesno_summary(self.logger, self.stats)
        return out


class VernierJudgment(Base):
    """Static vernier — is the LOWER bar LEFT or RIGHT of the upper?"""
    kind = 'vernier'

    def __init__(self, name, logger, ppd, staircase_params, n_trials=40,
                 feedback=True, practice_trials=3,
                 seed=None):
        super().__init__(name, logger, staircase_params, n_trials, feedback, practice_trials,
                         seed=seed)
        self.ppd = ppd
        self.px = int(round(3.0 * ppd))

    def trial(self, canvas, win, lvl, main):
        raw_px = 10 ** lvl * self.ppd
        clipped = raw_px < 1.0
        offset_px = max(1.0, raw_px)
        if not main:
            offset_px = max(offset_px, 0.2 * self.ppd)
        if main and clipped:
            self._clipped_levels = getattr(self, '_clipped_levels', [])
            self._clipped_levels.append(round(float(lvl), 3))
        sign = 1 if self.np_rng.random() < 0.5 else -1
        cx, cy = center(canvas)
        canvas.delete('all')
        fixation(canvas, cx, cy)
        show_img(canvas, cx, cy, vernier_bars(self.px, sign * offset_px))
        canvas.create_text(cx, cy + self.px * 0.62, text='Left / Right arrow: lower bar?',
                           fill='white')
        win.update()
        r, rt = get_key(win, ['Left', 'Right'])
        ok = (r == 'Right') == (sign > 0)
        if self.feedback:
            arcade_feedback(self, canvas, win, cx, cy, ok)
            wait_ms(win, 400)
        return ok, rt, {'offset_px': round(float(offset_px), 2), 'lower_right': bool(sign > 0),
                        'offset_clipped': bool(main and clipped)}


class Subitizing:
    """Static dot cloud, press 1-9 for how many. Accuracy + RT per numerosity."""
    kind = 'subitize'

    def __init__(self, name, logger, n_trials=36, feedback=True, ppd=43.0, seed=None):
        self.name = name
        self.logger = logger
        self.n_trials = max(1, int(n_trials))
        self.feedback = feedback
        self.ppd = ppd
        self.seed = random.randrange(2 ** 31) if seed is None else int(seed)
        self.rng = random.Random(self.seed)

    def run_gui(self, canvas, win):
        _streak_reset(self)
        px = int(round(7.0 * self.ppd))
        dot_r = max(2, int(round(0.12 * self.ppd)))
        ns = []
        for _ in range((self.n_trials + 8) // 9):
            block = list(range(1, 10))
            self.rng.shuffle(block)
            ns.extend(block)
        ns = ns[:self.n_trials]
        self.rng.shuffle(ns)
        correct = 0
        try:
            for t, n in enumerate(ns):
                seed = self.rng.randrange(2 ** 31)
                cx, cy = center(canvas)
                canvas.delete('all')
                fixation(canvas, cx, cy)
                show_img(canvas, cx, cy, dot_cloud(px, n, dot_r=dot_r, seed=seed))
                canvas.create_text(cx, cy + 200, text='How many dots? press 1-9', fill='white')
                win.update()
                r, rt = get_key(win, [str(i) for i in range(1, 10)])
                ok = int(r) == n
                correct += ok
                self.logger.log_trial(test=self.name, trial=t + 1, level=n,
                                      correct=ok, rt_s=round(rt, 3), response=int(r), n_dots=n,
                                      seed=seed, px=px)
                if self.feedback:
                    arcade_feedback(self, canvas, win, cx, cy, ok)
                    wait_ms(win, 300)
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt) as e:
            record_abort(self.logger, self.name, e, kind=self.kind,
                         n_completed=len([r for r in self.logger.trials
                                         if r.get('test') == self.name]),
                         n_hit=correct, ppd=self.ppd, seed=self.seed)
            raise
        self.logger.end_test(test=self.name, kind=self.kind,
                             accuracy=round(correct / self.n_trials, 3),
                             n_trials=self.n_trials, ppd=self.ppd, seed=self.seed)
        cx, cy = center(canvas)
        canvas.delete('all')
        canvas.create_text(cx, cy,
                           text=f'{self.name}\nAccuracy {correct}/{self.n_trials}\nPress any key',
                           font=('Arial', 18), justify='center')
        win.update()
        wait_dismiss(win)
        return correct / self.n_trials, [correct, self.n_trials]


class HueOrdering:
    """Six static hue chips in scrambled order; click them light→dark.
    Score = mean displacement from correct order."""
    kind = 'hueorder'

    def __init__(self, name, logger, n_trials=6, ppd=43.0, seed=None,
                 feedback=True):
        self.name = name
        self.logger = logger
        self.n_trials = max(1, int(n_trials))
        self.ppd = ppd
        self.feedback = feedback
        self.seed = random.randrange(2 ** 31) if seed is None else int(seed)
        self.rng = random.Random(self.seed)
        self.np_rng = np.random.default_rng(self.seed)

    def _wait_click(self, canvas, win, order, picked, x0, spacing, hit_r, cy,
                      timeout=RESPONSE_TIMEOUT_S):
        done, quit_ = [], []

        def click(e, order=order):
            for i, ci in enumerate(order):
                x = x0 + i * spacing
                if abs(e.x - x) < hit_r and abs(e.y - cy) < hit_r and ci not in picked:
                    picked.append(ci)
                    done.append(1)

        def esc(e):
            if e.keysym == 'Escape':
                quit_.append(1)
        canvas.bind('<Button-1>', click)
        win.bind('<KeyPress>', esc)
        win.focus_force()
        t0 = time.perf_counter()
        try:
            while not done and not quit_:
                if not win.winfo_exists():
                    raise RuntimeError("Stimulus window closed before response")
                if (time.perf_counter() - t0) > timeout:
                    raise TimeoutError(f"No response within {timeout:.0f}s")
                win.update()
                time.sleep(0.02)
        finally:
            try:
                canvas.unbind('<Button-1>')
            except Exception:
                pass
            try:
                if win.winfo_exists():
                    win.unbind('<KeyPress>')
            except Exception:
                pass
        if quit_:
            raise QuitExperiment("Participant pressed Escape")

    def run_gui(self, canvas, win):
        _streak_reset(self)
        chips = hue_chips()
        lum = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in chips]
        truth = sorted(range(6), key=lambda i: lum[i])
        chip_px = int(round(1.8 * self.ppd))
        spacing = int(round(2.3 * self.ppd))
        hit_r = int(round(1.0 * self.ppd))
        scores = []
        try:
            for t in range(self.n_trials):
                order = list(range(6))
                self.rng.shuffle(order)
                cx, cy = center(canvas)
                picked = []
                x0 = cx - spacing * 2.5

                def redraw():
                    canvas.delete('all')
                    msg = f'Trial {t + 1}/{self.n_trials}: click chips LIGHTEST → DARKEST'
                    canvas.create_text(cx, cy - 160, text=msg,
                                       fill='white', font=('Arial', 14))
                    for i, ci in enumerate(order):
                        x = x0 + i * spacing
                        img = solid_patch(chip_px, chips[ci])
                        tk_img = pil_to_tk(img)
                        setattr(canvas, f'hue{i}', tk_img)
                        tag = f'chip{i}'
                        canvas.create_image(x, cy, image=tk_img, tags=tag)
                        if ci in picked:
                            canvas.create_text(x, cy + chip_px // 2 + 20,
                                                 text=str(picked.index(ci) + 1),
                                                 fill='yellow', font=('Arial', 18, 'bold'))
                    win.update()
                redraw()
                while len(picked) < 6:
                    self._wait_click(canvas, win, order, picked, x0, spacing, hit_r, cy)
                    redraw()
                score = float(np.mean([abs(picked.index(c) - truth.index(c)) for c in range(6)]))
                scores.append(score)
                self.logger.log_trial(test=self.name, trial=t + 1, level=round(score, 3),
                                      correct=score == 0, rt_s='', order=list(map(int, picked)))
                perfect = score == 0
                msg = 'PERFECT! Score 0.00' if perfect else f'Score {score:.2f} (0 = perfect)'
                arcade_toast(canvas, win, cx, cy, msg,
                             fill='gold' if perfect else 'white', size=20,
                             sound='correct' if (perfect and self.feedback) else None)
                wait_ms(win, 800)
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt) as e:
            record_abort(self.logger, self.name, e, kind=self.kind,
                         n_completed=len(scores), n_trials=self.n_trials,
                         ppd=self.ppd, seed=self.seed)
            raise
        m = float(np.mean(scores))
        self.logger.end_test(test=self.name, kind=self.kind,
                             mean_displacement=round(m, 3), n_trials=self.n_trials,
                             ppd=self.ppd, seed=self.seed)
        return m, scores


class SizeMatch:
    """Left disc fixed; Up/Down resizes right disc; Enter when equal.
    Reports bias = matched/reference - 1 per trial (illusion strength)."""
    kind = 'sizematch'

    def __init__(self, name, logger, n_trials=10, ppd=43.0, seed=None,
                 feedback=True):
        self.name = name
        self.logger = logger
        self.n_trials = max(1, int(n_trials))
        self.ppd = ppd
        self.feedback = feedback
        self.seed = random.randrange(2 ** 31) if seed is None else int(seed)
        self.rng = random.Random(self.seed)

    def run_gui(self, canvas, win):
        px, ref = int(round(10.0 * self.ppd)), 2.8 * self.ppd
        biases = []
        try:
            for t in range(self.n_trials):
                cmp_d = ref * float(self.rng.uniform(0.7, 1.3))
                cx, cy = center(canvas)
                while True:
                    cmp_d = min(max(cmp_d, ref * 0.3), ref * 3.0)
                    canvas.delete('all')
                    fixation(canvas, cx, cy)
                    show_img(canvas, cx, cy, size_pair(px, ref, cmp_d))
                    canvas.create_text(cx, cy + 240,
                                         text='Up/Down = resize right disc, Enter = equal',
                                       fill='white')
                    win.update()
                    r, _ = get_key(win, ['Up', 'Down', 'Return'])
                    if r == 'Up':
                        cmp_d *= 1.03
                    elif r == 'Down':
                        cmp_d /= 1.03
                    else:
                        break
                bias = cmp_d / ref - 1.0
                biases.append(bias)
                self.logger.log_trial(test=self.name, trial=t + 1, level=round(bias, 4),
                                      correct=True, rt_s='', matched=round(cmp_d, 1))
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt) as e:
            record_abort(self.logger, self.name, e, kind=self.kind,
                         n_completed=len(biases), n_trials=self.n_trials,
                         ppd=self.ppd, seed=self.seed)
            raise
        m = float(np.mean(biases))
        self.logger.end_test(test=self.name, kind=self.kind,
                             mean_bias=round(m, 4), n_trials=self.n_trials,
                             ppd=self.ppd, seed=self.seed)
        cx, cy = center(canvas)
        canvas.delete('all')
        canvas.create_text(cx, cy, text=f'{self.name}\nMean bias {m * 100:+.1f}%\nPress any key',
                           font=('Arial', 18), justify='center')
        win.update()
        wait_dismiss(win)
        return m, biases


class MaskedGabor(Base):
    """Brief static Gabor (~50 ms) then noise mask. Y = stripes, N = nothing.

    Absent trials are catches (excluded from the staircase); the summary
    reports hit rate, false-alarm rate and d' alongside the threshold."""
    kind = 'masked'

    def __init__(self, name, logger, ppd, staircase_params, n_trials=40,
                 feedback=True, practice_trials=3,
                 seed=None):
        super().__init__(name, logger, staircase_params, n_trials, feedback, practice_trials,
                         seed=seed)
        self.ppd = ppd
        self.px = int(round(2.5 * ppd))
        self.stats = YesNoStats()

    def trial(self, canvas, win, lvl, main):
        contrast = 10 ** lvl
        present = True if not main else bool(self.np_rng.random() < 0.5)
        if not main:
            contrast = max(contrast, 0.5)
        dur = 50 if main else 300
        cx, cy = center(canvas)
        canvas.delete('all')
        fixation(canvas, cx, cy)
        show_img(canvas, cx, cy,
                 gabor_patch(self.px, self.ppd, 2.0, contrast) if present else blank_patch(self.px))
        win.update()
        shown_ms = wait_ms(win, dur)
        canvas.delete('all')
        show_img(canvas, cx, cy, noise_mask(self.px))
        win.update()
        mask_ms = wait_ms(win, 200)
        canvas.delete('all')
        canvas.create_text(cx, cy, text='Y = stripes   N = nothing',
                           fill='white', font=('Arial', 20))
        win.update()
        r, rt = get_key(win, ['y', 'Y', 'n', 'N'])
        said = r.lower() == 'y'
        catch = main and not present
        if main:
            self.stats.note(present, said)
        ok = said == present
        if self.feedback and not catch:
            arcade_feedback(self, canvas, win, cx, cy, ok)
            wait_ms(win, 400)
        return ok, rt, {'contrast': round(contrast, 5), 'present': present, 'dur_ms': dur,
                        'shown_ms': round(shown_ms, 1), 'mask_ms': round(mask_ms, 1),
                        'catch': catch}

    def run_gui(self, canvas, win):
        try:
            out = super().run_gui(canvas, win)
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt):
            attach_yesno_summary(self.logger, self.stats)
            raise
        attach_yesno_summary(self.logger, self.stats)
        return out


class StaticReactionTime:
    """Static simple reaction time: blank wait, disc pops up, press SPACE ASAP.
    No staircase; reports median RT and misses. Fixed trial count."""
    kind = 'static_rt'

    def __init__(self, name, logger, n_trials=30, ppd=43.0, seed=None,
                 feedback=True):
        self.name = name
        self.logger = logger
        self.n_trials = max(1, int(n_trials))
        self.ppd = ppd
        self.feedback = feedback
        self.seed = random.randrange(2 ** 31) if seed is None else int(seed)
        self.rng = random.Random(self.seed)

    def run_gui(self, canvas, win):
        _streak_reset(self)
        rts, misses, fas = [], 0, 0
        cx, cy = center(canvas)
        px = int(round(2.8 * self.ppd))
        try:
            for t in range(self.n_trials):
                while True:
                    canvas.delete('all')
                    fixation(canvas, cx, cy)
                    canvas.create_text(cx, cy - 100, text='Wait for the disc...', fill='white')
                    win.update()
                    early, quit_ = [], []

                    def pre(e):
                        if e.keysym == 'Escape':
                            quit_.append(1)
                        else:
                            early.append(1)
                    win.bind('<KeyPress>', pre)
                    win.focus_force()
                    foreperiod = self.rng.uniform(0.8, 2.5)
                    deadline = time.perf_counter() + foreperiod
                    while time.perf_counter() < deadline:
                        if not win.winfo_exists():
                            raise RuntimeError("Stimulus window closed before response")
                        try:
                            win.update()
                        except Exception as e:
                            raise RuntimeError(f"Stimulus window lost: {e}")
                        time.sleep(0.005)
                        if early or quit_:
                            break
                    try:
                        if win.winfo_exists():
                            win.unbind('<KeyPress>')
                    except Exception:
                        pass
                    if quit_:
                        raise QuitExperiment("Participant pressed Escape")
                    if early:
                        fas += 1
                        arcade_toast(canvas, win, cx, cy, 'Too soon! Wait for the disc.',
                                     fill='yellow', size=18,
                                     sound='wrong' if self.feedback else None)
                        wait_ms(win, 700)
                        continue
                    canvas.delete('all')
                    t0 = [None]
                    fixation(canvas, cx, cy)
                    show_img(canvas, cx, cy, bright_disc(px, lum=255, bg=BG))
                    win.update()
                    t0[0] = time.perf_counter()
                    rt = await_space(win, t0[0], timeout_s=1.5)
                    if rt is None:
                        misses += 1
                        self.logger.log_trial(test=self.name, trial=t + 1, level='n/a',
                                              correct=False, rt_s='', miss=True, fa=False,
                                              anticipatory=False,
                                              foreperiod_s=round(foreperiod, 3))
                    elif rt < MIN_RT_S:
                        fas += 1
                        self.logger.log_trial(test=self.name, trial=t + 1, level='n/a',
                                              correct=False, rt_s=round(rt, 4), miss=False, fa=True,
                                              anticipatory=True,
                                              foreperiod_s=round(foreperiod, 3))
                        arcade_toast(canvas, win, cx, cy, 'Too soon! Wait for the disc.',
                                     fill='yellow', size=18,
                                     sound='wrong' if self.feedback else None)
                        wait_ms(win, 700)
                        continue
                    else:
                        if rt < 0.30 and self.feedback:
                            try:
                                try:
                                    from .assets import play_async as _play
                                except ImportError:
                                    from assets import play_async as _play  # type: ignore[no-redef]
                                _play('streak', widget=win)
                            except Exception:
                                pass
                        rts.append(rt)
                        self.logger.log_trial(test=self.name, trial=t + 1, level='n/a',
                                              correct=True, rt_s=round(rt, 4), miss=False, fa=False,
                                              anticipatory=False,
                                              foreperiod_s=round(foreperiod, 3))
                    break
                canvas.delete('all')
                win.update()
                wait_ms(win, 400)
        except (QuitExperiment, TimeoutError, RuntimeError, KeyboardInterrupt) as e:
            record_abort(self.logger, self.name, e, kind=self.kind,
                         n_hit=len(rts), n_miss=misses, n_fa=fas,
                         n_trials=self.n_trials, ppd=self.ppd, seed=self.seed)
            raise
        med = float(np.median(rts)) if rts else float('nan')
        med_arg = round(med, 4) if rts else None
        n_miss = misses
        self.logger.end_test(test=self.name, kind=self.kind,
                             median_rt_s=med_arg,
                             n_trials=self.n_trials, n_miss=n_miss, n_hit=len(rts), n_fa=fas,
                             ppd=self.ppd, seed=self.seed)
        med_txt = f'{med * 1000:.0f} ms' if rts else 'no hits'
        canvas.delete('all')
        msg = (f'{self.name}\nMedian RT {med_txt}\nMisses {misses} '
               f'False starts {fas}\nPress any key')
        canvas.create_text(cx, cy, text=msg, font=('Arial', 18), justify='center')
        win.update()
        wait_dismiss(win)
        return med, rts, misses, fas
