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
