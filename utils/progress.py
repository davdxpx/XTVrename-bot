# --- Imports ---
import time
import asyncio
from pyrogram.errors import FloodWait
from utils.XTVengine import XTVEngine

# === Helper Functions ===
async def progress_for_pyrogram(
    current, total, ud_type, message, start_time, mode="core", is_priority=False
):
    now = time.time()
    diff = now - start_time

    # Adaptive throttle based on file size
    if total < 50 * 1024 * 1024:        # < 50MB
        throttle = 5.0
    elif total < 500 * 1024 * 1024:      # < 500MB
        throttle = 8.0
    else:                                 # >= 500MB
        throttle = 12.0

    if current == total:
        pass  # Always update on completion
    elif hasattr(message, "last_update"):
        if (now - getattr(message, "last_update")) < throttle:
            return
    else:
        setattr(message, "last_update", now)

    setattr(message, "last_update", now)

    percentage = current * 100 / total
    speed = current / diff if diff > 0 else 0

    if speed > 0:
        time_to_completion = round((total - current) / speed) * 1000
    else:
        time_to_completion = 0

    estimated_total_time = (
        XTVEngine.time_formatter(time_to_completion) if time_to_completion else "0s"
    )

    filled_length = int(10 * current // total)
    bar = "■" * filled_length + "□" * (10 - filled_length)

    current_fmt = XTVEngine.humanbytes(current)
    total_fmt = XTVEngine.humanbytes(total)
    speed_fmt = XTVEngine.humanbytes(speed)

    text = f"{ud_type}\n\n"

    text += f"**Progress:**  `{percentage:.1f}%`\n"
    text += f"[{bar}]\n\n"

    text += f"**Size:** `{current_fmt}` / `{total_fmt}`\n"
    text += f"**Speed:** `{speed_fmt}/s`\n"
    text += f"**ETA:** `{estimated_total_time}`\n"

    if is_priority:
        text += f"\n**Priority Queue:** `Active`\n"

    text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"{XTVEngine.get_signature(mode=mode)}"

    try:
        await message.edit(text=text)
    except FloodWait as e:
        setattr(message, "last_update", now + e.value)
    except Exception:
        # Message may have been deleted or is otherwise uneditable
        pass

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
