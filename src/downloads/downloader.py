import os
import re
import time
import shutil
import glob
from typing import Callable, Optional, Dict, Any
from telethon import TelegramClient
from src.core.models import DownloadItem, DownloadState
from src.database.database import Database
from src.utils.logger import logger

# Chunk size for MTProto downloads (512 KB)
CHUNK_SIZE = 512 * 1024
# Telegram MTProto offset alignment requirement (128 KB)
ALIGNMENT_SIZE = 128 * 1024

def format_bytes(size: float) -> str:
    """Formats bytes into human readable string (B, KB, MB, GB)."""
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

class FileDownloader:
    """Handles streaming downloads with resume support, progress calculation, and verification."""

    def __init__(self, client: TelegramClient, db: Database, download_dir: str, min_disk_space_gb: float = 5.0):
        self.client = client
        self.db = db
        self.download_dir = download_dir
        self.min_disk_space_gb = min_disk_space_gb

    def check_disk_space(self, needed_bytes: int) -> bool:
        """Verifies if sufficient free disk space exists before downloading."""
        try:
            total, used, free = shutil.disk_usage(self.download_dir)
            min_required = int(self.min_disk_space_gb * (1024 ** 3))
            
            if free < needed_bytes:
                logger.error(
                    f"Espacio insuficiente en disco. Disponible: {format_bytes(free)}, "
                    f"Necesario para archivo: {format_bytes(needed_bytes)}"
                )
                return False
                
            if free < min_required:
                logger.warning(
                    f"Alerta de disco: Espacio libre en disco ({format_bytes(free)}) "
                    f"es inferior al mínimo configurado ({format_bytes(min_required)})"
                )
            return True
        except Exception as e:
            logger.error(f"Error comprobando espacio en disco: {e}")
            return False

    async def download_item(
        self,
        item: DownloadItem,
        media_object: Any,
        progress_callback: Optional[Callable[[DownloadItem, Dict[str, Any]], None]] = None
    ) -> bool:
        """
        Downloads a Telegram media item using chunk streaming and resume capability.
        """
        final_path = item.file_path
        part_path = f"{final_path}.part"

        # 1. Check if final file already exists and is fully downloaded
        if os.path.exists(final_path):
            existing_final_size = os.path.getsize(final_path)
            if existing_final_size == item.file_size:
                logger.info(f"El archivo {item.file_name} ya existe y está completo ({format_bytes(item.file_size)}). Omite descarga.")
                self.db.update_status(item.id, DownloadState.COMPLETADO, downloaded_size=item.file_size)
                self.check_split_archive_group(final_path)
                return True

        # 2. Determine resume offset from .part file if it exists
        existing_part_size = 0
        if os.path.exists(part_path):
            existing_part_size = os.path.getsize(part_path)

        # Align offset to Telegram 128 KB boundary
        aligned_offset = (existing_part_size // ALIGNMENT_SIZE) * ALIGNMENT_SIZE
        
        # Calculate remaining bytes to download
        remaining_bytes = item.file_size - aligned_offset

        # 3. Check disk space for remaining bytes
        if not self.check_disk_space(remaining_bytes):
            err = f"Espacio insuficiente en disco. Disponible < {format_bytes(remaining_bytes)}"
            self.db.update_status(item.id, DownloadState.ERROR, last_error=err)
            return False

        # 4. Open .part file and position cursor at aligned offset
        if aligned_offset > 0:
            logger.info(f"Reanudando descarga para {item.file_name} desde byte {aligned_offset} ({format_bytes(aligned_offset)})")
            f = open(part_path, "r+b")
            f.seek(aligned_offset)
            f.truncate(aligned_offset)
        else:
            logger.info(f"Iniciando nueva descarga: {item.file_name} ({format_bytes(item.file_size)})")
            f = open(part_path, "wb")

        self.db.update_status(item.id, DownloadState.DESCARGANDO, downloaded_size=aligned_offset)

        downloaded_bytes = aligned_offset
        start_time = time.time()
        last_db_update = time.time()
        last_progress_call = time.time()

        try:
            # Stream chunks from Telegram via Telethon iter_download
            async for chunk in self.client.iter_download(
                media_object,
                offset=aligned_offset,
                request_size=CHUNK_SIZE
            ):
                f.write(chunk)
                downloaded_bytes += len(chunk)

                now = time.time()
                elapsed = now - start_time
                speed = (downloaded_bytes - aligned_offset) / elapsed if elapsed > 0 else 0
                remaining = item.file_size - downloaded_bytes
                eta = remaining / speed if speed > 0 else 0
                percent = (downloaded_bytes / item.file_size * 100) if item.file_size > 0 else 0

                progress_data = {
                    "downloaded": downloaded_bytes,
                    "total": item.file_size,
                    "percent": percent,
                    "speed": speed,
                    "eta": eta
                }

                # Update database progress every 3 seconds
                if now - last_db_update >= 3.0:
                    self.db.update_progress(item.id, downloaded_bytes)
                    last_db_update = now

                # Trigger UI callback every 0.5 seconds
                if progress_callback and (now - last_progress_call >= 0.5):
                    progress_callback(item, progress_data)
                    last_progress_call = now

            f.close()

            # 5. Integrity verification
            actual_size = os.path.getsize(part_path)
            if actual_size != item.file_size:
                err_msg = f"Verificación fallida: Tamaño descargado ({actual_size} B) != Esperado ({item.file_size} B)"
                logger.error(err_msg)
                self.db.update_status(item.id, DownloadState.ERROR, downloaded_size=actual_size, last_error=err_msg)
                return False

            # 6. Rename .part to final target file
            os.replace(part_path, final_path)
            self.db.update_status(item.id, DownloadState.COMPLETADO, downloaded_size=item.file_size)
            logger.info(f"Descarga completada con éxito: {item.file_name} ({format_bytes(item.file_size)})")

            # 7. Check for completed split archive set
            self.check_split_archive_group(final_path)
            return True

        except Exception as e:
            f.close()
            err_msg = f"Error durante la descarga de {item.file_name}: {str(e)}"
            logger.error(err_msg)
            self.db.update_status(item.id, DownloadState.ERROR, downloaded_size=downloaded_bytes, last_error=str(e))
            return False

    def check_split_archive_group(self, file_path: str):
        """
        Checks if the downloaded file is part of a split archive set
        (e.g., .part01.rar or .7z.001) and logs when all parts are complete.
        """
        filename = os.path.basename(file_path)
        dir_name = os.path.dirname(file_path)

        # Pattern 1: archive.part01.rar, archive.part02.rar
        match_part = re.search(r"^(.*?)\.part(\d+)\.rar$", filename, re.IGNORECASE)
        # Pattern 2: archive.7z.001, archive.rar.001, archive.zip.001
        match_001 = re.search(r"^(.*?)\.(7z|rar|zip|iso)\.(\d+)$", filename, re.IGNORECASE)

        base_name = None
        ext_type = None

        if match_part:
            base_name = match_part.group(1)
            ext_type = "part_rar"
        elif match_001:
            base_name = match_001.group(1)
            ext_type = "numbered"

        if not base_name:
            return

        # Find all related parts in directory
        if ext_type == "part_rar":
            pattern = os.path.join(dir_name, f"{glob.escape(base_name)}.part*.rar")
            files = glob.glob(pattern)
        else:
            pattern = os.path.join(dir_name, f"{glob.escape(base_name)}.*.[0-9]*")
            files = glob.glob(pattern)

        # Filter out .part temporary download files
        files = [f for f in files if not f.endswith(".part")]
        
        if len(files) > 1:
            part_basenames = [os.path.basename(f) for f in sorted(files)]
            logger.info(f"[CONJUNTO COMPLETO DETECTADO] Todos los archivos del conjunto están presentes ({len(files)} partes):\n" + "\n".join(f"  - {name}" for name in part_basenames))
