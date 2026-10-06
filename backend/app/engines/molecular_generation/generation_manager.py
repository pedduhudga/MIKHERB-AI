import logging
from typing import Dict, Any, List, Optional, Tuple
from app.engines.molecular_generation.schemas import (
    GenerationMode, GenerationRunStatus, MolecularFilterConfig,
    GeneratedMoleculeDetail, ChemicalProperties, NoveltyCategory,
    PocketComplementarityResult
)
from app.engines.molecular_generation.rdkit_generator import RDKitMolecularEnumerator
from app.engines.molecular_generation.fragment_generator import FragmentRecombinationGenerator
from app.engines.molecular_generation.database_generator import DatabaseRetrievalGenerator
from app.engines.molecular_generation.ai_generator import GenerativeModelAdapter
from app.engines.molecular_generation.filters import ChemicalValidatorAndFilter
from app.engines.molecular_generation.novelty import NoveltyAnalyzer
from app.engines.molecular_generation.provenance import GenerationProvenanceTracker
from app.engines.molecular_generation.pocket_aware_design import PocketPharmacophoreAnalyzer

logger = logging.getLogger(__name__)

class CandidateTier:
    QUICK = 10
    STANDARD = 50
    DEEP = 100
    EXPLORATORY = 500

HARD_MAX_CANDIDATES = 500


