export interface HardwareStatus {
  cpu: { cores: number; usage_percent: number };
  memory: { total_gb: number; available_gb: number; usage_percent: number };
  gpu: { available: boolean; name: string; vram_gb: number };
  engines: Record<string, string>;
}

export interface EngineInfo {
  engine: string;
  category: string;
  status: 'READY' | 'NOT_INSTALLED' | 'LIMITED' | 'SIMULATED';
  binary_path?: string | null;
  version: string;
  capabilities: string[];
  last_checked: string;
}

export interface EngineManagerResponse {
  engines: Record<string, EngineInfo>;
  summary: {
    READY: number;
    NOT_INSTALLED: number;
    SIMULATED: number;
  };
  total_engines: number;
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
  boltz_affinity_score?: number | null;
  boltz_confidence?: number | null;
  gnina_docking_score?: number | null;
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
