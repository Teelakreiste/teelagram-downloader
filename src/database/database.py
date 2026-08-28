import sqlite3
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from src.core.models import DownloadItem, DownloadState
from src.utils.logger import logger

class Database:
    """SQLite Database manager for download tasks and persistence."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    downloaded_size INTEGER DEFAULT 0,
                    status TEXT NOT NULL CHECK(status IN ('PENDIENTE', 'DESCARGANDO', 'COMPLETADO', 'ERROR', 'CANCELADO')),
                    date_detected TEXT,
                    date_started TEXT,
                    date_completed TEXT,
                    last_error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    mime_type TEXT,
                    UNIQUE(chat_id, message_id)
                )
            """)
            conn.commit()

    def add_item(self, item: DownloadItem) -> bool:
        """
        Inserts a new media file download task into the database.
        Returns True if inserted, False if it already existed (duplicate).
        """
        sql = """
            INSERT INTO downloads (
                chat_id, message_id, file_name, file_path, file_size,
                downloaded_size, status, date_detected, mime_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, message_id) DO NOTHING
        """
        now_str = (item.date_detected or datetime.now()).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (
                item.chat_id,
                item.message_id,
                item.file_name,
                item.file_path,
                item.file_size,
                item.downloaded_size,
                item.status.value,
                now_str,
                item.mime_type
            ))
            conn.commit()
            return cursor.rowcount > 0

    def get_pending_or_downloading(self) -> List[DownloadItem]:
        """Returns all items that are either PENDIENTE or DESCARGANDO (interrupted)."""
        sql = """
            SELECT * FROM downloads 
            WHERE status IN ('PENDIENTE', 'DESCARGANDO')
            ORDER BY id ASC
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql).fetchall()
            return [self._row_to_item(row) for row in rows]

    def update_status(
        self,
        item_id: int,
        status: DownloadState,
        downloaded_size: Optional[int] = None,
        last_error: Optional[str] = None
    ):
        """Updates status, timestamps, downloaded_size, and last_error of an item."""
        sql = "UPDATE downloads SET status = ?"
        params: List[Any] = [status.value]

        if downloaded_size is not None:
            sql += ", downloaded_size = ?"
            params.append(downloaded_size)

        if last_error is not None:
            sql += ", last_error = ?, retry_count = retry_count + 1"
            params.append(last_error)

        now_str = datetime.now().isoformat()
        if status == DownloadState.DESCARGANDO:
            sql += ", date_started = ?"
            params.append(now_str)
        elif status == DownloadState.COMPLETADO:
            sql += ", date_completed = ?"
            params.append(now_str)

        sql += " WHERE id = ?"
        params.append(item_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()

    def update_progress(self, item_id: int, downloaded_size: int):
        """Quick progress update for downloaded bytes."""
        sql = "UPDATE downloads SET downloaded_size = ? WHERE id = ?"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (downloaded_size, item_id))
            conn.commit()

    def get_summary_stats(self) -> Dict[str, int]:
        """Returns download summary counts for console UI dashboard."""
        sql = "SELECT status, COUNT(*) as count FROM downloads GROUP BY status"
        stats = {
            "PENDIENTE": 0,
            "DESCARGANDO": 0,
            "COMPLETADO": 0,
            "ERROR": 0,
            "CANCELADO": 0,
            "TOTAL": 0
        }
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql).fetchall()
            for row in rows:
                st = row["status"]
                cnt = row["count"]
                if st in stats:
                    stats[st] = cnt
                stats["TOTAL"] += cnt
        return stats

    def get_all_items(self) -> List[DownloadItem]:
        """Retrieves all download items ordered by ID."""
        sql = "SELECT * FROM downloads ORDER BY id DESC"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql).fetchall()
            return [self._row_to_item(row) for row in rows]

    def _row_to_item(self, row: sqlite3.Row) -> DownloadItem:
        return DownloadItem(
            id=row["id"],
            chat_id=row["chat_id"],
            message_id=row["message_id"],
            file_name=row["file_name"],
            file_path=row["file_path"],
            file_size=row["file_size"],
            downloaded_size=row["downloaded_size"],
            status=DownloadState(row["status"]),
            date_detected=datetime.fromisoformat(row["date_detected"]) if row["date_detected"] else None,
            date_started=datetime.fromisoformat(row["date_started"]) if row["date_started"] else None,
            date_completed=datetime.fromisoformat(row["date_completed"]) if row["date_completed"] else None,
            last_error=row["last_error"],
            retry_count=row["retry_count"],
            mime_type=row["mime_type"]
        )
