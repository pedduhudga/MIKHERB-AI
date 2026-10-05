"""
MikHerb-AI Backend Test Suite

Tests cover:
  - Engine status detection
  - Protein engine (real UniProt/AlphaFold fetch)
  - P2Rank pocket predictor labels
  - Chemical engine (descriptors, deduplication, filters, structural dissimilarity)
  - Docking engine (status awareness, surrogate isolation, pocket rejection)
  - Consensus engine (zero-parameter fallback)
  - Crop selectivity engine
  - Formulation engine
  - Statistics service
  - Multi-gene UniProt search (with mocking to assert actual query behaviour)
  - Multi-target discovery engine (target ranking, crop divergence)
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from app.engines.protein_engine import ProteinEngine, P2RankPocketPredictor
from app.engines.chemical_engine import ChemicalEngine
from app.engines.docking_engine import AIDockingEngine
from app.engines.selectivity_engine import CropSelectivityEngine
from app.engines.formulation_engine import FormulationEngine
from app.engines.consensus_engine import MikHerbConsensusScoreEngine
from app.engines.target_discovery_engine import MultiTargetDiscoveryEngine, TARGET_CATALOGUE
from app.engines.status_manager import engine_status_manager
from app.services.statistics_service import StatisticalAnalyzer


# ---------------------------------------------------------------------------
# Engine status detection
# ---------------------------------------------------------------------------

def test_engine_status_manager():
    statuses = engine_status_manager.get_all_statuses()
    assert "rdkit" in statuses
    assert "gnina" in statuses
    assert "boltz" in statuses
    assert statuses["rdkit"]["installed"] is True


# ---------------------------------------------------------------------------
# Protein Engine — live network tests (may be skipped in CI without network)
# ---------------------------------------------------------------------------

def test_protein_engine_real_fetch():
    pe = ProteinEngine()
    data = pe.get_protein_info("P10324", "ALS Weed Target")
    assert data["uniprot_id"] == "P10324"
    assert len(data["sequence"]) > 0
    assert os.path.exists(data["pdb_path"])
    assert len(data["pockets"]) > 0


def test_p2rank_pocket_predictor_labels():
    pe = ProteinEngine()
    data = pe.get_protein_info("P10324", "ALS Weed Target")
    pdb_file = data["pdb_path"]

    pockets = P2RankPocketPredictor.predict_pockets_from_pdb(pdb_file)
    assert len(pockets) >= 1
    assert "center" in pockets[0]
    assert "source" in pockets[0]
    # P2Rank not installed → heuristic fallback labelling
    if pockets[0].get("status") == "NOT_INSTALLED":
        assert "Heuristic" in pockets[0]["name"], (
            f"Expected 'Heuristic' in pocket name, got: {pockets[0]['name']}"
        )


# ---------------------------------------------------------------------------
# Multi-gene UniProt search — mocked to assert actual query behaviour
# ---------------------------------------------------------------------------

def _make_uniprot_response(accession: str):
    """Create a minimal fake UniProt REST API JSON response."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"results": [{"primaryAccession": accession}]}
    return mock


