from fastapi.testclient import TestClient

from chronologer_app.main import app


def test_frontend_served_with_its_modules():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="calibrate-panel"' in response.text
    assert 'id="process-panel"' in response.text
    for asset in (
        "css/app.css", "js/app.js", "js/calibrate.js", "js/api.js",
        "js/plots.js", "js/plot-interactions.js", "js/plot-export.js", "js/theme.js",
        "js/project.js", "js/project-state.js",
        "js/phase.js",
        "vendor/jspdf.umd.min.js", "vendor/svg2pdf.umd.min.js",
        "vendor/DejaVuSans.ttf", "vendor/DejaVuSans-Bold.ttf",
    ):
        assert client.get(f"/{asset}").status_code == 200
