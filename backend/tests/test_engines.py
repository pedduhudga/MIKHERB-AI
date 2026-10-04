import pytest
from app.engines.protein_engine import ProteinEngine
from app.engines.chemical_engine import ChemicalEngine
from app.engines.docking_engine import AIDockingEngine
from app.engines.selectivity_engine import CropSelectivityEngine
from app.engines.formulation_engine import FormulationEngine
from app.engines.consensus_engine import MikHerbConsensusScoreEngine
from app.services.statistics_service import StatisticalAnalyzer

def test_protein_engine():
    pe = ProteinEngine()
    data = pe.get_protein_info("P10324", "ALS Weed Target")
    assert data["uniprot_id"] == "P10324"
    assert len(data["pockets"]) > 0
    assert data["pLDDT_confidence"] > 80.0

def test_chemical_engine():
    ce = ChemicalEngine()
    smiles = "CC(=O)Oc1ccccc1C(=O)O"
    desc = ce.calculate_descriptors(smiles)
    assert desc is not None
    assert desc["mw"] > 100.0
    assert desc["lipinski_pass"] is True

def test_docking_engine():
    de = AIDockingEngine()
    res = de.screen_candidate("MAATTT", "CC(=O)Oc1ccccc1C(=O)O")
    assert res["boltz"]["pKd_predicted"] > 0
    assert res["gnina"]["cnn_score"] >= 0
    assert res["pose_agreement"] in ["HIGH", "MEDIUM", "LOW"]

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

def test_consensus_score_engine():
    me = MikHerbConsensusScoreEngine()
    score_res = me.calculate_score()
    assert 0 <= score_res["mikherb_score"] <= 100

def test_statistics_service():
    stats = StatisticalAnalyzer.analyze_replicates([80.0, 85.0, 90.0])
    assert stats["mean"] == 85.0
    assert stats["n"] == 3
