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
