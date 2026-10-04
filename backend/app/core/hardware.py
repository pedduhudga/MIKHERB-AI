import shutil
import sys
import psutil

def check_gpu():
    has_gpu = False
    gpu_name = None
    vram_gb = 0.0
    try:
        import torch
        if torch.cuda.is_available():
            has_gpu = True
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
    except Exception:
        pass

    return {
        "available": has_gpu,
        "name": gpu_name or "None (CPU Mode)",
        "vram_gb": vram_gb
    }

def check_hardware_status():
    cpu_count = psutil.cpu_count(logical=True)
    memory = psutil.virtual_memory()
    total_ram_gb = round(memory.total / (1024**3), 2)
    avail_ram_gb = round(memory.available / (1024**3), 2)

    gpu_info = check_gpu()

    gnina_bin = shutil.which("gnina")
    openmm_ready = False
    try:
        import openmm
        openmm_ready = True
    except ImportError:
        pass

    rdkit_ready = False
    try:
        import rdkit
        rdkit_ready = True
    except ImportError:
        pass

    p2rank_ready = shutil.which("p2rank") is not None
    foldseek_ready = shutil.which("foldseek") is not None

    return {
        "cpu": {
            "cores": cpu_count,
            "usage_percent": psutil.cpu_percent(interval=0.1)
        },
        "memory": {
            "total_gb": total_ram_gb,
            "available_gb": avail_ram_gb,
            "usage_percent": memory.percent
        },
        "gpu": gpu_info,
        "engines": {
            "rdkit": "READY" if rdkit_ready else "UNAVAILABLE",
            "boltz2": "READY" if gpu_info["available"] else "LIMITED (CPU Mode)",
            "gnina": "READY" if gnina_bin else "CPU Simulation Mode",
            "openmm": "READY" if openmm_ready else "CPU Fallback Mode",
            "p2rank": "READY" if p2rank_ready else "Built-in Pocket Analyzer",
            "foldseek": "READY" if foldseek_ready else "Built-in Alignment Engine"
        }
    }
