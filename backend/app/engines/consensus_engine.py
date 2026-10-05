from typing import Dict, Any, Optional

class MikHerbConsensusScoreEngine:
    """Calculates evidence-aware dynamic MikHerb Consensus Score, renormalizing over available scientific evidence."""

    DEFAULT_WEIGHTS = {
        "target_relevance": 0.10,
        "pocket_confidence": 0.10,
        "boltz_prediction": 0.20,
        "gnina_docking": 0.15,
        "pose_agreement": 0.10,
        "crop_selectivity": 0.15,
        "physicochemical_suitability": 0.10,
        "chemical_novelty": 0.05,
        "safety_environment": 0.05
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS

    def calculate_score(
        self,
        target_relevance: Optional[float] = None,
        pocket_confidence: Optional[float] = None,
        boltz_pKd: Optional[float] = None,
        gnina_cnn_score: Optional[float] = None,
        pose_agreement: Optional[str] = None,
        crop_selectivity_score: Optional[float] = None,
        physicochemical_pass: Optional[bool] = None,
        novelty_score: Optional[float] = None,
        safety_tier: Optional[str] = None,
        safety_evidence_clean: Optional[bool] = None
    ) -> Dict[str, Any]:

        components = {}

        if target_relevance is not None:
            components["target_relevance"] = float(target_relevance)

        if pocket_confidence is not None:
            components["pocket_confidence"] = float(pocket_confidence)

        if boltz_pKd is not None:
            components["boltz_prediction"] = min(100.0, max(0.0, (float(boltz_pKd) - 5.0) * 20.0))

        if gnina_cnn_score is not None:
            components["gnina_docking"] = min(100.0, max(0.0, float(gnina_cnn_score) * 100.0))

        if pose_agreement is not None and pose_agreement not in ["NOT_AVAILABLE", "SINGLE_MODEL_ONLY"]:
            components["pose_agreement"] = 100.0 if pose_agreement == "HIGH" else (60.0 if pose_agreement == "MEDIUM" else 30.0)

        if crop_selectivity_score is not None:
            components["crop_selectivity"] = float(crop_selectivity_score)

        if physicochemical_pass is not None:
            components["physicochemical_suitability"] = 100.0 if physicochemical_pass else 40.0

        if novelty_score is not None:
            components["chemical_novelty"] = float(novelty_score)

        # Explicit safety tier handling (avoids treating predictive screening as verified safety proof)
        if safety_tier is not None and safety_tier not in ["UNKNOWN", "UNKNOWN_REQUIRES_ASSAY"]:
            if safety_tier in ["VALIDATED_SAFETY", "VALIDATED_ASSAY_SAFE"]:
                components["safety_environment"] = 100.0
            elif safety_tier in ["PREDICTIVE_SAFETY", "PREDICTIVE_CLEAN"]:
                components["safety_environment"] = 75.0
            elif safety_tier in ["PREDICTIVE_CONCERN", "HIGH_MOBILITY"]:
                components["safety_environment"] = 35.0
        elif safety_evidence_clean is not None:
            components["safety_environment"] = 100.0 if safety_evidence_clean else 30.0

        if not components:
            return {
                "mikherb_score": 0.0,
                "component_scores": {},
                "status": "NO_EVIDENCE_AVAILABLE"
            }

        # Dynamically renormalize active weights
        active_weight_sum = sum(self.weights.get(k, 0.1) for k in components)
        if active_weight_sum > 0:
            total_score = sum(components[k] * (self.weights.get(k, 0.1) / active_weight_sum) for k in components)
        else:
            total_score = sum(components.values()) / len(components)

        return {
            "mikherb_score": round(total_score, 1),
            "component_scores": components,
            "weights_used": {k: round(self.weights.get(k, 0.1) / active_weight_sum, 3) for k in components},
            "disclaimer": "The MikHerb Score is a hypothesis prioritization metric, not experimental proof."
        }
