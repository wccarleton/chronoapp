from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chronologer_app.api import project_files as api
from chronologer_app.main import app
from chronologer_app.projects import load_project, new_project
from chronologer_app.services import project_files as files


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, 'project_files', files.ProjectFiles())
    with TestClient(app, base_url='http://127.0.0.1') as client:
        token = client.get('/api/projects/files/session').json()['token']
        client.headers['X-ChronoApp-Token'] = token
        yield client


def test_save_save_as_and_open_use_real_files(client, monkeypatch, tmp_path):
    first, second = tmp_path / 'first.chrono', tmp_path / 'second.chrono'
    selected = iter([first, second, second])
    calls = []
    def choose(mode, **kwargs):
        calls.append(mode)
        return next(selected)
    monkeypatch.setattr(files, 'choose_file', choose)
    project = new_project()
    project['metadata']['project_name'] = 'First'
    response = client.post('/api/projects/files/save', json={'project': project})
    assert response.status_code == 200, response.text
    reference = response.json()['file']
    assert Path(reference['path']) == first
    assert load_project(first.read_bytes()) == project
    project['metadata']['project_name'] = 'Edited'
    response = client.post('/api/projects/files/save', json={'project': project, 'file_id': reference['id']})
    assert response.status_code == 200
    assert response.json()['file']['id'] == reference['id']
    assert calls == ['save']
    assert load_project(first.read_bytes()) == project
    response = client.post('/api/projects/files/save', json={'project': project, 'file_id': reference['id'], 'save_as': True})
    assert response.status_code == 200
    assert response.json()['file']['id'] != reference['id']
    assert second.read_bytes() == first.read_bytes()
    opened = client.post('/api/projects/files/open').json()
    assert opened['project'] == project
    assert opened['file']['name'] == 'second.chrono'
    assert calls == ['save', 'save', 'open']


def test_cancel_and_validation_do_not_create_files(client, monkeypatch, tmp_path):
    monkeypatch.setattr(files, 'choose_file', lambda *args, **kwargs: None)
    assert client.post('/api/projects/files/open').json() == {'cancelled': True}
    assert client.post('/api/projects/files/save', json={'project': new_project()}).json() == {'cancelled': True}
    def never(*args, **kwargs):
        pytest.fail('Invalid data opened a native dialog')
    monkeypatch.setattr(files, 'choose_file', never)
    assert client.post('/api/projects/files/save', json={'project': {}}).status_code == 422


def test_atomic_failure_retains_original_file(client, monkeypatch, tmp_path):
    path = tmp_path / 'protected.chrono'
    monkeypatch.setattr(files, 'choose_file', lambda *args, **kwargs: path)
    project = new_project()
    reference = client.post('/api/projects/files/save', json={'project': project}).json()['file']
    original = path.read_bytes()
    def denied(*args):
        raise PermissionError('Simulated write restriction')
    monkeypatch.setattr(files.os, 'replace', denied)
    project['metadata']['project_name'] = 'Unsaved edit'
    response = client.post('/api/projects/files/save', json={'project': project, 'file_id': reference['id']})
    assert response.status_code == 409
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_stale_reference_and_external_edits_are_not_overwritten(client, monkeypatch, tmp_path):
    path = tmp_path / 'shared.chrono'
    monkeypatch.setattr(files, 'choose_file', lambda *args, **kwargs: path)
    project = new_project()
    reference = client.post('/api/projects/files/save', json={'project': project}).json()['file']
    path.write_bytes(b'External modification')
    response = client.post('/api/projects/files/save', json={'project': project, 'file_id': reference['id']})
    assert response.status_code == 409 and 'outside' in response.json()['detail']
    assert path.read_bytes() == b'External modification'
    assert client.post('/api/projects/files/save', json={'project': project, 'file_id': 'expired'}).status_code == 409


def test_no_arbitrary_paths_or_cross_origin_dialogs(client, monkeypatch):
    def never(*args, **kwargs):
        pytest.fail('Unauthorized request opened a dialog')
    monkeypatch.setattr(files, 'choose_file', never)
    assert client.post('/api/projects/files/save', json={'project': new_project(), 'path': 'outside.chrono'}).status_code == 422
    assert client.post('/api/projects/files/open', headers={'X-ChronoApp-Token': ''}).status_code == 403
    assert client.post('/api/projects/files/open', headers={'Origin': 'https://foreign.example'}).status_code == 403
    assert client.post('/api/projects/files/open', headers={'Origin': 'null'}).status_code == 403
    assert client.get('/api/projects/files/session', headers={'Host': 'foreign.example'}).status_code == 403
    assert client.get('/api/projects/files/session', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403


def test_invalid_open_leaves_no_reference(client, monkeypatch, tmp_path):
    path = tmp_path / 'invalid.chrono'
    path.write_bytes(b'not an archive')
    monkeypatch.setattr(files, 'choose_file', lambda *args, **kwargs: path)
    assert client.post('/api/projects/files/open').status_code == 422
    assert api.project_files.references == {}
