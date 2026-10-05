from typing import Dict, Any, Optional
from app.engines.base import BaseScientificEngine

class EngineStatusManager:
    """Manages system-wide transparency and live validation for scientific engines."""

    def __init__(self):
        self.engines = {
            "rdkit": BaseScientificEngine("RDKit Chemical Intelligence", is_python_lib=True, python_module="rdkit"),
            "uniprot": BaseScientificEngine("UniProt REST API", is_api=True),
            "alphafold": BaseScientificEngine("AlphaFold DB API", is_api=True),
            "pubchem": BaseScientificEngine("PubChem PUG-REST API", is_api=True),
            "p2rank": BaseScientificEngine("P2Rank Pocket Predictor", binary_name="p2rank", validation_args=["-h"]),
            "gnina": BaseScientificEngine("GNINA Deep Learning Docking", binary_name="gnina", validation_args=["--version"]),
            "boltz": BaseScientificEngine("Boltz-2 AI Structure Engine", binary_name="boltz", validation_args=["--help"]),
            "diffdock": BaseScientificEngine("DiffDock Pose Generator", binary_name="diffdock", validation_args=["--help"]),
            "openmm": BaseScientificEngine("OpenMM Molecular Dynamics", is_python_lib=True, python_module="openmm")
        }

    def get_all_statuses(self, validate: bool = False) -> Dict[str, Dict[str, Any]]:
        statuses = {}
        for key, engine in self.engines.items():
            if validate:
                statuses[key] = engine.validate()
            else:
                statuses[key] = engine.get_status()
        return statuses

    def validate_all(self) -> Dict[str, Dict[str, Any]]:
        """Runs executable/library validation across all engines and returns updated lifecycle statuses."""
        return self.get_all_statuses(validate=True)

    def validate_engine(self, engine_key: str) -> Optional[Dict[str, Any]]:
        """Validates a specific engine by key."""
        engine = self.engines.get(engine_key)
        if not engine:
            return None
        return engine.validate()

engine_status_manager = EngineStatusManager()

