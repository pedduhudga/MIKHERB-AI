import json
import os
import time
import sys
import platform
from datetime import datetime

def generate_provenance_record(
    action: str,
    parameters: dict,
    inputs: dict,
    outputs: dict,
    software_versions: dict = None
) -> dict:
    default_versions = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "mikherb_ai": "1.0.0"
    }
    try:
        import rdkit
        default_versions["rdkit"] = rdkit.__version__
    except Exception:
        pass

    if software_versions:
        default_versions.update(software_versions)

    provenance = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "timestamp_epoch": time.time(),
        "action": action,
        "parameters": parameters,
        "inputs": inputs,
        "outputs": outputs,
        "environment": {
            "os": platform.system(),
            "architecture": platform.machine(),
            "versions": default_versions
        },
        "reproducibility": {
            "random_seed": parameters.get("random_seed", 42),
            "deterministic": True
        }
    }
    return provenance

def save_provenance_file(directory: str, filename: str, record: dict):
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, filename)
    with open(filepath, "w") as f:
        json.dump(record, f, indent=2)
    return filepath
