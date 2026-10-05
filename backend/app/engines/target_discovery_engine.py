"""
Multi-Target Discovery Engine for MikHerb-AI (Evidence Integrity v6 + Target Ranking v2)

Discovers, ranks, and assesses validated herbicide target proteins across 10 major families:
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

Key scientific integrity enhancements:
    1. Distinguishes essentiality_status, essentiality_evidence, essentiality_source,
       and essentiality_score. Essentiality score is only derived when weed evidence exists.
    2. True Biopython global pairwise alignment (Needleman-Wunsch mode).
       Records sequence_identity, alignment_coverage, alignment_method, bit_score, and e_value.
    3. Fully curated UniProt accession provenance registry with active status verification.
    4. Explicit separation of target_evidence_score (empirical evidence strength)
       and target_opportunity_score (actionable discovery potential).
    5. Zero score fabrication when evidence is absent (preserved as None).
"""

import math
import re
import requests
from typing import Dict, Any, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Biopython Pairwise Alignment & Sequence Metrics
# ---------------------------------------------------------------------------

def _align_pairwise_biopython(seq_a: str, seq_b: str) -> Dict[str, Any]:
    """
    Performs true global pairwise sequence alignment between seq_a (weed) and seq_b (crop)
    using Biopython Bio.Align.PairwiseAligner (Needleman-Wunsch algorithm).
    
    Returns:
        alignment_status: "COMPLETED" or "FAILED"
        sequence_identity: percentage of identical residues across aligned columns
        alignment_coverage: percentage of weed sequence covered by aligned residues
        weed_coverage: percentage of weed sequence covered by non-gap aligned residues
        crop_coverage: percentage of crop sequence covered by non-gap aligned residues
        identity_over_aligned_positions: identity over paired non-gap columns
        alignment_length: total length of aligned sequences including gaps
        alignment_method: "Biopython-Needleman-Wunsch-Global"
        bit_score: raw alignment score from scoring matrix
        e_value: None (deterministic global dynamic programming)
        aligned_weed: aligned string with gaps
        aligned_crop: aligned string with gaps
    """
    if not seq_a or not seq_b:
        return {
            "alignment_status": "NOT_ATTEMPTED",
            "sequence_identity": None,
            "alignment_coverage": None,
            "weed_coverage": None,
            "crop_coverage": None,
            "identity_over_aligned_positions": None,
            "alignment_length": None,
            "alignment_method": None,
            "bit_score": None,
            "e_value": None,
            "aligned_weed": None,
            "aligned_crop": None,
        }

    try:
        from Bio import Align
        aligner = Align.PairwiseAligner()
        aligner.mode = 'global'
        aligner.open_gap_score = -10.0
        aligner.extend_gap_score = -0.5
        aligner.match_score = 1.0
        aligner.mismatch_score = 0.0

        alignments = aligner.align(seq_a.strip().upper(), seq_b.strip().upper())
        best = alignments[0]
        aligned_a, aligned_b = str(best[0]), str(best[1])

        aligned_pairs = sum(1 for a, b in zip(aligned_a, aligned_b) if a != '-' and b != '-')
        matches = sum(1 for a, b in zip(aligned_a, aligned_b) if a == b and a != '-' and b != '-')
        aligned_non_gap_a = sum(1 for a in aligned_a if a != '-')
        aligned_non_gap_b = sum(1 for b in aligned_b if b != '-')
        max_len = max(len(seq_a), len(seq_b))
        aln_len = len(aligned_a)

        identity_pct = round((matches / max_len) * 100.0, 1) if max_len > 0 else 0.0
        id_over_aligned_pct = round((matches / aligned_pairs) * 100.0, 1) if aligned_pairs > 0 else 0.0
        weed_coverage_pct = round((aligned_non_gap_a / len(seq_a)) * 100.0, 1) if len(seq_a) > 0 else 0.0
        crop_coverage_pct = round((aligned_non_gap_b / len(seq_b)) * 100.0, 1) if len(seq_b) > 0 else 0.0

        return {
            "alignment_status": "COMPLETED",
            "sequence_identity": identity_pct,
            "alignment_coverage": weed_coverage_pct,
            "weed_coverage": weed_coverage_pct,
            "crop_coverage": crop_coverage_pct,
            "identity_over_aligned_positions": id_over_aligned_pct,
            "alignment_length": aln_len,
            "alignment_method": "Biopython-Needleman-Wunsch-Global",
            "bit_score": round(float(best.score), 2),
            "e_value": None,
            "aligned_weed": aligned_a,
            "aligned_crop": aligned_b,
        }
    except Exception:
        # Strictly preserve scientific failure: never substitute a positional fallback score
        return {
            "alignment_status": "FAILED",
            "sequence_identity": None,
            "alignment_coverage": None,
            "weed_coverage": None,
            "crop_coverage": None,
            "identity_over_aligned_positions": None,
            "alignment_length": None,
            "alignment_method": None,
            "bit_score": None,
            "e_value": None,
            "aligned_weed": None,
            "aligned_crop": None,
        }


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
        "essentiality_status": "ESSENTIAL_KNOWN",
        "essentiality_source": "HRAC MoA Group 2 (Target validated)",
        "essentiality_evidence": "Essential branched-chain amino acid biosynthesis (valine, leucine, isoleucine).",
        "notes": "Most widely targeted enzyme in herbicide discovery; resistance common.",
    },
    {
        "gene":         "HPPD",
        "family":       "HPPD Inhibitors",
        "full_name":    "4-Hydroxyphenylpyruvate dioxygenase",
        "herbicide_classes": ["Triketones", "Isoxazoles", "Pyrazoles"],
        "resistance_known": False,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "essentiality_status": "ESSENTIAL_KNOWN",
        "essentiality_source": "HRAC MoA Group 27 (Target validated)",
        "essentiality_evidence": "Plastoquinone and tocopherol biosynthesis; inhibition causes lethal photobleaching.",
        "notes": "Bleaching herbicide target; crop tolerance via HPPD variant selectivity.",
    },
    {
        "gene":         "PPO",
        "family":       "PPO Inhibitors",
        "full_name":    "Protoporphyrinogen IX oxidase",
        "herbicide_classes": ["Diphenylethers", "N-phenylphthalimides", "Oxadiazoles", "Triazolinones"],
        "resistance_known": True,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "essentiality_status": "ESSENTIAL_KNOWN",
        "essentiality_source": "HRAC MoA Group 14 (Target validated)",
        "essentiality_evidence": "Chlorophyll and heme biosynthesis pathway; inhibition generates toxic ROS.",
        "notes": "ROS-generating mechanism; resistance via Gly210 mutations.",
    },
    {
        "gene":         "EPSPS",
        "family":       "EPSPS / Glyphosate Targets",
        "full_name":    "5-Enolpyruvylshikimate-3-phosphate synthase",
        "herbicide_classes": ["Glycines (Glyphosate)"],
        "resistance_known": True,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "essentiality_status": "ESSENTIAL_KNOWN",
        "essentiality_source": "HRAC MoA Group 9 (Target validated)",
        "essentiality_evidence": "Aromatic amino acid biosynthesis (shikimate pathway); lethality confirmed in plants.",
        "notes": "Shikimate pathway; glyphosate resistance via TIPS mutation or gene amplification.",
    },
    {
        "gene":         "ACCase",
        "family":       "ACCase Inhibitors",
        "full_name":    "Acetyl-CoA carboxylase",
        "herbicide_classes": ["Aryloxyphenoxypropionates (FOPs)", "Cyclohexanediones (DIMs)", "Phenylpyrazolines (DEN)"],
        "resistance_known": True,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "essentiality_status": "ESSENTIAL_KNOWN",
        "essentiality_source": "HRAC MoA Group 1 (Target validated)",
        "essentiality_evidence": "De novo fatty acid synthesis in plastids; selective lethality in monocot weeds.",
        "notes": "Selective for grass weeds over broadleaf crops (chloroplastic isoform).",
    },
    {
        "gene":         "psbA",
        "family":       "PSII / D1 Protein",
        "full_name":    "Photosystem II D1 reaction centre protein (psbA)",
        "herbicide_classes": ["Triazines", "Phenylureas", "Uracils", "Bentazon"],
        "resistance_known": True,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "essentiality_status": "ESSENTIAL_KNOWN",
        "essentiality_source": "HRAC MoA Group 5 (Target validated)",
        "essentiality_evidence": "Photosynthetic electron transport core; plastid genome encoded.",
        "notes": "Ser264Gly confers atrazine resistance; plastid-encoded target.",
    },
    {
        "gene":         "PDS",
        "family":       "PDS Inhibitors",
        "full_name":    "Phytoene desaturase",
        "herbicide_classes": ["Fluridone", "Norflurazon", "Diflufenican"],
        "resistance_known": False,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "essentiality_status": "ESSENTIAL_KNOWN",
        "essentiality_source": "HRAC MoA Group 12 (Target validated)",
        "essentiality_evidence": "Carotenoid biosynthesis; absence causes rapid photo-oxidation in plants.",
        "notes": "Bleaching target in carotenoid pathway; good structural information.",
    },
    {
        "gene":         "KAS",
        "family":       "VLCFA / KAS Inhibitors",
        "full_name":    "β-Ketoacyl-ACP synthase (VLCFA elongase; KAS III)",
        "herbicide_classes": ["Chloroacetamides", "Oxyacetamides", "Tetrazolinones"],
        "resistance_known": False,
        "essentiality_tier": "LIKELY_ESSENTIAL",
        "essentiality_status": "LIKELY_ESSENTIAL",
        "essentiality_source": "HRAC MoA Group 15 (Target validated)",
        "essentiality_evidence": "Very-long-chain fatty acid synthesis; cell division arrest in germinating weeds.",
        "notes": "VLCFA elongase inhibition; lipid biosynthesis target.",
    },
    {
        "gene":         "GS",
        "family":       "Glutamine Synthetase",
        "full_name":    "Glutamine synthetase (GS / GOGAT pathway)",
        "herbicide_classes": ["Phosphinic acids (Glufosinate / bialaphos)"],
        "resistance_known": False,
        "essentiality_tier": "ESSENTIAL_UNIQUE",
        "essentiality_status": "ESSENTIAL_KNOWN",
        "essentiality_source": "HRAC MoA Group 10 (Target validated)",
        "essentiality_evidence": "Nitrogen assimilation; inhibition causes toxic ammonia accumulation in plant cells.",
        "notes": "Ammonia assimilation target; glufosinate-ammonium mode of action.",
    },
    {
        "gene":         "DXS",
        "family":       "DXS / MEP Pathway",
        "full_name":    "1-Deoxy-D-xylulose-5-phosphate synthase (DXS; MEP pathway entry)",
        "herbicide_classes": ["Fosmidomycin analogues (experimental)"],
        "resistance_known": False,
        "essentiality_tier": "LIKELY_ESSENTIAL",
        "essentiality_status": "LIKELY_ESSENTIAL",
        "essentiality_source": "MEP Pathway Literature (Preclinical)",
        "essentiality_evidence": "Plastid isoprenoid synthesis; genetic disruption yields albino/lethal phenotype in plants.",
        "notes": "Plastidic isoprenoid biosynthesis; no commercial herbicide yet; novel opportunity.",
    },
]


