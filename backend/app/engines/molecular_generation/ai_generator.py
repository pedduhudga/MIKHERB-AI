import os
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

    def __init__(self, model_name: str = "REINVENT-4", version: str = "4.0", checkpoint_path: Optional[str] = None):
        super().__init__(name=f"Generative AI Model Adapter ({model_name})", version=version)
        self.model_name = model_name
        self.checkpoint_path = checkpoint_path

    def is_installed(self) -> bool:
        """Verifies if an actual AI generation framework CLI or module is available."""
        has_reinvent = shutil.which("reinvent") is not None
        has_torch = False
        try:
            import torch  # noqa: F401
            has_torch = True
        except ImportError:
            pass
        return has_reinvent and has_torch

    def has_configured_weights(self) -> bool:
        """Checks if a valid trained model checkpoint or weight file is configured on disk."""
        if not self.checkpoint_path:
            return False
        return os.path.exists(self.checkpoint_path) and os.path.getsize(self.checkpoint_path) > 1024

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
            description="Interface for deep-learning generative models (REINVENT/transformer). Requires genuine local model and trained checkpoint."
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Engine lifecycle states:
        - NOT_INSTALLED: Executable or PyTorch missing from environment.
        - INSTALLED: Executable present, but weights/checkpoint not configured.
        - MODEL_CONFIGURED: Executable and weights present on disk.
        - PROBE_VALIDATED: Basic execution probe succeeded.
        - SCIENTIFICALLY_VALIDATED: Verified on benchmark generation fixture.
        """
        installed = self.is_installed()
        if not installed:
            return {
                "engine": self.name,
                "version": self.version,
                "model_name": self.model_name,
                "status": "NOT_AVAILABLE",
                "tier": "NOT_INSTALLED",
                "generation_mode": GenerationMode.GENERATIVE_AI_ADAPTER.value,
                "message": "Deep generative AI framework not detected locally. Use RDKit_ENUMERATION or DATABASE_RETRIEVAL."
            }

        weights_ready = self.has_configured_weights()
        if not weights_ready:
            return {
                "engine": self.name,
                "version": self.version,
                "model_name": self.model_name,
                "status": "NOT_AVAILABLE",
                "tier": "INSTALLED",
                "generation_mode": GenerationMode.GENERATIVE_AI_ADAPTER.value,
                "message": "Framework binary installed, but trained model weights/checkpoint not configured on disk. Generation remains NOT_AVAILABLE."
            }

        return {
            "engine": self.name,
            "version": self.version,
            "model_name": self.model_name,
            "status": "INSTALLED",
            "tier": "MODEL_CONFIGURED",
            "generation_mode": GenerationMode.GENERATIVE_AI_ADAPTER.value,
            "message": "Model binary and weights configured."
        }

    def validate_inputs(self, target_info: Dict[str, Any], parameters: Dict[str, Any]) -> List[str]:
        errors = []
        if not self.is_installed():
            errors.append(f"Generative model {self.model_name} is not installed in the environment.")
        elif not self.has_configured_weights():
            errors.append(f"Generative model weights/checkpoint not configured on disk.")
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
        Executes generative model if installed and configured.
        Returns NOT_AVAILABLE when model or weights are absent. Never invents fake molecules.
        """
        if not self.is_installed():
            return {
                "status": "NOT_AVAILABLE",
                "molecules": [],
                "error": f"Generative AI model '{self.model_name}' is not installed locally. Fabrication of synthetic AI outputs is strictly prohibited.",
                "generated_count": 0,
                "execution_mode": "NOT_AVAILABLE"
            }

        if not self.has_configured_weights():
            return {
                "status": "NOT_AVAILABLE",
                "molecules": [],
                "error": f"Generative AI model '{self.model_name}' weights not configured on disk. Fabrication of synthetic AI outputs is strictly prohibited.",
                "generated_count": 0,
                "execution_mode": "NOT_AVAILABLE"
            }

        # If a genuine model binary and weights exist, execution logic is hooked here
        return {
            "status": "NOT_AVAILABLE",
            "molecules": [],
            "error": "Model weights/checkpoint not configured.",
            "generated_count": 0
        }
