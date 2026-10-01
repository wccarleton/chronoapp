import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from chronologer_app.main import app
from chronologer_app.projects import dump_project, load_project, new_project


def phases():
    return [{'id': f'phase-{i}', 'label': name, 'distribution': family, 'order': order,
             'parameters': {}} for order, (i, name, family) in enumerate([
                 (1, 'Early', 'uniform'), (3, 'Middle', 'normal'), (2, 'Late', 'uniform')])]


def test_phase_api_roundtrip_preserves_semantics():
    project = new_project()
    project['phases'] = phases()
    with TestClient(app) as client:
        response = client.post('/api/projects/encode', json=project)
        assert response.status_code == 200, response.text
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert json.loads(archive.read('data/phases.json')) == phases()
        restored = client.post('/api/projects/decode', content=response.content)
        assert restored.status_code == 200
        assert restored.json() == project


def test_projects_without_phases_still_roundtrip_unchanged():
    project = new_project()
    assert 'phases' not in load_project(dump_project(project))
    assert load_project(dump_project(project)) == project


@pytest.mark.parametrize('change, message', [
    ({'order': 3}, 'order'), ({'id': 'phase-3'}, 'unique'),
    ({'distribution': 'mixture'}, 'distribution'), ({'label': ''}, 'label'),
    ({'parameters': []}, 'parameters'),
])
def test_invalid_phase_specs_are_rejected(change, message):
    project = new_project()
    project['phases'] = phases()
    project['phases'][0].update(change)
    with pytest.raises(ValueError, match=message):
        dump_project(project)
