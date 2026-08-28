from typing import Dict, Any, List, Tuple, Optional
from src.config.settings import Config
from src.database.repository import DownloadRepository
from src.downloads.queue_manager import QueueManager
from src.telegram.client import TelegramClientManager
from src.utils.filesystem import format_bytes, format_time

class StatusService:
    """Shared service for retrieving real-time system metrics, statistics, and file lists."""

    def __init__(
        self,
        config: Config,
        repo: DownloadRepository,
        client_mgr: TelegramClientManager,
        queue_mgr: QueueManager
    ):
        self.config = config
        self.repo = repo
        self.client_mgr = client_mgr
        self.queue_mgr = queue_mgr

    def get_system_status(self) -> Dict[str, Any]:
        """Returns connection and monitor operational state."""
        telethon_connected = self.client_mgr.client.is_connected() if self.client_mgr and self.client_mgr.client else False
        queue_active = self.queue_mgr.is_running and not self.queue_mgr.is_paused
        
        return {
            "system": "🟢 Funcionando",
            "telethon_connected": telethon_connected,
            "monitor_active": telethon_connected,
            "queue_active": queue_active,
            "is_paused": self.queue_mgr.is_paused
        }

    def get_summary_stats(self) -> Dict[str, int]:
        """Returns counts for TOTAL, PENDIENTE, DESCARGANDO, COMPLETADO, ERROR, CANCELADO."""
        return self.repo.get_summary_stats()

    def get_active_download_info(self) -> Optional[Dict[str, Any]]:
        """Returns details about the current active download or None."""
        item = self.queue_mgr.active_item
        info = self.queue_mgr.current_download_info
        if not item or not info:
            return None

        return {
            "item_id": item.id,
            "file_name": item.file_name,
            "downloaded": info.get("downloaded", 0),
            "total": item.file_size,
            "percent": info.get("percent", 0.0),
            "speed": info.get("speed", 0.0),
            "eta": info.get("eta", 0),
            "formatted_downloaded": format_bytes(info.get("downloaded", 0)),
            "formatted_total": format_bytes(item.file_size),
            "formatted_speed": f"{format_bytes(info.get('speed', 0.0))}/s",
            "formatted_eta": format_time(info.get("eta", 0))
        }

    def get_paginated_files(
        self,
        status_filter: Optional[str] = "ALL",
        page: int = 1,
        page_size: int = 5
    ) -> Tuple[List[Dict[str, Any]], int, int, int]:
        """
        Returns paginated file items formatted for UI consumption.
        Returns (formatted_items, total_count, current_page, total_pages)
        """
        items, total_count, total_pages = self.repo.get_items_by_status(
            status_filter=status_filter,
            page=page,
            page_size=page_size
        )

        formatted_items = []
        for item in items:
            formatted_items.append({
                "id": item.id,
                "file_name": item.file_name,
                "file_size": item.file_size,
                "formatted_size": format_bytes(item.file_size),
                "status": item.status.value,
                "downloaded_size": item.downloaded_size,
                "retry_count": item.retry_count,
                "last_error": item.last_error
            })

        return formatted_items, total_count, page, total_pages

    def get_pending_queue(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns pending queue items up to limit."""
        pending_items = self.repo.get_pending_or_downloading()
        result = []
        for item in pending_items[:limit]:
            result.append({
                "id": item.id,
                "file_name": item.file_name,
                "file_size": item.file_size,
                "formatted_size": format_bytes(item.file_size),
                "status": item.status.value
            })
        return result
