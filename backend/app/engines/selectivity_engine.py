from typing import Dict, Any, List
from app.engines.target_discovery_engine import _align_pairwise_biopython

class CropSelectivityEngine:
    """Evaluates crop selectivity by comparing weed and crop target structures via real dual docking results."""

    @staticmethod
    def align_sequences(weed_seq: str, crop_seq: str) -> Dict[str, Any]:
        """
        Performs true global sequence alignment between weed and crop targets using Biopython
        Needleman-Wunsch dynamic programming. Identifies true insertions, deletions, and substitutions
        without naive positional distortion.
        """
        aln = _align_pairwise_biopython(weed_seq, crop_seq)
        if aln.get("alignment_status") != "COMPLETED":
            return {
                "alignment_method": aln.get("alignment_method") or "Biopython-Needleman-Wunsch-Global",
                "alignment_status": aln.get("alignment_status", "FAILED"),
                "sequence_identity_pct": aln.get("sequence_identity") if aln.get("sequence_identity") is not None else 0.0,
                "divergent_residues_count": 0,
                "divergent_residues": [],
                "key_pocket_divergences": [],
                "aligned_weed": None,
                "aligned_crop": None,
                "bit_score": None
            }

        aligned_weed = aln.get("aligned_weed", "")
        aligned_crop = aln.get("aligned_crop", "")
        seq_identity = aln.get("sequence_identity", 0.0)

        weed_pos = 0
        crop_pos = 0
        divergent_residues = []

        for col_idx, (w_aa, c_aa) in enumerate(zip(aligned_weed, aligned_crop), start=1):
            if w_aa != '-':
                weed_pos += 1
            if c_aa != '-':
                crop_pos += 1

            if w_aa != c_aa:
                if w_aa != '-' and c_aa != '-':
                    div_type = "substitution"
                elif w_aa == '-':
                    div_type = "crop_insertion"
                else:
                    div_type = "crop_deletion"

                divergent_residues.append({
                    "alignment_column": col_idx,
                    "position": weed_pos if w_aa != '-' else crop_pos,
                    "weed_position": weed_pos if w_aa != '-' else None,
                    "crop_position": crop_pos if c_aa != '-' else None,
                    "weed_aa": w_aa,
                    "crop_aa": c_aa,
                    "divergence_type": div_type
                })

        return {
            "alignment_method": "Biopython-Needleman-Wunsch-Global",
            "alignment_status": "COMPLETED",
            "sequence_identity_pct": seq_identity,
            "alignment_coverage_pct": aln.get("alignment_coverage"),
            "alignment_length": aln.get("alignment_length"),
            "divergent_residues_count": len(divergent_residues),
            "divergent_residues": divergent_residues,
            "key_pocket_divergences": divergent_residues[:5],
            "aligned_weed": aligned_weed,
            "aligned_crop": aligned_crop,
            "bit_score": aln.get("bit_score")
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
