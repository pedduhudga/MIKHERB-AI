import urllib.parse
import requests
import io
from typing import Dict, Any, List, Optional
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, AllChem, rdMolDescriptors

class ChemicalEngine:
    """RDKit-powered chemical intelligence, PubChem/ChEMBL importer, and SDF/CSV parser."""

    @staticmethod
    def standardize_smiles(smiles: str) -> Optional[str]:
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            Chem.SanitizeMol(mol)
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
        try:
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(query)}/property/ConnectivitySMILES,CanonicalSMILES,MolecularWeight,MolecularFormula/JSON"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                props = data["PropertyTable"]["Properties"][0]
                smiles = props.get("ConnectivitySMILES") or props.get("CanonicalSMILES")
                return {
                    "cid": str(props.get("CID")),
                    "smiles": smiles,
                    "mw": props.get("MolecularWeight"),
                    "formula": props.get("MolecularFormula")
                }
        except Exception:
            pass
        return None

    @staticmethod
    def parse_sdf_text(sdf_content: str) -> List[Dict[str, str]]:
        compounds = []
        try:
            suppl = Chem.SDMolSupplier()
            suppl.SetData(sdf_content)
            for idx, mol in enumerate(suppl, 1):
                if mol is not None:
                    smiles = Chem.MolToSmiles(mol, canonical=True)
                    name = mol.GetProp("_Name") if mol.HasProp("_Name") else f"SDF_Compound_{idx}"
                    compounds.append({"code": f"SDF-{idx:04d}", "name": name, "smiles": smiles})
        except Exception:
            pass
        return compounds

    def build_library(self, initial_compounds: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        processed = []
        for idx, comp in enumerate(initial_compounds, 1):
            smiles = comp.get("smiles", "")
            code = comp.get("code", f"MH-{idx:06d}")
            desc = self.calculate_descriptors(smiles)
            if desc:
                sim = self.compute_tanimoto_similarity(smiles, "CC(=O)Oc1ccccc1C(=O)O")
                processed.append({
                    "compound_code": code,
                    "name": comp.get("name", f"Compound-{idx}"),
                    "smiles": smiles,
                    **desc,
                    "novelty_score": round(max(10.0, 100.0 - (sim * 80.0)), 1)
                })
        return processed
