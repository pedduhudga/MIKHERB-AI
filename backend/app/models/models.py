import datetime
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.database import Base

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    owner_uid = Column(String, index=True, nullable=True)
    researcher = Column(String, default="Dr. Miklens Researcher")
    weed_species = Column(String, nullable=False)
    crop_species = Column(String, nullable=False)
    objective = Column(String, nullable=False)  # e.g., "new_herbicide", "improve_selectivity"
    notes = Column(Text, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    pipeline_stages = relationship("PipelineStage", back_populates="project", cascade="all, delete-orphan")
    targets = relationship("TargetProtein", back_populates="project", cascade="all, delete-orphan")
    candidates = relationship("Candidate", back_populates="project", cascade="all, delete-orphan")

class PipelineStage(Base):
    __tablename__ = "pipeline_stages"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    stage_name = Column(String, nullable=False)
    stage_order = Column(Integer, nullable=False)
    status = Column(String, default="pending")  # pending, running, completed, failed, skipped
    error_message = Column(Text, nullable=True)
    results_summary = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="pipeline_stages")

class TargetProtein(Base):
    __tablename__ = "target_proteins"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    uniprot_id = Column(String, nullable=True)
    weed_sequence = Column(Text, nullable=True)
    crop_homolog_uniprot_id = Column(String, nullable=True)
    crop_sequence = Column(Text, nullable=True)
    pdb_id = Column(String, nullable=True)
    alphafold_id = Column(String, nullable=True)

    # Multi-Target Discovery & Ranking metadata
    rank = Column(Integer, nullable=True)
    is_primary_selected = Column(Boolean, default=False)
    gene = Column(String, nullable=True)
    target_family = Column(String, nullable=True)
    target_evidence_score = Column(Float, nullable=True)
    target_evidence_confidence = Column(String, nullable=True)  # HIGH, MEDIUM, LOW, HYPOTHESIS_ONLY
    essentiality_status = Column(String, nullable=True)

    # Alignment Provenance & Metrics
    alignment_status = Column(String, nullable=True)  # COMPLETED, FAILED, NOT_ATTEMPTED
    alignment_method = Column(String, nullable=True)
    alignment_coverage_pct = Column(Float, nullable=True)
    weed_coverage_pct = Column(Float, nullable=True)
    crop_coverage_pct = Column(Float, nullable=True)
    identity_over_aligned_pct = Column(Float, nullable=True)

    # Essentiality evidence stratification
    essentiality_evidence_level = Column(String, nullable=True)  # SPECIES_SPECIFIC, GENERAL_PLANT_EVIDENCE, PRECLINICAL_HYPOTHESIS, UNKNOWN
    species_specific_essentiality = Column(Boolean, default=False)

    # Target Opportunity Scores — NULL = not measured (not fabricated defaults)
    essentiality_score = Column(Float, nullable=True)
    weed_specificity_score = Column(Float, nullable=True)
    crop_divergence_score = Column(Float, nullable=True)
    structure_confidence = Column(Float, nullable=True)  # pLDDT from AlphaFold
    druggability_score = Column(Float, nullable=True)
    existing_evidence_score = Column(Float, nullable=True)
    total_opportunity_score = Column(Float, nullable=True)

    pockets_json = Column(JSON, nullable=True)
    analysis_json = Column(JSON, nullable=True)

    project = relationship("Project", back_populates="targets")

class ChemicalLibrary(Base):
    __tablename__ = "chemical_libraries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    source = Column(String, default="User Upload / PubChem")
    compound_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    compounds = relationship("Compound", back_populates="library", cascade="all, delete-orphan")

class Compound(Base):
    __tablename__ = "compounds"

    id = Column(Integer, primary_key=True, index=True)
    library_id = Column(Integer, ForeignKey("chemical_libraries.id"), nullable=True)
    compound_code = Column(String, index=True, nullable=False)  # e.g., MH-000127
    name = Column(String, nullable=True)
    smiles = Column(Text, nullable=False)
    canonical_smiles = Column(Text, nullable=True)
    pubchem_cid = Column(String, nullable=True)
    chembl_id = Column(String, nullable=True)

    # Physicochemical properties
    mw = Column(Float, nullable=True)
    logp = Column(Float, nullable=True)
    hbd = Column(Integer, nullable=True)
    hba = Column(Integer, nullable=True)
    tpsa = Column(Float, nullable=True)
    rotatable_bonds = Column(Integer, nullable=True)
    lipinski_pass = Column(Boolean, default=True)

    # Toxicity & Novelty
    safety_evidence = Column(JSON, nullable=True)
    tanimoto_similarity_to_known = Column(Float, nullable=True)
    novelty_score = Column(Float, default=85.0)

    library = relationship("ChemicalLibrary", back_populates="compounds")

