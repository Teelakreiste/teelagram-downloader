import time
from typing import List, Optional, Dict, Any
from telegram import Bot, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter
from src.config.settings import Config
from src.core.models import DownloadItem
from src.utils.filesystem import format_bytes, format_time
from src.utils.logger import logger
from src.bot.keyboards import get_new_file_keyboard, get_stop_now_keyboard

def render_progress_bar(percent: float, length: int = 10) -> str:
    """Renders a text progress bar: [██████░░░░]"""
    filled = int(round(length * percent / 100))
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)

class BotNotifier:
    """Sends realtime event notifications to authorized admin Telegram accounts using rich HTML formatting."""

    def __init__(self, config: Config, bot: Optional[Bot] = None):
        self.config = config
        self.bot = bot
        self.last_progress_edit_time: float = 0.0
        self.progress_message_ids: Dict[int, int] = {}  # chat_id -> message_id

    def set_bot(self, bot: Bot):
        self.bot = bot

    async def _send_to_all_admins(self, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        if not self.bot or not self.config.admin_user_ids:
            return

        for admin_id in self.config.admin_user_ids:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error enviando notificación a admin {admin_id}: {e}")

    async def notify_new_file(self, item: DownloadItem):
        text = (
            f"📥 <b>NUEVO ARCHIVO DETECTADO</b>\n"
            f"──────────────────────────\n"
            f"📄 <b>Archivo:</b> <code>{item.file_name}</code>\n"
            f"📦 <b>Tamaño:</b> <code>{format_bytes(item.file_size)}</code>\n"
            f"💬 <b>Mensaje ID:</b> <code>#{item.message_id}</code>\n"
            f"⏳ <b>Estado:</b> <code>PENDIENTE</code>\n\n"
            f"<i>¿Deseas agregar este archivo a la cola de descargas?</i>"
        )
        keyboard = get_new_file_keyboard(item.id) if item.id else None
        await self._send_to_all_admins(text, reply_markup=keyboard)

    async def notify_download_start(self, item: DownloadItem):
        if not self.bot or not self.config.admin_user_ids:
            return

        pbar = render_progress_bar(0.0)
        tot = format_bytes(item.file_size)
        text = (
            f"⬇️ <b>INICIANDO DESCARGA</b>\n"
            f"──────────────────────────\n"
            f"📄 <code>{item.file_name}</code>\n\n"
            f"<code>[{pbar}]</code> <b>0.0%</b>\n\n"
            f"💾 <b>Progreso:</b> <code>0 B / {tot}</code>\n"
            f"⚡ <b>Velocidad:</b> <code>Iniciando...</code>\n"
            f"⏱️ <b>ETA:</b> <code>--:--</code>"
        )
        keyboard = get_stop_now_keyboard()

        for admin_id in self.config.admin_user_ids:
            try:
                msg = await self.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                self.progress_message_ids[admin_id] = msg.message_id
            except Exception as e:
                logger.error(f"Error enviando mensaje inicial de descarga a admin {admin_id}: {e}")

    async def notify_download_complete(self, item: DownloadItem):
        if not self.bot or not self.config.admin_user_ids:
            return

        pbar = render_progress_bar(100.0)
        tot = format_bytes(item.file_size)
        text = (
            f"✅ <b>DESCARGA COMPLETADA CON ÉXITO</b>\n"
            f"──────────────────────────\n"
            f"📄 <code>{item.file_name}</code>\n\n"
            f"<code>[{pbar}]</code> <b>100.0%</b>\n\n"
            f"📦 <b>Tamaño Final:</b> <code>{tot}</code>\n"
            f"📁 <b>Destino:</b> <code>{self.config.download_dir}</code>"
        )

        for admin_id in self.config.admin_user_ids:
            msg_id = self.progress_message_ids.pop(admin_id, None)
            try:
                if msg_id:
                    await self.bot.edit_message_text(
                        chat_id=admin_id,
                        message_id=msg_id,
                        text=text,
                        parse_mode="HTML"
                    )
                else:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        parse_mode="HTML"
                    )
            except Exception:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error enviando completado a admin {admin_id}: {e}")

    async def notify_download_error(self, item: DownloadItem, error_msg: str, retries: int):
        if not self.bot or not self.config.admin_user_ids:
            return

        text = (
            f"❌ <b>ERROR DE DESCARGA</b>\n"
            f"──────────────────────────\n"
            f"📄 <code>{item.file_name}</code>\n"
            f"⚠️ <b>Error:</b> <i>{error_msg}</i>\n"
            f"🔄 <b>Intento:</b> <code>{retries}/5</code>"
        )

        for admin_id in self.config.admin_user_ids:
            msg_id = self.progress_message_ids.pop(admin_id, None)
            try:
                if msg_id:
                    await self.bot.edit_message_text(
                        chat_id=admin_id,
                        message_id=msg_id,
                        text=text,
                        parse_mode="HTML"
                    )
                else:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        parse_mode="HTML"
                    )
            except Exception:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error enviando error a admin {admin_id}: {e}")

    async def notify_queue_completed(self, stats: Dict[str, int]):
        text = (
            f"🎉 <b>COLA DE DESCARGAS COMPLETADA</b>\n"
            f"──────────────────────────\n"
            f"📊 <b>Total procesados:</b> <code>{stats.get('TOTAL', 0)}</code>\n"
            f"✅ <b>Completados:</b> <code>{stats.get('COMPLETADO', 0)}</code>\n"
            f"❌ <b>Errores:</b> <code>{stats.get('ERROR', 0)}</code>"
        )
        await self._send_to_all_admins(text)

    async def update_progress_notification(self, item: DownloadItem, progress_data: Dict[str, Any]):
        """Real-time live updates to progress message with adaptive throttling."""
        if not self.bot or not self.config.admin_user_ids:
            return

        now = time.time()
        if now - self.last_progress_edit_time < self.config.bot_progress_update_interval:
            return
        self.last_progress_edit_time = now

        pct = progress_data.get("percent", 0.0)
        pbar = render_progress_bar(pct)
        spd = format_bytes(progress_data.get("speed", 0.0))
        dl = format_bytes(progress_data.get("downloaded", 0))
        tot = format_bytes(item.file_size)
        eta = format_time(progress_data.get("eta", 0))

        text = (
            f"⬇️ <b>DESCARGA EN PROGRESO</b>\n"
            f"──────────────────────────\n"
            f"📄 <code>{item.file_name}</code>\n\n"
            f"<code>[{pbar}]</code> <b>{pct:.1f}%</b>\n\n"
            f"💾 <b>Progreso:</b> <code>{dl} / {tot}</code>\n"
            f"⚡ <b>Velocidad:</b> <code>{spd}/s</code>\n"
            f"⏱️ <b>ETA:</b> <code>{eta}</code>"
        )
        keyboard = get_stop_now_keyboard()

        for admin_id in self.config.admin_user_ids:
            msg_id = self.progress_message_ids.get(admin_id)
            try:
                if msg_id:
                    await self.bot.edit_message_text(
                        chat_id=admin_id,
                        message_id=msg_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                else:
                    msg = await self.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    self.progress_message_ids[admin_id] = msg.message_id
            except BadRequest as be:
                if "message is not modified" in str(be).lower():
                    pass
                else:
                    self.progress_message_ids.pop(admin_id, None)
            except RetryAfter as ra:
                self.last_progress_edit_time = now + ra.retry_after
            except Exception as e:
                logger.debug(f"Error actualizando progreso a admin {admin_id}: {e}")
                self.progress_message_ids.pop(admin_id, None)

