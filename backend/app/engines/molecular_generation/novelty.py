from typing import Dict, Any, List, Optional, Tuple
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem
from app.engines.molecular_generation.schemas import NoveltyCategory, NoveltyAnalysisResult

# Curated reference catalogue of commercial and benchmark herbicides across 10 mode-of-action families
KNOWN_HERBICIDE_REFERENCES = [
    # ALS / AHAS inhibitors (Sulfonylureas, Imidazolinones, Triazolopyrimidines)
    {"name": "Imazethapyr", "family": "ALS", "smiles": "CC1=NC(C(C)C)=NC(=O)C1=C2C=CC(=CC2=O)O"},
    {"name": "Chlorimuron-ethyl", "family": "ALS", "smiles": "CCN(C)c1nc(nc(n1)Cl)NS(=O)(=O)c2ccccc2C(=O)OCC"},
    {"name": "Sulfometuron-methyl", "family": "ALS", "smiles": "CC1=NC(=NC(=N1)NC(=O)NS(=O)(=O)C2=CC=CC=C2C(=O)OC)C"},
    {"name": "Flumetsulam", "family": "ALS", "smiles": "Cc1cc(F)cc(c1)n2nc3nc(nc3n2)S(=O)(=O)Nc4c(F)cccc4F"},
    {"name": "Florasulam", "family": "ALS", "smiles": "COc1cc2nc(nc2n1)S(=O)(=O)Nc3c(F)cc(F)c(F)c3F"},
    {"name": "Imazapyr", "family": "ALS", "smiles": "CC(C)C1(NC(=O)C2=NC=CC=C21)C(=O)O"},
    {"name": "Chlorsulfuron", "family": "ALS", "smiles": "Cc1nc(nc(n1)Cl)NC(=O)NS(=O)(=O)c2ccccc2Cl"},
    {"name": "Bispyribac-sodium", "family": "ALS", "smiles": "COc1cc(OC)nc(n1)Oc2cccc(c2)C(=O)O"},

    # HPPD inhibitors (Triketones, Isoxazoles, Pyrazolones)
    {"name": "Mesotrione", "family": "HPPD", "smiles": "CS(=O)(=O)c1ccc(c(c1)N(=O)=O)C(=O)C2C(=O)CCCC2=O"},
    {"name": "Isoxaflutole", "family": "HPPD", "smiles": "CC1(CC1)C(=O)c2cc(c(cc2C(F)(F)F)S(=O)(=O)C)C3=NOC=C3"},
    {"name": "Tembotrione", "family": "HPPD", "smiles": "CS(=O)(=O)c1cc(c(c(c1)OCC(F)(F)F)C(=O)C2C(=O)CCCC2=O)Cl"},
    {"name": "Tolpyralate", "family": "HPPD", "smiles": "CCOC(=O)c1c(c(nc(n1)C)C(=O)c2c(c(cc(c2Cl)S(=O)(=O)C)F)Cl)O"},

    # PPO inhibitors (Diphenyl ethers, N-phenylphthalimides, Triazolinones)
    {"name": "Flumioxazin", "family": "PPO", "smiles": "CC1=CC(=O)C2=C(C=C1)N(C(=O)O2)C3=CC(=C(C=C3F)Cl)F"},
    {"name": "Fomesafen", "family": "PPO", "smiles": "COc1cc(c(cc1C(=O)NS(=O)(=O)C)Cl)Oc2ccc(cc2Cl)C(F)(F)F"},
    {"name": "Sulfentrazone", "family": "PPO", "smiles": "CS(=O)(=O)c1cc(c(cc1Cl)N2N=C(C(=O)N2C(F)F)C)Cl"},
    {"name": "Oxyfluorfen", "family": "PPO", "smiles": "CCOc1cc(c(cc1[N+](=O)[O-])Oc2ccc(cc2Cl)C(F)(F)F)Cl"},

    # EPSPS & Glutamine Synthetase inhibitors (Amino acid synthesis)
    {"name": "Glyphosate", "family": "EPSPS", "smiles": "C(C(=O)O)NCP(=O)(O)O"},
    {"name": "Glufosinate", "family": "GS", "smiles": "CP(=O)(O)CCC(N)C(=O)O"},

    # ACCase inhibitors (Aryloxyphenoxypropionates & Cyclohexanediones)
    {"name": "Clethodim", "family": "ACCase", "smiles": "CCCC(=O)C1C(=O)CC(CC1=NOCC=CCl)CCSC"},
    {"name": "Fluazifop-P-butyl", "family": "ACCase", "smiles": "CCCCOC(=O)C(C)Oc1ccc(cc1)Oc2ccc(nc2)C(F)(F)F"},
    {"name": "Haloxyfop-methyl", "family": "ACCase", "smiles": "COC(=O)C(C)Oc1ccc(cc1)Oc2ncc(cc2Cl)C(F)(F)F"},

    # Photosystem II / psbA inhibitors
    {"name": "Atrazine", "family": "psbA", "smiles": "CCNc1nc(nc(n1)Cl)NC(C)C"},
    {"name": "Metribuzin", "family": "psbA", "smiles": "CC(C)(C)c1nnc(n(c1=O)N)SC"},

    # PDS inhibitors (Phytoene Desaturase)
    {"name": "Norflurazon", "family": "PDS", "smiles": "CNc1c(c(=O)n(nc1Cl)c2cccc(c2)C(F)(F)F)Cl"},
    {"name": "Diflufenican", "family": "PDS", "smiles": "c1cc(c(c(c1)F)Oc2cc(ccn2)C(=O)Nc3ccc(cc3)C(F)(F)F)F"},
]


