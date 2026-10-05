import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.models import Project, TargetProtein, MolecularGenerationRun, GeneratedMolecule, Compound, ChemicalLibrary
from app.engines.molecular_generation import (
    MolecularGenerationManager, GenerationMode, GenerationRunStatus, NoveltyCategory,
    MolecularFilterConfig, ChemicalValidatorAndFilter, NoveltyAnalyzer,
    GenerationProvenanceTracker, RDKitMolecularEnumerator,
    FragmentRecombinationGenerator, DatabaseRetrievalGenerator,
    GenerativeModelAdapter
)
from app.services.pipeline_service import DiscoveryPipelineRunner

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
# 4. Multi-Database Novelty Scope & Tanimoto Classification Tests
# ===========================================================================

def test_novelty_multi_database_scope_and_tanimoto():
    """
    NoveltyAnalyzer must evaluate across multiple database scopes:
    Reference Catalogue, PubChem, ChEMBL, and Internal Project DB.
    """
    analyzer = NoveltyAnalyzer(internal_candidates=[
        {"smiles": "CC(=O)Oc1ccccc1C(=O)O", "compound_code": "MH-INTERNAL-01"}
    ])

    # 1. Exact match with internal reference catalogue (Imazethapyr)
    _, _, _, can_smiles, _, _, _, mol = ChemicalValidatorAndFilter.validate_and_characterize("CC1=NC(C(C)C)=NC(=O)C1=C2C=CC(=CC2=O)O")
    res_exact = analyzer.evaluate_novelty(mol, can_smiles, query_external_apis=False)
    assert res_exact.exact_match is True
    assert res_exact.max_tanimoto_similarity == 1.0
    assert res_exact.closest_known_compound == "Imazethapyr"
    assert res_exact.novelty_category == NoveltyCategory.KNOWN_EXACT_MATCH
    assert "MIKHERB_REFERENCE_CATALOGUE" in res_exact.database_scope
    assert "PUBCHEM" in res_exact.database_scope
    assert "CHEMBL" in res_exact.database_scope
    assert "INTERNAL_PROJECT_DATABASE" in res_exact.database_scope

    # 2. Exact match with internal project database candidate (Aspirin)
    _, _, _, can_asp, _, _, _, mol_asp = ChemicalValidatorAndFilter.validate_and_characterize("CC(=O)Oc1ccccc1C(=O)O")
    res_internal = analyzer.evaluate_novelty(mol_asp, can_asp, query_external_apis=False)
    assert res_internal.exact_match is True
    assert res_internal.novelty_category == NoveltyCategory.KNOWN_EXACT_MATCH
    assert res_internal.databases_checked["INTERNAL_PROJECT_DATABASE"]["exact_match"] is True

    # 3. Novel chemical candidate
    _, _, _, can_novel, _, _, _, mol_novel = ChemicalValidatorAndFilter.validate_and_characterize("c1nnn[nH]1")
    res_novel = analyzer.evaluate_novelty(mol_novel, can_novel, query_external_apis=False)
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
    """
    FragmentRecombinationGenerator must recombine fragments using authentic BRICS synthons.
    Must never use unguided arbitrary atom-0 single-bond coupling.
    """
    recombinator = FragmentRecombinationGenerator()
    target_info = {"gene": "HPPD", "target_family": "HPPD"}

    res = recombinator.generate(target_info, parameters={}, random_seed=123, max_candidates=5)
    assert res["status"] == "COMPLETED"
    assert len(res["molecules"]) > 0

    for m in res["molecules"]:
        is_valid, _, _, _, _, _, _, _ = ChemicalValidatorAndFilter.validate_and_characterize(m["smiles"])
        assert is_valid is True, f"Recombined molecule {m['smiles']} must be chemically valid"
        assert m["recombination_method"] == "RDKit_BRICS_Grammar_Assembly"


# ===========================================================================
# 7. Database Retrieval Engine Tests (with Live & Fallback Provenance)
# ===========================================================================

