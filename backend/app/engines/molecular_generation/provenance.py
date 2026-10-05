import hashlib
import json
import datetime
from typing import Dict, Any, Optional
from app.engines.molecular_generation.schemas import GenerationMode, ProvenanceMetadata

class GenerationProvenanceTracker:
    """
    Manages complete, tamper-evident scientific provenance records for every
    candidate molecule produced by any generation engine in MIKHERB AI.
    """

    @staticmethod
    def compute_sequence_hash(sequence: Optional[str]) -> Optional[str]:
        if not sequence:
            return None
        return hashlib.sha256(sequence.strip().upper().encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def create_record(
        target_info: Dict[str, Any],
        generation_mode: GenerationMode,
        generator_name: str,
        generator_version: str,
        generation_method: str,
        parameters: Dict[str, Any],
        random_seed: Optional[int] = None,
        parent_molecule: Optional[str] = None,
        parent_candidate_id: Optional[str] = None,
        source_database: Optional[str] = None,
        source_compound_id: Optional[str] = None,
        source_url: Optional[str] = None,
        query_endpoint: Optional[str] = None,
        response_hash: Optional[str] = None,
        retrieval_method: Optional[str] = None,
        external_verification_status: Optional[str] = None
    ) -> ProvenanceMetadata:
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        target_id = target_info.get("target_id") or target_info.get("id")
        target_family = target_info.get("target_family") or target_info.get("family")
        protein_seq = target_info.get("weed_sequence") or target_info.get("sequence")
        seq_hash = GenerationProvenanceTracker.compute_sequence_hash(protein_seq)

        provenance_payload = {
            "target_id": target_id,
            "target_family": target_family,
            "protein_sequence_hash": seq_hash,
            "generation_mode": generation_mode.value if hasattr(generation_mode, "value") else str(generation_mode),
            "generator_name": generator_name,
            "generator_version": generator_version,
            "generation_method": generation_method,
            "random_seed": random_seed,
            "parameters": parameters,
            "parent_molecule": parent_molecule,
            "source_database": source_database,
            "source_compound_id": source_compound_id,
            "source_url": source_url,
            "query_endpoint": query_endpoint,
            "response_hash": response_hash,
            "retrieval_method": retrieval_method,
            "external_verification_status": external_verification_status,
            "created_at": created_at
        }

        # Deterministic SHA-256 hash across all provenance inputs
        raw_bytes = json.dumps(provenance_payload, sort_keys=True).encode("utf-8")
        prov_hash = hashlib.sha256(raw_bytes).hexdigest()

        return ProvenanceMetadata(
            target_id=target_id,
            target_family=target_family,
            generation_method=generation_method,
            generation_mode=generation_mode,
            generator_name=generator_name,
            generator_version=generator_version,
            parent_molecule=parent_molecule,
            parent_candidate_id=parent_candidate_id,
            source_database=source_database,
            source_compound_id=source_compound_id,
            source_url=source_url,
            query_endpoint=query_endpoint,
            response_hash=response_hash,
            retrieval_method=retrieval_method,
            external_verification_status=external_verification_status,
            random_seed=random_seed,
            parameters=parameters,
            created_at=created_at,
            provenance_hash=prov_hash
        )
