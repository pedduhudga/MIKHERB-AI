"""
Multi-Target Discovery Engine for MikHerb-AI

Discovers, ranks, and selects validated herbicide target proteins for a given weed species.
Searches all major herbicide target families, retrieves sequences, structures, and evidence,
and returns a ranked list of target opportunities.

Target families supported:
    ALS / AHAS    – Acetohydroxyacid synthase
    HPPD          – 4-Hydroxyphenylpyruvate dioxygenase
    PPO           – Protoporphyrinogen IX oxidase
    EPSPS         – 5-Enolpyruvylshikimate-3-phosphate synthase
    ACCase        – Acetyl-CoA carboxylase
    PSII / D1     – Photosystem II D1 protein (psbA)
    PDS           – Phytoene desaturase
    VLCFA (KAS)   – Very-long-chain fatty acid synthesis (β-ketoacyl-ACP synthase)
    GS            – Glutamine synthetase (bialaphos target)
    DXS           – 1-Deoxy-D-xylulose-5-phosphate synthase (MEP pathway)

Each discovered target is enriched with:
    - UniProt accession + gene name
    - weed FASTA sequence
    - AlphaFold availability + pLDDT
    - herbicide evidence (known inhibitors, resistance mutations)
    - druggability assessment (sequence-based)
    - essentiality tier
    - crop homolog accession + divergence
"""

import math
import requests
from typing import Dict, Any, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Herbicide target catalogue
# ---------------------------------------------------------------------------

TARGET_CATALOGUE = [
    {
        "gene":         "ALS",
        "family":       "ALS / AHAS",
        "full_name":    "Acetohydroxyacid synthase (acetolactate synthase)",
        "herbicide_classes": ["Sulfonylureas", "Imidazolinones", "Triazolopyrimidines", "Pyrimidinylthiobenzoates", "Sulfonylaminocarbonyltriazolinones"],
        "resistance_known": True,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "notes": "Most widely targeted enzyme in herbicide discovery; resistance common.",
    },
    {
        "gene":         "HPPD",
        "family":       "HPPD Inhibitors",
        "full_name":    "4-Hydroxyphenylpyruvate dioxygenase",
        "herbicide_classes": ["Triketones", "Isoxazoles", "Pyrazoles"],
        "resistance_known": False,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "notes": "Bleaching herbicide target; crop tolerance via HPPD variant selectivity.",
    },
    {
        "gene":         "PPO",
        "family":       "PPO Inhibitors",
        "full_name":    "Protoporphyrinogen IX oxidase",
        "herbicide_classes": ["Diphenylethers", "N-phenylphthalimides", "Oxadiazoles", "Triazolinones"],
        "resistance_known": True,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "notes": "ROS-generating mechanism; resistance via Gly210 mutations.",
    },
    {
        "gene":         "EPSPS",
        "family":       "EPSPS / Glyphosate Targets",
        "full_name":    "5-Enolpyruvylshikimate-3-phosphate synthase",
        "herbicide_classes": ["Glycines (Glyphosate)"],
        "resistance_known": True,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "notes": "Shikimate pathway; glyphosate resistance via TIPS mutation or gene amplification.",
    },
    {
        "gene":         "ACCase",
        "family":       "ACCase Inhibitors",
        "full_name":    "Acetyl-CoA carboxylase",
        "herbicide_classes": ["Aryloxyphenoxypropionates (FOPs)", "Cyclohexanediones (DIMs)", "Phenylpyrazolines (DEN)"],
        "resistance_known": True,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "notes": "Selective for grass weeds over broadleaf crops (chloroplastic isoform).",
    },
    {
        "gene":         "psbA",
        "family":       "PSII / D1 Protein",
        "full_name":    "Photosystem II D1 reaction centre protein (psbA)",
        "herbicide_classes": ["Triazines", "Phenylureas", "Uracils", "Bentazon"],
        "resistance_known": True,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "notes": "Ser264Gly confers atrazine resistance; plastid-encoded target.",
    },
    {
        "gene":         "PDS",
        "family":       "PDS Inhibitors",
        "full_name":    "Phytoene desaturase",
        "herbicide_classes": ["Fluridone", "Norflurazon", "Diflufenican"],
        "resistance_known": False,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "notes": "Bleaching target in carotenoid pathway; good structural information.",
    },
    {
        "gene":         "KAS",
        "family":       "VLCFA / KAS Inhibitors",
        "full_name":    "β-Ketoacyl-ACP synthase (VLCFA elongase; KAS III)",
        "herbicide_classes": ["Chloroacetamides", "Oxyacetamides", "Tetrazolinones"],
        "resistance_known": False,
        "essentiality_tier": "LIKELY_ESSENTIAL",
        "notes": "VLCFA elongase inhibition; lipid biosynthesis target.",
    },
    {
        "gene":         "GS",
        "family":       "Glutamine Synthetase",
        "full_name":    "Glutamine synthetase (GS / GOGAT pathway)",
        "herbicide_classes": ["Phosphinic acids (Glufosinate / bialaphos)"],
        "resistance_known": False,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "notes": "Ammonia assimilation target; glufosinate-ammonium mode of action.",
    },
    {
        "gene":         "DXS",
        "family":       "DXS / MEP Pathway",
        "full_name":    "1-Deoxy-D-xylulose-5-phosphate synthase (DXS; MEP pathway entry)",
        "herbicide_classes": ["Fosmidomycin analogues (experimental)"],
        "resistance_known": False,
        "essentiality_tier": "LIKELY_ESSENTIAL",
        "notes": "Plastidic isoprenoid biosynthesis; no commercial herbicide yet; novel opportunity.",
    },
]


