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

def test_engines_status_endpoint():
    response = client.get("/api/v1/system/engines")
    assert response.status_code == 200
    data = response.json()
    assert "engines" in data
    assert "summary" in data
    assert "total_engines" in data
    assert data["total_engines"] == 11
    assert data["engines"]["rdkit"]["status"] == "READY"
    assert "p2rank" in data["engines"]

def test_create_project_and_pipeline():
    payload = {
        "name": "Pytest Discovery Project",
        "weed_species": "Amaranthus palmeri",
        "crop_species": "Glycine max",
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
