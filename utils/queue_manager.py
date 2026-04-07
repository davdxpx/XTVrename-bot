# --- Imports ---
import uuid
import time
from typing import Dict, Optional

# === Classes ===
class QueueItem:
    def __init__(
        self, item_id: str, sort_key: tuple, display_name: str, message_id: int, is_priority: bool = False
    ):
        self.item_id = item_id
        self.sort_key = sort_key
        self.display_name = display_name
        self.message_id = message_id
        self.status = "processing"
        self.error = None
        self.is_priority = is_priority

class BatchQueue:
    def __init__(self, batch_id: str):
        self.batch_id = batch_id
        self.items: Dict[str, QueueItem] = {}
        self.created_at = time.time()

    def add_item(self, item: QueueItem):
        self.items[item.item_id] = item

    def get_item(self, item_id: str) -> Optional[QueueItem]:
        return self.items.get(item_id)

    def is_blocked(self, item_id: str) -> Optional[QueueItem]:
        item = self.items.get(item_id)
        if not item:
            return None

        for earlier in self.items.values():
            if earlier.sort_key < item.sort_key and earlier.status in ["processing", "done_user"]:
                return earlier

        return None

    def is_batch_complete(self) -> bool:
        return all(item.status in ["done", "done_dumb", "done_user", "failed"] for item in self.items.values())

class QueueManager:
    _BATCH_MAX_AGE = 3600  # 1 hour

    def __init__(self):
        self.batches: Dict[str, BatchQueue] = {}

    def create_batch(self) -> str:
        batch_id = str(uuid.uuid4())
        self.batches[batch_id] = BatchQueue(batch_id)
        return batch_id

    def add_to_batch(
        self,
        batch_id: str,
        item_id: str,
        sort_key: tuple,
        display_name: str,
        message_id: int,
        is_priority: bool = False
    ):
        if batch_id not in self.batches:
            self.batches[batch_id] = BatchQueue(batch_id)

        item = QueueItem(item_id, sort_key, display_name, message_id, is_priority)
        self.batches[batch_id].add_item(item)

    def update_status(
        self, batch_id: str, item_id: str, status: str, error: str = None
    ):
        if batch_id in self.batches:
            item = self.batches[batch_id].get_item(item_id)
            if item:
                item.status = status
                if error:
                    item.error = error

    def cleanup_completed(self):
        """Remove completed or expired batches to prevent memory leaks."""
        now = time.time()
        to_remove = [
            bid for bid, batch in self.batches.items()
            if batch.is_batch_complete() or (now - batch.created_at > self._BATCH_MAX_AGE)
        ]
        for bid in to_remove:
            del self.batches[bid]
        return len(to_remove)

queue_manager = QueueManager()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
