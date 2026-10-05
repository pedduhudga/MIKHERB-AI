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
    """Verify that sync_project_to_firestore is called when pipeline creates or updates projects."""
    from unittest.mock import patch, MagicMock
    with patch("app.core.firebase._firebase_initialized", True), \
         patch("app.core.firebase._firestore_client", MagicMock()), \
         patch("app.core.firebase.sync_project_to_firestore") as mock_sync:
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


def test_project_ownership_multi_tenant_authorization():
    """Verify that a project created by User A cannot be accessed or modified by User B."""
    payload = {
        "name": "User A Private Discovery Project",
        "weed_species": "Palmer Amaranth",
        "crop_species": "Soybean",
        "objective": "new_herbicide"
    }
    user_a_headers = {"Authorization": "Bearer test_token_user_a_uid"}
    user_b_headers = {"Authorization": "Bearer test_token_user_b_uid"}

    # 1. User A creates project
    create_resp = client.post("/api/v1/projects", json=payload, headers=user_a_headers)
    assert create_resp.status_code == 200
    data = create_resp.json()
    proj_id = data["id"]
    assert data["owner_uid"] == "user_a_uid"

    # 2. User A can retrieve their own project and stages
    get_resp_a = client.get(f"/api/v1/projects/{proj_id}", headers=user_a_headers)
    assert get_resp_a.status_code == 200
    assert get_resp_a.json()["id"] == proj_id

    stages_resp_a = client.get(f"/api/v1/projects/{proj_id}/stages", headers=user_a_headers)
    assert stages_resp_a.status_code == 200

    cand_resp_a = client.get(f"/api/v1/projects/{proj_id}/candidates", headers=user_a_headers)
    assert cand_resp_a.status_code == 200

    # 3. User B is strictly forbidden from accessing User A's project
    get_resp_b = client.get(f"/api/v1/projects/{proj_id}", headers=user_b_headers)
    assert get_resp_b.status_code == 403
    assert "Forbidden" in get_resp_b.json()["detail"]

    stages_resp_b = client.get(f"/api/v1/projects/{proj_id}/stages", headers=user_b_headers)
    assert stages_resp_b.status_code == 403

    cand_resp_b = client.get(f"/api/v1/projects/{proj_id}/candidates", headers=user_b_headers)
    assert cand_resp_b.status_code == 403

    run_resp_b = client.post(f"/api/v1/projects/{proj_id}/run", headers=user_b_headers)
    assert run_resp_b.status_code == 403


def test_system_engines_validate_endpoint():
    """Verify live validation probe endpoint runs across all engines."""
    resp = client.post("/api/v1/system/engines/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert "rdkit" in data
    assert "gnina" in data
    assert "boltz" in data
    assert data["rdkit"]["status"] in ("VALIDATED", "INSTALLED")


def test_firebase_auth_production_default(monkeypatch):
    """Verify that is_auth_required defaults to True in production (when PYTEST_CURRENT_TEST is unset)."""
    from app.core.firebase import is_auth_required
    monkeypatch.delenv("REQUIRE_FIREBASE_AUTH", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert is_auth_required() is True