# ---------------------------------------------------------------------------
# Target Gene Keywords for Cross-Validation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Controlled Gene Aliases & Function Keywords for Verification (v9)
# ---------------------------------------------------------------------------

# Normalized exact gene aliases (UniProt geneName, synonyms, orderedLocusNames)
TARGET_GENE_ALIASES: Dict[str, List[str]] = {
    "ALS":    ["als", "ahas", "ahas1", "ahas2", "csr1", "tzp5", "ilvh", "ilvg", "ilvm"],
    "HPPD":   ["hppd", "hpd", "pds1", "4-hppd"],
    "PPO":    ["ppo", "ppx", "ppx2l", "ppx2", "ppx1", "ppox", "ppox1", "ppox2", "hemg", "hemg1", "ppop1"],
    "EPSPS":  ["epsps", "aroa", "arog", "epsp-s", "epsps-r", "epsps-r1", "epsps-r2", "epsps-s"],
    "ACCase": ["accase", "acc", "acc1", "acc2", "accd", "emb22", "gk", "pas3"],
    "psbA":   ["psba", "d1"],
    "PDS":    ["pds", "pds1", "pds2"],
    "KAS":    ["kas", "kas1", "kas2", "kas3", "kasi", "kasii", "kasiii", "fabh", "fabf", "mtkas"],
    "GS":     ["gs", "gln", "gln1", "gln2", "glna", "gln1-1", "gln1-2", "gln1-3", "gln1-4", "gln1-5", "gln2-1"],
    "DXS":    ["dxs", "cla1", "def"]
}

