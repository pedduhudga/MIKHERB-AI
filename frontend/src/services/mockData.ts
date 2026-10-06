import type { HardwareStatus, Project, TargetProtein, Candidate } from '../types';

export const fallbackHardware: HardwareStatus = {
  cpu: { cores: 8, usage_percent: 18.5 },
  memory: { total_gb: 16.0, available_gb: 9.4, usage_percent: 41.2 },
  gpu: { available: true, name: "NVIDIA RTX 4090 (Active Acceleration)", vram_gb: 24.0 },
  engines: {
    rdkit: "READY (Native 2024.03)",
    boltz2: "READY (High Confidence Structure Modeling)",
    gnina: "READY (Ensemble CNN Docking)",
    openmm: "READY (GPU Accelerated Molecular Dynamics)",
    p2rank: "READY (Native Deep Pocket Predictor)",
    foldseek: "READY (Structural Alignment Engine)"
  }
};

export const fallbackProjects: Project[] = [
  {
    id: 1,
    name: "Palmer Amaranth Target-ALS Discovery",
    researcher: "Dr. Miklens Researcher",
    weed_species: "Amaranthus palmeri",
    crop_species: "Glycine max (Soybean)",
    objective: "new_herbicide",
    status: "completed",
    created_at: new Date().toISOString()
  },
  {
    id: 2,
    name: "Waterhemp PPO Inhibitor Selectivity Screen",
    researcher: "Dr. Miklens Researcher",
    weed_species: "Amaranthus tuberculatus",
    crop_species: "Zea mays (Corn)",
    objective: "improve_selectivity",
    status: "active",
    created_at: new Date(Date.now() - 86400000).toISOString()
  }
];

export const fallbackTargets: TargetProtein[] = [
  {
    id: 101,
    name: "Amaranthus palmeri Acetolactate Synthase (ALS)",
    uniprot_id: "A0A890DLI3",
    weed_sequence: "MVKLAARSTPGRSVVTALKPALSDQTPSSGSSSSTSSPTSTPFEKKFRQARLSLPAVVSV",
    crop_sequence: "MATAAASTSLFSTSTTPKTPTTSPFTLPSSSHSTPTTRTAFEKKYRQAKLSLPAVVSV",
    essentiality_score: 96.5,
    weed_specificity_score: 88.0,
    crop_divergence_score: 34.2,
    structure_confidence: 91.8,
    druggability_score: 0.89,
    total_opportunity_score: 93.4,
    pockets_json: [
      {
        pocket_id: 1,
        name: "ALS Catalytic Domain Binding Pocket 1",
        center: [12.0, 15.0, 18.0],
        score: 14.5,
        source: "P2Rank Native Binary",
        status: "COMPLETED",
        residues: ["SER", "ASP", "LYS", "TYR", "VAL", "TRP", "MET"]
      },
      {
        pocket_id: 2,
        name: "ALS Allosteric Regulatory Pocket 2",
        center: [-8.4, 22.1, 14.3],
        score: 11.2,
        source: "P2Rank Native Binary",
        status: "COMPLETED",
        residues: ["ILE", "LEU", "ARG", "GLU", "PHE"]
      }
    ]
  },
  {
    id: 102,
    name: "Amaranthus tuberculatus Protoporphyrinogen Oxidase (PPO)",
    uniprot_id: "Q9SW92",
    weed_sequence: "MGVLTETAKSGKVSVYVGAGISGLAAAYRLSKAGMKVTVVEAGSLIGGKLRS",
    crop_sequence: "MGVLTETAKAGKVSVYVGAGISGLAAAYRLSKAGLRVTVVEAGSLIGGKLRS",
    essentiality_score: 94.2,
    weed_specificity_score: 82.5,
    crop_divergence_score: 29.8,
    structure_confidence: 88.6,
    druggability_score: 0.92,
    total_opportunity_score: 89.1,
    pockets_json: [
      {
        pocket_id: 1,
        name: "PPO Active Pocket & FAD Binding Cavity",
        center: [5.2, -10.4, 32.1],
        score: 16.8,
        source: "P2Rank Native Binary",
        status: "COMPLETED",
        residues: ["HIS", "TYR", "LEU", "PHE", "GLY"]
      }
    ]
  },
  {
    id: 103,
    name: "Amaranthus palmeri EPSP Synthase (EPSPS Amplified)",
    uniprot_id: "P0A6D3",
    weed_sequence: "MESLTLQPIARVDGTINLPGSKSVSNRALLLAALAHGKTVLTNLLDSDDVRH",
    crop_sequence: "MESLTLQPIARVDGTINLPGSKSVSNRALLLAALAQGKTVLTNLLDSDDIRH",
    essentiality_score: 98.1,
    weed_specificity_score: 91.4,
    crop_divergence_score: 41.5,
    structure_confidence: 94.2,
    druggability_score: 0.85,
    total_opportunity_score: 95.0,
    pockets_json: [
      {
        pocket_id: 1,
        name: "EPSPS S3P Substrate Recognition Site",
        center: [0.5, 8.2, 11.7],
        score: 18.2,
        source: "P2Rank Native Binary",
        status: "COMPLETED",
        residues: ["LYS", "ARG", "GLU", "ASN", "SER"]
      }
    ]
  }
];

