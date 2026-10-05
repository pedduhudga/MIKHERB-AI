import shutil
import sys
from typing import Dict, Any

class BaseScientificEngine:
    """Base class for all scientific engine adapters."""

    def __init__(self, name: str, binary_name: str = None):
        self.name = name
        self.binary_name = binary_name

    def is_installed(self) -> bool:
        if self.binary_name:
            return shutil.which(self.binary_name) is not None
        return True

    def get_status(self) -> Dict[str, Any]:
        installed = self.is_installed()
        return {
            "name": self.name,
            "installed": installed,
            "binary_name": self.binary_name,
            "status": "READY" if installed else "NOT_INSTALLED",
            "execution_mode": "NATIVE_BINARY" if installed else "SURROGATE_HEURISTIC_AVAILABLE"
        }