# Controlled target-specific biological function keywords (recommendedName, alternativeName, submissionNames, functional description)
TARGET_FUNCTION_KEYWORDS: Dict[str, List[str]] = {
    "ALS":    ["acetolactate synthase", "acetohydroxyacid synthase", "acetohydroxy-acid synthase", "chlorsulfuron resistant"],
    "HPPD":   ["hydroxyphenylpyruvate dioxygenase", "hydroxyphenylpyruvic acid oxidase", "4-hydroxyphenylpyruvate dioxygenase"],
    "PPO":    ["protoporphyrinogen oxidase", "protoporphyrinogen ix oxidase", "protox"],
    "EPSPS":  ["3-phosphoshikimate 1-carboxyvinyltransferase", "5-enolpyruvylshikimate-3-phosphate synthase", "epsp synthase", "shikimate-3-phosphate"],
    "ACCase": ["acetyl-coa carboxylase", "acetyl-coenzyme a carboxylase", "biotin carboxylase"],
    "psbA":   ["photosystem ii protein d1", "photosystem ii d1", "photosystem ii q(b) protein", "d1 reaction centre protein", "32 kda thylakoid membrane protein"],
    "PDS":    ["phytoene desaturase", "phytoene dehydrogenase", "15-cis-phytoene desaturase"],
    "KAS":    ["3-oxoacyl-[acyl-carrier-protein] synthase", "beta-ketoacyl-acp synthase", "ketoacyl-acp synthase", "3-ketoacyl-acyl carrier protein synthase"],
    "GS":     ["glutamine synthetase", "glutamate--ammonia ligase"],
    "DXS":    ["1-deoxy-d-xylulose-5-phosphate synthase", "deoxyxylulose-5-phosphate synthase", "cloroplastos alterados"]
}

# Backwards compatibility alias
TARGET_GENE_KEYWORDS: Dict[str, List[str]] = TARGET_GENE_ALIASES

# Curated Taxonomy ID mapping for plant organisms
SPECIES_TAXONOMY_MAP: Dict[str, int] = {
    "amaranthus palmeri": 107608,
    "amaranthus tuberculatus": 107609,
    "erigeron canadensis": 72917,
    "eleusine indica": 29674,
    "lolium rigidum": 89674,
    "alopecurus myosuroides": 81473,
    "arabidopsis thaliana": 3702,
    "glycine max": 3847,
    "zea mays": 4577,
    "oryza sativa": 4530,
    "oryza sativa subsp. japonica": 39947,
    "oryza sativa subsp. indica": 39946,
    "triticum aestivum": 4565,
    "nicotiana tabacum": 4097,
}

# ---------------------------------------------------------------------------
# Explicit Species-Specific Essentiality Registry
# ---------------------------------------------------------------------------

ESSENTIALITY_EVIDENCE_REGISTRY: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("ALS", "amaranthus palmeri"): {
        "target": "ALS",
        "species": "Amaranthus palmeri",
        "evidence_level": "SPECIES_SPECIFIC",
        "evidence_type": "CHEMICAL_GENETICS_AND_RESISTANCE_MUTATION",
        "source": "Weed Science Society of America (WSSA) / HRAC",
        "source_url": "https://weedscience.org",
        "publication": "Tranel & Wright (2002) Weed Sci 50:700-706",
        "evidence_summary": "In vivo ALS inhibition by multiple herbicide chemistries causes rapid plant death; Trp574Leu/Ser653Asn mutations restore viability.",
    },
    ("EPSPS", "amaranthus palmeri"): {
        "target": "EPSPS",
        "species": "Amaranthus palmeri",
        "evidence_level": "SPECIES_SPECIFIC",
        "evidence_type": "GENE_AMPLIFICATION_AND_SURVIVAL_ASSAY",
        "source": "Proceedings of the National Academy of Sciences",
        "source_url": "https://doi.org/10.1073/pnas.0909012107",
        "publication": "Gaines et al. (2010) PNAS 107(3):1029-1034",
        "evidence_summary": "EPSPS gene amplification directly dictates glyphosate lethal dose; absolute plant lethality upon target inhibition in sensitive biotypes.",
    },
    ("PPO", "amaranthus palmeri"): {
        "target": "PPO",
        "species": "Amaranthus palmeri",
        "evidence_level": "SPECIES_SPECIFIC",
        "evidence_type": "TARGET_DELETION_RESISTANCE_MUTATION",
        "source": "Pest Management Science",
        "source_url": "https://doi.org/10.1002/ps.4082",
        "publication": "Salas et al. (2016) Pest Manag Sci 72(4):664-671",
        "evidence_summary": "Gly210 deletion specifically prevents peroxidative lipid destruction and chlorosis, confirming in-weed target lethality.",
    },
}


# ---------------------------------------------------------------------------
# UniProt verification, search, and structure helpers
# ---------------------------------------------------------------------------

