import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_hardware_endpoint():
    response = client.get("/api/v1/system/hardware")
    assert response.status_code == 200
    data = response.json()
    assert "cpu" in data
    assert "gpu" in data

def test_create_project_and_pipeline():
    payload = {
        "name": "Pytest Discovery Project",
        "weed_species": "Palmer Amaranth",
        "crop_species": "Soybean",
        "objective": "new_herbicide"
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Pytest Discovery Project"
    project_id = data["id"]

    # Check stages initialized
    stages_resp = client.get(f"/api/v1/projects/{project_id}/stages")
    assert stages_resp.status_code == 200
    assert len(stages_resp.json()) == 7

def test_formulation_analyze_endpoint():
    payload = {
        "name": "Test Formulation",
        "active_ingredient": "MH-001",
        "active_concentration_g_l": 150.0,
        "solvent": "Water",
        "surfactant": "Tween 80"
    }
    response = client.post("/api/v1/formulation/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["compatibility_score"] > 0
    assert data["ph_predicted"] > 0

def test_pipeline_execution_integrity():
    from app.services.pipeline_service import DiscoveryPipelineRunner
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        payload = {
            "name": "Pipeline Integrity Test Project",
            "weed_species": "Palmer Amaranth",
            "crop_species": "Soybean",
            "objective": "new_herbicide"
        }
        response = client.post("/api/v1/projects", json=payload)
        assert response.status_code == 200
        proj_id = response.json()["id"]

        runner = DiscoveryPipelineRunner(db)
        res = runner.run_pipeline(proj_id)
        assert res["status"] == "COMPLETED"

        cand_resp = client.get(f"/api/v1/projects/{proj_id}/candidates")
        assert cand_resp.status_code == 200
        candidates = cand_resp.json()
        assert len(candidates) > 0

        for c in candidates:
            assert "evidence_level" in c
            assert "status" in c
            if c["evidence_level"] == 0:
                assert c["status"] == "HYPOTHESIS_ONLY"
    finally:
        db.close()

def test_firebase_status_endpoint():
    response = client.get("/api/v1/system/firebase")
    assert response.status_code == 200
    data = response.json()
    assert "firebase_active" in data
    assert "mode" in data

def test_firebase_auth_dependency_enforcement(monkeypatch):
    """When REQUIRE_FIREBASE_AUTH is enabled, missing or invalid token must return 401."""
    monkeypatch.setenv("REQUIRE_FIREBASE_AUTH", "true")
    payload = {
        "name": "Auth Guarded Project",
        "weed_species": "Palmer Amaranth",
        "crop_species": "Soybean",
        "objective": "new_herbicide"
    }

    # 1. Missing token -> 401
    resp_unauth = client.post("/api/v1/projects", json=payload)
    assert resp_unauth.status_code == 401
    assert "Unauthorized" in resp_unauth.json()["detail"]

    # 2. Invalid token -> 401
    resp_bad = client.post(
        "/api/v1/projects",
        json=payload,
        headers={"Authorization": "Bearer invalid_token_123"}
    )
    assert resp_bad.status_code == 401

    # 3. Valid test token -> 200
    resp_ok = client.post(
        "/api/v1/projects",
        json=payload,
        headers={"Authorization": "Bearer test_token_pawandeveloper"}
    )
    assert resp_ok.status_code == 200

def test_firestore_synchronization_called_on_pipeline():
    """Verify that sync_project_to_firestore is called when pipeline completes."""
    from unittest.mock import patch
    with patch("app.core.firebase.sync_project_to_firestore") as mock_sync:
        mock_sync.return_value = True
        payload = {
            "name": "Firestore Sync Test Project",
            "weed_species": "Palmer Amaranth",
            "crop_species": "Soybean",
            "objective": "new_herbicide"
        }
        res = client.post("/api/v1/projects", json=payload)
        assert res.status_code == 200
        # Check that sync_project_to_firestore was called
        assert mock_sync.called is True

def test_candidate_status_codes_in_api():
    """Verify boltz_status and gnina_status are populated and exposed in CandidateResponse."""
    from app.services.pipeline_service import DiscoveryPipelineRunner
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        payload = {
            "name": "Status Exposure Test Project",
            "weed_species": "Palmer Amaranth",
            "crop_species": "Soybean",
            "objective": "new_herbicide"
        }
        create_res = client.post("/api/v1/projects", json=payload)
        proj_id = create_res.json()["id"]

        runner = DiscoveryPipelineRunner(db)
        runner.run_pipeline(proj_id)

        cand_resp = client.get(f"/api/v1/projects/{proj_id}/candidates")
        assert cand_resp.status_code == 200
        candidates = cand_resp.json()
        assert len(candidates) > 0
        for c in candidates:
            assert "boltz_status" in c
            assert "gnina_status" in c
            assert c["boltz_status"] in ("COMPLETED", "NOT_INSTALLED", "FAILED_EXECUTION", "FAILED_OUTPUT_PARSE", "POCKET_CENTER_MISSING", "NOT_AVAILABLE")
            assert c["gnina_status"] in ("COMPLETED", "NOT_INSTALLED", "FAILED_EXECUTION", "FAILED_OUTPUT_PARSE", "POCKET_CENTER_MISSING", "NOT_AVAILABLE")
    finally:
        db.close()

