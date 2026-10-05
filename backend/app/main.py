import datetime
import os
import json
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.hardware import check_hardware_status
from app.db.database import get_db, engine, Base
from app.models.models import Project, PipelineStage, TargetProtein, Compound, Candidate, Formulation, ExperimentTrial, AIModelRegistry
from app.schemas.schemas import (
    ProjectCreate, ProjectResponse, PipelineStageResponse, TargetProteinResponse,
    CompoundResponse, CandidateResponse, FormulationCreate, FormulationResponse,
    ExperimentTrialCreate, ExperimentTrialResponse
)
from app.engines.protein_engine import ProteinEngine
from app.engines.chemical_engine import ChemicalEngine
from app.engines.docking_engine import AIDockingEngine
from app.engines.selectivity_engine import CropSelectivityEngine
from app.engines.formulation_engine import FormulationEngine
from app.engines.consensus_engine import MikHerbConsensusScoreEngine
from app.engines.status_manager import engine_status_manager
from app.services.pipeline_service import DiscoveryPipelineRunner
from app.services.statistics_service import StatisticalAnalyzer
from app.services.qsar_service import QSARActiveLearningEngine
from app.services.agent_service import AIResearchAgent
from app.services.report_service import ReportGenerator

# Ensure DB tables exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.core.firebase import init_firebase, is_firebase_active

# Initialize Firebase if credentials exist
init_firebase()

# Global service instances
protein_engine = ProteinEngine()
chemical_engine = ChemicalEngine()
docking_engine = AIDockingEngine()
selectivity_engine = CropSelectivityEngine()
formulation_engine = FormulationEngine()
consensus_engine = MikHerbConsensusScoreEngine()
qsar_engine = QSARActiveLearningEngine()
agent_service = AIResearchAgent()

# ---------------- API ENDPOINTS ----------------

@app.get("/api/v1/system/hardware")
def get_hardware_status():
    return check_hardware_status()

@app.get("/api/v1/system/engines")
def get_engines_status():
    return engine_status_manager.get_all_statuses()

@app.get("/api/v1/system/firebase")
def get_firebase_status():
    return {
        "firebase_active": is_firebase_active(),
        "mode": "firebase_connected" if is_firebase_active() else "local_sqlite_fallback"
    }

# Projects & Pipeline
@app.post("/api/v1/projects", response_model=ProjectResponse)
def create_project(project_in: ProjectCreate, db: Session = Depends(get_db)):
    db_project = Project(**project_in.model_dump())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)

    runner = DiscoveryPipelineRunner(db)
    runner.initialize_project_pipeline(db_project.id)
    return db_project

@app.get("/api/v1/projects", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).all()

