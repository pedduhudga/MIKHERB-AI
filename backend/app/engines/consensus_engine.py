from typing import Dict, Any, Optional
from app.engines.base import BaseScientificEngine

class MikHerbConsensusScoreEngine(BaseScientificEngine):
    """Calculates the multi-factor MikHerb Consensus Score combining all scientific evidence with configurable weights."""

    DEFAULT_WEIGHTS = {
        "target_relevance": 0.15,
        "pocket_confidence": 0.15,
        "boltz_prediction": 0.20,
        "gnina_docking": 0.15,
        "pose_agreement": 0.05,
        "crop_selectivity": 0.15,
        "physicochemical_suitability": 0.10,
        "chemical_novelty": 0.05
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        super().__init__(name="MikHerb Consensus Score Engine", category="consensus_ranking")
        self.weights = weights or self.DEFAULT_WEIGHTS

    def calculate_score(
        self,
        target_relevance: float = 80.0,                 # 0-100
        pocket_confidence: float = 90.0,                # 0-100
        boltz_pKd: Optional[float] = None,              # e.g. 6.0-10.0 or None if uninstalled
        gnina_cnn_score: Optional[float] = None,        # 0.0-1.0 or None if uninstalled
        pose_agreement: str = "NOT_EVALUATED",          # HIGH=100, MEDIUM=60, LOW=20, NOT_EVALUATED=50
        crop_selectivity_score: float = 75.0,           # 0-100
        physicochemical_pass: bool = True,              # True=100, False=40
        novelty_score: float = 80.0,                    # 0-100
        safety_evidence_clean: bool = True              # True=100, False=30
    ) -> Dict[str, Any]:

        active_components = {}
        active_weights = {}

        # Target & Pocket
        active_components["target_relevance"] = min(100.0, max(0.0, target_relevance))
        active_weights["target_relevance"] = self.weights.get("target_relevance", 0.15)

        active_components["pocket_confidence"] = min(100.0, max(0.0, pocket_confidence))
        active_weights["pocket_confidence"] = self.weights.get("pocket_confidence", 0.15)

        # AI Docking / Affinity (Only include when installed/computed)
        if boltz_pKd is not None:
            norm_boltz = min(100.0, max(0.0, (boltz_pKd - 5.0) * 20.0))
            active_components["boltz_prediction"] = norm_boltz
            active_weights["boltz_prediction"] = self.weights.get("boltz_prediction", 0.20)

        if gnina_cnn_score is not None:
            norm_gnina = min(100.0, max(0.0, gnina_cnn_score * 100.0))
            active_components["gnina_docking"] = norm_gnina
            active_weights["gnina_docking"] = self.weights.get("gnina_docking", 0.15)

        if pose_agreement in ["HIGH", "MEDIUM", "LOW"]:
            norm_pose = 100.0 if pose_agreement == "HIGH" else (60.0 if pose_agreement == "MEDIUM" else 20.0)
            active_components["pose_agreement"] = norm_pose
            active_weights["pose_agreement"] = self.weights.get("pose_agreement", 0.05)

        # Crop Selectivity
        active_components["crop_selectivity"] = min(100.0, max(0.0, crop_selectivity_score))
        active_weights["crop_selectivity"] = self.weights.get("crop_selectivity", 0.15)

        # Physicochemical
        active_components["physicochemical_suitability"] = 100.0 if physicochemical_pass else 40.0
        active_weights["physicochemical_suitability"] = self.weights.get("physicochemical_suitability", 0.10)

        # Chemical Novelty
        active_components["chemical_novelty"] = min(100.0, max(0.0, novelty_score))
        active_weights["chemical_novelty"] = self.weights.get("chemical_novelty", 0.05)

        # Normalize weights so sum of active_weights equals 1.0
        weight_sum = sum(active_weights.values())
        if weight_sum > 0:
            norm_weights = {k: v / weight_sum for k, v in active_weights.items()}
        else:
            norm_weights = {k: 1.0 / len(active_components) for k in active_components}

        total_score = sum(active_components[k] * norm_weights[k] for k in active_components)

        evidence_level = 1 if (boltz_pKd is not None and gnina_cnn_score is not None) else 0

        return {
            "mikherb_score": round(total_score, 1),
            "evidence_level": evidence_level,
            "evidence_level_label": "Evidence Level 1 — Multi-Model AI Agreement" if evidence_level == 1 else "Evidence Level 0 — Pure Computational Hypothesis",
            "component_scores": active_components,
            "normalized_weights": {k: round(v, 3) for k, v in norm_weights.items()},
            "disclaimer": "The MikHerb Score is a hypothesis prioritization metric, not experimental proof."
        }
