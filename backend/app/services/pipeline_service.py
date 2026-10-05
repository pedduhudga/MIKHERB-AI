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
from app.core.provenance import generate_provenance_record, save_provenance_file
from app.services.report_service import ReportGenerator

DEFAULT_STAGES = [
    (1, "Target Discovery & Structure Acquisition"),
    (2, "Binding Pocket Prediction"),
    (3, "Chemical Library Acquisition & RDKit Cleaning"),
    (4, "Boltz-2 & GNINA AI Docking Screening"),
    (5, "Weed vs Crop Selectivity Analysis"),
    (6, "Safety, Toxicity & Novelty Screening"),
    (7, "Consensus Candidate Ranking & Report Generation")
]

SPECIES_UNIPROT_MAP = {
    "palmer amaranth": "P10324",
    "amaranthus palmeri": "P10324",
    "soybean": "Q02145",
    "glycine max": "Q02145",
    "corn": "P06253",
    "maize": "P06253",
    "zea mays": "P06253",
    "rice": "Q03042",
    "oryza sativa": "Q03042",
    "arabidopsis": "P17597",
    "wheat": "Q41539",
    "triticum aestivum": "Q41539"
}

def resolve_uniprot_accession(species_name: str, default_accession: str) -> Optional[str]:
    s_clean = species_name.lower().strip()
    for key, acc in SPECIES_UNIPROT_MAP.items():
        if key in s_clean:
            return acc
    return default_accession

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
                return {"status": "FAILED", "failed_stage": stage.stage_name, "error": str(e)}

        project.status = "completed"
        self.db.commit()
        return {"status": "COMPLETED", "project_id": project_id}

    def _execute_stage(self, project: Project, stage: PipelineStage) -> dict:
        order = stage.stage_order

        if order == 1:
            weed_uniprot = resolve_uniprot_accession(project.weed_species, "P10324")
            crop_uniprot = resolve_uniprot_accession(project.crop_species, "Q02145")

            target_info = self.protein_engine.get_protein_info(weed_uniprot, f"{project.weed_species} Primary Target")

            crop_pdb_path = None
            crop_seq = None
            crop_pockets = None
            if crop_uniprot:
                try:
                    crop_info = self.protein_engine.get_protein_info(crop_uniprot, f"{project.crop_species} Homolog Target")
                    crop_seq = crop_info["sequence"]
                    crop_pdb_path = crop_info["pdb_path"]
                    crop_pockets = crop_info["pockets"]
                except Exception:
                    pass

            plddt_conf = None
            if target_info.get("pockets") and target_info["pockets"][0].get("plddt_avg") is not None:
                plddt_conf = target_info["pockets"][0]["plddt_avg"]

            target = TargetProtein(
                project_id=project.id,
                name=target_info["name"],
                uniprot_id=target_info["uniprot_id"],
                weed_sequence=target_info["sequence"],
                crop_homolog_uniprot_id=crop_uniprot,
                crop_sequence=crop_seq,
                pdb_id=target_info["pdb_path"],
                alphafold_id=target_info["alphafold_id"],
                structure_confidence=plddt_conf,
                pockets_json=target_info["pockets"],
                analysis_json={
                    **target_info["analysis"],
                    "crop_pdb_path": crop_pdb_path,
                    "crop_pockets": crop_pockets
                }
            )
            self.db.add(target)
            self.db.commit()
            return {
                "target_id": target.id,
                "weed_uniprot_id": target.uniprot_id,
                "crop_uniprot_id": crop_uniprot,
                "weed_pdb_path": target_info["pdb_path"],
                "crop_pdb_path": crop_pdb_path,
                "sequence_length": len(target_info["sequence"])
            }

        elif order == 2:
            target = self.db.query(TargetProtein).filter_by(project_id=project.id).first()
            if not target or not target.pdb_id or not os.path.exists(target.pdb_id):
                raise FileNotFoundError("Target protein structure PDB file unavailable for pocket prediction.")

            pockets = target.pockets_json if target.pockets_json else []
            return {"pocket_count": len(pockets), "primary_pocket": pockets[0] if pockets else None}

        elif order == 3:
            seed_compounds = [
                {"code": f"MH-{project.id}001", "name": "MikHerb Candidate Alpha", "smiles": "CC(=O)Oc1ccccc1C(=O)O"},
                {"code": f"MH-{project.id}002", "name": "MikHerb Candidate Beta", "smiles": "Cc1ccc(cc1)S(=O)(=O)N"},
                {"code": f"MH-{project.id}003", "name": "MikHerb Candidate Gamma", "smiles": "O=C(O)c1ccccc1O"},
                {"code": f"MH-{project.id}004", "name": "MikHerb Candidate Delta", "smiles": "CC1=CC(=O)C2=C(C=C1)N(C(=O)O2)C3=CC(=C(C=C3F)Cl)F"},
                {"code": f"MH-{project.id}005", "name": "MikHerb Candidate Epsilon", "smiles": "CN1C(=O)C2=CC=CC=C2N=C1C3=CC=CC=C3"}
            ]

            glyph_data = self.chemical_engine.fetch_pubchem_compound("Glyphosate")
            if glyph_data and glyph_data.get("smiles"):
                seed_compounds.append({"code": f"MH-{project.id}006", "name": "Glyphosate Reference", "smiles": glyph_data["smiles"]})

            library = ChemicalLibrary(name=f"Library for Project {project.name}", compound_count=len(seed_compounds))
            self.db.add(library)
            self.db.commit()

            processed_comps = self.chemical_engine.build_library(seed_compounds)
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
                    novelty_score=c_data["novelty_score"]
                )
                self.db.add(comp)
            self.db.commit()
            return {"library_id": library.id, "compounds_screened": len(processed_comps)}

        elif order == 4:
            target = self.db.query(TargetProtein).filter_by(project_id=project.id).first()
            compounds = self.db.query(Compound).all()

            pockets = target.pockets_json or [{"center": [0.0, 0.0, 0.0]}]
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
            return {"docking_completed_count": len(docking_results), "top_docking": docking_results[0]}

        elif order == 5:
            target = self.db.query(TargetProtein).filter_by(project_id=project.id).first()
            compounds = self.db.query(Compound).all()

            weed_pockets = target.pockets_json or [{"center": [0.0, 0.0, 0.0]}]
            weed_pocket_center = weed_pockets[0]["center"]
            weed_pdb_path = target.pdb_id

            crop_pdb_path = target.analysis_json.get("crop_pdb_path") if target.analysis_json else None
            crop_pockets = target.analysis_json.get("crop_pockets") if target.analysis_json else None
            crop_pocket_center = crop_pockets[0]["center"] if crop_pockets else None

            selectivity_results = []
            if crop_pdb_path and os.path.exists(crop_pdb_path) and crop_pocket_center and target.crop_sequence:
                for comp in compounds:
                    weed_dock = self.docking_engine.screen_candidate(weed_pdb_path, comp.smiles, weed_pocket_center)
                    crop_dock = self.docking_engine.screen_candidate(crop_pdb_path, comp.smiles, crop_pocket_center)

                    weed_pKd = weed_dock["boltz"].get("pKd_predicted")
                    if weed_pKd is None and weed_dock["gnina"].get("affinity_kcal_mol") is not None:
                        weed_pKd = abs(weed_dock["gnina"]["affinity_kcal_mol"]) / 1.363

                    crop_pKd = crop_dock["boltz"].get("pKd_predicted")
                    if crop_pKd is None and crop_dock["gnina"].get("affinity_kcal_mol") is not None:
                        crop_pKd = abs(crop_dock["gnina"]["affinity_kcal_mol"]) / 1.363

                    if weed_pKd is not None and crop_pKd is not None:
                        sel_res = self.selectivity_engine.evaluate_selectivity(
                            target.weed_sequence, target.crop_sequence, weed_affinity_pKd=weed_pKd, crop_affinity_pKd=crop_pKd
                        )
                        selectivity_results.append({
                            "compound_code": comp.compound_code,
                            "weed_pKd": round(weed_pKd, 2),
                            "crop_pKd": round(crop_pKd, 2),
                            "selectivity_score": sel_res["selectivity_score"],
                            "fold_difference": sel_res["selectivity_fold_difference"],
                            "status": "COMPLETED"
                        })
                    else:
                        selectivity_results.append({
                            "compound_code": comp.compound_code,
                            "weed_pKd": None,
                            "crop_pKd": None,
                            "selectivity_score": None,
                            "status": "SELECTIVITY_NOT_AVAILABLE_MISSING_DOCKING"
                        })
            else:
                for comp in compounds:
                    selectivity_results.append({
                        "compound_code": comp.compound_code,
                        "weed_pKd": None,
                        "crop_pKd": None,
                        "selectivity_score": None,
                        "status": "SELECTIVITY_NOT_AVAILABLE_CROP_STRUCTURE_MISSING"
                    })

            return {"dual_docking_selectivity": selectivity_results, "top_selectivity": selectivity_results[0]}

        elif order == 6:
            compounds = self.db.query(Compound).all()
            safety_records = []
            for comp in compounds:
                logkoc = round(0.81 * (comp.logp or 2.0) + 0.10, 2) if comp.logp is not None else None
                aquatic_mobility = ("HIGH" if logkoc < 2.0 else "MODERATE") if logkoc is not None else "UNKNOWN"
                safety_clean = (aquatic_mobility != "HIGH") and comp.lipinski_pass
                safety_records.append({
                    "compound_code": comp.compound_code,
                    "mammalian_toxicity": "UNKNOWN_REQUIRES_ASSAY",
                    "aquatic_mobility_LogKoc": logkoc,
                    "aquatic_mobility_class": aquatic_mobility,
                    "bee_pollinator_concern": "UNKNOWN_NO_PUBLIC_ALERT",
                    "known_pesticide_similarity": round(comp.novelty_score, 1) if comp.novelty_score is not None else None,
                    "safety_clean": safety_clean
                })
            return {"safety_screened": len(compounds), "safety_records": safety_records}

        elif order == 7:
            target = self.db.query(TargetProtein).filter_by(project_id=project.id).first()
            compounds = self.db.query(Compound).all()
            stage5 = self.db.query(PipelineStage).filter_by(project_id=project.id, stage_order=5).first()
            stage6 = self.db.query(PipelineStage).filter_by(project_id=project.id, stage_order=6).first()

            selectivity_map = {}
            if stage5 and stage5.results_summary and stage5.results_summary.get("dual_docking_selectivity"):
                for sel in stage5.results_summary["dual_docking_selectivity"]:
                    selectivity_map[sel["compound_code"]] = sel.get("selectivity_score")

            safety_map = {}
            if stage6 and stage6.results_summary and stage6.results_summary.get("safety_records"):
                for rec in stage6.results_summary["safety_records"]:
                    safety_map[rec["compound_code"]] = rec.get("safety_clean")

            weed_pockets = target.pockets_json or [{"center": [0.0, 0.0, 0.0]}]
            weed_pocket_center = weed_pockets[0]["center"]
            weed_pdb_path = target.pdb_id

            for idx, comp in enumerate(compounds):
                weed_dock = self.docking_engine.screen_candidate(weed_pdb_path, comp.smiles, weed_pocket_center)

                boltz_pKd = weed_dock["boltz"].get("pKd_predicted")
                boltz_conf = weed_dock["boltz"].get("complex_confidence_pLDDT")
                gnina_cnn = weed_dock["gnina"].get("cnn_score")
                gnina_aff = weed_dock["gnina"].get("affinity_kcal_mol")

                sel_score = selectivity_map.get(comp.compound_code)
                is_safe = safety_map.get(comp.compound_code)

                consensus = self.consensus_engine.calculate_score(
                    target_relevance=80.0,
                    pocket_confidence=target.pockets_json[0].get("plddt_avg") if target.pockets_json else None,
                    boltz_pKd=boltz_pKd,
                    gnina_cnn_score=gnina_cnn,
                    pose_agreement=weed_dock["pose_agreement"],
                    crop_selectivity_score=sel_score,
                    physicochemical_pass=comp.lipinski_pass,
                    novelty_score=comp.novelty_score,
                    safety_evidence_clean=is_safe
                )

                has_native_docking = (boltz_pKd is not None) or (gnina_aff is not None)
                evidence_lvl = 1 if has_native_docking else 0

                candidate = Candidate(
                    project_id=project.id,
                    compound_code=comp.compound_code,
                    smiles=comp.smiles,
                    target_name=target.name,
                    evidence_level=evidence_lvl,
                    boltz_affinity_score=boltz_pKd,
                    boltz_confidence=boltz_conf,
                    gnina_docking_score=gnina_aff,
                    pose_agreement=weed_dock["pose_agreement"],
                    crop_selectivity_score=sel_score if sel_score is not None else 0.0,
                    mikherb_score=consensus["mikherb_score"],
                    status="screened"
                )
                self.db.add(candidate)
            self.db.commit()

            pdf_path = f"./reports/project_{project.id}_report.pdf"
            ReportGenerator.generate_pdf_report({"id": project.id, "name": project.name, "weed_species": project.weed_species, "crop_species": project.crop_species, "objective": project.objective}, pdf_path)

            prov = generate_provenance_record("pipeline_completed", {"project_id": project.id}, {"project": project.name}, {"report": pdf_path})
            save_provenance_file(f"./data/projects/{project.id}", "provenance.json", prov)

            return {"ranked_candidates_count": len(compounds), "report_pdf": pdf_path}

        return {}