def test_database_retrieval_generator_provenance():
    """
    DatabaseRetrievalGenerator must retrieve known target inhibitors and preserve
    explicit provenance with audit hash and endpoint details. Must never label as AI-generated.
    """
    retriever = DatabaseRetrievalGenerator()
    target_info = {"gene": "ALS", "target_family": "ALS"}

    res = retriever.generate(target_info, parameters={"prefer_live_api": False}, max_candidates=4)
    assert res["status"] == "COMPLETED"
    assert len(res["molecules"]) > 0

    for m in res["molecules"]:
        assert m["generation_mode"] == GenerationMode.DATABASE_RETRIEVAL.value
        assert m["source_database"] == "PubChem"
        assert m["source_compound_id"] is not None
        assert m["source_url"] is not None
        assert m["retrieval_method"] in ["PUBCHEM_REST_API", "LOCAL_CURATED_BENCHMARK"]
        assert m["response_hash"] is not None
        assert m["query_endpoint"] is not None
        assert m["retrieved_at"] is not None


# ===========================================================================
# 8. Generative AI Adapter Lifecycle & NOT_AVAILABLE Tests
# ===========================================================================

def test_generative_ai_adapter_lifecycle_tiers():
    """
    GenerativeModelAdapter must distinguish lifecycle tiers:
    NOT_INSTALLED -> INSTALLED (unconfigured weights) -> MODEL_CONFIGURED.
    Must strictly return status = NOT_AVAILABLE when model or weights are missing.
    """
    # 1. Model binary absent -> NOT_INSTALLED
    adapter_uninstalled = GenerativeModelAdapter(model_name="REINVENT-4")
    with patch.object(adapter_uninstalled, "is_installed", return_value=False):
        status = adapter_uninstalled.get_status()
        assert status["tier"] == "NOT_INSTALLED"
        assert status["status"] == "NOT_AVAILABLE"

    # 2. Binary present but weights unconfigured -> INSTALLED
    adapter_installed = GenerativeModelAdapter(model_name="REINVENT-4")
    with patch.object(adapter_installed, "is_installed", return_value=True):
        with patch.object(adapter_installed, "has_configured_weights", return_value=False):
            status = adapter_installed.get_status()
            assert status["tier"] == "INSTALLED"
            assert status["status"] == "NOT_AVAILABLE"

            gen_res = adapter_installed.generate(
                target_info={"gene": "ALS", "target_family": "ALS"},
                parameters={},
                random_seed=42
            )
            assert gen_res["status"] == "NOT_AVAILABLE"
            assert len(gen_res["molecules"]) == 0
            assert "weights not configured" in gen_res["error"].lower()


# ===========================================================================
# 9. Target Validation Gate & Candidate Limit Tests
# ===========================================================================

