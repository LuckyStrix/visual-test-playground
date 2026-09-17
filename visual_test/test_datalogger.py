import csv
import json

from .datalogger import DataLogger


def test_schema_evolution_preserves_columns(tmp_path):
    logger = DataLogger(participant_id='TEST01', data_dir=str(tmp_path))
    logger.log_trial(test='test', trial=1, level=-1.0, correct=True, rt_s=0.3,
                     contrast=0.1, response='1')
    logger.log_trial(test='test2', trial=2, level=0.3, correct=False, rt_s=0.4,
                     logMAR=0.3, gap_deg=90)
    logger.end_test(test='test', threshold_log=-1.0, n_trials=1, n_reversals=0)
    logger.end_test(test='test2', threshold_log=0.3, n_trials=1, n_reversals=0)
    csv_path, json_path = logger.save()
    rows = list(csv.DictReader(open(csv_path)))
    assert rows[0].get('contrast') == '0.1'
    assert rows[1].get('logMAR') == '0.3'
    assert rows[1].get('contrast') == ''
    saved = json.load(open(json_path))
    assert len(saved['tests']) == 2


def test_per_session_files_and_incremental_json(tmp_path):
    logger = DataLogger(participant_id='P1', data_dir=str(tmp_path))
    logger.log_trial(test='t', trial=1, level=0.0, correct=True)
    assert '_trials.csv' in logger.csv_path
    logger.end_test(test='t', threshold_log=0.0, n_trials=1)
    saved = json.load(open(logger.json_path))
    assert len(saved['tests']) == 1
    old_csv = logger.csv_path
    logger.set_participant('P1')
    assert logger.csv_path != old_csv
    assert logger.tests == [] and logger.trials == []
