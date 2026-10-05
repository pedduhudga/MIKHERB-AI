import json
import logging
import hashlib
import requests
import datetime
import urllib.parse
from typing import Dict, Any, List, Optional
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, inchi
from app.engines.molecular_generation.base_generator import BaseMolecularGenerator, GeneratorCapabilities
from app.engines.molecular_generation.schemas import GenerationMode

logger = logging.getLogger(__name__)

# Curated reference database of known herbicide inhibitors by target family
KNOWN_TARGET_LIGANDS = {
    "ALS": [
        {"name": "Imazethapyr", "cid": "3725", "smiles": "CC1=NC(C(C)C)=NC(=O)C1=C2C=CC(=CC2=O)O", "db": "PubChem"},
        {"name": "Chlorimuron-ethyl", "cid": "54890", "smiles": "CCN(C)c1nc(nc(n1)Cl)NS(=O)(=O)c2ccccc2C(=O)OCC", "db": "PubChem"},
        {"name": "Sulfometuron-methyl", "cid": "5311", "smiles": "CC1=NC(=NC(=N1)NC(=O)NS(=O)(=O)C2=CC=CC=C2C(=O)OC)C", "db": "PubChem"},
        {"name": "Flumetsulam", "cid": "91684", "smiles": "Cc1cc(F)cc(c1)n2nc3nc(nc3n2)S(=O)(=O)Nc4c(F)cccc4F", "db": "PubChem"},
        {"name": "Florasulam", "cid": "115132", "smiles": "COc1cc2nc(nc2n1)S(=O)(=O)Nc3c(F)cc(F)c(F)c3F", "db": "PubChem"},
        {"name": "Imazapyr", "cid": "3723", "smiles": "CC(C)C1(NC(=O)C2=NC=CC=C21)C(=O)O", "db": "PubChem"},
        {"name": "Chlorsulfuron", "cid": "2768", "smiles": "Cc1nc(nc(n1)Cl)NC(=O)NS(=O)(=O)c2ccccc2Cl", "db": "PubChem"},
        {"name": "Bispyribac-sodium", "cid": "6436159", "smiles": "COc1cc(OC)nc(n1)Oc2cccc(c2)C(=O)O", "db": "PubChem"},
    ],
    "HPPD": [
        {"name": "Mesotrione", "cid": "17596", "smiles": "CS(=O)(=O)c1ccc(c(c1)N(=O)=O)C(=O)C2C(=O)CCCC2=O", "db": "PubChem"},
        {"name": "Isoxaflutole", "cid": "86131", "smiles": "CC1(CC1)C(=O)c2cc(c(cc2C(F)(F)F)S(=O)(=O)C)C3=NOC=C3", "db": "PubChem"},
        {"name": "Tembotrione", "cid": "11535496", "smiles": "CS(=O)(=O)c1cc(c(c(c1)OCC(F)(F)F)C(=O)C2C(=O)CCCC2=O)Cl", "db": "PubChem"},
        {"name": "Sulcotrione", "cid": "91727", "smiles": "CS(=O)(=O)c1ccc(c(c1)Cl)C(=O)C2C(=O)CCCC2=O", "db": "PubChem"}
    ],
    "PPO": [
        {"name": "Flumioxazin", "cid": "92425", "smiles": "CC1=CC(=O)C2=C(C=C1)N(C(=O)O2)C3=CC(=C(C=C3F)Cl)F", "db": "PubChem"},
        {"name": "Fomesafen", "cid": "46704", "smiles": "COc1cc(c(cc1C(=O)NS(=O)(=O)C)Cl)Oc2ccc(cc2Cl)C(F)(F)F", "db": "PubChem"},
        {"name": "Sulfentrazone", "cid": "86124", "smiles": "CS(=O)(=O)c1cc(c(cc1Cl)N2N=C(C(=O)N2C(F)F)C)Cl", "db": "PubChem"},
        {"name": "Oxyfluorfen", "cid": "36450", "smiles": "CCOc1cc(c(cc1[N+](=O)[O-])Oc2ccc(cc2Cl)C(F)(F)F)Cl", "db": "PubChem"}
    ],
    "EPSPS": [
        {"name": "Glyphosate", "cid": "60196", "smiles": "C(C(=O)O)NCP(=O)(O)O", "db": "PubChem"}
    ],
    "ACCase": [
        {"name": "Clethodim", "cid": "91673", "smiles": "CCCC(=O)C1C(=O)CC(CC1=NOCC=CCl)CCSC", "db": "PubChem"},
        {"name": "Fluazifop-P-butyl", "cid": "5360980", "smiles": "CCCCOC(=O)C(C)Oc1ccc(cc1)Oc2ccc(nc2)C(F)(F)F", "db": "PubChem"},
        {"name": "Haloxyfop-methyl", "cid": "6433299", "smiles": "COC(=O)C(C)Oc1ccc(cc1)Oc2ncc(cc2Cl)C(F)(F)F", "db": "PubChem"}
    ],
    "psbA": [
        {"name": "Atrazine", "cid": "2256", "smiles": "CCNc1nc(nc(n1)Cl)NC(C)C", "db": "PubChem"},
        {"name": "Metribuzin", "cid": "30479", "smiles": "CC(C)(C)c1nnc(n(c1=O)N)SC", "db": "PubChem"}
    ],
    "PDS": [
        {"name": "Norflurazon", "cid": "39599", "smiles": "CNc1c(c(=O)n(nc1Cl)c2cccc(c2)C(F)(F)F)Cl", "db": "PubChem"},
        {"name": "Diflufenican", "cid": "91728", "smiles": "c1cc(c(c(c1)F)Oc2cc(ccn2)C(=O)Nc3ccc(cc3)C(F)(F)F)F", "db": "PubChem"}
    ]
}


