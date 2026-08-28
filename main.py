import os
import sys
import argparse
import asyncio

from src.config.settings import get_config
from src.database.database import Database
from src.database.repository import DownloadRepository
from src.core.models import DownloadState
from src.telegram.client import TelegramClientManager
from src.downloads.downloader import FileDownloader
from src.downloads.queue_manager import QueueManager
from src.services.scan_service import ScanService
from src.services.download_service import DownloadService
from src.services.status_service import StatusService
from src.bot.bot import AdminBotManager
from src.bot.notifications import BotNotifier
from src.utils.filesystem import format_bytes, format_time
from src.utils.logger import logger

def print_banner():
    print("========================================")
    print(" TELEGRAM FILE DOWNLOADER (MTProto)")
    print("========================================\n")

async def cmd_auth(config, repo):
    """Executes initial authentication flow."""
    print_banner()
    print("Iniciando autenticación interactiva con Telegram...")
    client_mgr = TelegramClientManager(config, repo)
    await client_mgr.ensure_authenticated()
    await client_mgr.client.disconnect()
    print("\n[ÉXITO] Autenticación completada. Sesión guardada correctamente en el directorio de datos.")

async def cmd_list_chats(config, repo):
    """Lists user dialogs to help locate CHAT_ID."""
    print_banner()
    client_mgr = TelegramClientManager(config, repo)
    await client_mgr.start()
    await client_mgr.ensure_authenticated()

    print("Obteniendo diálogos y chats de la cuenta...\n")
    dialogs = await client_mgr.list_dialogs()
    await client_mgr.client.disconnect()

    print(f"{'TYPE':<12} | {'CHAT_ID':<20} | {'NAME':<35}")
    print("-" * 72)
    for d in dialogs:
        print(f"{d['type']:<12} | {d['id']:<20} | {d['name'][:35]:<35}")
    print("\nCopie el CHAT_ID deseado y configúrelo en su archivo .env como CHAT_ID=-100...")

async def cmd_scan(config, repo, client_mgr=None):
    """Scans history of configured CHAT_ID and registers downloadable media into DB queue."""
    print_banner()
    if not config.chat_id:
        print("[ERROR] CHAT_ID no está configurado en el archivo .env.")
        sys.exit(1)

    close_client = False
    if not client_mgr:
        client_mgr = TelegramClientManager(config, repo)
        close_client = True

    scan_service = ScanService(config, repo, client_mgr)
    total, new_items = await scan_service.scan_chat()

    if close_client:
        await client_mgr.client.disconnect()

    print(f"\n[ESCANEO FINALIZADO]")
    print(f"  Archivos multimedia detectados en chat: {total}")
    print(f"  Nuevos archivos agregados a la cola:     {new_items}")
    print(f"  Ejecute 'python main.py start' para iniciar las descargas.\n")

