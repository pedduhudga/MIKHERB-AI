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
from app.engines.docking_engine import AIDockingEngine, GNINAAdapter, Boltz2Adapter
from app.engines.selectivity_engine import CropSelectivityEngine
from app.engines.formulation_engine import FormulationEngine
from app.engines.consensus_engine import MikHerbConsensusScoreEngine
from app.engines.target_discovery_engine import MultiTargetDiscoveryEngine, TARGET_CATALOGUE
from app.engines.base import BaseScientificEngine
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


def test_gnina_native_execution_and_sdf_parser(tmp_path):
    """
    Mock GNINA executable to verify that:
    1. GNINA receives explicit pocket bounding box (--center_x, --center_y, --center_z, --size_x, --size_y, --size_z)
    2. GNINA does NOT use --autobox_ligand
    3. Output SDF is parsed correctly for minimizedAffinity and CNNscore
    4. Status is COMPLETED and metrics are returned as real numbers
    """
    adapter = GNINAAdapter()
    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  N   MET A   1      10.000  20.000  30.000  1.00 90.00           N\n")

    executed_cmds = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        executed_cmds.append(cmd)
        out_sdf_path = cmd[cmd.index("-o") + 1]
        sample_sdf = """
  Mrv2000 05102600002D 1   1.00000     0.00000     0
 10 10  0     0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
M  END
> <minimizedAffinity>
-8.74

> <CNNscore>
0.892

> <CNNaffinity>
7.15

$$$$
"""
        with open(out_sdf_path, "w") as sf:
            sf.write(sample_sdf)
        return MagicMock(returncode=0, stdout="GNINA run complete", stderr="")

    with patch("shutil.which", return_value="/usr/local/bin/gnina"), \
         patch("app.engines.docking_engine.subprocess.run", side_effect=mock_subprocess_run):

        res = adapter.dock(
            protein_pdb_path=dummy_pdb,
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            pocket_center=[14.25, -5.60, 28.10],
            box_size=[22.0, 20.0, 24.0]
        )

        assert len(executed_cmds) == 1
        cmd = executed_cmds[0]
        # Assert box coordinates passed directly
        assert "--center_x" in cmd
        assert cmd[cmd.index("--center_x") + 1] == "14.25"
        assert "--center_y" in cmd
        assert cmd[cmd.index("--center_y") + 1] == "-5.6"
        assert "--center_z" in cmd
        assert cmd[cmd.index("--center_z") + 1] == "28.1"
        assert "--size_x" in cmd
        assert cmd[cmd.index("--size_x") + 1] == "22.0"
        assert "--size_y" in cmd
        assert cmd[cmd.index("--size_y") + 1] == "20.0"
        assert "--size_z" in cmd
        assert cmd[cmd.index("--size_z") + 1] == "24.0"
        # Assert autobox_ligand is NOT used
        assert "--autobox_ligand" not in cmd

        # Assert scientific parsing
        assert res["status"] == "COMPLETED"
        assert res["affinity_kcal_mol"] == -8.74
        assert res["cnn_score"] == 0.892
        assert res["pose_confidence"] == "HIGH"
        assert res["execution_mode"] == "NATIVE_BINARY"
        assert res["docking_box"]["center"] == [14.25, -5.6, 28.1]


def test_gnina_native_malformed_sdf_fails_cleanly(tmp_path):
    """When GNINA finishes with returncode 0 but SDF lacks metrics, return FAILED_OUTPUT_PARSE."""
    adapter = GNINAAdapter()
    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  N   MET A   1      10.000  20.000  30.000  1.00 90.00           N\n")

    def mock_subprocess_run(cmd, *args, **kwargs):
        out_sdf_path = cmd[cmd.index("-o") + 1]
        with open(out_sdf_path, "w") as sf:
            sf.write("$$$$\n")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("shutil.which", return_value="/usr/local/bin/gnina"), \
         patch("app.engines.docking_engine.subprocess.run", side_effect=mock_subprocess_run):

        res = adapter.dock(dummy_pdb, "CC(=O)Oc1ccccc1C(=O)O", [10.0, 20.0, 30.0])
        assert res["status"] == "FAILED_OUTPUT_PARSE"
        assert res["affinity_kcal_mol"] is None
        assert res["cnn_score"] is None


def test_gnina_native_execution_failure(tmp_path):
    """When GNINA returns non-zero exit code, return FAILED_EXECUTION and all None numbers."""
    adapter = GNINAAdapter()
    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  N   MET A   1      10.000  20.000  30.000  1.00 90.00           N\n")

    def mock_subprocess_run(cmd, *args, **kwargs):
        return MagicMock(returncode=139, stdout="", stderr="Segmentation fault (core dumped)")

    with patch("shutil.which", return_value="/usr/local/bin/gnina"), \
         patch("app.engines.docking_engine.subprocess.run", side_effect=mock_subprocess_run):

        res = adapter.dock(dummy_pdb, "CC(=O)Oc1ccccc1C(=O)O", [10.0, 20.0, 30.0])
        assert res["status"] == "FAILED_EXECUTION"
        assert res["affinity_kcal_mol"] is None
        assert res["cnn_score"] is None
        assert "Segmentation fault" in res["error"]


