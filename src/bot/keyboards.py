from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Optional

def get_start_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for /start dashboard."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Estado", callback_data="cmd_status"),
            InlineKeyboardButton("📁 Archivos", callback_data="cmd_files_ALL_1"),
        ],
        [
            InlineKeyboardButton("📋 Cola", callback_data="cmd_queue"),
            InlineKeyboardButton("🔎 Escanear", callback_data="cmd_scan"),
        ],
        [
            InlineKeyboardButton("▶️ Iniciar descargas", callback_data="cmd_start_downloads"),
            InlineKeyboardButton("⏸ Detener descargas", callback_data="cmd_stop_downloads"),
        ],
        [
            InlineKeyboardButton("📖 Guía de uso", callback_data="cmd_guide_quick"),
            InlineKeyboardButton("❓ Ayuda", callback_data="cmd_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_new_file_keyboard(item_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard for new file detection notification."""
    keyboard = [
        [
            InlineKeyboardButton("📥 Descargar", callback_data=f"approve_file_{item_id}"),
            InlineKeyboardButton("❌ Ignorar", callback_data=f"ignore_file_{item_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_files_keyboard(current_filter: str, current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Inline keyboard for /files listing with filters and pagination."""
    filters = ["ALL", "PENDIENTE", "DESCARGANDO", "COMPLETADO", "ERROR"]
    filter_labels = {
        "ALL": "Todos",
        "PENDIENTE": "Pendientes",
        "DESCARGANDO": "Descargando",
        "COMPLETADO": "Completados",
        "ERROR": "Errores"
    }

    filter_row = []
    for f in filters:
        label = f"• {filter_labels[f]} •" if f == current_filter else filter_labels[f]
        filter_row.append(InlineKeyboardButton(label, callback_data=f"cmd_files_{f}_1"))

    row1 = filter_row[:3]
    row2 = filter_row[3:]

    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton("◀️ Anterior", callback_data=f"cmd_files_{current_filter}_{current_page - 1}"))
    nav_row.append(InlineKeyboardButton(f"Pág {current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton("Siguiente ▶️", callback_data=f"cmd_files_{current_filter}_{current_page + 1}"))

    return InlineKeyboardMarkup([row1, row2, nav_row])

def get_guide_keyboard(active_tab: str = "quick") -> InlineKeyboardMarkup:
    """Inline keyboard for interactive user guide navigation."""
    tabs = {
        "quick": "🚀 Inicio",
        "dl": "📥 Descargas & .part",
        "cmds": "🤖 Comandos",
        "config": "⚙️ Configuración"
    }
    
    row1 = []
    for tab_id, label in list(tabs.items())[:2]:
        btn_label = f"• {label} •" if tab_id == active_tab else label
        row1.append(InlineKeyboardButton(btn_label, callback_data=f"cmd_guide_{tab_id}"))

    row2 = []
    for tab_id, label in list(tabs.items())[2:]:
        btn_label = f"• {label} •" if tab_id == active_tab else label
        row2.append(InlineKeyboardButton(btn_label, callback_data=f"cmd_guide_{tab_id}"))

    back_row = [InlineKeyboardButton("🏠 Volver al Panel", callback_data="cmd_start")]
    return InlineKeyboardMarkup([row1, row2, back_row])

def get_cancel_confirm_keyboard(item_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard for download cancellation confirmation."""
    keyboard = [
        [
            InlineKeyboardButton("⚠️ Sí, cancelar", callback_data=f"confirm_cancel_{item_id}"),
            InlineKeyboardButton("No, mantener", callback_data="cmd_downloads")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_stop_now_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for active download progress view."""
    keyboard = [
        [
            InlineKeyboardButton("🛑 Detener ahora", callback_data="cmd_cancel_active")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
