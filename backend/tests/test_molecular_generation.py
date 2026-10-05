import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.models import Project, TargetProtein, MolecularGenerationRun, GeneratedMolecule
from app.engines.molecular_generation import (
    MolecularGenerationManager, GenerationMode, GenerationRunStatus, NoveltyCategory,
    MolecularFilterConfig, ChemicalValidatorAndFilter, NoveltyAnalyzer,
    GenerationProvenanceTracker, RDKitMolecularEnumerator,
    FragmentRecombinationGenerator, DatabaseRetrievalGenerator,
    GenerativeModelAdapter
)

# In-memory test database fixture
TEST_DATABASE_URL = "sqlite:///:memory:"
engine_test = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine_test)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine_test)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# 1. Chemical Validation & Property Characterization Tests
# ===========================================================================

def test_valid_smiles_parsing_and_canonicalization():
    """Valid SMILES must parse, sanitize, canonicalize, and generate InChI / InChIKey."""
    is_valid, status, rej, can_smiles, inchi_str, inchikey_str, props, mol = (
        ChemicalValidatorAndFilter.validate_and_characterize("CC(=O)Oc1ccccc1C(=O)O")
    )
    assert is_valid is True
    assert status == "VALID"
    assert rej is None
    assert can_smiles == "CC(=O)Oc1ccccc1C(=O)O"
    assert inchi_str is not None and "InChI=" in inchi_str
    assert inchikey_str is not None and len(inchikey_str) == 27
    assert props["molecular_formula"] == "C9H8O4"
    assert props["heavy_atom_count"] == 13
    assert props["molecular_weight"] == 180.16
    assert props["rotatable_bonds"] == 2
    assert props["ring_count"] == 1
    assert mol is not None


def test_invalid_smiles_rejection_with_reason():
    """Invalid, nonsensical, or unparseable SMILES must be rejected with explicit reason."""
    for invalid in ["INVALID_SMILES", "C12345", "N(=O)(=O)(=O)(=O)C", "", None]:
        is_valid, status, rej, can_smiles, _, _, _, _ = (
            ChemicalValidatorAndFilter.validate_and_characterize(invalid)
        )
        assert is_valid is False
        assert status == "REJECTED"
        assert rej is not None
        assert can_smiles is None


def test_disconnected_salts_keep_largest_organic_fragment():
    """Salt mixtures (e.g. sodium carboxylates) must retain the main active organic fragment."""
    is_valid, status, _, can_smiles, _, _, props, _ = (
        ChemicalValidatorAndFilter.validate_and_characterize("[Na+].CC(=O)[O-]")
    )
    assert is_valid is True
    assert status == "VALID"
    assert "Na" not in can_smiles
    assert props["heavy_atom_count"] == 4


# ===========================================================================
# 2. Configurable Property Filtering Tests
# ===========================================================================

def test_filter_config_threshold_enforcement():
    """Configurable filter thresholds must pass compliant molecules and reject outliers."""
    # Aspirin: MW 180.16, LogP ~1.31
    _, _, _, _, _, _, props, _ = ChemicalValidatorAndFilter.validate_and_characterize("CC(=O)Oc1ccccc1C(=O)O")

    # Standard filter config passes
    cfg_pass = MolecularFilterConfig(mw_min=150.0, mw_max=300.0, logp_min=-1.0, logp_max=3.0)
    passed, results = ChemicalValidatorAndFilter.apply_filters(props, cfg_pass)
    assert passed is True
    assert all(r.passed for r in results)

    # Restrictive MW max filter fails
    cfg_fail = MolecularFilterConfig(mw_min=50.0, mw_max=160.0)
    passed_fail, results_fail = ChemicalValidatorAndFilter.apply_filters(props, cfg_fail)
    assert passed_fail is False
    mw_result = next(r for r in results_fail if r.property == "molecular_weight")
    assert mw_result.passed is False
    assert "outside threshold" in mw_result.reason


# ===========================================================================
# 3. Structural Alert (PAINS & Reactive) Screen Tests
# ===========================================================================