def test_molecular_generation_manager_strict_7_stage_target_validation_gate():
    """
    MolecularGenerationManager enforces the mandatory 7-stage prerequisite validation chain:
    1. TARGET_DISCOVERED
    2. TARGET_IDENTITY_VERIFIED
    3. GENE_VERIFIED
    4. FUNCTION_VERIFIED
    5. WEED_SPECIES_VERIFIED
    6. PROTEIN_VALIDATED
    7. STRUCTURE_POCKET_VALIDATED
    """
    manager = MolecularGenerationManager()

    # 1. Missing target info completely
    res1 = manager.execute_generation_run(target_info={}, generation_mode=GenerationMode.RDKit_ENUMERATION)
    assert res1["status"] == GenerationRunStatus.FAILED.value
    assert "TARGET_VALIDATION_ERROR" in res1["error"]

    # 2. Stage 1: Missing gene or target_family
    res_s1 = manager.execute_generation_run(
        target_info={"id": 1, "weed_species": "Amaranthus palmeri", "sequence": "MVKLAARSTPGRSVVTALKP"},
        generation_mode=GenerationMode.RDKit_ENUMERATION
    )
    assert res_s1["status"] == GenerationRunStatus.FAILED.value
    assert "TARGET_DISCOVERED" in res_s1["error"]

    # 3. Stage 2: Missing target ID / UniProt accession
    res_s2 = manager.execute_generation_run(
        target_info={"gene": "ALS", "target_family": "ALS", "weed_species": "Amaranthus palmeri", "sequence": "MVKLAARSTPGRSVVTALKP"},
        generation_mode=GenerationMode.RDKit_ENUMERATION
    )
    assert res_s2["status"] == GenerationRunStatus.FAILED.value
    assert "TARGET_IDENTITY_VERIFIED" in res_s2["error"]

    # 4. Stage 3: Explicitly unverified gene
    res_s3 = manager.execute_generation_run(
        target_info={
            "id": 1, "gene": "ALS", "target_family": "ALS", "gene_verified": False,
            "weed_species": "Amaranthus palmeri", "sequence": "MVKLAARSTPGRSVVTALKP"
        },
        generation_mode=GenerationMode.RDKit_ENUMERATION
    )
    assert res_s3["status"] == GenerationRunStatus.FAILED.value
    assert "GENE_VERIFIED" in res_s3["error"]

    # 5. Stage 4: Unverified function
    res_s4 = manager.execute_generation_run(
        target_info={
            "id": 1, "gene": "ALS", "target_family": "ALS", "function_verified": False,
            "weed_species": "Amaranthus palmeri", "sequence": "MVKLAARSTPGRSVVTALKP"
        },
        generation_mode=GenerationMode.RDKit_ENUMERATION
    )
    assert res_s4["status"] == GenerationRunStatus.FAILED.value
    assert "FUNCTION_VERIFIED" in res_s4["error"]

    # 6. Stage 5: Missing or unknown weed species
    res_s5 = manager.execute_generation_run(
        target_info={
            "id": 1, "gene": "ALS", "target_family": "ALS",
            "weed_species": "Unknown", "sequence": "MVKLAARSTPGRSVVTALKP"
        },
        generation_mode=GenerationMode.RDKit_ENUMERATION
    )
    assert res_s5["status"] == GenerationRunStatus.FAILED.value
    assert "WEED_SPECIES_VERIFIED" in res_s5["error"]

    # 7. Stage 6: Missing or short peptide sequence (< 20 amino acids)
    res_s6 = manager.execute_generation_run(
        target_info={
            "id": 1, "gene": "ALS", "target_family": "ALS",
            "weed_species": "Amaranthus palmeri",
            "sequence": "MVKLA",  # Only 5 amino acids, rejected
            "pockets_json": [{"center": [1.0, 2.0, 3.0]}]
        },
        generation_mode=GenerationMode.RDKit_ENUMERATION
    )
    assert res_s6["status"] == GenerationRunStatus.FAILED.value
    assert "PROTEIN_VALIDATED" in res_s6["error"]

    # 8. Stage 7: Missing 3D pocket coordinates
    res_s7 = manager.execute_generation_run(
        target_info={
            "id": 1, "gene": "ALS", "target_family": "ALS",
            "weed_species": "Amaranthus palmeri",
            "sequence": "MVKLAARSTPGRSVVTALKPALSD"
        },
        generation_mode=GenerationMode.RDKit_ENUMERATION
    )
    assert res_s7["status"] == GenerationRunStatus.FAILED.value
    assert "STRUCTURE_POCKET_VALIDATED" in res_s7["error"]

    # 9. Complete valid target satisfies all 7 prerequisite gates
    valid_target = {
        "id": 101,
        "target_id": 101,
        "gene": "ALS",
        "name": "Acetohydroxyacid synthase",
        "target_family": "ALS",
        "weed_species": "Amaranthus palmeri",
        "uniprot_id": "A0A890DLI3",
        "gene_verified": True,
        "function_verified": True,
        "essentiality_evidence": "Branched-chain amino acid pathway",
        "weed_sequence": "MVKLAARSTPGRSVVTALKPALSDQ",
        "pockets_json": [{"center": [12.0, 15.0, 18.0], "residues": ["SER", "ASP", "LYS", "TYR", "VAL"]}]
    }
    res_valid = manager.execute_generation_run(
        target_info=valid_target,
        generation_mode=GenerationMode.RDKit_ENUMERATION,
        requested_count=5,
        random_seed=42
    )
    assert res_valid["status"] == GenerationRunStatus.COMPLETED.value
    assert res_valid["valid_count"] > 0
    # Structure-based pocket complementarity must be evaluated
    mol_1 = res_valid["molecules"][0]
    assert mol_1.pocket_complementarity is not None
    assert 0.0 <= mol_1.pocket_complementarity.pocket_fit_score <= 1.0
    assert mol_1.pocket_complementarity.shape_complementarity >= 0.0


