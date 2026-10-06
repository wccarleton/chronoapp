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


@pytest.mark.parametrize('dag', [False, True])
def test_phase_worker_and_saved_run(monkeypatch, dag):
    data = payload()
    if dag:
        data['phases'].extend(dict(id=f'phase-{i}', label=label, distribution='normal', order=i,
                                  parameters={'delta_scale': 40}, anchors=[.05, .95])
                              for i, label in enumerate(['Middle', 'Final'], start=2))
        data['events'].extend(dict(id=label, label=label, distribution='normal', parameters=dict(mean=mean, sd=20))
                              for label, mean in [('Middle', 2250), ('Final', 1800)])
        data['settings'].update(edges=[dict(source=f'phase-{a}', target=f'phase-{b}')
                                      for a, b in [(0,1),(0,2),(1,3),(2,3)]])
    request = phases.PhaseRequest(**data).model_dump()
    sampling = {**request['sampling'], 'random_seed': 912}
    values = np.arange(4, dtype=float).reshape(1, 4, 1)
    posterior = xr.Dataset({
        'mu': (('chain', 'draw', 'phase'), np.concatenate([-2500 + values, -2200 + values], axis=-1)),
        'scale': (('chain', 'draw', 'phase'), np.concatenate([100 + values, 20 + values], axis=-1)),
        'tau': (('chain', 'draw', 'event'), np.concatenate([-2500 + values, -2200 + values, -2450 + values], axis=-1)),
        'delta': (('chain', 'draw', 'input_phase'), 100 + values),
    }, coords={'phase': ['Early', 'Late'], 'input_phase': ['Late']})
    if dag:
        posterior = xr.Dataset({
            'mu': (('chain','draw','phase'), np.concatenate([-2500+values,-2200+values,-2350+100*values,-1800+values], axis=-1)),
            'scale': (('chain','draw','phase'), np.concatenate([100+values,20+values,20+values,20+values], axis=-1)),
            'tau': (('chain','draw','event'), np.concatenate([-2500+values,-2200+values,-2450+values,-2250+values,-1800+values], axis=-1)),
            'delta': (('chain','draw','input_phase'), np.repeat(100+values,3,axis=-1)),
        }, coords={'phase':['Early','Late','Middle','Final'], 'input_phase':['Late','Middle','Final']})
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
    assert len(result['marginals']['events']) == len(request['events'])
    assert result['model_diagnostics']['n_events'] == len(request['events'])
    if dag:
        assert captured['specs']['Final'].delta_scale == 40
        assert len(result['diagnostics']['deltas']) == 3  # Four edges, three receiving phases.
        final = next(d for d in result['diagnostics']['deltas'] if d['after'] == 'Final')
        assert [p['share'] for p in final['predecessors']] == [.5,.5]
    assert result['model_diagnostics']['likelihood'] == 'event_marginal'
    assert np.isfinite(result['model_diagnostics']['waic'])
    assert np.trapezoid(result['phases'][1]['density']['pdf_values'], result['phases'][1]['density']['t_values']) == pytest.approx(1, abs=1e-6)
    parameters = {**request['settings'], 'sampling': request['sampling'], 'phases': request['phases']}
    project = new_project(); project['events'] = request['events']; project['phases'] = request['phases']
    project['phase_model'] = dict(parameters={**request['settings'], 'sampling': request['sampling']},
        saved_run=dict(id='phase-run', created_at='2026-10-04T12:00:00+00:00', model='phase',
                       events=deepcopy(request['events']), parameters=deepcopy(parameters), result=result))
    assert load_project(dump_project(project)) == project
    legacy = deepcopy(project)
    if not dag:
        delta = legacy['phase_model']['saved_run']['result']['diagnostics']['deltas'][0]
        legacy['phase_model']['saved_run']['result']['diagnostics']['deltas'] = [dict(before='Early', after='Late', anchors=[1., .05],
            **{key: delta[key] for key in ('mean', 'lower', 'upper')})]
    del legacy['phase_model']['saved_run']['result']['model_diagnostics']
    assert load_project(dump_project(legacy)) == legacy
    invalid_score = deepcopy(project)
    invalid_score['phase_model']['saved_run']['result']['model_diagnostics']['waic'] = float('nan')
    with pytest.raises(ValueError, match='WAIC estimates'):
        dump_project(invalid_score)
    project['events'][0]['parameters']['mean'] += 50
    assert load_project(dump_project(project))['phase_model']['saved_run']['events'][0]['parameters']['mean'] == 2500
    invalid = deepcopy(project); invalid['phase_model']['saved_run']['result']['posterior']['samples'] = [[1]]
    with pytest.raises(ValueError, match='posterior metadata'):
        dump_project(invalid)