@app.get("/api/v1/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj

@app.get("/api/v1/projects/{project_id}/stages", response_model=List[PipelineStageResponse])
def get_project_stages(project_id: int, db: Session = Depends(get_db)):
    return db.query(PipelineStage).filter_by(project_id=project_id).order_by(PipelineStage.stage_order).all()

@app.post("/api/v1/projects/{project_id}/run")
def run_project_discovery(project_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    proj.status = "running"
    db.commit()

    runner = DiscoveryPipelineRunner(db)
    background_tasks.add_task(runner.run_pipeline, project_id)
    return {"status": "STARTED", "message": f"Discovery pipeline started for project {proj.name}"}

# Candidates & Targets
@app.get("/api/v1/projects/{project_id}/candidates", response_model=List[CandidateResponse])
def get_project_candidates(project_id: int, db: Session = Depends(get_db)):
    return db.query(Candidate).filter_by(project_id=project_id).order_by(Candidate.mikherb_score.desc()).all()

@app.get("/api/v1/candidates/{candidate_id}", response_model=CandidateResponse)
def get_candidate_detail(candidate_id: int, db: Session = Depends(get_db)):
    cand = db.query(Candidate).filter_by(id=candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return cand

@app.post("/api/v1/candidates/{candidate_id}/add_to_queue")
def add_candidate_to_experimental_queue(candidate_id: int, db: Session = Depends(get_db)):
    cand = db.query(Candidate).filter_by(id=candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    cand.status = "in_experimental_queue"
    db.commit()
    return {"status": "SUCCESS", "candidate_code": cand.compound_code, "new_status": cand.status}

@app.get("/api/v1/projects/{project_id}/targets", response_model=List[TargetProteinResponse])
def get_project_targets(project_id: int, db: Session = Depends(get_db)):
    return db.query(TargetProtein).filter_by(project_id=project_id).all()

# Chemical Intelligence
@app.get("/api/v1/chemistry/descriptors")
def calculate_chemical_descriptors(smiles: str = Query(...)):
    desc = chemical_engine.calculate_descriptors(smiles)
    if not desc:
        raise HTTPException(status_code=400, detail="Invalid SMILES string")
    return desc

@app.get("/api/v1/chemistry/pubchem_search")
def pubchem_search(query: str = Query(...)):
    res = chemical_engine.fetch_pubchem_compound(query)
    if not res:
        raise HTTPException(status_code=404, detail="Compound not found in PubChem")
    return res

# Formulation Intelligence
@app.post("/api/v1/formulation/analyze", response_model=FormulationResponse)
def analyze_formulation_endpoint(formulation_in: FormulationCreate, db: Session = Depends(get_db)):
    analysis = formulation_engine.analyze_formulation(
        formulation_in.active_ingredient,
        formulation_in.active_concentration_g_l,
        formulation_in.solvent,
        formulation_in.surfactant,
        formulation_in.adjuvant,
        formulation_in.acid_base_buffer
    )

    db_form = Formulation(
        name=formulation_in.name,
        active_ingredient=formulation_in.active_ingredient,
        active_concentration_g_l=formulation_in.active_concentration_g_l,
        solvent=formulation_in.solvent,
        surfactant=formulation_in.surfactant,
        adjuvant=formulation_in.adjuvant,
        acid_base_buffer=formulation_in.acid_base_buffer,
        preservative=formulation_in.preservative,
        ph_predicted=analysis["predicted_ph"],
        solubility_risk=analysis["solubility_risk"],
        precipitation_risk=analysis["precipitation_risk"],
        phase_separation_risk=analysis["phase_separation_risk"],
        compatibility_score=analysis["compatibility_score"],
        risk_flags=analysis["risk_flags"],
        notes=formulation_in.notes
    )
    db.add(db_form)
    db.commit()
    db.refresh(db_form)
    return db_form

@app.get("/api/v1/formulation", response_model=List[FormulationResponse])
def list_formulations(db: Session = Depends(get_db)):
    return db.query(Formulation).all()

# Experiments & Active Learning
@app.post("/api/v1/experiments", response_model=ExperimentTrialResponse)
def record_experiment_trial(trial_in: ExperimentTrialCreate, db: Session = Depends(get_db)):
    raw_vals = [r.get("visual_injury_pct", 0.0) for r in trial_in.replicates_data]
    stats_res = StatisticalAnalyzer.analyze_replicates(raw_vals)

    db_trial = ExperimentTrial(
        trial_name=trial_in.trial_name,
        trial_type=trial_in.trial_type,
        target_name=trial_in.target_name,
        compound_code=trial_in.compound_code,
        dose_rate_g_ha=trial_in.dose_rate_g_ha,
        weed_species=trial_in.weed_species,
        crop_species=trial_in.crop_species,
        visual_injury_pct=stats_res["mean"],
        replicates_data=trial_in.replicates_data,
        statistical_summary=stats_res
    )
    db.add(db_trial)
    db.commit()
    db.refresh(db_trial)
    return db_trial

@app.get("/api/v1/experiments", response_model=List[ExperimentTrialResponse])
def list_experiment_trials(db: Session = Depends(get_db)):
    return db.query(ExperimentTrial).all()

@app.post("/api/v1/ai_lab/train_qsar")
def train_qsar_model(db: Session = Depends(get_db)):
    trials = db.query(ExperimentTrial).all()
    if not trials:
        return {
            "status": "INSUFFICIENT_DATA",
            "sample_count": 0,
            "message": "Zero experimental trials recorded. At least 3 experimental observation trials are required to train QSAR model."
        }

    smiles_list = [t.compound_code for t in trials if t.compound_code and "MH-" in t.compound_code]
    act_list = [t.visual_injury_pct or 0.0 for t in trials if t.compound_code and "MH-" in t.compound_code]

    return qsar_engine.train_qsar(smiles_list, act_list)

@app.post("/api/v1/ai_lab/active_learning_prioritize")
def active_learning_prioritize(smiles_list: List[str]):
    return qsar_engine.predict_with_uncertainty(smiles_list)

# AI Research Agent Interface
@app.post("/api/v1/agent/chat")
def agent_chat(query: str, context: Optional[Dict[str, Any]] = None):
    return agent_service.execute_agent_query(query, context)

@app.get("/api/v1/agent/tools")
def get_agent_tools():
    return agent_service.available_tools()
