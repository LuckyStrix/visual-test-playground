"""Trial-by-trial logging with full provenance for psychophysics."""
import csv
import json
import os
from datetime import datetime, timezone


def safe_name(s):
    keep = ''.join(c if (c.isalnum() or c in ('-', '_')) else '_' for c in (s or '').strip())
    return keep.strip('_') or 'anon'


def _sanitize(v):
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@'):
        return "'" + v
    return v


class DataLogger:
    """One CSV + one JSON per participant *session*; every trial appends immediately."""

    def __init__(self, participant_id=None, data_dir=None, meta=None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'data', 'sessions')
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.meta = meta or {}
        self.trials = []
        self.tests = []
        self._f = None
        self._w = None
        cleaned = safe_name(participant_id) if participant_id else ''
        if not cleaned or cleaned == 'anon':
            now = datetime.now(timezone.utc)
            stamp = now.strftime('%Y%m%d_%H%M%S')
            cleaned = f"P{stamp}" if not participant_id else f"anon_{stamp}"
        self.participant_id = cleaned
        self.session_id = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        self._set_paths()

    def _set_paths(self):
        base = f"{self.participant_id}_{self.session_id}"
        self.csv_path = os.path.join(self.data_dir, f"{base}_trials.csv")
        self.json_path = os.path.join(self.data_dir, f"{base}.json")

    def set_participant(self, participant_id):
        if not self.trials and not self.tests:
            try:
                if self._f is not None and not self._f.closed:
                    self._f.close()
            except Exception:
                pass
            for path in (self.csv_path, self.json_path):
                try:
                    if os.path.exists(path) and os.path.getsize(path) == 0:
                        os.remove(path)
                except Exception:
                    pass
        else:
            self.save()
        cleaned = safe_name(participant_id) if participant_id else ''
        if not cleaned or cleaned == 'anon':
            stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
            cleaned = f"P{stamp}" if not participant_id else f"anon_{stamp}"
        self.participant_id = cleaned
        self.session_id = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        self._set_paths()
        self.trials = []
        self.tests = []

    def _open(self):
        if self._f is None or getattr(self._f, 'closed', True):
            self._f = open(self.csv_path, 'a', newline='', encoding='utf-8')
            self._w = None

    def _rewrite_with_fields(self, fields):
        try:
            if self._f is not None:
                self._f.close()
        except Exception:
            pass
        self._f = None
        self._w = None
        rows = []
        try:
            with open(self.csv_path, 'r', newline='', encoding='utf-8') as rf:
                rows = list(csv.DictReader(rf))
        except Exception:
            rows = []
        tmp = self.csv_path + '.tmp'
        try:
            with open(tmp, 'w', newline='', encoding='utf-8') as wf:
                w = csv.DictWriter(wf, fieldnames=fields)
                w.writeheader()
                for r in rows:
                    w.writerow({k: _sanitize(r.get(k, '')) for k in fields})
                wf.flush()
                os.fsync(wf.fileno())
            os.replace(tmp, self.csv_path)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            raise
        self._f = open(self.csv_path, 'a', newline='', encoding='utf-8')
        self._w = csv.DictWriter(self._f, fieldnames=fields)

    def _ensure(self, rec):
        self._open()
        if self._w is None:
            existing = []
            try:
                if self._f.tell() > 0:
                    self._f.flush()
                    with open(self.csv_path, 'r', newline='', encoding='utf-8') as rf:
                        existing = next(csv.reader(rf), [])
            except Exception:
                existing = []
            fields = list(dict.fromkeys(list(existing) + list(rec.keys())))
            if existing and fields != existing:
                self._rewrite_with_fields(fields)
            else:
                self._w = csv.DictWriter(self._f, fieldnames=fields)
                if self._f.tell() == 0:
                    self._w.writeheader()
        elif set(rec.keys()) - set(self._w.fieldnames):
            extra = [k for k in rec.keys() if k not in self._w.fieldnames]
            fields = list(self._w.fieldnames) + extra
            self._rewrite_with_fields(fields)

    def _write_json(self):
        tmp = self.json_path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'schema': 2, 'app': 'visual_test',
                       'participant': self.participant_id, 'session': self.session_id,
                       'meta': self.meta, 'tests': self.tests,
                       'trials_logged': len(self.trials)}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.json_path)

    def log_trial(self, **rec):
        rec = {'utc': datetime.now(timezone.utc).isoformat(),
               'participant': self.participant_id, 'session': self.session_id, **rec}
        rec.setdefault('rt_s', '')
        rec = {k: _sanitize(v) for k, v in rec.items()}
        try:
            self._ensure(rec)
            self._w.writerow({k: rec.get(k, '') for k in self._w.fieldnames})
            self._f.flush()
            os.fsync(self._f.fileno())
        except Exception:
            try:
                if self._f is not None and not self._f.closed:
                    self._f.close()
            except Exception:
                pass
            self._f = None
            self._w = None
            raise
        self.trials.append(rec)
        try:
            self._write_json()
        except Exception:
            pass

    def end_test(self, **summary):
        if not isinstance(summary.get('test'), str) or not summary.get('test'):
            summary['test'] = 'unknown'
        summary['utc_end'] = datetime.now(timezone.utc).isoformat()
        self.tests.append(summary)
        try:
            if self._f is not None and not self._f.closed:
                self._f.flush()
        except Exception:
            pass
        self._write_json()

    def save(self):
        try:
            if self._f is not None and not self._f.closed:
                self._f.close()
        except Exception:
            pass
        self._f = None
        self._w = None
        self._write_json()
        return self.csv_path, self.json_path
