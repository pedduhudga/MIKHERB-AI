import logging
from typing import Dict, Any, List, Tuple, Optional
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, inchi
from app.engines.molecular_generation.schemas import (
    MolecularFilterConfig, ChemicalProperties, FilterItemResult, StructuralAlertScreenResult
)

logger = logging.getLogger(__name__)

# Controlled PAINS & Reactive functional group SMARTS definitions
PAINS_SMARTS = [
    ("quinone_derivative", "[#6]1(=[#8])[#6]=[#6][#6](=[#8])[#6]=[#6]1"),
    ("azo_compound", "[#6]-[#7]=[#7]-[#6]"),
    ("rhodanine_core", "O=C1NC(=S)SC1"),
    ("ene_rhodanine", "O=C1NC(=S)S/C1=C"),
    ("anilino_heterocycle", "c1ccccc1Nc2nccs2"),
    ("catechol", "c1ccc(O)c(O)c1"),
    ("hydroxamic_acid", "C(=O)NO"),
]

REACTIVE_SMARTS = [
    ("acyl_halide", "[CX3](=[OX1])[F,Cl,Br,I]"),
    ("sulfonyl_halide", "[SX4](=[OX1])(=[OX1])[Cl,Br]"),
    ("anhydride", "[CX3](=[OX1])[OX2][CX3](=[OX1])"),
    ("epoxide", "C1OC1"),
    ("aziridine", "C1NC1"),
    ("aliphatic_ester_halide", "[CX4][Cl,Br,I]"),
    ("isocyanate", "N=C=O"),
    ("isothiocyanate", "N=C=S"),
    ("peroxide", "[OX2][OX2]"),
    ("phosphorane", "[PX5]"),
]

COMPILED_PAINS = [(name, Chem.MolFromSmarts(smarts)) for name, smarts in PAINS_SMARTS if Chem.MolFromSmarts(smarts) is not None]
COMPILED_REACTIVE = [(name, Chem.MolFromSmarts(smarts)) for name, smarts in REACTIVE_SMARTS if Chem.MolFromSmarts(smarts) is not None]


