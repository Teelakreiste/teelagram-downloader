import asyncio
from typing import Tuple
from src.config.settings import Config
from src.database.repository import DownloadRepository
from src.telegram.client import TelegramClientManager
from src.utils.logger import logger

class ScanService:
    """Shared service for scanning target chat history and registering media items into SQLite."""

    def __init__(self, config: Config, repo: DownloadRepository, client_mgr: TelegramClientManager):
        self.config = config
        self.repo = repo
        self.client_mgr = client_mgr

    async def scan_chat(self) -> Tuple[int, int]:
        """
        Executes chat history scan for the configured CHAT_ID.
        Returns (total_found, newly_added)
        """
        if not self.config.chat_id:
            raise ValueError("CHAT_ID no está configurado en las variables de entorno.")

        # Ensure client is connected and authenticated
        if not self.client_mgr.client.is_connected():
            await self.client_mgr.start()
        await self.client_mgr.ensure_authenticated()

        total, new_items = await self.client_mgr.scan_chat(
            chat_id=self.config.chat_id,
            repo=self.repo,
            download_dir=self.config.download_dir
        )
        return total, new_items
