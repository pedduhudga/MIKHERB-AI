import datetime
import os
import traceback
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.models.models import Project, PipelineStage, TargetProtein, ChemicalLibrary, Compound, Candidate
from app.engines.protein_engine import ProteinEngine, P2RankPocketPredictor
from app.engines.chemical_engine import ChemicalEngine
from app.engines.docking_engine import AIDockingEngine
from app.engines.selectivity_engine import CropSelectivityEngine
from app.engines.consensus_engine import MikHerbConsensusScoreEngine
from app.engines.target_discovery_engine import MultiTargetDiscoveryEngine, _fetch_fasta_seq
from app.core.provenance import generate_provenance_record, save_provenance_file
from app.core.firebase import sync_db_project_to_firestore
from app.services.report_service import ReportGenerator

DEFAULT_STAGES = [
    (1, "Multi-Target Discovery & Structure Acquisition"),
    (2, "Binding Pocket Prediction"),
    (3, "Chemical Library Acquisition & RDKit Cleaning"),
    (4, "Boltz-2 & GNINA AI Docking Screening"),
    (5, "Weed vs Crop Selectivity Analysis"),
    (6, "Safety, Toxicity & Novelty Screening"),
    (7, "Consensus Candidate Ranking & Report Generation")
]

# Known UniProt accessions for quick lookup (supplements dynamic UniProt search)
SPECIES_UNIPROT_MAP = {
    # Weed targets (ALS gene, verified active entries)
    "palmer amaranth": "A0A890DLI3",
    "amaranthus palmeri": "A0A890DLI3",
    # Crop homologs (ALS, verified active plant accessions)
    "soybean": "U5JC63",
    "glycine max": "U5JC63",
    "corn": "Q41768",
    "maize": "Q41768",
    "zea mays": "Q41768",
    "rice": "Q6K2E8",
    "oryza sativa": "Q6K2E8",
    "arabidopsis": "P17597",
    "wheat": "A0A3B6PRC5",
    "triticum aestivum": "A0A3B6PRC5"
}

# Target gene search priority for single-target fallback
TARGET_GENE_PRIORITY = ["ALS", "HPPD", "PPO", "EPSPS", "ACCase", "psbA", "PDS", "GS", "DXS"]


def resolve_uniprot_accession(species_name: str) -> Optional[str]:
    """Resolves the primary weed target accession using map lookup, then UniProt multi-gene search."""
    s_clean = species_name.lower().strip()
    for key, acc in SPECIES_UNIPROT_MAP.items():
        if key in s_clean:
            return acc

    # Dynamic multi-gene search: try each gene in priority order
    return ProteinEngine.search_uniprot_accession(species_name, TARGET_GENE_PRIORITY)


