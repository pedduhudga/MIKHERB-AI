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
        weed_pIC50: float,
        crop_pIC50: float
    ) -> Dict[str, Any]:
        """
        Calculates selectivity fold difference and score from actual dual docking pIC50 predictions.
        Method: Boltz-2 pIC50 Comparison.
        """
        seq_analysis = self.align_sequences(weed_seq, crop_seq)

        # Selectivity fold difference from pIC50 difference:
        # pIC50 = -log10(IC50_M) = 6 - log10(IC50_uM)
        # Higher pIC50 means higher potency (lower IC50).
        # IC50_fold_difference (selectivity towards weed vs crop) = 10 ^ (weed_pIC50 - crop_pIC50)
        pic50_diff = round(weed_pIC50 - crop_pIC50, 3)
        if pic50_diff > 0:
            selectivity_fold = round(10 ** pic50_diff, 1)
        else:
            selectivity_fold = round(1.0 / (10 ** abs(pic50_diff)), 2)

        selectivity_score = min(100.0, max(0.0, 50.0 + (pic50_diff * 25.0)))

        return {
            "method": "Boltz-2 pIC50 Comparison",
            "weed_pIC50": round(weed_pIC50, 2),
            "crop_pIC50": round(crop_pIC50, 2),
            "pIC50_difference": pic50_diff,
            "IC50_fold_difference": selectivity_fold,
            "selectivity_fold_difference": selectivity_fold,
            "selectivity_score": round(selectivity_score, 1),
            "crop_safety_margin": "EXCELLENT" if selectivity_fold >= 10.0 else ("MODERATE" if selectivity_fold >= 3.0 else "POOR"),
            "sequence_alignment": seq_analysis
        }
