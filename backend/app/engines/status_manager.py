from typing import Dict, Any, Optional
from app.engines.base import BaseScientificEngine

def _validate_rdkit() -> bool:
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        m = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        if m is None:
            return False
        m = Chem.AddHs(m)
        return AllChem.EmbedMolecule(m, AllChem.ETKDG()) == 0
    except Exception:
        return False

def _validate_gnina() -> bool:
    import shutil, tempfile, os
    gnina_bin = shutil.which("gnina")
    if not gnina_bin:
        return False
    try:
        from app.engines.docking_engine import GNINAAdapter
        adapter = GNINAAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_pdb = os.path.join(tmpdir, "fixture.pdb")
            with open(dummy_pdb, "w") as f:
                f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")
            res = adapter.dock(dummy_pdb, "CCO", [10.0, 10.0, 10.0], [15.0, 15.0, 15.0])
            return res.get("status") == "COMPLETED" and res.get("cnn_score") is not None
    except Exception:
        return False

def _validate_boltz() -> bool:
    import shutil, tempfile, os
    boltz_bin = shutil.which("boltz")
    if not boltz_bin:
        return False
    try:
        from app.engines.docking_engine import Boltz2Adapter
        adapter = Boltz2Adapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_pdb = os.path.join(tmpdir, "fixture.pdb")
            with open(dummy_pdb, "w") as f:
                f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")
            res = adapter.predict_complex(dummy_pdb, "CCO", [10.0, 10.0, 10.0], protein_sequence="MKVLA")
            return (
                res.get("status") == "COMPLETED"
                and res.get("pIC50_predicted") is not None
                and res.get("boltz_complex_plddt") is not None
            )
    except Exception:
        return False

def _validate_p2rank() -> bool:
    import shutil, tempfile, os
    p2rank_bin = shutil.which("p2rank")
    if not p2rank_bin:
        return False
    try:
        from app.engines.protein_engine import P2RankPocketPredictor
        predictor = P2RankPocketPredictor()
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_pdb = os.path.join(tmpdir, "fixture.pdb")
            with open(dummy_pdb, "w") as f:
                f.write("ATOM      1  CA  MET A   1      10.000  10.000  10.000  1.00 88.00           C\n")
            res = predictor.predict_pockets_from_pdb(dummy_pdb)
            if isinstance(res, list) and len(res) > 0:
                first = res[0]
                return (
                    first.get("status") == "COMPLETED"
                    and isinstance(first.get("center"), list)
                    and len(first["center"]) == 3
                    and first.get("score") is not None
                )
            return False
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Explicit External Service Validation Fixtures (NOT implicit biological targets)
# Dedicated reference accessions used exclusively to verify external API availability & schemas.
# These accessions MUST NEVER enter actual target discovery, ranking, or candidate scoring.
# ---------------------------------------------------------------------------
UNIPROT_API_TEST_ACCESSION = "P69905"     # Human Hemoglobin subunit alpha (standard universal reference)
ALPHAFOLD_API_TEST_ACCESSION = "P69905"   # Well-characterized standard reference model in AlphaFold DB

def _validate_uniprot() -> bool:
    """
    Validates UniProt REST API connectivity and FASTA payload schema.
    Uses dedicated external service test accession P69905 (not a platform herbicide target).
    """
    import requests
    try:
        url = f"https://rest.uniprot.org/uniprotkb/{UNIPROT_API_TEST_ACCESSION}.fasta"
        r = requests.get(url, timeout=5)
        return r.status_code == 200 and r.text.startswith(">")
    except Exception:
        return False

def _validate_alphafold() -> bool:
    """
    Validates AlphaFold EBI prediction API connectivity and JSON schema.
    Uses dedicated external service test accession P69905 (not a platform herbicide target).
    """
    import requests
    try:
        url = f"https://alphafold.ebi.ac.uk/api/prediction/{ALPHAFOLD_API_TEST_ACCESSION}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return isinstance(data, list) and len(data) > 0 and "pdbUrl" in data[0]
        return False
    except Exception:
        return False

def _validate_pubchem() -> bool:
    """
    Validates PubChem PUG-REST API connectivity and JSON response schema.
    Uses standard reference compound CID 2244 (Aspirin).
    """
    import requests
    try:
        r = requests.get("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/property/MolecularWeight/JSON", timeout=5)
        if r.status_code == 200:
            data = r.json()
            return "PropertyTable" in data and "Properties" in data["PropertyTable"]
        return False
    except Exception:
        return False

class EngineStatusManager:
    """Manages system-wide transparency and two-phase (probe & scientific) validation for engines."""

    def __init__(self):
        self.engines = {
            "rdkit": BaseScientificEngine("RDKit Chemical Intelligence", is_python_lib=True, python_module="rdkit", scientific_validator=_validate_rdkit),
            "uniprot": BaseScientificEngine("UniProt REST API", is_api=True, scientific_validator=_validate_uniprot),
            "alphafold": BaseScientificEngine("AlphaFold DB API", is_api=True, scientific_validator=_validate_alphafold),
            "pubchem": BaseScientificEngine("PubChem PUG-REST API", is_api=True, scientific_validator=_validate_pubchem),
            "p2rank": BaseScientificEngine("P2Rank Pocket Predictor", binary_name="p2rank", validation_args=["-h"], scientific_validator=_validate_p2rank),
            "gnina": BaseScientificEngine("GNINA Deep Learning Docking", binary_name="gnina", validation_args=["--version"], scientific_validator=_validate_gnina),
            "boltz": BaseScientificEngine("Boltz-2 AI Structure Engine", binary_name="boltz", validation_args=["--help"], scientific_validator=_validate_boltz),
            "diffdock": BaseScientificEngine("DiffDock Pose Generator", binary_name="diffdock", validation_args=["--help"]),
            "openmm": BaseScientificEngine("OpenMM Molecular Dynamics", is_python_lib=True, python_module="openmm")
        }

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        statuses = {}
        for key, engine in self.engines.items():
            statuses[key] = engine.get_status()
        return statuses

    def probe_all(self) -> Dict[str, Dict[str, Any]]:
        """Runs basic executable/library probe validation (--version, --help, import) across all engines."""
        statuses = {}
        for key, engine in self.engines.items():
            statuses[key] = engine.probe_validate()
        return statuses

    def scientifically_validate_all(self) -> Dict[str, Dict[str, Any]]:
        """Runs deep scientific verification workflows across all engines."""
        statuses = {}
        for key, engine in self.engines.items():
            statuses[key] = engine.scientific_validate()
        return statuses

    def validate_all(self) -> Dict[str, Dict[str, Any]]:
        """Runs complete probe and scientific validation across all engines."""
        statuses = {}
        for key, engine in self.engines.items():
            statuses[key] = engine.validate()
        return statuses

    def validate_engine(self, engine_key: str, scientific: bool = True) -> Optional[Dict[str, Any]]:
        """Validates a specific engine by key."""
        engine = self.engines.get(engine_key)
        if not engine:
            return None
        return engine.scientific_validate() if scientific else engine.probe_validate()

engine_status_manager = EngineStatusManager()