class MolecularGenerationManager:
    """
    Orchestrates target-conditioned candidate molecule generation, chemical characterization,
    structural filtering, multi-database novelty calculation, structure-based pocket complementarity,
    and scientific provenance tracking.
    Enforces the mandatory 7-stage prerequisite validation chain:
    TARGET_DISCOVERED -> TARGET_IDENTITY_VERIFIED -> GENE_VERIFIED -> FUNCTION_VERIFIED -> WEED_SPECIES_VERIFIED -> PROTEIN_VALIDATED -> STRUCTURE_POCKET_VALIDATED
    """

    def __init__(self, internal_candidates: Optional[List[Dict[str, Any]]] = None):
        self.generators = {
            GenerationMode.RDKit_ENUMERATION: RDKitMolecularEnumerator(),
            GenerationMode.FRAGMENT_RECOMBINATION: FragmentRecombinationGenerator(),
            GenerationMode.DATABASE_RETRIEVAL: DatabaseRetrievalGenerator(),
            GenerationMode.GENERATIVE_AI_ADAPTER: GenerativeModelAdapter()
        }
        self.novelty_analyzer = NoveltyAnalyzer(internal_candidates=internal_candidates)

    def get_generator(self, mode: GenerationMode):
        return self.generators.get(mode)

    @staticmethod
    def validate_target_prerequisites(target_info: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, bool]]]:
        """
        Enforces the mandatory 7-stage prerequisite validation chain for target-conditioned generation:
        1. TARGET_DISCOVERED: Target identifier and target_family present
        2. TARGET_IDENTITY_VERIFIED: Valid UniProt accession or target identifier resolved
        3. GENE_VERIFIED: Strict gene identity confirmation (gene_verified True in provenance/catalogue)
        4. FUNCTION_VERIFIED: Strict biological function confirmation (function_verified True or essentiality evidence)
        5. WEED_SPECIES_VERIFIED: Known botanical weed species name provided (not placeholder/unknown)
        6. PROTEIN_VALIDATED: Verified biological protein sequence (len >= 20)
        7. STRUCTURE_POCKET_VALIDATED: Validated 3D binding pocket coordinates [x, y, z] and structural evidence
        """
        if not target_info or not isinstance(target_info, dict):
            return False, "TARGET_VALIDATION_ERROR: Target information is missing. Validated target object required.", None

        # Stage 1: TARGET_DISCOVERED
        gene = target_info.get("gene") or target_info.get("name")
        family = target_info.get("target_family") or target_info.get("family")
        if not gene or not family:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [TARGET_DISCOVERED]. Both gene identifier and target_family must be specified.", None

        # Stage 2: TARGET_IDENTITY_VERIFIED (Strict affirmative True requirement; None or False is rejected)
        # Provenance status alone cannot substitute for explicit target_identity_verified=True
        target_id = target_info.get("id") or target_info.get("target_id") or target_info.get("weed_uniprot_id") or target_info.get("uniprot_id")
        target_ident_ver = target_info.get("target_identity_verified")

        if not target_id:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [TARGET_IDENTITY_VERIFIED]. Target ID or UniProt accession identifier must be resolved.", None

        if target_ident_ver is not True:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [TARGET_IDENTITY_VERIFIED]. Target identity verification must be explicitly confirmed (True).", None

        # Stage 3: GENE_VERIFIED (Strict affirmative True requirement; None or False is rejected)
        gene_verified = target_info.get("gene_verified")
        prov_dict = target_info.get("weed_accession_provenance") or target_info.get("provenance") or {}
        if gene_verified is None and isinstance(prov_dict, dict):
            gene_verified = prov_dict.get("gene_verified")
        if gene_verified is not True:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [GENE_VERIFIED]. Target gene verification must be explicitly confirmed (True).", None

        # Stage 4: FUNCTION_VERIFIED (Strict affirmative True requirement AND essentiality evidence required; neither can substitute for the other)
        function_verified = target_info.get("function_verified")
        if function_verified is None and isinstance(prov_dict, dict):
            function_verified = prov_dict.get("function_verified")
        essentiality = target_info.get("essentiality_evidence") or target_info.get("essentiality_status")
        if function_verified is not True:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [FUNCTION_VERIFIED]. Biological target function must be explicitly confirmed (True).", None
        if not essentiality or str(essentiality).strip().lower() in ["none", "unknown", "n/a", ""]:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [FUNCTION_VERIFIED]. Documented essentiality evidence is required.", None

        # Stage 5: WEED_SPECIES_VERIFIED (Strict affirmative True requirement; weed species must be verified)
        weed_species = target_info.get("weed_species") or target_info.get("organism")
        organism_verified = target_info.get("organism_verified")
        if organism_verified is None and isinstance(prov_dict, dict):
            organism_verified = prov_dict.get("organism_verified")

        if not weed_species or str(weed_species).strip().lower() in ["unknown", "none", "n/a", ""]:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [WEED_SPECIES_VERIFIED]. Valid botanical weed species (e.g. Amaranthus palmeri) is required.", None

        if organism_verified is not True:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [WEED_SPECIES_VERIFIED]. Weed organism identity verification must be explicitly confirmed (True).", None

        # Stage 6: PROTEIN_VALIDATED
        sequence = target_info.get("weed_sequence") or target_info.get("sequence")
        if not sequence or len(str(sequence).strip()) < 20:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [PROTEIN_VALIDATED]. Verified full biological protein sequence (minimum 20 amino acids) required.", None

        # Stage 7: STRUCTURE_POCKET_VALIDATED
        # Require verified AlphaFold / 3D structure
        struct_status = target_info.get("structure_status")
        if str(struct_status).upper() in ["STRUCTURE_UNAVAILABLE", "FAILED", "NOT_FOUND", "HEURISTIC_ONLY", "FAILED_EXECUTION"]:
            return False, f"TARGET_VALIDATION_GATE_ERROR: Target failed at stage [STRUCTURE_POCKET_VALIDATED]. 3D structure is unavailable [{struct_status}].", None

        # Require explicit COMPLETED pocket prediction status
        pockets = target_info.get("pockets_json") or target_info.get("pockets") or []
        first_pocket = pockets[0] if (isinstance(pockets, list) and len(pockets) > 0 and isinstance(pockets[0], dict)) else {}

        pocket_pred_status = target_info.get("pocket_prediction_status") or first_pocket.get("status")
        if str(pocket_pred_status).upper() != "COMPLETED":
            return False, f"TARGET_VALIDATION_GATE_ERROR: Target failed at stage [STRUCTURE_POCKET_VALIDATED]. Pocket prediction must be completed (got [{pocket_pred_status}]).", None

        # Strict Native P2Rank requirement: source must be 'P2Rank Native Binary'
        pocket_source = (
            target_info.get("pocket_source")
            or first_pocket.get("source")
            or target_info.get("pocket_prediction_source")
        )
        if pocket_source != "P2Rank Native Binary":
            return False, f"TARGET_VALIDATION_GATE_ERROR: Target failed at stage [STRUCTURE_POCKET_VALIDATED]. Pocket prediction must originate from P2Rank Native Binary (got '{pocket_source}').", None

        # Strict Native P2Rank requirement: numerical pocket score
        pocket_score = target_info.get("pocket_score") or first_pocket.get("score")
        if pocket_score is None and first_pocket:
            pocket_score = first_pocket.get("p2rank_score")

        if pocket_score is None:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [STRUCTURE_POCKET_VALIDATED]. Numerical P2Rank pocket score is required.", None
        try:
            float(pocket_score)
        except (ValueError, TypeError):
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [STRUCTURE_POCKET_VALIDATED]. Numerical P2Rank pocket score is required.", None

        # Strict 3D binding pocket coordinates center [x, y, z]
        pocket_center = target_info.get("pocket_center")
        if not pocket_center and first_pocket:
            pocket_center = first_pocket.get("center")

        if not pocket_center or not isinstance(pocket_center, (list, tuple)) or len(pocket_center) != 3:
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [STRUCTURE_POCKET_VALIDATED]. Target must have verified 3D binding pocket coordinates with center [x, y, z].", None

        try:
            [float(c) for c in pocket_center]
        except (ValueError, TypeError):
            return False, "TARGET_VALIDATION_GATE_ERROR: Target failed at stage [STRUCTURE_POCKET_VALIDATED]. Pocket center coordinates must be numerical [x, y, z].", None

        chain_status = {
            "TARGET_DISCOVERED": True,
            "TARGET_IDENTITY_VERIFIED": True,
            "GENE_VERIFIED": True,
            "FUNCTION_VERIFIED": True,
            "WEED_SPECIES_VERIFIED": True,
            "PROTEIN_VALIDATED": True,
            "STRUCTURE_POCKET_VALIDATED": True
        }
        return True, None, chain_status

    def execute_generation_run(
        self,
        target_info: Dict[str, Any],
        generation_mode: GenerationMode,
        requested_count: int = 50,
        random_seed: Optional[int] = 42,
        parameters: Optional[Dict[str, Any]] = None,
        filter_config: Optional[MolecularFilterConfig] = None,
        database_scope: Optional[List[str]] = None,
        internal_candidates: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Executes an end-to-end generation run with strict scientific integrity.
        Validates target prerequisites, generates candidates, filters, evaluates novelty,
        assesses pocket pharmacophore complementarity, and produces complete provenance records.
        """
        # 1. Scientific Target Validation Guard (Strict 7-stage Gate)
        is_valid_target, gate_error, validation_chain = self.validate_target_prerequisites(target_info)
        if not is_valid_target:
            return {
                "status": GenerationRunStatus.FAILED.value,
                "error": gate_error,
                "molecules": [],
                "requested_count": requested_count,
                "generated_count": 0,
                "valid_count": 0,
                "rejected_count": 0,
                "unique_count": 0,
                "novel_count": 0,
                "validation_chain": validation_chain
            }

        gene = target_info.get("gene") or target_info.get("name")
        family = target_info.get("target_family") or target_info.get("family")
        pockets = target_info.get("pockets_json") or target_info.get("pockets") or []
        primary_pocket = pockets[0] if (isinstance(pockets, list) and len(pockets) > 0) else {"center": target_info.get("pocket_center")}
        pocket_features = PocketPharmacophoreAnalyzer.extract_pocket_features(primary_pocket)

        # 2. Hard limit enforcement with tiered sizing
        safe_count = min(max(1, requested_count), HARD_MAX_CANDIDATES)
        params = parameters or {}
        cfg = filter_config or MolecularFilterConfig()

        # Update novelty analyzer with any project-level internal candidates
        if internal_candidates:
            self.novelty_analyzer._initialize_internal(internal_candidates)

        # 3. Obtain Generator
        generator = self.get_generator(generation_mode)
        if not generator:
            return {
                "status": GenerationRunStatus.FAILED.value,
                "error": f"UNSUPPORTED_GENERATION_MODE: {generation_mode}",
                "molecules": [],
                "requested_count": safe_count,
                "generated_count": 0,
                "valid_count": 0,
                "rejected_count": 0,
                "unique_count": 0,
                "novel_count": 0
            }

        # 4. Generate raw candidate molecules conditioned on biological target and pocket
        gen_result = generator.generate(
            target_info=target_info,
            parameters=params,
            random_seed=random_seed,
            max_candidates=safe_count
        )

        if gen_result.get("status") == "NOT_AVAILABLE":
            return {
                "status": GenerationRunStatus.NOT_AVAILABLE.value,
                "error": gen_result.get("error", "Generator not available"),
                "molecules": [],
                "requested_count": safe_count,
                "generated_count": 0,
                "valid_count": 0,
                "rejected_count": 0,
                "unique_count": 0,
                "novel_count": 0
            }

        if gen_result.get("status") != "COMPLETED":
            return {
                "status": GenerationRunStatus.FAILED.value,
                "error": gen_result.get("error", "Generation failed"),
                "molecules": [],
                "requested_count": safe_count,
                "generated_count": 0,
                "valid_count": 0,
                "rejected_count": 0,
                "unique_count": 0,
                "novel_count": 0
            }

        raw_molecules = gen_result.get("molecules", [])
        validated_candidates: List[GeneratedMoleculeDetail] = []
        seen_inchikeys = set()

        valid_count = 0
        rejected_count = 0
        novel_count = 0

        # 5. Characterization, Filtering, Alert Screening, Pocket Fit, Novelty & Provenance Loop
        for idx, raw in enumerate(raw_molecules):
            smiles = raw.get("smiles")
            compound_code = f"MH-GEN-{gene}-{idx+1:04d}"

            # RDKit validation & characterization
            is_valid, val_status, rej_reason, can_smiles, inchi_str, inchikey_str, props_dict, mol_obj = (
                ChemicalValidatorAndFilter.validate_and_characterize(smiles)
            )

            # Build comprehensive provenance record with audit trail
            prov = GenerationProvenanceTracker.create_record(
                target_info=target_info,
                generation_mode=generation_mode,
                generator_name=generator.name,
                generator_version=generator.version,
                generation_method=raw.get("transformation") or raw.get("recombination_method") or raw.get("retrieval_method") or generation_mode.value,
                parameters=params,
                random_seed=random_seed,
                parent_molecule=raw.get("parent_scaffold"),
                parent_candidate_id=raw.get("parent_candidate_id"),
                source_database=raw.get("source_database"),
                source_compound_id=raw.get("source_compound_id"),
                source_url=raw.get("source_url"),
                query_endpoint=raw.get("query_endpoint"),
                response_hash=raw.get("response_hash"),
                retrieval_method=raw.get("retrieval_method"),
                external_verification_status=raw.get("external_verification_status")
            )
            prov.candidate_id = compound_code

            if not is_valid:
                rejected_count += 1
                validated_candidates.append(GeneratedMoleculeDetail(
                    compound_code=compound_code,
                    smiles=smiles or "",
                    canonical_smiles="",
                    inchi="",
                    inchikey="",
                    chemical_validation_status="REJECTED",
                    rejection_reason=rej_reason,
                    properties=None,
                    filter_results=[],
                    passed_all_filters=False,
                    structural_alerts=None,
                    novelty=None,
                    pocket_complementarity=None,
                    provenance=prov
                ))
                continue

            # Deduplication
            if inchikey_str in seen_inchikeys:
                continue
            seen_inchikeys.add(inchikey_str)
            valid_count += 1

            # Property filter evaluation
            passed_filters, filter_items = ChemicalValidatorAndFilter.apply_filters(props_dict, cfg)

            # Structural alert screen (PAINS / reactive)
            alert_screen = ChemicalValidatorAndFilter.screen_structural_alerts(mol_obj, cfg)

            # Structure-based pocket pharmacophore complementarity evaluation
            pocket_eval = PocketPharmacophoreAnalyzer.evaluate_molecule_pocket_fit(mol_obj, pocket_features)
            pocket_comp = PocketComplementarityResult(**pocket_eval)

            # Multi-database novelty analysis (Reference, PubChem, ChEMBL, Internal)
            novelty_eval = self.novelty_analyzer.evaluate_novelty(
                mol_obj,
                can_smiles,
                database_scope=database_scope,
                query_external_apis=params.get("query_external_novelty_apis", True)
            )
            if novelty_eval.novelty_category in [
                NoveltyCategory.LOW_SIMILARITY,
                NoveltyCategory.NO_MATCH_IN_SEARCHED_DATABASE
            ]:
                novel_count += 1

            chem_props = ChemicalProperties(**props_dict)

            validated_candidates.append(GeneratedMoleculeDetail(
                compound_code=compound_code,
                smiles=smiles,
                canonical_smiles=can_smiles,
                inchi=inchi_str or "",
                inchikey=inchikey_str or "",
                chemical_validation_status="VALID",
                rejection_reason=None,
                properties=chem_props,
                filter_results=filter_items,
                passed_all_filters=passed_filters,
                structural_alerts=alert_screen,
                novelty=novelty_eval,
                pocket_complementarity=pocket_comp,
                provenance=prov
            ))

        return {
            "status": GenerationRunStatus.COMPLETED.value,
            "target_id": target_info.get("target_id") or target_info.get("id"),
            "gene": gene,
            "target_family": family,
            "generation_mode": generation_mode.value,
            "generator_name": generator.name,
            "generator_version": generator.version,
            "requested_count": safe_count,
            "generated_count": len(raw_molecules),
            "valid_count": valid_count,
            "rejected_count": rejected_count,
            "unique_count": len(seen_inchikeys),
            "novel_count": novel_count,
            "random_seed": random_seed,
            "molecules": [c.model_dump() for c in validated_candidates]
        }
