import os
import sys
import asyncio
import time
from typing import Dict, Any, Optional, List
from telethon.errors import FloodWaitError
from src.core.models import DownloadItem, DownloadState
from src.database.database import Database
from src.downloads.downloader import FileDownloader, format_bytes, format_time
from src.telegram.client import TelegramClientManager
from src.config.settings import Config
from src.utils.logger import logger

class QueueManager:
    """Manages persistent SQLite download queue and interactive console UI updates."""

    def __init__(self, config: Config, db: Database, client_mgr: TelegramClientManager, downloader: FileDownloader):
        self.config = config
        self.db = db
        self.client_mgr = client_mgr
        self.downloader = downloader
        self.is_running = False
        self.current_download_info: Dict[str, Any] = {}
        self.active_file_name: str = "Ninguno"
        self.chat_title: str = str(config.chat_id)

    def render_console_dashboard(self, stats: Dict[str, int]):
        """Renders clean, non-flooding real-time terminal dashboard."""
        os.system("cls" if os.name == "nt" else "clear")

        info = self.current_download_info
        print("========================================")
        print(" TELEGRAM FILE DOWNLOADER")
        print("========================================")
        print(f"\nChat: {self.chat_title}\n")
        print("Archivos:")
        print(f"  Detectados:   {stats.get('TOTAL', 0):>5}")
        print(f"  Pendientes:   {stats.get('PENDIENTE', 0):>5}")
        print(f"  Descargando:  {stats.get('DESCARGANDO', 0):>5}")
        print(f"  Completados:  {stats.get('COMPLETADO', 0):>5}")
        print(f"  Errores:      {stats.get('ERROR', 0):>5}")
        print()

        if self.active_file_name != "Ninguno" and info:
            dl = info.get("downloaded", 0)
            tot = info.get("total", 0)
            pct = info.get("percent", 0.0)
            spd = info.get("speed", 0.0)
            eta = info.get("eta", 0)

            print("Descarga actual:")
            print(f"  Archivo:   {self.active_file_name}")
            print(f"  Progreso:  {pct:.1f}%")
            print(f"  Tamaño:    {format_bytes(dl)} / {format_bytes(tot)}")
            print(f"  Velocidad: {format_bytes(spd)}/s")
            print(f"  ETA:       {format_time(eta)}")
        else:
            print("Descarga actual: Ninguna en progreso.")
        print("\n[Presione Ctrl+C para detener el servicio]\n")

    def _on_progress(self, item: DownloadItem, progress: Dict[str, Any]):
        """Callback from FileDownloader on progress ticks."""
        self.active_file_name = item.file_name
        self.current_download_info = progress
        stats = self.db.get_summary_stats()
        self.render_console_dashboard(stats)

    async def process_queue_loop(self):
        """Main loop that continuously pulls tasks from SQLite queue and processes downloads."""
        self.is_running = True
        logger.info("Iniciando servicio de cola de descargas...")

        try:
            entity = await self.client_mgr.client.get_entity(self.config.chat_id)
            self.chat_title = getattr(entity, 'title', getattr(entity, 'first_name', str(self.config.chat_id)))
        except Exception:
            self.chat_title = str(self.config.chat_id)

        while self.is_running:
            try:
                stats = self.db.get_summary_stats()
                pending_items = self.db.get_pending_or_downloading()

                if not pending_items:
                    self.active_file_name = "Ninguno"
                    self.current_download_info = {}
                    self.render_console_dashboard(stats)
                    await asyncio.sleep(5)
                    continue

                # Process tasks up to MAX_CONCURRENT_DOWNLOADS
                batch = pending_items[:self.config.max_concurrent_downloads]

                for item in batch:
                    if not self.is_running:
                        break

                    # Check max retry limit (5 retries)
                    if item.retry_count >= 5:
                        logger.error(f"El archivo {item.file_name} ha alcanzado el límite máximo de reintentos (5). Marcando como ERROR.")
                        self.db.update_status(item.id, DownloadState.ERROR, last_error="Límite máximo de reintentos alcanzado")
                        continue

                    # Fetch Telegram Message object
                    try:
                        messages = await self.client_mgr.client.get_messages(self.config.chat_id, ids=item.message_id)
                        if not messages or not messages.media:
                            logger.error(f"Mensaje ID {item.message_id} ya no contiene media descargable en Telegram.")
                            self.db.update_status(item.id, DownloadState.ERROR, last_error="Mensaje no encontrado o sin media")
                            continue

                        media_obj = messages.media
                    except FloodWaitError as e:
                        logger.warning(f"FloodWaitError: Esperando {e.seconds}s antes de reintentar...")
                        await asyncio.sleep(e.seconds)
                        continue
                    except Exception as e:
                        logger.error(f"Error al obtener mensaje ID {item.message_id}: {e}")
                        self.db.update_status(item.id, DownloadState.ERROR, last_error=str(e))
                        continue

                    # Perform streaming download with resume
                    success = await self.downloader.download_item(
                        item=item,
                        media_object=media_obj,
                        progress_callback=self._on_progress
                    )

                    self.active_file_name = "Ninguno"
                    self.current_download_info = {}

                    if not success:
                        # Pause briefly before continuing queue on error
                        await asyncio.sleep(3)

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                self.is_running = False
                break
            except Exception as e:
                logger.error(f"Error imprevisto en el bucle de la cola: {e}")
                await asyncio.sleep(5)

    def stop(self):
        """Stops the queue manager loop."""
        self.is_running = False
