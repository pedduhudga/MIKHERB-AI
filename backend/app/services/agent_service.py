from typing import Dict, Any, List
from app.engines.protein_engine import ProteinEngine
from app.engines.chemical_engine import ChemicalEngine
from app.engines.docking_engine import AIDockingEngine
from app.engines.selectivity_engine import CropSelectivityEngine
from app.engines.formulation_engine import FormulationEngine
from app.engines.consensus_engine import MikHerbConsensusScoreEngine
from app.engines.status_manager import engine_status_manager

class AIResearchAgent:
    """AI Research Agent executing scientific tools with strict non-fabrication guardrails and input requirements."""

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
            uniprot_id = context.get("uniprot_id")
            if not uniprot_id:
                return {
                    "agent_response": "REQUIRED_INPUT_MISSING: Please specify a valid UniProt accession ID (e.g., P10324) for target protein analysis.",
                    "tool_executed": "protein_analysis",
                    "status": "INPUT_REQUIRED"
                }
            try:
                data = self.protein_engine.get_protein_info(uniprot_id)
                return {
                    "agent_response": f"Retrieved structure & pocket analysis for target protein {data['name']} (UniProt: {uniprot_id}). Found {len(data['pockets'])} druggable binding pockets.",
                    "tool_executed": "protein_analysis",
                    "output_data": data,
                    "status": "COMPLETED"
                }
            except Exception as e:
                return {
                    "agent_response": f"Protein analysis failed for UniProt ID '{uniprot_id}': {e}",
                    "tool_executed": "protein_analysis",
                    "status": "FAILED"
                }

        elif "smiles" in q_lower or "chemical" in q_lower or "rdkit" in q_lower:
            smiles = context.get("smiles")
            if not smiles:
                return {
                    "agent_response": "REQUIRED_INPUT_MISSING: Please provide a valid chemical SMILES string (e.g., CC(=O)Oc1ccccc1C(=O)O) for RDKit analysis.",
                    "tool_executed": "rdkit_filter",
                    "status": "INPUT_REQUIRED"
                }
            desc = self.chemical_engine.calculate_descriptors(smiles)
            if not desc:
                return {
                    "agent_response": f"RDKit analysis failed: Invalid SMILES string '{smiles}'.",
                    "tool_executed": "rdkit_filter",
                    "status": "FAILED"
                }
            return {
                "agent_response": f"Executed RDKit analysis for compound SMILES `{smiles}`. MW = {desc['mw']} g/mol, LogP = {desc['logp']}, Lipinski Pass: {desc['lipinski_pass']}.",
                "tool_executed": "rdkit_filter",
                "output_data": desc,
                "status": "COMPLETED"
            }

        elif "dock" in q_lower or "boltz" in q_lower or "screen" in q_lower:
            uniprot_id = context.get("uniprot_id")
            smiles = context.get("smiles")
            if not uniprot_id or not smiles:
                return {
                    "agent_response": "REQUIRED_INPUT_MISSING: Docking requires both a target UniProt ID and a compound SMILES string.",
                    "tool_executed": "boltz_and_gnina",
                    "status": "INPUT_REQUIRED"
                }

            gnina_installed = engine_status_manager.engines["gnina"].is_installed()
            boltz_installed = engine_status_manager.engines["boltz"].is_installed()

            if not gnina_installed and not boltz_installed:
                return {
                    "agent_response": "Docking NOT AVAILABLE: Native GNINA and Boltz-2 engines are not installed in local environment.",
                    "tool_executed": "boltz_and_gnina",
                    "status": "NOT_AVAILABLE"
                }

            try:
                protein_data = self.protein_engine.get_protein_info(uniprot_id)
                pdb_path = protein_data["pdb_path"]
                pockets = protein_data.get("pockets", [])
                native_pocket = pockets[0] if (pockets and pockets[0].get("status") == "COMPLETED") else None
                if not native_pocket or not native_pocket.get("center"):
                    return {
                        "agent_response": f"Docking NOT AVAILABLE: Native P2Rank pocket prediction missing for target protein {uniprot_id}.",
                        "tool_executed": "boltz_and_gnina",
                        "status": "P2RANK_POCKET_ENGINE_NOT_INSTALLED"
                    }

                pocket_center = native_pocket["center"]
                res = self.docking_engine.screen_candidate(
                    pdb_path, smiles, pocket_center, protein_sequence=protein_data.get("sequence")
                )

                b_status = res["boltz"].get("status") == "COMPLETED"
                g_status = res["gnina"].get("status") == "COMPLETED"

                if b_status and g_status:
                    overall_status = "COMPLETED"
                elif b_status or g_status:
                    overall_status = "PARTIAL"
                else:
                    overall_status = "NOT_AVAILABLE"

                return {
                    "agent_response": f"Screening run (Status: {overall_status}). Boltz pKd: {res['boltz'].get('pKd_predicted') or 'NOT_INSTALLED'}, GNINA Affinity: {res['gnina'].get('affinity_kcal_mol') or 'NOT_INSTALLED'} kcal/mol.",
                    "tool_executed": "boltz_and_gnina",
                    "output_data": res,
                    "status": overall_status
                }
            except Exception as e:
                return {
                    "agent_response": f"Docking screening failed: {e}",
                    "tool_executed": "boltz_and_gnina",
                    "status": "FAILED"
                }

        elif "formulation" in q_lower or "compatibility" in q_lower:
            res = self.formulation_engine.analyze_formulation("Active-Herbicide-1", 120.0, "Water", "Tween 80", acid_base_buffer="Citrate Buffer")
            return {
                "agent_response": f"Formulation analysis completed. Compatibility score: {res['compatibility_score']}/100. Predicted pH: {res['predicted_ph']}.",
                "tool_executed": "formulation",
                "output_data": res,
                "status": "COMPLETED"
            }

        else:
            score_res = self.consensus_engine.calculate_score()
            return {
                "agent_response": "MIKHERB AI Agent active. Ready for target analysis, chemical library screening, or docking commands.",
                "tool_executed": "consensus_score",
                "output_data": score_res,
                "status": "READY"
            }
