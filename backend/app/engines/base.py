import shutil
import platform
import datetime
from typing import Dict, Any, List, Optional

class BaseScientificEngine:
    """Base interface for all MIKHERB AI scientific engine adapters."""

    def __init__(self, name: str, category: str, binary_name: Optional[str] = None):
        self.name = name
        self.category = category
        self.binary_name = binary_name

    def check_installation(self) -> Dict[str, Any]:
        """Check if engine or binary is installed and executable."""
        binary_path = shutil.which(self.binary_name) if self.binary_name else None
        installed = binary_path is not None if self.binary_name else True
        status = "READY" if installed else "NOT_INSTALLED"

        return {
            "engine": self.name,
            "category": self.category,
            "status": status,
            "binary_path": binary_path,
            "version": self.get_version(),
            "capabilities": self.get_capabilities(),
            "last_checked": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    def get_version(self) -> str:
        return "1.0.0"

    def get_capabilities(self) -> List[str]:
        return []

    def get_provenance(self) -> Dict[str, Any]:
        return {
            "engine": self.name,
            "status": self.check_installation()["status"],
            "version": self.get_version(),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "platform": platform.platform()
        }


class EngineStatusManager:
    """Central registry and diagnostic status manager for all scientific engines."""

    def __init__(self):
        self._engines: Dict[str, BaseScientificEngine] = {}

    def register_engine(self, key: str, engine: BaseScientificEngine):
        self._engines[key] = engine

    def get_engine_statuses(self) -> Dict[str, Any]:
        statuses = {}
        counts = {"READY": 0, "NOT_INSTALLED": 0, "SIMULATED": 0}
        for key, engine in self._engines.items():
            st = engine.check_installation()
            statuses[key] = st
            status_str = st.get("status", "NOT_INSTALLED")
            counts[status_str] = counts.get(status_str, 0) + 1

        return {
            "engines": statuses,
            "summary": counts,
            "total_engines": len(self._engines)
        }
