import datetime
import os
import traceback
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.models.models import (
    Project, PipelineStage, TargetProtein, ChemicalLibrary, Compound, Candidate,
    GeneratedMolecule, MolecularGenerationRun, MoleculeFilterResult, MoleculeNoveltyResult, MoleculeProvenance
)
from app.engines.molecular_generation import (
    MolecularGenerationManager, GenerationMode, MolecularFilterConfig
)
from app.engines.molecular_generation.generation_manager import CandidateTier
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

    def run_stage(self, project_id: int, stage_order: int) -> Dict[str, Any]:
        project = self.db.query(Project).filter_by(id=project_id).first()
        if not project:
            return {"status": "failed", "error": "Project not found"}
        self.initialize_project_pipeline(project_id)
        stage = self.db.query(PipelineStage).filter_by(project_id=project_id, stage_order=stage_order).first()
        if not stage:
            return {"status": "failed", "error": f"Stage {stage_order} not found"}
        stage.status = "running"
        stage.started_at = datetime.datetime.utcnow()
        self.db.commit()
        try:
            summary = self._execute_stage(project, stage)
            stage.status = "completed"
            stage.results_summary = summary
            stage.completed_at = datetime.datetime.utcnow()
            self.db.commit()
            return {"status": "completed", "stage": stage.stage_name, "results": summary}
        except Exception as e:
            stage.status = "failed"
            stage.error_message = str(e) + "\n" + traceback.format_exc()
            self.db.commit()
            return {"status": "failed", "stage": stage.stage_name, "error": str(e)}

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

            # --- 1b. Determine downstream targets count and primary target ---
            downstream_count = getattr(project, "downstream_target_count", 3) or 3
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

            gene_selected = best_target["gene"]

            # --- 1c. Clear existing targets and fetch structures for Top-N downstream targets ---
            self.db.query(TargetProtein).filter_by(project_id=project.id).delete()

            selected_db_target = None
            downstream_targets_info = {}

            # Pre-fetch structures and pockets for Top-N targets
            for idx, candidate in enumerate(all_targets):
                is_selected = (candidate.get("gene") == gene_selected)
                is_downstream = (idx < downstream_count) or is_selected
                weed_acc = candidate.get("weed_uniprot_id")

                t_info = None
                t_crop_info = None
                crop_status = "NOT_ATTEMPTED"
                crop_error_reason = None
                crop_acc = candidate.get("crop_uniprot_id")

                if is_downstream and weed_acc:
                    try:
                        t_info = self.protein_engine.get_protein_info(
                            weed_acc,
                            f"{project.weed_species} {candidate['gene']} Target"
                        )
                    except Exception as e:
                        t_info = None

                    # Resolve crop homolog accession if missing
                    if not crop_acc:
                        c_clean = project.crop_species.lower().strip()
                        for key, acc in SPECIES_UNIPROT_MAP.items():
                            if key in c_clean:
                                crop_acc = acc
                                break

                    if crop_acc:
                        try:
                            t_crop_info = self.protein_engine.get_protein_info(
                                crop_acc,
                                f"{project.crop_species} {candidate['gene']} Homolog"
                            )
                            crop_status = "FETCH_SUCCESSFUL"
                        except Exception as e:
                            crop_status = "ALPHAFOLD_STRUCTURE_UNAVAILABLE"
                            crop_error_reason = str(e)
                    else:
                        crop_status = "CROP_ACCESSION_UNRESOLVED"
                        crop_error_reason = f"No UniProt accession found for crop species '{project.crop_species}'."

                t_pdb_path = t_info["pdb_path"] if t_info else None
                t_pockets = t_info["pockets"] if t_info else None
                t_weed_seq = t_info["sequence"] if t_info else _fetch_fasta_seq(weed_acc) if weed_acc else None

                t_crop_pdb = t_crop_info["pdb_path"] if t_crop_info else None
                t_crop_pockets = t_crop_info["pockets"] if t_crop_info else None
                t_crop_seq = t_crop_info["sequence"] if t_crop_info else None

                t_plddt = candidate.get("plddt_avg")
                if t_plddt is None and t_pockets:
                    t_plddt = t_pockets[0].get("plddt_avg")

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
                    uniprot_id=weed_acc,
                    weed_sequence=t_weed_seq,
                    crop_homolog_uniprot_id=crop_acc,
                    crop_sequence=t_crop_seq,
                    pdb_id=t_pdb_path,
                    alphafold_id=f"AF-{weed_acc}-F1" if weed_acc else None,
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
                        "downstream_selected": is_downstream,
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
                        "crop_pockets": t_crop_pockets,
                        "crop_status": crop_status,
                        "crop_error_reason": crop_error_reason,
                        "all_targets_discovered": target_discovery_summary,
                        "target_identity_verified": candidate.get("target_identity_verified", False),
                        "organism_verified": candidate.get("organism_verified", False),
                        "gene_verified": candidate.get("gene_verified", False),
                        "function_verified": candidate.get("function_verified", False),
                        "weed_accession_provenance": candidate.get("weed_accession_provenance"),
                        "validated_target_artifact": {
                            "target_id": None,  # Will be set to target_row.id below
                            "gene": candidate["gene"],
                            "target_family": candidate.get("family"),
                            "weed_species": project.weed_species,
                            "weed_uniprot_id": weed_acc,
                            "target_identity_verified": candidate.get("target_identity_verified", False),
                            "organism_verified": candidate.get("organism_verified", False),
                            "gene_verified": candidate.get("gene_verified", False),
                            "function_verified": candidate.get("function_verified", False),
                            "essentiality_evidence": candidate.get("essentiality_evidence") or candidate.get("essentiality_status"),
                            "weed_sequence": t_weed_seq,
                            "sequence": t_weed_seq,
                            "pdb_path": t_pdb_path,
                            "structure_status": "ALPHA_FOLD_RETRIEVED" if t_pdb_path else "STRUCTURE_UNAVAILABLE",
                            "structure_confidence": t_plddt,
                            "pockets_json": t_pockets,
                            "pocket_prediction_status": t_pockets[0].get("status") if (t_pockets and isinstance(t_pockets, list)) else "NO_POCKETS",
                            "provenance_status": candidate.get("weed_accession_provenance", {}).get("provenance_status") if candidate.get("weed_accession_provenance") else "UNVERIFIED"
                        }
                    }
                )
                self.db.add(target_row)
                if is_selected:
                    selected_db_target = target_row
                if is_downstream:
                    downstream_targets_info[candidate["gene"]] = {
                        "rank": idx + 1,
                        "uniprot_id": weed_acc,
                        "pdb_path": t_pdb_path,
                        "has_pockets": bool(t_pockets and t_pockets[0].get("center")),
                        "plddt": t_plddt,
                        "crop_status": crop_status
                    }

            self.db.commit()
            if selected_db_target:
                self.db.refresh(selected_db_target)

            return {
                "target_id": selected_db_target.id if selected_db_target else None,
                "gene_selected": gene_selected,
                "execution_mode": f"MULTI_TARGET_DOWNSTREAM_TOP_{downstream_count}",
                "downstream_target_count": downstream_count,
                "downstream_targets_acquired": len(downstream_targets_info),
                "downstream_targets": downstream_targets_info,
                "all_targets_discovered_count": len(all_targets),
                "targets_with_structure": sum(1 for t in all_targets if t.get("alphafold_available")),
                "top_ranked_targets": target_discovery_summary[:downstream_count],
                "weed_uniprot_id": selected_db_target.uniprot_id if selected_db_target else None,
                "crop_uniprot_id": selected_db_target.crop_homolog_uniprot_id if selected_db_target else None,
                "weed_pdb_path": selected_db_target.pdb_id if selected_db_target else None,
                "plddt_avg": selected_db_target.structure_confidence if selected_db_target else None,
                "sequence_length": len(selected_db_target.weed_sequence) if selected_db_target and selected_db_target.weed_sequence else 0
            }

        # ---------------------------------------------------------------
        # STAGE 2 — Binding Pocket Prediction
        # ---------------------------------------------------------------
        elif order == 2:
            downstream_count = getattr(project, "downstream_target_count", 3) or 3
            downstream_targets = (
                self.db.query(TargetProtein)
                .filter_by(project_id=project.id)
                .filter(TargetProtein.rank <= downstream_count)
                .order_by(TargetProtein.rank)
                .all()
            )
            if not downstream_targets:
                downstream_targets = self.db.query(TargetProtein).filter_by(project_id=project.id, is_primary_selected=True).all()
            if not downstream_targets:
                downstream_targets = self.db.query(TargetProtein).filter_by(project_id=project.id).all()

            target_pocket_summaries = []
            for t in downstream_targets:
                pockets = t.pockets_json or []
                is_native = pockets and pockets[0].get("status") == "COMPLETED"
                target_pocket_summaries.append({
                    "target_id": t.id,
                    "gene": t.gene,
                    "rank": t.rank,
                    "is_primary": t.is_primary_selected,
                    "pocket_count": len(pockets) if is_native else 0,
                    "primary_pocket": pockets[0] if is_native else None,
                    "status": pockets[0].get("status") if pockets else "NO_POCKETS"
                })

            primary = target_pocket_summaries[0] if target_pocket_summaries else {}
            return {
                "downstream_targets_evaluated": len(target_pocket_summaries),
                "target_pocket_summaries": target_pocket_summaries,
                "primary_pocket": primary.get("primary_pocket"),
                "pocket_count": primary.get("pocket_count", 0),
                "pocket_predictor_status": primary.get("status", "NO_POCKETS"),
                "message": f"Pocket prediction summarized across Top-{len(target_pocket_summaries)} downstream targets."
            }

        # ---------------------------------------------------------------
        # STAGE 3 — Target-Conditioned Molecular Generation & Library Assembly
        # ---------------------------------------------------------------
        elif order == 3:
            # 1. Retrieve validated biological target with structure & pocket
            primary_target = self.db.query(TargetProtein).filter_by(project_id=project.id, is_primary_selected=True).first()
            if not primary_target:
                primary_target = self.db.query(TargetProtein).filter_by(project_id=project.id).first()

            auto_gen_count = 0
            if primary_target and primary_target.weed_sequence and primary_target.pockets_json:
                p_center = None
                if isinstance(primary_target.pockets_json, list) and len(primary_target.pockets_json) > 0:
                    p_center = primary_target.pockets_json[0].get("center")

                if p_center and len(p_center) == 3:
                    existing_run = self.db.query(MolecularGenerationRun).filter_by(
                        project_id=project.id,
                        target_id=primary_target.id
                    ).first()

                    if not existing_run:
                        mgr = MolecularGenerationManager()
                        
                        # Determine generation candidate tier (Default: STANDARD = 50)
                        tier_setting = getattr(project, "generation_tier", "STANDARD") or "STANDARD"
                        tier_counts = {
                            "QUICK": CandidateTier.QUICK,
                            "STANDARD": CandidateTier.STANDARD,
                            "DEEP": CandidateTier.DEEP,
                            "EXPLORATORY": CandidateTier.EXPLORATORY
                        }
                        req_count = tier_counts.get(str(tier_setting).upper(), CandidateTier.STANDARD)

                        # Consume real validated target artifact & evidence from Stage 1 & Stage 2
                        target_analysis = primary_target.analysis_json or {}
                        validated_artifact = target_analysis.get("validated_target_artifact") or {}

                        # Resolve UniProt accession strictly from primary target without hardcoded accession fallback
                        real_uniprot_id = primary_target.uniprot_id or validated_artifact.get("weed_uniprot_id")

                        # Resolve verification evidence preserved from Stage 1 target discovery
                        gene_ver = target_analysis.get("gene_verified")
                        if gene_ver is None:
                            gene_ver = validated_artifact.get("gene_verified")

                        func_ver = target_analysis.get("function_verified")
                        if func_ver is None:
                            func_ver = validated_artifact.get("function_verified")

                        target_ident_ver = target_analysis.get("target_identity_verified")
                        if target_ident_ver is None:
                            target_ident_ver = validated_artifact.get("target_identity_verified")

                        org_ver = target_analysis.get("organism_verified")
                        if org_ver is None:
                            org_ver = validated_artifact.get("organism_verified")

                        essentiality_ev = (
                            primary_target.essentiality_status
                            or validated_artifact.get("essentiality_evidence")
                            or target_analysis.get("essentiality_evidence")
                        )

                        target_dict = {
                            "id": primary_target.id,
                            "target_id": primary_target.id,
                            "gene": primary_target.gene or primary_target.name,
                            "name": primary_target.name,
                            "target_family": primary_target.target_family,
                            "weed_species": project.weed_species,
                            "organism": project.weed_species,
                            "weed_uniprot_id": real_uniprot_id,
                            "uniprot_id": real_uniprot_id,
                            "target_identity_verified": target_ident_ver,
                            "organism_verified": org_ver,
                            "gene_verified": gene_ver,
                            "function_verified": func_ver,
                            "essentiality_evidence": essentiality_ev,
                            "weed_sequence": primary_target.weed_sequence,
                            "sequence": primary_target.weed_sequence,
                            "pdb_path": primary_target.pdb_id or validated_artifact.get("pdb_path"),
                            "structure_status": validated_artifact.get("structure_status", "ALPHA_FOLD_RETRIEVED" if primary_target.pdb_id else "STRUCTURE_UNAVAILABLE"),
                            "structure_confidence": primary_target.structure_confidence,
                            "alphafold_available": bool(primary_target.alphafold_id or primary_target.structure_confidence),
                            "pockets_json": primary_target.pockets_json,
                            "pocket_center": p_center,
                            "pocket_prediction_status": validated_artifact.get("pocket_prediction_status", "COMPLETED" if p_center else "NO_POCKETS"),
                            "pocket_source": primary_target.pockets_json[0].get("source") if (primary_target.pockets_json and isinstance(primary_target.pockets_json, list)) else None,
                            "pocket_score": primary_target.pockets_json[0].get("score") if (primary_target.pockets_json and isinstance(primary_target.pockets_json, list)) else None,
                            "weed_accession_provenance": target_analysis.get("weed_accession_provenance") or validated_artifact.get("provenance")
                        }

                        gen_run = MolecularGenerationRun(
                            project_id=project.id,
                            target_id=primary_target.id,
                            run_name=f"Pipeline Target-Conditioned Generation ({primary_target.gene})",
                            generation_mode="RDKit_ENUMERATION",
                            generator_name="RDKit Chemical Enumerator",
                            generator_version="1.0.0",
                            status="RUNNING",
                            random_seed=42,
                            requested_count=req_count
                        )
                        self.db.add(gen_run)
                        self.db.commit()
                        self.db.refresh(gen_run)

                        exec_res = mgr.execute_generation_run(
                            target_info=target_dict,
                            generation_mode=GenerationMode.RDKit_ENUMERATION,
                            requested_count=req_count,
                            random_seed=42
                        )

                        gen_run.status = exec_res.get("status", "COMPLETED")
                        gen_run.generated_count = exec_res.get("generated_count", 0)
                        gen_run.valid_count = exec_res.get("valid_count", 0)
                        gen_run.rejected_count = exec_res.get("rejected_count", 0)
                        gen_run.unique_count = exec_res.get("unique_count", 0)
                        gen_run.novel_count = exec_res.get("novel_count", 0)
                        gen_run.completed_at = datetime.datetime.utcnow()

                        for mol_data in exec_res.get("molecules", []):
                            props = mol_data.get("properties") or {}
                            alerts = mol_data.get("structural_alerts") or {}
                            novelty = mol_data.get("novelty") or {}
                            prov = mol_data.get("provenance") or {}
                            p_comp = mol_data.get("pocket_complementarity")
                            p_comp_dict = p_comp.dict() if hasattr(p_comp, "dict") else (p_comp if isinstance(p_comp, dict) else None)
                            p_fit = p_comp_dict.get("pocket_fit_score") if p_comp_dict else None

                            db_mol = GeneratedMolecule(
                                run_id=gen_run.id,
                                project_id=project.id,
                                target_id=primary_target.id,
                                compound_code=mol_data.get("compound_code", f"MH-GEN-{primary_target.gene}"),
                                smiles=mol_data.get("smiles", ""),
                                canonical_smiles=mol_data.get("canonical_smiles"),
                                inchi=mol_data.get("inchi"),
                                inchikey=mol_data.get("inchikey"),
                                molecular_formula=props.get("molecular_formula"),
                                mw=props.get("molecular_weight"),
                                logp=props.get("logp"),
                                hbd=props.get("hbd"),
                                hba=props.get("hba"),
                                tpsa=props.get("tpsa"),
                                rotatable_bonds=props.get("rotatable_bonds"),
                                formal_charge=props.get("formal_charge"),
                                heavy_atom_count=props.get("heavy_atom_count"),
                                ring_count=props.get("ring_count"),
                                chemical_validation_status=mol_data.get("chemical_validation_status", "VALID"),
                                rejection_reason=mol_data.get("rejection_reason"),
                                generation_mode=gen_run.generation_mode,
                                parent_molecule_smiles=prov.get("parent_molecule"),
                                parent_candidate_id=prov.get("parent_candidate_id"),
                                passed_all_filters=mol_data.get("passed_all_filters", False),
                                structural_alerts_count=alerts.get("alerts_count", 0),
                                structural_alerts_json=alerts.get("alerts_detected", []),
                                max_tanimoto_similarity=novelty.get("max_tanimoto_similarity"),
                                novelty_category=novelty.get("novelty_category"),
                                closest_known_compound=novelty.get("closest_known_compound"),
                                pocket_fit_score=p_fit,
                                pocket_compatibility_json=p_comp_dict
                            )
                            self.db.add(db_mol)
                            self.db.commit()
                            self.db.refresh(db_mol)

                            db_filter = MoleculeFilterResult(
                                molecule_id=db_mol.id,
                                passed_all_filters=mol_data.get("passed_all_filters", False),
                                property_results_json=mol_data.get("filter_results"),
                                structural_alert_screen_passed=alerts.get("passed", True),
                                structural_alerts_detected_json=alerts.get("alerts_detected", [])
                            )
                            self.db.add(db_filter)

                            db_novelty = MoleculeNoveltyResult(
                                molecule_id=db_mol.id,
                                exact_match=novelty.get("exact_match", False),
                                max_tanimoto_similarity=novelty.get("max_tanimoto_similarity"),
                                closest_known_compound=novelty.get("closest_known_compound"),
                                novelty_category=novelty.get("novelty_category"),
                                reference_database=novelty.get("reference_database", "Default")
                            )
                            self.db.add(db_novelty)

                            db_prov = MoleculeProvenance(
                                molecule_id=db_mol.id,
                                target_id=primary_target.id,
                                protein_sequence_hash=prov.get("protein_sequence_hash"),
                                pocket_center_json=p_center,
                                generation_method=prov.get("generation_method", gen_run.generation_mode),
                                generator_name=prov.get("generator_name", gen_run.generator_name),
                                generator_version=prov.get("generator_version", gen_run.generator_version),
                                parameters_json=prov.get("parameters"),
                                random_seed=prov.get("random_seed"),
                                query_endpoint=prov.get("query_endpoint"),
                                response_hash=prov.get("response_hash"),
                                external_verification_status=prov.get("external_verification_status"),
                                provenance_hash=prov.get("provenance_hash", "UNKNOWN")
                            )
                            self.db.add(db_prov)

                        self.db.commit()
                        auto_gen_count = gen_run.valid_count

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

            # Integrate candidate molecules from any completed molecular generation runs
            gen_molecules = self.db.query(GeneratedMolecule).filter_by(
                project_id=project.id,
                chemical_validation_status="VALID",
                passed_all_filters=True
            ).all()
            for gm in gen_molecules:
                if not any(c["code"] == gm.compound_code for c in raw_compounds):
                    raw_compounds.append({
                        "code": gm.compound_code,
                        "name": f"{gm.compound_code} ({gm.generation_mode})",
                        "smiles": gm.canonical_smiles or gm.smiles
                    })

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
            downstream_count = getattr(project, "downstream_target_count", 3) or 3
            downstream_targets = (
                self.db.query(TargetProtein)
                .filter_by(project_id=project.id)
                .filter(TargetProtein.rank <= downstream_count)
                .order_by(TargetProtein.rank)
                .all()
            )
            if not downstream_targets:
                downstream_targets = self.db.query(TargetProtein).filter_by(project_id=project.id, is_primary_selected=True).all()
            if not downstream_targets:
                downstream_targets = self.db.query(TargetProtein).filter_by(project_id=project.id).all()

            compounds = self.db.query(Compound).all()

            docking_by_target = {}
            docking_by_compound = {}
            primary_docking_results = []
            total_docked = 0

            for target in downstream_targets:
                pockets = target.pockets_json or []
                if not pockets or pockets[0].get("status") != "COMPLETED" or not pockets[0].get("center"):
                    docking_by_target[target.gene] = {
                        "status": pockets[0].get("status", "P2RANK_POCKET_ENGINE_NOT_INSTALLED") if pockets else "P2RANK_POCKET_ENGINE_NOT_INSTALLED",
                        "target_name": target.name,
                        "results": []
                    }
                    continue

                pocket_center = pockets[0]["center"]
                weed_pdb_path = target.pdb_id
                target_results = []

                for comp in compounds:
                    res = self.docking_engine.screen_candidate(
                        weed_pdb_path, comp.smiles, pocket_center, protein_sequence=target.weed_sequence
                    )
                    dock_item = {
                        "target_gene": target.gene,
                        "target_name": target.name,
                        "compound_code": comp.compound_code,
                        "smiles": comp.smiles,
                        "boltz_status": res["boltz"].get("status"),
                        "boltz_pIC50": res["boltz"].get("pIC50_predicted"),
                        "boltz_confidence": res["boltz"].get("complex_confidence_pLDDT"),
                        "boltz_native_confidence": res["boltz"].get("boltz_confidence_score"),
                        "gnina_status": res["gnina"].get("status"),
                        "gnina_affinity": res["gnina"].get("affinity_kcal_mol"),
                        "gnina_cnn": res["gnina"].get("cnn_score"),
                        "pose_agreement": res["pose_agreement"],
                        "gnina_mode": res["gnina"].get("execution_mode")
                    }
                    target_results.append(dock_item)
                    total_docked += 1

                    if comp.compound_code not in docking_by_compound:
                        docking_by_compound[comp.compound_code] = {
                            "primary": dock_item,
                            "panel": [dock_item]
                        }
                    else:
                        docking_by_compound[comp.compound_code]["panel"].append(dock_item)
                        if target.is_primary_selected:
                            docking_by_compound[comp.compound_code]["primary"] = dock_item

                docking_by_target[target.gene] = {
                    "status": "COMPLETED",
                    "target_name": target.name,
                    "results": target_results
                }
                if target.is_primary_selected or not primary_docking_results:
                    primary_docking_results = target_results

            return {
                "downstream_targets_screened": len(downstream_targets),
                "docking_completed_count": total_docked,
                "docking_by_target": docking_by_target,
                "docking_by_compound": docking_by_compound,
                "top_docking": primary_docking_results[0] if primary_docking_results else None,
                "message": f"Multi-target screening evaluated {len(compounds)} compounds across {len(downstream_targets)} downstream targets ({total_docked} total docking runs)."
            }

        # ---------------------------------------------------------------
        # STAGE 5 — Weed vs Crop Selectivity Analysis
        # ---------------------------------------------------------------
        elif order == 5:
            downstream_count = getattr(project, "downstream_target_count", 3) or 3
            downstream_targets = (
                self.db.query(TargetProtein)
                .filter_by(project_id=project.id)
                .filter(TargetProtein.rank <= downstream_count)
                .order_by(TargetProtein.rank)
                .all()
            )
            if not downstream_targets:
                downstream_targets = self.db.query(TargetProtein).filter_by(project_id=project.id, is_primary_selected=True).all()
            if not downstream_targets:
                downstream_targets = self.db.query(TargetProtein).filter_by(project_id=project.id).all()

            compounds = self.db.query(Compound).all()
            selectivity_by_target = {}
            primary_selectivity_results = []

            for target in downstream_targets:
                weed_pockets = target.pockets_json or []
                is_weed_p2rank = weed_pockets and weed_pockets[0].get("status") == "COMPLETED"
                weed_pocket_center = weed_pockets[0]["center"] if is_weed_p2rank and weed_pockets[0].get("center") else None
                weed_pdb_path = target.pdb_id

                crop_pdb_path = target.analysis_json.get("crop_pdb_path") if target.analysis_json else None
                crop_pockets = target.analysis_json.get("crop_pockets") if target.analysis_json else None
                is_crop_p2rank = crop_pockets and crop_pockets[0].get("status") == "COMPLETED"
                crop_pocket_center = crop_pockets[0]["center"] if is_crop_p2rank and crop_pockets[0].get("center") else None

                target_sel_results = []
                if weed_pocket_center and crop_pdb_path and os.path.exists(crop_pdb_path) and crop_pocket_center and target.crop_sequence:
                    for comp in compounds:
                        weed_dock = self.docking_engine.screen_candidate(
                            weed_pdb_path, comp.smiles, weed_pocket_center, protein_sequence=target.weed_sequence
                        )
                        crop_dock = self.docking_engine.screen_candidate(
                            crop_pdb_path, comp.smiles, crop_pocket_center, protein_sequence=target.crop_sequence
                        )

                        weed_pIC50 = weed_dock["boltz"].get("pIC50_predicted") if weed_dock["boltz"].get("status") == "COMPLETED" else None
                        weed_gnina_aff = weed_dock["gnina"].get("affinity_kcal_mol") if weed_dock["gnina"].get("status") == "COMPLETED" else None

                        crop_pIC50 = crop_dock["boltz"].get("pIC50_predicted") if crop_dock["boltz"].get("status") == "COMPLETED" else None
                        crop_gnina_aff = crop_dock["gnina"].get("affinity_kcal_mol") if crop_dock["gnina"].get("status") == "COMPLETED" else None

                        if weed_pIC50 is not None and crop_pIC50 is not None:
                            sel_res = self.selectivity_engine.evaluate_selectivity(
                                target.weed_sequence, target.crop_sequence, weed_pIC50=weed_pIC50, crop_pIC50=crop_pIC50
                            )
                            target_sel_results.append({
                                "target_gene": target.gene,
                                "compound_code": comp.compound_code,
                                "method": "Boltz-2 pIC50 Comparison",
                                "weed_pIC50": round(weed_pIC50, 2),
                                "crop_pIC50": round(crop_pIC50, 2),
                                "pIC50_difference": sel_res.get("pIC50_difference"),
                                "IC50_fold_difference": sel_res.get("IC50_fold_difference"),
                                "selectivity_score": sel_res["selectivity_score"],
                                "fold_difference": sel_res["selectivity_fold_difference"],
                                "status": "COMPLETED"
                            })
                        elif weed_gnina_aff is not None and crop_gnina_aff is not None:
                            aff_diff = abs(weed_gnina_aff) - abs(crop_gnina_aff)
                            sel_score = min(100.0, max(0.0, 50.0 + (aff_diff * 15.0)))
                            target_sel_results.append({
                                "target_gene": target.gene,
                                "compound_code": comp.compound_code,
                                "method": "GNINA kcal/mol Comparison",
                                "weed_affinity_kcal": weed_gnina_aff,
                                "crop_affinity_kcal": crop_gnina_aff,
                                "selectivity_score": round(sel_score, 1),
                                "status": "COMPLETED"
                            })
                        else:
                            target_sel_results.append({
                                "target_gene": target.gene,
                                "compound_code": comp.compound_code,
                                "weed_pIC50": None,
                                "crop_pIC50": None,
                                "selectivity_score": None,
                                "status": "SELECTIVITY_NOT_AVAILABLE_MISSING_DOCKING"
                            })
                else:
                    crop_err = target.analysis_json.get("crop_error_reason", "Crop structure or native pocket missing") if target.analysis_json else "Crop structure or native pocket missing"
                    for comp in compounds:
                        target_sel_results.append({
                            "target_gene": target.gene,
                            "compound_code": comp.compound_code,
                            "weed_pIC50": None,
                            "crop_pIC50": None,
                            "selectivity_score": None,
                            "status": "SELECTIVITY_NOT_AVAILABLE_CROP_STRUCTURE_MISSING",
                            "reason": crop_err
                        })

                selectivity_by_target[target.gene] = target_sel_results
                if target.is_primary_selected or not primary_selectivity_results:
                    primary_selectivity_results = target_sel_results

            return {
                "downstream_targets_evaluated": len(downstream_targets),
                "dual_docking_selectivity": primary_selectivity_results,
                "selectivity_by_target": selectivity_by_target,
                "top_selectivity": primary_selectivity_results[0] if primary_selectivity_results else None
            }

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
            stage4 = self.db.query(PipelineStage).filter_by(project_id=project.id, stage_order=4).first()
            stage5 = self.db.query(PipelineStage).filter_by(project_id=project.id, stage_order=5).first()
            stage6 = self.db.query(PipelineStage).filter_by(project_id=project.id, stage_order=6).first()

            # Retrieve Stage 4 docking results directly — ZERO double-docking in Stage 7
            docking_summary = stage4.results_summary if (stage4 and stage4.results_summary) else {}
            docking_by_comp = docking_summary.get("docking_by_compound", {})

            selectivity_map: Dict[str, Optional[float]] = {}
            if stage5 and stage5.results_summary and stage5.results_summary.get("dual_docking_selectivity"):
                for sel in stage5.results_summary["dual_docking_selectivity"]:
                    selectivity_map[sel["compound_code"]] = sel.get("selectivity_score")

            safety_metadata_map: Dict[str, dict] = {}
            if stage6 and stage6.results_summary and stage6.results_summary.get("safety_records"):
                for rec in stage6.results_summary["safety_records"]:
                    safety_metadata_map[rec["compound_code"]] = {
                        "safety_status":        rec.get("safety_status"),
                        "evidence_level":       rec.get("evidence_level"),
                        "aquatic_mobility":     rec.get("aquatic_mobility_class"),
                        "predictive_concern":   rec.get("predictive_aquatic_concern"),
                    }

            weed_pockets = target.pockets_json or [] if target else []
            is_weed_p2rank = weed_pockets and weed_pockets[0].get("status") == "COMPLETED"
            weed_pocket_center = weed_pockets[0]["center"] if is_weed_p2rank and weed_pockets[0].get("center") else None
            weed_pdb_path = target.pdb_id if target else None

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
                dyn_target_relevance = None

            # Clear existing candidates for this project before ranking
            self.db.query(Candidate).filter_by(project_id=project.id).delete()

            for idx, comp in enumerate(compounds):
                comp_dock = docking_by_comp.get(comp.compound_code, {})
                primary_dock = comp_dock.get("primary")

                if primary_dock:
                    # Use stored Stage 4 scientific output — NO re-execution
                    boltz_pIC50 = primary_dock.get("boltz_pIC50")
                    boltz_conf = primary_dock.get("boltz_confidence")
                    boltz_actual_status = primary_dock.get("boltz_status", "NOT_AVAILABLE")
                    gnina_cnn = primary_dock.get("gnina_cnn")
                    gnina_aff = primary_dock.get("gnina_affinity")
                    gnina_actual_status = primary_dock.get("gnina_status", "NOT_AVAILABLE")
                    pose_agree = primary_dock.get("pose_agreement", "NOT_AVAILABLE")
                elif weed_pocket_center and weed_pdb_path:
                    # Fallback only if Stage 4 was skipped
                    weed_dock = self.docking_engine.screen_candidate(
                        weed_pdb_path, comp.smiles, weed_pocket_center, protein_sequence=target.weed_sequence
                    )
                    boltz_pIC50 = weed_dock["boltz"].get("pIC50_predicted") if weed_dock["boltz"].get("status") == "COMPLETED" else None
                    boltz_conf = weed_dock["boltz"].get("complex_confidence_pLDDT") if weed_dock["boltz"].get("status") == "COMPLETED" else None
                    gnina_cnn = weed_dock["gnina"].get("cnn_score") if weed_dock["gnina"].get("status") == "COMPLETED" else None
                    gnina_aff = weed_dock["gnina"].get("affinity_kcal_mol") if weed_dock["gnina"].get("status") == "COMPLETED" else None
                    pose_agree = weed_dock["pose_agreement"]
                    boltz_actual_status = weed_dock["boltz"].get("status", "NOT_AVAILABLE")
                    gnina_actual_status = weed_dock["gnina"].get("status", "NOT_AVAILABLE")
                else:
                    boltz_pIC50, boltz_conf, gnina_cnn, gnina_aff = None, None, None, None
                    pose_agree = "POCKET_CENTER_MISSING"
                    boltz_actual_status = "POCKET_CENTER_MISSING"
                    gnina_actual_status = "POCKET_CENTER_MISSING"

                sel_score = selectivity_map.get(comp.compound_code)

                p_conf = target.pockets_json[0].get("plddt_avg") if (is_weed_p2rank and target.pockets_json) else None

                consensus = self.consensus_engine.calculate_score(
                    target_relevance=dyn_target_relevance,
                    pocket_confidence=p_conf,
                    boltz_pIC50=boltz_pIC50,
                    gnina_cnn_score=gnina_cnn,
                    pose_agreement=pose_agree,
                    crop_selectivity_score=sel_score,
                    physicochemical_pass=comp.lipinski_pass,
                    novelty_score=comp.novelty_score,
                    safety_evidence_clean=None,
                )

                has_native_docking = (boltz_pIC50 is not None) or (gnina_aff is not None)
                evidence_lvl = 1 if has_native_docking else 0
                status_tag = "NATIVE_DOCKING_SUPPORTED" if has_native_docking else "HYPOTHESIS_ONLY"

                candidate = Candidate(
                    project_id=project.id,
                    compound_code=comp.compound_code,
                    smiles=comp.smiles,
                    target_name=target.name if target else "Unknown Target",
                    evidence_level=evidence_lvl,
                    boltz_status=boltz_actual_status,
                    boltz_affinity_score=boltz_pIC50,
                    boltz_confidence=boltz_conf,
                    gnina_status=gnina_actual_status,
                    gnina_docking_score=gnina_aff,
                    pose_agreement=pose_agree,
                    crop_selectivity_score=sel_score,
                    mikherb_score=consensus["mikherb_score"],
                    status=status_tag
                )
                self.db.add(candidate)
            self.db.commit()

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
