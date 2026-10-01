"""The application's numerical boundary must preserve the engine's output."""

import chronologer
import numpy as np
import pytest
from fastapi.testclient import TestClient

from chronologer_app.main import app

client = TestClient(app)


@pytest.mark.parametrize("ages,errors", [([3240], [25]), ([3240, 4500], [25, 30])])
def test_results_match_direct_engine_call(ages, errors):
    rows = [{"id": f"Sample {i}", "age": age, "error": error} for i, (age, error) in enumerate(zip(ages, errors))]
    response = client.post("/api/calibrate", json={"curve": "intcal20", "determinations": rows})
    assert response.status_code == 200, response.text
    direct = chronologer.calibrate([-age for age in ages], errors, chronologer.load_calcurve("intcal20", quiet=True), as_pandas=False)
    body = response.json()
    assert body["coordinate_system"] == "negative_bp"
    assert len(body["results"]) == len(rows)
    for result, expected, row in zip(body["results"], direct, rows):
        assert result["id"] == row["id"]
        assert result["age"] == row["age"]
        np.testing.assert_array_equal(result["t_values"], expected["t_values"])
        np.testing.assert_array_equal(result["pdf_values"], expected["pdf_values"])
        assert result["posterior_mean"] == expected["mean"]
        assert result["hdi_probability"] == 0.95
        np.testing.assert_array_equal(result["hdi_intervals"], expected["hdi_intervals"])
        assert result["t_values"][0] <= result["posterior_mean"] <= result["t_values"][-1]


@pytest.mark.parametrize("row", [
    {"id": "Sample", "age": 3240},
    {"id": "Sample", "error": 25},
    {"id": " ", "age": 3240, "error": 25},
    {"id": "Sample", "age": "invalid", "error": 25},
    {"id": "Sample", "age": 3240, "error": 0},
    {"id": "Sample", "age": 3240, "error": -25},
    {"id": "Sample", "age": None, "error": 25},
    {"id": "Sample", "age": True, "error": 25},
    {"id": "Sample", "age": 3240, "error": "NaN"},
])
def test_invalid_rows(row):
    response = client.post("/api/calibrate", json={"curve": "intcal20", "determinations": [row]})
    assert response.status_code == 422


def test_unsupported_curve():
    response = client.post("/api/calibrate", json={"curve": "unknown", "determinations": [{"id": "A", "age": 3240, "error": 25}]})
    assert response.status_code == 422
    assert client.get("/api/curves/unknown").status_code == 422


def test_empty_and_malformed_requests():
    assert client.post("/api/calibrate", json={"curve": "intcal20", "determinations": []}).status_code == 422
    assert client.post("/api/calibrate", content="{", headers={"Content-Type": "application/json"}).status_code == 422


def test_unusable_age_is_a_useful_error():
    response = client.post("/api/calibrate", json={"curve": "intcal20", "determinations": [{"id": "A", "age": 1e9, "error": 25}]})
    assert response.status_code == 422
    assert "usable range" in response.json()["detail"]


def test_curve_catalog_and_data():
    from chronologer.calcurves import DEFAULT_CURVES

    catalog = client.get("/api/curves").json()
    assert {item["id"] for item in catalog["curves"]} == set(DEFAULT_CURVES)
    curve = client.get("/api/curves/intcal20").json()
    expected = chronologer.load_calcurve("intcal20", quiet=True)
    for key in ("calbp", "c14bp", "c14_sigma"):
        np.testing.assert_array_equal(curve[key], expected[key])


def test_unavailable_curve_does_not_download(monkeypatch, tmp_path):
    import chronologer_app.api.calibration as api

    monkeypatch.setattr(api, "CACHE_DIR", str(tmp_path))
    assert client.get("/api/curves/intcal20").status_code == 409
    assert not any(item["available"] for item in client.get("/api/curves").json()["curves"])
