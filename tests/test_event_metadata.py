import pytest

from chronologer_app.projects import dump_project, import_csv, load_project, new_project


def test_event_labels_datums_and_inclusion_roundtrip():
    imported = import_csv(
        b'id,c14_mean,c14_err,curve,label,datum,include_in_calibration\n'
        b'A,2500,30,intcal20,Context A,BCAD,false\n'
        b'B,2550,30,intcal20,,,\n', 'labelled.csv')
    assert imported['events'][0]['label'] == 'Context A'
    assert imported['events'][0]['datum'] == 'BCAD'
    assert imported['events'][0]['include_in_calibration'] is False
    assert imported['events'][1]['datum'] == 'BP1950'
    assert imported['events'][1]['include_in_calibration'] is True
    project = new_project()
    project['events'] = imported['events'] + [
        {'id': 'N', 'distribution': 'normal', 'label': 'Context B', 'datum': 'BCAD',
         'parameters': {'mean': 100, 'sd': 10}},
        {'id': 'F', 'distribution': 'future', 'parameters': {'a': 1, 'b': 2, 'c': 3, 'extra': [4, 5]}},
    ]
    assert load_project(dump_project(project)) == project


@pytest.mark.parametrize('metadata', [
    {'label': None}, {'label': 'x' * 121}, {'datum': 'unknown'}, {'include_in_calibration': 'false'},
])
def test_invalid_event_metadata_is_rejected(metadata):
    project = new_project()
    project['events'] = [{'id': 'N', 'distribution': 'normal', 'parameters': {'mean': 1, 'sd': 2}, **metadata}]
    with pytest.raises(ValueError):
        dump_project(project)


def test_invalid_csv_inclusion_is_rejected():
    with pytest.raises(ValueError, match='true or false'):
        import_csv(b'id,c14_mean,c14_err,curve,include_in_calibration\nA,2500,30,intcal20,maybe', 'bad.csv')