def test_boltz2_native_execution_and_json_parser(tmp_path):
    """
    Mock Boltz-2 CLI to verify that:
    1. Input YAML file is correctly created with sequences and binder properties
    2. Output JSON confidence and affinity metrics are parsed
    3. Status is COMPLETED and real predicted pKd / confidence are returned
    """
    adapter = Boltz2Adapter()
    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  20.000  30.000  1.00 90.00           C\n")

    executed_cmds = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        executed_cmds.append(cmd)
        out_dir = cmd[cmd.index("--out_dir") + 1]
        preds_dir = os.path.join(out_dir, "predictions", "test_complex")
        os.makedirs(preds_dir, exist_ok=True)

        conf_file = os.path.join(preds_dir, "confidence_model_0.json")
        with open(conf_file, "w") as jf:
            import json
            json.dump({"complex_plddt": 93.4, "confidence_score": 0.92}, jf)

        aff_file = os.path.join(preds_dir, "affinity_model_0.json")
        with open(aff_file, "w") as jf:
            import json
            json.dump({"affinity_pred_value": -2.5}, jf)

        return MagicMock(returncode=0, stdout="Boltz run completed", stderr="")

    with patch("shutil.which", return_value="/usr/local/bin/boltz"), \
         patch("app.engines.docking_engine.subprocess.run", side_effect=mock_subprocess_run):

        res = adapter.predict_complex(
            dummy_pdb,
            "CC(=O)Oc1ccccc1C(=O)O",
            pocket_center=[10.0, 20.0, 30.0],
            protein_sequence="MVKLA"
        )

        assert len(executed_cmds) == 1
        cmd = executed_cmds[0]
        assert cmd[1] == "predict"
        yaml_path = cmd[2]
        assert os.path.exists(yaml_path)
        with open(yaml_path, "r") as yf:
            content = yf.read()
            assert "sequence: \"MVKLA\"" in content
            assert "smiles: \"CC(=O)Oc1ccccc1C(=O)O\"" in content

        assert res["status"] == "COMPLETED"
        assert res["complex_confidence_pLDDT"] == 93.4
        assert res["pKd_predicted"] == 8.5
        assert res["estimated_affinity_nM"] == round(10 ** (9 - 8.5), 1)
        assert res["execution_mode"] == "NATIVE_BINARY"


def test_boltz2_native_malformed_output_fails_cleanly(tmp_path):
    """When Boltz-2 returns code 0 but prediction JSON is missing or empty, return FAILED_OUTPUT_PARSE."""
    adapter = Boltz2Adapter()
    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  20.000  30.000  1.00 90.00           C\n")

    def mock_subprocess_run(cmd, *args, **kwargs):
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("shutil.which", return_value="/usr/local/bin/boltz"), \
         patch("app.engines.docking_engine.subprocess.run", side_effect=mock_subprocess_run):

        res = adapter.predict_complex(dummy_pdb, "CC(=O)Oc1ccccc1C(=O)O", [10.0, 20.0, 30.0])
        assert res["status"] == "FAILED_OUTPUT_PARSE"
        assert res["pKd_predicted"] is None
        assert res["complex_confidence_pLDDT"] is None


def test_boltz2_native_execution_failure(tmp_path):
    """When Boltz-2 binary fails, return FAILED_EXECUTION."""
    adapter = Boltz2Adapter()
    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  20.000  30.000  1.00 90.00           C\n")

    def mock_subprocess_run(cmd, *args, **kwargs):
        return MagicMock(returncode=2, stdout="", stderr="boltz: command error")

    with patch("shutil.which", return_value="/usr/local/bin/boltz"), \
         patch("app.engines.docking_engine.subprocess.run", side_effect=mock_subprocess_run):

        res = adapter.predict_complex(dummy_pdb, "CC(=O)Oc1ccccc1C(=O)O", [10.0, 20.0, 30.0])
        assert res["status"] == "FAILED_EXECUTION"
        assert res["pKd_predicted"] is None
        assert res["complex_confidence_pLDDT"] is None


def test_scientific_engine_lifecycle_tiers():
    """Verify NOT_INSTALLED -> INSTALLED -> VALIDATED -> FAILED status transitions."""
    # 1. Not installed
    with patch("shutil.which", return_value=None):
        eng = BaseScientificEngine("Test Engine", binary_name="fake_tool")
        status = eng.get_status()
        assert status["status"] == "NOT_INSTALLED"
        assert status["installed"] is False
        assert status["validated"] is False

    # 2. Installed but not yet validated
    with patch("shutil.which", return_value="/bin/fake_tool"):
        eng = BaseScientificEngine("Test Engine", binary_name="fake_tool")
        status = eng.get_status()
        assert status["status"] == "INSTALLED"
        assert status["installed"] is True
        assert status["validated"] is False

        # 3. Successful validation -> SCIENTIFICALLY_VALIDATED
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="FakeTool v2.1.0\n", stderr="")):
            v_status = eng.validate()
            assert v_status["status"] == "SCIENTIFICALLY_VALIDATED"
            assert v_status["validated"] is True
            assert v_status["version"] == "FakeTool v2.1.0"

        # 4. Failed validation -> FAILED
        with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="error: license missing")):
            f_status = eng.validate()
            assert f_status["status"] == "FAILED"
            assert f_status["validated"] is False
            assert "error: license missing" in f_status["validation_error"]


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
    assert aln["alignment_status"] == "COMPLETED"
    assert aln["sequence_identity"] is not None
    assert aln["alignment_method"] == "Biopython-Needleman-Wunsch-Global"
    assert aln["weed_coverage"] == 100.0  # All 11 residues aligned
    assert aln["crop_coverage"] == 100.0  # All 9 residues aligned
    assert aln["identity_over_aligned_positions"] == 100.0  # 9 identical matches / 9 paired non-gap residues
    assert aln["alignment_coverage"] == 100.0
    assert aln["bit_score"] is not None
    # 9 matching characters out of 11 length = 81.8%
    assert aln["sequence_identity"] == 81.8


