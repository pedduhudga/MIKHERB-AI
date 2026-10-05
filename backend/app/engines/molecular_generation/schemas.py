from typing import Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel, Field

class GenerationMode(str, Enum):
    DATABASE_RETRIEVAL = "DATABASE_RETRIEVAL"
    RDKit_ENUMERATION = "RDKit_ENUMERATION"
    FRAGMENT_RECOMBINATION = "FRAGMENT_RECOMBINATION"
    GENERATIVE_AI_ADAPTER = "GENERATIVE_AI_ADAPTER"

class GenerationRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NOT_AVAILABLE = "NOT_AVAILABLE"

class NoveltyCategory(str, Enum):
    KNOWN_EXACT_MATCH = "KNOWN_EXACT_MATCH"
    HIGH_SIMILARITY = "HIGH_SIMILARITY"
    MODERATE_SIMILARITY = "MODERATE_SIMILARITY"
    LOW_SIMILARITY = "LOW_SIMILARITY"
    NO_MATCH_IN_SEARCHED_DATABASE = "NO_MATCH_IN_SEARCHED_DATABASE"

class MolecularFilterConfig(BaseModel):
    """Configurable physicochemical and structural property filters for herbicide candidates."""
    mw_min: float = Field(default=120.0, description="Minimum molecular weight (g/mol)")
    mw_max: float = Field(default=600.0, description="Maximum molecular weight (g/mol)")
    logp_min: float = Field(default=-2.5, description="Minimum calculated LogP")
    logp_max: float = Field(default=5.5, description="Maximum calculated LogP")
    tpsa_min: float = Field(default=15.0, description="Minimum topological polar surface area (Å²)")
    tpsa_max: float = Field(default=170.0, description="Maximum topological polar surface area (Å²)")
    hbd_max: int = Field(default=4, description="Maximum hydrogen bond donors")
    hba_max: int = Field(default=10, description="Maximum hydrogen bond acceptors")
    rotatable_bonds_max: int = Field(default=10, description="Maximum rotatable bonds")
    formal_charge_min: int = Field(default=-2, description="Minimum net formal charge")
    formal_charge_max: int = Field(default=2, description="Maximum net formal charge")
    heavy_atoms_min: int = Field(default=8, description="Minimum heavy atom count")
    heavy_atoms_max: int = Field(default=50, description="Maximum heavy atom count")
    ring_count_min: int = Field(default=1, description="Minimum ring count")
    ring_count_max: int = Field(default=6, description="Maximum ring count")
    enable_pains_filter: bool = Field(default=True, description="Enable PAINS structural alert screen")
    enable_reactive_filter: bool = Field(default=True, description="Enable reactive functional groups alert screen")

class ChemicalProperties(BaseModel):
    molecular_formula: str
    molecular_weight: float
    heavy_atom_count: int
    hbd: int
    hba: int
    rotatable_bonds: int
    tpsa: float
    logp: float
    formal_charge: int
    ring_count: int

class FilterItemResult(BaseModel):
    property: str
    value: Any
    threshold: str
    passed: bool
    reason: Optional[str] = None

class StructuralAlertScreenResult(BaseModel):
    passed: bool
    alerts_count: int
    alerts_detected: List[str] = []
    screen_name: str = "STRUCTURAL_ALERT_SCREEN"
    scientific_disclaimer: str = (
        "Computational structural alert screen only; does not establish biological safety."
    )

class NoveltyAnalysisResult(BaseModel):
    exact_match: bool
    max_tanimoto_similarity: float
    closest_known_compound: Optional[str] = None
    novelty_category: NoveltyCategory
    reference_database: str
    database_scope: List[str] = Field(default_factory=lambda: [
        "MIKHERB_REFERENCE_CATALOGUE",
        "PUBCHEM",
        "CHEMBL",
        "INTERNAL_PROJECT_DATABASE"
    ])
    databases_checked: Dict[str, Any] = Field(default_factory=dict)
    fingerprint_type: str = "Morgan-Radius-2-2048bit"

class ProvenanceMetadata(BaseModel):
    candidate_id: Optional[str] = None
    target_id: Optional[int] = None
    target_family: Optional[str] = None
    generation_method: str
    generation_mode: GenerationMode
    generator_name: str
    generator_version: str
    parent_molecule: Optional[str] = None
    parent_candidate_id: Optional[str] = None
    source_database: Optional[str] = None
    source_compound_id: Optional[str] = None
    source_url: Optional[str] = None
    query_endpoint: Optional[str] = None
    response_hash: Optional[str] = None
    retrieval_method: Optional[str] = None
    external_verification_status: Optional[str] = None  # VERIFIED_EXTERNAL, LOCAL_REFERENCE_ONLY, NOT_APPLICABLE
    random_seed: Optional[int] = None
    parameters: Dict[str, Any] = {}
    created_at: str
    provenance_hash: Optional[str] = None

class PocketComplementarityResult(BaseModel):
    pocket_fit_score: float = Field(..., description="Pocket-derived compatibility heuristic score (0.0 to 1.0)")
    pocket_compatibility_heuristic: float = Field(default=0.0, description="Explicitly labelled pocket compatibility heuristic")
    evaluation_type: str = Field(default="POCKET_DERIVED_HEURISTIC", description="Evaluation methodology tier")
    methodology: str = Field(default="Pocket Volume & Residue Physicochemical Complementarity (Heuristic)")
    is_pocket_compatible: bool = Field(..., description="Whether candidate satisfies binding pocket volume and residue constraints")
    shape_complementarity: float = Field(..., description="Shape and volume match with pocket")
    electrostatic_complementarity: float = Field(..., description="Charge and H-bond donor/acceptor match with pocket residues")
    ligand_volume_angstrom3: float = Field(..., description="Estimated ligand volume in Å³")
    volume_fit_ratio: float = Field(..., description="Ratio of ligand volume to pocket volume")
    satisfied_interactions: List[str] = Field(default_factory=list, description="Key pocket interactions satisfied")
    warnings: List[str] = Field(default_factory=list)

class GeneratedMoleculeDetail(BaseModel):
    compound_code: str
    smiles: str
    canonical_smiles: str
    inchi: str
    inchikey: str
    chemical_validation_status: str  # VALID or REJECTED
    rejection_reason: Optional[str] = None
    properties: Optional[ChemicalProperties] = None
    filter_results: List[FilterItemResult] = []
    passed_all_filters: bool = False
    structural_alerts: Optional[StructuralAlertScreenResult] = None
    novelty: Optional[NoveltyAnalysisResult] = None
    pocket_complementarity: Optional[PocketComplementarityResult] = None
    provenance: ProvenanceMetadata

class GenerationRunCreateRequest(BaseModel):
    target_id: int
    generation_mode: GenerationMode
    run_name: Optional[str] = None
    requested_count: int = Field(default=20, ge=1, le=500, description="Requested candidate count (max 500)")
    random_seed: Optional[int] = Field(default=42, description="Random seed for reproducible generation")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Generator-specific parameters")
    filter_config: Optional[MolecularFilterConfig] = None

class GenerationRunSummaryResponse(BaseModel):
    id: int
    project_id: int
    target_id: int
    run_name: str
    generation_mode: GenerationMode
    generator_name: str
    generator_version: str
    status: GenerationRunStatus
    requested_count: int
    generated_count: int
    valid_count: int
    rejected_count: int
    unique_count: int
    novel_count: int
    random_seed: Optional[int]
    created_at: str
    completed_at: Optional[str]
    error_message: Optional[str] = None