def test_top_n_candidate_limit_enforcement_up_to_500():
    """Requested candidate counts exceeding safe thresholds must be clamped to HARD_MAX_CANDIDATES (500)."""
    manager = MolecularGenerationManager()
    target_info = {
        "id": 1,
        "gene": "ALS",
        "target_family": "ALS",
        "weed_species": "Amaranthus palmeri",
        "weed_sequence": "MVKLAARSTPGRSVVTALKPALSDQ",
        "pockets_json": [{"center": [12.0, 15.0, 18.0]}]
    }

    res = manager.execute_generation_run(
        target_info=target_info,
        generation_mode=GenerationMode.RDKit_ENUMERATION,
        requested_count=1000,  # Exceeds max 500
        random_seed=42
    )
    assert res["status"] == GenerationRunStatus.COMPLETED.value
    assert res["requested_count"] == 500  # Clamped to 500


def test_structure_based_pocket_pharmacophore_analysis():
    """PocketPharmacophoreAnalyzer extracts pocket volume, residue requirements, and computes ligand shape fit."""
    from app.engines.molecular_generation.pocket_aware_design import PocketPharmacophoreAnalyzer
    from rdkit import Chem

    pocket_dict = {
        "center": [10.0, 20.0, 30.0],
        "score": 0.85,
        "residues": ["ASP", "LYS", "PHE", "ARG", "SER", "VAL", "LEU", "TYR"]
    }
    features = PocketPharmacophoreAnalyzer.extract_pocket_features(pocket_dict)
    assert features["pocket_volume_angstrom3"] > 300.0
    assert features["residue_counts"]["acidic"] == 1  # ASP
    assert features["residue_counts"]["basic"] == 2   # LYS, ARG
    assert features["residue_counts"]["aromatic"] == 2  # PHE, TYR
    assert features["pharmacophore_requirements"]["recommended_hba_min"] >= 2

    # Evaluate a real drug-like molecule against this pocket
    test_mol = Chem.MolFromSmiles("Cc1nc(nc(n1)Cl)NC(=O)NS(=O)(=O)c2ccccc2Cl")  # Chlorsulfuron
    eval_res = PocketPharmacophoreAnalyzer.evaluate_molecule_pocket_fit(test_mol, features)
    assert 0.0 <= eval_res["pocket_fit_score"] <= 1.0
    assert eval_res["is_pocket_compatible"] is True
    assert eval_res["shape_complementarity"] > 0.4
    assert len(eval_res["satisfied_interactions"]) > 0


