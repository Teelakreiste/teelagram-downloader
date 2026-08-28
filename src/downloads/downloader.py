import os
import re
import time
import glob
import math
import asyncio
from typing import Callable, Optional, Dict, Any, List, Awaitable
from telethon import TelegramClient, utils, errors
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import GetFileRequest
from telethon.network import MTProtoSender

from src.core.models import DownloadItem, DownloadState
from src.database.repository import DownloadRepository
from src.utils.filesystem import format_bytes, format_time, check_disk_space
from src.utils.logger import logger

# Chunk size for MTProto downloads (512 KB)
CHUNK_SIZE = 512 * 1024
# Telegram MTProto offset alignment requirement (128 KB)
ALIGNMENT_SIZE = 128 * 1024


class ParallelFileTransferrer:
    """
    High-speed parallel MTProto downloader that establishes multiple concurrent
    connections to Telegram Data Centers to saturate available network bandwidth.
    """

    def __init__(
        self,
        client: TelegramClient,
        dc_id: int,
        connections: int = 4,
        on_refresh_media: Optional[Callable[[], Awaitable[Any]]] = None
    ):
        self.client = client
        self.dc_id = dc_id
        self.connections = max(1, connections)
        self.on_refresh_media = on_refresh_media
        self.senders: List[MTProtoSender] = []
        self.auth_key = (
            None if dc_id and self.client.session.dc_id != dc_id
            else self.client.session.auth_key
        )

    async def _create_sender(self, auth_key: Optional[Any] = None) -> MTProtoSender:
        """Creates and connects an individual MTProtoSender connection to the target DC."""
        dc = await self.client._get_dc(self.dc_id)
        sender = MTProtoSender(auth_key, loggers=self.client._log)
        await sender.connect(self.client._connection(
            dc.ip_address,
            dc.port,
            dc.id,
            loggers=self.client._log,
            proxy=self.client._proxy,
            local_addr=getattr(self.client, '_local_addr', None)
        ))

        if not auth_key:
            logger.debug(f"Exportando e importando autorización para DC {self.dc_id}...")
            auth = await self.client(ExportAuthorizationRequest(self.dc_id))
            self.client._init_request.query = ImportAuthorizationRequest(
                id=auth.id,
                bytes=auth.bytes
            )
            req = InvokeWithLayerRequest(LAYER, self.client._init_request)
            await sender.send(req)
            self.auth_key = sender.auth_key

        return sender

    async def init_senders(self, count: int) -> None:
        """Initializes the required number of parallel MTProto connections."""
        count = min(self.connections, count)
        if count <= 0:
            count = 1

        if self.auth_key:
            # Same DC or auth already available
            self.senders = await asyncio.gather(*[
                self._create_sender(self.auth_key) for _ in range(count)
            ])
        else:
            # Cross-DC: First sender obtains and imports auth key
            first_sender = await self._create_sender(None)
            other_senders = []
            if count > 1:
                other_senders = await asyncio.gather(*[
                    self._create_sender(self.auth_key) for _ in range(count - 1)
                ])
            self.senders = [first_sender] + list(other_senders)

        logger.info(f"Pool de {len(self.senders)} conexiones paralelas establecido con DC {self.dc_id}.")

    async def reconnect_sender(self, sender: MTProtoSender) -> bool:
        """Reconnects a disconnected sender to its target DC."""
        try:
            dc = await self.client._get_dc(self.dc_id)
            try:
                await sender.disconnect()
            except Exception:
                pass
            await sender.connect(self.client._connection(
                dc.ip_address,
                dc.port,
                dc.id,
                loggers=self.client._log,
                proxy=self.client._proxy,
                local_addr=getattr(self.client, '_local_addr', None)
            ))
            return True
        except Exception as e:
            logger.warning(f"Fallo al reconectar sender con DC {self.dc_id}: {e}")
            return False

    async def cleanup(self) -> None:
        """Gracefully closes all parallel sender connections."""
        if self.senders:
            await asyncio.gather(*[s.disconnect() for s in self.senders], return_exceptions=True)
            self.senders = []


