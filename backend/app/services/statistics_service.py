import numpy as np
from scipy import stats
from typing import List, Dict, Any

class StatisticalAnalyzer:
    """Calculates Mean, SD, SE, CV (%), and ANOVA p-value for multi-replicate trial data."""

    @staticmethod
    def analyze_replicates(values: List[float]) -> Dict[str, Any]:
        if not values:
            return {"mean": 0.0, "sd": 0.0, "se": 0.0, "cv_pct": 0.0, "n": 0}

        arr = np.array(values, dtype=float)
        n = len(arr)
        mean_val = float(np.mean(arr))
        sd_val = float(np.std(arr, ddof=1)) if n > 1 else 0.0
        se_val = float(sd_val / np.sqrt(n)) if n > 0 else 0.0
        cv_pct = float((sd_val / mean_val) * 100) if mean_val != 0 else 0.0

        return {
            "mean": round(mean_val, 2),
            "sd": round(sd_val, 2),
            "se": round(se_val, 2),
            "cv_pct": round(cv_pct, 2),
            "n": n
        }

    @staticmethod
    def run_anova(groups: List[List[float]]) -> Dict[str, Any]:
        """One-way ANOVA across treatment groups."""
        if len(groups) < 2:
            return {"f_stat": 0.0, "p_value": 1.0, "significant": False}

        valid_groups = [g for g in groups if len(g) > 1]
        if len(valid_groups) < 2:
            return {"f_stat": 0.0, "p_value": 1.0, "significant": False}

        f_stat, p_val = stats.f_oneway(*valid_groups)
        return {
            "f_stat": round(float(f_stat), 3),
            "p_value": round(float(p_val), 4),
            "significant": bool(p_val < 0.05)
        }
