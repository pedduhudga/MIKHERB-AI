from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime

class ProjectBase(BaseModel):
    name: str
    researcher: str = "Dr. Miklens Researcher"
    weed_species: str
    crop_species: str
    objective: str
    notes: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectResponse(ProjectBase):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PipelineStageResponse(BaseModel):
    id: int
    stage_name: str
    stage_order: int
    status: str
    error_message: Optional[str] = None
    results_summary: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class TargetProteinResponse(BaseModel):
    id: int
    project_id: int
    name: str
    rank: Optional[int] = None
    is_primary_selected: Optional[bool] = False
    gene: Optional[str] = None
    target_family: Optional[str] = None
    target_evidence_score: Optional[float] = None
    target_evidence_confidence: Optional[str] = None
    essentiality_status: Optional[str] = None
    essentiality_evidence_level: Optional[str] = None
    species_specific_essentiality: Optional[bool] = False
    alignment_status: Optional[str] = None
    alignment_method: Optional[str] = None
    alignment_coverage_pct: Optional[float] = None
    weed_coverage_pct: Optional[float] = None
    crop_coverage_pct: Optional[float] = None
    identity_over_aligned_pct: Optional[float] = None
    uniprot_id: Optional[str] = None
    weed_sequence: Optional[str] = None
    crop_homolog_uniprot_id: Optional[str] = None
    crop_sequence: Optional[str] = None
    pdb_id: Optional[str] = None
    alphafold_id: Optional[str] = None
    essentiality_score: Optional[float] = None
    weed_specificity_score: Optional[float] = None
    crop_divergence_score: Optional[float] = None
    structure_confidence: Optional[float] = None
    druggability_score: Optional[float] = None
    existing_evidence_score: Optional[float] = None
    total_opportunity_score: Optional[float] = None
    pockets_json: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True)

class CompoundResponse(BaseModel):
    id: int
    compound_code: str
    name: Optional[str] = None
    smiles: str
    canonical_smiles: Optional[str] = None
    mw: Optional[float] = None
    logp: Optional[float] = None
    hbd: Optional[int] = None
    hba: Optional[int] = None
    tpsa: Optional[float] = None
    lipinski_pass: bool
    novelty_score: float

    model_config = ConfigDict(from_attributes=True)

class CandidateResponse(BaseModel):
    id: int
    project_id: int
    compound_code: str
    smiles: str
    target_name: str
    evidence_level: int
    boltz_affinity_score: Optional[float] = None
    boltz_confidence: Optional[float] = None
    gnina_docking_score: Optional[float] = None
    diffdock_score: Optional[float] = None
    pose_agreement: Optional[str] = None
    crop_selectivity_score: Optional[float] = None
    mikherb_score: Optional[float] = None
    status: str

    model_config = ConfigDict(from_attributes=True)

class FormulationCreate(BaseModel):
    name: str
    active_ingredient: str
    active_concentration_g_l: float = 100.0
    solvent: str = "Water"
    surfactant: str = "Non-ionic Surfactant"
    adjuvant: Optional[str] = None
    acid_base_buffer: Optional[str] = None
    preservative: Optional[str] = None
    notes: Optional[str] = None

class FormulationResponse(FormulationCreate):
    id: int
    ph_predicted: float
    solubility_risk: str
    precipitation_risk: str
    phase_separation_risk: str
    compatibility_score: float
    risk_flags: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)

class ExperimentTrialCreate(BaseModel):
    trial_name: str
    trial_type: str
    target_name: Optional[str] = None
    compound_code: str
    dose_rate_g_ha: Optional[float] = None
    weed_species: str
    crop_species: Optional[str] = None
    replicates_data: List[Dict[str, float]]

class ExperimentTrialResponse(BaseModel):
    id: int
    trial_name: str
    trial_type: str
    compound_code: str
    weed_species: str
    crop_species: Optional[str] = None
    visual_injury_pct: Optional[float] = None
    biomass_reduction_pct: Optional[float] = None
    mortality_pct: Optional[float] = None
    crop_phytotoxicity_pct: Optional[float] = None
    statistical_summary: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