class ChemicalValidatorAndFilter:
    """
    RDKit-based chemical validation, descriptor calculation, and property filtering.
    Preserves explicit scientific failure semantics and rejection tracking.
    """

    @staticmethod
    def validate_and_characterize(smiles: str) -> Tuple[bool, str, Optional[str], Optional[str], Optional[str], Optional[str], Optional[Dict[str, Any]], Optional[Chem.Mol]]:
        """
        Validates SMILES string, canonicalizes, derives InChI and InChIKey, and calculates all physicochemical properties.
        
        Returns:
            (is_valid, validation_status, rejection_reason, canonical_smiles, inchi_str, inchikey_str, properties_dict, mol_obj)
        """
        if not smiles or not isinstance(smiles, str) or not smiles.strip():
            return False, "REJECTED", "EMPTY_OR_NON_STRING_SMILES", None, None, None, None, None

        raw_smiles = smiles.strip()
        try:
            mol = Chem.MolFromSmiles(raw_smiles)
        except Exception as e:
            return False, "REJECTED", f"SMILES_PARSE_EXCEPTION: {str(e)}", None, None, None, None, None

        if mol is None:
            return False, "REJECTED", "INVALID_SMILES_CANNOT_PARSE", None, None, None, None, None

        # Check for disconnected components / salts
        frags = Chem.GetMolFrags(mol, asMols=True)
        if len(frags) > 1:
            # Keep the largest organic fragment by heavy atom count
            mol = max(frags, key=lambda m: m.GetNumHeavyAtoms())

        try:
            Chem.SanitizeMol(mol)
        except Exception as e:
            return False, "REJECTED", f"VALENCE_SANITIZATION_FAILED: {str(e)}", None, None, None, None, None

        if mol.GetNumHeavyAtoms() == 0:
            return False, "REJECTED", "NO_HEAVY_ATOMS", None, None, None, None, None

        canonical_smiles = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        try:
            inchi_str = inchi.MolToInchi(mol)
            inchikey_str = inchi.MolToInchiKey(mol)
        except Exception:
            inchi_str = None
            inchikey_str = None

        formula = rdMolDescriptors.CalcMolFormula(mol)
        mw = round(Descriptors.MolWt(mol), 2)
        heavy_atoms = mol.GetNumHeavyAtoms()
        hbd = Descriptors.NumHDonors(mol)
        hba = Descriptors.NumHAcceptors(mol)
        rot_bonds = Descriptors.NumRotatableBonds(mol)
        tpsa = round(Descriptors.TPSA(mol), 2)
        logp = round(Descriptors.MolLogP(mol), 2)
        formal_charge = Chem.GetFormalCharge(mol)
        ring_count = rdMolDescriptors.CalcNumRings(mol)

        props = {
            "molecular_formula": formula,
            "molecular_weight": mw,
            "heavy_atom_count": heavy_atoms,
            "hbd": hbd,
            "hba": hba,
            "rotatable_bonds": rot_bonds,
            "tpsa": tpsa,
            "logp": logp,
            "formal_charge": formal_charge,
            "ring_count": ring_count
        }

        return True, "VALID", None, canonical_smiles, inchi_str, inchikey_str, props, mol

    @staticmethod
    def apply_filters(props: Dict[str, Any], config: MolecularFilterConfig) -> Tuple[bool, List[FilterItemResult]]:
        """Applies configurable property boundaries to characterize candidate drug/herbicide-likeness."""
        results: List[FilterItemResult] = []

        checks = [
            ("molecular_weight", props["molecular_weight"], f"[{config.mw_min}, {config.mw_max}]", config.mw_min <= props["molecular_weight"] <= config.mw_max),
            ("logp", props["logp"], f"[{config.logp_min}, {config.logp_max}]", config.logp_min <= props["logp"] <= config.logp_max),
            ("tpsa", props["tpsa"], f"[{config.tpsa_min}, {config.tpsa_max}]", config.tpsa_min <= props["tpsa"] <= config.tpsa_max),
            ("hbd", props["hbd"], f"<= {config.hbd_max}", props["hbd"] <= config.hbd_max),
            ("hba", props["hba"], f"<= {config.hba_max}", props["hba"] <= config.hba_max),
            ("rotatable_bonds", props["rotatable_bonds"], f"<= {config.rotatable_bonds_max}", props["rotatable_bonds"] <= config.rotatable_bonds_max),
            ("formal_charge", props["formal_charge"], f"[{config.formal_charge_min}, {config.formal_charge_max}]", config.formal_charge_min <= props["formal_charge"] <= config.formal_charge_max),
            ("heavy_atom_count", props["heavy_atom_count"], f"[{config.heavy_atoms_min}, {config.heavy_atoms_max}]", config.heavy_atoms_min <= props["heavy_atom_count"] <= config.heavy_atoms_max),
            ("ring_count", props["ring_count"], f"[{config.ring_count_min}, {config.ring_count_max}]", config.ring_count_min <= props["ring_count"] <= config.ring_count_max),
        ]

        passed_all = True
        for name, val, thresh, passed in checks:
            reason = None if passed else f"{name} ({val}) outside threshold {thresh}"
            if not passed:
                passed_all = False
            results.append(FilterItemResult(
                property=name,
                value=val,
                threshold=thresh,
                passed=passed,
                reason=reason
            ))

        return passed_all, results

    @staticmethod
    def screen_structural_alerts(mol: Chem.Mol, config: MolecularFilterConfig) -> StructuralAlertScreenResult:
        """
        Identifies PAINS and reactive functional group alerts using substructure search.
        Scientific rule: Computational screen only; never equates lack of alerts with proven biological safety.
        """
        detected: List[str] = []

        if config.enable_pains_filter:
            for name, pattern in COMPILED_PAINS:
                if mol.HasSubstructMatch(pattern):
                    detected.append(f"PAINS:{name}")

        if config.enable_reactive_filter:
            for name, pattern in COMPILED_REACTIVE:
                if mol.HasSubstructMatch(pattern):
                    detected.append(f"REACTIVE:{name}")

        passed = len(detected) == 0
        return StructuralAlertScreenResult(
            passed=passed,
            alerts_count=len(detected),
            alerts_detected=detected,
            screen_name="STRUCTURAL_ALERT_SCREEN",
            scientific_disclaimer="Computational structural alert screen only; does not establish biological safety."
        )