def test_card_anchors_and_validation():
    data = payload()
    data['settings'] = dict(ordered=True, delta_scale=100)
    data['phases'][0]['anchors'] = [.5]
    data['phases'][1]['anchors'] = [.2, .8]
    data['phases'].append(dict(id='phase-2', label='Final', distribution='uniform', order=2,
                               parameters={}, anchors=[.25]))
    data['events'].append(dict(id='last', label='Final', distribution='normal',
                              parameters=dict(mean=2000, sd=20)))
    request = phases.PhaseRequest(**data).model_dump()
    _, orders = service.specification(request)
    assert [order.anchors for order in orders] == [(.5, .2), (.8, .25)]
    project = new_project(); project['phases'] = data['phases']
    project['phase_model'] = dict(parameters={**data['settings'], 'sampling': data['sampling']})
    assert load_project(dump_project(project)) == project
    for invalid_anchors in ([.2, .2], [.8, .2], [0.]):
        invalid = deepcopy(data); invalid['phases'][1]['anchors'] = invalid_anchors
        with pytest.raises(ValueError):
            phases.PhaseRequest(**invalid)
        invalid_project = deepcopy(project); invalid_project['phases'][1]['anchors'] = invalid_anchors
        with pytest.raises(ValueError):
            dump_project(invalid_project)


def test_legacy_anchor_presets_preserve_meaning():
    for preset, expected in [('center', [(.5, .5)]), ('end_start', [(1., .05)]), ('none', [])]:
        data = payload(); data['settings']['anchors'] = preset
        _, orders = service.specification(phases.PhaseRequest(**data).model_dump())
        assert [order.anchors for order in orders] == expected
        project = new_project(); project['phases'] = data['phases']
        project['phase_model'] = dict(parameters={**data['settings'], 'sampling': data['sampling']})
        assert load_project(dump_project(project)) == project


def test_explicit_connections_and_positions():
    data = payload()
    # Explicit direction overrides list order. Pixels are never sent to the engine.
    data['settings'] = dict(ordered=True, edges=[dict(source='phase-1', target='phase-0')])
    request = phases.PhaseRequest(**data).model_dump()
    _, orders = service.specification(request)
    assert [(order.before, order.after) for order in orders] == [('Late', 'Early')]
    project = new_project(); project['phases'] = deepcopy(data['phases'])
    for i, phase in enumerate(project['phases']):
        phase['position'] = dict(x=50 + i * 100, y=200 - i * 100)
    project['phase_model'] = dict(parameters={**data['settings'], 'sampling': data['sampling']})
    assert load_project(dump_project(project)) == project
    invalid = deepcopy(project); invalid['phase_model']['parameters']['edges'].append(dict(source='phase-0', target='phase-1'))
    with pytest.raises(ValueError, match='cycles'):
        dump_project(invalid)
    invalid = deepcopy(project); invalid['phase_model']['parameters']['edges'][0]['target'] = 'missing'
    with pytest.raises(ValueError, match='existing'):
        dump_project(invalid)
    invalid = deepcopy(project); invalid['phases'][0]['position']['x'] = float('nan')
    with pytest.raises(ValueError, match='position'):
        dump_project(invalid)
