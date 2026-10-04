from pydantic import BaseModel, Field
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

    class Config:
        from_attributes = True

class PipelineStageResponse(BaseModel):
    id: int
    stage_name: str
    stage_order: int
    status: str
    error_message: Optional[str] = None
    results_summary: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class TargetProteinResponse(BaseModel):
    id: int
    project_id: int
    name: str
    uniprot_id: Optional[str] = None
    weed_sequence: Optional[str] = None
    crop_homolog_uniprot_id: Optional[str] = None
    crop_sequence: Optional[str] = None
    pdb_id: Optional[str] = None
    alphafold_id: Optional[str] = None
    essentiality_score: float
    weed_specificity_score: float
    crop_divergence_score: float
    structure_confidence: float
    druggability_score: float
    existing_evidence_score: float
    total_opportunity_score: float
    pockets_json: Optional[List[Dict[str, Any]]] = None

    class Config:
        from_attributes = True

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

    class Config:
        from_attributes = True

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
    pose_agreement: str
    crop_selectivity_score: float
    mikherb_score: float
    status: str

    class Config:
        from_attributes = True

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

    class Config:
        from_attributes = True

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

    class Config:
        from_attributes = True
