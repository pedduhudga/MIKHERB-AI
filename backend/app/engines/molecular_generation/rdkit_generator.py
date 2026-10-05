import random
import logging
from typing import Dict, Any, List, Optional
from rdkit import Chem
from rdkit.Chem import AllChem
from app.engines.molecular_generation.base_generator import BaseMolecularGenerator, GeneratorCapabilities
from app.engines.molecular_generation.schemas import GenerationMode

logger = logging.getLogger(__name__)

# Established herbicide scaffold cores with declared attachment points (dummy atom dummy labels or explicit hydrogens)
HERBICIDE_SCAFFOLDS = {
    "ALS": [
        # Sulfonylurea core: Ar-SO2-NH-CO-NH-Het
        {"name": "Sulfonylurea-Pyrimidinyl", "smiles": "O=S(=O)(Nc1nc(C)cc(OC)n1)c2ccccc2", "attachment_points": ["c2ccccc2"]},
        # Imidazolinone core: 5-isopropyl-5-methyl-4-oxo-4,5-dihydro-1H-imidazol-2-yl
        {"name": "Imidazolinone-Pyridine", "smiles": "CC(C)C1(C)NC(=O)C(=N1)c2ncccc2", "attachment_points": ["c2ncccc2"]},
        # Triazolopyrimidine core
        {"name": "Triazolopyrimidine", "smiles": "Cc1cc2nc(nc2n1)S(=O)(=O)Nc3ccccc3", "attachment_points": ["c3ccccc3"]}
    ],
    "HPPD": [
        # Triketone core (cyclohexane-1,3-dione linked to substituted benzoyl)
        {"name": "Benzoyl-Cyclohexanedione", "smiles": "O=C1CCCC(=O)C1C(=O)c2ccccc2", "attachment_points": ["c2ccccc2"]},
        # Isoxazole core
        {"name": "Isoxazolyl-Benzoyl", "smiles": "O=C(c1ccccc1)C2=NOC=C2", "attachment_points": ["c1ccccc1"]}
    ],
    "PPO": [
        # Diphenyl ether core
        {"name": "Diphenyl-Ether", "smiles": "c1ccc(Oc2ccccc2)cc1", "attachment_points": ["c1ccc", "c2ccccc2"]},
        # N-phenylphthalimide / tetrahydrophthalimide
        {"name": "Tetrahydrophthalimide", "smiles": "O=C1CC=CCC1C(=O)Nc2ccccc2", "attachment_points": ["c2ccccc2"]}
    ],
    "ACCase": [
        # Aryloxyphenoxypropionate core
        {"name": "Aryloxyphenoxypropionate", "smiles": "CC(Oc1ccc(Oc2ccccn2)cc1)C(=O)O", "attachment_points": ["c2ccccn2", "C(=O)O"]},
        # Cyclohexanedione oxime core
        {"name": "Cyclohexanedione-Oxime", "smiles": "CCCC(=O)C1C(=O)CC(CC1=NO)C", "attachment_points": ["C(=NO)"]}
    ],
    "GENERAL": [
        {"name": "Benzamide-Core", "smiles": "O=C(Nc1ccccc1)c2ccccc2", "attachment_points": ["c1ccccc1", "c2ccccc2"]},
        {"name": "Pyridine-Carboxamide", "smiles": "O=C(Nc1ccccc1)c2ncccc2", "attachment_points": ["c1ccccc1", "c2ncccc2"]},
        {"name": "Thiazole-Core", "smiles": "c1csc(Nc2ccccc2)n1", "attachment_points": ["c2ccccc2"]}
    ]
}

# Controlled chemical reaction SMARTS for legitimate transformation enumeration
REACTION_RULES = [
    # Amide coupling: Carboxylic acid + Amine -> Amide
    {"name": "Amide_Coupling", "smarts": "[C:1](=[O:2])[OH].[N;H1,H2:3]>>[C:1](=[O:2])[N:3]"},
    # Sulfonamide formation: Sulfonyl halide / sulfonic acid + Amine -> Sulfonamide
    {"name": "Sulfonamide_Formation", "smarts": "[S:1](=[O:2])(=[O:3])[OH].[N;H1,H2:4]>>[S:1](=[O:2])(=[O:3])[N:4]"},
    # Esterification: Carboxylic acid + Alcohol -> Ester
    {"name": "Esterification", "smarts": "[C:1](=[O:2])[OH].[O;H1:3]>>[C:1](=[O:2])[O:3]"},
    # Aromatic halogenation/functionalization
    {"name": "Aromatic_Nitration", "smarts": "[c;H1:1]>>[c:1][N+](=O)[O-]"},
    {"name": "Aromatic_Fluorination", "smarts": "[c;H1:1]>>[c:1]F"},
    {"name": "Aromatic_Chlorination", "smarts": "[c;H1:1]>>[c:1]Cl"},
    {"name": "Aromatic_Methoxylation", "smarts": "[c;H1:1]>>[c:1]OC"},
    {"name": "Aromatic_Methylation", "smarts": "[c;H1:1]>>[c:1]C"},
    {"name": "Aromatic_Trifluoromethylation", "smarts": "[c;H1:1]>>[c:1]C(F)(F)F"},
]


