import shutil
from typing import Dict, Any, List, Optional
from app.engines.molecular_generation.base_generator import BaseMolecularGenerator, GeneratorCapabilities
from app.engines.molecular_generation.schemas import GenerationMode

class GenerativeModelAdapter(BaseMolecularGenerator):
    """
    Adapter interface for deep generative molecular models (e.g., REINVENT,
    Graph generative models, SMILES language models, Chemformer).
    
    SCIENTIFIC INTEGRITY RULE:
    Strictly preserves availability semantics. If a genuine generative AI model
    is not installed and configured locally, it returns status = NOT_AVAILABLE.
    NEVER fabricates synthetic AI-generated structures.
    """

    def __init__(self, model_name: str = "REINVENT-4", version: str = "4.0"):
        super().__init__(name=f"Generative AI Model Adapter ({model_name})", version=version)
        self.model_name = model_name

    def is_installed(self) -> bool:
        """Verifies if an actual AI generation framework CLI or module is available."""
        # Check for genuine external binaries or Python modules
        has_reinvent = shutil.which("reinvent") is not None
        has_torch = False
        try:
            import torch  # noqa: F401
            has_torch = True
        except ImportError:
            pass
        return has_reinvent and has_torch

    def get_capabilities(self) -> GeneratorCapabilities:
        return GeneratorCapabilities(
            name=self.name,
            generation_mode=GenerationMode.GENERATIVE_AI_ADAPTER.value,
            supports_target_conditioning=True,
            supports_scaffold_hopping=True,
            supports_fragment_recombination=False,
            supports_substituent_enumeration=False,
            supports_database_retrieval=False,
            deterministic_with_seed=True,
            description="Interface for deep-learning generative models (REINVENT/transformer). Requires genuine local model."
        )

    def get_status(self) -> Dict[str, Any]:
        installed = self.is_installed()
        return {
            "engine": self.name,
            "version": self.version,
            "model_name": self.model_name,
            "status": "INSTALLED" if installed else "NOT_AVAILABLE",
            "tier": "SCIENTIFICALLY_VALIDATED" if installed else "NOT_AVAILABLE",
            "generation_mode": GenerationMode.GENERATIVE_AI_ADAPTER.value,
            "message": "Model ready" if installed else "Deep generative AI framework not detected locally. Use RDKit_ENUMERATION or DATABASE_RETRIEVAL."
        }

    def validate_inputs(self, target_info: Dict[str, Any], parameters: Dict[str, Any]) -> List[str]:
        errors = []
        if not self.is_installed():
            errors.append(f"Generative model {self.model_name} is not installed in the environment.")
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
        Executes generative model if installed.
        Returns NOT_AVAILABLE when model is absent. Never invents fake molecules.
        """
        if not self.is_installed():
            return {
                "status": "NOT_AVAILABLE",
                "molecules": [],
                "error": f"Generative AI model '{self.model_name}' is not installed locally. Fabrication of synthetic AI outputs is strictly prohibited.",
                "generated_count": 0,
                "execution_mode": "NOT_AVAILABLE"
            }

        # If a genuine model binary exists in the future, execution logic is hooked here
        return {
            "status": "NOT_AVAILABLE",
            "molecules": [],
            "error": "Model weights/checkpoint not configured.",
            "generated_count": 0
        }
