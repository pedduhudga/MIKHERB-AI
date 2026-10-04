from typing import Dict, Any, List

class FormulationEngine:
    """Evaluates formulation compatibility, pH, solubility, phase separation, and crystallization risks."""

    @staticmethod
    def analyze_formulation(
        active_ingredient: str,
        concentration_g_l: float,
        solvent: str,
        surfactant: str,
        adjuvant: str = None,
        acid_base_buffer: str = None
    ) -> Dict[str, Any]:
        risk_flags = []

        # pH estimation
        ph_est = 6.5
        if acid_base_buffer:
            if "citrate" in acid_base_buffer.lower() or "acid" in acid_base_buffer.lower():
                ph_est = 4.8
            elif "amine" in acid_base_buffer.lower() or "ammonia" in acid_base_buffer.lower():
                ph_est = 8.2

        # Solubility & precipitation check
        solubility_risk = "LOW"
        if concentration_g_l > 250.0 and solvent.lower() == "water":
            solubility_risk = "HIGH"
            risk_flags.append("High active concentration in aqueous solvent may cause active crystallization at lower temperatures.")
        elif concentration_g_l > 150.0 and solvent.lower() == "water":
            solubility_risk = "MEDIUM"
            risk_flags.append("Moderate solubility risk; recommend adding cosolvent or anti-crystallization polymer.")

        # Phase separation risk
        phase_risk = "LOW"
        if "oil" in solvent.lower() and "water" in surfactant.lower():
            phase_risk = "MEDIUM"
            risk_flags.append("Emulsion system detected; ensure proper HLB balance to prevent phase separation.")

        # Compatibility score
        comp_score = 100.0 - (len(risk_flags) * 15.0)
        comp_score = max(30.0, min(100.0, comp_score))

        return {
            "predicted_ph": ph_est,
            "solubility_risk": solubility_risk,
            "precipitation_risk": solubility_risk,
            "phase_separation_risk": phase_risk,
            "compatibility_score": round(comp_score, 1),
            "risk_flags": risk_flags,
            "disclaimer": "IMPORTANT: All formulation compatibility outputs are computational predictions requiring physical laboratory validation."
        }
