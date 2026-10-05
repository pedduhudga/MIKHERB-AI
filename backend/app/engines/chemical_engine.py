import urllib.parse
import requests
import io
from typing import Dict, Any, List, Optional
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, AllChem, rdMolDescriptors, FilterCatalog

_pains_params = FilterCatalog.FilterCatalogParams()
_pains_params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
PAINS_CATALOG = FilterCatalog.FilterCatalog(_pains_params)

class ChemicalEngine:
    """RDKit-powered chemical intelligence, PubChem/ChEMBL importer, and SDF/CSV parser."""

    REFERENCE_HERBICIDES = {
        "atrazine": "CCNc1nc(nc(n1)Cl)NC(C)C",
        "glyphosate": "C(C(=O)O)NCP(=O)(O)O",
        "2_4_d": "O=C(O)COc1ccc(Cl)cc1Cl",
        "paraquat": "C[n+]1ccc(cc1)c2cc[n+](C)cc2",
        "imazethapyr": "CC1=NC(C(C)C)=NC(=O)C1=C2C=CC(=CC2=O)O",
        "chlorimuron_ethyl": "CCN(C)c1nc(nc(n1)Cl)NS(=O)(=O)c2ccccc2C(=O)OCC"
    }

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
    def remove_salts_get_parent(smiles: str) -> str:
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return smiles
            frags = Chem.GetMolFrags(mol, asMols=True)
            if not frags:
                return smiles
            parent = max(frags, key=lambda f: f.GetNumHeavyAtoms())
            return Chem.MolToSmiles(parent, canonical=True)
        except Exception:
            return smiles

    @staticmethod
    def check_pains_filter(mol: Chem.Mol) -> bool:
        try:
            return not PAINS_CATALOG.HasMatch(mol)
        except Exception:
            return True

    @staticmethod
    def calculate_descriptors(smiles: str) -> Optional[Dict[str, Any]]:
        parent_smiles = ChemicalEngine.remove_salts_get_parent(smiles)
        mol = Chem.MolFromSmiles(parent_smiles)
        if mol is None:
            return None

        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = Lipinski.NumHDonors(mol)
        hba = Lipinski.NumHAcceptors(mol)
        tpsa = Descriptors.TPSA(mol)
        rotatable = Lipinski.NumRotatableBonds(mol)

        lipinski_pass = (mw <= 500) and (logp <= 5) and (hbd <= 5) and (hba <= 10)
        veber_pass = (rotatable <= 10) and (tpsa <= 140.0)
        pains_pass = ChemicalEngine.check_pains_filter(mol)

        return {
            "canonical_smiles": Chem.MolToSmiles(mol, canonical=True),
            "mw": round(mw, 2),
            "logp": round(logp, 2),
            "hbd": hbd,
            "hba": hba,
            "tpsa": round(tpsa, 2),
            "rotatable_bonds": rotatable,
            "lipinski_pass": lipinski_pass,
            "veber_pass": veber_pass,
            "pains_pass": pains_pass
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
        seen_smiles = set()
        for idx, comp in enumerate(initial_compounds, 1):
            smiles = comp.get("smiles", "")
            code = comp.get("code", f"MH-{idx:06d}")
            std_smiles = self.standardize_smiles(smiles)
            if not std_smiles or std_smiles in seen_smiles:
                continue
            seen_smiles.add(std_smiles)

            desc = self.calculate_descriptors(std_smiles)
            if desc:
                max_sim = 0.0
                for ref_smiles in self.REFERENCE_HERBICIDES.values():
                    sim = self.compute_tanimoto_similarity(std_smiles, ref_smiles)
                    if sim > max_sim:
                        max_sim = sim

                struct_dissim = round(max(0.0, min(100.0, (1.0 - max_sim) * 100.0)), 1)

                processed.append({
                    "compound_code": code,
                    "name": comp.get("name", f"Compound-{idx}"),
                    "smiles": std_smiles,
                    **desc,
                    "max_tanimoto_reference_similarity": max_sim,
                    "structural_dissimilarity_score": struct_dissim,
                    "novelty_score": round(max(10.0, 100.0 - (max_sim * 80.0)), 1)
                })
        return processed
