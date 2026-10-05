from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class GeneratorCapabilities(BaseModel):
    name: str
    generation_mode: str
    supports_target_conditioning: bool = True
    supports_scaffold_hopping: bool = False
    supports_fragment_recombination: bool = False
    supports_substituent_enumeration: bool = False
    supports_database_retrieval: bool = False
    deterministic_with_seed: bool = True
    description: str = ""

class BaseMolecularGenerator(ABC):
    """
    Abstract Base Class for all molecular generation engines in MIKHERB AI.
    Every generator must declare its capabilities, execute with full scientific
    provenance, and never produce fabricated outputs.
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version

    @abstractmethod
    def get_capabilities(self) -> GeneratorCapabilities:
        """Returns the capabilities and supported modes of this generator."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns current operational status (INSTALLED, NOT_INSTALLED, NOT_AVAILABLE, etc.)."""
        pass

    @abstractmethod
    def generate(
        self,
        target_info: Dict[str, Any],
        parameters: Dict[str, Any],
        random_seed: Optional[int] = None,
        max_candidates: int = 50
    ) -> Dict[str, Any]:
        """
        Generates candidate molecules against target.
        Must return structured dictionary with:
        - status: COMPLETED, FAILED, or NOT_AVAILABLE
        - molecules: List of candidate dictionaries with SMILES and provenance
        - metadata: Execution statistics and provenance details
        """
        pass

    @abstractmethod
    def validate_inputs(self, target_info: Dict[str, Any], parameters: Dict[str, Any]) -> List[str]:
        """Validates input parameters before execution. Returns list of error messages (empty if valid)."""
        pass
