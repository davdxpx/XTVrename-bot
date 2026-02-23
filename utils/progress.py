import time
import math
from utils.XTVcore import XTVEngine

async def progress_for_pyrogram(current, total, ud_type, message, start_time):
    """
    Enhanced progress callback for Pyrogram with 'Business Software Level' formatting.
    Features:
    - Visual progress bar [■■■■■□□□□□]
    - Detailed metrics (Size, Speed, ETA, Percentage)
    - Clean layout and XTV Engine branding.
    """
    now = time.time()
    diff = now - start_time

    # Throttle updates: Every 5 seconds or upon completion/start
    if current == total:
        pass # Force update on completion
    elif hasattr(message, "last_update"):
        if (now - getattr(message, "last_update")) < 3.0: # 3 second throttle
            return
    else:
        # First update
        setattr(message, "last_update", now)

    setattr(message, "last_update", now)

    percentage = current * 100 / total
    speed = current / diff if diff > 0 else 0
    elapsed_time = round(diff) * 1000

    if speed > 0:
        time_to_completion = round((total - current) / speed) * 1000
    else:
        time_to_completion = 0

    estimated_total_time = XTVEngine.time_formatter(time_to_completion) if time_to_completion else "0s"

    # Visual Progress Bar (10 blocks)
    # ■ = Completed, □ = Remaining
    filled_length = int(10 * current // total)
    bar = '■' * filled_length + '□' * (10 - filled_length)

    # Format Size
    current_fmt = XTVEngine.humanbytes(current)
    total_fmt = XTVEngine.humanbytes(total)
    speed_fmt = XTVEngine.humanbytes(speed)

    # Business Layout
    text = f"{ud_type}\n\n"

    text += f"**Progress:**  `{percentage:.1f}%`\n"
    text += f"[{bar}]\n\n"

    text += f"**💾 Size:** `{current_fmt}` / `{total_fmt}`\n"
    text += f"**🚀 Speed:** `{speed_fmt}/s`\n"
    text += f"**⏳ ETA:** `{estimated_total_time}`\n"

    # Engine Footer
    text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"{XTVEngine.get_signature()}"

    try:
        await message.edit(text=text)
    except Exception as e:
        # Ignore message not modified errors
        pass
