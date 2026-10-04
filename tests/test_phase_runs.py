"""Fast phase request/adaptation/archive checks, with no sampler execution."""
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient

from chronologer_app.api import phases
from chronologer_app.main import app
from chronologer_app.projects import new_project, dump_project, load_project
from chronologer_app.services import phases as service


def payload():
    return dict(phases=[dict(id=f'phase-{i}', label=label, distribution=family, order=i, parameters={})
                        for i, (label, family) in enumerate([('Early', 'uniform'), ('Late', 'normal')])],
                events=[dict(id=f'event-{i}', label=label, distribution='normal', parameters=dict(mean=mean, sd=20), datum='BP1950')
                        for i, (label, mean) in enumerate([('Early', 2500), ('Late', 2200), ('Early', 2450)])],
                settings=dict(anchors='end_start', delta_scale=100),
                sampling=dict(draws=4, tune=4, chains=1, cores=1))


def test_phase_submission_and_validation(monkeypatch):
    submitted = []
    class Queue:
        def submit(self, function, args, label):
            submitted.append(args)
            return dict(id='phase-test', status='queued')
    monkeypatch.setattr(phases, 'get_jobs', lambda: Queue())
    with TestClient(app) as client:
        assert client.post('/api/phases/jobs', json=payload()).status_code == 202
        assert submitted[0][1]['cores'] == 1
        invalid = payload(); invalid['phases'][1]['label'] = 'Early'
        assert client.post('/api/phases/jobs', json=invalid).status_code == 422
        invalid = payload(); invalid['events'][0]['datum'] = 'BCAD'
        assert client.post('/api/phases/jobs', json=invalid).status_code == 422
        invalid = payload(); invalid['phases'][0]['parameters']['prior_scale'] = -1
        assert client.post('/api/phases/jobs', json=invalid).status_code == 422


def test_phase_worker_and_saved_run(monkeypatch):
    request = phases.PhaseRequest(**payload()).model_dump()
    sampling = {**request['sampling'], 'random_seed': 912}
    values = np.arange(4, dtype=float).reshape(1, 4, 1)
    posterior = xr.Dataset({
        'mu': (('chain', 'draw', 'phase'), np.concatenate([-2500 + values, -2200 + values], axis=-1)),
        'scale': (('chain', 'draw', 'phase'), np.concatenate([100 + values, 20 + values], axis=-1)),
        'tau': (('chain', 'draw', 'event'), np.concatenate([-2500 + values, -2200 + values, -2450 + values], axis=-1)),
        'delta': (('chain', 'draw', 'order'), 100 + values),
    }, coords={'phase': ['Early', 'Late']})
    stats = xr.Dataset({'diverging': (('chain', 'draw'), np.zeros((1, 4), dtype=bool))})
    trace = xr.DataTree.from_dict({'posterior': posterior, 'sample_stats': stats})
    captured = {}
    def fit(rows, specs, *, measurements, orders, **kwargs):
        captured.update(specs=specs, orders=orders, measurements=measurements, sampling=kwargs)
        return trace
    monkeypatch.setattr(service.chronologer, 'fit_phase', fit)
    # Report generation is independently covered; this test checks adaptation.
    monkeypatch.setattr(service, 'build_diagnostics', lambda *args, **kwargs: {
        'version': 1, 'variables': [dict(variable='mu[0]', r_hat=None, ess_bulk=None, ess_tail=None,
            mcse_mean=None, mcse_sd=None, geweke_z=[None])],
        'chains': [dict(chain=1, divergences=0, bfmi=None, max_tree_depth=None,
            reached_max_treedepth=None, acceptance_mean=None)],
        'notes': [], 'versions': {}, 'artifacts': []})
    updates = []
    result = service.fit_in_worker(request, sampling, updates.append)
    assert captured['orders'][0].anchors == (1., .05)
    assert captured['orders'][0].delta_scale == 100
    assert captured['measurements'][0].mean() == -2500
    assert result['phases'][0]['interval']['lower']['mean'] == pytest.approx(-2549.25)
    assert updates[-1]['completed'] == updates[-1]['total'] == 8
    assert len(result['marginals']['events']) == 3
    assert np.trapezoid(result['phases'][1]['density']['pdf_values'], result['phases'][1]['density']['t_values']) == pytest.approx(1, abs=1e-6)
    parameters = {**request['settings'], 'sampling': request['sampling'], 'phases': request['phases']}
    project = new_project(); project['events'] = request['events']; project['phases'] = request['phases']
    project['phase_model'] = dict(parameters={**request['settings'], 'sampling': request['sampling']},
        saved_run=dict(id='phase-run', created_at='2026-10-04T12:00:00+00:00', model='phase',
                       events=deepcopy(request['events']), parameters=deepcopy(parameters), result=result))
    assert load_project(dump_project(project)) == project
    project['events'][0]['parameters']['mean'] += 50
    assert load_project(dump_project(project))['phase_model']['saved_run']['events'][0]['parameters']['mean'] == 2500
    invalid = deepcopy(project); invalid['phase_model']['saved_run']['result']['posterior']['samples'] = [[1]]
    with pytest.raises(ValueError, match='posterior metadata'):
        dump_project(invalid)
