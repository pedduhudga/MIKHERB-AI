from typing import Dict, Any
from app.engines.base import BaseScientificEngine, EngineStatusManager
from app.engines.docking_engine import Boltz2Adapter, GNINAAdapter, DiffDockAdapter, OpenMMAdapter

class RDKitEngineAdapter(BaseScientificEngine):
    def __init__(self):
        super().__init__(name="RDKit Cheminformatics", category="chemical_intelligence")

    def check_installation(self) -> Dict[str, Any]:
        st = super().check_installation()
        try:
            import rdkit
            st["status"] = "READY"
            st["version"] = getattr(rdkit, "__version__", "2026.3.6")
        except ImportError:
            st["status"] = "NOT_INSTALLED"
        return st

    def get_capabilities(self) -> list:
        return ["smiles_standardization", "descriptors_calculation", "morgan_fingerprints", "tanimoto_similarity", "lipinski_filter"]


class UniProtEngineAdapter(BaseScientificEngine):
    def __init__(self):
        super().__init__(name="UniProt API", category="protein_intelligence")

    def check_installation(self) -> Dict[str, Any]:
        st = super().check_installation()
        st["status"] = "READY"
        st["binary_path"] = "rest_api:https://rest.uniprot.org"
        return st

    def get_capabilities(self) -> list:
        return ["protein_sequence_retrieval", "gene_annotation_fetch", "organism_target_search", "pdb_cross_references"]


class PubChemEngineAdapter(BaseScientificEngine):
    def __init__(self):
        super().__init__(name="PubChem PUG-REST API", category="chemical_intelligence")

    def check_installation(self) -> Dict[str, Any]:
        st = super().check_installation()
        st["status"] = "READY"
        st["binary_path"] = "rest_api:https://pubchem.ncbi.nlm.nih.gov/rest/pug"
        return st

    def get_capabilities(self) -> list:
        return ["compound_search_by_name", "smiles_download", "physicochemical_properties_fetch"]


class ChEMBLEngineAdapter(BaseScientificEngine):
    def __init__(self):
        super().__init__(name="ChEMBL REST API", category="chemical_intelligence")

    def check_installation(self) -> Dict[str, Any]:
        st = super().check_installation()
        st["status"] = "READY"
        st["binary_path"] = "rest_api:https://www.ebi.ac.uk/chembl/api"
        return st

    def get_capabilities(self) -> list:
        return ["bioactivity_retrieval", "target_assay_data", "known_herbicide_search"]


class PDBAlphaFoldEngineAdapter(BaseScientificEngine):
    def __init__(self):
        super().__init__(name="PDB / AlphaFold DB", category="protein_intelligence")

    def check_installation(self) -> Dict[str, Any]:
        st = super().check_installation()
        st["status"] = "READY"
        st["binary_path"] = "rest_api:https://alphafold.ebi.ac.uk"
        return st

    def get_capabilities(self) -> list:
        return ["alphafold_structure_download", "rcsb_pdb_download", "pLDDT_quality_scores"]


class P2RankEngineAdapter(BaseScientificEngine):
    def __init__(self):
        super().__init__(name="P2Rank Binding Pocket Predictor", category="pocket_prediction", binary_name="p2rank")

    def get_capabilities(self) -> list:
        return ["3d_pocket_prediction", "druggability_scoring", "residue_binding_cavity_mapping"]


class FoldseekEngineAdapter(BaseScientificEngine):
    def __init__(self):
        super().__init__(name="Foldseek Structural Homology", category="protein_intelligence", binary_name="foldseek")

    def get_capabilities(self) -> list:
        return ["fast_structural_alignment", "structural_homolog_search"]


def get_global_engine_manager() -> EngineStatusManager:
    manager = EngineStatusManager()
    manager.register_engine("rdkit", RDKitEngineAdapter())
    manager.register_engine("uniprot", UniProtEngineAdapter())
    manager.register_engine("pubchem", PubChemEngineAdapter())
    manager.register_engine("chembl", ChEMBLEngineAdapter())
    manager.register_engine("pdb_alphafold", PDBAlphaFoldEngineAdapter())
    manager.register_engine("p2rank", P2RankEngineAdapter())
    manager.register_engine("foldseek", FoldseekEngineAdapter())
    manager.register_engine("gnina", GNINAAdapter())
    manager.register_engine("boltz2", Boltz2Adapter())
    manager.register_engine("diffdock", DiffDockAdapter())
    manager.register_engine("openmm", OpenMMAdapter())
    return manager