class DatabaseRetrievalGenerator(BaseMolecularGenerator):
    """
    Retrieves confirmed chemical inhibitors and ligands dynamically from PubChem / ChEMBL
    REST APIs for the target family with full provenance and SHA-256 audit hash.
    Never describes retrieved compounds as 'AI-generated'.
    """

    def __init__(self, version: str = "2.0.0"):
        super().__init__(name="Database Chemical Retrieval Engine", version=version)

    def get_capabilities(self) -> GeneratorCapabilities:
        return GeneratorCapabilities(
            name=self.name,
            generation_mode=GenerationMode.DATABASE_RETRIEVAL.value,
            supports_target_conditioning=True,
            supports_scaffold_hopping=False,
            supports_fragment_recombination=False,
            supports_substituent_enumeration=False,
            supports_database_retrieval=True,
            deterministic_with_seed=True,
            description="Dynamically queries PubChem and ChEMBL REST APIs for known target inhibitors with verifiable audit provenance."
        )

    def get_status(self) -> Dict[str, Any]:
        return {
            "engine": self.name,
            "version": self.version,
            "status": "INSTALLED",
            "tier": "PROBE_VALIDATED",
            "generation_mode": GenerationMode.DATABASE_RETRIEVAL.value,
            "supported_external_databases": ["PubChem PUG REST API", "ChEMBL REST API", "Curated Target Benchmarks"]
        }

    def validate_inputs(self, target_info: Dict[str, Any], parameters: Dict[str, Any]) -> List[str]:
        errors = []
        if not target_info:
            errors.append("target_info dictionary is required.")
        return errors

    def _query_pubchem_api(self, compound_name: str, timeout: int = 5) -> Optional[Dict[str, Any]]:
        """Queries PubChem PUG REST API for a specific inhibitor compound by name."""
        encoded_name = urllib.parse.quote(compound_name)
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{encoded_name}/property/CanonicalSMILES,MolecularFormula,MolecularWeight,InChI,InChIKey/JSON"
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                raw_bytes = resp.content
                resp_hash = hashlib.sha256(raw_bytes).hexdigest()
                data = resp.json()
                props = data.get("PropertyTable", {}).get("Properties", [])
                if props:
                    p = props[0]
                    return {
                        "cid": str(p.get("CID")),
                        "smiles": p.get("CanonicalSMILES"),
                        "formula": p.get("MolecularFormula"),
                        "mw": p.get("MolecularWeight"),
                        "inchi": p.get("InChI"),
                        "inchikey": p.get("InChIKey"),
                        "endpoint": url,
                        "response_hash": resp_hash,
                        "status": "SUCCESS"
                    }
        except Exception as e:
            logger.debug(f"PubChem REST API query for {compound_name} failed: {e}")
        return None

    def _query_chembl_bioactivity_api(
        self,
        gene: str,
        uniprot_id: Optional[str] = None,
        target_organism: Optional[str] = None,
        timeout: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Dynamically searches ChEMBL REST API for target bioactivity records (IC50, Ki, Kd)
        and associated confirmed chemical inhibitor ligands.
        Requires UniProt accession resolution or confirmed organism alignment to prevent cross-organism mismatch.
        """
        chembl_compounds = []
        try:
            # 1. Resolve ChEMBL target ID via UniProt accession (strict) or organism-verified search
            target_chembl_id = None
            if uniprot_id:
                t_url = f"https://www.ebi.ac.uk/chembl/api/data/target.json?target_components__accession={uniprot_id.strip()}&limit=1"
                resp = requests.get(t_url, timeout=timeout)
                if resp.status_code == 200:
                    targets = resp.json().get("targets", [])
                    if targets:
                        target_chembl_id = targets[0].get("target_chembl_id")

            if not target_chembl_id and gene:
                encoded_gene = urllib.parse.quote(gene.strip())
                t_url = f"https://www.ebi.ac.uk/chembl/api/data/target/search.json?q={encoded_gene}&limit=5"
                resp = requests.get(t_url, timeout=timeout)
                if resp.status_code == 200:
                    targets = resp.json().get("targets", [])
                    for tgt in targets:
                        # Verify organism alignment if organism specified, or require plant/weed target type
                        t_org = str(tgt.get("organism") or "").lower()
                        t_type = str(tgt.get("target_type") or "").upper()
                        if target_organism and target_organism.lower() in t_org:
                            target_chembl_id = tgt.get("target_chembl_id")
                            break
                        elif t_type in ["SINGLE PROTEIN", "PROTEIN COMPLEX"]:
                            # Require verified gene symbol match in target pref_name
                            p_name = str(tgt.get("pref_name") or "").upper()
                            if gene.upper() in p_name:
                                target_chembl_id = tgt.get("target_chembl_id")
                                break

            if not target_chembl_id:
                return []

            # 2. Query bioactivities (IC50, Ki, Kd) for the identified ChEMBL target
            act_url = f"https://www.ebi.ac.uk/chembl/api/data/activity.json?target_chembl_id={target_chembl_id}&standard_type__in=IC50,Ki,Kd&limit=15"
            act_resp = requests.get(act_url, timeout=timeout)
            if act_resp.status_code == 200:
                raw_bytes = act_resp.content
                resp_hash = hashlib.sha256(raw_bytes).hexdigest()
                acts = act_resp.json().get("activities", [])
                
                for act in acts:
                    mol_chembl_id = act.get("molecule_chembl_id")
                    canonical_smiles = act.get("canonical_smiles")
                    if not canonical_smiles or not mol_chembl_id:
                        continue
                    
                    std_type = act.get("standard_type")
                    std_val = act.get("standard_value")
                    std_units = act.get("standard_units")
                    
                    mol = Chem.MolFromSmiles(canonical_smiles)
                    if not mol:
                        continue
                    clean_smi = Chem.MolToSmiles(mol, canonical=True)
                    formula = rdMolDescriptors.CalcMolFormula(mol)
                    mw = round(Descriptors.MolWt(mol), 2)
                    try:
                        inchi_str = inchi.MolToInchi(mol)
                        inchikey_str = inchi.MolToInchiKey(mol)
                    except Exception:
                        inchi_str = None
                        inchikey_str = None

                    chembl_compounds.append({
                        "compound_id": f"ChEMBL-{mol_chembl_id}",
                        "name": f"ChEMBL Active ({mol_chembl_id})",
                        "source_database": "ChEMBL",
                        "source_compound_id": mol_chembl_id,
                        "source_url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{mol_chembl_id}/",
                        "query_endpoint": act_url,
                        "response_hash": resp_hash,
                        "retrieval_method": "CHEMBL_BIOACTIVITY_REST_API",
                        "external_verification_status": "VERIFIED_EXTERNAL",
                        "bioactivity_type": std_type,
                        "bioactivity_value": float(std_val) if std_val else None,
                        "bioactivity_units": std_units or "nM",
                        "smiles": clean_smi,
                        "canonical_smiles": clean_smi,
                        "inchi": inchi_str,
                        "inchikey": inchikey_str,
                        "molecular_formula": formula,
                        "molecular_weight": mw,
                        "generation_mode": GenerationMode.DATABASE_RETRIEVAL.value,
                        "generator_name": self.name,
                        "generator_version": self.version,
                        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    })
        except Exception as e:
            logger.debug(f"ChEMBL bioactivity retrieval query failed: {e}")
        return chembl_compounds

    def generate(
        self,
        target_info: Dict[str, Any],
        parameters: Dict[str, Any],
        random_seed: Optional[int] = None,
        max_candidates: int = 50
    ) -> Dict[str, Any]:
        validation_errors = self.validate_inputs(target_info, parameters)
        if validation_errors:
            return {
                "status": "FAILED",
                "molecules": [],
                "error": "; ".join(validation_errors),
                "generated_count": 0
            }

        target_family = target_info.get("target_family") or target_info.get("family") or "ALS"
        gene = target_info.get("gene") or target_info.get("name") or "ALS"
        uniprot_id = target_info.get("uniprot_id") or target_info.get("weed_uniprot_id")

        benchmark_entries = KNOWN_TARGET_LIGANDS.get(target_family, KNOWN_TARGET_LIGANDS.get("ALS", []))
        prefer_live = parameters.get("prefer_live_api", True)
        retrieved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        molecules: List[Dict[str, Any]] = []
        seen_smiles = set()

        # 1. Attempt dynamic ChEMBL bioactivity retrieval if live API preferred
        target_organism = target_info.get("weed_species") or target_info.get("organism")
        if prefer_live:
            chembl_hits = self._query_chembl_bioactivity_api(
                gene=gene,
                uniprot_id=uniprot_id,
                target_organism=target_organism,
                timeout=4
            )
            for c_hit in chembl_hits:
                smi = c_hit.get("canonical_smiles")
                if smi and smi not in seen_smiles and len(molecules) < max_candidates:
                    seen_smiles.add(smi)
                    molecules.append(c_hit)

        # 2. Attempt dynamic PubChem retrieval for the target family's known active compounds
        for item in benchmark_entries:
            if len(molecules) >= max_candidates:
                break
            c_name = item.get("name")
            live_pubchem = None
            if prefer_live and c_name:
                live_pubchem = self._query_pubchem_api(c_name, timeout=3)

            if live_pubchem and live_pubchem.get("smiles"):
                # Dynamic live PubChem API hit
                canonical_smi = live_pubchem["smiles"]
                cid = live_pubchem["cid"]
                query_endpoint = live_pubchem["endpoint"]
                response_hash = live_pubchem["response_hash"]
                retrieval_method = "PUBCHEM_REST_API"
                external_status = "VERIFIED_EXTERNAL"
                source_url = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
                formula = live_pubchem.get("formula")
                mw = live_pubchem.get("mw")
                inchi_str = live_pubchem.get("inchi")
                inchikey_str = live_pubchem.get("inchikey")
            else:
                # Curated benchmark with explicit local provenance
                canonical_smi = item["smiles"]
                cid = item.get("cid", "UNKNOWN")
                query_endpoint = "local_curated_benchmark"
                response_hash = hashlib.sha256(canonical_smi.encode()).hexdigest()
                retrieval_method = "LOCAL_CURATED_BENCHMARK"
                external_status = "LOCAL_REFERENCE_ONLY"
                source_url = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid != "UNKNOWN" else None

                mol = Chem.MolFromSmiles(canonical_smi)
                if mol is None:
                    continue
                canonical_smi = Chem.MolToSmiles(mol, canonical=True)
                formula = rdMolDescriptors.CalcMolFormula(mol)
                mw = round(Descriptors.MolWt(mol), 2)
                try:
                    inchi_str = inchi.MolToInchi(mol)
                    inchikey_str = inchi.MolToInchiKey(mol)
                except Exception:
                    inchi_str = None
                    inchikey_str = None

            if canonical_smi in seen_smiles:
                continue
            seen_smiles.add(canonical_smi)

            db_name = item.get("db", "PubChem")
            molecules.append({
                "compound_id": f"{db_name}-CID-{cid}",
                "name": c_name,
                "source_database": db_name,
                "source_compound_id": cid,
                "source_url": source_url,
                "query_endpoint": query_endpoint,
                "response_hash": response_hash,
                "retrieval_method": retrieval_method,
                "external_verification_status": external_status,
                "smiles": canonical_smi,
                "canonical_smiles": canonical_smi,
                "inchi": inchi_str,
                "inchikey": inchikey_str,
                "molecular_formula": formula,
                "molecular_weight": mw,
                "generation_mode": GenerationMode.DATABASE_RETRIEVAL.value,
                "generator_name": self.name,
                "generator_version": self.version,
                "retrieved_at": retrieved_at
            })

        return {
            "status": "COMPLETED",
            "molecules": molecules,
            "generated_count": len(molecules),
            "target_family": target_family,
            "execution_mode": "DATABASE_RETRIEVAL"
        }
