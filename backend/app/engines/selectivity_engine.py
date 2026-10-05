from typing import Dict, Any, List

class CropSelectivityEngine:
    """Evaluates crop selectivity by comparing weed and crop target structures via real dual docking results."""

    @staticmethod
    def align_sequences(weed_seq: str, crop_seq: str) -> Dict[str, Any]:
        min_len = min(len(weed_seq), len(crop_seq))
        matches = sum(1 for i in range(min_len) if weed_seq[i] == crop_seq[i])
        seq_identity = round((matches / max(len(weed_seq), len(crop_seq))) * 100, 1) if max(len(weed_seq), len(crop_seq)) > 0 else 0.0

        divergent_residues = [
            {"position": i + 1, "weed_aa": weed_seq[i], "crop_aa": crop_seq[i]}
            for i in range(min_len) if weed_seq[i] != crop_seq[i]
        ]

        return {
            "sequence_identity_pct": seq_identity,
            "divergent_residues_count": len(divergent_residues),
            "key_pocket_divergences": divergent_residues[:5]
        }

    def evaluate_selectivity(
        self,
        weed_seq: str,
        crop_seq: str,
        weed_affinity_pKd: float,
        crop_affinity_pKd: float
    ) -> Dict[str, Any]:
        """Calculates selectivity fold difference and score from actual dual docking affinity predictions."""
        seq_analysis = self.align_sequences(weed_seq, crop_seq)

        # Selectivity fold = 10 ^ (weed_pKd - crop_pKd)
        kd_diff = weed_affinity_pKd - crop_affinity_pKd
        selectivity_fold = round(10 ** kd_diff, 1) if kd_diff > 0 else round(1.0 / (10 ** abs(kd_diff)), 2)

        selectivity_score = min(100.0, max(0.0, 50.0 + (kd_diff * 25.0)))

        return {
            "weed_affinity_pKd": round(weed_affinity_pKd, 2),
            "crop_affinity_pKd": round(crop_affinity_pKd, 2),
            "selectivity_fold_difference": selectivity_fold,
            "selectivity_score": round(selectivity_score, 1),
            "crop_safety_margin": "EXCELLENT" if selectivity_fold >= 10.0 else ("MODERATE" if selectivity_fold >= 3.0 else "POOR"),
            "sequence_alignment": seq_analysis
        }
