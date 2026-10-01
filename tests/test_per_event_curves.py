"""Mixed-curve app orchestration with unchanged engine code and isolated caches."""

from concurrent.futures import ProcessPoolExecutor
from functools import partial

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from chronologer_app.main import app
from chronologer_app.projects import dump_project, import_csv, load_project, new_project


def _temporary_engine_cache(path):
    # Test-only child initialization; never changes engine files or real data.
    import chronologer.calcurves as curves
    curves.CACHE_DIR = path


def test_mixed_curves_use_separate_workers_and_preserve_order(monkeypatch, tmp_path):
    import chronologer_app.api.calibration as api

    grid = np.linspace(-10000., 0., 101)
    for name, offset in [('intcal20', 0.), ('shcal20', 200.)]:
        pd.DataFrame({'calbp': grid, 'c14bp': grid + offset,
                      'c14_sigma': np.full_like(grid, 15.)}).to_csv(tmp_path / f'{name}.14c', index=False)
    monkeypatch.setattr(api, 'CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(api, 'ProcessPoolExecutor', partial(ProcessPoolExecutor,
                        initializer=_temporary_engine_cache, initargs=(str(tmp_path),)))
    # Same IDs and ages deliberately expose any ID-keyed merge or curve-cache leak.
    rows = [{'id': 'duplicate', 'age': 3240, 'error': 25, 'curve': name}
            for name in ['shcal20', 'intcal20', 'shcal20']]
    with TestClient(app) as client:
        response = client.post('/api/calibrate', json={'determinations': rows})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['curve'] is None
        assert body['curves'] == ['shcal20', 'intcal20']
        assert [r['curve'] for r in body['results']] == [r['curve'] for r in rows]
        assert body['results'][0]['posterior_mean'] == pytest.approx(-3440, abs=.1)
        assert body['results'][1]['posterior_mean'] == pytest.approx(-3240, abs=.1)
        for name in ['shcal20', 'intcal20']:
            row = next(row for row in rows if row['curve'] == name)
            # A conflicting legacy default must never replace the explicit row curve.
            single = client.post('/api/calibrate', json={'curve': 'intcal20', 'determinations': [row]})
            assert single.status_code == 200, single.text
            expected = single.json()['results'][0]
            for actual in [r for r in body['results'] if r['curve'] == name]:
                for key in ['t_values', 'pdf_values', 'hdi_intervals']:
                    np.testing.assert_array_equal(actual[key], expected[key])
                assert actual['posterior_mean'] == expected['posterior_mean']


def test_event_curve_csv_and_project_roundtrip():
    content = b'id,c14_mean,c14_err,curve\nA,3240,25,intcal20\nB,3240,25,shcal20\nC,3240,25,marine20\n'
    project = new_project()
    project.update(import_csv(content, 'mixed.csv', default_curve='intcal20'))
    restored = load_project(dump_project(project))
    assert restored == project
    assert [event['parameters']['curve'] for event in restored['events']] == ['intcal20', 'shcal20', 'marine20']


def test_csv_default_only_fills_missing_curve():
    imported = import_csv(b'id,c14_mean,c14_err,curve\nA,3240,25,shcal20\nB,3240,25,\n',
                          'mixed.csv', default_curve='intcal20')
    assert [r['parameters']['curve'] for r in imported['events']] == ['shcal20', 'intcal20']


def test_missing_and_unavailable_event_curves(monkeypatch, tmp_path):
    import chronologer_app.api.calibration as api
    with TestClient(app) as client:
        row = {'id': 'A', 'age': 3240, 'error': 25}
        response = client.post('/api/calibrate', json={'determinations': [row]})
        assert response.status_code == 422
        assert 'choose a calibration curve' in response.json()['detail']
        monkeypatch.setattr(api, 'CACHE_DIR', str(tmp_path))
        response = client.post('/api/calibrate', json={'determinations': [{**row, 'curve': 'shcal20'}]})
        assert response.status_code == 409
        assert not list(tmp_path.iterdir())
