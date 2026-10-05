import urllib.parse
import requests
from typing import Dict, Any, List, Optional
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, AllChem, rdMolDescriptors

class ChemicalEngine:
    """RDKit-powered chemical intelligence & Public API adapter (PubChem/ChEMBL)."""

    @staticmethod
    def standardize_smiles(smiles: str) -> Optional[str]:
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            # Standardize & remove salts if any
            return Chem.MolToSmiles(mol, canonical=True)
        except Exception:
            return None

    @staticmethod
    def calculate_descriptors(smiles: str) -> Optional[Dict[str, Any]]:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = Lipinski.NumHDonors(mol)
        hba = Lipinski.NumHAcceptors(mol)
        tpsa = Descriptors.TPSA(mol)
        rotatable = Lipinski.NumRotatableBonds(mol)

        # Lipinski Rule of 5
        lipinski_pass = (mw <= 500) and (logp <= 5) and (hbd <= 5) and (hba <= 10)

        return {
            "canonical_smiles": Chem.MolToSmiles(mol, canonical=True),
            "mw": round(mw, 2),
            "logp": round(logp, 2),
            "hbd": hbd,
            "hba": hba,
            "tpsa": round(tpsa, 2),
            "rotatable_bonds": rotatable,
            "lipinski_pass": lipinski_pass
        }

    @staticmethod
    def compute_tanimoto_similarity(smiles1: str, smiles2: str) -> float:
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

    @staticmethod
    def fetch_pubchem_compound(query: str) -> Optional[Dict[str, Any]]:
        """Fetch compound info from PubChem REST API."""
        try:
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(query)}/property/CanonicalSMILES,MolecularWeight,MolecularFormula/JSON"
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                props = data["PropertyTable"]["Properties"][0]
                return {
                    "cid": str(props.get("CID")),
                    "smiles": props.get("CanonicalSMILES"),
                    "mw": props.get("MolecularWeight"),
                    "formula": props.get("MolecularFormula")
                }
        except Exception:
            pass
        return None

    def build_library(self, initial_compounds: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Build and filter a chemical library with RDKit descriptors."""
        processed = []
        for idx, comp in enumerate(initial_compounds, 1):
            smiles = comp.get("smiles", "")
            code = comp.get("code", f"MH-{idx:06d}")
            desc = self.calculate_descriptors(smiles)
            if desc:
                processed.append({
                    "compound_code": code,
                    "name": comp.get("name", f"Compound-{idx}"),
                    "smiles": smiles,
                    **desc,
                    "novelty_score": round(100.0 - (self.compute_tanimoto_similarity(smiles, "CC(=O)Oc1ccccc1C(=O)O") * 50), 1)
                })
        return processed
