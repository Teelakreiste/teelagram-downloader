import os
import sys
import asyncio
from typing import Optional, List, Dict, Any, Callable
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import Message, Document, Channel, Chat, User
from src.core.models import DownloadItem, DownloadState
from src.database.database import Database
from src.config.settings import Config
from src.utils.logger import logger

def sanitize_filename(filename: Optional[str], default_id: int) -> str:
    """Sanitizes filename while preserving spaces, accents, unicode, and extensions."""
    if not filename:
        return f"file_{default_id}.bin"
    
    # Remove invalid path characters for Windows/Linux while preserving spaces and unicode
    cleaned = "".join(c for c in filename if c not in r'<>:"/\|?*')
    cleaned = cleaned.strip()
    return cleaned if cleaned else f"file_{default_id}.bin"

class TelegramClientManager:
    """Manages Telethon connection, authentication, chat scanning, and message listening."""

    def __init__(self, config: Config):
        self.config = config
        session_path = os.path.join(config.data_dir, "telegram_session")
        self.client = TelegramClient(
            session_path,
            config.api_id,
            config.api_hash,
            system_version="4.16.30-custom",
            device_model="Desktop",
            app_version="1.0.0"
        )

    async def start(self):
        """Starts the Telethon client."""
        await self.client.connect()

    async def ensure_authenticated(self):
        """Interactive authentication flow supporting 2FA."""
        await self.client.connect()
        if not await self.client.is_user_authorized():
            phone = self.config.phone_number or input("Ingrese su número de teléfono de Telegram (con código de país, ej: +57...): ").strip()
            print(f"Enviando código de verificación a {phone}...")
            await self.client.send_code_request(phone)
            
            code = input("Ingrese el código de verificación recibido en Telegram: ").strip()
            try:
                await self.client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = input("Su cuenta tiene autenticación en dos pasos (2FA). Ingrese su contraseña: ").strip()
                await self.client.sign_in(password=password)

        me = await self.client.get_me()
        logger.info(f"Cliente Telegram conectado como: {me.first_name} (@{me.username or 'sin_user'}) [ID: {me.id}]")

    async def list_dialogs(self) -> List[Dict[str, Any]]:
        """Returns recent dialogs to help user locate CHAT_ID."""
        dialogs = []
        async for dialog in self.client.iter_dialogs(limit=50):
            entity = dialog.entity
            chat_type = "Usuario"
            if isinstance(entity, Channel):
                chat_type = "Canal" if entity.broadcast else "Supergrupo"
            elif isinstance(entity, Chat):
                chat_type = "Grupo"

            dialogs.append({
                "id": dialog.id,
                "name": dialog.name or "Sin Nombre",
                "type": chat_type
            })
        return dialogs

    def extract_file_info(self, message: Message, download_dir: str) -> Optional[DownloadItem]:
        """Extracts media file metadata from a Telegram message."""
        if not message.media:
            return None

        document = getattr(message.media, "document", None)
        if not document or not isinstance(document, Document):
            return None

        # Determine original filename
        raw_name = message.file.name if message.file else None
        file_name = sanitize_filename(raw_name, message.id)
        file_size = document.size
        mime_type = document.mime_type or "application/octet-stream"
        file_path = os.path.join(download_dir, file_name)

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

    async def scan_chat(self, chat_id: int, db: Database, download_dir: str) -> tuple[int, int]:
        """
        Scans all past messages in target chat_id and adds downloadable media to database queue.
        Returns tuple: (total_media_found, newly_registered)
        """
        logger.info(f"Iniciando escaneo de mensajes en chat_id: {chat_id}...")
        total_found = 0
        newly_added = 0

        try:
            entity = await self.client.get_entity(chat_id)
            async for message in self.client.iter_messages(entity):
                item = self.extract_file_info(message, download_dir)
                if item:
                    total_found += 1
                    inserted = db.add_item(item)
                    if inserted:
                        newly_added += 1
                        logger.info(f"Archivo detectado en escaneo: {item.file_name} ({item.file_size} B) [Msg ID: {message.id}]")

            logger.info(f"Escaneo completado. Encontrados: {total_found}, Nuevos agregados a la cola: {newly_added}")
            return total_found, newly_added

        except FloodWaitError as e:
            logger.warning(f"Límite de frecuencia de Telegram (FloodWait). Esperando {e.seconds} segundos...")
            await asyncio.sleep(e.seconds)
            return await self.scan_chat(chat_id, db, download_dir)
        except Exception as e:
            logger.error(f"Error al escanear chat {chat_id}: {e}")
            raise

    def setup_new_message_listener(
        self,
        chat_id: int,
        db: Database,
        download_dir: str,
        on_new_item_callback: Optional[Callable[[DownloadItem], None]] = None
    ):
        """Sets up live listener for incoming media messages from the configured chat_id."""
        @self.client.on(events.NewMessage(chats=chat_id))
        async def handler(event: events.NewMessage.Event):
            message = event.message
            item = self.extract_file_info(message, download_dir)
            if item:
                inserted = db.add_item(item)
                if inserted:
                    logger.info(f"[NUEVO MENSAJE] Archivo detectado: {item.file_name} ({item.file_size} B) [Msg ID: {message.id}]")
                    if on_new_item_callback:
                        on_new_item_callback(item)
