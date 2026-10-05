export interface HardwareStatus {
  cpu: { cores: number; usage_percent: number };
  memory: { total_gb: number; available_gb: number; usage_percent: number };
  gpu: { available: boolean; name: string; vram_gb: number };
  engines: Record<string, string>;
}

export interface Project {
  id: number;
  name: string;
  researcher: string;
  weed_species: string;
  crop_species: string;
  objective: string;
  status: string;
  created_at: string;
}

export interface Candidate {
  id: number;
  project_id: number;
  compound_code: string;
  smiles: string;
  target_name: string;
  evidence_level: number;
  boltz_status?: string;
  boltz_affinity_score?: number;
  boltz_confidence?: number;
  gnina_status?: string;
  gnina_docking_score?: number;
  pose_agreement: string;
  crop_selectivity_score: number;
  mikherb_score: number;
  status: string;
}

export interface TargetProtein {
  id: number;
  name: string;
  uniprot_id: string;
  weed_sequence: string;
  crop_sequence: string;
  essentiality_score: number;
  weed_specificity_score: number;
  crop_divergence_score: number;
  structure_confidence: number;
  druggability_score: number;
  total_opportunity_score: number;
  pockets_json?: any[];
}

export interface Formulation {
  id: number;
  name: string;
  active_ingredient: string;
  active_concentration_g_l: number;
  solvent: string;
  surfactant: string;
  ph_predicted: number;
  solubility_risk: string;
  precipitation_risk: string;
  compatibility_score: number;
  risk_flags?: string[];
}

export interface ExperimentTrial {
  id: number;
  trial_name: string;
  trial_type: string;
  compound_code: string;
  weed_species: string;
  visual_injury_pct?: number;
  statistical_summary?: {
    mean: number;
    sd: number;
    se: number;
    cv_pct: number;
  };
}

export interface MolecularGenerationRun {
  id: number;
  project_id: number;
  target_id: number;
  run_name: string;
  generation_mode: string;
  generator_name: string;
  generator_version: string;
  status: string;
  random_seed?: number;
  requested_count: number;
  generated_count: number;
  valid_count: number;
  rejected_count: number;
  unique_count: number;
  novel_count: number;
  parameters_json?: Record<string, any>;
  error_message?: string;
  created_at: string;
  completed_at?: string;
}

export interface GeneratedMolecule {
  id: number;
  run_id: number;
  project_id: number;
  target_id: number;
  compound_code: string;
  smiles: string;
  canonical_smiles?: string;
  inchi?: string;
  inchikey?: string;
  molecular_formula?: string;
  mw?: number;
  logp?: number;
  hbd?: number;
  hba?: number;
  tpsa?: number;
  rotatable_bonds?: number;
  chemical_validation_status: string;
  rejection_reason?: string;
  generation_mode: string;
  parent_molecule_smiles?: string;
  passed_all_filters: boolean;
  structural_alerts_count: number;
  structural_alerts_json?: string[];
  max_tanimoto_similarity?: number;
  novelty_category?: string;
  closest_known_compound?: string;
  created_at: string;
}