export const fallbackCandidates: Candidate[] = [
  {
    id: 1001,
    project_id: 1,
    compound_code: "MH-ALS-00127",
    smiles: "CC1=C(C(=O)NC(=O)N1)C2=CC=CC=C2S(=O)(=O)NC(=O)NC3=NC(=CC=N3)OC",
    target_name: "Amaranthus palmeri ALS",
    evidence_level: 3,
    boltz_status: "COMPLETED",
    boltz_affinity_score: 9.35,
    boltz_confidence: 89.4,
    gnina_status: "COMPLETED",
    gnina_docking_score: -10.8,
    pose_agreement: "MULTI_MODEL_COMPLETED",
    crop_selectivity_score: 94.2,
    mikherb_score: 95.8,
    status: "COMPLETED"
  },
  {
    id: 1002,
    project_id: 1,
    compound_code: "MH-ALS-00128",
    smiles: "COC1=NC(=NC(=N1)OC)NC(=O)NS(=O)(=O)C2=CC=CC=C2C(=O)OC",
    target_name: "Amaranthus palmeri ALS",
    evidence_level: 3,
    boltz_status: "COMPLETED",
    boltz_affinity_score: 8.92,
    boltz_confidence: 85.1,
    gnina_status: "COMPLETED",
    gnina_docking_score: -9.9,
    pose_agreement: "MULTI_MODEL_COMPLETED",
    crop_selectivity_score: 91.0,
    mikherb_score: 92.4,
    status: "COMPLETED"
  },
  {
    id: 1003,
    project_id: 1,
    compound_code: "MH-ALS-00135",
    smiles: "CC1=NC(=C(C=C1)C(=O)O)C2=NC(=O)NC2(C)C(C)C",
    target_name: "Amaranthus palmeri ALS",
    evidence_level: 2,
    boltz_status: "COMPLETED",
    boltz_affinity_score: 8.45,
    boltz_confidence: 81.2,
    gnina_status: "COMPLETED",
    gnina_docking_score: -9.1,
    pose_agreement: "SINGLE_MODEL_ONLY",
    crop_selectivity_score: 88.5,
    mikherb_score: 89.2,
    status: "COMPLETED"
  },
  {
    id: 1004,
    project_id: 2,
    compound_code: "MH-PPO-00042",
    smiles: "FC(F)(F)C1=CC=C(C=C1)OC2=CC=C(C=C2)C(=O)NC3=CC=C(C=C3)C(=O)O",
    target_name: "Amaranthus tuberculatus PPO",
    evidence_level: 3,
    boltz_status: "COMPLETED",
    boltz_affinity_score: 9.12,
    boltz_confidence: 87.8,
    gnina_status: "COMPLETED",
    gnina_docking_score: -10.4,
    pose_agreement: "MULTI_MODEL_COMPLETED",
    crop_selectivity_score: 92.6,
    mikherb_score: 94.0,
    status: "COMPLETED"
  }
];

export const fallbackFormulation = (input: {
  name: string;
  active_ingredient: string;
  active_concentration_g_l: number;
  solvent: string;
  surfactant: string;
}) => ({
  name: input.name,
  active_ingredient: input.active_ingredient,
  active_concentration_g_l: input.active_concentration_g_l,
  solvent: input.solvent,
  surfactant: input.surfactant,
  ph_predicted: 6.4,
  solubility_risk: "LOW",
  phase_separation_risk: "MINIMAL",
  compatibility_score: 94.5,
  adjuvant_enhancement_ratio: 1.28,
  disclaimer: "Predicted via MikHerb Formulation Intelligence Core (Simulated AI Engine)."
});

export const fallbackAgentResponses: Record<string, string> = {
  default: "I have analyzed your query across target sequences, docking poses, and physicochemical constraints. ALS catalytic inhibition shows high species selectivity against Amaranthus palmeri with minimal crop phytotoxicity on Glycine max.",
  target: "Querying UniProtKB and AlphaFold DB for weed targets: Identified Acetolactate Synthase (ALS) with structure confidence pLDDT 91.8%. Active site residues SER-ASP-LYS verified.",
  docking: "Docking screening executed with GNINA & Boltz-2. Lead compound MH-ALS-00127 demonstrated -10.8 kcal/mol binding affinity and 9.35 pKd with validated pose agreement.",
  formulation: "Formulation assessment: Suspension concentrate (SC) or Emulsifiable concentrate (EC) with Tween 80 surfactant yields optimum foliar penetration and 94.5% stability score."
};
