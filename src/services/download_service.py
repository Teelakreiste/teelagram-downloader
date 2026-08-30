from typing import Optional, Dict, Any
from src.config.settings import Config
from src.core.models import DownloadState, DownloadItem
from src.database.repository import DownloadRepository
from src.downloads.queue_manager import QueueManager
from src.utils.logger import logger

class DownloadService:
    """Shared service managing queue controls, item actions, and download options."""

    def __init__(self, config: Config, repo: DownloadRepository, queue_mgr: QueueManager):
        self.config = config
        self.repo = repo
        self.queue_mgr = queue_mgr

    def start_downloads(self):
        """Starts/resumes queue processing."""
        self.queue_mgr.start_downloads()

    def stop_downloads(self):
        """Pauses new queue tasks."""
        self.queue_mgr.stop_downloads()

    def cancel_active_download(self):
        """Immediately cancels current active file download."""
        self.queue_mgr.cancel_active_download()

    def approve_item_for_download(self, item_id: int) -> bool:
        """Approves a pending file for download, setting its state to PENDIENTE."""
        item = self.repo.get_item(item_id)
        if not item:
            return False
        if item.status in (DownloadState.PENDIENTE, DownloadState.ERROR, DownloadState.CANCELADO):
            self.repo.update_status(item_id, DownloadState.PENDIENTE, last_error=None)
            logger.info(f"Item ID {item_id} ({item.file_name}) aprobado y marcado como PENDIENTE.")
            return True
        return False

    def ignore_item(self, item_id: int) -> bool:
        """Ignores a pending item by setting state to CANCELADO."""
        item = self.repo.get_item(item_id)
        if not item:
            return False
        self.repo.update_status(item_id, DownloadState.CANCELADO, last_error="Ignorado por el usuario")
        logger.info(f"Item ID {item_id} ({item.file_name}) marcado como CANCELADO (ignorado).")
        return True

    def is_queue_paused(self) -> bool:
        return self.queue_mgr.is_paused

    def is_auto_download_enabled(self) -> bool:
        return self.config.auto_download

    def retry_errors(self, item_id: Optional[int] = None) -> int:
        """
        Resets ERROR or CANCELADO items back to PENDIENTE so the queue retries them.
        If item_id is given, only that item is reset.
        Returns the number of items reset.
        """
        count = self.repo.reset_errors_to_pending(item_id=item_id)
        if count > 0:
            label = f"Item ID {item_id}" if item_id else f"{count} item(s)"
            logger.info(f"{label} reseteado(s) a PENDIENTE para reintento.")
        return count

    def prioritize_item(self, item_id: int) -> bool:
        """
        Moves a download item to the top of the queue by setting priority=1000.
        Returns True if the item was found and updated.
        """
        ok = self.repo.set_priority(item_id, 1000)
        if ok:
            item = self.repo.get_item(item_id)
            logger.info(f"Prioridad máxima asignada a item ID {item_id} ({item.file_name if item else '?'}).")
        return ok

    def deprioritize_item(self, item_id: int) -> bool:
        """
        Removes priority from a download item, returning it to normal queue order (priority=0).
        Returns True if the item was found and updated.
        """
        ok = self.repo.set_priority(item_id, 0)
        if ok:
            item = self.repo.get_item(item_id)
            logger.info(f"Prioridad removida de item ID {item_id} ({item.file_name if item else '?'}).")
        return ok

