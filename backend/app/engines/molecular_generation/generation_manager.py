import logging
from typing import Dict, Any, List, Optional
from app.engines.molecular_generation.schemas import (
    GenerationMode, GenerationRunStatus, MolecularFilterConfig,
    GeneratedMoleculeDetail, ChemicalProperties, NoveltyCategory
)
from app.engines.molecular_generation.rdkit_generator import RDKitMolecularEnumerator
from app.engines.molecular_generation.fragment_generator import FragmentRecombinationGenerator
from app.engines.molecular_generation.database_generator import DatabaseRetrievalGenerator
from app.engines.molecular_generation.ai_generator import GenerativeModelAdapter
from app.engines.molecular_generation.filters import ChemicalValidatorAndFilter
from app.engines.molecular_generation.novelty import NoveltyAnalyzer
from app.engines.molecular_generation.provenance import GenerationProvenanceTracker

logger = logging.getLogger(__name__)

HARD_MAX_CANDIDATES = 200

class MolecularGenerationManager:
    """
    Orchestrates candidate molecule generation, chemical characterization,
    structural filtering, novelty calculation, and scientific provenance tracking.
    """

    def __init__(self):
        self.generators = {
            GenerationMode.RDKit_ENUMERATION: RDKitMolecularEnumerator(),
            GenerationMode.FRAGMENT_RECOMBINATION: FragmentRecombinationGenerator(),
            GenerationMode.DATABASE_RETRIEVAL: DatabaseRetrievalGenerator(),
            GenerationMode.GENERATIVE_AI_ADAPTER: GenerativeModelAdapter()
        }
        self.novelty_analyzer = NoveltyAnalyzer()

    def get_generator(self, mode: GenerationMode):
        return self.generators.get(mode)

    def execute_generation_run(
        self,
        target_info: Dict[str, Any],
        generation_mode: GenerationMode,
        requested_count: int = 20,
        random_seed: Optional[int] = 42,
        parameters: Optional[Dict[str, Any]] = None,
        filter_config: Optional[MolecularFilterConfig] = None
    ) -> Dict[str, Any]:
        """
        Executes an end-to-end generation run with strict scientific integrity.
        """
        # 1. Target Validation Guard: Cannot generate against missing/unvalidated target
        if not target_info or (not target_info.get("gene") and not target_info.get("target_family") and not target_info.get("family")):
            return {
                "status": GenerationRunStatus.FAILED.value,
                "error": "TARGET_VALIDATION_ERROR: Valid biological target information (gene/target_family) required before molecular generation.",
                "molecules": [],
                "requested_count": requested_count,
                "generated_count": 0,
                "valid_count": 0,
                "rejected_count": 0,
                "unique_count": 0,
                "novel_count": 0
            }

        # 2. Hard limit enforcement
        safe_count = min(max(1, requested_count), HARD_MAX_CANDIDATES)
        params = parameters or {}
        cfg = filter_config or MolecularFilterConfig()

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

        # 4. Generate raw candidate molecules
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

        # 5. Characterization, Filtering, Alert Screening, Novelty & Provenance Loop
        for idx, raw in enumerate(raw_molecules):
            smiles = raw.get("smiles")
            compound_code = f"MH-GEN-{target_info.get('gene', 'UNK')}-{idx+1:04d}"

            # RDKit validation & characterization
            is_valid, val_status, rej_reason, can_smiles, inchi_str, inchikey_str, props_dict, mol_obj = (
                ChemicalValidatorAndFilter.validate_and_characterize(smiles)
            )

            # Build provenance
            prov = GenerationProvenanceTracker.create_record(
                target_info=target_info,
                generation_mode=generation_mode,
                generator_name=generator.name,
                generator_version=generator.version,
                generation_method=raw.get("transformation") or raw.get("recombination_method") or generation_mode.value,
                parameters=params,
                random_seed=random_seed,
                parent_molecule=raw.get("parent_scaffold"),
                parent_candidate_id=raw.get("parent_candidate_id"),
                source_database=raw.get("source_database"),
                source_compound_id=raw.get("source_compound_id")
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

            # Novelty analysis
            novelty_eval = self.novelty_analyzer.evaluate_novelty(mol_obj, can_smiles)
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
                provenance=prov
            ))

        return {
            "status": GenerationRunStatus.COMPLETED.value,
            "target_id": target_info.get("target_id") or target_info.get("id"),
            "gene": target_info.get("gene"),
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
