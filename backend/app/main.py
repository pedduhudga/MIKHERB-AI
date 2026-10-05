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
from app.models.models import (
    Project, PipelineStage, TargetProtein, Compound, Candidate, Formulation, ExperimentTrial, AIModelRegistry,
    MolecularGenerationRun, GeneratedMolecule, MoleculeFilterResult, MoleculeNoveltyResult, MoleculeProvenance
)
from app.schemas.schemas import (
    ProjectCreate, ProjectResponse, PipelineStageResponse, TargetProteinResponse,
    CompoundResponse, CandidateResponse, FormulationCreate, FormulationResponse,
    ExperimentTrialCreate, ExperimentTrialResponse,
    MolecularGenerationRunCreate, MolecularGenerationRunResponse, GeneratedMoleculeResponse
)
from app.engines.protein_engine import ProteinEngine
from app.engines.chemical_engine import ChemicalEngine
from app.engines.docking_engine import AIDockingEngine
from app.engines.selectivity_engine import CropSelectivityEngine
from app.engines.formulation_engine import FormulationEngine
from app.engines.consensus_engine import MikHerbConsensusScoreEngine
from app.engines.status_manager import engine_status_manager
from app.engines.molecular_generation import (
    MolecularGenerationManager, GenerationMode, MolecularFilterConfig, ChemicalValidatorAndFilter, NoveltyAnalyzer
)
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

from app.core.firebase import init_firebase, is_firebase_active, get_current_user, sync_db_project_to_firestore, verify_project_ownership

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
mol_gen_manager = MolecularGenerationManager()

# ---------------- API ENDPOINTS ----------------

@app.get("/api/v1/system/hardware")
def get_hardware_status():
    return check_hardware_status()

@app.get("/api/v1/system/engines")
def get_engines_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    return engine_status_manager.get_all_statuses()

