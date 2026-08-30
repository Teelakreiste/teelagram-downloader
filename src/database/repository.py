from typing import List, Optional, Dict, Any, Tuple
from math import ceil
from src.core.models import DownloadItem, DownloadState
from src.database.database import Database
from src.utils.logger import logger

class DownloadRepository:
    """Repository wrapping database queries for download tasks and persistent status."""

    def __init__(self, db: Database):
        self.db = db

    def add_item(self, item: DownloadItem) -> bool:
        """
        Inserts a new media download item into SQLite.
        Returns True if inserted, False if it was already present.
        """
        return self.db.add_item(item)

    def get_item(self, item_id: int) -> Optional[DownloadItem]:
        """Retrieves a single download item by ID."""
        sql = "SELECT * FROM downloads WHERE id = ?"
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(sql, (item_id,)).fetchone()
            return self.db._row_to_item(row) if row else None

    def get_pending_or_downloading(self) -> List[DownloadItem]:
        """Returns all items in PENDIENTE or DESCARGANDO state ordered by ID."""
        return self.db.get_pending_or_downloading()

    def get_items_by_status(
        self,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 5
    ) -> Tuple[List[DownloadItem], int, int]:
        """
        Retrieves paginated download items filtered by status.
        status_filter can be 'ALL', 'PENDIENTE', 'DESCARGANDO', 'COMPLETADO', 'ERROR', 'CANCELADO'.
        Returns (items, total_count, total_pages)
        """
        where_clause = ""
        params: List[Any] = []

        if status_filter and status_filter.upper() != "ALL":
            where_clause = "WHERE status = ?"
            params.append(status_filter.upper())

        count_sql = f"SELECT COUNT(*) FROM downloads {where_clause}"
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            total_items = cursor.execute(count_sql, params).fetchone()[0]

            if total_items == 0:
                return [], 0, 1

            total_pages = max(1, ceil(total_items / page_size))
            page = max(1, min(page, total_pages))
            offset = (page - 1) * page_size

            query_sql = f"SELECT * FROM downloads {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?"
            params_query = params + [page_size, offset]
            rows = cursor.execute(query_sql, params_query).fetchall()
            items = [self.db._row_to_item(r) for r in rows]

            return items, total_items, total_pages

    def get_summary_stats(self) -> Dict[str, int]:
        """Returns stats summary dictionary."""
        return self.db.get_summary_stats()

    def update_status(
        self,
        item_id: int,
        status: DownloadState,
        downloaded_size: Optional[int] = None,
        last_error: Optional[str] = None
    ):
        """Updates item download state."""
        self.db.update_status(item_id, status, downloaded_size=downloaded_size, last_error=last_error)

    def update_progress(self, item_id: int, downloaded_size: int):
        """Updates item downloaded size."""
        self.db.update_progress(item_id, downloaded_size)

    def get_all_items(self) -> List[DownloadItem]:
        """Returns all items ordered by ID DESC."""
        return self.db.get_all_items()

    def clear_pending_queue(self) -> int:
        """Cancels all currently pending tasks in database."""
        sql = "UPDATE downloads SET status = 'CANCELADO' WHERE status = 'PENDIENTE'"
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            conn.commit()
            return cursor.rowcount

    def reset_errors_to_pending(self, item_id: Optional[int] = None) -> int:
        """
        Resets ERROR or CANCELADO items back to PENDIENTE for retry.
        Clears last_error and resets retry_count.
        If item_id is provided, only that item is reset.
        Returns the number of items reset.
        """
        return self.db.reset_errors_to_pending(item_id=item_id)

    def set_priority(self, item_id: int, priority: int) -> bool:
        """
        Sets the priority of a download item.
        Higher value = processed sooner. Default is 0.
        Returns True if item was found and updated.
        """
        return self.db.set_priority(item_id, priority)

