from typing import Dict, Any, List, Optional
from app.engines.base import BaseScientificEngine

class CropSelectivityEngine(BaseScientificEngine):
    """Evaluates crop selectivity by comparing weed and crop homologs at sequence, structure, pocket, and binding levels."""

    def __init__(self):
        super().__init__(name="Crop Selectivity Engine", category="selectivity")

    @staticmethod
    def align_sequences(weed_seq: str, crop_seq: str) -> Dict[str, Any]:
        """Perform pairwise sequence alignment to identify divergent amino acid residues."""
        if not weed_seq or not crop_seq:
            return {"sequence_identity_pct": 0.0, "divergent_residues_count": 0, "key_pocket_divergences": []}

        min_len = min(len(weed_seq), len(crop_seq))
        max_len = max(len(weed_seq), len(crop_seq))
        matches = sum(1 for i in range(min_len) if weed_seq[i] == crop_seq[i])
        seq_identity = round((matches / max_len) * 100, 1)

        divergent_residues = [
            {"position": i + 1, "weed_aa": weed_seq[i], "crop_aa": crop_seq[i]}
            for i in range(min_len) if weed_seq[i] != crop_seq[i]
        ]

        return {
            "sequence_identity_pct": seq_identity,
            "alignment_length": max_len,
            "identical_residues_count": matches,
            "divergent_residues_count": len(divergent_residues),
            "key_pocket_divergences": divergent_residues[:10]
        }

    @staticmethod
    def compare_binding_pocket(weed_pockets: List[Dict], crop_pockets: List[Dict]) -> Dict[str, Any]:
        """Compare structural geometry and volume difference between weed and crop pockets."""
        if not weed_pockets or not crop_pockets:
            return {"pocket_rmsd_A": 1.5, "pocket_divergence_level": "UNKNOWN", "crop_pocket_volume_diff_pct": 0.0}

        w_p1 = weed_pockets[0]
        c_p1 = crop_pockets[0]

        w_vol = w_p1.get("volume_A3", 750.0)
        c_vol = c_p1.get("volume_A3", 750.0)
        vol_diff_pct = round(((c_vol - w_vol) / w_vol) * 100.0, 1) if w_vol > 0 else 0.0

        # Calculate coordinate RMSD between pocket centers
        w_center = w_p1.get("center", [0, 0, 0])
        c_center = c_p1.get("center", [0, 0, 0])
        dx = w_center[0] - c_center[0]
        dy = w_center[1] - c_center[1]
        dz = w_center[2] - c_center[2]
        pocket_rmsd = round((dx*dx + dy*dy + dz*dz)**0.5, 2)

        divergence_level = "HIGH" if pocket_rmsd > 1.5 or abs(vol_diff_pct) > 10.0 else "LOW"

        return {
            "pocket_rmsd_A": pocket_rmsd,
            "pocket_divergence_level": divergence_level,
            "crop_pocket_volume_diff_pct": vol_diff_pct
        }

    def evaluate_selectivity(
        self,
        weed_seq: str,
        crop_seq: str,
        weed_affinity_pKd: Optional[float] = None,
        crop_affinity_pKd: Optional[float] = None,
        weed_pockets: Optional[List[Dict]] = None,
        crop_pockets: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        seq_analysis = self.align_sequences(weed_seq, crop_seq)
        pocket_analysis = self.compare_binding_pocket(weed_pockets or [], crop_pockets or [])

        # If affinities are available, calculate affinity fold difference
        if weed_affinity_pKd is not None and crop_affinity_pKd is not None:
            kd_diff = weed_affinity_pKd - crop_affinity_pKd
            selectivity_fold = round(10 ** kd_diff, 1) if kd_diff > 0 else round(1.0 / (10 ** abs(kd_diff)), 2)
            affinity_selectivity_score = min(100.0, max(0.0, 50.0 + (kd_diff * 25.0)))
        else:
            # Estimate structural divergence score when affinity metrics are not present
            divergence_count = seq_analysis["divergent_residues_count"]
            seq_id = seq_analysis["sequence_identity_pct"]
            affinity_selectivity_score = min(100.0, max(30.0, 100.0 - seq_id + (divergence_count * 0.5)))
            selectivity_fold = 1.0

        safety_margin = (
            "EXCELLENT" if selectivity_fold >= 10.0 or affinity_selectivity_score >= 80.0
            else ("MODERATE" if selectivity_fold >= 3.0 or affinity_selectivity_score >= 60.0 else "POOR")
        )

        return {
            "weed_affinity_pKd": weed_affinity_pKd,
            "crop_affinity_pKd": crop_affinity_pKd,
            "selectivity_fold_difference": selectivity_fold,
            "selectivity_score": round(affinity_selectivity_score, 1),
            "crop_safety_margin": safety_margin,
            "sequence_alignment": seq_analysis,
            "pocket_comparison": pocket_analysis
        }
