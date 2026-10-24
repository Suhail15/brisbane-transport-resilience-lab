"""The optional prepared study is separate from custom calculation endpoints."""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from resilience import api


def test_case_study_absence_and_prepared_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "archive", SimpleNamespace(root=tmp_path))
    client = TestClient(api.app)
    assert client.get("/v1/case-study").status_code == 404
    path = tmp_path / "processed/corridor-impact-v2/case-study.json"
    path.parent.mkdir(parents=True)
    study = {"schema_version": 1, "study_id": "fixture-only", "dates": []}
    path.write_text(json.dumps(study))
    response = client.get("/v1/case-study")
    assert response.status_code == 200
    assert response.json() == study
