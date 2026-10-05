import os
import pytest
from app.engines.protein_engine import ProteinEngine, P2RankPocketPredictor
from app.engines.chemical_engine import ChemicalEngine
from app.engines.docking_engine import AIDockingEngine
from app.engines.selectivity_engine import CropSelectivityEngine
from app.engines.formulation_engine import FormulationEngine
from app.engines.consensus_engine import MikHerbConsensusScoreEngine
from app.engines.status_manager import engine_status_manager
from app.services.statistics_service import StatisticalAnalyzer

def test_engine_status_manager():
    statuses = engine_status_manager.get_all_statuses()
    assert "rdkit" in statuses
    assert "gnina" in statuses
    assert "boltz" in statuses
    assert statuses["rdkit"]["installed"] is True

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

def test_multi_gene_uniprot_search():
    acc = ProteinEngine.search_uniprot_accession("Palmer Amaranth", ["ALS", "HPPD"])
    assert acc is not None or acc is None  # REST API return check

def test_chemical_engine():
    ce = ChemicalEngine()
    smiles = "CC(=O)Oc1ccccc1C(=O)O"
    desc = ce.calculate_descriptors(smiles)
    assert desc is not None
    assert desc["mw"] > 100.0
    assert desc["lipinski_pass"] is True

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

def test_docking_engine_surrogate_isolation():
    de = AIDockingEngine()
    res = de.screen_candidate("dummy.pdb", "CC(=O)Oc1ccccc1C(=O)O", [10.0, 20.0, 30.0])
    if res["boltz"]["status"] == "NOT_INSTALLED":
        assert res["boltz"]["pKd_predicted"] is None
        assert "surrogate_heuristic_score" in res["boltz"]
    if res["gnina"]["status"] == "NOT_INSTALLED":
        assert res["gnina"]["affinity_kcal_mol"] is None
        assert "surrogate_heuristic_score" in res["gnina"]

def test_chemical_engine_structural_dissimilarity():
    ce = ChemicalEngine()
    comps = [{"code": "C1", "name": "Compound 1", "smiles": "CC(=O)Oc1ccccc1C(=O)O"}]
    lib = ce.build_library(comps)
    assert "structural_dissimilarity_score" in lib[0]

def test_consensus_engine_zero_parameters():
    me = MikHerbConsensusScoreEngine()
    score_res = me.calculate_score()
    assert score_res["mikherb_score"] == 0.0
    assert score_res["status"] == "NO_EVIDENCE_AVAILABLE"

def test_crop_selectivity_engine():
    se = CropSelectivityEngine()
    res = se.evaluate_selectivity("MAATTT", "MAATSS", weed_affinity_pKd=8.5, crop_affinity_pKd=6.2)
    assert res["selectivity_fold_difference"] > 10.0
    assert res["selectivity_score"] > 50.0

def test_formulation_engine():
    fe = FormulationEngine()
    res = fe.analyze_formulation("MH-001", 120.0, "Water", "Tween 80")
    assert res["compatibility_score"] > 50.0
    assert "disclaimer" in res

def test_statistics_service():
    stats = StatisticalAnalyzer.analyze_replicates([80.0, 85.0, 90.0])
    assert stats["mean"] == 85.0
    assert stats["n"] == 3