def _normalize_name(s: Optional[str]) -> str:
    """Normalize scientific species name or identifier for exact string comparison."""
    if not s:
        return ""
    import re
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def _verify_uniprot_accession(accession: str, expected_gene: str, expected_species: str, timeout: int = 8) -> Dict[str, Any]:
    """
    Verifies that a UniProt accession exists, is active, matches the expected species,
    matches the expected gene, and represents the correct biological target function.

    Evidence Integrity v9 principles:
      1. Exact organism verification:
         - Validates UniProt taxonomy ID when available in SPECIES_TAXONOMY_MAP.
         - Exact normalized scientific name match.
         - 'Amaranthus palmeri' will NEVER match 'Amaranthus tuberculatus'.
      2. Strict separation of gene vs function verification:
         - gene_verified ONLY checks gene fields (geneName, synonyms, orderedLocusNames).
           Protein description cannot make gene_verified True.
         - function_verified ONLY checks protein recommendedName, alternativeNames, submissionNames.
           Gene presence cannot make function_verified True.
      3. Provenance status requires:
         organism_verified == True AND gene_verified == True AND function_verified == True.
         Otherwise status = INVALID.
      4. Missing or empty gene/function fields cause INVALID status.

    Returns:
        organism_verified: bool
        gene_verified: bool
        function_verified: bool
        provenance_status: "VERIFIED", "INVALID", or "CURATED_UNVERIFIED"
        status: backwards-compatible alias for provenance_status
        reviewed: bool (True for Swiss-Prot, False for TrEMBL)
        organism_scientific: str or None
        taxon_id: int or None
        reason: str or None
    """
    if not accession:
        return {
            "status": "INVALID",
            "provenance_status": "INVALID",
            "organism_verified": False,
            "gene_verified": False,
            "function_verified": False,
            "reviewed": False,
            "organism_scientific": None,
            "taxon_id": None,
            "reason": "EMPTY_ACCESSION"
        }

    try:
        url = f"https://rest.uniprot.org/uniprotkb/{accession.strip().upper()}.json"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            return {
                "status": "INVALID",
                "provenance_status": "INVALID",
                "organism_verified": False,
                "gene_verified": False,
                "function_verified": False,
                "reviewed": False,
                "organism_scientific": None,
                "taxon_id": None,
                "reason": "ACCESSION_NOT_FOUND"
            }
        if resp.status_code != 200:
            return {
                "status": "CURATED_UNVERIFIED",
                "provenance_status": "CURATED_UNVERIFIED",
                "organism_verified": False,
                "gene_verified": False,
                "function_verified": False,
                "reviewed": False,
                "organism_scientific": None,
                "taxon_id": None,
                "reason": f"HTTP_{resp.status_code}"
            }

        data = resp.json()
        if data.get("entryType") == "Inactive":
            return {
                "status": "INVALID",
                "provenance_status": "INVALID",
                "organism_verified": False,
                "gene_verified": False,
                "function_verified": False,
                "reviewed": False,
                "organism_scientific": None,
                "taxon_id": None,
                "reason": "ENTRY_INACTIVE"
            }

        entry_type_str = data.get("entryType", "")
        is_reviewed = ("Swiss-Prot" in entry_type_str) or ("reviewed" in entry_type_str.lower() and "unreviewed" not in entry_type_str.lower())

        # -------------------------------------------------------------------
        # 1. Exact Scientific Organism & Taxonomy Verification
        # -------------------------------------------------------------------
        org_data = data.get("organism") or {}
        raw_sci = org_data.get("scientificName", "")
        norm_sci = _normalize_name(raw_sci)
        norm_expected_species = _normalize_name(expected_species)
        uniprot_taxon_id = org_data.get("taxonId")

        expected_taxon_id = SPECIES_TAXONOMY_MAP.get(norm_expected_species)

        # Exact match logic
        organism_verified = False
        if expected_taxon_id is not None and uniprot_taxon_id is not None:
            if uniprot_taxon_id == expected_taxon_id:
                organism_verified = True
            elif norm_expected_species in ("oryza sativa",) and uniprot_taxon_id in (39947, 39946, 4530):
                organism_verified = True

        if not organism_verified and norm_sci and norm_expected_species:
            # Check exact normalized scientific name or exact subspecies match
            if norm_sci == norm_expected_species:
                organism_verified = True
            elif norm_sci.startswith(norm_expected_species + " "):
                # e.g., 'oryza sativa subsp japonica' matching expected 'oryza sativa'
                organism_verified = True

        # -------------------------------------------------------------------
        # 2. Strict Gene Name Verification (Independent from Protein Description)
        # -------------------------------------------------------------------
        gene_entries = data.get("genes") or []
        gene_tokens: List[str] = []
        for g in gene_entries:
            if g.get("geneName", {}).get("value"):
                gene_tokens.append(_normalize_name(g["geneName"]["value"]))
            for syn in g.get("synonyms", []):
                if syn.get("value"):
                    gene_tokens.append(_normalize_name(syn["value"]))
            for ol in g.get("orderedLocusNames", []):
                if ol.get("value"):
                    gene_tokens.append(_normalize_name(ol["value"]))

        expected_gene_norm = _normalize_name(expected_gene)
        registered_aliases = TARGET_GENE_ALIASES.get(expected_gene, [expected_gene])
        # Build exact normalized match set and exact compact alphanumeric match set
        allowed_gene_aliases = set(_normalize_name(a) for a in registered_aliases)
        allowed_gene_aliases.add(expected_gene_norm)
        allowed_compact_aliases = set(re.sub(r"[\s\-_]+", "", a.lower()) for a in registered_aliases)
        allowed_compact_aliases.add(re.sub(r"[\s\-_]+", "", expected_gene.lower()))

        gene_verified = False
        if gene_tokens:
            # Check strict exact match against approved registered aliases / variants
            # Evidence Integrity: NEVER use generic startswith/endswith or loose token split
            for gt in gene_tokens:
                gt_norm = _normalize_name(gt)
                gt_compact = re.sub(r"[\s\-_]+", "", gt.lower())
                if gt_norm in allowed_gene_aliases or gt_compact in allowed_compact_aliases:
                    gene_verified = True
                    break

        # -------------------------------------------------------------------
        # 3. Strict Protein Function Verification (Independent from Gene Fields)
        # -------------------------------------------------------------------
        pdesc = data.get("proteinDescription") or {}
        function_strings: List[str] = []
        rec = pdesc.get("recommendedName", {}).get("fullName", {}).get("value")
        if rec:
            function_strings.append(_normalize_name(rec))
        for sub in pdesc.get("submissionNames", []):
            if sub.get("fullName", {}).get("value"):
                function_strings.append(_normalize_name(sub["fullName"]["value"]))
        for alt in pdesc.get("alternativeNames", []):
            if alt.get("fullName", {}).get("value"):
                function_strings.append(_normalize_name(alt["fullName"]["value"]))

        func_kws = [
            _normalize_name(kw) for kw in TARGET_FUNCTION_KEYWORDS.get(expected_gene, [expected_gene])
        ]

        function_verified = False
        if function_strings:
            for fs in function_strings:
                # 1. Exact normalized match
                if fs in func_kws:
                    function_verified = True
                    break
                # 2. Strict word-bounded phrase match (approved functional variant)
                for kw in func_kws:
                    # Require word boundaries around the approved keyword phrase
                    pattern = r"(?:\b|^)" + re.escape(kw) + r"(?:\b|$)"
                    if re.search(pattern, fs):
                        function_verified = True
                        break
                if function_verified:
                    break

        # -------------------------------------------------------------------
        # 4. Provenance Status Determination: ALL THREE MUST BE TRUE
        # -------------------------------------------------------------------
        if not organism_verified:
            reason = f"ORGANISM_MISMATCH: expected '{expected_species}' (taxon: {expected_taxon_id}), found '{raw_sci}' (taxon: {uniprot_taxon_id})"
            status = "INVALID"
        elif not gene_tokens:
            reason = f"EMPTY_GENE_FIELDS: no gene symbols or locus names found for expected gene '{expected_gene}'"
            status = "INVALID"
        elif not gene_verified:
            reason = f"GENE_MISMATCH: expected gene '{expected_gene}', found gene fields {gene_tokens}"
            status = "INVALID"
        elif not function_strings:
            reason = f"EMPTY_FUNCTION_FIELDS: no protein description found for target '{expected_gene}'"
            status = "INVALID"
        elif not function_verified:
            reason = f"FUNCTION_MISMATCH: expected target function '{expected_gene}', found descriptions {function_strings}"
            status = "INVALID"
        else:
            reason = None
            status = "VERIFIED"

        return {
            "status": status,
            "provenance_status": status,
            "organism_verified": organism_verified,
            "gene_verified": gene_verified,
            "function_verified": function_verified,
            "reviewed": is_reviewed,
            "organism_scientific": raw_sci,
            "taxon_id": uniprot_taxon_id,
            "reason": reason
        }
    except Exception as e:
        return {
            "status": "CURATED_UNVERIFIED",
            "provenance_status": "CURATED_UNVERIFIED",
            "organism_verified": False,
            "gene_verified": False,
            "function_verified": False,
            "reviewed": False,
            "organism_scientific": None,
            "taxon_id": None,
            "reason": str(e)
        }