class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    compound_code = Column(String, nullable=False)
    smiles = Column(Text, nullable=False)
    target_name = Column(String, nullable=False)

    # Evidence level: 0=computational, 1=multi-model agree, 2=biochemical, 3=whole-plant, 4=greenhouse, 5=field
    evidence_level = Column(Integer, default=0)

    # Predictions & Docking scores
    boltz_status = Column(String, nullable=True)  # COMPLETED, NOT_INSTALLED, FAILED_EXECUTION, FAILED_OUTPUT_PARSE, POCKET_CENTER_MISSING, NOT_AVAILABLE
    boltz_affinity_score = Column(Float, nullable=True)  # pKd / pKi or affinity metric
    boltz_confidence = Column(Float, nullable=True)
    gnina_status = Column(String, nullable=True)  # COMPLETED, NOT_INSTALLED, FAILED_EXECUTION, FAILED_OUTPUT_PARSE, POCKET_CENTER_MISSING, NOT_AVAILABLE
    gnina_docking_score = Column(Float, nullable=True)  # kcal/mol
    diffdock_score = Column(Float, nullable=True)
    pose_agreement = Column(String, nullable=True)  # HIGH, MEDIUM, LOW, NOT_AVAILABLE

    # Selectivity & Scores — NULL = not computed (scientifically unknown, not zero)
    crop_selectivity_score = Column(Float, nullable=True)  # None means NOT_AVAILABLE
    mikherb_score = Column(Float, nullable=True)

    status = Column(String, default="screened")  # screened, in_experimental_queue, tested

    project = relationship("Project", back_populates="candidates")

class Formulation(Base):
    __tablename__ = "formulations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    active_ingredient = Column(String, nullable=False)
    active_concentration_g_l = Column(Float, default=100.0)
    solvent = Column(String, default="Water")
    surfactant = Column(String, default="Non-ionic Surfactant")
    adjuvant = Column(String, nullable=True)
    acid_base_buffer = Column(String, nullable=True)
    preservative = Column(String, nullable=True)

    # Predicted compatibility & stability flags
    ph_predicted = Column(Float, default=6.5)
    solubility_risk = Column(String, default="LOW")
    precipitation_risk = Column(String, default="LOW")
    phase_separation_risk = Column(String, default="LOW")
    compatibility_score = Column(Float, default=88.0)
    risk_flags = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

class ExperimentTrial(Base):
    __tablename__ = "experiment_trials"

    id = Column(Integer, primary_key=True, index=True)
    trial_name = Column(String, nullable=False)
    trial_type = Column(String, nullable=False)  # biochemical, pot, greenhouse, RCBD, field
    target_name = Column(String, nullable=True)
    compound_code = Column(String, nullable=False)
    dose_rate_g_ha = Column(Float, nullable=True)
    weed_species = Column(String, nullable=False)
    crop_species = Column(String, nullable=True)

    # Results
    visual_injury_pct = Column(Float, nullable=True)
    biomass_reduction_pct = Column(Float, nullable=True)
    mortality_pct = Column(Float, nullable=True)
    crop_phytotoxicity_pct = Column(Float, nullable=True)

    replicates_data = Column(JSON, nullable=True)
    statistical_summary = Column(JSON, nullable=True)  # Mean, SD, SE, CV, ANOVA p-value
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AIModelRegistry(Base):
    __tablename__ = "ai_model_registry"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    model_type = Column(String, nullable=False)  # QSAR, ActiveLearning, Docking, Boltz
    description = Column(Text, nullable=True)
    training_dataset_summary = Column(Text, nullable=True)
    metrics = Column(JSON, nullable=True)  # R2, RMSE, Accuracy
    status = Column(String, default="validated")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
