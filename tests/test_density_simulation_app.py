"""Simulation request/adaptation/save checks with no sampling."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient

from chronologer_app.api import density
from chronologer_app.main import app
from chronologer_app.projects import new_project, dump_project, load_project
from chronologer_app.services import simulation


@pytest.mark.parametrize('model,n,draws', [('single_density', 3, 4), ('mixture', 3, 4),
                                         ('single_density', 1000, 1), ('mixture', 10000, 1)])
def test_simulation_request_worker_and_archive(monkeypatch, model, n, draws):
    request = dict(simulation=dict(n=n, distribution='calrcarbon', error=30., curve='intcal20', draws=draws),
        settings=dict(older=5000, younger=1, mean=2500, mean_sd=500, sd_scale=400))
    if model == 'mixture':
        request.update(model='mixture', settings=dict(K_max=2, prior_center=2500, prior_scale=400))
    submitted = []
    class Queue:
        def submit(self, function, args, label):
            submitted.append(args[0]); return dict(id='mock', status='queued')
    monkeypatch.setattr(density, 'get_jobs', lambda: Queue())
    monkeypatch.setattr(density, 'require_local_curve', lambda curve: None)
    with TestClient(app) as client:
        assert client.post('/api/simulation/jobs', json=request).status_code == 202
        invalid = deepcopy(request); invalid['simulation']['n'] = 0
        assert client.post('/api/simulation/jobs', json=invalid).status_code == 422
        invalid = deepcopy(request); invalid['simulation'].update(n=10000, draws=101)
        assert client.post('/api/simulation/jobs', json=invalid).status_code == 422
    values = np.arange(draws).reshape(1, draws)
    prior = xr.Dataset({'tau_mu': (('chain', 'draw'), -2500 + values),
        'tau_sd': (('chain', 'draw'), 100 + values),
        'tau': (('chain', 'draw', 'event'), np.repeat((-2500 + values)[..., None], n, axis=-1)),
        'measured': (('chain', 'draw', 'event'), np.broadcast_to(-2400. - np.arange(n), (1, draws, n)).copy())})
    trace = xr.DataTree.from_dict({'prior': prior})
    if model == 'mixture':
        prior = prior.drop_vars(['tau_mu', 'tau_sd']).assign(
            means=(('chain', 'draw', 'component'), np.repeat([[[-2600., -2400.]]], draws, axis=1)),
            scales=(('chain', 'draw', 'component'), np.full((1, draws, 2), 100.)),
            weights=(('chain', 'draw', 'component'), np.full((1, draws, 2), .5)))
        trace = xr.DataTree.from_dict({'prior': prior})
    monkeypatch.setattr(simulation.chronologer, 'load_calcurve', lambda *args, **kwargs: {'mock': True})
    captured = []
    def simulate(n, **kwargs):
        captured.append((n, kwargs))
        return SimpleNamespace(prior=trace, priors=dict(center=-2500., scale=400., concentration=.3, log_scale_sd=.75, scale_fraction=.2), density=dict(t_values=np.array([-3000., -2500., -2000.]),
            pdf_values=np.array([0., .002, 0.]), lower_values=np.array([0., .001, 0.]), upper_values=np.array([0., .003, 0.])))
    monkeypatch.setattr(simulation.chronologer, 'simulate_gaussian_mixture' if model == 'mixture' else 'simulate_single_density', simulate)
    result = simulation.simulate_in_worker(submitted[0])
    assert captured[0][0] == n and captured[0][1]['prior_center' if model == 'mixture' else 'lower'] == (-2500 if model == 'mixture' else -5000)
    assert len(result['simulation']['events']) == n
    assert len(result['marginals']['events']) == result['simulation']['plotted_events'] == min(n, 100)
    assert result['simulation']['events'][0]['parameters']['c14_mean'] == 2400
    assert result['simulation']['event_density'] == 'measurement'
    event = result['marginals']['events'][0]
    peak = np.argmax(event['pdf_values'])
    assert event['t_values'][peak] == -2400  # Measured age, not tau=-2500.
    assert event['pdf_values'][peak] == pytest.approx(1 / (30 * np.sqrt(2 * np.pi)))
    assert 'posterior' not in result and 'mcmc' not in result
    project = new_project()
    parameters = {**request['settings'], 'mode': 'simulate', 'simulation': request['simulation']}
    project['summaries'] = [dict(id='sim', label='Simulation', model=model, events=[], parameters=parameters,
        saved_run=dict(id='run', created_at='2026-10-04T12:00:00+00:00', model=model,
                       events=[], parameters=parameters, result=result))]
    assert load_project(dump_project(project)) == project
    invalid = deepcopy(project); invalid['summaries'][0]['saved_run']['result']['simulation']['events'][0]['parameters']['c14_err'] = -1
    with pytest.raises(ValueError, match='simulated event'):
        dump_project(invalid)


def test_calendar_measurement_plots():
    rows = [dict(id='normal', distribution='normal', parameters=dict(mean=2500., sd=20.)),
            dict(id='uniform', distribution='uniform', parameters=dict(lower=2400., upper=2600.))]
    normal, uniform = simulation.measurement_plots(rows)
    assert normal['t_values'][np.argmax(normal['pdf_values'])] == -2500
    assert uniform['t_values'][0] == -2600 and uniform['t_values'][-1] == -2400
    assert np.allclose(uniform['pdf_values'], 1 / 200)
