"""Transformed up-down staircases (Levitt, 1971) operating in log units."""

import math
import warnings

import numpy as np

RULES = {
    "1U1D": (1, 1, 0.500),
    "2D1U": (1, 2, 0.707),
    "3D1U": (1, 3, 0.794),
    "4D1U": (1, 4, 0.841),
}


class Staircase:
    def __init__(
        self,
        start_val,
        step_sizes,
        n_reversals=8,
        n_trials_max=60,
        min_val=-3.0,
        max_val=0.0,
        rule="3D1U",
    ):
        if rule not in RULES:
            raise ValueError(f"rule must be one of {list(RULES)}, got {rule}")
        if not step_sizes:
            raise ValueError("step_sizes must be a non-empty sequence")
        if any(not math.isfinite(s) or not s > 0 for s in step_sizes):
            raise ValueError("step_sizes must all be finite and positive")
        for label, v in (("min_val", min_val), ("max_val", max_val), ("start_val", start_val)):
            if not math.isfinite(v):
                raise ValueError(f"{label} must be finite, got {v!r}")
        if min_val > max_val:
            raise ValueError(f"min_val ({min_val}) must be <= max_val ({max_val})")
        if int(n_reversals) < 1:
            raise ValueError("n_reversals must be >= 1")
        if int(n_trials_max) < 1:
            raise ValueError("n_trials_max must be >= 1")
        self.step_sizes = list(step_sizes)
        self.n_reversals = int(n_reversals)
        self.n_trials_max = int(n_trials_max)
        self.min_val = min_val
        self.max_val = max_val
        self.rule = rule
        self.n_up, self.n_down, self.target_p = RULES[rule]
        self.start_val = min(max(start_val, min_val), max_val)
        if self.start_val != start_val:
            warnings.warn(
                f"start_val ({start_val}) outside [{min_val}, {max_val}]; "
                f"clamped to {self.start_val}",
                stacklevel=2,
            )
        self.current = self.start_val
        self.step_index = 0
        self.reversals = []
        self.reversal_trials = []
        self.levels = []
        self.responses = []
        self.direction = None
        self.n_consec_correct = 0
        self.n_consec_incorrect = 0
        self.trial_num = 0

    def reset(self):
        self.current = self.start_val
        self.step_index = 0
        self.reversals = []
        self.reversal_trials = []
        self.levels = []
        self.responses = []
        self.direction = None
        self.n_consec_correct = 0
        self.n_consec_incorrect = 0
        self.trial_num = 0

    def _step(self):
        return self.step_sizes[min(self.step_index, len(self.step_sizes) - 1)]

    def respond(self, correct):
        if correct is None:
            raise ValueError("respond() requires True/False, got None")
        correct = bool(correct)
        self.levels.append(self.current)
        self.responses.append(correct)
        self.trial_num += 1
        if correct:
            self.n_consec_correct += 1
            self.n_consec_incorrect = 0
        else:
            self.n_consec_incorrect += 1
            self.n_consec_correct = 0
        move = None
        if self.n_consec_incorrect >= self.n_up:
            move = "up"
            self.n_consec_correct = 0
            self.n_consec_incorrect = 0
        elif self.n_consec_correct >= self.n_down:
            move = "down"
            self.n_consec_correct = 0
            self.n_consec_incorrect = 0
        if move is not None:
            step = self._step()
            if move == "up":
                new_val = min(self.current + step, self.max_val)
            else:
                new_val = max(self.current - step, self.min_val)
            if new_val == self.current:
                self.direction = None
                self.n_consec_correct = 0
                self.n_consec_incorrect = 0
                finished = (
                    len(self.reversals) >= self.n_reversals or self.trial_num >= self.n_trials_max
                )
                return self.current, finished
            if self.direction is not None and move != self.direction:
                self.reversals.append(self.current)
                self.reversal_trials.append(self.trial_num)
                if self.step_index < len(self.step_sizes) - 1:
                    self.step_index += 1
            self.direction = move
            self.current = new_val
        finished = len(self.reversals) >= self.n_reversals or self.trial_num >= self.n_trials_max
        return self.current, finished

    def threshold(self, n_discard=2):
        if not self.reversals:
            return float(self.current)
        revs = self.reversals[n_discard:] if len(self.reversals) > n_discard else self.reversals
        return float(np.mean(revs))

    def reversal_sd(self, n_discard=2):
        if len(self.reversals) <= n_discard + 1:
            return float("nan")
        return float(np.std(self.reversals[n_discard:], ddof=1))
