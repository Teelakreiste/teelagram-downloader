import os
from typing import Optional, Callable
from telethon import events
from telethon.tl.types import Message, Document
from src.core.models import DownloadItem, DownloadState
from src.database.repository import DownloadRepository
from src.utils.filesystem import sanitize_filename
from src.utils.logger import logger

class TelegramMessageHandler:
    """Extracts media metadata and listens for incoming media messages in Telegram channels/chats."""

    def __init__(self, repo: DownloadRepository, download_dir: str):
        self.repo = repo
        self.download_dir = download_dir

    def extract_file_info(self, message: Message) -> Optional[DownloadItem]:
        """Extracts media metadata from a Telethon Message object."""
        if not message or not message.media:
            return None

        document = getattr(message.media, "document", None)
        if not document or not isinstance(document, Document):
            return None

        raw_name = message.file.name if message.file else None
        file_name = sanitize_filename(raw_name, message.id)
        file_size = document.size
        mime_type = document.mime_type or "application/octet-stream"
        file_path = os.path.join(self.download_dir, file_name)

        return DownloadItem(
            id=None,
            chat_id=message.chat_id,
            message_id=message.id,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            status=DownloadState.PENDIENTE,
            date_detected=message.date
        )

    def register_new_message_listener(
        self,
        client,
        chat_id: int,
        on_new_item_callback: Optional[Callable[[DownloadItem], None]] = None
    ):
        """Attaches a listener for incoming messages on the configured chat_id."""
        @client.on(events.NewMessage(chats=chat_id))
        async def handler(event: events.NewMessage.Event):
            message = event.message
            item = self.extract_file_info(message)
            if item:
                inserted = self.repo.add_item(item)
                if inserted:
                    logger.info(f"[NUEVO ARCHIVO] Detectado: {item.file_name} ({item.file_size} B) [Msg ID: {message.id}]")
                    if on_new_item_callback:
                        try:
                            # Fetch full item with database assigned ID if needed
                            registered_item = self.repo.db.get_all_items()[0] if self.repo.get_all_items() else item
                            on_new_item_callback(registered_item)
                        except Exception as e:
                            logger.error(f"Error invocado callback de nuevo archivo: {e}")
