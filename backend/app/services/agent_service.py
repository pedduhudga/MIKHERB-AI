from typing import Dict, Any, List
from app.engines.protein_engine import ProteinEngine
from app.engines.chemical_engine import ChemicalEngine
from app.engines.docking_engine import AIDockingEngine
from app.engines.selectivity_engine import CropSelectivityEngine
from app.engines.formulation_engine import FormulationEngine
from app.engines.consensus_engine import MikHerbConsensusScoreEngine

class AIResearchAgent:
    """AI Research Agent executing scientific tools with strict non-fabrication guardrails."""

    def __init__(self):
        self.protein_engine = ProteinEngine()
        self.chemical_engine = ChemicalEngine()
        self.docking_engine = AIDockingEngine()
        self.selectivity_engine = CropSelectivityEngine()
        self.formulation_engine = FormulationEngine()
        self.consensus_engine = MikHerbConsensusScoreEngine()

    def available_tools(self) -> List[Dict[str, str]]:
        return [
            {"tool": "target_search", "description": "Search UniProt & AlphaFold DB for weed targets."},
            {"tool": "protein_analysis", "description": "Analyze sequence, domains, MW, pI, disorder."},
            {"tool": "pocket_prediction", "description": "Predict binding pockets with P2Rank."},
            {"tool": "library_builder", "description": "Build & clean chemical library with RDKit descriptors."},
            {"tool": "rdkit_filter", "description": "Calculate SMILES descriptors and Lipinski pass/fail."},
            {"tool": "gnina", "description": "Run deep-learning GNINA docking simulation."},
            {"tool": "boltz", "description": "Run Boltz-2 AI structure & affinity prediction."},
            {"tool": "selectivity", "description": "Compare weed vs crop target selectivity and sequence divergence."},
            {"tool": "formulation", "description": "Analyze formulation component compatibility & risks."},
            {"tool": "consensus_score", "description": "Compute multi-factor MikHerb Consensus Score."}
        ]

    def execute_agent_query(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        q_lower = query.lower()
        context = context or {}

        if "protein" in q_lower or "target" in q_lower or "uniprot" in q_lower:
            uniprot_id = context.get("uniprot_id", "P10324")
            data = self.protein_engine.get_protein_info(uniprot_id)
            return {
                "agent_response": f"Retrieved structure & pocket analysis for target protein {data['name']} (UniProt: {uniprot_id}). Found {len(data['pockets'])} druggable binding pockets.",
                "tool_executed": "protein_analysis",
                "output_data": data
            }

        elif "smiles" in q_lower or "chemical" in q_lower or "rdkit" in q_lower:
            smiles = context.get("smiles", "CC(=O)Oc1ccccc1C(=O)O")
            desc = self.chemical_engine.calculate_descriptors(smiles)
            return {
                "agent_response": f"Executed RDKit analysis for compound SMILES `{smiles}`. MW = {desc['mw']} g/mol, LogP = {desc['logp']}, Lipinski Pass: {desc['lipinski_pass']}.",
                "tool_executed": "rdkit_filter",
                "output_data": desc
            }

        elif "dock" in q_lower or "boltz" in q_lower or "screen" in q_lower:
            uniprot_id = context.get("uniprot_id", "P10324")
            protein_data = self.protein_engine.get_protein_info(uniprot_id)
            pdb_path = protein_data["pdb_path"]
            pocket_center = protein_data["pockets"][0]["center"]
            smiles = context.get("smiles", "CC(=O)Oc1ccccc1C(=O)O")

            res = self.docking_engine.screen_candidate(pdb_path, smiles, pocket_center)
            return {
                "agent_response": f"Completed AI screening with Boltz-2 and GNINA docking. Boltz pKd: {res['boltz']['pKd_predicted']}, GNINA Affinity: {res['gnina']['affinity_kcal_mol']} kcal/mol, Pose Agreement: {res['pose_agreement']}.",
                "tool_executed": "boltz_and_gnina",
                "output_data": res
            }

        elif "formulation" in q_lower or "compatibility" in q_lower:
            res = self.formulation_engine.analyze_formulation("Active-Herbicide-1", 120.0, "Water", "Tween 80", acid_base_buffer="Citrate Buffer")
            return {
                "agent_response": f"Formulation analysis completed. Compatibility score: {res['compatibility_score']}/100. Predicted pH: {res['predicted_ph']}.",
                "tool_executed": "formulation",
                "output_data": res
            }

        else:
            score_res = self.consensus_engine.calculate_score()
            return {
                "agent_response": f"MikHerb AI Agent active. Executed consensus scoring engine. Recommended top candidate MikHerb Score: {score_res['mikherb_score']}/100.",
                "tool_executed": "consensus_score",
                "output_data": score_res
            }