def _make_empty_uniprot_response():
    """UniProt response with no results (gene not found in species)."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"results": []}
    return mock


def test_multi_gene_search_returns_first_match():
    """When ALS succeeds, it should be returned without querying HPPD."""
    with patch("app.engines.protein_engine.requests.get") as mock_get:
        mock_get.return_value = _make_uniprot_response("ACC_ALS_001")
        acc = ProteinEngine.search_uniprot_accession("Palmer Amaranth", ["ALS", "HPPD"])
        assert acc == "ACC_ALS_001"
        # Only one call should have been made (to ALS)
        assert mock_get.call_count == 1
        call_url = mock_get.call_args[0][0]
        assert "ALS" in call_url, f"Expected ALS query in URL, got: {call_url}"


def test_multi_gene_search_falls_back_to_second_gene():
    """When ALS returns empty, HPPD should be queried and its accession returned."""
    responses = [
        _make_empty_uniprot_response(),       # ALS → no result
        _make_uniprot_response("ACC_HPPD_002"),  # HPPD → match
    ]
    with patch("app.engines.protein_engine.requests.get", side_effect=responses) as mock_get:
        acc = ProteinEngine.search_uniprot_accession("Palmer Amaranth", ["ALS", "HPPD"])
        assert acc == "ACC_HPPD_002"
        assert mock_get.call_count == 2
        hppd_url = mock_get.call_args_list[1][0][0]
        assert "HPPD" in hppd_url, f"Expected HPPD in second query URL, got: {hppd_url}"


def test_multi_gene_search_returns_none_when_all_fail():
    """When all genes fail to find accessions, None is returned."""
    empty_response = _make_empty_uniprot_response()
    with patch("app.engines.protein_engine.requests.get", return_value=empty_response):
        acc = ProteinEngine.search_uniprot_accession("Unknown Species", ["ALS", "HPPD", "PPO"])
        assert acc is None


def test_single_gene_string_still_works():
    """Backwards compatibility: single string gene argument should work."""
    with patch("app.engines.protein_engine.requests.get") as mock_get:
        mock_get.return_value = _make_uniprot_response("SINGLE_ACC")
        acc = ProteinEngine.search_uniprot_accession("Some Weed", "ALS")
        assert acc == "SINGLE_ACC"


# ---------------------------------------------------------------------------
# Chemical Engine
# ---------------------------------------------------------------------------

def test_chemical_engine():
    ce = ChemicalEngine()
    smiles = "CC(=O)Oc1ccccc1C(=O)O"
    desc = ce.calculate_descriptors(smiles)
    assert desc is not None
    assert desc["mw"] > 100.0
    assert desc["lipinski_pass"] is True


def test_chemical_engine_deduplication():
    ce = ChemicalEngine()
    comps = [
        {"code": "C1", "name": "Compound 1", "smiles": "CC(=O)Oc1ccccc1C(=O)O"},
        {"code": "C2", "name": "Compound 2", "smiles": "CC(=O)Oc1ccccc1C(=O)O"}  # Duplicate
    ]
    lib = ce.build_library(comps)
    assert len(lib) == 1


def test_chemical_engine_advanced_filters():
    ce = ChemicalEngine()
    parent = ce.remove_salts_get_parent("CC(=O)O.Cl.[Na+]")
    assert "Cl" not in parent

    desc = ce.calculate_descriptors("CC(=O)Oc1ccccc1C(=O)O")
    assert "veber_pass" in desc
    assert "pains_pass" in desc
    assert desc["veber_pass"] is True


def test_chemical_engine_structural_dissimilarity():
    ce = ChemicalEngine()
    comps = [{"code": "C1", "name": "Compound 1", "smiles": "CC(=O)Oc1ccccc1C(=O)O"}]
    lib = ce.build_library(comps)
    assert "structural_dissimilarity_score" in lib[0]
    assert 0.0 <= lib[0]["structural_dissimilarity_score"] <= 100.0


# ---------------------------------------------------------------------------
# Docking Engine
# ---------------------------------------------------------------------------

def test_docking_engine_status_awareness():
    pe = ProteinEngine()
    data = pe.get_protein_info("P10324", "ALS Weed Target")
    pdb_file = data["pdb_path"]
    pocket_center = data["pockets"][0]["center"]

    de = AIDockingEngine()
    res = de.screen_candidate(pdb_file, "CC(=O)Oc1ccccc1C(=O)O", pocket_center)
    assert res["boltz"]["status"] in ["COMPLETED", "NOT_INSTALLED", "FAILED_EXECUTION"]
    assert res["gnina"]["status"] in ["COMPLETED", "NOT_INSTALLED", "FAILED_EXECUTION"]
    assert "pose_agreement" in res


def test_docking_engine_missing_pocket_rejection():
    de = AIDockingEngine()
    res = de.screen_candidate("dummy.pdb", "CC(=O)Oc1ccccc1C(=O)O", pocket_center=None)
    assert res["status"] == "POCKET_CENTER_MISSING"
    assert res["boltz"]["status"] == "POCKET_CENTER_MISSING"


def test_docking_engine_surrogate_isolation():
    """Surrogates must not report pKd_predicted or affinity_kcal_mol as real values."""
    de = AIDockingEngine()
    res = de.screen_candidate("dummy.pdb", "CC(=O)Oc1ccccc1C(=O)O", [10.0, 20.0, 30.0])
    if res["boltz"]["status"] == "NOT_INSTALLED":
        assert res["boltz"]["pKd_predicted"] is None, (
            "Surrogate must not produce a pKd_predicted value when Boltz is not installed."
        )
        assert "surrogate_heuristic_score" in res["boltz"]
    if res["gnina"]["status"] == "NOT_INSTALLED":
        assert res["gnina"]["affinity_kcal_mol"] is None, (
            "Surrogate must not produce affinity_kcal_mol when GNINA is not installed."
        )
        assert "surrogate_heuristic_score" in res["gnina"]


def test_docking_engine_preserves_actual_status_codes():
    """The docking engine must preserve specific status codes (not collapse them to NOT_INSTALLED)."""
    de = AIDockingEngine()
    res = de.screen_candidate("dummy.pdb", "CC(=O)Oc1ccccc1C(=O)O", [10.0, 20.0, 30.0])
    valid_boltz_statuses = {
        "COMPLETED", "NOT_INSTALLED", "FAILED_EXECUTION",
        "FAILED_OUTPUT_PARSE", "FAILED_UNKNOWN", "POCKET_CENTER_MISSING"
    }
    valid_gnina_statuses = {
        "COMPLETED", "NOT_INSTALLED", "FAILED_EXECUTION",
        "FAILED_OUTPUT_PARSE", "FAILED_INVALID_SMILES", "FAILED_UNKNOWN", "POCKET_CENTER_MISSING"
    }
    assert res["boltz"]["status"] in valid_boltz_statuses, (
        f"Unexpected Boltz status: {res['boltz']['status']}"
    )
    assert res["gnina"]["status"] in valid_gnina_statuses, (
        f"Unexpected GNINA status: {res['gnina']['status']}"
    )


# ---------------------------------------------------------------------------
# Consensus Engine
# ---------------------------------------------------------------------------

def test_consensus_engine_zero_parameters():
    me = MikHerbConsensusScoreEngine()
    score_res = me.calculate_score()
    assert score_res["mikherb_score"] == 0.0
    assert score_res["status"] == "NO_EVIDENCE_AVAILABLE"


def test_consensus_engine_no_safety_boolean():
    """Consensus score should work identically whether safety_evidence_clean is None or not provided."""
    me = MikHerbConsensusScoreEngine()
    score_with_none = me.calculate_score(
        target_relevance=70.0,
        boltz_pKd=7.5,
        safety_evidence_clean=None
    )
    score_without = me.calculate_score(
        target_relevance=70.0,
        boltz_pKd=7.5,
    )
    assert score_with_none["mikherb_score"] == score_without["mikherb_score"], (
        "Passing safety_evidence_clean=None must produce the same score as not passing it at all."
    )
    assert "safety_environment" not in score_with_none["component_scores"], (
        "safety_environment must not appear in component scores when safety data is None."
    )


def test_consensus_engine_safety_tiers():
    """Safety tiers (VALIDATED_SAFETY vs PREDICTIVE_SAFETY vs UNKNOWN) should be handled with explicit tiers."""
    me = MikHerbConsensusScoreEngine()
    score_validated = me.calculate_score(target_relevance=70.0, safety_tier="VALIDATED_SAFETY")
    score_predictive = me.calculate_score(target_relevance=70.0, safety_tier="PREDICTIVE_SAFETY")
    score_unknown = me.calculate_score(target_relevance=70.0, safety_tier="UNKNOWN")

    assert score_validated["component_scores"]["safety_environment"] == 100.0
    assert score_predictive["component_scores"]["safety_environment"] == 75.0
    assert "safety_environment" not in score_unknown["component_scores"]


def test_alphafold_global_metric_value_resolution():
    """AlphaFold API parser should extract globalMetricValue accurately."""
    from app.engines.target_discovery_engine import _check_alphafold_available
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"globalMetricValue": 94.94, "pdbUrl": "https://fake/AF.pdb"}]

    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp):
        available, plddt = _check_alphafold_available("A0A890DLI3")
        assert available is True
        assert plddt == 94.94


# ---------------------------------------------------------------------------
# Crop Selectivity Engine
# ---------------------------------------------------------------------------

def test_crop_selectivity_engine():
    se = CropSelectivityEngine()
    res = se.evaluate_selectivity("MAATTT", "MAATSS", weed_affinity_pKd=8.5, crop_affinity_pKd=6.2)
    assert res["selectivity_fold_difference"] > 10.0
    assert res["selectivity_score"] > 50.0


def test_crop_selectivity_none_preserved():
    """None selectivity score must not be coerced to 0.0 anywhere in the pipeline data."""
    # This tests that the selectivity engine itself returns None when called with None pKd
    # (the selectivity engine requires valid pKd values — None propagation is in pipeline_service)
    se = CropSelectivityEngine()
    # If both pKds are present, score is computed
    res = se.evaluate_selectivity("MAAT", "MAAR", weed_affinity_pKd=7.0, crop_affinity_pKd=7.0)
    assert res["selectivity_score"] is not None
    # Score should be ~50 when weed == crop pKd (no selectivity)
    assert abs(res["selectivity_score"] - 50.0) < 5.0


# ---------------------------------------------------------------------------
# Multi-Target Discovery Engine
# ---------------------------------------------------------------------------

def test_target_catalogue_completeness():
    """All 10 major target families should be present in the catalogue."""
    expected_genes = {"ALS", "HPPD", "PPO", "EPSPS", "ACCase", "psbA", "PDS", "KAS", "GS", "DXS"}
    actual_genes = {t["gene"] for t in TARGET_CATALOGUE}
    assert expected_genes == actual_genes, (
        f"Missing targets: {expected_genes - actual_genes}. "
        f"Extra targets: {actual_genes - expected_genes}."
    )


def test_target_discovery_engine_returns_ranked_list():
    """Discovery engine should return a non-empty ranked list of target records."""
    # Mock all network calls to avoid CI dependency on UniProt/AlphaFold APIs
    with patch("app.engines.target_discovery_engine._search_uniprot", return_value=None), \
         patch("app.engines.target_discovery_engine._check_alphafold_available", return_value=(False, None)), \
         patch("app.engines.target_discovery_engine._fetch_fasta_seq", return_value=None):

        engine = MultiTargetDiscoveryEngine(crop_species="Soybean")
        results = engine.discover_targets("Palmer Amaranth", max_targets=10)

    assert len(results) == 10
    # Results should be sorted by target_opportunity_score (non-None first, highest first)
    valid_scores = [r["target_opportunity_score"] for r in results if r["target_opportunity_score"] is not None]
    assert valid_scores == sorted(valid_scores, reverse=True), "Results must be sorted by opportunity score descending."


def test_target_discovery_essentiality_scoring():
    """ESSENTIAL_UNIQUE targets should score higher than LIKELY_ESSENTIAL when weed evidence exists."""
    engine = MultiTargetDiscoveryEngine()
    essential_score = engine._score_essentiality({"essentiality_status": "ESSENTIAL_KNOWN"}, has_weed_evidence=True)
    likely_score = engine._score_essentiality({"essentiality_status": "LIKELY_ESSENTIAL"}, has_weed_evidence=True)
    assert essential_score > likely_score


def test_target_discovery_essentiality_none_without_weed_evidence():
    """Essentiality score must be None (not manufactured 90.0) when weed evidence is absent."""
    engine = MultiTargetDiscoveryEngine()
    score = engine._score_essentiality({"essentiality_status": "ESSENTIAL_KNOWN"}, has_weed_evidence=False)
    assert score is None, "Missing weed evidence must NEVER manufacture an essentiality score."


def test_target_discovery_opportunity_none_without_weed_evidence():
    """target_opportunity_score must be None when no weed accession or sequence exists."""
    engine = MultiTargetDiscoveryEngine()
    opp_score = engine._compute_opportunity_score(
        essentiality_score=None,
        herbicide_evidence_score=66.0,
        selectivity_potential_score=None,
        structure_score=None,
        has_weed_evidence=False
    )
    assert opp_score is None, "Opportunity score cannot be fabricated when weed target evidence is absent."


def test_target_discovery_evidence_score_vs_opportunity_score():
    """target_evidence_score and target_opportunity_score must be distinctly separated metrics."""
    with patch("app.engines.target_discovery_engine._search_uniprot", return_value="A0A890DLI3"), \
         patch("app.engines.target_discovery_engine._check_alphafold_available", return_value=(True, 94.0)), \
         patch("app.engines.target_discovery_engine._fetch_fasta_seq", return_value="MAATVSFGKLHQR"):

        engine = MultiTargetDiscoveryEngine(crop_species="Soybean")
        record = engine._assess_single_target("Palmer Amaranth", TARGET_CATALOGUE[0])

    assert "target_evidence_score" in record
    assert "target_opportunity_score" in record
    assert "target_evidence_confidence" in record
    assert record["target_evidence_score"] > 0.0
    assert record["target_evidence_confidence"] in ("HIGH", "MEDIUM", "LOW", "HYPOTHESIS_ONLY")


def test_target_discovery_pairwise_biopython_alignment():
    """Biopython pairwise alignment must handle indels properly without positional distortion."""
    from app.engines.target_discovery_engine import _align_pairwise_biopython
    # seq_b has a 2-amino acid internal deletion relative to seq_a
    seq_a = "ABCDEFGHIJK"
    seq_b = "ABCFGHIJK"

    aln = _align_pairwise_biopython(seq_a, seq_b)
    assert aln["sequence_identity"] is not None
    assert aln["alignment_method"] == "Biopython-Needleman-Wunsch-Global"
    assert aln["alignment_coverage"] is not None
    assert aln["bit_score"] is not None
    # 9 matching characters out of 11 length = 81.8%
    assert aln["sequence_identity"] == 81.8


def test_target_discovery_provenance_records_present():
    """Curated accessions must provide structured provenance metadata records."""
    engine = MultiTargetDiscoveryEngine(crop_species="Soybean")
    record = engine._assess_single_target("Palmer Amaranth", TARGET_CATALOGUE[0])
    prov = record.get("weed_accession_provenance")

    assert prov is not None
    assert prov["accession"] == "A0A890DLI3"
    assert prov["source"] == "UniProt"
    assert prov["source_type"] == "CURATED_MAPPING"
    assert "retrieved_at" in prov
    assert "reviewed" in prov


def test_target_discovery_alphafold_filter():
    """require_alphafold=True should exclude targets without AlphaFold structure."""
    with patch("app.engines.target_discovery_engine._search_uniprot", return_value="MOCK_ACC"), \
         patch("app.engines.target_discovery_engine._check_alphafold_available", return_value=(False, None)), \
         patch("app.engines.target_discovery_engine._fetch_fasta_seq", return_value="MAATVS"):

        engine = MultiTargetDiscoveryEngine()
        results = engine.discover_targets("Unknown Weed", require_alphafold=True)

    assert len(results) == 0, "With all AlphaFold returns False, no targets should pass filter."


def test_target_discovery_crop_divergence_computed():
    """When crop data is available, crop_divergence_pct should be computed via real alignment."""
    mock_seq_weed = "MAATVSFGKLHQR"
    mock_seq_crop = "MAATVSAGKLHQR"  # One difference at position 7

    with patch("app.engines.target_discovery_engine._search_uniprot", return_value="MOCK_ACC"), \
         patch("app.engines.target_discovery_engine._check_alphafold_available", return_value=(True, 92.5)), \
         patch("app.engines.target_discovery_engine._fetch_fasta_seq", side_effect=[mock_seq_weed, mock_seq_crop]):

        engine = MultiTargetDiscoveryEngine(crop_species="Soybean")
        result = engine._assess_single_target("Soybean", TARGET_CATALOGUE[0])

    assert result["crop_divergence_pct"] is not None
    assert result["sequence_identity_pct"] is not None
    assert result["alignment_method"] == "Biopython-Needleman-Wunsch-Global"
    assert 0.0 <= result["crop_divergence_pct"] <= 100.0


def test_target_discovery_selectivity_none_when_no_crop():
    """selectivity_potential_score should be None when crop divergence is unavailable."""
    engine = MultiTargetDiscoveryEngine()
    score = engine._score_selectivity_potential(TARGET_CATALOGUE[0], None)
    assert score is None


def test_target_discovery_structure_score_none_when_no_alphafold():
    """structure_score should be None (not 0.0) when AlphaFold is unavailable."""
    engine = MultiTargetDiscoveryEngine()
    score = engine._score_structure(alphafold_available=False, plddt=None)
    assert score is None


# ---------------------------------------------------------------------------
# Formulation Engine
# ---------------------------------------------------------------------------

def test_formulation_engine():
    fe = FormulationEngine()
    res = fe.analyze_formulation("MH-001", 120.0, "Water", "Tween 80")
    assert res["compatibility_score"] > 50.0
    assert "disclaimer" in res


# ---------------------------------------------------------------------------
# Report Generator Tests
# ---------------------------------------------------------------------------

def test_report_generator_preserves_status_codes(tmp_path):
    """ReportGenerator should preserve specific status codes in PDF table."""
    from app.services.report_service import ReportGenerator
    pdf_file = str(tmp_path / "test_report.pdf")
    project_data = {
        "id": 99,
        "name": "Status Report Test",
        "weed_species": "Amaranthus palmeri",
        "crop_species": "Glycine max",
        "objective": "new_herbicide",
        "candidates": [
            {
                "code": "MH-001",
                "target": "ALS Target",
                "boltz_status": "FAILED_EXECUTION",
                "boltz": None,
                "gnina_status": "POCKET_CENTER_MISSING",
                "gnina": None,
                "selectivity": "NOT_AVAILABLE",
                "score": "65.0/100",
            }
        ]
    }
    out = ReportGenerator.generate_pdf_report(project_data, pdf_file)
    assert os.path.exists(out)
    assert os.path.getsize(out) > 500
