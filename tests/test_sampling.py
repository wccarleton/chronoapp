import pytest
from pydantic import ValidationError
from chronologer_app.sampling import SamplingSettings, resolve_cores, validate_saved_sampling


def test_auto_and_explicit_cpu_limits(monkeypatch):
    monkeypatch.setattr('chronologer_app.sampling.os.cpu_count', lambda: 8)
    assert resolve_cores(8) == 4
    assert resolve_cores(2) == 2
    assert resolve_cores(16, 12) == 8
    assert resolve_cores(4, 1) == 1
    for value in (0, -1, True, 1.5):
        with pytest.raises(ValidationError):
            SamplingSettings(cores=value)


def test_saved_legacy_auto_and_explicit_settings():
    base = dict(draws=10, tune=10, chains=4)
    result = {'sampling': {**base, 'cores': 2}}
    for settings in (base, {**base, 'cores': None}, {**base, 'cores': 8}):
        validate_saved_sampling({'sampling': settings}, result)
    with pytest.raises(ValueError):
        validate_saved_sampling({'sampling': {**base, 'cores': 0}}, result)
