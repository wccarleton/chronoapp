import time
import numpy as np
from fastapi.testclient import TestClient
from chronologer_app.main import app
from chronologer_app.api import density


def payload():
    return dict(K_max=2, events=[
        dict(id='A', distribution='normal', parameters=dict(mean=2000, sd=30)),
        dict(id='B', distribution='normal', parameters=dict(mean=2400, sd=40)),
    ])


def test_mixture_job_engine_and_serialization(monkeypatch, tmp_path):
    monkeypatch.setenv('CHRONOAPP_LOG_DIR', str(tmp_path))
    monkeypatch.setattr(density, 'SAMPLING', dict(draws=6, tune=6, chains=1, random_seed=912))
    with TestClient(app) as client:
        response = client.post('/api/mixture/jobs', json=payload())
        assert response.status_code == 202, response.text
        job = response.json()
        deadline = time.monotonic() + 180
        while job['status'] not in {'completed', 'failed', 'cancelled'} and time.monotonic() < deadline:
            time.sleep(.1)
            job = client.get(f"/api/jobs/{job['id']}").json()
        assert job['status'] == 'completed', job
        result = client.get(f"/api/jobs/{job['id']}/result").json()
        assert result['model'] == 'gaussian_mixture'
        assert result['posterior']['sizes']['component'] == 2
        assert result['marginals']['parameters'] == []
        assert len(result['marginals']['events']) == 2
        assert all(np.isfinite(values).all() and len(values) == 2048 for values in result['density'].values())
        assert np.isclose(sum(result['diagnostics']['weight_mean']), 1)
        assert np.trapezoid(result['density']['pdf_values'], result['density']['t_values']) > .99


def test_mixture_validation():
    with TestClient(app) as client:
        for k in [0, 21, 1.5, True]:
            assert client.post('/api/mixture/jobs', json={**payload(), 'K_max': k}).status_code == 422
        data = payload()
        data['events'][0]['datum'] = 'BCAD'
        assert client.post('/api/mixture/jobs', json=data).status_code == 422
        data = payload()
        data['events'][0]['parameters']['sd'] = 0
        assert client.post('/api/mixture/jobs', json=data).status_code == 422
        data = dict(K_max=5, events=[dict(id=str(i), distribution='calrcarbon',
                    parameters=dict(c14_mean=2500, c14_err=30, curve=curve))
                    for i, curve in enumerate(['intcal20', 'shcal20'])])
        assert client.post('/api/mixture/jobs', json=data).status_code == 422
