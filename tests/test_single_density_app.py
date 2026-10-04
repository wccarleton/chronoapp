"""Mixed-measurement request, worker and archive checks without sampling."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import xarray as xr
from fastapi.testclient import TestClient

from chronologer_app.api import density
from chronologer_app.main import app
from chronologer_app.projects import new_project, dump_project, load_project


def test_single_density_request_worker_and_archive(monkeypatch):
    request = dict(events=[
        dict(id='normal', distribution='normal', parameters=dict(mean=50, sd=3)),
        dict(id='uniform', distribution='uniform', parameters=dict(lower=40, upper=60)),
        dict(id='north', distribution='calrcarbon', parameters=dict(c14_mean=50, c14_err=3, curve='intcal20')),
        dict(id='south', distribution='calrcarbon', parameters=dict(c14_mean=50, c14_err=3, curve='shcal20')),
    ], settings=dict(older=90, younger=10, mean=50, mean_sd=20, sd_scale=15),
       sampling=dict(draws=4, tune=4, chains=1, cores=1))
    submitted, curves = [], []
    class Queue:
        def submit(self, function, args, label):
            submitted.append(args); return dict(id='mock', status='queued')
    monkeypatch.setattr(density, 'get_jobs', lambda: Queue())
    monkeypatch.setattr(density, 'require_local_curve', curves.append)
    with TestClient(app) as client:
        assert client.post('/api/single_density/jobs', json=request).status_code == 202
        invalid = deepcopy(request); invalid['events'][0]['datum'] = 'BCAD'
        assert client.post('/api/single_density/jobs', json=invalid).status_code == 422
    assert set(curves) == {'intcal20', 'shcal20'}
    values = np.arange(4).reshape(1, 4)
    posterior = xr.Dataset({'tau_mu': (('chain', 'draw'), -50 + values),
        'tau_sd': (('chain', 'draw'), 10 + values),
        'tau': (('chain', 'draw', 'event'), np.repeat((-50 + values)[..., None], 4, axis=-1))})
    trace = xr.DataTree.from_dict({'posterior': posterior,
        'sample_stats': xr.Dataset({'diverging': (('chain', 'draw'), np.zeros((1, 4), dtype=bool))})})
    monkeypatch.setattr(density.chronologer, 'load_calcurve', lambda *args, **kwargs:
        dict(calbp=np.linspace(-100, 0, 11), c14bp=np.linspace(-100, 0, 11), c14_sigma=np.full(11, 2.)))
    captured = []
    def fit(events, **kwargs):
        captured.append((events, kwargs))
        return SimpleNamespace(posterior=trace, density=dict(t_values=np.array([-90., -50., -10.]),
            pdf_values=np.array([0., .025, 0.]), lower_values=np.array([0., .02, 0.]), upper_values=np.array([0., .03, 0.])))
    monkeypatch.setattr(density.chronologer.models.density, 'single_density', fit)
    monkeypatch.setattr(density, 'build_diagnostics', lambda *args, **kwargs: dict(version=1,
        variables=[dict(variable='tau_mu', r_hat=None, ess_bulk=None, ess_tail=None, mcse_mean=None, mcse_sd=None, geweke_z=[None])],
        chains=[dict(chain=1, divergences=0, bfmi=None, max_tree_depth=None, reached_max_treedepth=None, acceptance_mean=None)],
        notes=[], versions={}, artifacts=[]))
    data, sampling = submitted[0]
    result = density.fit_in_worker(data, sampling)
    assert captured[0][0][0].mean() == -50
    assert captured[0][0][1].support() == (-60, -40)
    assert captured[0][1]['params']['lower'] == -90
    assert result['model'] == 'single_density'
    assert len(result['marginals']['events']) == 4
    project = new_project()
    parameters = {**request['settings'], 'sampling': request['sampling']}
    run = dict(id='run', created_at='2026-10-04T12:00:00+00:00', model='single_density',
               events=data['events'], parameters=parameters, result=result)
    project['summaries'] = [dict(id='summary', label='Single density', model='single_density',
        events=data['events'], parameters=parameters, saved_run=run)]
    assert load_project(dump_project(project)) == project
