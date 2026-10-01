"""Data-only project serialization and the CSV -> file -> fresh-session benchmark."""

import io
import json
import zipfile
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from chronologer_app.main import app
from chronologer_app.projects import dump_project, import_csv, load_project, new_project

CSV = b'id,c14_mean,c14_err,curve\r\nA1,1045,25,intcal20\r\n"B, two",3240,30,intcal20\r\nC3,4500,35,intcal20\r\n'


def example():
    project = new_project()
    project['metadata']['project_name'] = 'My dates'
    project.update(import_csv(CSV, 'dates.csv'))
    return project


def test_csv_canonical_records_and_provenance():
    imported = import_csv(CSV, 'dates.csv')
    assert imported['events'][0] == {'id': 'A1', 'distribution': 'calrcarbon',
        'parameters': {'c14_mean': 1045., 'c14_err': 25., 'curve': 'intcal20'}}
    assert imported['events'][1]['id'] == 'B, two'
    assert imported['source_csv']['text'].encode('utf-8') == CSV


def test_csv_explicit_default_and_bom():
    csv = b'\xef\xbb\xbfid,c14_mean,c14_err\nA,1045,25\n'
    assert import_csv(csv, 'a.csv', 'intcal20')['events'][0]['parameters']['curve'] == 'intcal20'
    assert import_csv(csv, 'a.csv', 'intcal20')['source_csv']['text'].encode('utf-8') == csv
    with pytest.raises(ValueError, match='supply curve'):
        import_csv(csv, 'a.csv')


@pytest.mark.parametrize('csv, message', [
    (b'id,age,error\nA,1045,25\n', 'requires columns'),
    (b'id,c14_mean,c14_err\nA,no,25\n', 'must be numbers'),
    (b'id,c14_mean,c14_err\nA,nan,25\n', 'finite number'),
    (b'id,c14_mean,c14_err\nA,1045,0\n', 'greater than zero'),
    (b'id,c14_mean,c14_err\n,1045,25\n', 'ID'),
    (b'id,c14_mean,c14_err\nA,1045\n', 'column count'),
    (b'id,c14_mean,c14_err\nA,1045,25,extra\n', 'column count'),
    (b'id,c14_mean,c14_err\n"unclosed,1045,25', 'Malformed CSV'),
    (b'id,c14_mean,c14_err\n', 'no event rows'),
    (b'id,c14_mean,c14_err,curve\nA,1045,25,unknown\n', 'unsupported calibration curve'),
    (b'id,c14_mean,c14_err,id\nA,1045,25,B\n', 'duplicate'),
    (b'\xff', 'UTF-8'),
])
def test_invalid_csv(csv, message):
    with pytest.raises(ValueError, match=message):
        import_csv(csv, 'bad.csv', 'intcal20')


def test_archive_structure_and_exact_roundtrip():
    project = example()
    content = dump_project(project)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert set(archive.namelist()) == {'project.json', 'data/events.json', 'data/source.csv', 'data/source.json'}
        assert json.loads(archive.read('project.json')) == project['metadata']
        assert json.loads(archive.read('data/events.json')) == project['events']
        assert archive.read('data/source.csv') == CSV
    assert load_project(content) == project


def test_empty_project_and_no_source_roundtrip():
    project = new_project()
    assert load_project(dump_project(project)) == project
    with zipfile.ZipFile(io.BytesIO(dump_project(project))) as archive:
        assert set(archive.namelist()) == {'project.json', 'data/events.json'}


def test_future_distribution_is_data_only_and_preserved():
    project = new_project()
    project['events'] = [{'id': 'future', 'distribution': 'future_measurement',
                          'parameters': {'mean': 123, 'nested': [1, 2], 'label': '__import__("os")'}}]
    assert load_project(dump_project(project)) == project


def archive_with(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return stream.getvalue()


def test_unknown_project_version():
    meta = new_project()['metadata']
    meta['format_version'] = 2
    content = archive_with({'project.json': json.dumps(meta), 'data/events.json': '[]'})
    with pytest.raises(ValueError, match='Unsupported project format version'):
        load_project(content)


@pytest.mark.parametrize('extra', ['../outside.json', 'state.pkl', 'model.py'])
def test_archive_does_not_accept_executable_or_extra_entries(extra):
    entries = {'project.json': json.dumps(new_project()['metadata']), 'data/events.json': '[]', extra: 'anything'}
    with pytest.raises(ValueError, match='Invalid project archive entries'):
        load_project(archive_with(entries))


@pytest.mark.parametrize('content', [b'not a zip', b'\x80\x04N.', archive_with({'project.json': '{}'})])
def test_malformed_project(content):
    with pytest.raises(ValueError):
        load_project(content)


def test_invalid_draft_cannot_be_saved():
    project = example()
    project['events'][0]['parameters']['c14_mean'] = None
    with pytest.raises(ValueError, match='finite number'):
        dump_project(project)


def test_csv_save_clear_reopen_benchmark(tmp_path):
    # An arbitrary user-selected directory, outside the application installation.
    destination = tmp_path / 'chosen location' / 'example.chrono'
    destination.parent.mkdir()
    with TestClient(app) as first_session:
        original = first_session.get('/api/projects/new').json()
        original['metadata']['project_name'] = 'Benchmark dates'
        response = first_session.post('/api/projects/import-csv?filename=dates.csv', content=CSV)
        assert response.status_code == 200, response.text
        original.update(response.json())
        encoded = first_session.post('/api/projects/encode', json=original)
        assert encoded.status_code == 200, encoded.text
        destination.write_bytes(encoded.content)
    # No shared server document state or original import is needed to reopen.
    with TestClient(app) as reopened_session:
        assert reopened_session.get('/api/projects/new').json()['events'] == []
        response = reopened_session.post('/api/projects/decode', content=destination.read_bytes())
        assert response.status_code == 200, response.text
        assert response.json() == original


def test_api_invalid_files_have_useful_errors():
    with TestClient(app) as client:
        assert client.post('/api/projects/decode', content=b'not zip').status_code == 422
        response = client.post('/api/projects/import-csv', content=b'id,age\nA,4\n')
        assert response.status_code == 422
        assert 'requires columns' in response.json()['detail']
