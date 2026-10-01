import pytest

from chronologer_app.projects import dump_project, load_project, new_project


def summary_project():
    project = new_project()
    project['summaries'] = [{
        'id': 'summary-1', 'label': 'Occupation', 'model': 'mixture', 'parameters': {},
        'events': [{'id': 'A', 'distribution': 'calrcarbon',
                    'parameters': {'c14_mean': 3000, 'c14_err': 30, 'curve': 'intcal20'}}],
    }]
    return project


def test_summary_snapshots_roundtrip_without_source_dataset():
    project = summary_project()
    assert project['events'] == []
    assert load_project(dump_project(project)) == project
    old = new_project()
    assert load_project(dump_project(old)) == old


@pytest.mark.parametrize('change', [
    {'model': 'unknown'}, {'label': ''}, {'events': [{}]}, {'parameters': []},
])
def test_invalid_summary_rejected(change):
    project = summary_project()
    project['summaries'][0].update(change)
    with pytest.raises(ValueError):
        dump_project(project)
