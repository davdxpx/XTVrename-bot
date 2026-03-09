import asyncio
import uuid
import time
from typing import Dict, List, Any, Optional

class QueueItem:
    def __init__(self, item_id: str, sort_key: tuple, display_name: str, message_id: int):
        self.item_id = item_id
        self.sort_key = sort_key
        self.display_name = display_name
        self.message_id = message_id
        self.status = "processing" # processing, done_user, done_dumb, failed
        self.error = None

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
        """
        Checks if the given item is blocked by any earlier item in the batch
        that hasn't finished its dumb channel upload yet.
        Returns the blocking QueueItem if blocked, None otherwise.
        """
        item = self.items.get(item_id)
        if not item:
            return None

        # Find all items that should come BEFORE this item
        earlier_items = [
            i for i in self.items.values()
            if i.sort_key < item.sort_key
        ]

        # An item is blocked if ANY earlier item is not "done_dumb" or "failed"
        for earlier in sorted(earlier_items, key=lambda x: x.sort_key):
            if earlier.status in ["processing", "done_user"]:
                return earlier

        return None

class QueueManager:
    def __init__(self):
        self.batches: Dict[str, BatchQueue] = {}

    def create_batch(self) -> str:
        batch_id = str(uuid.uuid4())
        self.batches[batch_id] = BatchQueue(batch_id)
        return batch_id

    def add_to_batch(self, batch_id: str, item_id: str, sort_key: tuple, display_name: str, message_id: int):
        if batch_id not in self.batches:
            self.batches[batch_id] = BatchQueue(batch_id)

        item = QueueItem(item_id, sort_key, display_name, message_id)
        self.batches[batch_id].add_item(item)

    def update_status(self, batch_id: str, item_id: str, status: str, error: str = None):
        if batch_id in self.batches:
            item = self.batches[batch_id].get_item(item_id)
            if item:
                item.status = status
                if error:
                    item.error = error

    def get_blocking_item(self, batch_id: str, item_id: str) -> Optional[QueueItem]:
        if batch_id in self.batches:
            return self.batches[batch_id].is_blocked(item_id)
        return None

# Singleton instance
queue_manager = QueueManager()