@app.post("/api/v1/system/engines/validate")
def validate_engines(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Complete probe and scientific validation across all engines."""
    return engine_status_manager.validate_all()

@app.post("/api/v1/system/engines/probe")
def probe_engines(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Live CLI probe validation (--version, --help, imports) across scientific engines."""
    return engine_status_manager.probe_all()

@app.post("/api/v1/system/engines/validate_scientific")
def validate_engines_scientifically(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Deep scientific fixture verification workflows across scientific engines."""
    return engine_status_manager.scientifically_validate_all()

@app.get("/api/v1/system/firebase")
def get_firebase_status():
    return {
        "firebase_active": is_firebase_active(),
        "mode": "firebase_connected" if is_firebase_active() else "local_sqlite_fallback"
    }

# Projects & Pipeline
@app.post("/api/v1/projects", response_model=ProjectResponse)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    project_data = project_in.model_dump()
    if current_user:
        if current_user.get("uid"):
            project_data["owner_uid"] = current_user.get("uid")
        if current_user.get("email"):
            project_data["researcher"] = current_user.get("email")
    db_project = Project(**project_data)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)

    runner = DiscoveryPipelineRunner(db)
    runner.initialize_project_pipeline(db_project.id)
    sync_db_project_to_firestore(db_project.id, db)
    return db_project

@app.get("/api/v1/projects", response_model=List[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_uid = current_user.get("uid") if current_user else None
    if user_uid and user_uid != "local_dev_user":
        return db.query(Project).filter(Project.owner_uid == user_uid).all()
    return db.query(Project).all()

@app.get("/api/v1/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)
    return proj

@app.get("/api/v1/projects/{project_id}/stages", response_model=List[PipelineStageResponse])
def get_project_stages(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)
    return db.query(PipelineStage).filter_by(project_id=project_id).order_by(PipelineStage.stage_order).all()

@app.post("/api/v1/projects/{project_id}/run")
def run_project_discovery(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)

    proj.status = "running"
    db.commit()
    sync_db_project_to_firestore(project_id, db)

    runner = DiscoveryPipelineRunner(db)
    background_tasks.add_task(runner.run_pipeline, project_id)
    return {"status": "STARTED", "message": f"Discovery pipeline started for project {proj.name}"}

# Candidates & Targets
@app.get("/api/v1/projects/{project_id}/candidates", response_model=List[CandidateResponse])
def get_project_candidates(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)
    return db.query(Candidate).filter_by(project_id=project_id).order_by(Candidate.mikherb_score.desc()).all()

@app.get("/api/v1/candidates/{candidate_id}", response_model=CandidateResponse)
def get_candidate_detail(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    cand = db.query(Candidate).filter_by(id=candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if cand.project:
        verify_project_ownership(cand.project, current_user)
    return cand

@app.post("/api/v1/candidates/{candidate_id}/add_to_queue")
def add_candidate_to_experimental_queue(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    cand = db.query(Candidate).filter_by(id=candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if cand.project:
        verify_project_ownership(cand.project, current_user)
    cand.status = "in_experimental_queue"
    db.commit()
    sync_db_project_to_firestore(cand.project_id, db)
    return {"status": "SUCCESS", "candidate_code": cand.compound_code, "new_status": cand.status}

@app.get("/api/v1/projects/{project_id}/targets", response_model=List[TargetProteinResponse])
def get_project_targets(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)
    return db.query(TargetProtein).filter_by(project_id=project_id).all()

# ---------------- Molecular Generation Endpoints ----------------

@app.post("/api/v1/projects/{project_id}/molecular-generation/runs", response_model=MolecularGenerationRunResponse)
def create_molecular_generation_run(
    project_id: int,
    run_in: MolecularGenerationRunCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)

    target = db.query(TargetProtein).filter_by(id=run_in.target_id, project_id=project_id).first()
    if not target:
        raise HTTPException(status_code=404, detail=f"Target {run_in.target_id} not found for this project")

    try:
        mode_enum = GenerationMode(run_in.generation_mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid generation mode '{run_in.generation_mode}'")

    generator = mol_gen_manager.get_generator(mode_enum)
    gen_name = generator.name if generator else run_in.generation_mode
    gen_ver = generator.version if generator else "1.0.0"

    run = MolecularGenerationRun(
        project_id=project_id,
        target_id=run_in.target_id,
        run_name=run_in.run_name or f"{run_in.generation_mode} for {target.gene or target.name}",
        generation_mode=run_in.generation_mode,
        generator_name=gen_name,
        generator_version=gen_ver,
        status="PENDING",
        random_seed=run_in.random_seed,
        requested_count=run_in.requested_count,
        parameters_json=run_in.parameters,
        filter_config_json=run_in.filter_config
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

@app.get("/api/v1/projects/{project_id}/molecular-generation/runs", response_model=List[MolecularGenerationRunResponse])
def list_molecular_generation_runs(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)
    return db.query(MolecularGenerationRun).filter_by(project_id=project_id).order_by(MolecularGenerationRun.created_at.desc()).all()

@app.get("/api/v1/projects/{project_id}/molecular-generation/runs/{run_id}", response_model=MolecularGenerationRunResponse)
def get_molecular_generation_run(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)

    run = db.query(MolecularGenerationRun).filter_by(id=run_id, project_id=project_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Molecular generation run not found")
    return run

@app.post("/api/v1/projects/{project_id}/molecular-generation/runs/{run_id}/execute")
def execute_molecular_generation_run(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)

    run = db.query(MolecularGenerationRun).filter_by(id=run_id, project_id=project_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Molecular generation run not found")

    target = db.query(TargetProtein).filter_by(id=run.target_id).first()
    if not target:
        raise HTTPException(status_code=400, detail="Run target not found")

    p_center = None
    if target.pockets_json and isinstance(target.pockets_json, list) and len(target.pockets_json) > 0:
        p_center = target.pockets_json[0].get("center")

    target_analysis = target.analysis_json or {}
    validated_artifact = target_analysis.get("validated_target_artifact") or {}
    real_uniprot_id = target.uniprot_id or validated_artifact.get("weed_uniprot_id")

    gene_ver = target_analysis.get("gene_verified")
    if gene_ver is None:
        gene_ver = validated_artifact.get("gene_verified")

    func_ver = target_analysis.get("function_verified")
    if func_ver is None:
        func_ver = validated_artifact.get("function_verified")

    target_ident_ver = target_analysis.get("target_identity_verified")
    if target_ident_ver is None:
        target_ident_ver = validated_artifact.get("target_identity_verified")

    org_ver = target_analysis.get("organism_verified")
    if org_ver is None:
        org_ver = validated_artifact.get("organism_verified")

    essentiality_ev = (
        target.essentiality_status
        or validated_artifact.get("essentiality_evidence")
        or target_analysis.get("essentiality_evidence")
    )

    target_info = {
        "id": target.id,
        "target_id": target.id,
        "gene": target.gene or target.name,
        "name": target.name,
        "target_family": target.target_family,
        "weed_species": proj.weed_species,
        "organism": proj.weed_species,
        "weed_uniprot_id": real_uniprot_id,
        "uniprot_id": real_uniprot_id,
        "target_identity_verified": target_ident_ver,
        "organism_verified": org_ver,
        "gene_verified": gene_ver,
        "function_verified": func_ver,
        "essentiality_evidence": essentiality_ev,
        "weed_sequence": target.weed_sequence,
        "sequence": target.weed_sequence,
        "pdb_path": target.pdb_id or validated_artifact.get("pdb_path"),
        "structure_status": validated_artifact.get("structure_status", "ALPHA_FOLD_RETRIEVED" if target.pdb_id else "STRUCTURE_UNAVAILABLE"),
        "structure_confidence": target.structure_confidence,
        "alphafold_available": bool(target.alphafold_id or target.structure_confidence),
        "pockets_json": target.pockets_json,
        "pocket_center": p_center,
        "pocket_prediction_status": validated_artifact.get("pocket_prediction_status", "COMPLETED" if p_center else "NO_POCKETS"),
        "weed_accession_provenance": target_analysis.get("weed_accession_provenance") or validated_artifact.get("provenance")
    }

    filter_cfg = MolecularFilterConfig(**(run.filter_config_json or {})) if run.filter_config_json else None

    existing_mols = db.query(GeneratedMolecule).filter_by(project_id=project_id).all()
    internal_candidates = [{"smiles": m.canonical_smiles or m.smiles, "inchikey": m.inchikey} for m in existing_mols]

    run.status = "RUNNING"
    db.commit()

    try:
        gen_res = mol_gen_manager.execute_generation_run(
            target_info=target_info,
            generation_mode=GenerationMode(run.generation_mode),
            requested_count=run.requested_count,
            random_seed=run.random_seed,
            parameters=run.parameters_json,
            filter_config=filter_cfg,
            internal_candidates=internal_candidates
        )

        run.status = gen_res.get("status", "COMPLETED")
        run.generated_count = gen_res.get("generated_count", 0)
        run.valid_count = gen_res.get("valid_count", 0)
        run.rejected_count = gen_res.get("rejected_count", 0)
        run.unique_count = gen_res.get("unique_count", 0)
        run.novel_count = gen_res.get("novel_count", 0)
        run.completed_at = datetime.datetime.utcnow()
        if gen_res.get("error"):
            run.error_message = gen_res.get("error")

        # Persist generated molecules and detail records
        for mol_data in gen_res.get("molecules", []):
            props = mol_data.get("properties") or {}
            alerts = mol_data.get("structural_alerts") or {}
            novelty = mol_data.get("novelty") or {}
            prov = mol_data.get("provenance") or {}
            p_comp = mol_data.get("pocket_complementarity")
            p_comp_dict = p_comp.dict() if hasattr(p_comp, "dict") else (p_comp if isinstance(p_comp, dict) else None)
            p_fit = p_comp_dict.get("pocket_fit_score") if p_comp_dict else None

            db_mol = GeneratedMolecule(
                run_id=run.id,
                project_id=project_id,
                target_id=target.id,
                compound_code=mol_data.get("compound_code"),
                smiles=mol_data.get("smiles"),
                canonical_smiles=mol_data.get("canonical_smiles"),
                inchi=mol_data.get("inchi"),
                inchikey=mol_data.get("inchikey"),
                molecular_formula=props.get("molecular_formula"),
                mw=props.get("molecular_weight"),
                logp=props.get("logp"),
                hbd=props.get("hbd"),
                hba=props.get("hba"),
                tpsa=props.get("tpsa"),
                rotatable_bonds=props.get("rotatable_bonds"),
                formal_charge=props.get("formal_charge"),
                heavy_atom_count=props.get("heavy_atom_count"),
                ring_count=props.get("ring_count"),
                chemical_validation_status=mol_data.get("chemical_validation_status", "VALID"),
                rejection_reason=mol_data.get("rejection_reason"),
                generation_mode=run.generation_mode,
                parent_molecule_smiles=prov.get("parent_molecule"),
                parent_candidate_id=prov.get("parent_candidate_id"),
                passed_all_filters=mol_data.get("passed_all_filters", False),
                structural_alerts_count=alerts.get("alerts_count", 0),
                structural_alerts_json=alerts.get("alerts_detected", []),
                max_tanimoto_similarity=novelty.get("max_tanimoto_similarity"),
                novelty_category=novelty.get("novelty_category"),
                closest_known_compound=novelty.get("closest_known_compound"),
                pocket_fit_score=p_fit,
                pocket_compatibility_json=p_comp_dict
            )
            db.add(db_mol)
            db.commit()
            db.refresh(db_mol)

            # Persist filter result
            db_filter = MoleculeFilterResult(
                molecule_id=db_mol.id,
                passed_all_filters=mol_data.get("passed_all_filters", False),
                property_results_json=mol_data.get("filter_results"),
                structural_alert_screen_passed=alerts.get("passed", True),
                structural_alerts_detected_json=alerts.get("alerts_detected", [])
            )
            db.add(db_filter)

            # Persist novelty result
            db_novelty = MoleculeNoveltyResult(
                molecule_id=db_mol.id,
                exact_match=novelty.get("exact_match", False),
                max_tanimoto_similarity=novelty.get("max_tanimoto_similarity"),
                closest_known_compound=novelty.get("closest_known_compound"),
                novelty_category=novelty.get("novelty_category"),
                reference_database=novelty.get("reference_database", "Default")
            )
            db.add(db_novelty)

            # Persist provenance record
            p_center = None
            if target.pockets_json and len(target.pockets_json) > 0:
                p_center = target.pockets_json[0].get("center")

            db_prov = MoleculeProvenance(
                molecule_id=db_mol.id,
                target_id=target.id,
                protein_sequence_hash=prov.get("protein_sequence_hash"),
                pocket_center_json=p_center,
                generation_method=prov.get("generation_method", run.generation_mode),
                generator_name=prov.get("generator_name", run.generator_name),
                generator_version=prov.get("generator_version", run.generator_version),
                parameters_json=prov.get("parameters"),
                random_seed=prov.get("random_seed"),
                provenance_hash=prov.get("provenance_hash", "UNKNOWN")
            )
            db.add(db_prov)

        db.commit()
        db.refresh(run)
        return {
            "status": run.status,
            "run_id": run.id,
            "generated_count": run.generated_count,
            "valid_count": run.valid_count,
            "rejected_count": run.rejected_count,
            "unique_count": run.unique_count,
            "novel_count": run.novel_count,
            "error_message": run.error_message
        }
    except Exception as e:
        run.status = "FAILED"
        run.error_message = str(e)
        db.commit()
        return {"status": "FAILED", "run_id": run.id, "error": str(e)}

@app.get("/api/v1/projects/{project_id}/molecules", response_model=List[GeneratedMoleculeResponse])
def list_project_molecules(
    project_id: int,
    run_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)

    query = db.query(GeneratedMolecule).filter_by(project_id=project_id)
    if run_id:
        query = query.filter_by(run_id=run_id)
    if status:
        query = query.filter_by(chemical_validation_status=status)
    return query.order_by(GeneratedMolecule.created_at.desc()).all()

@app.get("/api/v1/projects/{project_id}/molecules/{molecule_id}")
def get_project_molecule(
    project_id: int,
    molecule_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)

    mol = db.query(GeneratedMolecule).filter_by(id=molecule_id, project_id=project_id).first()
    if not mol:
        raise HTTPException(status_code=404, detail="Molecule not found")

    return {
        "molecule": mol,
        "filter_results": mol.filter_result,
        "novelty": mol.novelty_result,
        "provenance": mol.provenance_record
    }

@app.post("/api/v1/projects/{project_id}/molecules/{molecule_id}/validate")
def revalidate_project_molecule(
    project_id: int,
    molecule_id: int,
    filter_config: Optional[MolecularFilterConfig] = None,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)

    mol = db.query(GeneratedMolecule).filter_by(id=molecule_id, project_id=project_id).first()
    if not mol:
        raise HTTPException(status_code=404, detail="Molecule not found")

    cfg = filter_config or MolecularFilterConfig()
    is_valid, val_status, rej_reason, can_smiles, inchi_str, inchikey_str, props_dict, mol_obj = (
        ChemicalValidatorAndFilter.validate_and_characterize(mol.smiles)
    )

    if not is_valid:
        return {"status": "REJECTED", "rejection_reason": rej_reason}

    passed_all, filter_items = ChemicalValidatorAndFilter.apply_filters(props_dict, cfg)
    alert_screen = ChemicalValidatorAndFilter.screen_structural_alerts(mol_obj, cfg)

    return {
        "status": "VALID",
        "passed_all_filters": passed_all,
        "filter_results": [f.model_dump() for f in filter_items],
        "structural_alerts": alert_screen.model_dump()
    }

@app.post("/api/v1/projects/{project_id}/molecules/{molecule_id}/novelty")
def evaluate_project_molecule_novelty(
    project_id: int,
    molecule_id: int,
    database_scope: str = Query("MIKHERB Known Commercial Herbicides Catalogue"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    verify_project_ownership(proj, current_user)

    mol = db.query(GeneratedMolecule).filter_by(id=molecule_id, project_id=project_id).first()
    if not mol:
        raise HTTPException(status_code=404, detail="Molecule not found")

    is_valid, _, _, can_smiles, _, _, _, mol_obj = ChemicalValidatorAndFilter.validate_and_characterize(mol.smiles)
    if not is_valid or mol_obj is None:
        raise HTTPException(status_code=400, detail="Cannot evaluate novelty on invalid molecule")

    analyzer = NoveltyAnalyzer()
    res = analyzer.evaluate_novelty(mol_obj, can_smiles, database_scope=database_scope)
    return res.model_dump()

# Chemical Intelligence
@app.get("/api/v1/chemistry/descriptors")
def calculate_chemical_descriptors(
    smiles: str = Query(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    desc = chemical_engine.calculate_descriptors(smiles)
    if not desc:
        raise HTTPException(status_code=400, detail="Invalid SMILES string")
    return desc

@app.get("/api/v1/chemistry/pubchem_search")
def pubchem_search(
    query: str = Query(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    res = chemical_engine.fetch_pubchem_compound(query)
    if not res:
        raise HTTPException(status_code=404, detail="Compound not found in PubChem")
    return res

# Formulation Intelligence
@app.post("/api/v1/formulation/analyze", response_model=FormulationResponse)
def analyze_formulation_endpoint(
    formulation_in: FormulationCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
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
def list_formulations(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    return db.query(Formulation).all()

# Experiments & Active Learning
@app.post("/api/v1/experiments", response_model=ExperimentTrialResponse)
def record_experiment_trial(
    trial_in: ExperimentTrialCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
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
def list_experiment_trials(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    return db.query(ExperimentTrial).all()

@app.post("/api/v1/ai_lab/train_qsar")
def train_qsar_model(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
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
def active_learning_prioritize(
    smiles_list: List[str],
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    return qsar_engine.predict_with_uncertainty(smiles_list)

# AI Research Agent Interface
@app.post("/api/v1/agent/chat")
def agent_chat(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    return agent_service.execute_agent_query(query, context)

@app.get("/api/v1/agent/tools")
def get_agent_tools(current_user: Dict[str, Any] = Depends(get_current_user)):
    return agent_service.available_tools()