def test_structural_alert_screen_identifies_pains_and_reactive_motifs():
    """
    PAINS (rhodanine) and reactive (sulfonyl chloride) motifs must be detected.
    Screen must strictly declare STRUCTURAL_ALERT_SCREEN and never use 'SAFE'.
    """
    cfg = MolecularFilterConfig(enable_pains_filter=True, enable_reactive_filter=True)

    # Rhodanine core (PAINS alert)
    _, _, _, _, _, _, _, rhodanine_mol = ChemicalValidatorAndFilter.validate_and_characterize("O=C1NC(=S)SC1")
    alert_res = ChemicalValidatorAndFilter.screen_structural_alerts(rhodanine_mol, cfg)
    assert alert_res.passed is False
    assert alert_res.alerts_count > 0
    assert any("PAINS" in a for a in alert_res.alerts_detected)
    assert alert_res.screen_name == "STRUCTURAL_ALERT_SCREEN"
    assert "safety" not in alert_res.screen_name.lower()

    # Clean molecule (Aspirin) passes screen
    _, _, _, _, _, _, _, aspirin_mol = ChemicalValidatorAndFilter.validate_and_characterize("CC(=O)Oc1ccccc1C(=O)O")
    clean_res = ChemicalValidatorAndFilter.screen_structural_alerts(aspirin_mol, cfg)
    assert clean_res.passed is True
    assert clean_res.alerts_count == 0


# ===========================================================================
# 4. Novelty Analysis & Tanimoto Classification Tests
# ===========================================================================

def test_novelty_exact_match_and_tanimoto_similarity():
    """
    Identical commercial herbicide matches must be categorized KNOWN_EXACT_MATCH (similarity 1.0).
    Novel or modified analogs must be classified into HIGH, MODERATE, LOW, or NO_MATCH.
    """
    analyzer = NoveltyAnalyzer()

    # 1. Exact match with commercial herbicide (Imazethapyr)
    _, _, _, can_smiles, _, _, _, mol = ChemicalValidatorAndFilter.validate_and_characterize("CC1=NC(C(C)C)=NC(=O)C1=C2C=CC(=CC2=O)O")
    res_exact = analyzer.evaluate_novelty(mol, can_smiles)
    assert res_exact.exact_match is True
    assert res_exact.max_tanimoto_similarity == 1.0
    assert res_exact.closest_known_compound == "Imazethapyr"
    assert res_exact.novelty_category == NoveltyCategory.KNOWN_EXACT_MATCH

    # 2. Unrelated novel chemical (e.g. Adamantane-tetrazole)
    _, _, _, can_smiles_novel, _, _, _, mol_novel = ChemicalValidatorAndFilter.validate_and_characterize("c1nnn[nH]1")
    res_novel = analyzer.evaluate_novelty(mol_novel, can_smiles_novel)
    assert res_novel.exact_match is False
    assert res_novel.max_tanimoto_similarity < 0.60
    assert res_novel.novelty_category in [NoveltyCategory.LOW_SIMILARITY, NoveltyCategory.NO_MATCH_IN_SEARCHED_DATABASE]


# ===========================================================================
# 5. RDKit Enumeration Engine Tests
# ===========================================================================

def test_rdkit_chemical_enumeration_validity_and_reproducibility():
    """
    RDKitMolecularEnumerator must generate chemically valid molecules with identical
    reproducible output when provided the same random_seed.
    """
    enumerator = RDKitMolecularEnumerator()
    target_info = {"gene": "ALS", "target_family": "ALS"}

    run1 = enumerator.generate(target_info, parameters={}, random_seed=42, max_candidates=5)
    assert run1["status"] == "COMPLETED"
    assert len(run1["molecules"]) == 5

    smiles_run1 = [m["smiles"] for m in run1["molecules"]]
    for s in smiles_run1:
        is_valid, _, _, _, _, _, _, _ = ChemicalValidatorAndFilter.validate_and_characterize(s)
        assert is_valid is True, f"Generated molecule {s} must be chemically valid"

    # Deterministic reproducibility check
    run2 = enumerator.generate(target_info, parameters={}, random_seed=42, max_candidates=5)
    smiles_run2 = [m["smiles"] for m in run2["molecules"]]
    assert smiles_run1 == smiles_run2, "Same random_seed must produce identical enumerated molecules"


# ===========================================================================
# 6. Fragment Recombination Engine Tests
# ===========================================================================

