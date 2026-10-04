from typing import Dict, Any, Optional

class MikHerbConsensusScoreEngine:
    """Calculates the multi-factor MikHerb Consensus Score combining all scientific evidence with configurable weights."""

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
        target_relevance: float = 80.0,       # 0-100
        pocket_confidence: float = 90.0,      # 0-100
        boltz_pKd: float = 8.0,               # e.g., 6.0 to 10.0 -> mapped to 0-100
        gnina_cnn_score: float = 0.85,        # 0.0 to 1.0 -> mapped to 0-100
        pose_agreement: str = "HIGH",         # HIGH=100, MEDIUM=60, LOW=20
        crop_selectivity_score: float = 85.0, # 0-100
        physicochemical_pass: bool = True,    # True=100, False=40
        novelty_score: float = 80.0,          # 0-100
        safety_evidence_clean: bool = True    # True=100, False=30
    ) -> Dict[str, Any]:

        # Normalize component scores to 0 - 100
        norm_boltz = min(100.0, max(0.0, (boltz_pKd - 5.0) * 20.0))
        norm_gnina = min(100.0, max(0.0, gnina_cnn_score * 100.0))
        norm_pose = 100.0 if pose_agreement == "HIGH" else (60.0 if pose_agreement == "MEDIUM" else 20.0)
        norm_physchem = 100.0 if physicochemical_pass else 40.0
        norm_safety = 100.0 if safety_evidence_clean else 30.0

        components = {
            "target_relevance": target_relevance,
            "pocket_confidence": pocket_confidence,
            "boltz_prediction": norm_boltz,
            "gnina_docking": norm_gnina,
            "pose_agreement": norm_pose,
            "crop_selectivity": crop_selectivity_score,
            "physicochemical_suitability": norm_physchem,
            "chemical_novelty": novelty_score,
            "safety_environment": norm_safety
        }

        total_score = sum(components[k] * self.weights.get(k, 0.1) for k in components)

        return {
            "mikherb_score": round(total_score, 1),
            "component_scores": components,
            "weights_used": self.weights,
            "disclaimer": "The MikHerb Score is a hypothesis prioritization metric, not experimental proof."
        }
