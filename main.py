import os
import sys
import argparse
import asyncio

from src.config.settings import get_config
from src.database.database import Database
from src.core.models import DownloadState
from src.telegram.client import TelegramClientManager
from src.downloads.downloader import FileDownloader, format_bytes, format_time
from src.downloads.queue_manager import QueueManager
from src.utils.logger import logger

def print_banner():
    print("========================================")
    print(" TELEGRAM FILE DOWNLOADER (MTProto)")
    print("========================================\n")

async def cmd_auth(config, db):
    """Executes initial authentication flow."""
    print_banner()
    print("Iniciando autenticación interactiva con Telegram...")
    client_mgr = TelegramClientManager(config)
    await client_mgr.ensure_authenticated()
    await client_mgr.client.disconnect()
    print("\n[ÉXITO] Autenticación completada. Sesión guardada correctamente en el directorio de datos.")

async def cmd_list_chats(config, db):
    """Lists user dialogs to help locate CHAT_ID."""
    print_banner()
    client_mgr = TelegramClientManager(config)
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

async def cmd_scan(config, db):
    """Scans history of configured CHAT_ID and registers downloadable media into DB queue."""
    print_banner()
    if not config.chat_id:
        print("[ERROR] CHAT_ID no está configurado en el archivo .env.")
        sys.exit(1)

    client_mgr = TelegramClientManager(config)
    await client_mgr.start()
    await client_mgr.ensure_authenticated()

    total, new_items = await client_mgr.scan_chat(config.chat_id, db, config.download_dir)
    await client_mgr.client.disconnect()

    print(f"\n[ESCANEO FINALIZADO]")
    print(f"  Archivos multimedia detectados en chat: {total}")
    print(f"  Nuevos archivos agregados a la cola:     {new_items}")
    print(f"  Ejecute 'python main.py start' para iniciar las descargas.\n")

async def cmd_start(config, db):
    """Starts live listener and background queue downloader."""
    print_banner()
    if not config.chat_id:
        print("[ERROR] CHAT_ID no está configurado en el archivo .env.")
        sys.exit(1)

    client_mgr = TelegramClientManager(config)
    await client_mgr.start()
    await client_mgr.ensure_authenticated()

    downloader = FileDownloader(
        client=client_mgr.client,
        db=db,
        download_dir=config.download_dir,
        min_disk_space_gb=config.min_disk_space_gb
    )

    queue_mgr = QueueManager(config, db, client_mgr, downloader)

    # Listen for new incoming files in configured chat
    client_mgr.setup_new_message_listener(
        chat_id=config.chat_id,
        db=db,
        download_dir=config.download_dir
    )

    print("Servicio de descargas iniciado. Presione Ctrl+C para salir.")
    
    try:
        await queue_mgr.process_queue_loop()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Deteniendo el servicio por solicitud del usuario...")
    finally:
        queue_mgr.stop()
        await client_mgr.client.disconnect()
        print("\nServicio detenido de forma segura.")

def cmd_status(config, db):
    """Queries DB and prints download statistics and active downloads."""
    print_banner()
    stats = db.get_summary_stats()
    items = db.get_all_items()

    print("Estadísticas Generales:")
    print(f"  Total Registrados: {stats['TOTAL']}")
    print(f"  Pendientes:        {stats['PENDIENTE']}")
    print(f"  Descargando:       {stats['DESCARGANDO']}")
    print(f"  Completados:       {stats['COMPLETADO']}")
    print(f"  Errores:           {stats['ERROR']}")
    print(f"  Cancelados:        {stats['CANCELADO']}")
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
        description="Telegram Large File Downloader (MTProto / Telethon)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    subparsers.add_parser("auth", help="Inicia sesión interactiva con Telegram y guarda la sesión localmente.")
    subparsers.add_parser("list-chats", help="Lista los chats recientes para identificar el CHAT_ID.")
    subparsers.add_parser("scan", help="Escanea el chat configurado para buscar y registrar archivos en la cola.")
    subparsers.add_parser("start", help="Inicia el servicio de escuchador en tiempo real y la cola de descargas.")
    subparsers.add_parser("status", help="Muestra el estado general de las descargas en la base de datos.")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    config = get_config()
    db_path = os.path.join(config.data_dir, "downloads.db")
    db = Database(db_path)

    if args.command == "auth":
        asyncio.run(cmd_auth(config, db))
    elif args.command == "list-chats":
        asyncio.run(cmd_list_chats(config, db))
    elif args.command == "scan":
        asyncio.run(cmd_scan(config, db))
    elif args.command == "start":
        asyncio.run(cmd_start(config, db))
    elif args.command == "status":
        cmd_status(config, db)

if __name__ == "__main__":
    main()
