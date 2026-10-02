import base64
from copy import deepcopy
import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from chronologer_app.main import app
from chronologer_app.api import density
from chronologer_app.projects import new_project, dump_project, load_project


def payload():
    return dict(events=[dict(id='A', distribution='normal', parameters=dict(mean=2000, sd=30)),
                        dict(id='B', distribution='normal', parameters=dict(mean=2400, sd=40))],
                observation=dict(older=3000, younger=1000, grid_size=8),
                sampling=dict(draws=4, tune=4, chains=1))


def test_gp_api_requires_observation_endpoints_and_rejects_invalid_bounds(monkeypatch):
    def no_queue():
        raise AssertionError('Invalid requests must not spawn inference')
    monkeypatch.setattr(density, 'get_jobs', no_queue)
    with TestClient(app) as client:
        for observation in [None, {}, {'older': 3000}, {'younger': 1000},
                            {'older': None, 'younger': 1000}, {'older': 1000, 'younger': 3000},
                            {'older': 1000, 'younger': 1000}, {'older': 3000, 'younger': 1000, 'grid_size': 3}]:
            data = payload()
            if observation is None:
                del data['observation']
            else:
                data['observation'] = observation
            assert client.post('/api/ippp/jobs', json=data).status_code == 422


def test_gp_worker_result_and_project_portability(monkeypatch, tmp_path):
    monkeypatch.setenv('CHRONOAPP_LOG_DIR', str(tmp_path))
    with TestClient(app) as client:
        response = client.post('/api/ippp/jobs', json=payload())
        assert response.status_code == 202, response.text
        job = response.json()
        deadline = time.monotonic() + 180
        while job['status'] not in {'completed', 'failed', 'cancelled'} and time.monotonic() < deadline:
            time.sleep(.1)
            job = client.get(f"/api/jobs/{job['id']}").json()
        assert job['status'] == 'completed', job
        result = client.get(f"/api/jobs/{job['id']}/result").json()
        assert job['completed'] == job['total'] == 8
    assert result['model'] == 'ippp_gp' and 'density' not in result
    assert result['intensity']['t_values'][0] == -3000
    assert result['intensity']['t_values'][-1] == -1000
    assert all(np.isfinite(v).all() and len(v) == 8 for v in result['intensity'].values())
    assert [p['name'] for p in result['marginals']['parameters']] == ['log_rate', 'amplitude', 'length_scale', 'integrated_intensity']
    assert len(result['marginals']['events']) == 2
    artifacts = {a['name']: base64.b64decode(a['data']) for a in result['mcmc']['artifacts']}
    assert json.loads(artifacts['diagnostics.json'])['model_spec']['start'] == -3000
    assert artifacts['trace-plots.pdf'].startswith(b'%PDF') and b'Completed' in artifacts['messages.txt']
    run = dict(id='gp-run', created_at='2026-10-02T12:00:00+00:00', model='ippp_gp',
               events=payload()['events'], parameters={**payload()['observation'], 'sampling': payload()['sampling']}, result=result)
    project = new_project()
    project['processes'] = [dict(id='process-1', label='GP IPPP', model='ippp_gp',
                                  events=run['events'], parameters=run['parameters'], saved_run=run)]
    assert load_project(dump_project(project)) == project
    for edit in [lambda r: r['parameters'].pop('older'),
                 lambda r: r['result']['diagnostics'].__setitem__('start', -5000),
                 lambda r: r['result']['intensity']['t_values'].__setitem__(0, -4000)]:
        bad = deepcopy(project)
        edit(bad['processes'][0]['saved_run'])
        with pytest.raises(ValueError):
            dump_project(bad)


def test_unconfigured_process_draft_can_be_saved():
    project = new_project()
    project['processes'] = [dict(id='process-1', label='Process 1', model='ippp_gp', events=[], parameters={})]
    assert load_project(dump_project(project)) == project
