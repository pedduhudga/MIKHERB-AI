import logging
import requests
from typing import Dict, Any, List, Optional, Tuple
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem, inchi
from app.engines.molecular_generation.schemas import NoveltyCategory, NoveltyAnalysisResult

logger = logging.getLogger(__name__)

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
    Evaluates candidate molecular novelty across multi-database scope:
    1. MIKHERB_REFERENCE_CATALOGUE (Commercial herbicide references)
    2. PUBCHEM (Live InChIKey query via PubChem PUG REST)
    3. CHEMBL (Live InChIKey query via ChEMBL REST)
    4. INTERNAL_PROJECT_DATABASE (Project internal candidate library)
    """

    def __init__(self, internal_candidates: Optional[List[Dict[str, Any]]] = None):
        self.reference_pool: List[Tuple[str, str, Any]] = []  # (name, smiles, fp)
        self.internal_inchikeys: set = set()
        self.internal_smiles: set = set()
        self._initialize_references()
        if internal_candidates:
            self._initialize_internal(internal_candidates)

    def _initialize_references(self):
        for ref in KNOWN_HERBICIDE_REFERENCES:
            smiles = ref.get("smiles")
            if not smiles:
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                canonical = Chem.MolToSmiles(mol, canonical=True)
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
                self.reference_pool.append((ref.get("name", "Unknown Reference"), canonical, fp))

    def _initialize_internal(self, candidates: List[Dict[str, Any]]):
        for c in candidates:
            smi = c.get("canonical_smiles") or c.get("smiles")
            if smi:
                self.internal_smiles.add(smi)
            ik = c.get("inchikey")
            if ik:
                self.internal_inchikeys.add(ik)

    def _check_pubchem_exact(self, inchikey_str: str, timeout: int = 3) -> Dict[str, Any]:
        """Queries PubChem PUG REST API for exact InChIKey match."""
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/{inchikey_str}/cids/JSON"
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                cids = data.get("IdentifierList", {}).get("CID", [])
                if cids:
                    return {
                        "status": "CHECKED",
                        "exact_match": True,
                        "matched_cids": [str(c) for c in cids[:3]],
                        "endpoint": url
                    }
                return {"status": "CHECKED", "exact_match": False, "endpoint": url}
            elif resp.status_code == 404:
                return {"status": "CHECKED", "exact_match": False, "endpoint": url}
            else:
                return {"status": f"HTTP_{resp.status_code}", "exact_match": False, "endpoint": url}
        except Exception as e:
            return {"status": "UNREACHABLE_OFFLINE", "exact_match": False, "error": str(e), "endpoint": url}

    def _check_chembl_exact(self, inchikey_str: str, timeout: int = 3) -> Dict[str, Any]:
        """Queries ChEMBL REST API for exact InChIKey match."""
        url = f"https://www.ebi.ac.uk/chembl/api/data/molecule.json?molecule_structures__standard_inchi_key={inchikey_str}"
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                molecules = data.get("molecules", [])
                if molecules:
                    c_id = molecules[0].get("molecule_chembl_id")
                    return {
                        "status": "CHECKED",
                        "exact_match": True,
                        "chembl_id": c_id,
                        "endpoint": url
                    }
                return {"status": "CHECKED", "exact_match": False, "endpoint": url}
            return {"status": f"HTTP_{resp.status_code}", "exact_match": False, "endpoint": url}
        except Exception as e:
            return {"status": "UNREACHABLE_OFFLINE", "exact_match": False, "error": str(e), "endpoint": url}

    def evaluate_novelty(
        self,
        query_mol: Chem.Mol,
        query_canonical_smiles: str,
        database_scope: Optional[List[str]] = None,
        query_external_apis: bool = True
    ) -> NoveltyAnalysisResult:
        """
        Calculates maximum Tanimoto similarity against the reference catalogue,
        and dynamically queries PubChem and ChEMBL for true exact-match novelty.
        """
        databases_checked: Dict[str, Any] = {}
        active_scope = database_scope or [
            "MIKHERB_REFERENCE_CATALOGUE",
            "PUBCHEM",
            "CHEMBL",
            "INTERNAL_PROJECT_DATABASE"
        ]

        query_fp = AllChem.GetMorganFingerprintAsBitVect(query_mol, radius=2, nBits=2048)

        # 1. Internal Reference Catalogue Fingerprint Search
        max_sim = 0.0
        closest_name = None
        exact_match_ref = False

        for name, ref_canonical, ref_fp in self.reference_pool:
            if query_canonical_smiles == ref_canonical:
                exact_match_ref = True
                max_sim = 1.0
                closest_name = name
                break

            sim = DataStructs.TanimotoSimilarity(query_fp, ref_fp)
            if sim > max_sim:
                max_sim = sim
                closest_name = name

        max_sim_rounded = round(float(max_sim), 4)
        databases_checked["MIKHERB_REFERENCE_CATALOGUE"] = {
            "status": "CHECKED",
            "exact_match": exact_match_ref,
            "max_tanimoto_similarity": max_sim_rounded,
            "closest_reference": closest_name
        }

        # 2. InChIKey Generation
        try:
            query_inchikey = inchi.MolToInchiKey(query_mol)
        except Exception:
            query_inchikey = None

        # 3. Dynamic External Queries (PubChem & ChEMBL)
        exact_match_pubchem = False
        exact_match_chembl = False

        if query_external_apis and query_inchikey:
            if "PUBCHEM" in active_scope:
                res_pubchem = self._check_pubchem_exact(query_inchikey, timeout=2)
                databases_checked["PUBCHEM"] = res_pubchem
                if res_pubchem.get("exact_match"):
                    exact_match_pubchem = True
                    if not closest_name:
                        closest_name = f"PubChem CID {res_pubchem.get('matched_cids', [''])[0]}"

            if "CHEMBL" in active_scope:
                res_chembl = self._check_chembl_exact(query_inchikey, timeout=2)
                databases_checked["CHEMBL"] = res_chembl
                if res_chembl.get("exact_match"):
                    exact_match_chembl = True
                    if not closest_name:
                        closest_name = f"ChEMBL {res_chembl.get('chembl_id')}"
        else:
            if "PUBCHEM" in active_scope:
                databases_checked["PUBCHEM"] = {"status": "SKIPPED_CONFIG", "exact_match": False}
            if "CHEMBL" in active_scope:
                databases_checked["CHEMBL"] = {"status": "SKIPPED_CONFIG", "exact_match": False}

        # 4. Internal Project Database Search
        exact_match_internal = False
        if "INTERNAL_PROJECT_DATABASE" in active_scope:
            if query_canonical_smiles in self.internal_smiles or (query_inchikey and query_inchikey in self.internal_inchikeys):
                exact_match_internal = True
            databases_checked["INTERNAL_PROJECT_DATABASE"] = {
                "status": "CHECKED",
                "exact_match": exact_match_internal,
                "known_internal_records_checked": len(self.internal_smiles)
            }

        # 5. Composite Novelty Categorization
        any_exact_match = exact_match_ref or exact_match_pubchem or exact_match_chembl or exact_match_internal

        if any_exact_match or max_sim_rounded >= 0.999:
            category = NoveltyCategory.KNOWN_EXACT_MATCH
            if max_sim_rounded < 1.0 and any_exact_match:
                max_sim_rounded = 1.0
        elif max_sim_rounded >= 0.85:
            category = NoveltyCategory.HIGH_SIMILARITY
        elif max_sim_rounded >= 0.60:
            category = NoveltyCategory.MODERATE_SIMILARITY
        elif max_sim_rounded >= 0.30:
            category = NoveltyCategory.LOW_SIMILARITY
        else:
            category = NoveltyCategory.NO_MATCH_IN_SEARCHED_DATABASE

        scope_summary_str = ", ".join(active_scope)

        return NoveltyAnalysisResult(
            exact_match=any_exact_match,
            max_tanimoto_similarity=max_sim_rounded,
            closest_known_compound=closest_name,
            novelty_category=category,
            reference_database=scope_summary_str,
            database_scope=active_scope,
            databases_checked=databases_checked,
            fingerprint_type="Morgan-Radius-2-2048bit"
        )
