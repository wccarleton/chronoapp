import numpy as np
import time
from fastapi.testclient import TestClient

from chronologer_app.main import app
from chronologer_app.api import density


def payload():
    return {'determinations': [
        {'id': 'A', 'age': 2500, 'error': 30, 'curve': 'intcal20'},
        {'id': 'B', 'age': 2550, 'error': 30, 'curve': 'intcal20'},
    ], 'settings': {'older': 3500, 'younger': 1500, 'mean': 2500, 'mean_sd': 500, 'sd_scale': 400}}


def test_density_api_executes_public_engine_in_spawned_worker(monkeypatch, tmp_path):
    monkeypatch.setenv('CHRONOAPP_LOG_DIR', str(tmp_path))
    monkeypatch.setattr(density, 'SAMPLING', dict(draws=8, tune=8, chains=1, random_seed=912))
    with TestClient(app) as client:
        response = client.post('/api/density/jobs', json={**payload(), 'label': 'Test fit'})
        assert response.status_code == 202, response.text
        job = response.json()
        deadline = time.monotonic() + 120
        progress = []
        while job['status'] not in {'completed', 'failed', 'cancelled'} and time.monotonic() < deadline:
            time.sleep(.05)
            job = client.get(f"/api/jobs/{job['id']}").json()
            progress.append(job['completed'])
        assert job['status'] == 'completed', job
        assert job['completed'] == job['total'] == 16
        assert progress == sorted(progress)
        result = client.get(f"/api/jobs/{job['id']}/result").json()
        log = client.get(f"/api/jobs/{job['id']}/log").text
        assert 'Sampling' in log and 'Completed' in log
        assert client.get(f"/api/jobs/{job['id']}/log?download=true").status_code == 200
        assert client.get('/api/jobs').json()['jobs'][0]['id'] == job['id']
    assert result['posterior']['type'] == 'xarray.DataTree'
    assert {'tau', 'r_latent', 'tau_mu', 'tau_sd'} <= set(result['posterior']['variables'])
    assert result['posterior']['sizes']['draw'] == 8
    assert result['coordinate_system'] == 'negative_bp'
    assert all(len(a) == 512 and np.isfinite(a).all() for a in result['density'].values())
    assert np.all(np.array(result['density']['lower_values']) <= result['density']['upper_values'])
    assert result['warnings'] and result['elapsed_seconds'] > 0
    marginals = result['marginals']
    assert [p['name'] for p in marginals['parameters']] == ['tau_mu', 'tau_sd']
    assert [e['id'] for e in marginals['events']] == ['A', 'B']
    for marginal in marginals['parameters'] + marginals['events']:
        times, heights = np.array(marginal['t_values']), np.array(marginal['pdf_values'])
        assert np.isfinite(times).all() and np.isfinite(heights).all()
        assert (heights >= 0).all() and (np.diff(times) >= 0).all()
        assert np.isclose(np.trapezoid(heights, times), 1)
    assert min(marginals['parameters'][1]['t_values']) >= 0


def test_marginals_use_event_posterior_draws_in_input_order():
    import xarray as xr
    from chronologer_app.services.posterior_plots import posterior_plots
    posterior = xr.Dataset({
        'tau_mu': (('chain', 'draw'), [[-200, -210, -220, -230]]),
        'tau_sd': (('chain', 'draw'), [[10, 20, 30, 40]]),
        'tau': (('chain', 'draw', 'event'), [[[-100, -300], [-110, -310], [-120, -320], [-130, -330]]]),
    })
    result = posterior_plots(posterior, [{'id': 'duplicate'}, {'id': 'duplicate'}])
    assert [e['index'] for e in result['events']] == [0, 1]
    assert result['events'][0]['t_values'][0] == -130
    assert result['events'][1]['t_values'][-1] == -300
    assert result['parameters'][0]['calendar'] is True
    assert result['parameters'][1]['calendar'] is False


def test_density_rejects_mixed_curves_bad_settings_and_missing_jobs():
    with TestClient(app) as client:
        data = payload()
        data['determinations'][1]['curve'] = 'shcal20'
        assert client.post('/api/density', json=data).status_code == 422
        data = payload()
        data['settings']['mean_sd'] = 0
        assert client.post('/api/density', json=data).status_code == 422
        assert client.get('/api/jobs/nonexistent').status_code == 404