class NoveltyAnalyzer:
    """
    Evaluates candidate molecular novelty using Morgan fingerprints and Tanimoto similarity
    against known commercial herbicides and optional project-specific reference sets.
    """

    def __init__(self, additional_references: Optional[List[Dict[str, Any]]] = None):
        self.reference_pool: List[Tuple[str, str, Any]] = []  # (name, smiles, fp)
        self._initialize_references(additional_references or [])

    def _initialize_references(self, additional_references: List[Dict[str, Any]]):
        combined = list(KNOWN_HERBICIDE_REFERENCES) + additional_references
        for ref in combined:
            smiles = ref.get("smiles")
            if not smiles:
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                canonical = Chem.MolToSmiles(mol, canonical=True)
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
                self.reference_pool.append((ref.get("name", "Unknown Reference"), canonical, fp))

    def evaluate_novelty(
        self,
        query_mol: Chem.Mol,
        query_canonical_smiles: str,
        database_scope: str = "MIKHERB Known Commercial Herbicides Catalogue"
    ) -> NoveltyAnalysisResult:
        """
        Calculates maximum Tanimoto similarity against the reference database and categorizes novelty.
        """
        query_fp = AllChem.GetMorganFingerprintAsBitVect(query_mol, radius=2, nBits=2048)

        max_sim = 0.0
        closest_name = None
        exact_match = False

        for name, ref_canonical, ref_fp in self.reference_pool:
            if query_canonical_smiles == ref_canonical:
                exact_match = True
                max_sim = 1.0
                closest_name = name
                break

            sim = DataStructs.TanimotoSimilarity(query_fp, ref_fp)
            if sim > max_sim:
                max_sim = sim
                closest_name = name

        max_sim_rounded = round(float(max_sim), 4)

        if exact_match or max_sim_rounded >= 0.999:
            category = NoveltyCategory.KNOWN_EXACT_MATCH
        elif max_sim_rounded >= 0.85:
            category = NoveltyCategory.HIGH_SIMILARITY
        elif max_sim_rounded >= 0.60:
            category = NoveltyCategory.MODERATE_SIMILARITY
        elif max_sim_rounded >= 0.30:
            category = NoveltyCategory.LOW_SIMILARITY
        else:
            category = NoveltyCategory.NO_MATCH_IN_SEARCHED_DATABASE

        return NoveltyAnalysisResult(
            exact_match=exact_match,
            max_tanimoto_similarity=max_sim_rounded,
            closest_known_compound=closest_name,
            novelty_category=category,
            reference_database=database_scope,
            fingerprint_type="Morgan-Radius-2-2048bit"
        )