def test_target_discovery_alignment_failure_handling():
    """Alignment failure must return status=FAILED and None values, never a silent positional fallback."""
    from app.engines.target_discovery_engine import _align_pairwise_biopython
    with patch("Bio.Align.PairwiseAligner", side_effect=RuntimeError("Biopython aligner crash")):
        aln = _align_pairwise_biopython("ABCDEFGHIJK", "ABCFGHIJK")
        assert aln["alignment_status"] == "FAILED"
        assert aln["sequence_identity"] is None
        assert aln["alignment_coverage"] is None
        assert aln["weed_coverage"] is None
        assert aln["crop_coverage"] is None
        assert aln["identity_over_aligned_positions"] is None
        assert aln["alignment_method"] is None
        assert aln["bit_score"] is None


def test_target_discovery_provenance_records_present():
    """Curated accessions must provide structured provenance metadata records with verification."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "entryType": "UniProtKB unreviewed (TrEMBL)",
        "organism": {"scientificName": "Amaranthus palmeri"},
        "genes": [{"geneName": {"value": "ALS"}}],
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Acetolactate synthase"}}}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp), \
         patch("app.engines.target_discovery_engine._check_alphafold_available", return_value=(True, 94.0)), \
         patch("app.engines.target_discovery_engine._fetch_fasta_seq", return_value="MAATVSFGKL"):

        engine = MultiTargetDiscoveryEngine(crop_species="Soybean")
        record = engine._assess_single_target("Palmer Amaranth", TARGET_CATALOGUE[0])
        prov = record.get("weed_accession_provenance")

    assert prov is not None
    assert prov["accession"] == "A0A890DLI3"
    assert prov["source"] == "UniProt"
    assert prov["source_type"] == "CURATED_MAPPING"
    assert prov["provenance_status"] in ("VERIFIED", "CURATED_UNVERIFIED")
    assert "retrieved_at" in prov
    assert "reviewed" in prov


def test_target_discovery_uniprot_accession_verification_invalid():
    """Accession verification must flag organism mismatches as INVALID and reject poisoned accessions."""
    from app.engines.target_discovery_engine import _verify_uniprot_accession
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"scientificName": "Arabidopsis thaliana", "taxonId": 3702},
        "genes": [{"geneName": {"value": "ALS"}}],
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Acetolactate synthase"}}}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp):
        v_res = _verify_uniprot_accession("P17597", "ALS", "Zea mays")
        assert v_res["status"] == "INVALID"
        assert v_res["provenance_status"] == "INVALID"
        assert v_res["organism_verified"] is False
        assert "ORGANISM_MISMATCH" in v_res["reason"]


def test_target_discovery_uniprot_accession_verification_gene_mismatch():
    """Accession verification must flag gene mismatches as INVALID even when organism and function match."""
    from app.engines.target_discovery_engine import _verify_uniprot_accession
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Correct organism + wrong gene + correct function
    mock_resp.json.return_value = {
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"scientificName": "Arabidopsis thaliana", "taxonId": 3702},
        "genes": [{"geneName": {"value": "HPPD"}}],
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Acetolactate synthase"}}}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp):
        v_res = _verify_uniprot_accession("P93836", "ALS", "Arabidopsis thaliana")
        assert v_res["status"] == "INVALID"
        assert v_res["organism_verified"] is True
        assert v_res["gene_verified"] is False
        assert v_res["function_verified"] is True
        assert "GENE_MISMATCH" in v_res["reason"]


def test_target_discovery_uniprot_accession_verification_function_mismatch():
    """Accession verification must flag functional description mismatches as INVALID even when organism and gene match."""
    from app.engines.target_discovery_engine import _verify_uniprot_accession
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Correct organism + correct gene + wrong function
    mock_resp.json.return_value = {
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"scientificName": "Arabidopsis thaliana", "taxonId": 3702},
        "genes": [{"geneName": {"value": "ALS"}}],
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Histone H3"}}}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp):
        v_res = _verify_uniprot_accession("P17597", "ALS", "Arabidopsis thaliana")
        assert v_res["status"] == "INVALID"
        assert v_res["organism_verified"] is True
        assert v_res["gene_verified"] is True
        assert v_res["function_verified"] is False
        assert "FUNCTION_MISMATCH" in v_res["reason"]


def test_target_discovery_uniprot_species_exact_isolation_palmeri_vs_tuberculatus():
    """Amaranthus palmeri must NOT match Amaranthus tuberculatus even though genus tokens overlap."""
    from app.engines.target_discovery_engine import _verify_uniprot_accession
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "entryType": "UniProtKB unreviewed",
        "organism": {"scientificName": "Amaranthus tuberculatus", "taxonId": 107609},
        "genes": [{"geneName": {"value": "ALS"}}],
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Acetolactate synthase"}}}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp):
        v_res = _verify_uniprot_accession("A0A890DLI3", "ALS", "Amaranthus palmeri")
        assert v_res["status"] == "INVALID"
        assert v_res["organism_verified"] is False
        assert "ORGANISM_MISMATCH" in v_res["reason"]


def test_target_discovery_uniprot_verification_empty_gene_fields():
    """Empty or missing gene fields must result in INVALID status and empty_gene_fields reason."""
    from app.engines.target_discovery_engine import _verify_uniprot_accession
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"scientificName": "Arabidopsis thaliana", "taxonId": 3702},
        "genes": [],
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Acetolactate synthase"}}}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp):
        v_res = _verify_uniprot_accession("P17597", "ALS", "Arabidopsis thaliana")
        assert v_res["status"] == "INVALID"
        assert v_res["gene_verified"] is False
        assert "EMPTY_GENE_FIELDS" in v_res["reason"]


def test_target_discovery_uniprot_verification_empty_function_fields():
    """Empty or missing protein description must result in INVALID status and empty_function_fields reason."""
    from app.engines.target_discovery_engine import _verify_uniprot_accession
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"scientificName": "Arabidopsis thaliana", "taxonId": 3702},
        "genes": [{"geneName": {"value": "ALS"}}],
        "proteinDescription": {}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp):
        v_res = _verify_uniprot_accession("P17597", "ALS", "Arabidopsis thaliana")
        assert v_res["status"] == "INVALID"
        assert v_res["function_verified"] is False
        assert "EMPTY_FUNCTION_FIELDS" in v_res["reason"]


def test_target_discovery_uniprot_verification_all_correct_verified():
    """When organism, gene, and function all match strictly, provenance_status must be VERIFIED."""
    from app.engines.target_discovery_engine import _verify_uniprot_accession
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"scientificName": "Arabidopsis thaliana", "taxonId": 3702},
        "genes": [{"geneName": {"value": "ALS"}, "synonyms": [{"value": "AHAS"}]}],
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Acetolactate synthase, chloroplastic"}}}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp):
        v_res = _verify_uniprot_accession("P17597", "ALS", "Arabidopsis thaliana")
        assert v_res["status"] == "VERIFIED"
        assert v_res["provenance_status"] == "VERIFIED"
        assert v_res["organism_verified"] is True
        assert v_res["gene_verified"] is True
        assert v_res["function_verified"] is True
        assert v_res["reason"] is None


def test_target_discovery_missing_plddt_never_manufactures_score():
    """Missing pLDDT must produce None for structure_score and 0 for AlphaFold evidence contribution (never 50.0 or 0.7)."""
    engine = MultiTargetDiscoveryEngine()
    # 1. Structure score must be None
    struct_score = engine._score_structure(alphafold_available=True, plddt=None)
    assert struct_score is None, "Missing pLDDT must yield None structure score, not 50.0."

    # 2. Evidence score must not fabricate 0.7 factor
    ev_score_without_plddt = engine._compute_target_evidence_score(
        has_weed_accession=True,
        has_weed_seq=True,
        alphafold_available=True,
        plddt_avg=None,
        has_crop_homolog=False,
        has_alignment=False,
        resistance_known=False,
        herbicide_classes_count=0
    )
    # Weed accession (20) + weed sequence (20) = 40.0; AlphaFold with None pLDDT contributes 0.0
    assert ev_score_without_plddt == 40.0


def test_target_discovery_species_specific_essentiality_requires_registry():
    """Species-specific essentiality must require explicit empirical registry record, not merely Amaranthus presence."""
    engine = MultiTargetDiscoveryEngine()

    # Case 1: ALS in Amaranthus palmeri has an explicit registry record -> SPECIES_SPECIFIC
    with patch("app.engines.target_discovery_engine._verify_uniprot_accession", return_value={"status": "VERIFIED", "reviewed": False}), \
         patch("app.engines.target_discovery_engine._fetch_fasta_seq", return_value="MAATVS"):
        als_record = engine._assess_single_target("Amaranthus palmeri", TARGET_CATALOGUE[0])
    assert als_record["essentiality_evidence_level"] == "SPECIES_SPECIFIC"
    assert als_record["species_specific_essentiality"] is True

    # Case 2: psbA in Amaranthus palmeri has target present, but NO species-specific essentiality record in registry
    with patch("app.engines.target_discovery_engine._verify_uniprot_accession", return_value={"status": "VERIFIED", "reviewed": False}), \
         patch("app.engines.target_discovery_engine._fetch_fasta_seq", return_value="MTIAV"):
        psba_def = next(t for t in TARGET_CATALOGUE if t["gene"] == "psbA")
        psba_record = engine._assess_single_target("Amaranthus palmeri", psba_def)
    assert psba_record["essentiality_evidence_level"] == "GENERAL_PLANT_EVIDENCE"
    assert psba_record["species_specific_essentiality"] is False


def test_target_discovery_species_specific_essentiality_stratification():
    """Must separate SPECIES_SPECIFIC from GENERAL_PLANT_EVIDENCE and PRECLINICAL_HYPOTHESIS."""
    engine = MultiTargetDiscoveryEngine()
    sp_score = engine._score_essentiality({"essentiality_status": "ESSENTIAL_KNOWN"}, has_weed_evidence=True, evidence_level="SPECIES_SPECIFIC")
    gen_score = engine._score_essentiality({"essentiality_status": "ESSENTIAL_KNOWN"}, has_weed_evidence=True, evidence_level="GENERAL_PLANT_EVIDENCE")
    preclin_score = engine._score_essentiality({"essentiality_status": "LIKELY_ESSENTIAL"}, has_weed_evidence=True, evidence_level="PRECLINICAL_HYPOTHESIS")
    unknown_score = engine._score_essentiality({"essentiality_status": "ESSENTIAL_KNOWN"}, has_weed_evidence=False, evidence_level="UNKNOWN")

    assert sp_score > gen_score > preclin_score
    assert unknown_score is None


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


def test_target_discovery_gene_alias_strict_exact_matching():
    """
    Evidence Integrity v9.1:
    Gene alias matching must follow the strict hierarchy:
      EXACT NORMALIZED ALIAS -> explicit approved variant -> otherwise INVALID
    Unregistered prefix/suffix tokens (e.g. 'alstemp', 'false_als', 'epsps_fake') must be strictly rejected.
    """
    from app.engines.target_discovery_engine import _verify_uniprot_accession

    # Case 1: Loose prefix like 'alstemp' must NOT pass ALS matching
    mock_resp_bad = MagicMock()
    mock_resp_bad.status_code = 200
    mock_resp_bad.json.return_value = {
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"scientificName": "Arabidopsis thaliana", "taxonId": 3702},
        "genes": [{"geneName": {"value": "alstemp"}}],
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Acetolactate synthase, chloroplastic"}}}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp_bad):
        res = _verify_uniprot_accession("P17597", "ALS", "Arabidopsis thaliana")
        assert res["status"] == "INVALID"
        assert res["gene_verified"] is False
        assert "GENE_MISMATCH" in res["reason"]

    # Case 2: Exact registered variant 'ahas' or 'csr1' must pass
    mock_resp_good = MagicMock()
    mock_resp_good.status_code = 200
    mock_resp_good.json.return_value = {
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"scientificName": "Arabidopsis thaliana", "taxonId": 3702},
        "genes": [{"geneName": {"value": "CSR1"}}],
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Acetolactate synthase, chloroplastic"}}}
    }
    with patch("app.engines.target_discovery_engine.requests.get", return_value=mock_resp_good):
        res_good = _verify_uniprot_accession("P17597", "ALS", "Arabidopsis thaliana")
        assert res_good["status"] == "VERIFIED"
        assert res_good["gene_verified"] is True
        assert res_good["function_verified"] is True


def test_p2rank_installed_execution_failure_state_machine(tmp_path):
    """
    Scientific Integrity: If P2Rank binary is found on PATH but execution fails,
    status must be FAILED_EXECUTION, NEVER NOT_INSTALLED.
    """
    from app.engines.protein_engine import P2RankPocketPredictor
    predictor = P2RankPocketPredictor()

    dummy_pdb = str(tmp_path / "test.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 45.00           C\n")

    with patch("shutil.which", return_value="/opt/p2rank/p2rank"), \
         patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=1, stderr="OutOfMemoryError: Java heap space")
        res = predictor.predict_pockets(dummy_pdb)
        assert len(res) == 1
        assert res[0]["status"] == "FAILED_EXECUTION"
        assert res[0]["status"] != "NOT_INSTALLED"
        assert "Java heap space" in res[0]["error"]


def test_p2rank_installed_missing_output_state_machine(tmp_path):
    """
    Scientific Integrity: If P2Rank binary executes with code 0 but CSV is missing or malformed,
    status must be FAILED_OUTPUT_PARSE, NEVER NOT_INSTALLED.
    """
    from app.engines.protein_engine import P2RankPocketPredictor
    predictor = P2RankPocketPredictor()

    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 45.00           C\n")

    with patch("shutil.which", return_value="/opt/p2rank/p2rank"), \
         patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=0, stdout="P2Rank completed successfully", stderr="")
        res = predictor.predict_pockets(dummy_pdb)
        assert len(res) == 1
        assert res[0]["status"] == "FAILED_OUTPUT_PARSE"
        assert res[0]["status"] != "NOT_INSTALLED"


def test_pdb_b_factor_integrity_not_plddt(tmp_path):
    """
    Scientific Integrity: Arbitrary PDB crystallographic B-factors must NOT be reported as pLDDT.
    Only structures identified as AlphaFold models can populate plddt_avg.
    """
    from app.engines.protein_engine import P2RankPocketPredictor
    predictor = P2RankPocketPredictor()

    # Experimental PDB (crystallographic B-factor = 32.5)
    exp_pdb = str(tmp_path / "crystal_structure_1abc.pdb")
    with open(exp_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 32.50           C\n")

    with patch("shutil.which", return_value=None):
        res = predictor.predict_pockets(exp_pdb)
        assert len(res) == 1
        assert res[0]["status"] == "NOT_INSTALLED"
        assert res[0]["is_alphafold_model"] is False
        assert res[0]["plddt_avg"] is None, "Experimental PDB must NOT set plddt_avg"
        assert res[0]["b_factor_avg"] == 32.5

    # AlphaFold PDB (B-factor encodes pLDDT = 88.0)
    af_pdb = str(tmp_path / "AF-P10324-F1-model_v4.pdb")
    with open(af_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")

    with patch("shutil.which", return_value=None):
        res_af = predictor.predict_pockets(af_pdb)
        assert len(res_af) == 1
        assert res_af[0]["is_alphafold_model"] is True
        assert res_af[0]["plddt_avg"] == 88.0
        assert res_af[0]["b_factor_avg"] is None


def test_boltz_strict_schema_rejects_generic_affinity(tmp_path):
    """
    Scientific Integrity: Boltz parser must reject generic 'affinity' keys and non-documented schema.
    """
    import json
    from app.engines.docking_engine import Boltz2Adapter
    adapter = Boltz2Adapter()

    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")

    def mock_run(cmd, *args, **kwargs):
        out_dir = cmd[cmd.index("--out_dir") + 1]
        # Write generic json with "affinity": -8.5 (NOT documented schema)
        with open(os.path.join(out_dir, "other_output.json"), "w") as f:
            json.dump({"affinity": -8.5, "score": 90.0}, f)
        return MagicMock(returncode=0)

    with patch("shutil.which", return_value="/usr/local/bin/boltz"), \
         patch("subprocess.run", side_effect=mock_run):
        res = adapter.predict_complex(dummy_pdb, "CC(=O)O", [10.0, 10.0, 10.0])
        assert res["status"] == "FAILED_OUTPUT_PARSE"
        assert res["pKd_predicted"] is None
        assert res["complex_confidence_pLDDT"] is None


def test_boltz_strict_schema_documented_units_conversion(tmp_path):
    """
    Scientific Integrity: Boltz-2 documented schema output must convert affinity_pred_value (log10 µM)
    strictly via pKd = 6.0 - affinity_pred_value.
    """
    import json
    from app.engines.docking_engine import Boltz2Adapter
    adapter = Boltz2Adapter()

    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")

    def mock_run(cmd, *args, **kwargs):
        out_dir = cmd[cmd.index("--out_dir") + 1]
        with open(os.path.join(out_dir, "confidence_model_0.json"), "w") as f:
            json.dump({"complex_plddt": 91.5, "confidence_score": 0.89}, f)
        with open(os.path.join(out_dir, "affinity_model_0.json"), "w") as f:
            json.dump({"affinity_pred_value": -2.5, "affinity_probability_binary": 0.95}, f)
        return MagicMock(returncode=0)

    with patch("shutil.which", return_value="/usr/local/bin/boltz"), \
         patch("subprocess.run", side_effect=mock_run):
        res = adapter.predict_complex(dummy_pdb, "CC(=O)O", [10.0, 10.0, 10.0])
        assert res["status"] == "COMPLETED"
        assert res["pIC50_predicted"] == 8.5  # 6.0 - (-2.5) = 8.5
        assert res["boltz_pIC50_predicted"] == 8.5
        assert res["pKd_predicted"] == 8.5
        assert res["complex_confidence_pLDDT"] == 91.5
        assert res["affinity_metric"] in ("log10_uM_IC50", "log_ic50_uM")
        assert res["affinity_raw_log_ic50_uM"] == -2.5
        assert res["affinity_probability_binary"] == 0.95


def test_engine_validation_tiers_probe_vs_scientific():
    """
    Engine Lifecycle: Test distinct tiers PROBE_VALIDATED vs SCIENTIFICALLY_VALIDATED.
    """
    from app.engines.base import BaseScientificEngine

    # Dummy engine with custom probe and scientific validator
    engine = BaseScientificEngine(
        name="Test Simulation Engine",
        binary_name="dummy_tool",
        validation_args=["--version"],
        scientific_validator=lambda: True
    )

    with patch("shutil.which", return_value="/usr/bin/dummy_tool"), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="dummy_tool v1.2.3")):
        # Probe validation: verifies executable responds to probe
        probe_res = engine.probe_validate()
        assert probe_res["status"] == "PROBE_VALIDATED"
        assert probe_res["is_installed"] is True
        assert probe_res["is_probe_validated"] is True

        # Scientific validation: executes scientific workflow test
        sci_res = engine.scientific_validate()
        assert sci_res["status"] == "SCIENTIFICALLY_VALIDATED"
        assert sci_res["is_scientifically_validated"] is True


# ===========================================================================
# SCIENTIFIC INTEGRITY PASS REGRESSION TESTS
# ===========================================================================

def test_p2rank_csv_exact_xyz_coordinates(tmp_path):
    """
    Scientific Integrity: P2Rank CSV parser must parse by COLUMN NAME and correctly map:
    center_x -> X, center_y -> Y, center_z -> Z.
    Must NOT confuse probability with X.
    """
    from app.engines.protein_engine import P2RankAdapter
    adapter = P2RankAdapter()

    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")

    def mock_p2rank(cmd, *args, **kwargs):
        out_dir = cmd[cmd.index("-o") + 1]
        csv_path = os.path.join(out_dir, f"{os.path.basename(dummy_pdb)}_predictions.csv")
        with open(csv_path, "w") as f:
            f.write("name,rank,score,probability,center_x,center_y,center_z\n")
            f.write("pocket1,1,12.5,0.85,10.0,20.0,30.0\n")
        return MagicMock(returncode=0, stdout="P2Rank completed", stderr="")

    with patch("shutil.which", return_value="/usr/local/bin/p2rank"), \
         patch("subprocess.run", side_effect=mock_p2rank):
        pockets = adapter.predict_pockets(dummy_pdb)
        assert len(pockets) == 1
        pkt = pockets[0]
        assert pkt["status"] == "COMPLETED"
        # Exact coordinate mapping: center must be [10.0, 20.0, 30.0]
        assert pkt["center"] == [10.0, 20.0, 30.0], f"Center was incorrectly parsed as {pkt['center']}"
        assert pkt["score"] == 12.5
        assert pkt["druggability_score"] == 0.85
        assert pkt["probability"] == 0.85


def test_p2rank_malformed_csv_returns_failed_output_parse(tmp_path):
    """
    Scientific Integrity: Malformed P2Rank CSV missing center coordinates or corrupt rows
    must return FAILED_OUTPUT_PARSE instead of falling back to fake coordinates.
    """
    from app.engines.protein_engine import P2RankAdapter
    adapter = P2RankAdapter()

    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")

    def mock_malformed_csv(cmd, *args, **kwargs):
        out_dir = cmd[cmd.index("-o") + 1]
        csv_path = os.path.join(out_dir, f"{os.path.basename(dummy_pdb)}_predictions.csv")
        with open(csv_path, "w") as f:
            # Missing center_z column!
            f.write("name,rank,score,probability,center_x,center_y\n")
            f.write("pocket1,1,12.5,0.85,10.0,20.0\n")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("shutil.which", return_value="/usr/local/bin/p2rank"), \
         patch("subprocess.run", side_effect=mock_malformed_csv):
        pockets = adapter.predict_pockets(dummy_pdb)
        assert len(pockets) == 1
        assert pockets[0]["status"] == "FAILED_OUTPUT_PARSE"
        assert pockets[0]["center"] is None


def test_p2rank_installed_execution_failure(tmp_path):
    """
    Scientific Integrity: When P2Rank is installed but executable fails (non-zero return code),
    must report FAILED_EXECUTION and not disguise as success or surrogate.
    """
    from app.engines.protein_engine import P2RankAdapter
    adapter = P2RankAdapter()

    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")

    with patch("shutil.which", return_value="/usr/local/bin/p2rank"), \
         patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="Java heap space out of memory")):
        pockets = adapter.predict_pockets(dummy_pdb)
        assert len(pockets) == 1
        assert pockets[0]["status"] == "FAILED_EXECUTION"
        assert "Java heap space" in pockets[0]["error"]
        assert pockets[0]["center"] is None


def test_api_unavailable_returns_failed_scientific_validation():
    """
    Scientific Integrity: External API failure (UniProt, AlphaFold, PubChem) must NEVER
    return True / SCIENTIFICALLY_VALIDATED. Network failure MUST produce FAILED.
    """
    import requests
    from app.engines.base import BaseScientificEngine
    from app.engines.status_manager import _validate_uniprot, _validate_alphafold, _validate_pubchem

    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Network down")):
        # Direct function calls must return False
        assert _validate_uniprot() is False
        assert _validate_alphafold() is False
        assert _validate_pubchem() is False

        # In BaseScientificEngine lifecycle, must result in FAILED status
        u_eng = BaseScientificEngine("UniProt REST API", is_api=True, scientific_validator=_validate_uniprot)
        res = u_eng.scientific_validate()
        assert res["status"] == "FAILED"
        assert res["scientifically_validated"] is False
        assert res["validated"] is False
        assert "failed or service unreachable" in res["validation_error"]


def test_validation_success_followed_by_failure_resets_state():
    """
    Engine Lifecycle: A previous successful validation followed by a failed validation
    MUST completely reset previous state and report status = FAILED.
    """
    from app.engines.base import BaseScientificEngine

    validator_state = {"should_succeed": True}

    def dynamic_validator():
        return validator_state["should_succeed"]

    eng = BaseScientificEngine(
        name="Dynamic Test Engine",
        binary_name="dynamic_bin",
        validation_args=["--version"],
        scientific_validator=dynamic_validator
    )

    with patch("shutil.which", return_value="/usr/bin/dynamic_bin"), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="dynamic_bin v1.0")):
        # 1. First run: succeeds
        first_status = eng.scientific_validate()
        assert first_status["status"] == "SCIENTIFICALLY_VALIDATED"
        assert first_status["validated"] is True
        assert first_status["scientifically_validated"] is True

        # 2. Second run: scientific validation fails
        validator_state["should_succeed"] = False
        second_status = eng.scientific_validate()
        assert second_status["status"] == "FAILED"
        assert second_status["validated"] is False
        assert second_status["scientifically_validated"] is False
        assert second_status["probe_validated"] is False
        assert second_status["validation_error"] is not None


def test_boltz_pic50_naming_and_conversion(tmp_path):
    """
    Scientific Integrity: Boltz-2 documented affinity_pred_value (log10 µM) must be stored
    as affinity_raw_log_ic50_uM and converted to pIC50_predicted = 6.0 - affinity_pred_value.
    Must clearly label predicted IC50 equivalent, not measured affinity.
    """
    import json
    from app.engines.docking_engine import Boltz2Adapter
    adapter = Boltz2Adapter()

    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")

    def mock_run(cmd, *args, **kwargs):
        out_dir = cmd[cmd.index("--out_dir") + 1]
        with open(os.path.join(out_dir, "confidence_model_0.json"), "w") as f:
            json.dump({"complex_plddt": 0.88, "confidence_score": 0.85}, f)
        with open(os.path.join(out_dir, "affinity_model_0.json"), "w") as f:
            json.dump({"affinity_pred_value": -1.5, "affinity_probability_binary": 0.92}, f)
        return MagicMock(returncode=0)

    with patch("shutil.which", return_value="/usr/local/bin/boltz"), \
         patch("subprocess.run", side_effect=mock_run):
        res = adapter.predict_complex(dummy_pdb, "CCO", [10.0, 10.0, 10.0], protein_sequence="MKVLA")
        assert res["status"] == "COMPLETED"
        assert res["affinity_raw_log_ic50_uM"] == -1.5
        assert res["affinity_metric"] == "log10_uM_IC50"
        # 6.0 - (-1.5) = 7.5
        assert res["pIC50_predicted"] == 7.5
        assert res["boltz_pIC50_predicted"] == 7.5
        assert res["affinity_probability_binary"] == 0.92
        # IC50 equivalent in nM: 10^(9 - 7.5) = 10^1.5 = 31.6 nM
        assert res["predicted_ic50_equivalent_nM"] == 31.6


def test_boltz_native_confidence_scale_0_to_1(tmp_path):
    """
    Scientific Integrity: Boltz confidence metrics must be preserved in native 0-1 scale.
    Must not mutate 0.91 -> 91 in backend storage metrics.
    """
    import json
    from app.engines.docking_engine import Boltz2Adapter
    adapter = Boltz2Adapter()

    dummy_pdb = str(tmp_path / "target.pdb")
    with open(dummy_pdb, "w") as f:
        f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")

    def mock_run(cmd, *args, **kwargs):
        out_dir = cmd[cmd.index("--out_dir") + 1]
        with open(os.path.join(out_dir, "confidence_model_0.json"), "w") as f:
            json.dump({"complex_plddt": 0.925, "confidence_score": 0.91}, f)
        with open(os.path.join(out_dir, "affinity_model_0.json"), "w") as f:
            json.dump({"affinity_pred_value": -2.0, "affinity_probability_binary": 0.96}, f)
        return MagicMock(returncode=0)

    with patch("shutil.which", return_value="/usr/local/bin/boltz"), \
         patch("subprocess.run", side_effect=mock_run):
        res = adapter.predict_complex(dummy_pdb, "CCO", [10.0, 10.0, 10.0], protein_sequence="MKVLA")
        assert res["status"] == "COMPLETED"
        assert res["boltz_confidence_score"] == 0.91
        assert res["boltz_complex_plddt"] == 0.925
        assert res["confidence_scale"] == "0_to_1"
        assert res["complex_confidence_pLDDT"] == 92.5  # presentation percentage


def test_boltz_missing_protein_sequence_returns_failed_input(tmp_path):
    """
    Scientific Integrity: Missing protein sequence must return FAILED_INPUT
    and NEVER inject fake sequence 'M'.
    """
    from app.engines.docking_engine import Boltz2Adapter
    adapter = Boltz2Adapter()

    # Empty PDB without sequence
    empty_pdb = str(tmp_path / "empty.pdb")
    with open(empty_pdb, "w") as f:
        f.write("REMARK   Empty test structure\n")

    with patch("shutil.which", return_value="/usr/local/bin/boltz"):
        res = adapter.predict_complex(empty_pdb, "CCO", [10.0, 10.0, 10.0], protein_sequence=None)
        assert res["status"] == "FAILED_INPUT"
        assert "PROTEIN_SEQUENCE_MISSING" in res["error"]
        assert res["pIC50_predicted"] is None
        assert res["pKd_predicted"] is None
        assert res["boltz_complex_plddt"] is None



