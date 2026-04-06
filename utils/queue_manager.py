# --- Imports ---
import asyncio
import uuid
import time
from typing import Dict, List, Any, Optional

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

        earlier_items = [i for i in self.items.values() if i.sort_key < item.sort_key]

        for earlier in sorted(earlier_items, key=lambda x: x.sort_key):
            if earlier.status in ["processing", "done_user"]:
                return earlier

        return None

    def is_batch_complete(self) -> bool:
        return all(item.status in ["done", "done_dumb", "done_user", "failed"] for item in self.items.values())

class QueueManager:
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

    def get_blocking_item(self, batch_id: str, item_id: str) -> Optional[QueueItem]:
        if batch_id in self.batches:
            return self.batches[batch_id].is_blocked(item_id)
        return None

    def is_batch_complete(self, batch_id: str) -> bool:
        if batch_id in self.batches:
            return self.batches[batch_id].is_batch_complete()
        return True

    def get_batch_summary(self, batch_id: str, usage_text: str, group_link: str = None) -> str:
        if batch_id not in self.batches:
            if group_link:
                return f"✅ **Batch Processing Complete!**\n\n🔗 **Group Link:** `{group_link}`\n\n📊 **Usage:** {usage_text}"
            return f"✅ **Batch Processing Complete!**\n\n📊 **Usage:** {usage_text}"

        batch = self.batches[batch_id]
        success_items = []
        failed_items = []

        for item in sorted(batch.items.values(), key=lambda x: x.sort_key):
            if item.status == "failed":
                failed_items.append(item.display_name)
            else:
                success_items.append(item.display_name)

        total = len(batch.items)
        success_count = len(success_items)
        failed_count = len(failed_items)

        text = f"✅ **Batch Processing Complete!**\n\n"
        text += f"**Processed:** `{success_count}/{total}` files successfully.\n"

        if success_items:

            if len(success_items) <= 5:
                items_str = ", ".join(success_items)
                text += f"**Included:** `{items_str}`\n"
            else:
                text += f"**Included:** `{success_items[0]} ... {success_items[-1]}`\n"

        if failed_items:
            text += f"**Failed:** `{failed_count}` files.\n"

        if group_link:
            text += f"\n🔗 **Share Link:**\n`{group_link}`\n"

        text += f"\n📊 **Usage:** {usage_text.replace('Today: ', '')}"
        return text

queue_manager = QueueManager()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
