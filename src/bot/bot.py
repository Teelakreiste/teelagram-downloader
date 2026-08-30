import asyncio
from typing import Optional
from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from src.config.settings import Config
from src.services.scan_service import ScanService
from src.services.download_service import DownloadService
from src.services.status_service import StatusService
from src.bot.handlers import BotHandlers
from src.bot.notifications import BotNotifier
from src.utils.logger import logger

class AdminBotManager:
    """Manages Telegram Bot API lifecycle, handler wiring, command menu setup, and asynchronous polling background task."""

    def __init__(
        self,
        config: Config,
        scan_service: ScanService,
        download_service: DownloadService,
        status_service: StatusService,
        notifier: BotNotifier
    ):
        self.config = config
        self.scan_service = scan_service
        self.download_service = download_service
        self.status_service = status_service
        self.notifier = notifier
        self.app: Optional[Application] = None
        self.handlers = BotHandlers(config, scan_service, download_service, status_service)

    async def _setup_bot_commands(self):
        """Registers command menu in Telegram UI so users see command autocomplete suggestions."""
        if not self.app or not self.app.bot:
            return

        commands = [
            BotCommand("start", "Panel principal de administración"),
            BotCommand("status", "Estado del sistema y descarga activa"),
            BotCommand("scan", "Escanear chat configurado"),
            BotCommand("files", "Explorador de archivos registrados"),
            BotCommand("queue", "Ver cola de descargas pendientes"),
            BotCommand("downloads", "Detalles de descarga en progreso"),
            BotCommand("start_downloads", "Iniciar/reanudar descargas en cola"),
            BotCommand("stop_downloads", "Pausar la cola de descargas"),
            BotCommand("cancel", "Cancelar la descarga activa actual"),
            BotCommand("retry", "Reintentar errores: /retry o /retry <ID>"),
            BotCommand("priority", "Priorizar archivo: /priority <ID>"),
            BotCommand("guide", "Guía de uso interactiva"),
            BotCommand("help", "Lista de comandos y ayuda rápida")
        ]

        try:
            await self.app.bot.set_my_commands(commands)
            logger.info("[BOT API] Menú de comandos registrado con éxito en Telegram UI.")
        except Exception as e:
            logger.warning(f"[BOT API] No se pudo registrar el menú de comandos en Telegram UI: {e}")

    async def initialize(self) -> bool:
        """Initializes python-telegram-bot application."""
        if not self.config.bot_token:
            logger.info("[BOT API] BOT_TOKEN no configurado en .env. El bot de administración no se iniciará.")
            return False

        try:
            self.app = ApplicationBuilder().token(self.config.bot_token).build()
            self.notifier.set_bot(self.app.bot)

            # Register Command Handlers
            self.app.add_handler(CommandHandler("start", self.handlers.cmd_start))
            self.app.add_handler(CommandHandler("help", self.handlers.cmd_help))
            self.app.add_handler(CommandHandler("guide", self.handlers.cmd_guide))
            self.app.add_handler(CommandHandler("status", self.handlers.cmd_status))
            self.app.add_handler(CommandHandler("scan", self.handlers.cmd_scan))
            self.app.add_handler(CommandHandler("files", self.handlers.cmd_files))
            self.app.add_handler(CommandHandler("queue", self.handlers.cmd_queue))
            self.app.add_handler(CommandHandler("downloads", self.handlers.cmd_downloads))
            self.app.add_handler(CommandHandler("start_downloads", self.handlers.cmd_start_downloads))
            self.app.add_handler(CommandHandler("stop_downloads", self.handlers.cmd_stop_downloads))
            self.app.add_handler(CommandHandler("cancel", self.handlers.cmd_cancel))
            self.app.add_handler(CommandHandler("retry", self.handlers.cmd_retry))
            self.app.add_handler(CommandHandler("priority", self.handlers.cmd_priority))


            # Register Callback Query Handler
            self.app.add_handler(CallbackQueryHandler(self.handlers.handle_callback_query))

            # Register Global Error Handler for transient network drops
            async def bot_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
                err_str = str(context.error) if context.error else ""
                if "getaddrinfo failed" in err_str or "ConnectError" in err_str or "NetworkError" in err_str:
                    logger.warning(f"[BOT API] Desconexión temporal de red detectada en polling: {err_str[:120]}")
                else:
                    logger.warning(f"[BOT API] Error no crítico en Bot API: {err_str[:120]}")

            self.app.add_error_handler(bot_error_handler)

            await self.app.initialize()
            await self._setup_bot_commands()
            logger.info("[BOT API] Bot de administración inicializado con éxito.")
            return True
        except Exception as e:
            logger.error(f"[BOT API] Error inicializando el Bot de administración: {e}")
            return False

    async def start(self):
        """Starts bot polling as an async background task."""
        if self.app:
            await self.app.start()
            await self.app.updater.start_polling(drop_pending_updates=True)
            logger.info("[BOT API] Bot de administración escuchando comandos remotamente...")

    async def stop(self):
        """Stops bot polling and closes connection."""
        if self.app:
            try:
                if self.app.updater and self.app.updater.running:
                    await self.app.updater.stop()
                await self.app.stop()
                await self.app.shutdown()
                logger.info("[BOT API] Bot de administración detenido correctamente.")
            except Exception as e:
                logger.error(f"[BOT API] Error al detener el Bot de administración: {e}")
