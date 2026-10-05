import os
import pytest
from app.engines.protein_engine import ProteinEngine, P2RankPocketPredictor
from app.engines.chemical_engine import ChemicalEngine
from app.engines.docking_engine import AIDockingEngine, GNINAAdapter, Boltz2Adapter
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
    pdb_file = "./data/structures/AF-P10324-F1-model_v6.pdb"
    if not os.path.exists(pdb_file):
        pe = ProteinEngine()
        pe.fetch_alphafold_structure("P10324")

    pockets = P2RankPocketPredictor.predict_pockets_from_pdb(pdb_file)
    assert len(pockets) >= 1
    assert "center" in pockets[0]
    assert "source" in pockets[0]

def test_chemical_engine():
    ce = ChemicalEngine()
    smiles = "CC(=O)Oc1ccccc1C(=O)O"
    desc = ce.calculate_descriptors(smiles)
    assert desc is not None
    assert desc["mw"] > 100.0
    assert desc["lipinski_pass"] is True

def test_docking_engine_status_awareness():
    de = AIDockingEngine()
    pdb_file = "./data/structures/AF-P10324-F1-model_v6.pdb"
    if not os.path.exists(pdb_file):
        ProteinEngine().fetch_alphafold_structure("P10324")

    res = de.screen_candidate(pdb_file, "CC(=O)Oc1ccccc1C(=O)O", [-0.988, -1.353, 2.374])
    assert res["boltz"]["status"] in ["COMPLETED", "NOT_INSTALLED", "FAILED_EXECUTION"]
    assert res["gnina"]["status"] in ["COMPLETED", "NOT_INSTALLED", "FAILED_EXECUTION"]
    assert "pose_agreement" in res

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