def test_fragment_recombination_generator_validity():
    """FragmentRecombinationGenerator must recombine fragments into valid chemical structures."""
    recombinator = FragmentRecombinationGenerator()
    target_info = {"gene": "HPPD", "target_family": "HPPD"}

    res = recombinator.generate(target_info, parameters={}, random_seed=123, max_candidates=5)
    assert res["status"] == "COMPLETED"
    assert len(res["molecules"]) > 0

    for m in res["molecules"]:
        is_valid, _, _, _, _, _, _, _ = ChemicalValidatorAndFilter.validate_and_characterize(m["smiles"])
        assert is_valid is True, f"Recombined molecule {m['smiles']} must be chemically valid"


# ===========================================================================
# 7. Database Retrieval Engine Tests
# ===========================================================================

def test_database_retrieval_generator_provenance():
    """
    DatabaseRetrievalGenerator must retrieve known target inhibitors and preserve
    explicit provenance. Must never label them as AI-generated.
    """
    retriever = DatabaseRetrievalGenerator()
    target_info = {"gene": "ALS", "target_family": "ALS"}

    res = retriever.generate(target_info, parameters={}, max_candidates=4)
    assert res["status"] == "COMPLETED"
    assert len(res["molecules"]) == 4

    for m in res["molecules"]:
        assert m["generation_mode"] == GenerationMode.DATABASE_RETRIEVAL.value
        assert m["source_database"] == "PubChem"
        assert m["source_compound_id"] is not None
        assert m["source_url"] is not None
        assert m["retrieved_at"] is not None


# ===========================================================================
# 8. Generative AI Adapter NOT_AVAILABLE Semantic Tests
# ===========================================================================

def test_generative_ai_adapter_returns_not_available_when_not_installed():
    """
    GenerativeModelAdapter must strictly return status = NOT_AVAILABLE when no
    genuine local AI framework (e.g. REINVENT) is installed. Must NEVER fake output.
    """
    adapter = GenerativeModelAdapter(model_name="REINVENT-4")
    with patch.object(adapter, "is_installed", return_value=False):
        status = adapter.get_status()
        assert status["status"] == "NOT_AVAILABLE"

        gen_res = adapter.generate(
            target_info={"gene": "ALS", "target_family": "ALS"},
            parameters={},
            random_seed=42,
            max_candidates=10
        )
        assert gen_res["status"] == "NOT_AVAILABLE"
        assert len(gen_res["molecules"]) == 0
        assert "not installed" in gen_res["error"].lower()


# ===========================================================================
# 9. Target Validation Guard Tests
# ===========================================================================

def test_molecular_generation_manager_blocks_missing_target():
    """MolecularGenerationManager cannot execute without valid biological target information."""
    manager = MolecularGenerationManager()
    res = manager.execute_generation_run(
        target_info={},  # Empty/unvalidated target
        generation_mode=GenerationMode.RDKit_ENUMERATION,
        requested_count=10
    )
    assert res["status"] == GenerationRunStatus.FAILED.value
    assert "TARGET_VALIDATION_ERROR" in res["error"]
    assert res["generated_count"] == 0


def test_top_n_candidate_limit_enforcement():
    """Requested candidate counts exceeding safe thresholds must be clamped to HARD_MAX_CANDIDATES."""
    manager = MolecularGenerationManager()
    target_info = {"gene": "ALS", "target_family": "ALS"}

    res = manager.execute_generation_run(
        target_info=target_info,
        generation_mode=GenerationMode.RDKit_ENUMERATION,
        requested_count=500,  # Exceeds max 200
        random_seed=42
    )
    assert res["status"] == GenerationRunStatus.COMPLETED.value
    assert res["requested_count"] == 200  # Clamped


# ===========================================================================
# 10. Scientific Provenance Tracker Tests
# ===========================================================================

def test_provenance_tracker_generates_tamper_evident_sha256_hash():
    """Provenance record must include target, seed, parameters, and a SHA-256 hash."""
    target_info = {"target_id": 1, "gene": "ALS", "family": "ALS", "sequence": "MVKLA"}
    prov = GenerationProvenanceTracker.create_record(
        target_info=target_info,
        generation_mode=GenerationMode.RDKit_ENUMERATION,
        generator_name="RDKit Chemical Enumerator",
        generator_version="1.0.0",
        generation_method="Amide_Coupling",
        parameters={"scaffold": "Sulfonylurea"},
        random_seed=42
    )
    assert prov.target_id == 1
    assert prov.target_family == "ALS"
    assert prov.random_seed == 42
    assert prov.provenance_hash is not None
    assert len(prov.provenance_hash) == 64  # SHA-256 hex length


