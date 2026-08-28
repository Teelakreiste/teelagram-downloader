import os
import shutil
from typing import Optional, Tuple

def format_bytes(size: float) -> str:
    """Formats bytes into human readable string (B, KB, MB, GB, TB)."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def format_time(seconds: float) -> str:
    """Formats seconds into HH:MM:SS string."""
    if seconds < 0 or seconds != seconds:  # NaN check
        return "00:00:00"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def sanitize_filename(filename: Optional[str], default_id: int) -> str:
    """Sanitizes filename while preserving spaces, accents, unicode, and extensions."""
    if not filename:
        return f"file_{default_id}.bin"
    
    # Remove invalid path characters for Windows/Linux while preserving spaces and unicode
    cleaned = "".join(c for c in filename if c not in r'<>:"/\|?*')
    cleaned = cleaned.strip()
    return cleaned if cleaned else f"file_{default_id}.bin"

def check_disk_space(download_dir: str, needed_bytes: int, min_disk_space_gb: float = 5.0) -> Tuple[bool, int, str]:
    """
    Verifies if sufficient free disk space exists before downloading.
    Returns (has_space: bool, free_bytes: int, message: str)
    """
    try:
        os.makedirs(download_dir, exist_ok=True)
        total, used, free = shutil.disk_usage(download_dir)
        min_required = int(min_disk_space_gb * (1024 ** 3))
        
        if free < needed_bytes:
            msg = f"Espacio insuficiente en disco. Disponible: {format_bytes(free)}, Necesario: {format_bytes(needed_bytes)}"
            return False, free, msg
            
        if free < min_required:
            msg = f"Alerta de disco: Espacio libre ({format_bytes(free)}) es inferior al mínimo configurado ({format_bytes(min_required)})"
            return True, free, msg

        return True, free, "Espacio en disco suficiente."
    except Exception as e:
        return False, 0, f"Error comprobando espacio en disco: {e}"