async def cmd_start(config, repo):
    """Starts Telethon listener, background queue downloader, and Admin Telegram Bot."""
    print_banner()
    if not config.chat_id:
        print("[ERROR] CHAT_ID no está configurado en el archivo .env.")
        sys.exit(1)

    client_mgr = TelegramClientManager(config, repo)
    await client_mgr.start()
    await client_mgr.ensure_authenticated()

    downloader = FileDownloader(
        client=client_mgr.client,
        repo=repo,
        download_dir=config.download_dir,
        min_disk_space_gb=config.min_disk_space_gb,
        parallel_connections=config.parallel_connections
    )

    queue_mgr = QueueManager(config, repo, client_mgr, downloader)
    notifier = BotNotifier(config)

    # Wire QueueManager callbacks to BotNotifier
    def on_dl_start(item):
        asyncio.create_task(notifier.notify_download_start(item))

    def on_dl_complete(item):
        asyncio.create_task(notifier.notify_download_complete(item))

    def on_dl_error(item, err_msg, retries):
        asyncio.create_task(notifier.notify_download_error(item, err_msg, retries))

    def on_queue_done(stats):
        asyncio.create_task(notifier.notify_queue_completed(stats))

    def on_prog_update(item, progress):
        asyncio.create_task(notifier.update_progress_notification(item, progress))

    queue_mgr.on_download_start = on_dl_start
    queue_mgr.on_download_complete = on_dl_complete
    queue_mgr.on_download_error = on_dl_error
    queue_mgr.on_queue_completed = on_queue_done
    queue_mgr.on_progress_update = on_prog_update

    # Wire Telethon live new message listener
    def on_new_item_detected(item):
        if not config.auto_download:
            # Mark auto-detected item as PENDIENTE without auto queueing
            logger.info(f"AUTO_DOWNLOAD=false. Archivo {item.file_name} requiere aprobación.")
        else:
            logger.info(f"AUTO_DOWNLOAD=true. Archivo {item.file_name} agregado automáticamente a la cola.")
        asyncio.create_task(notifier.notify_new_file(item))

    client_mgr.setup_new_message_listener(
        chat_id=config.chat_id,
        repo=repo,
        download_dir=config.download_dir,
        on_new_item_callback=on_new_item_detected
    )

    # Initialize Services
    scan_service = ScanService(config, repo, client_mgr)
    download_service = DownloadService(config, repo, queue_mgr)
    status_service = StatusService(config, repo, client_mgr, queue_mgr)

    # Initialize and start Bot Manager
    bot_mgr = AdminBotManager(config, scan_service, download_service, status_service, notifier)
    bot_started = await bot_mgr.initialize()
    if bot_started:
        await bot_mgr.start()

    print("Servicio de descargas iniciado. Presione Ctrl+C para salir.")

    try:
        await queue_mgr.process_queue_loop()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Deteniendo el servicio por solicitud del usuario...")
    finally:
        queue_mgr.stop()
        if bot_started:
            await bot_mgr.stop()
        await client_mgr.client.disconnect()
        print("\nServicio detenido de forma segura.")

def cmd_status(config, repo):
    """Queries DB and prints download statistics and active downloads."""
    print_banner()
    stats = repo.get_summary_stats()
    items = repo.get_all_items()

    print("Estadísticas Generales:")
    print(f"  Total Registrados: {stats.get('TOTAL', 0)}")
    print(f"  Pendientes:        {stats.get('PENDIENTE', 0)}")
    print(f"  Descargando:       {stats.get('DESCARGANDO', 0)}")
    print(f"  Completados:       {stats.get('COMPLETADO', 0)}")
    print(f"  Errores:           {stats.get('ERROR', 0)}")
    print(f"  Cancelados:        {stats.get('CANCELADO', 0)}")
    print("\nÚltimos 15 Registros:")
    print(f"{'ID':<5} | {'ESTADO':<11} | {'PROGRESO':<18} | {'ARCHIVO':<35}")
    print("-" * 76)

    for item in items[:15]:
        pct = (item.downloaded_size / item.file_size * 100) if item.file_size > 0 else 0.0
        prog_str = f"{format_bytes(item.downloaded_size)} / {format_bytes(item.file_size)} ({pct:.1f}%)"
        print(f"{item.id:<5} | {item.status.value:<11} | {prog_str:<18} | {item.file_name[:35]:<35}")
    print()

def main():
    parser = argparse.ArgumentParser(
        description="Telegram Large File Downloader (MTProto / Telethon) con Bot de Administración",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    subparsers.add_parser("auth", help="Inicia sesión interactiva con Telegram y guarda la sesión localmente.")
    subparsers.add_parser("list-chats", help="Lista los chats recientes para identificar el CHAT_ID.")
    subparsers.add_parser("scan", help="Escanea el chat configurado para buscar y registrar archivos en la cola.")
    subparsers.add_parser("start", help="Inicia el servicio de escuchador en tiempo real, la cola de descargas y el Bot de Administración.")
    subparsers.add_parser("status", help="Muestra el estado general de las descargas en la base de datos.")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    config = get_config()
    db_path = os.path.join(config.data_dir, "downloads.db")
    db = Database(db_path)
    repo = DownloadRepository(db)

    if args.command == "auth":
        asyncio.run(cmd_auth(config, repo))
    elif args.command == "list-chats":
        asyncio.run(cmd_list_chats(config, repo))
    elif args.command == "scan":
        asyncio.run(cmd_scan(config, repo))
    elif args.command == "start":
        asyncio.run(cmd_start(config, repo))
    elif args.command == "status":
        cmd_status(config, repo)

if __name__ == "__main__":
    main()
