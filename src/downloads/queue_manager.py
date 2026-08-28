import os
import sys
import asyncio
import time
from typing import Dict, Any, Optional, List, Callable
from telethon.errors import FloodWaitError
from src.core.models import DownloadItem, DownloadState
from src.database.repository import DownloadRepository
from src.downloads.downloader import FileDownloader
from src.telegram.client import TelegramClientManager
from src.config.settings import Config
from src.utils.filesystem import format_bytes, format_time
from src.utils.logger import logger

class QueueManager:
    """Manages persistent SQLite download queue, pause/resume controls, and event callbacks."""

    def __init__(self, config: Config, repo: DownloadRepository, client_mgr: TelegramClientManager, downloader: FileDownloader):
        self.config = config
        self.repo = repo
        self.client_mgr = client_mgr
        self.downloader = downloader
        self.is_running = False
        self.is_paused = False
        self.current_download_info: Dict[str, Any] = {}
        self.active_item: Optional[DownloadItem] = None
        self.active_file_name: str = "Ninguno"
        self.chat_title: str = str(config.chat_id)

        # Callbacks
        self.on_download_start: Optional[Callable[[DownloadItem], None]] = None
        self.on_download_complete: Optional[Callable[[DownloadItem], None]] = None
        self.on_download_error: Optional[Callable[[DownloadItem, str, int], None]] = None
        self.on_queue_completed: Optional[Callable[[Dict[str, int]], None]] = None
        self.on_progress_update: Optional[Callable[[DownloadItem, Dict[str, Any]], None]] = None

    def render_console_dashboard(self, stats: Dict[str, int]):
        """Renders clean, non-flooding real-time terminal dashboard."""
        os.system("cls" if os.name == "nt" else "clear")

        info = self.current_download_info
        print("========================================")
        print(" TELEGRAM FILE DOWNLOADER")
        print("========================================")
        print(f"\nChat: {self.chat_title}")
        print(f"Estado de la Cola: {'⏸ Detenida' if self.is_paused else '🟢 Activa'}\n")
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
        self.active_item = item
        self.active_file_name = item.file_name
        self.current_download_info = progress
        stats = self.repo.get_summary_stats()
        self.render_console_dashboard(stats)

        if self.on_progress_update:
            try:
                self.on_progress_update(item, progress)
            except Exception as e:
                logger.error(f"Error en callback on_progress_update: {e}")

    def start_downloads(self):
        """Resumes/starts processing the queue."""
        self.is_paused = False
        logger.info("Procesamiento de la cola iniciado/reanudado.")

    def stop_downloads(self):
        """Pauses processing new files in queue (current file will finish unless cancelled)."""
        self.is_paused = True
        logger.info("Procesamiento de la cola detenido. No se iniciarán nuevos archivos.")

    def cancel_active_download(self):
        """Immediately cancels current active download."""
        if self.active_item:
            logger.info(f"Solicitando cancelación de descarga activa: {self.active_file_name}")
            self.downloader.request_cancel()

    async def process_queue_loop(self):
        """Main loop that continuously pulls tasks from SQLite queue and processes downloads."""
        self.is_running = True
        logger.info("Iniciando bucle del gestor de colas de descargas...")

        try:
            entity = await self.client_mgr.client.get_entity(self.config.chat_id)
            self.chat_title = getattr(entity, 'title', getattr(entity, 'first_name', str(self.config.chat_id)))
        except Exception:
            self.chat_title = str(self.config.chat_id)

        had_pending_work = False

        while self.is_running:
            try:
                stats = self.repo.get_summary_stats()

                if self.is_paused:
                    self.active_file_name = "Ninguno"
                    self.active_item = None
                    self.current_download_info = {}
                    self.render_console_dashboard(stats)
                    await asyncio.sleep(3)
                    continue

                # Ensure client is connected
                if not self.client_mgr.client.is_connected():
                    try:
                        logger.info("Cliente Telethon desconectado. Reconectando...")
                        await self.client_mgr.client.connect()
                    except Exception as ce:
                        logger.warning(f"Esperando restauración de red para reconectar Telethon: {ce}")
                        await asyncio.sleep(5)
                        continue

                pending_items = self.repo.get_pending_or_downloading()

                if not pending_items:
                    if had_pending_work:
                        logger.info("Todas las descargas pendientes de la cola han sido completadas.")
                        had_pending_work = False
                        if self.on_queue_completed:
                            try:
                                self.on_queue_completed(stats)
                            except Exception as e:
                                logger.error(f"Error en callback on_queue_completed: {e}")

                    self.active_file_name = "Ninguno"
                    self.active_item = None
                    self.current_download_info = {}
                    self.render_console_dashboard(stats)
                    await asyncio.sleep(5)
                    continue

                had_pending_work = True

                # Process tasks up to MAX_CONCURRENT_DOWNLOADS
                batch = pending_items[:self.config.max_concurrent_downloads]

                for item in batch:
                    if not self.is_running or self.is_paused:
                        break

                    # Check max retry limit (5 retries)
                    if item.retry_count >= 5:
                        err_msg = "Límite máximo de reintentos (5) alcanzado"
                        logger.error(f"El archivo {item.file_name} ha alcanzado el límite máximo de reintentos.")
                        self.repo.update_status(item.id, DownloadState.ERROR, last_error=err_msg)
                        if self.on_download_error:
                            self.on_download_error(item, err_msg, item.retry_count)
                        continue

                    # Fetch Telegram Message object
                    try:
                        messages = await self.client_mgr.client.get_messages(self.config.chat_id, ids=item.message_id)
                        if not messages or not messages.media:
                            err_msg = "Mensaje no encontrado o sin media descargable"
                            logger.error(f"Mensaje ID {item.message_id} ya no contiene media descargable.")
                            self.repo.update_status(item.id, DownloadState.ERROR, last_error=err_msg)
                            if self.on_download_error:
                                self.on_download_error(item, err_msg, item.retry_count)
                            continue

                        media_obj = messages.media
                    except FloodWaitError as e:
                        logger.warning(f"FloodWaitError: Esperando {e.seconds}s antes de reintentar...")
                        await asyncio.sleep(e.seconds)
                        continue
                    except (OSError, ConnectionError, TimeoutError, asyncio.TimeoutError) as e:
                        logger.warning(f"Error de red temporal al obtener mensaje ID {item.message_id}: {e}. Reintentando en 5s...")
                        await asyncio.sleep(5)
                        continue
                    except Exception as e:
                        logger.error(f"Error al obtener mensaje ID {item.message_id}: {e}")
                        self.repo.update_status(item.id, DownloadState.ERROR, last_error=str(e))
                        if self.on_download_error:
                            self.on_download_error(item, str(e), item.retry_count + 1)
                        continue

                    self.active_item = item
                    self.active_file_name = item.file_name

                    if self.on_download_start:
                        try:
                            self.on_download_start(item)
                        except Exception as e:
                            logger.error(f"Error en callback on_download_start: {e}")

                    async def refresh_media_for_item():
                        fresh_msgs = await self.client_mgr.client.get_messages(self.config.chat_id, ids=item.message_id)
                        if fresh_msgs and fresh_msgs.media:
                            return fresh_msgs.media
                        raise ValueError(f"Mensaje ID {item.message_id} ya no tiene media disponible.")

                    # Perform streaming download with resume
                    success = await self.downloader.download_item(
                        item=item,
                        media_object=media_obj,
                        progress_callback=self._on_progress,
                        refresh_media_callback=refresh_media_for_item
                    )

                    if success:
                        if self.on_download_complete:
                            try:
                                self.on_download_complete(item)
                            except Exception as e:
                                logger.error(f"Error en callback on_download_complete: {e}")
                    else:
                        updated_item = self.repo.get_item(item.id)
                        if updated_item and updated_item.status == DownloadState.ERROR:
                            if self.on_download_error:
                                try:
                                    self.on_download_error(updated_item, updated_item.last_error or "Error de descarga", updated_item.retry_count)
                                except Exception as e:
                                    logger.error(f"Error en callback on_download_error: {e}")

                    self.active_file_name = "Ninguno"
                    self.active_item = None
                    self.current_download_info = {}

                    if not success:
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