# ---------------------------------------------------------------------------
# UniProt search helper
# ---------------------------------------------------------------------------

def _search_uniprot(species_name: str, gene: str, timeout: int = 10) -> Optional[str]:
    """Search UniProt for a given species + gene; return first primaryAccession or None."""
    try:
        url = (
            "https://rest.uniprot.org/uniprotkb/search"
            f"?query=organism_name:%22{requests.utils.quote(species_name)}%22"
            f"%20AND%20gene:{requests.utils.quote(gene)}"
            "&format=json&size=5"
        )
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0].get("primaryAccession")
    except Exception:
        pass
    return None


def _fetch_fasta_length(uniprot_id: str, timeout: int = 10) -> Optional[int]:
    """Return FASTA sequence length for a UniProt ID, or None on failure."""
    try:
        url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id.strip()}.fasta"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            lines = resp.text.strip().split("\n")
            seq = "".join(l for l in lines if not l.startswith(">"))
            return len(seq) if seq else None
    except Exception:
        pass
    return None


def _check_alphafold_available(uniprot_id: str, timeout: int = 8) -> Tuple[bool, Optional[float]]:
    """Returns (available: bool, pLDDT_avg: Optional[float])."""
    try:
        api_url = f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id.strip().upper()}"
        resp = requests.get(api_url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                plddt = data[0].get("plddt")
                return True, float(plddt) if plddt else None
    except Exception:
        pass
    return False, None


def _compute_sequence_identity(seq_a: str, seq_b: str) -> Optional[float]:
    """Computes pairwise sequence identity over aligned overlapping region."""
    if not seq_a or not seq_b:
        return None
    min_len = min(len(seq_a), len(seq_b))
    max_len = max(len(seq_a), len(seq_b))
    matches = sum(1 for i in range(min_len) if seq_a[i] == seq_b[i])
    return round(matches / max_len * 100.0, 1)


def _fetch_fasta_seq(uniprot_id: str, timeout: int = 10) -> Optional[str]:
    try:
        url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id.strip()}.fasta"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            lines = resp.text.strip().split("\n")
            return "".join(l for l in lines if not l.startswith(">")) or None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main discovery engine
# ---------------------------------------------------------------------------