def _search_uniprot(species_name: str, gene: str, timeout: int = 10) -> Optional[str]:
    """Search UniProt for a given species + gene; return first active primaryAccession or None."""
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
            for res in results:
                if res.get("entryType") != "Inactive":
                    return res.get("primaryAccession")
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
                plddt = data[0].get("globalMetricValue") or data[0].get("plddt")
                return True, float(plddt) if plddt is not None else None
    except Exception:
        pass
    return False, None


def _fetch_fasta_seq(uniprot_id: str, timeout: int = 10) -> Optional[str]:
    try:
        url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id.strip()}.fasta"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            lines = resp.text.strip().split("\n")
            return "".join(l.strip() for l in lines if not l.startswith(">")) or None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# MultiTargetDiscoveryEngine (Evidence Integrity v6 + Target Ranking v2)
# ---------------------------------------------------------------------------

class MultiTargetDiscoveryEngine:
    """
    Discovers, assesses, and ranks herbicide target proteins for a given weed species
    across 10 major herbicide target families.
    
    Rigorous scientific principles:
      1. Essentiality status, evidence, and source are recorded; essentiality_score is only
         computed when specific weed sequence/accession evidence exists.
      2. Pairwise sequence identity uses true Biopython global alignment (Needleman-Wunsch).
      3. Curated accessions are validated with complete provenance metadata records.
      4. Explicitly separates target_evidence_score (empirical evidence strength)
         from target_opportunity_score (actionable discovery potential).
    """

    # Curated, validated UniProt accessions with full provenance records
    PROVENANCE_REGISTRY: Dict[Tuple[str, str], Dict[str, Any]] = {
        # Weeds
        ("ALS", "amaranthus palmeri"): {"accession": "A0A890DLI3", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Amaranthus palmeri", "gene": "ALS"},
        ("ALS", "erigeron canadensis"): {"accession": "G8E459", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Erigeron canadensis", "gene": "ALS"},
        ("ALS", "arabidopsis thaliana"): {"accession": "P17597", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Arabidopsis thaliana", "gene": "ALS"},
        ("HPPD", "arabidopsis thaliana"): {"accession": "P93836", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Arabidopsis thaliana", "gene": "HPPD"},
        ("PPO", "amaranthus palmeri"): {"accession": "A0A6C0RR75", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Amaranthus palmeri", "gene": "PPO"},
        ("PPO", "arabidopsis thaliana"): {"accession": "P55826", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Arabidopsis thaliana", "gene": "PPO"},
        ("EPSPS", "amaranthus palmeri"): {"accession": "M1K439", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Amaranthus palmeri", "gene": "EPSPS"},
        ("EPSPS", "eleusine indica"): {"accession": "A0A0A1C3J0", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Eleusine indica", "gene": "EPSPS"},
        ("EPSPS", "lolium rigidum"): {"accession": "A0A5B9T5W8", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Lolium rigidum", "gene": "EPSPS"},
        ("EPSPS", "arabidopsis thaliana"): {"accession": "Q9FVP6", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Arabidopsis thaliana", "gene": "EPSPS"},
        ("ACCase", "alopecurus myosuroides"): {"accession": "Q5CCG4", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Alopecurus myosuroides", "gene": "ACCase"},
        ("ACCase", "lolium rigidum"): {"accession": "A0A5B9T5R1", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Lolium rigidum", "gene": "ACCase"},
        ("ACCase", "arabidopsis thaliana"): {"accession": "Q38970", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Arabidopsis thaliana", "gene": "ACCase"},
        ("psbA", "amaranthus palmeri"): {"accession": "A0A890DLU5", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Amaranthus palmeri", "gene": "psbA"},
        ("psbA", "arabidopsis thaliana"): {"accession": "P83755", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Arabidopsis thaliana", "gene": "psbA"},
        ("PDS", "arabidopsis thaliana"): {"accession": "Q07356", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Arabidopsis thaliana", "gene": "PDS"},
        ("KAS", "arabidopsis thaliana"): {"accession": "Q8L3X9", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Arabidopsis thaliana", "gene": "KAS"},
        ("GS", "arabidopsis thaliana"): {"accession": "Q56WN1", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Arabidopsis thaliana", "gene": "GS"},
        ("DXS", "arabidopsis thaliana"): {"accession": "Q38854", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Arabidopsis thaliana", "gene": "DXS"},
        # Crops
        ("ALS", "glycine max"): {"accession": "U5JC63", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Glycine max", "gene": "ALS"},
        ("ALS", "zea mays"): {"accession": "Q41768", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Zea mays", "gene": "ALS"},
        ("ALS", "oryza sativa"): {"accession": "Q6K2E8", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Oryza sativa", "gene": "ALS"},
        ("ALS", "triticum aestivum"): {"accession": "A0A3B6PRC5", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Triticum aestivum", "gene": "ALS"},
        ("HPPD", "glycine max"): {"accession": "I1M6Z5", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Glycine max", "gene": "HPPD"},
        ("HPPD", "zea mays"): {"accession": "I7HIS1", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Zea mays", "gene": "HPPD"},
        ("HPPD", "oryza sativa"): {"accession": "Q0E3L4", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Oryza sativa", "gene": "HPPD"},
        ("PPO", "glycine max"): {"accession": "P35055", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Glycine max", "gene": "PPO"},
        ("PPO", "zea mays"): {"accession": "Q9ZTP4", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Zea mays", "gene": "PPO"},
        ("EPSPS", "glycine max"): {"accession": "I1J7U9", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Glycine max", "gene": "EPSPS"},
        ("EPSPS", "zea mays"): {"accession": "O24566", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Zea mays", "gene": "EPSPS"},
        ("EPSPS", "oryza sativa"): {"accession": "Q5NTH3", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Oryza sativa", "gene": "EPSPS"},
        ("ACCase", "glycine max"): {"accession": "P49158", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Glycine max", "gene": "ACCase"},
        ("ACCase", "zea mays"): {"accession": "A0A804ULV9", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": False, "species": "Zea mays", "gene": "ACCase"},
        ("psbA", "glycine max"): {"accession": "P02957", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Glycine max", "gene": "psbA"},
        ("psbA", "zea mays"): {"accession": "P48183", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Zea mays", "gene": "psbA"},
        ("PDS", "glycine max"): {"accession": "P28553", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Glycine max", "gene": "PDS"},
        ("GS", "glycine max"): {"accession": "O82560", "source": "UniProt", "source_type": "CURATED_MAPPING", "retrieved_at": "2026-10-05", "reviewed": True, "species": "Glycine max", "gene": "GS"},
    }

    # Species aliases for weed and crop lookup
    SPECIES_ALIASES = {
        "palmer amaranth": "amaranthus palmeri",
        "palmer's pigweed": "amaranthus palmeri",
        "waterhemp": "amaranthus tuberculatus",
        "tall waterhemp": "amaranthus tuberculatus",
        "horseweed": "erigeron canadensis",
        "canadian horseweed": "erigeron canadensis",
        "conyza canadensis": "erigeron canadensis",
        "goosegrass": "eleusine indica",
        "rigid ryegrass": "lolium rigidum",
        "annual ryegrass": "lolium rigidum",
        "blackgrass": "alopecurus myosuroides",
        "thale cress": "arabidopsis thaliana",
        "arabidopsis": "arabidopsis thaliana",
        "soybean": "glycine max",
        "corn": "zea mays",
        "maize": "zea mays",
        "rice": "oryza sativa",
        "wheat": "triticum aestivum",
    }

    def __init__(self, crop_species: Optional[str] = None):
        self.crop_species = crop_species

    def _canonical_species(self, species: str) -> str:
        s = species.lower().strip()
        return self.SPECIES_ALIASES.get(s, s)

    def discover_targets(
        self,
        weed_species: str,
        max_targets: int = 10,
        require_alphafold: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Discovers, assesses, and ranks herbicide targets for *weed_species*.
        """
        results = []
        for target_def in TARGET_CATALOGUE:
            record = self._assess_single_target(weed_species, target_def)
            if require_alphafold and not record.get("alphafold_available"):
                continue
            results.append(record)

        # Rank by target_opportunity_score (preserves None as lowest)
        results.sort(
            key=lambda r: (
                r.get("target_opportunity_score") is not None,
                r.get("target_opportunity_score") or -1.0,
                r.get("target_evidence_score") or -1.0
            ),
            reverse=True
        )
        return results[:max_targets]

    def _assess_single_target(
        self, weed_species: str, target_def: Dict[str, Any]
    ) -> Dict[str, Any]:
        gene = target_def["gene"]
        weed_canonical = self._canonical_species(weed_species)

        # --- 1. Resolve weed UniProt accession with provenance & verification ---
        weed_provenance: Optional[Dict[str, Any]] = None
        weed_accession: Optional[str] = None

        if (gene, weed_canonical) in self.PROVENANCE_REGISTRY:
            weed_provenance = dict(self.PROVENANCE_REGISTRY[(gene, weed_canonical)])
            weed_accession = weed_provenance["accession"]
            # Verify accession against UniProt
            v_res = _verify_uniprot_accession(weed_accession, gene, weed_canonical)
            weed_provenance["provenance_status"] = v_res["status"]
            if v_res.get("reason"):
                weed_provenance["verification_detail"] = v_res["reason"]
            if v_res["status"] == "INVALID":
                # Do not proceed with an invalid poisoned accession
                weed_accession = None
        else:
            dyn_acc = _search_uniprot(weed_canonical, gene)
            if not dyn_acc and weed_species.lower() != weed_canonical:
                dyn_acc = _search_uniprot(weed_species, gene)
            if dyn_acc:
                weed_accession = dyn_acc
                v_res = _verify_uniprot_accession(dyn_acc, gene, weed_species)
                weed_provenance = {
                    "accession": dyn_acc,
                    "source": "UniProt",
                    "source_type": "DYNAMIC_SEARCH",
                    "provenance_status": v_res["status"],
                    "retrieved_at": "dynamic",
                    "reviewed": v_res["reviewed"],
                    "species": weed_species,
                    "gene": gene,
                    "verification_detail": v_res.get("reason")
                }
                if v_res["status"] == "INVALID":
                    weed_accession = None

        # --- 2. AlphaFold availability + pLDDT ---
        alphafold_available = False
        plddt_avg: Optional[float] = None
        if weed_accession:
            alphafold_available, plddt_avg = _check_alphafold_available(weed_accession)

        # --- 3. Weed FASTA sequence ---
        weed_seq: Optional[str] = _fetch_fasta_seq(weed_accession) if weed_accession else None
        sequence_length: Optional[int] = len(weed_seq) if weed_seq else None

        # --- 4. Crop homolog accession, alignment & divergence ---
        crop_accession: Optional[str] = None
        crop_provenance: Optional[Dict[str, Any]] = None
        crop_seq: Optional[str] = None
        alignment_info: Dict[str, Any] = {
            "alignment_status": "NOT_ATTEMPTED",
            "sequence_identity": None,
            "alignment_coverage": None,
            "weed_coverage": None,
            "crop_coverage": None,
            "identity_over_aligned_positions": None,
            "alignment_length": None,
            "alignment_method": None,
            "bit_score": None,
            "e_value": None,
            "aligned_weed": None,
            "aligned_crop": None,
        }
        crop_divergence: Optional[float] = None

        if self.crop_species:
            crop_canonical = self._canonical_species(self.crop_species)
            if (gene, crop_canonical) in self.PROVENANCE_REGISTRY:
                crop_provenance = dict(self.PROVENANCE_REGISTRY[(gene, crop_canonical)])
                crop_accession = crop_provenance["accession"]
                v_crop = _verify_uniprot_accession(crop_accession, gene, crop_canonical)
                crop_provenance["provenance_status"] = v_crop["status"]
                if v_crop.get("reason"):
                    crop_provenance["verification_detail"] = v_crop["reason"]
                if v_crop["status"] == "INVALID":
                    crop_accession = None
            else:
                dyn_crop_acc = _search_uniprot(crop_canonical, gene)
                if not dyn_crop_acc and self.crop_species.lower() != crop_canonical:
                    dyn_crop_acc = _search_uniprot(self.crop_species, gene)
                if dyn_crop_acc:
                    crop_accession = dyn_crop_acc
                    v_crop = _verify_uniprot_accession(dyn_crop_acc, gene, self.crop_species)
                    crop_provenance = {
                        "accession": dyn_crop_acc,
                        "source": "UniProt",
                        "source_type": "DYNAMIC_SEARCH",
                        "provenance_status": v_crop["status"],
                        "retrieved_at": "dynamic",
                        "reviewed": v_crop["reviewed"],
                        "species": self.crop_species,
                        "gene": gene,
                        "verification_detail": v_crop.get("reason")
                    }
                    if v_crop["status"] == "INVALID":
                        crop_accession = None

            if crop_accession:
                crop_seq = _fetch_fasta_seq(crop_accession)
                if weed_seq and crop_seq:
                    alignment_info = _align_pairwise_biopython(weed_seq, crop_seq)
                    seq_id = alignment_info.get("sequence_identity")
                    crop_divergence = round(100.0 - seq_id, 1) if seq_id is not None else None

        # --- 5. Evidence & Essentiality Level Stratification ---
        essentiality_status = target_def.get("essentiality_status", "UNKNOWN")
        essentiality_evidence = target_def.get("essentiality_evidence", "No evidence recorded.")
        essentiality_source = target_def.get("essentiality_source", "Curated Catalogue")

        # Determine evidence level: requires explicit empirical species-specific evidence in registry
        target_present_in_weed = (weed_accession is not None or weed_seq is not None)
        species_specific_essentiality = False
        evidence_registry_key = (gene, weed_canonical)
        evidence_record = ESSENTIALITY_EVIDENCE_REGISTRY.get(evidence_registry_key)

        if not target_present_in_weed:
            essentiality_evidence_level = "UNKNOWN"
        elif evidence_record is not None and evidence_record.get("evidence_level") == "SPECIES_SPECIFIC":
            essentiality_evidence_level = "SPECIES_SPECIFIC"
            species_specific_essentiality = True
            essentiality_evidence = evidence_record.get("evidence_summary", essentiality_evidence)
            essentiality_source = f"{evidence_record.get('source')} ({evidence_record.get('publication')})"
        elif gene in ("DXS",):
            essentiality_evidence_level = "PRECLINICAL_HYPOTHESIS"
        else:
            essentiality_evidence_level = "GENERAL_PLANT_EVIDENCE"

        # Essentiality score: requires target presence in weed
        essentiality_score = self._score_essentiality(
            target_def=target_def,
            has_weed_evidence=target_present_in_weed,
            evidence_level=essentiality_evidence_level
        )
        herbicide_evidence_score = self._score_herbicide_evidence(target_def)
        selectivity_potential_score = self._score_selectivity_potential(target_def, crop_divergence)
        structure_score = self._score_structure(alphafold_available, plddt_avg)

        # Target Evidence Score (measures empirical evidence retrieved)
        target_evidence_score = self._compute_target_evidence_score(
            has_weed_accession=weed_accession is not None,
            has_weed_seq=weed_seq is not None,
            alphafold_available=alphafold_available,
            plddt_avg=plddt_avg,
            has_crop_homolog=crop_accession is not None,
            has_alignment=alignment_info.get("sequence_identity") is not None,
            resistance_known=target_def.get("resistance_known", False),
            herbicide_classes_count=len(target_def.get("herbicide_classes", []))
        )
        target_evidence_confidence = self._compute_target_evidence_confidence(
            target_evidence_score, weed_seq is not None, alphafold_available and plddt_avg is not None
        )

        # Target Opportunity Score (measures actionable discovery suitability)
        target_opportunity_score = self._compute_opportunity_score(
            essentiality_score=essentiality_score,
            herbicide_evidence_score=herbicide_evidence_score,
            selectivity_potential_score=selectivity_potential_score,
            structure_score=structure_score,
            has_weed_evidence=target_present_in_weed
        )

        return {
            # Identity
            "gene":                       gene,
            "family":                     target_def["family"],
            "full_name":                  target_def["full_name"],
            # Weed target
            "weed_species":               weed_species,
            "weed_uniprot_id":            weed_accession,
            "weed_accession_provenance":  weed_provenance,
            "weed_sequence_length":       sequence_length,
            "weed_sequence_available":    weed_seq is not None,
            "target_present_in_weed":     target_present_in_weed,
            # Structure
            "alphafold_available":        alphafold_available,
            "plddt_avg":                  plddt_avg,
            "structure_confidence_level": self._plddt_label(plddt_avg),
            # Crop homolog & Alignment
            "crop_species":               self.crop_species,
            "crop_uniprot_id":            crop_accession,
            "crop_accession_provenance":  crop_provenance,
            "alignment_status":           alignment_info.get("alignment_status"),
            "sequence_identity_pct":      alignment_info.get("sequence_identity"),
            "alignment_coverage":         alignment_info.get("alignment_coverage"),
            "weed_coverage_pct":          alignment_info.get("weed_coverage"),
            "crop_coverage_pct":          alignment_info.get("crop_coverage"),
            "identity_over_aligned_pct":   alignment_info.get("identity_over_aligned_positions"),
            "alignment_length":           alignment_info.get("alignment_length"),
            "alignment_method":           alignment_info.get("alignment_method"),
            "bit_score":                  alignment_info.get("bit_score"),
            "e_value":                    alignment_info.get("e_value"),
            "crop_divergence_pct":        crop_divergence,
            "crop_selectivity_potential": self._selectivity_label(crop_divergence),
            # Chemical & Resistance evidence
            "herbicide_classes":          target_def["herbicide_classes"],
            "known_chemical_matter":      len(target_def["herbicide_classes"]) > 0,
            "resistance_reported":        target_def["resistance_known"],
            "notes":                      target_def["notes"],
            # Essentiality fields (scientifically honest distinction)
            "essentiality_tier":          target_def.get("essentiality_tier"),
            "essentiality_status":        essentiality_status,
            "essentiality_evidence":      essentiality_evidence,
            "essentiality_source":        essentiality_source,
            "essentiality_evidence_level": essentiality_evidence_level,
            "species_specific_essentiality": species_specific_essentiality,
            "essentiality_score":         essentiality_score,
            # Component scores
            "herbicide_evidence_score":   herbicide_evidence_score,
            "selectivity_potential_score": selectivity_potential_score,
            "structure_score":            structure_score,
            # Dual composite metrics
            "target_evidence_score":      target_evidence_score,
            "target_evidence_confidence": target_evidence_confidence,
            "target_opportunity_score":   target_opportunity_score,
            # Provenance
            "evidence_sources": [
                "UniProt REST API / Curated Registry",
                "AlphaFold EBI API",
                "Biopython Pairwise Alignment Engine",
                "HRAC Herbicide Mechanism Literature Database",
            ],
            "evidence_status": "SEQUENCE_RETRIEVED" if weed_seq else ("ACCESSION_RESOLVED" if weed_accession else "COMPUTATIONAL_HYPOTHESIS_ONLY"),
        }

    # -----------------------------------------------------------------------
    # Scoring helpers (All values derived from evidence; no fabricated numbers)
    # -----------------------------------------------------------------------

    @staticmethod
    def _score_essentiality(
        target_def: Dict[str, Any],
        has_weed_evidence: bool = True,
        evidence_level: str = "GENERAL_PLANT_EVIDENCE"
    ) -> Optional[float]:
        """
        Returns essentiality_score ONLY when empirical weed evidence is present.
        If no weed accession or sequence exists, returns None rather than manufacturing 90.0.

        Distinguishes:
          - SPECIES_SPECIFIC: Target essentiality confirmed in this specific weed species via empirical evidence.
          - GENERAL_PLANT_EVIDENCE: Essential in plant kingdom, but species-specific trial data not yet published.
          - PRECLINICAL_HYPOTHESIS: Experimental pathway target.
        """
        if not has_weed_evidence or evidence_level == "UNKNOWN":
            return None

        status = target_def.get("essentiality_status", target_def.get("essentiality_tier", "UNKNOWN"))
        if evidence_level == "SPECIES_SPECIFIC":
            if status in ("ESSENTIAL_KNOWN", "ESSENTIAL_UNIQUE"):
                return 95.0
            return 80.0
        elif evidence_level == "GENERAL_PLANT_EVIDENCE":
            if status in ("ESSENTIAL_KNOWN", "ESSENTIAL_UNIQUE"):
                return 85.0
            elif status == "LIKELY_ESSENTIAL":
                return 65.0
            return 40.0
        elif evidence_level == "PRECLINICAL_HYPOTHESIS":
            return 50.0

        return 40.0

    @staticmethod
    def _score_herbicide_evidence(target_def: Dict[str, Any]) -> float:
        """Herbicide evidence score scaled strictly by documented chemical inhibitor classes."""
        n = len(target_def.get("herbicide_classes", []))
        return min(100.0, 30.0 + n * 12.0)

    @staticmethod
    def _score_selectivity_potential(
        target_def: Dict[str, Any],
        crop_divergence: Optional[float],
        seq_identity: Optional[float] = None
    ) -> Optional[float]:
        if crop_divergence is not None:
            return round(min(100.0, max(0.0, crop_divergence * 1.5)), 1)
        return None

    @staticmethod
    def _score_structure(alphafold_available: bool, plddt: Optional[float]) -> Optional[float]:
        """
        Structure score is derived strictly from real pLDDT.
        If AlphaFold is unavailable OR pLDDT is missing, returns None. Never fabricates 50.0.
        """
        if not alphafold_available or plddt is None:
            return None
        return round(min(100.0, max(0.0, plddt)), 1)

    @staticmethod
    def _compute_target_evidence_score(
        has_weed_accession: bool,
        has_weed_seq: bool,
        alphafold_available: bool,
        plddt_avg: Optional[float],
        has_crop_homolog: bool,
        has_alignment: bool,
        resistance_known: bool,
        herbicide_classes_count: int,
    ) -> float:
        """
        Calculates target_evidence_score: How strong is the actual verified evidence?
        Max 100.0.
          - Weed accession verified: 20
          - Weed sequence retrieved: 20
          - AlphaFold structure available with verified pLDDT: 20 * (plddt / 100.0)
            (If plddt is unavailable, contributes 0.0 — no fabricated 0.7 factor)
          - Crop homolog accession: 15
          - Pairwise sequence alignment computed: 10
          - Commercial herbicide chemical matter: up to 10
          - Resistance mutation characterization: 5
        """
        score = 0.0
        if has_weed_accession:
            score += 20.0
        if has_weed_seq:
            score += 20.0
        if alphafold_available and plddt_avg is not None:
            factor = (plddt_avg / 100.0)
            score += 20.0 * max(0.0, min(1.0, factor))
        if has_crop_homolog:
            score += 15.0
        if has_alignment:
            score += 10.0
        score += min(10.0, herbicide_classes_count * 2.5)
        if resistance_known:
            score += 5.0
        return round(min(100.0, score), 1)

    @staticmethod
    def _compute_target_evidence_confidence(evidence_score: float, has_weed_seq: bool, has_structure: bool) -> str:
        if evidence_score >= 75.0 and has_weed_seq and has_structure:
            return "HIGH"
        elif evidence_score >= 50.0 and has_weed_seq:
            return "MEDIUM"
        elif evidence_score >= 25.0:
            return "LOW"
        return "HYPOTHESIS_ONLY"

    @staticmethod
    def _compute_opportunity_score(
        essentiality_score: Optional[float],
        herbicide_evidence_score: float,
        selectivity_potential_score: Optional[float],
        structure_score: Optional[float],
        has_weed_evidence: bool = True,
    ) -> Optional[float]:
        """
        Calculates target_opportunity_score: How promising is this target for discovery?
        If no weed evidence exists, return None (cannot fabricate opportunity score for unknown weed target).
        """
        if not has_weed_evidence:
            return None

        components: List[Tuple[float, float]] = []
        if essentiality_score is not None:
            components.append((essentiality_score, 0.35))
        components.append((herbicide_evidence_score, 0.30))
        if selectivity_potential_score is not None:
            components.append((selectivity_potential_score, 0.20))
        if structure_score is not None:
            components.append((structure_score, 0.15))

        total_weight = sum(w for _, w in components)
        if total_weight <= 0:
            return None
        score = sum(v * w for v, w in components) / total_weight
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
