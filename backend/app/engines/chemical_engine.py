import urllib.parse
import json
import urllib.request
from typing import Dict, Any, List, Optional
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, AllChem, SaltRemover
from app.engines.base import BaseScientificEngine

class ChemicalEngine(BaseScientificEngine):
    """RDKit-powered chemical intelligence & Public API adapter (PubChem/ChEMBL)."""

    def __init__(self):
        super().__init__(name="RDKit Chemical Intelligence", category="chemical_intelligence")
        self.salt_remover = SaltRemover.SaltRemover()

    def standardize_smiles(self, smiles: str) -> Optional[str]:
        """Canonicalize SMILES string and strip salts using RDKit."""
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            mol_clean = self.salt_remover.StripMol(mol)
            return Chem.MolToSmiles(mol_clean, canonical=True)
        except Exception:
            return None

    def calculate_descriptors(self, smiles: str) -> Optional[Dict[str, Any]]:
        """Calculate real physicochemical descriptors using RDKit."""
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None

            mw = Descriptors.MolWt(mol)
            logp = Descriptors.MolLogP(mol)
            hbd = Lipinski.NumHDonors(mol)
            hba = Lipinski.NumHAcceptors(mol)
            tpsa = Descriptors.TPSA(mol)
            rotatable = Lipinski.NumRotatableBonds(mol)
            num_rings = Lipinski.RingCount(mol)
            aromatic_rings = Lipinski.NumAromaticRings(mol)

            # Lipinski Rule of 5
            lipinski_pass = (mw <= 500.0) and (logp <= 5.0) and (hbd <= 5) and (hba <= 10)

            canonical = Chem.MolToSmiles(mol, canonical=True)

            return {
                "canonical_smiles": canonical,
                "mw": round(mw, 2),
                "logp": round(logp, 2),
                "hbd": hbd,
                "hba": hba,
                "tpsa": round(tpsa, 2),
                "rotatable_bonds": rotatable,
                "num_rings": num_rings,
                "aromatic_rings": aromatic_rings,
                "lipinski_pass": lipinski_pass
            }
        except Exception:
            return None

    def compute_tanimoto_similarity(self, smiles1: str, smiles2: str) -> float:
        """Calculate Tanimoto similarity using RDKit Morgan fingerprints (ECFP4)."""
        try:
            mol1 = Chem.MolFromSmiles(smiles1)
            mol2 = Chem.MolFromSmiles(smiles2)
            if not mol1 or not mol2:
                return 0.0
            fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=2048)
            fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=2048)

            intersection = (fp1 & fp2).GetNumOnBits()
            union = (fp1 | fp2).GetNumOnBits()
            return round(intersection / union, 3) if union > 0 else 0.0
        except Exception:
            return 0.0

    def fetch_pubchem_compound(self, query: str) -> Optional[Dict[str, Any]]:
        """Fetch compound info from PubChem PUG-REST API."""
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{encoded_query}/property/CanonicalSMILES,MolecularWeight,MolecularFormula/JSON"
            req = urllib.request.Request(url, headers={"User-Agent": "MikHerb-AI/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    props = data["PropertyTable"]["Properties"][0]
                    return {
                        "cid": str(props.get("CID")),
                        "smiles": props.get("CanonicalSMILES"),
                        "mw": props.get("MolecularWeight"),
                        "formula": props.get("MolecularFormula"),
                        "source": "PubChem PUG-REST"
                    }
        except Exception:
            pass
        return None

    def fetch_chembl_herbicide(self, query: str = "ALS inhibitor") -> List[Dict[str, Any]]:
        """Fetch bioactivity/compound data from ChEMBL REST API."""
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/search.json?q={encoded_query}&limit=5"
            req = urllib.request.Request(url, headers={"User-Agent": "MikHerb-AI/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    molecules = data.get("molecules", [])
                    results = []
                    for m in molecules:
                        pref_name = m.get("pref_name") or m.get("molecule_chembl_id")
                        structures = m.get("molecule_structures") or {}
                        smiles = structures.get("canonical_smiles")
                        if smiles:
                            results.append({
                                "chembl_id": m.get("molecule_chembl_id"),
                                "name": pref_name,
                                "smiles": smiles,
                                "source": "ChEMBL REST API"
                            })
                    return results
        except Exception:
            pass
        return []

    def cluster_compounds(self, smiles_list: List[str], similarity_threshold: float = 0.7) -> List[int]:
        """Cluster compounds based on Morgan fingerprint Tanimoto distance matrix."""
        if not smiles_list:
            return []

        fps = []
        for sm in smiles_list:
            m = Chem.MolFromSmiles(sm)
            if m:
                fps.append(AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048))
            else:
                fps.append(None)

        clusters = []
        current_cluster = 1
        cluster_assignments = [-1] * len(smiles_list)

        for i in range(len(smiles_list)):
            if cluster_assignments[i] != -1 or fps[i] is None:
                continue
            cluster_assignments[i] = current_cluster
            for j in range(i + 1, len(smiles_list)):
                if cluster_assignments[j] == -1 and fps[j] is not None:
                    intersection = (fps[i] & fps[j]).GetNumOnBits()
                    union = (fps[i] | fps[j]).GetNumOnBits()
                    sim = intersection / union if union > 0 else 0.0
                    if sim >= similarity_threshold:
                        cluster_assignments[j] = current_cluster
            current_cluster += 1

        return [c if c != -1 else 0 for c in cluster_assignments]

    def build_library(self, initial_compounds: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Build, standardize, filter, and cluster a chemical library using RDKit."""
        processed = []
        smiles_list = []

        for idx, comp in enumerate(initial_compounds, 1):
            raw_smiles = comp.get("smiles", "")
            code = comp.get("code", f"MH-{idx:06d}")
            std_smiles = self.standardize_smiles(raw_smiles) or raw_smiles
            desc = self.calculate_descriptors(std_smiles)

            if desc:
                smiles_list.append(std_smiles)
                # Known reference herbicide: Chlorsulfuron SMILES
                reference_herbicide = "O=S(=O)(Nc1nc(C)nc(OC)n1)c2ccccc2Cl"
                sim_to_ref = self.compute_tanimoto_similarity(std_smiles, reference_herbicide)
                novelty_score = round(max(0.0, min(100.0, (1.0 - sim_to_ref) * 100.0)), 1)

                processed.append({
                    "compound_code": code,
                    "name": comp.get("name", f"Compound-{idx}"),
                    "smiles": std_smiles,
                    **desc,
                    "tanimoto_ref_herbicide_similarity": sim_to_ref,
                    "novelty_score": novelty_score
                })

        cluster_ids = self.cluster_compounds(smiles_list)
        for i, item in enumerate(processed):
            item["cluster_id"] = cluster_ids[i] if i < len(cluster_ids) else 1

        return processed
