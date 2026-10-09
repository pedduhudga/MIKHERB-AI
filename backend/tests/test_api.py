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
    assert data["rdkit"]["status"] in ("SCIENTIFICALLY_VALIDATED", "PROBE_VALIDATED", "INSTALLED")



def test_firebase_auth_production_default(monkeypatch):
    """Verify that is_auth_required defaults to True in production (when PYTEST_CURRENT_TEST is unset)."""
    from app.core.firebase import is_auth_required
    monkeypatch.delenv("REQUIRE_FIREBASE_AUTH", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert is_auth_required() is True


def test_unauthenticated_access_to_protected_endpoints(monkeypatch):
    """Verify that all non-health endpoints return 401 when unauthenticated under REQUIRE_FIREBASE_AUTH."""
    monkeypatch.setenv("REQUIRE_FIREBASE_AUTH", "true")

    # 1. Health/Connectivity endpoints are public (200)
    assert client.get("/api/v1/system/hardware").status_code == 200
    assert client.get("/api/v1/system/firebase").status_code == 200

    # 2. Engines, chemistry, formulation, experiments, AI lab, and agent endpoints require auth (401)
    assert client.get("/api/v1/system/engines").status_code == 401
    assert client.post("/api/v1/system/engines/validate").status_code == 401
    assert client.post("/api/v1/system/engines/probe").status_code == 401
    assert client.post("/api/v1/system/engines/validate_scientific").status_code == 401
    assert client.get("/api/v1/chemistry/descriptors?smiles=CC").status_code == 401
    assert client.get("/api/v1/chemistry/pubchem_search?query=glyphosate").status_code == 401
    assert client.get("/api/v1/formulation").status_code == 401
    assert client.get("/api/v1/experiments").status_code == 401
    assert client.post("/api/v1/ai_lab/train_qsar").status_code == 401
    assert client.post("/api/v1/ai_lab/active_learning_prioritize", json=["CC"]).status_code == 401
    assert client.post("/api/v1/agent/chat", params={"query": "test"}).status_code == 401
    assert client.get("/api/v1/agent/tools").status_code == 401


def test_configurable_downstream_target_count():
    """Verify that projects can configure downstream_target_count (Top 1, 3, 5, etc)."""
    payload = {
        "name": "Configurable Top-N Discovery",
        "weed_species": "Palmer Amaranth",
        "crop_species": "Soybean",
        "objective": "new_herbicide",
        "downstream_target_count": 5
    }
    resp = client.post("/api/v1/projects", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["downstream_target_count"] == 5

    get_resp = client.get(f"/api/v1/projects/{data['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["downstream_target_count"] == 5


def test_strict_project_ownership_no_null_exposure():
    """
    Security Regression Test:
    Authenticated users must NEVER receive unowned/legacy projects (owner_uid == NULL)
    or projects owned by another user.
    """
    from app.db.database import SessionLocal
    from app.models.models import Project

    db = SessionLocal()
    p_user_a = Project(
        name="User A Project",
        owner_uid="user_a_123",
        weed_species="Palmer Amaranth",
        crop_species="Soybean",
        objective="new_herbicide"
    )
    p_user_b = Project(
        name="User B Project",
        owner_uid="user_b_456",
        weed_species="Barnyard Grass",
        crop_species="Rice",
        objective="new_herbicide"
    )
    p_unowned = Project(
        name="Legacy Unowned Project",
        owner_uid=None,
        weed_species="Kochia",
        crop_species="Wheat",
        objective="new_herbicide"
    )
    db.add_all([p_user_a, p_user_b, p_unowned])
    db.commit()
    db.refresh(p_user_a)
    db.refresh(p_user_b)
    db.refresh(p_unowned)

    headers_a = {"Authorization": "Bearer test_token_user_a_123"}
    resp = client.get("/api/v1/projects", headers=headers_a)
    assert resp.status_code == 200
    returned_projects = resp.json()
    returned_ids = [p["id"] for p in returned_projects]

    assert p_user_a.id in returned_ids
    assert p_user_b.id not in returned_ids
    assert p_unowned.id not in returned_ids, "Unowned projects (owner_uid == NULL) must NEVER be exposed to authenticated users"

    # User A attempting to directly GET unowned project must be forbidden (403)
    get_unowned_resp = client.get(f"/api/v1/projects/{p_unowned.id}", headers=headers_a)
    assert get_unowned_resp.status_code == 403

    # Clean up test rows
    db.delete(p_user_a)
    db.delete(p_user_b)
    db.delete(p_unowned)
    db.commit()
    db.close()


def test_get_target_pdb_endpoint(tmp_path):
    """Verify that /api/v1/targets/{target_id}/pdb serves target PDB content and handles missing targets."""
    from app.db.database import SessionLocal
    from app.models.models import Project, TargetProtein

    db = SessionLocal()
    try:
        proj = Project(
            name="Target PDB Test Project",
            weed_species="Palmer Amaranth",
            crop_species="Soybean",
            objective="new_herbicide"
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)

        dummy_pdb = str(tmp_path / "test_target.pdb")
        dummy_pdb_text = "HEADER    TEST TARGET PDB\nATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 90.00           C\nEND\n"
        with open(dummy_pdb, "w") as f:
            f.write(dummy_pdb_text)

        target = TargetProtein(
            project_id=proj.id,
            name="ALS Target Protein",
            gene="ALS",
            target_family="ALS / AHAS",
            pdb_id=dummy_pdb,
            uniprot_id="P10324"
        )
        db.add(target)
        db.commit()
        db.refresh(target)

        # 1. Fetch valid target PDB -> 200 with text/plain content
        resp = client.get(f"/api/v1/targets/{target.id}/pdb")
        assert resp.status_code == 200
        assert "TEST TARGET PDB" in resp.text

        # 2. Fetch non-existent target ID -> 404
        resp_404 = client.get("/api/v1/targets/99999/pdb")
        assert resp_404.status_code == 404
    finally:
        db.close()

