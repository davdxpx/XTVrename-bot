import math
import time

async def progress_for_pyrogram(current, total, ud_type, message, start_time):
    now = time.time()
    diff = now - start_time

    # Check if we should update (every 5 seconds or on completion)
    if current == total:
        pass
    elif hasattr(message, "last_update"):
        if now - getattr(message, "last_update") < 5:
            return
    else:
        # First update
        setattr(message, "last_update", now)

    setattr(message, "last_update", now)

    percentage = current * 100 / total
    speed = current / diff if diff > 0 else 0

    def humanbytes(size):
        if not size: return ""
        power = 2**10
        n = 0
        Dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

    def TimeFormatter(milliseconds: int) -> str:
        seconds, milliseconds = divmod(int(milliseconds), 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        tmp = ((str(days) + "d, ") if days else "") + \
              ((str(hours) + "h, ") if hours else "") + \
              ((str(minutes) + "m, ") if minutes else "") + \
              ((str(seconds) + "s, ") if seconds else "")
        return tmp[:-2] if tmp else "0s"

    if speed > 0:
        time_to_completion = round((total - current) / speed) * 1000
    else:
        time_to_completion = 0

    estimated_total_time = TimeFormatter(time_to_completion)

    filled_length = int(20 * current // total)
    bar = '▣' * filled_length + '▢' * (20 - filled_length)

    text = f"{ud_type}\n"
    text += f"{bar} Size : {humanbytes(current)} / {humanbytes(total)}\n"
    text += f"Done : {round(percentage, 2)}%\n"
    text += f"Speed : {humanbytes(speed)}/s\n"
    text += f"ETA : {estimated_total_time}"

    try:
        await message.edit(text=text)
    except Exception as e:
        pass