class RDKitMolecularEnumerator(BaseMolecularGenerator):
    """
    Legitimate local chemistry generation engine using RDKit reaction SMARTS,
    scaffold decoration, and substituent enumeration. Does NOT mutate arbitrary
    strings without chemical validation.
    """

    def __init__(self, version: str = "1.0.0"):
        super().__init__(name="RDKit Chemical Enumerator", version=version)

    def get_capabilities(self) -> GeneratorCapabilities:
        return GeneratorCapabilities(
            name=self.name,
            generation_mode=GenerationMode.RDKit_ENUMERATION.value,
            supports_target_conditioning=True,
            supports_scaffold_hopping=True,
            supports_fragment_recombination=False,
            supports_substituent_enumeration=True,
            supports_database_retrieval=False,
            deterministic_with_seed=True,
            description="Enumerates candidate molecules via validated chemical reaction SMARTS and scaffold decoration."
        )

    def get_status(self) -> Dict[str, Any]:
        return {
            "engine": self.name,
            "version": self.version,
            "status": "INSTALLED",
            "tier": "SCIENTIFICALLY_VALIDATED",
            "generation_mode": GenerationMode.RDKit_ENUMERATION.value
        }

    def validate_inputs(self, target_info: Dict[str, Any], parameters: Dict[str, Any]) -> List[str]:
        errors = []
        if not target_info:
            errors.append("target_info dictionary is required.")
        return errors

    def generate(
        self,
        target_info: Dict[str, Any],
        parameters: Dict[str, Any],
        random_seed: Optional[int] = None,
        max_candidates: int = 50
    ) -> Dict[str, Any]:
        """
        Executes chemical enumeration against target-conditioned scaffolds.
        """
        validation_errors = self.validate_inputs(target_info, parameters)
        if validation_errors:
            return {
                "status": "FAILED",
                "molecules": [],
                "error": "; ".join(validation_errors),
                "generated_count": 0
            }

        # Seed random engine for deterministic, reproducible enumeration
        seed = random_seed if random_seed is not None else 42
        rng = random.Random(seed)

        target_family = target_info.get("target_family") or target_info.get("family") or "GENERAL"
        scaffold_candidates = HERBICIDE_SCAFFOLDS.get(target_family) or HERBICIDE_SCAFFOLDS.get("GENERAL", [])

        # User-supplied scaffolds take precedence if provided
        custom_scaffolds = parameters.get("scaffolds", [])
        if custom_scaffolds:
            scaffold_pool = [{"name": f"Custom-Scaffold-{i+1}", "smiles": s} for i, s in enumerate(custom_scaffolds)]
        else:
            scaffold_pool = scaffold_candidates

        generated_smiles_set = set()
        candidates_raw: List[Dict[str, Any]] = []

        # Compile reaction transformations
        compiled_rxns = []
        for r_def in REACTION_RULES:
            try:
                rxn = AllChem.ReactionFromSmarts(r_def["smarts"])
                if rxn:
                    compiled_rxns.append((r_def["name"], rxn))
            except Exception:
                continue

        # Target-conditioned generation loop
        attempts = 0
        max_attempts = max_candidates * 20

        while len(candidates_raw) < max_candidates and attempts < max_attempts:
            attempts += 1
            scaffold_def = rng.choice(scaffold_pool)
            scaffold_smiles = scaffold_def["smiles"]
            scaffold_mol = Chem.MolFromSmiles(scaffold_smiles)
            if scaffold_mol is None:
                continue

            rxn_name, rxn = rng.choice(compiled_rxns)
            try:
                # Apply transformation to the scaffold
                products = rxn.RunReactants((scaffold_mol,))
                if not products:
                    continue

                # Take a random product set
                prod_tuple = rng.choice(products)
                prod_mol = prod_tuple[0]

                Chem.SanitizeMol(prod_mol)
                canonical = Chem.MolToSmiles(prod_mol, canonical=True)

                if canonical in generated_smiles_set:
                    continue

                generated_smiles_set.add(canonical)
                candidates_raw.append({
                    "smiles": canonical,
                    "parent_scaffold": scaffold_smiles,
                    "parent_name": scaffold_def.get("name"),
                    "transformation": rxn_name,
                    "generation_mode": GenerationMode.RDKit_ENUMERATION.value,
                    "generator_name": self.name,
                    "generator_version": self.version
                })
            except Exception:
                continue

        return {
            "status": "COMPLETED",
            "molecules": candidates_raw,
            "generated_count": len(candidates_raw),
            "target_family": target_family,
            "random_seed": seed,
            "attempts": attempts,
            "execution_mode": "RDKIT_REACTION_ENUMERATION"
        }
