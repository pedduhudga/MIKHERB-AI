from typing import Dict, Any
from app.engines.base import BaseScientificEngine

class EngineStatusManager:
    """Manages system-wide transparency for installed vs missing scientific engines."""

    def __init__(self):
        self.engines = {
            "rdkit": BaseScientificEngine("RDKit Chemical Intelligence"),
            "uniprot": BaseScientificEngine("UniProt REST API"),
            "alphafold": BaseScientificEngine("AlphaFold DB API"),
            "pubchem": BaseScientificEngine("PubChem PUG-REST API"),
            "p2rank": BaseScientificEngine("P2Rank Pocket Predictor", binary_name="p2rank"),
            "gnina": BaseScientificEngine("GNINA Deep Learning Docking", binary_name="gnina"),
            "boltz": BaseScientificEngine("Boltz-2 AI Structure Engine", binary_name="boltz"),
            "diffdock": BaseScientificEngine("DiffDock Pose Generator", binary_name="diffdock"),
            "openmm": BaseScientificEngine("OpenMM Molecular Dynamics", binary_name="openmm")
        }

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        statuses = {}
        for key, engine in self.engines.items():
            statuses[key] = engine.get_status()
        return statuses

engine_status_manager = EngineStatusManager()
