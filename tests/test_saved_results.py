from copy import deepcopy
from pathlib import Path
import json
import pytest
from chronologer_app.projects import new_project, dump_project, load_project


def saved_project():
    result = json.loads((Path(__file__).parents[1] / 'docs/mixture-benchmark-result.json').read_text())
    # Use the established real result, with its exact 20-event input snapshot.
    from chronologer_app.projects import import_csv
    events = import_csv((Path(__file__).parents[1] / 'docs/examples/density-benchmark.csv').read_bytes(), 'example.csv')['events']
    project = new_project()
    run = dict(id='run-1', created_at='2026-10-01T12:00:00+00:00', model='mixture',
               events=events, parameters={'K_max': 5}, result=result)
    project['summaries'] = [dict(id='summary-1', label='Saved result', model='mixture',
                                  events=events, parameters={'K_max': 5}, saved_run=run)]
    return project


def test_actual_mixture_result_roundtrips_compactly():
    project = saved_project()
    encoded = dump_project(project)
    assert load_project(encoded) == project
    assert len(encoded) < 150000
    # Changing current inputs doesn't corrupt the retained run snapshot.
    project['summaries'][0]['parameters'] = {'K_max': 4}
    assert load_project(dump_project(project))['summaries'][0]['saved_run']['parameters'] == {'K_max': 5}
    del project['summaries'][0]['saved_run']
    assert load_project(dump_project(project)) == project


def test_model_diagnostics_roundtrip_and_validation():
    project = saved_project()
    result = project['summaries'][0]['saved_run']['result']
    result['model_diagnostics'] = dict(waic=20., elpd_waic=-10., p_waic=2., se=1.,
        n_events=20, n_units=20, n_samples=100, warning=False, notes=[], likelihood='event_marginal')
    assert load_project(dump_project(project)) == project
    result['model_diagnostics']['waic'] = float('nan')
    with pytest.raises(ValueError, match='model diagnostics'):
        dump_project(project)
    result['model_diagnostics'] = {'unavailable': 'Too few retained draws.'}
    assert load_project(dump_project(project)) == project


def test_ippp_score_unit_validation():
    from chronologer_app.saved_results import validate_model_diagnostics
    score = dict(waic=20., elpd_waic=-10., p_waic=2., se=None, n_events=3,
                 n_units=1, n_samples=100, warning=True, notes=[], likelihood='observation_window')
    validate_model_diagnostics(score, 3, process=True)
    score['se'] = 1.
    with pytest.raises(ValueError, match='model diagnostics'):
        validate_model_diagnostics(score, 3, process=True)


@pytest.mark.parametrize('change', [
    lambda r: r['density']['pdf_values'].__setitem__(0, -1),
    lambda r: r['density']['upper_values'].pop(),
    lambda r: r['posterior'].__setitem__('samples', [[1, 2]]),
    lambda r: r['marginals']['events'][0].__setitem__('index', 2),
    lambda r: r['diagnostics'].__setitem__('weight_mean', [1]),
    lambda r: r.__setitem__('elapsed_seconds', 'bad'),
])
def test_invalid_saved_result_rejected(change):
    project = saved_project()
    change(project['summaries'][0]['saved_run']['result'])
    with pytest.raises(ValueError, match='saved Summary result'):
        dump_project(project)