# ===========================================================================
# 11. API Endpoints & Firebase Project Isolation Tests
# ===========================================================================

def test_molecular_generation_api_crud_and_execution_lifecycle(client, db_session):
    """
    End-to-end integration test for molecular generation API:
    Create Run -> List Runs -> Execute Run -> Verify Generated Molecules & Provenance -> Query Detail.
    """
    # Create test project and validated target
    project = Project(
        name="Test Palmer Amaranth Discovery",
        owner_uid="user_123",
        weed_species="Amaranthus palmeri",
        crop_species="Glycine max",
        objective="new_herbicide"
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    target = TargetProtein(
        project_id=project.id,
        name="Palmer Amaranth ALS",
        gene="ALS",
        target_family="ALS",
        weed_sequence="MVKLA",
        is_primary_selected=True,
        pockets_json=[{"center": [12.0, 15.0, 18.0]}]
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)

    auth_headers = {"Authorization": "Bearer mock_token"}
    with patch("app.core.firebase.verify_firebase_token", return_value={"uid": "user_123", "email": "user@example.com"}):
        # 1. Create run
        run_payload = {
            "target_id": target.id,
            "generation_mode": "RDKit_ENUMERATION",
            "run_name": "ALS RDKit Library",
            "requested_count": 5,
            "random_seed": 42
        }
        res_create = client.post(f"/api/v1/projects/{project.id}/molecular-generation/runs", json=run_payload, headers=auth_headers)
        assert res_create.status_code == 200
        run_data = res_create.json()
        assert run_data["status"] == "PENDING"
        run_id = run_data["id"]

        # 2. List runs
        res_list = client.get(f"/api/v1/projects/{project.id}/molecular-generation/runs", headers=auth_headers)
        assert res_list.status_code == 200
        assert len(res_list.json()) == 1

        # 3. Execute run
        res_exec = client.post(f"/api/v1/projects/{project.id}/molecular-generation/runs/{run_id}/execute", headers=auth_headers)
        assert res_exec.status_code == 200
        exec_data = res_exec.json()
        assert exec_data["status"] == "COMPLETED"
        assert exec_data["valid_count"] > 0

        # 4. List generated molecules
        res_mols = client.get(f"/api/v1/projects/{project.id}/molecules?run_id={run_id}", headers=auth_headers)
        assert res_mols.status_code == 200
        mols = res_mols.json()
        assert len(mols) == exec_data["unique_count"]
        mol_id = mols[0]["id"]

        # 5. Get molecule detail with filter, novelty, and provenance records
        res_detail = client.get(f"/api/v1/projects/{project.id}/molecules/{mol_id}", headers=auth_headers)
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert "molecule" in detail
        assert "filter_results" in detail
        assert "novelty" in detail
        assert "provenance" in detail
        assert detail["provenance"]["target_id"] == target.id
        assert detail["provenance"]["provenance_hash"] is not None


def test_molecular_generation_api_enforces_firebase_owner_isolation(client, db_session):
    """Users cannot create or access molecular generation runs on projects owned by others."""
    project = Project(
        name="Private Project",
        owner_uid="user_owner",
        weed_species="Palmer Amaranth",
        crop_species="Soybean",
        objective="new_herbicide"
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    # User 'unauthorized_attacker' tries to access project
    attacker_headers = {"Authorization": "Bearer mock_token"}
    with patch("app.core.firebase.verify_firebase_token", return_value={"uid": "unauthorized_attacker", "email": "attacker@example.com"}):
        res_create = client.post(
            f"/api/v1/projects/{project.id}/molecular-generation/runs",
            json={"target_id": 1, "generation_mode": "RDKit_ENUMERATION"},
            headers=attacker_headers
        )
        assert res_create.status_code == 403
        assert "Access denied" in res_create.json()["detail"]

        res_list = client.get(f"/api/v1/projects/{project.id}/molecular-generation/runs", headers=attacker_headers)
        assert res_list.status_code == 403

        res_mols = client.get(f"/api/v1/projects/{project.id}/molecules", headers=attacker_headers)
        assert res_mols.status_code == 403
