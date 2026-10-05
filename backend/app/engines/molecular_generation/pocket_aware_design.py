"""
Structure-Based Pocket-Aware Molecular Design & Pharmacophore Engine
MIKHERB AI - Scientific Integrity Layer

Evaluates target binding pocket geometry, physicochemical features, and residue
composition (from P2Rank / AlphaFold / PDB) to condition de novo generation and
score candidates for shape complementarity, electrostatic matching, and pharmacophore fit.
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, Crippen

logger = logging.getLogger(__name__)

# Amino acid physicochemical classification for binding pocket analysis
POCKET_RESIDUE_PROPERTIES = {
    # Acidic / Negative charge (H-bond acceptors in pocket -> require basic/donor groups in ligand)
    "ASP": {"type": "ACIDIC", "charge": -1, "hbond_acceptor": True, "hbond_donor": False, "aromatic": False, "hydropathy": -3.5},
    "GLU": {"type": "ACIDIC", "charge": -1, "hbond_acceptor": True, "hbond_donor": False, "aromatic": False, "hydropathy": -3.5},
    # Basic / Positive charge (H-bond donors in pocket -> require acidic/acceptor groups in ligand)
    "LYS": {"type": "BASIC", "charge": +1, "hbond_acceptor": False, "hbond_donor": True, "aromatic": False, "hydropathy": -3.9},
    "ARG": {"type": "BASIC", "charge": +1, "hbond_acceptor": False, "hbond_donor": True, "aromatic": False, "hydropathy": -4.5},
    "HIS": {"type": "BASIC", "charge": +0.5, "hbond_acceptor": True, "hbond_donor": True, "aromatic": True, "hydropathy": -3.2},
    # Polar uncharged
    "SER": {"type": "POLAR", "charge": 0, "hbond_acceptor": True, "hbond_donor": True, "aromatic": False, "hydropathy": -0.8},
    "THR": {"type": "POLAR", "charge": 0, "hbond_acceptor": True, "hbond_donor": True, "aromatic": False, "hydropathy": -0.7},
    "ASN": {"type": "POLAR", "charge": 0, "hbond_acceptor": True, "hbond_donor": True, "aromatic": False, "hydropathy": -3.5},
    "GLN": {"type": "POLAR", "charge": 0, "hbond_acceptor": True, "hbond_donor": True, "aromatic": False, "hydropathy": -3.5},
    "CYS": {"type": "POLAR", "charge": 0, "hbond_acceptor": True, "hbond_donor": True, "aromatic": False, "hydropathy": 2.5},
    # Aromatic / Hydrophobic
    "PHE": {"type": "AROMATIC", "charge": 0, "hbond_acceptor": False, "hbond_donor": False, "aromatic": True, "hydropathy": 2.8},
    "TYR": {"type": "AROMATIC", "charge": 0, "hbond_acceptor": True, "hbond_donor": True, "aromatic": True, "hydropathy": -1.3},
    "TRP": {"type": "AROMATIC", "charge": 0, "hbond_acceptor": False, "hbond_donor": True, "aromatic": True, "hydropathy": -0.9},
    # Aliphatic / Hydrophobic
    "ALA": {"type": "ALIPHATIC", "charge": 0, "hbond_acceptor": False, "hbond_donor": False, "aromatic": False, "hydropathy": 1.8},
    "VAL": {"type": "ALIPHATIC", "charge": 0, "hbond_acceptor": False, "hbond_donor": False, "aromatic": False, "hydropathy": 4.2},
    "LEU": {"type": "ALIPHATIC", "charge": 0, "hbond_acceptor": False, "hbond_donor": False, "aromatic": False, "hydropathy": 3.8},
    "ILE": {"type": "ALIPHATIC", "charge": 0, "hbond_acceptor": False, "hbond_donor": False, "aromatic": False, "hydropathy": 4.5},
    "MET": {"type": "ALIPHATIC", "charge": 0, "hbond_acceptor": True, "hbond_donor": False, "aromatic": False, "hydropathy": 1.9},
    "PRO": {"type": "ALIPHATIC", "charge": 0, "hbond_acceptor": False, "hbond_donor": False, "aromatic": False, "hydropathy": -1.6},
    "GLY": {"type": "TINY", "charge": 0, "hbond_acceptor": False, "hbond_donor": False, "aromatic": False, "hydropathy": -0.4}
}


class PocketPharmacophoreAnalyzer:
    """
    Extracts structure-based pharmacophore constraints from pocket 3D coordinates,
    estimated pocket volume/bounding box, and lining residues.
    """

    @staticmethod
    def extract_pocket_features(pocket_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses pocket geometry and residue list into a normalized pharmacophore profile.
        """
        center = pocket_data.get("center") or [0.0, 0.0, 0.0]
        p_score = pocket_data.get("score", 1.0)
        residues = pocket_data.get("residues") or []

        # Estimated pocket volume in Å³
        # Standard herbicide binding pockets range 400 - 1200 Å³
        pocket_volume = pocket_data.get("volume")
        if pocket_volume is None:
            # Estimate volume from residue count or default to typical enzyme active site ~650 Å³
            num_res = len(residues) if isinstance(residues, list) else 15
            pocket_volume = max(350.0, min(1400.0, num_res * 45.0))

        # Analyze residue distribution
        acidic_count = 0
        basic_count = 0
        aromatic_count = 0
        polar_count = 0
        aliphatic_count = 0

        parsed_residues = []
        if isinstance(residues, list):
            for res in residues:
                r_name = str(res).strip().upper()[:3]
                if r_name in POCKET_RESIDUE_PROPERTIES:
                    props = POCKET_RESIDUE_PROPERTIES[r_name]
                    parsed_residues.append(r_name)
                    if props["type"] == "ACIDIC":
                        acidic_count += 1
                    elif props["type"] == "BASIC":
                        basic_count += 1
                    elif props["type"] == "AROMATIC":
                        aromatic_count += 1
                    elif props["type"] == "POLAR":
                        polar_count += 1
                    elif props["type"] == "ALIPHATIC":
                        aliphatic_count += 1

        # Derive target pharmacophore constraints
        # Pockets with basic residues require H-bond acceptors in ligand
        # Pockets with acidic residues require H-bond donors in ligand
        # Pockets with aromatic residues favor pi-stacking (aromatic rings)
        req_hba_min = 2 if basic_count > 0 else 1
        req_hbd_min = 1 if acidic_count > 0 else 0
        req_aromatic_min = 1 if aromatic_count > 0 else 0

        # Maximum ligand molecular volume that fits comfortably in pocket (typically 40-70% of pocket volume)
        max_ligand_volume = pocket_volume * 0.75
        min_ligand_volume = pocket_volume * 0.30

        return {
            "center": center,
            "pocket_score": p_score,
            "pocket_volume_angstrom3": round(pocket_volume, 1),
            "max_ligand_volume_angstrom3": round(max_ligand_volume, 1),
            "min_ligand_volume_angstrom3": round(min_ligand_volume, 1),
            "residue_counts": {
                "acidic": acidic_count,
                "basic": basic_count,
                "aromatic": aromatic_count,
                "polar": polar_count,
                "aliphatic": aliphatic_count
            },
            "pharmacophore_requirements": {
                "recommended_hba_min": req_hba_min,
                "recommended_hbd_min": req_hbd_min,
                "recommended_aromatic_rings_min": req_aromatic_min,
                "optimal_mw_range": (
                    round(min_ligand_volume / 1.3, 1),
                    round(max_ligand_volume / 1.3, 1)
                )
            }
        }

    @classmethod
    def evaluate_molecule_pocket_fit(
        cls,
        mol: Chem.Mol,
        pocket_features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculates structure-based shape and pharmacophore complementarity score
        between a chemical candidate and the target binding pocket.
        """
        if not mol:
            return {
                "pocket_fit_score": 0.0,
                "is_pocket_compatible": False,
                "shape_complementarity": 0.0,
                "electrostatic_complementarity": 0.0,
                "volume_fit_ratio": 0.0,
                "satisfied_interactions": [],
                "warnings": ["INVALID_RDKIT_MOLECULE"]
            }

        mw = Descriptors.MolWt(mol)
        hbd = Descriptors.NumHDonors(mol)
        hba = Descriptors.NumHAcceptors(mol)
        aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        rotatable = Descriptors.NumRotatableBonds(mol)
        clogp = Crippen.MolLogP(mol)

        # Estimate ligand molecular van der Waals volume (approx 1.3 Å³ per Da for organic molecules)
        ligand_vol_est = mw * 1.3

        min_vol = pocket_features.get("min_ligand_volume_angstrom3", 200.0)
        max_vol = pocket_features.get("max_ligand_volume_angstrom3", 700.0)
        pocket_vol = pocket_features.get("pocket_volume_angstrom3", 650.0)

        # 1. Shape / Volume Complementarity
        if ligand_vol_est < min_vol:
            # Under-occupying pocket
            shape_score = max(0.2, ligand_vol_est / min_vol)
        elif ligand_vol_est > max_vol:
            # Steric clash / overflow
            excess = ligand_vol_est - max_vol
            shape_score = max(0.1, 1.0 - (excess / max_vol))
        else:
            # Ideal occupancy range (50-70% pocket volume)
            occupancy = ligand_vol_est / pocket_vol
            shape_score = 1.0 - abs(occupancy - 0.55) * 1.5
            shape_score = max(0.5, min(1.0, shape_score))

        vol_ratio = round(ligand_vol_est / pocket_vol, 3)

        # 2. Electrostatic & Pharmacophore Complementarity
        reqs = pocket_features.get("pharmacophore_requirements", {})
        res_counts = pocket_features.get("residue_counts", {})
        satisfied_interactions = []

        electro_score = 0.5  # neutral baseline

        # Check basic residues (pocket Lys/Arg/His require ligand HBA)
        if res_counts.get("basic", 0) > 0:
            if hba >= reqs.get("recommended_hba_min", 2):
                electro_score += 0.25
                satisfied_interactions.append(f"HBOND_ACCEPTOR_TO_BASIC_RESIDUES (HBA={hba})")
            else:
                electro_score -= 0.15

        # Check acidic residues (pocket Asp/Glu require ligand HBD)
        if res_counts.get("acidic", 0) > 0:
            if hbd >= reqs.get("recommended_hbd_min", 1):
                electro_score += 0.25
                satisfied_interactions.append(f"HBOND_DONOR_TO_ACIDIC_RESIDUES (HBD={hbd})")
            else:
                electro_score -= 0.10

        # Check aromatic residues (pi-pi stacking)
        if res_counts.get("aromatic", 0) > 0:
            if aromatic_rings >= reqs.get("recommended_aromatic_rings_min", 1):
                electro_score += 0.20
                satisfied_interactions.append(f"PI_STACKING_TO_AROMATIC_RESIDUES (AromaticRings={aromatic_rings})")
            else:
                electro_score -= 0.10

        # Flexibility check: excessive rotatable bonds pay entropic penalty upon binding
        if rotatable <= 7:
            electro_score += 0.10
            satisfied_interactions.append(f"FAVORABLE_ENTROPIC_FLEXIBILITY (RotBonds={rotatable})")
        elif rotatable > 10:
            electro_score -= 0.15

        electro_score = max(0.1, min(1.0, electro_score))

        # 3. Overall Pocket Fit Score (weighted combination)
        composite_fit = round(0.50 * shape_score + 0.50 * electro_score, 3)
        is_compatible = composite_fit >= 0.45 and (ligand_vol_est <= max_vol * 1.25)

        warnings = []
        if ligand_vol_est > max_vol:
            warnings.append(f"LIGAND_VOLUME_EXCEEDS_POCKET: {round(ligand_vol_est, 1)} Å³ > {max_vol} Å³")
        if rotatable > 10:
            warnings.append("HIGH_CONFORMATIONAL_ENTROPY_PENALTY")

        return {
            "pocket_fit_score": composite_fit,
            "pocket_compatibility_heuristic": composite_fit,
            "evaluation_type": "POCKET_DERIVED_HEURISTIC",
            "methodology": "Pocket Volume & Residue Physicochemical Complementarity (Heuristic)",
            "is_pocket_compatible": is_compatible,
            "shape_complementarity": round(shape_score, 3),
            "electrostatic_complementarity": round(electro_score, 3),
            "ligand_volume_angstrom3": round(ligand_vol_est, 1),
            "volume_fit_ratio": vol_ratio,
            "satisfied_interactions": satisfied_interactions,
            "warnings": warnings
        }