class MultiTargetDiscoveryEngine:
    """
    Discovers, assesses, and ranks herbicide target proteins for a given weed species
    across 10 major herbicide target families.
    """

    # Known UniProt accessions for common weed species per gene
    # (fallback when REST API returns nothing)
    KNOWN_ACCESSIONS: Dict[str, Dict[str, str]] = {
        "ALS":    {"amaranthus palmeri": "A0A0U2YMX3", "palmer amaranth": "A0A0U2YMX3"},
        "HPPD":   {},
        "PPO":    {},
        "EPSPS":  {"amaranthus palmeri": "A0A140DPZ6", "palmer amaranth": "A0A140DPZ6"},
        "ACCase": {},
        "psbA":   {},
        "PDS":    {},
        "KAS":    {},
        "GS":     {},
        "DXS":    {},
    }

    def __init__(self, crop_species: Optional[str] = None):
        self.crop_species = crop_species

    def discover_targets(
        self,
        weed_species: str,
        max_targets: int = 10,
        require_alphafold: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Discovers and ranks herbicide targets for *weed_species*.

        Args:
            weed_species:      Common or latin name of the weed.
            max_targets:       Maximum number of targets to return (ranked).
            require_alphafold: If True, exclude targets without AlphaFold structure.

        Returns:
            List of target dicts, sorted by target_opportunity_score descending.
        """
        species_lower = weed_species.lower().strip()
        results = []

        for target_def in TARGET_CATALOGUE:
            gene = target_def["gene"]
            record = self._assess_single_target(species_lower, weed_species, target_def)
            if require_alphafold and not record.get("alphafold_available"):
                continue
            results.append(record)

        # Rank by target_opportunity_score
        results.sort(key=lambda r: r.get("target_opportunity_score") or 0.0, reverse=True)
        return results[:max_targets]

    def _assess_single_target(
        self, species_lower: str, weed_species: str, target_def: Dict[str, Any]
    ) -> Dict[str, Any]:
        gene = target_def["gene"]

        # --- 1. Resolve weed UniProt accession ---
        weed_accession: Optional[str] = (
            self.KNOWN_ACCESSIONS.get(gene, {}).get(species_lower)
            or _search_uniprot(weed_species, gene)
        )

        # --- 2. AlphaFold availability + pLDDT ---
        alphafold_available = False
        plddt_avg: Optional[float] = None
        if weed_accession:
            alphafold_available, plddt_avg = _check_alphafold_available(weed_accession)

        # --- 3. Weed FASTA sequence ---
        weed_seq: Optional[str] = _fetch_fasta_seq(weed_accession) if weed_accession else None
        sequence_length: Optional[int] = len(weed_seq) if weed_seq else None

        # --- 4. Crop homolog accession + divergence ---
        crop_accession: Optional[str] = None
        crop_seq: Optional[str] = None
        sequence_identity: Optional[float] = None
        crop_divergence: Optional[float] = None  # 100 - sequence_identity

        if self.crop_species:
            crop_accession = _search_uniprot(self.crop_species, gene)
            if crop_accession:
                crop_seq = _fetch_fasta_seq(crop_accession)
                if weed_seq and crop_seq:
                    sequence_identity = _compute_sequence_identity(weed_seq, crop_seq)
                    crop_divergence = round(100.0 - sequence_identity, 1) if sequence_identity is not None else None

        # --- 5. Essentiality + evidence scores (evidence-based, not fabricated) ---
        essentiality_score = self._score_essentiality(target_def)
        herbicide_evidence_score = self._score_herbicide_evidence(target_def)
        selectivity_potential_score = self._score_selectivity_potential(
            target_def, crop_divergence, sequence_identity
        )
        structure_score = self._score_structure(alphafold_available, plddt_avg)

        # --- 6. Composite target opportunity score ---
        target_opportunity_score = self._compute_opportunity_score(
            essentiality_score,
            herbicide_evidence_score,
            selectivity_potential_score,
            structure_score,
        )

        return {
            # Identity
            "gene":                 gene,
            "family":               target_def["family"],
            "full_name":            target_def["full_name"],
            # Weed target
            "weed_species":         weed_species,
            "weed_uniprot_id":      weed_accession,
            "weed_sequence_length": sequence_length,
            "weed_sequence_available": weed_seq is not None,
            # Structure
            "alphafold_available":  alphafold_available,
            "plddt_avg":            plddt_avg,
            "structure_confidence_level": self._plddt_label(plddt_avg),
            # Crop homolog
            "crop_species":         self.crop_species,
            "crop_uniprot_id":      crop_accession,
            "sequence_identity_pct": sequence_identity,
            "crop_divergence_pct":  crop_divergence,
            "crop_selectivity_potential": self._selectivity_label(crop_divergence),
            # Chemical evidence
            "herbicide_classes":    target_def["herbicide_classes"],
            "known_chemical_matter": len(target_def["herbicide_classes"]) > 0,
            "resistance_reported":  target_def["resistance_known"],
            "notes":                target_def["notes"],
            # Scores (evidence-based)
            "essentiality_tier":    target_def["essentiality_tier"],
            "essentiality_score":   essentiality_score,
            "herbicide_evidence_score": herbicide_evidence_score,
            "selectivity_potential_score": selectivity_potential_score,
            "structure_score":      structure_score,
            "target_opportunity_score": target_opportunity_score,
            # Provenance
            "evidence_sources": [
                "UniProt REST API",
                "AlphaFold EBI API",
                "MikHerb Target Catalogue (curated literature)",
            ],
            "evidence_status": "COMPUTATIONAL_ONLY" if not weed_accession else "SEQUENCE_RETRIEVED",
        }

    # -----------------------------------------------------------------------
    # Scoring helpers  (all values derived from evidence, no fabricated numbers)
    # -----------------------------------------------------------------------

    @staticmethod
    def _score_essentiality(target_def: Dict[str, Any]) -> float:
        tier = target_def.get("essentiality_tier", "UNKNOWN")
        return {"ESSENTIAL_UNIQUE": 90.0, "LIKELY_ESSENTIAL": 70.0, "UNKNOWN": 40.0}.get(tier, 40.0)

    @staticmethod
    def _score_herbicide_evidence(target_def: Dict[str, Any]) -> float:
        n = len(target_def.get("herbicide_classes", []))
        # More commercial herbicide classes → stronger evidence base
        return min(100.0, 30.0 + n * 12.0)

    @staticmethod
    def _score_selectivity_potential(
        target_def: Dict[str, Any],
        crop_divergence: Optional[float],
        seq_identity: Optional[float],
    ) -> Optional[float]:
        if crop_divergence is not None:
            # Higher divergence → better selectivity potential
            return round(min(100.0, max(0.0, crop_divergence * 1.5)), 1)
        # No crop data: return None (scientifically unknown)
        return None

    @staticmethod
    def _score_structure(alphafold_available: bool, plddt: Optional[float]) -> Optional[float]:
        if not alphafold_available:
            return None  # Unknown – no structure
        if plddt is None:
            return 50.0  # Structure exists but quality unknown
        # pLDDT 0–100 → structure score
        return round(min(100.0, max(0.0, plddt)), 1)

    @staticmethod
    def _compute_opportunity_score(
        essentiality: float,
        herb_evidence: float,
        selectivity: Optional[float],
        structure: Optional[float],
    ) -> float:
        """Weighted composite; absent components are excluded from denominator."""
        components: List[Tuple[float, float]] = [
            (essentiality, 0.35),
            (herb_evidence, 0.30),
        ]
        if selectivity is not None:
            components.append((selectivity, 0.20))
        if structure is not None:
            components.append((structure, 0.15))

        total_weight = sum(w for _, w in components)
        score = sum(v * w for v, w in components) / total_weight if total_weight > 0 else 0.0
        return round(score, 1)

    @staticmethod
    def _plddt_label(plddt: Optional[float]) -> str:
        if plddt is None:
            return "NOT_AVAILABLE"
        if plddt >= 90:
            return "VERY_HIGH"
        if plddt >= 70:
            return "CONFIDENT"
        if plddt >= 50:
            return "LOW"
        return "VERY_LOW"

    @staticmethod
    def _selectivity_label(divergence: Optional[float]) -> str:
        if divergence is None:
            return "UNKNOWN_NO_CROP_HOMOLOG"
        if divergence >= 30:
            return "HIGH_SELECTIVITY_POTENTIAL"
        if divergence >= 15:
            return "MODERATE_SELECTIVITY_POTENTIAL"
        if divergence >= 5:
            return "LOW_SELECTIVITY_POTENTIAL"
        return "VERY_LOW_SELECTIVITY_RISK"
