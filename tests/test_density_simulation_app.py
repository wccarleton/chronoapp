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


def test_simulation_request_worker_and_archive(monkeypatch):
    request = dict(simulation=dict(n=3, distribution='calrcarbon', error=30., curve='intcal20', draws=4),
        settings=dict(older=5000, younger=1, mean=2500, mean_sd=500, sd_scale=400))
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
    values = np.arange(4).reshape(1, 4)
    prior = xr.Dataset({'tau_mu': (('chain', 'draw'), -2500 + values),
        'tau_sd': (('chain', 'draw'), 100 + values),
        'tau': (('chain', 'draw', 'event'), np.repeat((-2500 + values)[..., None], 3, axis=-1)),
        'measured': (('chain', 'draw', 'event'), np.array([[[-2400., -2500., -2600.]] * 4]))})
    trace = xr.DataTree.from_dict({'prior': prior})
    monkeypatch.setattr(simulation.chronologer, 'load_calcurve', lambda *args, **kwargs: {'mock': True})
    captured = []
    def simulate(n, **kwargs):
        captured.append((n, kwargs))
        return SimpleNamespace(prior=trace, density=dict(t_values=np.array([-3000., -2500., -2000.]),
            pdf_values=np.array([0., .002, 0.]), lower_values=np.array([0., .001, 0.]), upper_values=np.array([0., .003, 0.])))
    monkeypatch.setattr(simulation.chronologer, 'simulate_single_density', simulate)
    result = simulation.simulate_in_worker(submitted[0])
    assert captured[0][0] == 3 and captured[0][1]['lower'] == -5000
    assert result['simulation']['events'][0]['parameters']['c14_mean'] == 2400
    assert 'posterior' not in result and 'mcmc' not in result
    project = new_project()
    parameters = {**request['settings'], 'mode': 'simulate', 'simulation': request['simulation']}
    project['summaries'] = [dict(id='sim', label='Simulation', model='single_density', events=[], parameters=parameters,
        saved_run=dict(id='run', created_at='2026-10-04T12:00:00+00:00', model='single_density',
                       events=[], parameters=parameters, result=result))]
    assert load_project(dump_project(project)) == project
    invalid = deepcopy(project); invalid['summaries'][0]['saved_run']['result']['simulation']['events'][0]['parameters']['c14_err'] = -1
    with pytest.raises(ValueError, match='simulated event'):
        dump_project(invalid)
