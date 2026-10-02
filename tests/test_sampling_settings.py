from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from chronologer_app.main import app
from chronologer_app.api import density
from chronologer_app.projects import dump_project, load_project
from test_density import payload as density_payload
from test_mixture import payload as mixture_payload
from test_saved_results import saved_project


@pytest.mark.parametrize('endpoint,payload', [('/api/density/jobs', density_payload), ('/api/mixture/jobs', mixture_payload)])
def test_counts_reach_worker_and_defaults_are_shared(monkeypatch, endpoint, payload):
    queued = []
    class Queue:
        def submit(self, function, args, label):
            queued.append(args[1])
            return {'id': 'test', 'status': 'queued'}
    monkeypatch.setattr(density, 'get_jobs', lambda: Queue())
    monkeypatch.setattr(density, 'require_local_curve', lambda name: None)
    with TestClient(app) as client:
        assert client.post(endpoint, json=payload()).status_code == 202
        assert queued[-1] == dict(draws=1000, tune=1000, chains=4, random_seed=912)
        assert client.post(endpoint, json={**payload(), 'sampling': dict(draws=27, tune=0, chains=3)}).status_code == 202
        assert queued[-1] == dict(draws=27, tune=0, chains=3, random_seed=912)
        for key, value in [('draws', 0), ('draws', 1.5), ('draws', True), ('draws', '100'),
                           ('tune', -1), ('chains', 0), ('chains', None), ('random_seed', 123)]:
            assert client.post(endpoint, json={**payload(), 'sampling': {key: value}}).status_code == 422
        assert len(queued) == 2


def test_saved_counts_roundtrip_and_match_recorded_result():
    project = saved_project()
    summary = project['summaries'][0]
    values = {key: summary['saved_run']['result']['sampling'][key] for key in ('draws', 'tune', 'chains')}
    summary['parameters']['sampling'] = deepcopy(values)
    summary['saved_run']['parameters']['sampling'] = deepcopy(values)
    assert load_project(dump_project(project)) == project
    summary['parameters']['sampling']['draws'] = 999
    assert load_project(dump_project(project)) == project  # Changed draft, retained older run.
    summary['saved_run']['parameters']['sampling']['draws'] += 1
    with pytest.raises(ValueError, match='do not match'):
        dump_project(project)


def test_unfinished_sampling_draft_can_be_saved():
    project = saved_project()
    project['summaries'][0]['parameters']['sampling'] = dict(draws=None, tune=1000, chains=4)
    assert load_project(dump_project(project)) == project
