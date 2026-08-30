from telegram import Update
from telegram.ext import ContextTypes
from src.config.settings import Config
from src.services.scan_service import ScanService
from src.services.download_service import DownloadService
from src.services.status_service import StatusService
from src.bot.keyboards import (
    get_start_keyboard,
    get_files_keyboard,
    get_guide_keyboard,
    get_cancel_confirm_keyboard,
    get_stop_now_keyboard,
    get_retry_all_keyboard,
    get_retry_item_keyboard,
    get_priority_keyboard
)
from src.bot.notifications import render_progress_bar
from src.utils.filesystem import format_bytes, format_time
from src.utils.logger import logger

def is_authorized(user_id: int, admin_ids: list[int]) -> bool:
    """Checks if telegram user ID is authorized."""
    if not admin_ids:
        return True
    return user_id in admin_ids

class BotHandlers:
    """Encapsulates command handlers and callback query handlers for the Admin Bot using rich HTML formatting."""

    def __init__(
        self,
        config: Config,
        scan_service: ScanService,
        download_service: DownloadService,
        status_service: StatusService
    ):
        self.config = config
        self.scan_service = scan_service
        self.download_service = download_service
        self.status_service = status_service

    async def _check_auth(self, update: Update) -> bool:
        user_id = update.effective_user.id if update.effective_user else 0
        if not is_authorized(user_id, self.config.admin_user_ids):
            msg = "⛔ <b>Acceso denegado:</b> No tienes autorización para utilizar este bot."
            if update.message:
                await update.message.reply_text(msg, parse_mode="HTML")
            elif update.callback_query:
                await update.callback_query.answer("No tienes autorización para utilizar este bot.", show_alert=True)
            return False
        return True

    # 1. /start
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        sys_status = self.status_service.get_system_status()
        stats = self.status_service.get_summary_stats()

        telethon_str = "🟢 <b>Conectado</b>" if sys_status["telethon_connected"] else "🔴 <b>Desconectado</b>"
        monitor_str = "🟢 <b>Activo</b>" if sys_status["monitor_active"] else "🔴 <b>Inactivo</b>"
        dl_str = "🟢 <b>Activas</b>" if sys_status["queue_active"] else "⏸ <b>Detenidas</b>"

        text = (
            f"<b>🤖 TELEGRAM DOWNLOADER — PANEL DE CONTROL</b>\n"
            f"──────────────────────────\n\n"
            f"⚡ <b>Estado del Sistema:</b> 🟢 <code>Activo</code>\n\n"
            f"📡 <b>Telethon MTProto:</b> {telethon_str}\n"
            f"👁️ <b>Monitor de Chat:</b> {monitor_str}\n"
            f"⬇️ <b>Cola de Descargas:</b> {dl_str}\n\n"
            f"📊 <b>Resumen de Archivos:</b>\n"
            f"  • 🔍 <b>Detectados:</b> <code>{stats.get('TOTAL', 0)}</code>\n"
            f"  • ✅ <b>Completados:</b> <code>{stats.get('COMPLETADO', 0)}</code>\n"
            f"  • ⏳ <b>Pendientes:</b> <code>{stats.get('PENDIENTE', 0)}</code>\n"
            f"  • ⬇️ <b>Descargando:</b> <code>{stats.get('DESCARGANDO', 0)}</code>\n"
            f"  • ❌ <b>Errores:</b> <code>{stats.get('ERROR', 0)}</code>"
        )

        keyboard = get_start_keyboard()
        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    # 2. /help
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        text = (
            f"<b>❓ AYUDA RÁPIDA DE COMANDOS</b>\n"
            f"──────────────────────────\n\n"
            f"<b>Comandos Disponibles:</b>\n"
            f"• /start — Panel principal e indicadores\n"
            f"• /status — Estado detallado y descarga activa\n"
            f"• /scan — Escanear historial del chat\n"
            f"• /files — Lista paginada con filtros\n"
            f"• /queue — Lista de archivos pendientes\n"
            f"• /downloads — Detalle de descarga actual\n"
            f"• /start_downloads — Iniciar/reanudar la cola\n"
            f"• /stop_downloads — Pausar la cola\n"
            f"• /cancel — Cancelar descarga activa\n"
            f"• /retry — Reintentar todos los archivos con error\n"
            f"• /retry &lt;ID&gt; — Reintentar un archivo específico por ID\n"
            f"• /priority &lt;ID&gt; — Priorizar un archivo (subirlo al tope)\n"
            f"• /priority &lt;ID&gt; 0 — Quitar prioridad de un archivo\n"
            f"• /guide — Guía de uso completa interactiva\n"
            f"• /help — Mostrar este menú de ayuda"
        )
        keyboard = get_guide_keyboard("cmds")
        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


    # 3. /guide (Interactive User Guide)
    async def cmd_guide(self, update: Update, context: ContextTypes.DEFAULT_TYPE, tab: str = "quick"):
        if not await self._check_auth(update):
            return

        if tab == "quick":
            text = (
                f"<b>🚀 GUÍA DE USO — INICIO RÁPIDO</b>\n"
                f"──────────────────────────\n\n"
                f"1️⃣ <b>Escanear Chat:</b>\n"
                f"   Ejecuta <code>/scan</code> para detectar archivos pasados en tu chat configurado.\n\n"
                f"2️⃣ <b>Detección en Vivo:</b>\n"
                f"   Cuando se envíe un nuevo archivo al chat, el bot te notificará automáticamente con botones para <b>[ Descargar ]</b> o <b>[ Ignorar ]</b>.\n\n"
                f"3️⃣ <b>Iniciar Descargas:</b>\n"
                f"   Presiona <b>▶️ Iniciar descargas</b> o envía <code>/start_downloads</code>.\n\n"
                f"4️⃣ <b>Monitoreo:</b>\n"
                f"   Consulta el avance en tiempo real con <code>/status</code> o <code>/downloads</code>."
            )
        elif tab == "dl":
            text = (
                f"<b>📥 GUÍA DE DESCARGAS & ARCHIVOS .PART</b>\n"
                f"──────────────────────────\n\n"
                f"• <b>Archivos Grandes (4 GB+):</b>\n"
                f"  Las descargas las realiza Telethon vía MTProto nativo en bloques streaming de 512 KB.\n\n"
                f"• <b>Reanudación (.part):</b>\n"
                f"  Durante la descarga el archivo se llama <code>archivo.part</code>. Si el proceso se interrumpe o cancela, <b>el progreso se conserva</b>.\n\n"
                f"• <b>Control de Disco:</b>\n"
                f"  Se verifica automáticamente si tienes suficiente espacio disponible antes de iniciar la descarga."
            )
        elif tab == "cmds":
            text = (
                f"<b>🤖 LISTA DE COMANDOS DEL BOT</b>\n"
                f"──────────────────────────\n\n"
                f"<code>/start</code> — Panel principal de administración\n"
                f"<code>/status</code> — Estado del sistema y descarga activa\n"
                f"<code>/scan</code> — Escanear chat configurado\n"
                f"<code>/files</code> — Ver archivos con paginación y filtros\n"
                f"<code>/queue</code> — Cola de pendientes\n"
                f"<code>/downloads</code> — Descarga actual en progreso\n"
                f"<code>/start_downloads</code> — Iniciar/reanudar descargas\n"
                f"<code>/stop_downloads</code> — Pausar la cola de descargas\n"
                f"<code>/cancel</code> — Cancelar descarga activa\n"
                f"<code>/retry</code> — Reintentar todos los errores\n"
                f"<code>/retry &lt;ID&gt;</code> — Reintentar archivo específico\n"
                f"<code>/priority &lt;ID&gt;</code> — Priorizar archivo (tope de cola)\n"
                f"<code>/priority &lt;ID&gt; 0</code> — Quitar prioridad\n"
                f"<code>/guide</code> — Esta guía de uso interactiva"
            )

        else: # config
            text = (
                f"<b>⚙️ GUÍA DE CONFIGURACIÓN (.ENV)</b>\n"
                f"──────────────────────────\n\n"
                f"• <code>ADMIN_USER_IDS</code>: IDs numéricos de Telegram con permiso para utilizar este bot.\n"
                f"• <code>AUTO_DOWNLOAD</code>:\n"
                f"  - <code>false</code>: Requiere confirmación manual.\n"
                f"  - <code>true</code>: Encola automáticamente todo archivo detectado.\n"
                f"• <code>BOT_PROGRESS_UPDATE_INTERVAL</code>: Intervalo en segundos de actualización del progreso (default: 10s)."
            )

        keyboard = get_guide_keyboard(tab)
        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    # 4. /status
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        sys_status = self.status_service.get_system_status()
        stats = self.status_service.get_summary_stats()
        active_info = self.status_service.get_active_download_info()

        dl_status_str = "🟢 <b>Activas</b>" if sys_status["queue_active"] else "⏸ <b>Detenidas</b>"
        telethon_str = "🟢 <b>Conectado</b>" if sys_status["telethon_connected"] else "🔴 <b>Desconectado</b>"

        text = (
            f"<b>📊 ESTADO DEL SYSTEMA DOWNLOADER</b>\n"
            f"──────────────────────────\n\n"
            f"📡 <b>Telethon:</b> {telethon_str}\n"
            f"👁️ <b>Monitor:</b> 🟢 <b>Escuchando</b>\n"
            f"⬇️ <b>Descargas:</b> {dl_status_str}\n\n"
            f"<b>Métricas DB:</b>\n"
            f"  • Total: <code>{stats.get('TOTAL', 0)}</code> | Completados: <code>{stats.get('COMPLETADO', 0)}</code>\n"
            f"  • Pendientes: <code>{stats.get('PENDIENTE', 0)}</code> | Errores: <code>{stats.get('ERROR', 0)}</code>\n\n"
            f"──────────────────────────\n"
        )

        if active_info:
            pct = active_info['percent']
            pbar = render_progress_bar(pct)
            text += (
                f"⬇️ <b>Descarga Actual:</b>\n"
                f"📄 <code>{active_info['file_name']}</code>\n\n"
                f"<code>[{pbar}]</code> <b>{pct:.1f}%</b>\n\n"
                f"💾 <b>Progreso:</b> <code>{active_info['formatted_downloaded']} / {active_info['formatted_total']}</code>\n"
                f"⚡ <b>Velocidad:</b> <code>{active_info['formatted_speed']}</code>\n"
                f"⏱️ <b>ETA:</b> <code>{active_info['formatted_eta']}</code>"
            )
        else:
            text += "ℹ️ <i>No hay ninguna descarga activa en este momento.</i>"

        keyboard = get_stop_now_keyboard() if active_info else None

        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    # 5. /scan
    async def cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        chat_name = str(self.config.chat_id)
        msg_text = (
            f"🔎 <b>INICIANDO ESCANEO DE CHAT</b>\n"
            f"──────────────────────────\n"
            f"📌 <b>Chat ID:</b> <code>{chat_name}</code>\n"
            f"⏳ <i>Procesando mensajes pasados...</i>"
        )

        if update.message:
            msg = await update.message.reply_text(msg_text, parse_mode="HTML")
        elif update.callback_query:
            msg = update.callback_query.message
            await msg.edit_text(msg_text, parse_mode="HTML")

        try:
            total, new_items = await self.scan_service.scan_chat()
            already_registered = total - new_items

            result_text = (
                f"✅ <b>ESCANEO COMPLETADO</b>\n"
                f"──────────────────────────\n"
                f"📨 <b>Mensajes revisados:</b> <code>{total}</code>\n"
                f"📦 <b>Archivos encontrados:</b> <code>{total}</code>\n"
                f"✨ <b>Archivos nuevos:</b> <code>{new_items}</code>\n"
                f"📁 <b>Archivos ya registrados:</b> <code>{already_registered}</code>"
            )
            await msg.edit_text(result_text, parse_mode="HTML")
        except Exception as e:
            await msg.edit_text(f"❌ <b>Error al ejecutar el escaneo:</b> <i>{e}</i>", parse_mode="HTML")

    # 6. /files
    async def cmd_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE, status_filter: str = "ALL", page: int = 1):
        if not await self._check_auth(update):
            return

        items, total_count, current_page, total_pages = self.status_service.get_paginated_files(
            status_filter=status_filter,
            page=page,
            page_size=5
        )

        status_symbols = {
            "COMPLETADO": "✅ Completado",
            "DESCARGANDO": "⬇️ Descargando",
            "PENDIENTE": "⏳ Pendiente",
            "ERROR": "❌ Error",
            "CANCELADO": "⏸ Cancelado"
        }

        filter_names = {
            "ALL": "Todos",
            "PENDIENTE": "Pendientes",
            "DESCARGANDO": "Descargando",
            "COMPLETADO": "Completados",
            "ERROR": "Errores"
        }

        text = (
            f"📁 <b>EXPLORADOR DE ARCHIVOS</b>\n"
            f"Filtro: <code>{filter_names.get(status_filter, status_filter)}</code> | Pág: <b>{current_page}/{total_pages}</b>\n"
            f"──────────────────────────\n\n"
        )

        if not items:
            text += "<i>No se encontraron archivos en este filtro.</i>"
        else:
            for idx, item in enumerate(items, start=1 + (current_page - 1) * 5):
                st_label = status_symbols.get(item['status'], item['status'])
                text += f"<b>{idx}.</b> <code>{item['file_name']}</code>\n    📦 {item['formatted_size']} — <b>{st_label}</b> — ID: <code>{item['id']}</code>\n\n"

        keyboard = get_files_keyboard(status_filter, current_page, total_pages)

        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    # 7. /queue
    async def cmd_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        queue_items = self.status_service.get_pending_queue(limit=10)
        stats = self.status_service.get_summary_stats()
        pending_count = stats.get('PENDIENTE', 0)

        text = (
            f"📋 <b>COLA DE DESCARGAS PENDIENTES</b>\n"
            f"Total Pendientes: <b>{pending_count}</b>\n"
            f"──────────────────────────\n\n"
        )

        if not queue_items:
            text += "<i>La cola de descargas está vacía.</i>"
        else:
            for idx, item in enumerate(queue_items, start=1):
                priority_tag = " 🔝" if item.get('priority', 0) > 0 else ""
                text += (
                    f"<b>{idx}.</b> <code>{item['file_name']}</code>{priority_tag}\n"
                    f"    📦 <code>{item['formatted_size']}</code> — ID: <code>{item['id']}</code>\n\n"
                )
            text += "<i>Usa /priority &lt;ID&gt; para priorizar un archivo.</i>"

        if update.message:
            await update.message.reply_text(text, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="HTML")


    # 8. /downloads
    async def cmd_downloads(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        active_info = self.status_service.get_active_download_info()

        if not active_info:
            text = "ℹ️ <b>No hay ninguna descarga activa en este momento.</b>"
            keyboard = None
        else:
            pct = active_info['percent']
            pbar = render_progress_bar(pct)
            text = (
                f"⬇️ <b>DESCARGA EN PROGRESO</b>\n"
                f"──────────────────────────\n"
                f"📄 <code>{active_info['file_name']}</code>\n\n"
                f"<code>[{pbar}]</code> <b>{pct:.1f}%</b>\n\n"
                f"💾 <b>Progreso:</b> <code>{active_info['formatted_downloaded']} / {active_info['formatted_total']}</code>\n"
                f"⚡ <b>Velocidad:</b> <code>{active_info['formatted_speed']}</code>\n"
                f"⏱️ <b>ETA:</b> <code>{active_info['formatted_eta']}</code>"
            )
            keyboard = get_stop_now_keyboard()

        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    # 9. /start_downloads
    async def cmd_start_downloads(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        self.download_service.start_downloads()
        stats = self.status_service.get_summary_stats()

        text = (
            f"▶️ <b>DESCARGAS INICIADAS</b>\n"
            f"──────────────────────────\n"
            f"⏳ <b>Pendientes en cola:</b> <code>{stats.get('PENDIENTE', 0)}</code>\n"
            f"⚡ <b>Máximo simultáneo:</b> <code>{self.config.max_concurrent_downloads}</code>"
        )

        if update.message:
            await update.message.reply_text(text, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="HTML")

    # 10. /stop_downloads
    async def cmd_stop_downloads(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        self.download_service.stop_downloads()

        text = (
            f"⏸ <b>COLA DE DESCARGAS PAUSADA</b>\n"
            f"──────────────────────────\n"
            f"• La descarga actual continuará hasta finalizar.\n"
            f"• Los archivos pendientes permanecerán en la cola."
        )

        if update.message:
            await update.message.reply_text(text, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="HTML")

    # 11. /cancel
    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        active_info = self.status_service.get_active_download_info()

        if not active_info:
            text = "ℹ️ <b>No hay ninguna descarga activa para cancelar.</b>"
            if update.message:
                await update.message.reply_text(text, parse_mode="HTML")
            elif update.callback_query:
                await update.callback_query.message.edit_text(text, parse_mode="HTML")
            return

        text = (
            f"⚠️ <b>CONFIRMACIÓN DE CANCELACIÓN</b>\n"
            f"──────────────────────────\n"
            f"📄 <code>{active_info['file_name']}</code>\n\n"
            f"<i>¿Estás seguro de que deseas cancelar esta descarga?</i>"
        )
        keyboard = get_cancel_confirm_keyboard(active_info['item_id'])

        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    # 12. /retry [ID]
    async def cmd_retry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Resets ERROR/CANCELADO items back to PENDIENTE.
        Usage: /retry        → all errors
               /retry <ID>   → specific item
        """
        if not await self._check_auth(update):
            return

        item_id: int | None = None
        if context.args:
            try:
                item_id = int(context.args[0])
            except ValueError:
                text = "⚠️ <b>ID inválido.</b> Uso: <code>/retry</code> o <code>/retry &lt;ID&gt;</code>"
                if update.message:
                    await update.message.reply_text(text, parse_mode="HTML")
                return

        count = self.download_service.retry_errors(item_id=item_id)

        if item_id is not None:
            if count > 0:
                item = self.download_service.repo.get_item(item_id)
                name = item.file_name if item else f"ID {item_id}"
                text = (
                    f"🔁 <b>ARCHIVO PUESTO EN COLA PARA REINTENTO</b>\n"
                    f"──────────────────────────\n"
                    f"📄 <code>{name}</code>\n\n"
                    f"El archivo fue reseteado a <b>PENDIENTE</b>.\n"
                    f"Inicia la cola con /start_downloads si está pausada."
                )
            else:
                text = f"ℹ️ El archivo con ID <code>{item_id}</code> no existe o no está en estado ERROR/CANCELADO."
            if update.message:
                await update.message.reply_text(text, parse_mode="HTML")
        else:
            if count > 0:
                text = (
                    f"🔁 <b>ERRORES RESETEADOS</b>\n"
                    f"──────────────────────────\n"
                    f"✅ <b>{count}</b> archivo(s) reseteados a <b>PENDIENTE</b>.\n\n"
                    f"Inicia la cola con /start_downloads si está pausada."
                )
                keyboard = None
            else:
                text = (
                    f"ℹ️ <b>Sin errores que reintentar</b>\n"
                    f"──────────────────────────\n"
                    f"No hay archivos en estado ERROR o CANCELADO."
                )
                keyboard = get_retry_all_keyboard()
            if update.message:
                await update.message.reply_text(text, reply_markup=keyboard if count == 0 else None, parse_mode="HTML")

    # 13. /priority <ID> [0]
    async def cmd_priority(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sets or removes priority for a download item.
        Usage: /priority <ID>    → max priority (top of queue)
               /priority <ID> 0  → remove priority
        """
        if not await self._check_auth(update):
            return

        if not context.args:
            text = (
                f"ℹ️ <b>Uso del comando /priority:</b>\n"
                f"──────────────────────────\n"
                f"• <code>/priority &lt;ID&gt;</code> — Mover al tope de la cola\n"
                f"• <code>/priority &lt;ID&gt; 0</code> — Quitar prioridad\n\n"
                f"Consulta los IDs con /queue"
            )
            if update.message:
                await update.message.reply_text(text, parse_mode="HTML")
            return

        try:
            item_id = int(context.args[0])
        except ValueError:
            if update.message:
                await update.message.reply_text("⚠️ <b>ID inválido.</b> Debe ser un número.", parse_mode="HTML")
            return

        remove_priority = len(context.args) > 1 and context.args[1] == "0"

        if remove_priority:
            ok = self.download_service.deprioritize_item(item_id)
            if ok:
                item = self.download_service.repo.get_item(item_id)
                name = item.file_name if item else f"ID {item_id}"
                text = (
                    f"⬇️ <b>PRIORIDAD REMOVIDA</b>\n"
                    f"──────────────────────────\n"
                    f"📄 <code>{name}</code>\n\n"
                    f"El archivo vuelve al orden normal de la cola."
                )
            else:
                text = f"⚠️ No se encontró el archivo con ID <code>{item_id}</code>."
        else:
            ok = self.download_service.prioritize_item(item_id)
            if ok:
                item = self.download_service.repo.get_item(item_id)
                name = item.file_name if item else f"ID {item_id}"
                text = (
                    f"🔝 <b>PRIORIDAD MÁXIMA ASIGNADA</b>\n"
                    f"──────────────────────────\n"
                    f"📄 <code>{name}</code>\n\n"
                    f"Este archivo se descargará antes que los demás.\n"
                    f"Usa <code>/priority {item_id} 0</code> para quitar la prioridad."
                )
            else:
                text = f"⚠️ No se encontró el archivo con ID <code>{item_id}</code>."

        if update.message:
            await update.message.reply_text(text, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="HTML")


    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "noop":
            return
        elif data == "cmd_start":
            await self.cmd_start(update, context)
        elif data == "cmd_status":
            await self.cmd_status(update, context)
        elif data == "cmd_help":
            await self.cmd_help(update, context)
        elif data == "cmd_queue":
            await self.cmd_queue(update, context)
        elif data == "cmd_scan":
            await self.cmd_scan(update, context)
        elif data == "cmd_start_downloads":
            await self.cmd_start_downloads(update, context)
        elif data == "cmd_stop_downloads":
            await self.cmd_stop_downloads(update, context)
        elif data == "cmd_downloads":
            await self.cmd_downloads(update, context)
        elif data == "cmd_cancel_active":
            await self.cmd_cancel(update, context)
        elif data.startswith("cmd_guide_"):
            tab = data.split("_")[2]
            await self.cmd_guide(update, context, tab=tab)
        elif data.startswith("cmd_files_"):
            parts = data.split("_")
            status_filter = parts[2]
            page = int(parts[3])
            await self.cmd_files(update, context, status_filter=status_filter, page=page)
        elif data.startswith("approve_file_"):
            item_id = int(data.split("_")[2])
            success = self.download_service.approve_item_for_download(item_id)
            if success:
                await query.message.edit_text(f"✅ <b>Archivo ID #{item_id} aprobado y agregado a la cola.</b>", parse_mode="HTML")
            else:
                await query.message.edit_text(f"⚠️ <b>No se pudo aprobar el archivo ID #{item_id}.</b>", parse_mode="HTML")
        elif data.startswith("ignore_file_"):
            item_id = int(data.split("_")[2])
            self.download_service.ignore_item(item_id)
            await query.message.edit_text(f"❌ <b>Archivo ID #{item_id} ignorado.</b>", parse_mode="HTML")
        elif data.startswith("confirm_cancel_"):
            self.download_service.cancel_active_download()
            text = (
                f"⏸ <b>DESCARGA CANCELADA</b>\n"
                f"──────────────────────────\n"
                f"• El progreso parcial en el archivo <code>.part</code> se conserva.\n"
                f"• Podrá reanudarse posteriormente."
            )
            await query.message.edit_text(text, parse_mode="HTML")
        elif data == "retry_all":
            count = self.download_service.retry_errors()
            if count > 0:
                text = (
                    f"🔁 <b>ERRORES RESETEADOS</b>\n"
                    f"──────────────────────────\n"
                    f"✅ <b>{count}</b> archivo(s) reseteados a <b>PENDIENTE</b>.\n\n"
                    f"Inicia la cola con /start_downloads si está pausada."
                )
            else:
                text = "ℹ️ No hay archivos en estado ERROR o CANCELADO para reintentar."
            await query.message.edit_text(text, parse_mode="HTML")
        elif data.startswith("retry_item_"):
            item_id = int(data.split("_")[2])
            count = self.download_service.retry_errors(item_id=item_id)
            if count > 0:
                item = self.download_service.repo.get_item(item_id)
                name = item.file_name if item else f"ID {item_id}"
                text = (
                    f"🔁 <b>REINTENTO PROGRAMADO</b>\n"
                    f"──────────────────────────\n"
                    f"📄 <code>{name}</code>\n\n"
                    f"Reseteado a <b>PENDIENTE</b>."
                )
            else:
                text = f"ℹ️ El archivo ID <code>{item_id}</code> no está en ERROR/CANCELADO."
            await query.message.edit_text(text, parse_mode="HTML")
        elif data.startswith("priority_set_"):
            item_id = int(data.split("_")[2])
            ok = self.download_service.prioritize_item(item_id)
            if ok:
                item = self.download_service.repo.get_item(item_id)
                name = item.file_name if item else f"ID {item_id}"
                text = (
                    f"🔝 <b>PRIORIDAD MÁXIMA ASIGNADA</b>\n"
                    f"──────────────────────────\n"
                    f"📄 <code>{name}</code>\n\n"
                    f"Se descargará antes que los demás."
                )
            else:
                text = f"⚠️ No se encontró el archivo con ID <code>{item_id}</code>."
            await query.message.edit_text(text, parse_mode="HTML")
        elif data.startswith("priority_unset_"):
            item_id = int(data.split("_")[2])
            ok = self.download_service.deprioritize_item(item_id)
            if ok:
                item = self.download_service.repo.get_item(item_id)
                name = item.file_name if item else f"ID {item_id}"
                text = (
                    f"⬇️ <b>PRIORIDAD REMOVIDA</b>\n"
                    f"──────────────────────────\n"
                    f"📄 <code>{name}</code>\n\n"
                    f"Vuelve al orden normal de la cola."
                )
            else:
                text = f"⚠️ No se encontró el archivo con ID <code>{item_id}</code>."
            await query.message.edit_text(text, parse_mode="HTML")

