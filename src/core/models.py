from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

class DownloadState(str, Enum):
    PENDIENTE = "PENDIENTE"
    DESCARGANDO = "DESCARGANDO"
    COMPLETADO = "COMPLETADO"
    ERROR = "ERROR"
    CANCELADO = "CANCELADO"

@dataclass
class DownloadItem:
    id: Optional[int]
    chat_id: int
    message_id: int
    file_name: str
    file_path: str
    file_size: int
    downloaded_size: int = 0
    status: DownloadState = DownloadState.PENDIENTE
    date_detected: Optional[datetime] = None
    date_started: Optional[datetime] = None
    date_completed: Optional[datetime] = None
    last_error: Optional[str] = None
    retry_count: int = 0
    mime_type: Optional[str] = None