class FileDownloader:
    """Handles streaming downloads with resume support, cancellation, progress calculation, and verification."""

    def __init__(
        self,
        client: TelegramClient,
        repo: DownloadRepository,
        download_dir: str,
        min_disk_space_gb: float = 5.0,
        parallel_connections: int = 4
    ):
        self.client = client
        self.repo = repo
        self.download_dir = download_dir
        self.min_disk_space_gb = min_disk_space_gb
        self.parallel_connections = max(1, parallel_connections)
        self.cancel_requested = False

    def request_cancel(self):
        """Signals active download to stop immediately."""
        self.cancel_requested = True

    def reset_cancel(self):
        self.cancel_requested = False

    async def download_item(
        self,
        item: DownloadItem,
        media_object: Any,
        progress_callback: Optional[Callable[[DownloadItem, Dict[str, Any]], None]] = None,
        refresh_media_callback: Optional[Callable[[], Awaitable[Any]]] = None
    ) -> bool:
        """
        Downloads a Telegram media item using high-speed parallel MTProto chunk streaming
        with resume capability, dynamic file reference renewal, and integrity checking.
        Returns True if complete, False if errored or cancelled.
        """
        self.reset_cancel()
        final_path = item.file_path
        part_path = f"{final_path}.part"

        # 1. Check if final file already exists and is fully downloaded
        if os.path.exists(final_path):
            existing_final_size = os.path.getsize(final_path)
            if existing_final_size == item.file_size:
                logger.info(f"El archivo {item.file_name} ya existe y está completo ({format_bytes(item.file_size)}). Omite descarga.")
                self.repo.update_status(item.id, DownloadState.COMPLETADO, downloaded_size=item.file_size)
                self.check_split_archive_group(final_path)
                return True

        # 2. Determine resume offset from .part file if it exists
        existing_part_size = 0
        if os.path.exists(part_path):
            existing_part_size = os.path.getsize(part_path)

        # Align offset to Telegram 128 KB boundary
        aligned_offset = (existing_part_size // ALIGNMENT_SIZE) * ALIGNMENT_SIZE
        remaining_bytes = item.file_size - aligned_offset

        # 3. Check disk space for remaining bytes
        has_space, free_bytes, disk_msg = check_disk_space(self.download_dir, remaining_bytes, self.min_disk_space_gb)
        if not has_space:
            logger.error(disk_msg)
            self.repo.update_status(item.id, DownloadState.ERROR, last_error=disk_msg)
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

        self.repo.update_status(item.id, DownloadState.DESCARGANDO, downloaded_size=aligned_offset)

        # 5. Extract DC ID and Input Location for MTProto transfers
        dc_id, input_location = utils.get_input_location(media_object)
        bytes_to_download = item.file_size - aligned_offset
        total_parts = math.ceil(bytes_to_download / CHUNK_SIZE) if bytes_to_download > 0 else 0

        if total_parts == 0:
            f.close()
            os.replace(part_path, final_path)
            self.repo.update_status(item.id, DownloadState.COMPLETADO, downloaded_size=item.file_size)
            return True

        # Calculate optimal number of parallel workers for this file
        conns_to_use = min(self.parallel_connections, total_parts)
        transferrer = ParallelFileTransferrer(
            client=self.client,
            dc_id=dc_id,
            connections=conns_to_use,
            on_refresh_media=refresh_media_callback
        )

        try:
            await transferrer.init_senders(conns_to_use)
        except Exception as e:
            logger.warning(f"No se pudo inicializar pool paralelo ({e}). Usando modo secuencial de respaldo...")
            transferrer = None

        if transferrer and transferrer.senders:
            success = await self._download_parallel(
                transferrer=transferrer,
                item=item,
                file_handle=f,
                aligned_offset=aligned_offset,
                total_parts=total_parts,
                initial_location=input_location,
                progress_callback=progress_callback,
                refresh_media_callback=refresh_media_callback
            )
            await transferrer.cleanup()
        else:
            # Fallback to standard sequential iter_download
            success = await self._download_sequential(
                item=item,
                media_object=media_object,
                file_handle=f,
                aligned_offset=aligned_offset,
                progress_callback=progress_callback
            )

        f.close()

        if self.cancel_requested:
            logger.info(f"Descarga cancelada a petición del usuario: {item.file_name}. Archivo .part conservado.")
            current_size = os.path.getsize(part_path) if os.path.exists(part_path) else aligned_offset
            self.repo.update_status(item.id, DownloadState.CANCELADO, downloaded_size=current_size, last_error="Cancelado por el usuario")
            return False

        if not success:
            return False

        # 6. Integrity verification
        actual_size = os.path.getsize(part_path)
        if actual_size != item.file_size:
            err_msg = f"Verificación fallida: Tamaño descargado ({actual_size} B) != Esperado ({item.file_size} B)"
            logger.error(err_msg)
            self.repo.update_status(item.id, DownloadState.ERROR, downloaded_size=actual_size, last_error=err_msg)
            return False

        # 7. Rename .part to final target file
        os.replace(part_path, final_path)
        self.repo.update_status(item.id, DownloadState.COMPLETADO, downloaded_size=item.file_size)
        logger.info(f"Descarga completada con éxito: {item.file_name} ({format_bytes(item.file_size)})")

        # 8. Check for completed split archive set
        self.check_split_archive_group(final_path)
        return True

    async def _download_parallel(
        self,
        transferrer: ParallelFileTransferrer,
        item: DownloadItem,
        file_handle: Any,
        aligned_offset: int,
        total_parts: int,
        initial_location: Any,
        progress_callback: Optional[Callable[[DownloadItem, Dict[str, Any]], None]],
        refresh_media_callback: Optional[Callable[[], Awaitable[Any]]]
    ) -> bool:
        """Executes parallel chunk pipeline across multiple MTProto connections."""
        part_queue: asyncio.Queue[int] = asyncio.Queue()
        for idx in range(total_parts):
            part_queue.put_nowait(idx)

        buffer_cond = asyncio.Condition()
        downloaded_chunks: Dict[int, bytes] = {}
        cancel_event = asyncio.Event()
        error_event = asyncio.Event()
        error_holder: List[str] = []

        location_lock = asyncio.Lock()
        current_location = [initial_location]

        async def worker_loop(sender_idx: int, sender: MTProtoSender):
            while not cancel_event.is_set() and not error_event.is_set():
                if self.cancel_requested:
                    cancel_event.set()
                    break

                try:
                    part_idx = part_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                part_offset = aligned_offset + part_idx * CHUNK_SIZE
                part_limit = min(CHUNK_SIZE, item.file_size - part_offset)

                max_retries = 10
                success = False

                for attempt in range(max_retries):
                    if cancel_event.is_set() or error_event.is_set() or self.cancel_requested:
                        break

                    try:
                        if not sender.is_connected():
                            logger.info(f"Reconectando sender #{sender_idx} con DC {transferrer.dc_id}...")
                            await transferrer.reconnect_sender(sender)

                        req = GetFileRequest(
                            location=current_location[0],
                            offset=part_offset,
                            limit=CHUNK_SIZE
                        )
                        result = await self.client._call(sender, req)
                        chunk_bytes = result.bytes[:part_limit]

                        async with buffer_cond:
                            downloaded_chunks[part_idx] = chunk_bytes
                            buffer_cond.notify_all()

                        part_queue.task_done()
                        success = True
                        break

                    except errors.FileReferenceExpiredError:
                        logger.warning(f"FileReferenceExpiredError en chunk {part_idx}. Refrescando referencia de archivo...")
                        if refresh_media_callback:
                            try:
                                async with location_lock:
                                    fresh_media = await refresh_media_callback()
                                    _, current_location[0] = utils.get_input_location(fresh_media)
                                logger.info("Referencia de archivo de Telegram renovada con éxito. Reintentando...")
                                continue
                            except Exception as re:
                                logger.error(f"Fallo al renovar referencia de archivo: {re}")
                                error_holder.append(str(re))
                                error_event.set()
                                break
                        else:
                            error_holder.append("File reference expired and no refresh callback provided.")
                            error_event.set()
                            break

                    except errors.FloodWaitError as fwe:
                        logger.warning(f"FloodWait de {fwe.seconds}s en worker {sender_idx}. Pausando...")
                        await asyncio.sleep(fwe.seconds)

                    except Exception as ex:
                        logger.warning(f"Error temporal en chunk {part_idx} (intento {attempt + 1}/{max_retries}): {ex}")
                        try:
                            await sender.disconnect()
                        except Exception:
                            pass
                        wait_time = min(20.0, 2.0 ** min(attempt, 4))
                        await asyncio.sleep(wait_time)

                if not success and not cancel_event.is_set():
                    if not error_event.is_set():
                        err_msg = f"Fallo al descargar bloque {part_idx} tras {max_retries} intentos"
                        error_holder.append(err_msg)
                        error_event.set()
                    break

        async def writer_loop():
            next_part = 0
            downloaded_bytes = aligned_offset
            start_time = time.time()
            last_db_update = time.time()
            last_progress_call = time.time()

            while next_part < total_parts and not cancel_event.is_set() and not error_event.is_set():
                if self.cancel_requested:
                    cancel_event.set()
                    break

                async with buffer_cond:
                    while next_part not in downloaded_chunks and not cancel_event.is_set() and not error_event.is_set():
                        try:
                            await asyncio.wait_for(buffer_cond.wait(), timeout=1.0)
                        except asyncio.TimeoutError:
                            if self.cancel_requested:
                                cancel_event.set()
                                break

                    if cancel_event.is_set() or error_event.is_set():
                        break

                    chunk_data = downloaded_chunks.pop(next_part)

                file_handle.write(chunk_data)
                downloaded_bytes += len(chunk_data)
                next_part += 1

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
                    self.repo.update_progress(item.id, downloaded_bytes)
                    last_db_update = now

                # Trigger UI callback every 0.5 seconds
                if progress_callback and (now - last_progress_call >= 0.5):
                    progress_callback(item, progress_data)
                    last_progress_call = now

            file_handle.flush()
            return next_part == total_parts

        # Launch workers and writer coroutines
        worker_tasks = [
            asyncio.create_task(worker_loop(i, sender))
            for i, sender in enumerate(transferrer.senders)
        ]
        writer_task = asyncio.create_task(writer_loop())

        await asyncio.gather(*worker_tasks, writer_task, return_exceptions=True)

        if self.cancel_requested:
            return False

        if error_event.is_set():
            err_msg = error_holder[0] if error_holder else "Error desconocido durante la descarga paralela"
            logger.error(err_msg)
            self.repo.update_status(item.id, DownloadState.ERROR, last_error=err_msg)
            return False

        return writer_task.result() if writer_task.done() and not writer_task.exception() else False

    async def _download_sequential(
        self,
        item: DownloadItem,
        media_object: Any,
        file_handle: Any,
        aligned_offset: int,
        progress_callback: Optional[Callable[[DownloadItem, Dict[str, Any]], None]]
    ) -> bool:
        """Fallback sequential chunk downloader using Telethon iter_download."""
        downloaded_bytes = aligned_offset
        start_time = time.time()
        last_db_update = time.time()
        last_progress_call = time.time()

        try:
            async for chunk in self.client.iter_download(
                media_object,
                offset=aligned_offset,
                request_size=CHUNK_SIZE
            ):
                if self.cancel_requested:
                    return False

                file_handle.write(chunk)
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

                if now - last_db_update >= 3.0:
                    self.repo.update_progress(item.id, downloaded_bytes)
                    last_db_update = now

                if progress_callback and (now - last_progress_call >= 0.5):
                    progress_callback(item, progress_data)
                    last_progress_call = now

            file_handle.flush()
            return True

        except Exception as e:
            err_msg = f"Error en descarga secuencial de {item.file_name}: {e}"
            logger.error(err_msg)
            self.repo.update_status(item.id, DownloadState.ERROR, downloaded_size=downloaded_bytes, last_error=str(e))
            return False

    def check_split_archive_group(self, file_path: str):
        """
        Checks if the downloaded file is part of a split archive set
        (e.g., .part01.rar or .7z.001) and logs when all parts are complete.
        """
        filename = os.path.basename(file_path)
        dir_name = os.path.dirname(file_path)

        match_part = re.search(r"^(.*?)\.part(\d+)\.rar$", filename, re.IGNORECASE)
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

        if ext_type == "part_rar":
            pattern = os.path.join(dir_name, f"{glob.escape(base_name)}.part*.rar")
            files = glob.glob(pattern)
        else:
            pattern = os.path.join(dir_name, f"{glob.escape(base_name)}.*.[0-9]*")
            files = glob.glob(pattern)

        files = [f for f in files if not f.endswith(".part")]
        
        if len(files) > 1:
            part_basenames = [os.path.basename(f) for f in sorted(files)]
            logger.info(f"[CONJUNTO COMPLETO DETECTADO] Todos los archivos del conjunto están presentes ({len(files)} partes):\n" + "\n".join(f"  - {name}" for name in part_basenames))