def test_chembl_bioactivity_retrieval_and_provenance_labels():
    """Database retrieval distinguishes live REST vs local benchmark with external_verification_status."""
    gen = DatabaseRetrievalGenerator()
    target_info = {
        "gene": "ALS",
        "target_family": "ALS",
        "weed_species": "Amaranthus palmeri",
        "weed_sequence": "MVKLAARSTPGRSVVTALKPALSDQ",
        "pocket_center": [1.0, 2.0, 3.0]
    }
    res = gen.generate(target_info=target_info, parameters={"prefer_live_api": False}, max_candidates=5)
    assert res["status"] == "COMPLETED"
    assert len(res["molecules"]) > 0
    # Benchmark fallback molecules must be clearly stamped
    first_mol = res["molecules"][0]
    assert first_mol["external_verification_status"] == "LOCAL_REFERENCE_ONLY"
    assert first_mol["retrieval_method"] == "LOCAL_CURATED_BENCHMARK"


# ===========================================================================
# 10. Scientific Provenance Tracker Audit Tests
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
        random_seed=42,
        query_endpoint="local",
        response_hash="abc123hash",
        retrieval_method="ENUMERATION"
    )
    assert prov.target_id == 1
    assert prov.target_family == "ALS"
    assert prov.random_seed == 42
    assert prov.query_endpoint == "local"
    assert prov.response_hash == "abc123hash"
    assert prov.provenance_hash is not None
    assert len(prov.provenance_hash) == 64


# ===========================================================================
# 11. API Endpoints & Firebase Project Isolation Tests
# ===========================================================================

def test_molecular_generation_api_crud_and_execution_lifecycle(client, db_session):
    """
    End-to-end integration test for molecular generation API:
    Create Run -> List Runs -> Execute Run -> Verify Generated Molecules & Provenance -> Query Detail.
    """
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
        weed_sequence="MVKLAARSTPGRSVVTALKPALSDQ",
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

    attacker_headers = {"Authorization": "Bearer mock_token"}
    with patch("app.core.firebase.verify_firebase_token", return_value={"uid": "unauthorized_attacker", "email": "attacker@example.com"}):
        res_create = client.post(
            f"/api/v1/projects/{project.id}/molecular-generation/runs",
            json={"target_id": 1, "generation_mode": "RDKit_ENUMERATION"},
            headers=attacker_headers
        )
        assert res_create.status_code == 403
        assert "Forbidden" in res_create.json()["detail"]


# ===========================================================================
# 12. Discovery Pipeline Stage 3 Molecular Generation Integration Tests
# ===========================================================================

def test_discovery_pipeline_stage_3_executes_target_conditioned_generation(db_session):
    """
    DiscoveryPipelineRunner Stage 3 must dynamically execute target-conditioned molecular
    generation on validated target with pocket, and assemble the candidates into ChemicalLibrary.
    """
    project = Project(
        name="Pipeline Auto-Gen Test",
        owner_uid="user_pipeline",
        weed_species="Palmer Amaranth",
        crop_species="Soybean",
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
        weed_sequence="MVKLAARSTPGRSVVTALKP",
        is_primary_selected=True,
        pockets_json=[{"center": [10.5, 20.2, 30.8]}]
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)

    runner = DiscoveryPipelineRunner(db_session)
    runner.initialize_project_pipeline(project.id)

    # Run Stage 3
    stage_3_res = runner.run_stage(project.id, 3)
    assert stage_3_res["status"] == "completed"

    # Verify a MolecularGenerationRun was created and completed
    run = db_session.query(MolecularGenerationRun).filter_by(project_id=project.id, target_id=target.id).first()
    assert run is not None
    assert run.status == "COMPLETED"
    assert run.valid_count > 0

    # Verify GeneratedMolecule records exist and were added to ChemicalLibrary
    gen_mols = db_session.query(GeneratedMolecule).filter_by(project_id=project.id, run_id=run.id).all()
    assert len(gen_mols) > 0

    lib = db_session.query(ChemicalLibrary).filter_by(id=stage_3_res["results"]["library_id"]).first()
    assert lib is not None
    assert lib.compound_count > 0

    # Verify compounds in library contain generated molecules
    comps = db_session.query(Compound).filter_by(library_id=lib.id).all()
    comp_codes = [c.compound_code for c in comps]
    assert any(gm.compound_code in comp_codes for gm in gen_mols)
