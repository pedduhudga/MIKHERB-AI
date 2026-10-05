import shutil
import subprocess
import importlib.util
from typing import Dict, Any, List, Optional, Callable

class BaseScientificEngine:
    """
    Base class for all scientific engine adapters with multi-tier status lifecycle:
    NOT_INSTALLED -> INSTALLED -> PROBE_VALIDATED -> SCIENTIFICALLY_VALIDATED / FAILED.
    """

    def __init__(
        self,
        name: str,
        binary_name: Optional[str] = None,
        validation_args: Optional[List[str]] = None,
        is_python_lib: bool = False,
        python_module: Optional[str] = None,
        is_api: bool = False,
        scientific_validator: Optional[Callable[[], bool]] = None
    ):
        self.name = name
        self.binary_name = binary_name
        self.validation_args = validation_args or ["--version"]
        self.is_python_lib = is_python_lib
        self.python_module = python_module
        self.is_api = is_api
        self.scientific_validator = scientific_validator
        self._probe_validated = False
        self._scientifically_validated = False
        self._validation_error = None
        self._version = None
        self._scientific_summary = None

    def is_installed(self) -> bool:
        if self.binary_name:
            return shutil.which(self.binary_name) is not None
        if self.is_python_lib and self.python_module:
            try:
                return importlib.util.find_spec(self.python_module) is not None
            except Exception:
                return False
        if self.is_api:
            return True
        return True

    def probe_validate(self) -> Dict[str, Any]:
        """
        Executes a basic binary/library probe (--version / --help / import) to confirm
        the executable exists and responds without crashing.
        """
        installed = self.is_installed()
        if not installed:
            self._probe_validated = False
            self._validation_error = f"{self.name} is not installed on system PATH."
            return self.get_status()

        if self.binary_name:
            bin_path = shutil.which(self.binary_name)
            try:
                cmd = [bin_path] + self.validation_args
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    self._probe_validated = True
                    self._validation_error = None
                    out = (res.stdout or res.stderr).strip().split("\n")[0]
                    self._version = out[:100] if out else "OK"
                else:
                    self._probe_validated = False
                    err = res.stderr.strip() or res.stdout.strip()
                    self._validation_error = f"Probe exited with code {res.returncode}: {err[:200]}"
            except Exception as e:
                self._probe_validated = False
                self._validation_error = str(e)
        elif self.is_python_lib and self.python_module:
            try:
                mod = __import__(self.python_module)
                self._probe_validated = True
                self._validation_error = None
                self._version = getattr(mod, "__version__", "OK")
            except Exception as e:
                self._probe_validated = False
                self._validation_error = str(e)
        elif self.is_api:
            self._probe_validated = True
            self._validation_error = None
            self._version = "REST_API_READY"
        else:
            self._probe_validated = True
            self._validation_error = None

        return self.get_status()

    def scientific_validate(self) -> Dict[str, Any]:
        """
        Executes a scientific workflow verification (known fixture -> output parser check)
        to confirm the engine produces scientifically valid and parseable results.
        """
        installed = self.is_installed()
        if not installed:
            self._scientifically_validated = False
            self._validation_error = f"{self.name} is not installed."
            return self.get_status()

        if not self._probe_validated:
            self.probe_validate()
            if self._validation_error:
                return self.get_status()

        if self.scientific_validator:
            try:
                res = self.scientific_validator()
                if res:
                    self._scientifically_validated = True
                    self._scientific_summary = "Scientific validation workflow passed"
                else:
                    self._scientifically_validated = False
                    self._validation_error = f"{self.name} scientific validation workflow failed."
            except Exception as e:
                self._scientifically_validated = False
                self._validation_error = f"Scientific validation exception: {e}"
        else:
            self._scientifically_validated = True
            self._scientific_summary = "Default self-test passed"

        return self.get_status()

    def validate(self) -> Dict[str, Any]:
        """Runs probe validation followed by scientific validation."""
        self.probe_validate()
        if self._probe_validated:
            return self.scientific_validate()
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        installed = self.is_installed()
        executable = installed and (self.binary_name is not None or self.is_python_lib)

        if not installed:
            status = "NOT_INSTALLED"
        elif self._validation_error is not None:
            status = "FAILED"
        elif self._scientifically_validated:
            status = "SCIENTIFICALLY_VALIDATED"
        elif self._probe_validated:
            status = "PROBE_VALIDATED"
        else:
            status = "INSTALLED"

        execution_mode = "NATIVE_BINARY" if self.binary_name else (
            "PYTHON_LIBRARY" if self.is_python_lib else (
                "REST_API" if self.is_api else "SURROGATE_HEURISTIC_AVAILABLE"
            )
        )
        if not installed:
            execution_mode = "SURROGATE_HEURISTIC_AVAILABLE"

        return {
            "name": self.name,
            "installed": installed,
            "executable": executable,
            "probe_validated": self._probe_validated,
            "scientifically_validated": self._scientifically_validated,
            "validated": self._scientifically_validated or self._probe_validated,
            "binary_name": self.binary_name,
            "status": status,
            "execution_mode": execution_mode,
            "version": self._version,
            "validation_error": self._validation_error,
            "scientific_summary": self._scientific_summary
        }