class DiscoveryPipelineRunner:
    def __init__(self, db: Session):
        self.db = db
        self.protein_engine = ProteinEngine()
        self.chemical_engine = ChemicalEngine()
        self.docking_engine = AIDockingEngine()
        self.selectivity_engine = CropSelectivityEngine()
        self.consensus_engine = MikHerbConsensusScoreEngine()

    def initialize_project_pipeline(self, project_id: int):
        existing_stages = self.db.query(PipelineStage).filter_by(project_id=project_id).all()
        if not existing_stages:
            for order, name in DEFAULT_STAGES:
                stage = PipelineStage(
                    project_id=project_id,
                    stage_name=name,
                    stage_order=order,
                    status="pending"
                )
                self.db.add(stage)
            self.db.commit()

    def run_pipeline(self, project_id: int):
        project = self.db.query(Project).filter_by(id=project_id).first()
        if not project:
            return {"error": "Project not found"}

        self.initialize_project_pipeline(project_id)
        stages = self.db.query(PipelineStage).filter_by(project_id=project_id).order_by(PipelineStage.stage_order).all()

        for stage in stages:
            if stage.status == "completed":
                continue

            stage.status = "running"
            stage.started_at = datetime.datetime.utcnow()
            self.db.commit()

            try:
                summary = self._execute_stage(project, stage)
                stage.status = "completed"
                stage.results_summary = summary
                stage.completed_at = datetime.datetime.utcnow()
                self.db.commit()
            except Exception as e:
                stage.status = "failed"
                stage.error_message = str(e) + "\n" + traceback.format_exc()
                self.db.commit()
                project.status = "failed"
                self.db.commit()
                sync_db_project_to_firestore(project_id, self.db)
                return {"status": "FAILED", "failed_stage": stage.stage_name, "error": str(e)}

        project.status = "completed"
        self.db.commit()
        sync_db_project_to_firestore(project_id, self.db)
        return {"status": "COMPLETED", "project_id": project_id}

    def _execute_stage(self, project: Project, stage: PipelineStage) -> dict:
        order = stage.stage_order

        # ---------------------------------------------------------------
        # STAGE 1 — Multi-Target Discovery & Structure Acquisition
        # ---------------------------------------------------------------
        if order == 1:
            # --- 1a. Discover ALL candidate herbicide targets ---
            discovery_engine = MultiTargetDiscoveryEngine(crop_species=project.crop_species)
            all_targets = discovery_engine.discover_targets(
                weed_species=project.weed_species,
                max_targets=10,
                require_alphafold=False,
            )

            # Store discovery summary in stage results before selecting best
            target_discovery_summary = [
                {
                    "rank": idx + 1,
                    "gene": t["gene"],
                    "family": t["family"],
                    "weed_uniprot_id": t["weed_uniprot_id"],
                    "alphafold_available": t["alphafold_available"],
                    "plddt_avg": t["plddt_avg"],
                    "sequence_identity_pct": t["sequence_identity_pct"],
                    "crop_divergence_pct": t["crop_divergence_pct"],
                    "crop_selectivity_potential": t["crop_selectivity_potential"],
                    "essentiality_score": t.get("essentiality_score"),
                    "target_opportunity_score": t["target_opportunity_score"],
                    "herbicide_classes": t["herbicide_classes"],
                    "resistance_reported": t["resistance_reported"],
                    "evidence_status": t["evidence_status"],
                }
                for idx, t in enumerate(all_targets)
            ]

            # --- 1b. Select best validated target with AlphaFold structure ---
            best_target = None
            for candidate in all_targets:
                if candidate.get("weed_uniprot_id") and candidate.get("alphafold_available"):
                    best_target = candidate
                    break

            # Fall back to best with UniProt accession (even without AlphaFold)
            if not best_target:
                for candidate in all_targets:
                    if candidate.get("weed_uniprot_id"):
                        best_target = candidate
                        break

            if not best_target or not best_target.get("weed_uniprot_id"):
                raise ValueError(
                    f"No validated target accession found for weed species '{project.weed_species}'. "
                    f"Discovered targets: {[t['gene'] for t in all_targets]}. "
                    "Please verify species name or provide a UniProt ID directly."
                )

            weed_uniprot = best_target["weed_uniprot_id"]
            gene_selected = best_target["gene"]

            # --- 1c. Fetch structure and pocket data for the best target ---
            target_info = self.protein_engine.get_protein_info(
                weed_uniprot,
                f"{project.weed_species} {gene_selected} Target"
            )

            # --- 1d. Crop homolog structure ---
            crop_uniprot = best_target.get("crop_uniprot_id")
            if not crop_uniprot:
                # Fallback: look up in map
                c_clean = project.crop_species.lower().strip()
                for key, acc in SPECIES_UNIPROT_MAP.items():
                    if key in c_clean:
                        crop_uniprot = acc
                        break

            crop_pdb_path = None
            crop_seq = None
            crop_pockets = None
            crop_status = "NOT_ATTEMPTED"
            crop_error_reason = None

            if crop_uniprot:
                try:
                    crop_info = self.protein_engine.get_protein_info(crop_uniprot, f"{project.crop_species} Homolog")
                    crop_seq = crop_info["sequence"]
                    crop_pdb_path = crop_info["pdb_path"]
                    crop_pockets = crop_info["pockets"]
                    crop_status = "FETCH_SUCCESSFUL"
                except Exception as e:
                    crop_status = "ALPHAFOLD_STRUCTURE_UNAVAILABLE"
                    crop_error_reason = str(e)
            else:
                crop_status = "CROP_ACCESSION_UNRESOLVED"
                crop_error_reason = f"No UniProt accession found for crop species '{project.crop_species}'."

            # --- 1e. Persist ALL discovered targets as independent TargetProtein records ---
            # Clear existing targets for this project if re-running
            self.db.query(TargetProtein).filter_by(project_id=project.id).delete()

            selected_db_target = None
            for idx, candidate in enumerate(all_targets):
                is_selected = (candidate.get("gene") == gene_selected)
                t_plddt = candidate.get("plddt_avg")
                if is_selected and t_plddt is None and target_info.get("pockets"):
                    t_plddt = target_info["pockets"][0].get("plddt_avg")

                t_crop_acc = candidate.get("crop_uniprot_id")
                if is_selected and not t_crop_acc:
                    t_crop_acc = crop_uniprot

                t_pdb_path = target_info["pdb_path"] if is_selected else None
                t_crop_pdb = crop_pdb_path if is_selected else None
                t_pockets = target_info["pockets"] if is_selected else None
                t_weed_seq = target_info["sequence"] if is_selected else _fetch_fasta_seq(candidate.get("weed_uniprot_id")) if candidate.get("weed_uniprot_id") else None

                target_row = TargetProtein(
                    project_id=project.id,
                    name=f"{project.weed_species} {candidate['gene']} ({candidate['family']})",
                    rank=idx + 1,
                    is_primary_selected=is_selected,
                    gene=candidate["gene"],
                    target_family=candidate["family"],
                    target_evidence_score=candidate.get("target_evidence_score"),
                    target_evidence_confidence=candidate.get("target_evidence_confidence"),
                    essentiality_status=candidate.get("essentiality_status"),
                    essentiality_evidence_level=candidate.get("essentiality_evidence_level"),
                    species_specific_essentiality=candidate.get("species_specific_essentiality", False),
                    alignment_status=candidate.get("alignment_status"),
                    alignment_method=candidate.get("alignment_method"),
                    alignment_coverage_pct=candidate.get("alignment_coverage"),
                    weed_coverage_pct=candidate.get("weed_coverage_pct"),
                    crop_coverage_pct=candidate.get("crop_coverage_pct"),
                    identity_over_aligned_pct=candidate.get("identity_over_aligned_pct"),
                    uniprot_id=candidate.get("weed_uniprot_id"),
                    weed_sequence=t_weed_seq,
                    crop_homolog_uniprot_id=t_crop_acc,
                    crop_sequence=crop_seq if is_selected else None,
                    pdb_id=t_pdb_path,
                    alphafold_id=f"AF-{candidate['weed_uniprot_id']}-F1" if candidate.get("weed_uniprot_id") else None,
                    essentiality_score=candidate.get("essentiality_score"),
                    structure_confidence=t_plddt,
                    crop_divergence_score=candidate.get("crop_divergence_pct"),
                    total_opportunity_score=candidate.get("target_opportunity_score"),
                    pockets_json=t_pockets,
                    analysis_json={
                        "gene_selected": candidate["gene"],
                        "gene_family": candidate.get("family"),
                        "rank": idx + 1,
                        "is_primary_selected": is_selected,
                        "target_evidence_score": candidate.get("target_evidence_score"),
                        "target_evidence_confidence": candidate.get("target_evidence_confidence"),
                        "herbicide_classes": candidate.get("herbicide_classes"),
                        "resistance_reported": candidate.get("resistance_reported"),
                        "essentiality_status": candidate.get("essentiality_status"),
                        "essentiality_evidence_level": candidate.get("essentiality_evidence_level"),
                        "species_specific_essentiality": candidate.get("species_specific_essentiality"),
                        "essentiality_evidence": candidate.get("essentiality_evidence"),
                        "essentiality_source": candidate.get("essentiality_source"),
                        "alignment_status": candidate.get("alignment_status"),
                        "sequence_identity_pct": candidate.get("sequence_identity_pct"),
                        "alignment_coverage": candidate.get("alignment_coverage"),
                        "weed_coverage_pct": candidate.get("weed_coverage_pct"),
                        "crop_coverage_pct": candidate.get("crop_coverage_pct"),
                        "identity_over_aligned_pct": candidate.get("identity_over_aligned_pct"),
                        "alignment_method": candidate.get("alignment_method"),
                        "bit_score": candidate.get("bit_score"),
                        "crop_selectivity_potential": candidate.get("crop_selectivity_potential"),
                        "crop_pdb_path": t_crop_pdb,
                        "crop_pockets": crop_pockets if is_selected else None,
                        "crop_status": crop_status if is_selected else "NOT_ATTEMPTED",
                        "crop_error_reason": crop_error_reason if is_selected else None,
                        "all_targets_discovered": target_discovery_summary,
                    }
                )
                self.db.add(target_row)
                if is_selected:
                    selected_db_target = target_row

            self.db.commit()
            if selected_db_target:
                self.db.refresh(selected_db_target)

            return {
                "target_id": selected_db_target.id if selected_db_target else None,
                "gene_selected": gene_selected,
                "execution_mode": "MULTI_TARGET_DISCOVERY_SINGLE_TARGET_EXECUTION",
                "all_targets_discovered_count": len(all_targets),
                "targets_with_structure": sum(1 for t in all_targets if t.get("alphafold_available")),
                "top_ranked_targets": target_discovery_summary[:5],
                "weed_uniprot_id": selected_db_target.uniprot_id if selected_db_target else None,
                "crop_uniprot_id": crop_uniprot,
                "weed_pdb_path": target_info["pdb_path"],
                "crop_pdb_path": crop_pdb_path,
                "crop_status": crop_status,
                "crop_error_reason": crop_error_reason,
                "plddt_avg": selected_db_target.structure_confidence if selected_db_target else None,
                "sequence_length": len(target_info["sequence"])
            }

        # ---------------------------------------------------------------
        # STAGE 2 — Binding Pocket Prediction
        # ---------------------------------------------------------------
        elif order == 2:
            target = self.db.query(TargetProtein).filter_by(project_id=project.id, is_primary_selected=True).first()
            if not target:
                target = self.db.query(TargetProtein).filter_by(project_id=project.id).first()
            if not target or not target.pdb_id or not os.path.exists(target.pdb_id):
                raise FileNotFoundError("Target protein structure PDB file unavailable for pocket prediction.")

            pockets = target.pockets_json if target.pockets_json else []
            is_native = pockets and pockets[0].get("status") == "COMPLETED"
            return {
                "pocket_count": len(pockets) if is_native else 0,
                "primary_pocket": pockets[0] if is_native else None,
                "pocket_predictor_status": pockets[0].get("status") if pockets else "NO_POCKETS",
                "message": "P2Rank native pockets predicted successfully" if is_native else "P2Rank binary not installed; heuristic centroid only."
            }

        # ---------------------------------------------------------------
        # STAGE 3 — Chemical Library Acquisition & RDKit Cleaning
        # ---------------------------------------------------------------
        elif order == 3:
            real_herbicide_queries = [
                # ALS / AHAS Inhibitors
                "Imazethapyr", "Chlorimuron-ethyl", "Sulfometuron-methyl", "Flumetsulam", "Florasulam",
                "Pyrithiobac", "Bispyribac", "Penoxsulam", "Chlorsulfuron", "Imazapyr",
                # HPPD Inhibitors
                "Mesotrione", "Isoxaflutole", "Tembotrione",
                # PPO Inhibitors
                "Flumioxazin", "Fomesafen", "Sulfentrazone",
                # EPSPS & PSII References
                "Glyphosate", "Atrazine", "Metribuzin"
            ]

            raw_compounds = []
            for q in real_herbicide_queries:
                p_data = self.chemical_engine.fetch_pubchem_compound(q)
                if p_data and p_data.get("smiles"):
                    raw_compounds.append({
                        "code": f"PUBCHEM-CID-{p_data.get('cid', 'UNK')}",
                        "name": f"{q} (PubChem CID {p_data.get('cid')})",
                        "smiles": p_data["smiles"]
                    })

            if len(raw_compounds) < 5:
                curated_real_compounds = [
                    {"code": "PUBCHEM-CID-3725", "name": "Imazethapyr (ALS Inhibitor)", "smiles": "CC1=NC(C(C)C)=NC(=O)C1=C2C=CC(=CC2=O)O"},
                    {"code": "PUBCHEM-CID-54890", "name": "Chlorimuron-ethyl (ALS Inhibitor)", "smiles": "CCN(C)c1nc(nc(n1)Cl)NS(=O)(=O)c2ccccc2C(=O)OCC"},
                    {"code": "PUBCHEM-CID-5311", "name": "Sulfometuron-methyl (ALS Inhibitor)", "smiles": "CC1=NC(=NC(=N1)NC(=O)NS(=O)(=O)C2=CC=CC=C2C(=O)OC)C"},
                    {"code": "PUBCHEM-CID-91684", "name": "Flumetsulam (ALS Inhibitor)", "smiles": "Cc1cc(F)cc(c1)n2nc3nc(nc3n2)S(=O)(=O)Nc4c(F)cccc4F"},
                    {"code": "PUBCHEM-CID-115132", "name": "Florasulam (ALS Inhibitor)", "smiles": "COc1cc2nc(nc2n1)S(=O)(=O)Nc3c(F)cc(F)c(F)c3F"},
                    {"code": "PUBCHEM-CID-3723", "name": "Imazapyr (ALS Inhibitor)", "smiles": "CC(C)C1(NC(=O)C2=NC=CC=C21)C(=O)O"},
                    {"code": "PUBCHEM-CID-17596", "name": "Mesotrione (HPPD Inhibitor)", "smiles": "CS(=O)(=O)c1ccc(c(c1)N(=O)=O)C(=O)C2C(=O)CCCC2=O"},
                    {"code": "PUBCHEM-CID-92425", "name": "Flumioxazin (PPO Inhibitor)", "smiles": "CC1=CC(=O)C2=C(C=C1)N(C(=O)O2)C3=CC(=C(C=C3F)Cl)F"},
                    {"code": "PUBCHEM-CID-60196", "name": "Glyphosate Reference", "smiles": "C(C(=O)O)NCP(=O)(O)O"},
                    {"code": "PUBCHEM-CID-2256", "name": "Atrazine Reference", "smiles": "CCNc1nc(nc(n1)Cl)NC(C)C"}
                ]
                for comp in curated_real_compounds:
                    if not any(c["code"] == comp["code"] for c in raw_compounds):
                        raw_compounds.append(comp)

            processed_comps = self.chemical_engine.build_library(raw_compounds)

            library = ChemicalLibrary(name=f"Multi-Target Real Chemical Discovery Library for Project {project.name}", compound_count=len(processed_comps))
            self.db.add(library)
            self.db.commit()

            for c_data in processed_comps:
                comp = Compound(
                    library_id=library.id,
                    compound_code=c_data["compound_code"],
                    name=c_data["name"],
                    smiles=c_data["smiles"],
                    canonical_smiles=c_data["canonical_smiles"],
                    mw=c_data["mw"],
                    logp=c_data["logp"],
                    hbd=c_data["hbd"],
                    hba=c_data["hba"],
                    tpsa=c_data["tpsa"],
                    lipinski_pass=c_data["lipinski_pass"],
                    novelty_score=c_data["structural_dissimilarity_score"]  # Use dissimilarity, not novelty alias
                )
                self.db.add(comp)
            self.db.commit()
            return {
                "library_id": library.id,
                "compounds_screened": len(processed_comps),
                "source": "PubChem & Multi-Target Real Chemical Database",
                "filters_applied": ["Salt Removal", "PAINS Filter", "Morgan Fingerprints", "SMILES Deduplication"]
            }

        # ---------------------------------------------------------------
        # STAGE 4 — Boltz-2 & GNINA AI Docking Screening
        # ---------------------------------------------------------------
        elif order == 4:
            target = self.db.query(TargetProtein).filter_by(project_id=project.id, is_primary_selected=True).first()
            if not target:
                target = self.db.query(TargetProtein).filter_by(project_id=project.id).first()
            compounds = self.db.query(Compound).all()

            pockets = target.pockets_json or []
            if not pockets or pockets[0].get("status") != "COMPLETED" or not pockets[0].get("center"):
                return {
                    "status": "P2RANK_POCKET_ENGINE_NOT_INSTALLED",
                    "docking_completed_count": 0,
                    "message": "P2Rank native binary not installed. Pocket prediction required before native AI docking."
                }

            pocket_center = pockets[0]["center"]
            weed_pdb_path = target.pdb_id

            docking_results = []
            for comp in compounds:
                res = self.docking_engine.screen_candidate(weed_pdb_path, comp.smiles, pocket_center)
                docking_results.append({
                    "compound_code": comp.compound_code,
                    "smiles": comp.smiles,
                    "boltz_status": res["boltz"].get("status"),
                    "boltz_pKd": res["boltz"].get("pKd_predicted"),
                    "gnina_status": res["gnina"].get("status"),
                    "gnina_affinity": res["gnina"].get("affinity_kcal_mol"),
                    "pose_agreement": res["pose_agreement"],
                    "gnina_mode": res["gnina"].get("execution_mode")
                })
            return {"docking_completed_count": len(docking_results), "top_docking": docking_results[0] if docking_results else None}

        # ---------------------------------------------------------------
        # STAGE 5 — Weed vs Crop Selectivity Analysis
        # ---------------------------------------------------------------
        elif order == 5:
            target = self.db.query(TargetProtein).filter_by(project_id=project.id, is_primary_selected=True).first()
            if not target:
                target = self.db.query(TargetProtein).filter_by(project_id=project.id).first()
            compounds = self.db.query(Compound).all()

            weed_pockets = target.pockets_json or []
            is_weed_p2rank = weed_pockets and weed_pockets[0].get("status") == "COMPLETED"
            weed_pocket_center = weed_pockets[0]["center"] if is_weed_p2rank and weed_pockets[0].get("center") else None
            weed_pdb_path = target.pdb_id

            crop_pdb_path = target.analysis_json.get("crop_pdb_path") if target.analysis_json else None
            crop_pockets = target.analysis_json.get("crop_pockets") if target.analysis_json else None
            is_crop_p2rank = crop_pockets and crop_pockets[0].get("status") == "COMPLETED"
            crop_pocket_center = crop_pockets[0]["center"] if is_crop_p2rank and crop_pockets[0].get("center") else None

            selectivity_results = []
            if weed_pocket_center and crop_pdb_path and os.path.exists(crop_pdb_path) and crop_pocket_center and target.crop_sequence:
                for comp in compounds:
                    weed_dock = self.docking_engine.screen_candidate(weed_pdb_path, comp.smiles, weed_pocket_center)
                    crop_dock = self.docking_engine.screen_candidate(crop_pdb_path, comp.smiles, crop_pocket_center)

                    weed_pKd = weed_dock["boltz"].get("pKd_predicted") if weed_dock["boltz"].get("status") == "COMPLETED" else None
                    weed_gnina_aff = weed_dock["gnina"].get("affinity_kcal_mol") if weed_dock["gnina"].get("status") == "COMPLETED" else None

                    crop_pKd = crop_dock["boltz"].get("pKd_predicted") if crop_dock["boltz"].get("status") == "COMPLETED" else None
                    crop_gnina_aff = crop_dock["gnina"].get("affinity_kcal_mol") if crop_dock["gnina"].get("status") == "COMPLETED" else None

                    if weed_pKd is not None and crop_pKd is not None:
                        sel_res = self.selectivity_engine.evaluate_selectivity(
                            target.weed_sequence, target.crop_sequence, weed_affinity_pKd=weed_pKd, crop_affinity_pKd=crop_pKd
                        )
                        selectivity_results.append({
                            "compound_code": comp.compound_code,
                            "method": "Boltz-2 pKd Comparison",
                            "weed_pKd": round(weed_pKd, 2),
                            "crop_pKd": round(crop_pKd, 2),
                            "selectivity_score": sel_res["selectivity_score"],
                            "fold_difference": sel_res["selectivity_fold_difference"],
                            "status": "COMPLETED"
                        })
                    elif weed_gnina_aff is not None and crop_gnina_aff is not None:
                        aff_diff = abs(weed_gnina_aff) - abs(crop_gnina_aff)
                        sel_score = min(100.0, max(0.0, 50.0 + (aff_diff * 15.0)))
                        selectivity_results.append({
                            "compound_code": comp.compound_code,
                            "method": "GNINA kcal/mol Comparison",
                            "weed_affinity_kcal": weed_gnina_aff,
                            "crop_affinity_kcal": crop_gnina_aff,
                            "selectivity_score": round(sel_score, 1),
                            "status": "COMPLETED"
                        })
                    else:
                        selectivity_results.append({
                            "compound_code": comp.compound_code,
                            "weed_pKd": None,
                            "crop_pKd": None,
                            "selectivity_score": None,  # Preserve None — not 0.0
                            "status": "SELECTIVITY_NOT_AVAILABLE_MISSING_DOCKING"
                        })
            else:
                crop_err = target.analysis_json.get("crop_error_reason", "Crop structure or native pocket missing") if target.analysis_json else "Crop structure or native pocket missing"
                for comp in compounds:
                    selectivity_results.append({
                        "compound_code": comp.compound_code,
                        "weed_pKd": None,
                        "crop_pKd": None,
                        "selectivity_score": None,  # Preserve None — scientifically unknown
                        "status": "SELECTIVITY_NOT_AVAILABLE_CROP_STRUCTURE_MISSING",
                        "reason": crop_err
                    })

            return {"dual_docking_selectivity": selectivity_results, "top_selectivity": selectivity_results[0] if selectivity_results else None}

        # ---------------------------------------------------------------
        # STAGE 6 — Safety, Toxicity & Novelty Screening
        # ---------------------------------------------------------------
        elif order == 6:
            compounds = self.db.query(Compound).all()
            safety_records = []
            for comp in compounds:
                logkoc = round(0.81 * (comp.logp or 2.0) + 0.10, 2) if comp.logp is not None else None
                aquatic_mobility = ("HIGH" if logkoc < 2.0 else "MODERATE") if logkoc is not None else "UNKNOWN"

                # FIX: predictive_flag is NOT used as safety evidence in consensus scoring.
                # It is preserved as a screening indicator with explicit uncertainty labelling.
                predictive_aquatic_concern = (
                    "PREDICTIVE_CONCERN_HIGH_MOBILITY"
                    if aquatic_mobility == "HIGH"
                    else ("PREDICTIVE_LOW_CONCERN" if aquatic_mobility == "MODERATE" else "UNKNOWN")
                )

                safety_records.append({
                    "compound_code":                comp.compound_code,
                    "safety_status":                "PREDICTIVE_SCREEN_ONLY",
                    "experimental_safety":          "UNKNOWN_REQUIRES_ASSAY",
                    "mammalian_toxicity":           "UNKNOWN_REQUIRES_ASSAY",
                    "bee_pollinator_concern":       "UNKNOWN_NO_PUBLIC_ALERT",
                    "aquatic_mobility_LogKoc_prediction": logkoc,
                    "aquatic_mobility_class":       aquatic_mobility,
                    "predictive_aquatic_concern":   predictive_aquatic_concern,
                    "structural_dissimilarity":     round(comp.novelty_score, 1) if comp.novelty_score is not None else None,
                    "evidence_level":               "PREDICTED_HEURISTIC",
                    # Removed 'safety_clean' boolean — not used as evidence in consensus
                })
            return {"safety_screened": len(compounds), "safety_records": safety_records}

        # ---------------------------------------------------------------
        # STAGE 7 — Consensus Candidate Ranking & Report Generation
        # ---------------------------------------------------------------
        elif order == 7:
            target = self.db.query(TargetProtein).filter_by(project_id=project.id, is_primary_selected=True).first()
            if not target:
                target = self.db.query(TargetProtein).filter_by(project_id=project.id).first()
            compounds = self.db.query(Compound).all()
            stage5 = self.db.query(PipelineStage).filter_by(project_id=project.id, stage_order=5).first()
            stage6 = self.db.query(PipelineStage).filter_by(project_id=project.id, stage_order=6).first()

            selectivity_map: Dict[str, Optional[float]] = {}
            if stage5 and stage5.results_summary and stage5.results_summary.get("dual_docking_selectivity"):
                for sel in stage5.results_summary["dual_docking_selectivity"]:
                    # Preserve None — don't coerce to 0.0
                    selectivity_map[sel["compound_code"]] = sel.get("selectivity_score")  # may be None

            # FIX: Safety is NOT fed into consensus as boolean.
            # Safety flags are preserved as metadata only.
            safety_metadata_map: Dict[str, dict] = {}
            if stage6 and stage6.results_summary and stage6.results_summary.get("safety_records"):
                for rec in stage6.results_summary["safety_records"]:
                    safety_metadata_map[rec["compound_code"]] = {
                        "safety_status":        rec.get("safety_status"),
                        "evidence_level":       rec.get("evidence_level"),
                        "aquatic_mobility":     rec.get("aquatic_mobility_class"),
                        "predictive_concern":   rec.get("predictive_aquatic_concern"),
                    }

            weed_pockets = target.pockets_json or []
            is_weed_p2rank = weed_pockets and weed_pockets[0].get("status") == "COMPLETED"
            weed_pocket_center = weed_pockets[0]["center"] if is_weed_p2rank and weed_pockets[0].get("center") else None
            weed_pdb_path = target.pdb_id

            # FIX: target_relevance — only compute if all components are actually measured
            if (
                target
                and target.structure_confidence is not None
                and target.crop_divergence_score is not None
                and target.essentiality_score is not None
            ):
                dyn_target_relevance = round(
                    min(100.0, max(0.0,
                        (target.structure_confidence * 0.4) +
                        (target.crop_divergence_score * 0.3) +
                        (target.essentiality_score * 0.3)
                    )), 1
                )
            else:
                dyn_target_relevance = None  # Unknown — not fabricated

            for idx, comp in enumerate(compounds):
                if weed_pocket_center:
                    weed_dock = self.docking_engine.screen_candidate(weed_pdb_path, comp.smiles, weed_pocket_center)
                    boltz_pKd = weed_dock["boltz"].get("pKd_predicted") if weed_dock["boltz"].get("status") == "COMPLETED" else None
                    boltz_conf = weed_dock["boltz"].get("complex_confidence_pLDDT") if weed_dock["boltz"].get("status") == "COMPLETED" else None
                    gnina_cnn = weed_dock["gnina"].get("cnn_score") if weed_dock["gnina"].get("status") == "COMPLETED" else None
                    gnina_aff = weed_dock["gnina"].get("affinity_kcal_mol") if weed_dock["gnina"].get("status") == "COMPLETED" else None
                    pose_agree = weed_dock["pose_agreement"]
                    # FIX: Preserve actual docking status codes from each engine
                    boltz_actual_status = weed_dock["boltz"].get("status", "NOT_AVAILABLE")
                    gnina_actual_status = weed_dock["gnina"].get("status", "NOT_AVAILABLE")
                else:
                    boltz_pKd, boltz_conf, gnina_cnn, gnina_aff = None, None, None, None
                    pose_agree = "POCKET_CENTER_MISSING"
                    boltz_actual_status = "POCKET_CENTER_MISSING"
                    gnina_actual_status = "POCKET_CENTER_MISSING"

                sel_score = selectivity_map.get(comp.compound_code)  # None if not available
                safety_meta = safety_metadata_map.get(comp.compound_code, {})

                p_conf = target.pockets_json[0].get("plddt_avg") if (is_weed_p2rank and target.pockets_json) else None

                # FIX: consensus engine does NOT receive safety_evidence_clean boolean.
                # Safety data is preserved as metadata on the candidate, not mixed into ranking.
                consensus = self.consensus_engine.calculate_score(
                    target_relevance=dyn_target_relevance,
                    pocket_confidence=p_conf,
                    boltz_pKd=boltz_pKd,
                    gnina_cnn_score=gnina_cnn,
                    pose_agreement=pose_agree,
                    crop_selectivity_score=sel_score,
                    physicochemical_pass=comp.lipinski_pass,
                    novelty_score=comp.novelty_score,
                    safety_evidence_clean=None,  # Not used in ranking — PREDICTIVE_SCREEN_ONLY
                )

                has_native_docking = (boltz_pKd is not None) or (gnina_aff is not None)
                evidence_lvl = 1 if has_native_docking else 0
                status_tag = "NATIVE_DOCKING_SUPPORTED" if has_native_docking else "HYPOTHESIS_ONLY"

                candidate = Candidate(
                    project_id=project.id,
                    compound_code=comp.compound_code,
                    smiles=comp.smiles,
                    target_name=target.name,
                    evidence_level=evidence_lvl,
                    boltz_status=boltz_actual_status,
                    boltz_affinity_score=boltz_pKd,
                    boltz_confidence=boltz_conf,
                    gnina_status=gnina_actual_status,
                    gnina_docking_score=gnina_aff,
                    pose_agreement=pose_agree,
                    crop_selectivity_score=sel_score,  # Preserved as None if unavailable
                    mikherb_score=consensus["mikherb_score"],
                    status=status_tag
                )
                self.db.add(candidate)
            self.db.commit()

            # Use stored status codes from DB — avoids re-running docking just for report generation.
            # boltz_status and gnina_status are persisted on each Candidate during the primary scoring loop.
            cand_data_for_report = []
            for c in self.db.query(Candidate).filter_by(project_id=project.id).order_by(Candidate.mikherb_score.desc()).all():
                boltz_report_status = c.boltz_status or "NOT_AVAILABLE"
                gnina_report_status = c.gnina_status or "NOT_AVAILABLE"

                cand_data_for_report.append({
                    "code":         c.compound_code,
                    "target":       c.target_name,
                    "boltz_status": boltz_report_status,
                    "boltz":        c.boltz_affinity_score if c.boltz_affinity_score is not None else f"[{boltz_report_status}]",
                    "gnina_status": gnina_report_status,
                    "gnina":        f"{c.gnina_docking_score} kcal/mol" if c.gnina_docking_score is not None else f"[{gnina_report_status}]",
                    "selectivity":  f"{c.crop_selectivity_score}/100" if c.crop_selectivity_score is not None else "NOT_AVAILABLE",
                    "score":        f"{c.mikherb_score}/100" if c.mikherb_score else "N/A",
                    "safety_metadata": safety_metadata_map.get(c.compound_code, {}),
                })

            pdf_path = f"./reports/project_{project.id}_report.pdf"
            ReportGenerator.generate_pdf_report({
                "id": project.id,
                "name": project.name,
                "weed_species": project.weed_species,
                "crop_species": project.crop_species,
                "objective": project.objective,
                "candidates": cand_data_for_report
            }, pdf_path)

            prov = generate_provenance_record("pipeline_completed", {"project_id": project.id}, {"project": project.name}, {"report": pdf_path})
            save_provenance_file(f"./data/projects/{project.id}", "provenance.json", prov)

            return {"ranked_candidates_count": len(compounds), "report_pdf": pdf_path}

        return {}
