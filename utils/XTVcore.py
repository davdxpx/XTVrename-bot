"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    Developed by 𝕏0L0™ (@davdxpx)                         ║
║     © 2024 XTV Network Global. All Rights Reserved.                      ║
║                                                                          ║
║  Project: XTV Rename Bot                                                 ║
║  Author: 𝕏0L0™                                                           ║
║  Telegram: @davdxpx                                                      ║
║  Channel: @XTVbots                                                       ║
║  Network: @XTVglobal                                                     ║
║  Backup: @XTVhome                                                        ║
║                                                                          ║
║  WARNING: This code is the intellectual property of XTV Network.         ║
║  Unauthorized modification, redistribution, or removal of this credit    ║
║  is strictly prohibited. Forking and simple usage is allowed under       ║
║  the terms of the license.                                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from datetime import datetime
import time

class XTVEngine:
    # Core Mode (Default)
    NAME_CORE = "𝕏TV Core"
    VERSION_CORE = "2.1"

    # Pro Mode (Userbot for >2GB)
    NAME_PRO = "𝕏TV Pro"
    VERSION_PRO = "1.1"

    BUILD = "2405.1" # YearMonth.Revision
    DEVELOPER = "@davdxpx"
    ORGANIZATION = "@XTVglobal"

    # Visual Branding
    ICON_ENGINE = "🤖"
    ICON_DEV = "👨‍💻"
    ICON_ORG = "🏢"

    @classmethod
    def get_signature(cls, mode="core"):
        """Returns the official engine signature string."""
        if mode.lower() == "pro":
            name = cls.NAME_PRO
            version = cls.VERSION_PRO
        else:
            name = cls.NAME_CORE
            version = cls.VERSION_CORE

        return f"{cls.ICON_ENGINE} **Engine:** {name} v{version}"

    @classmethod
    def get_footer(cls):
        """Returns the standard footer for completion messages."""
        return (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{cls.ICON_DEV} **Developer:** {cls.DEVELOPER}\n"
            f"{cls.ICON_ORG} **Powered by:** {cls.ORGANIZATION}"
        )

    @staticmethod
    def humanbytes(size):
        """Standard human-readable size formatter for the engine."""
        if not size:
            return "0 B"
        power = 2**10
        n = 0
        dic_power = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return str(round(size, 2)) + " " + dic_power[n] + 'B'

    @staticmethod
    def time_formatter(milliseconds: int) -> str:
        """Formats milliseconds into readable duration (H:M:S)."""
        seconds, milliseconds = divmod(int(milliseconds), 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        tmp = ((str(days) + "d, ") if days else "") + \
              ((str(hours) + "h, ") if hours else "") + \
              ((str(minutes) + "m, ") if minutes else "") + \
              ((str(seconds) + "s") if seconds else "")
        return tmp[:-2] if tmp.endswith(", ") else tmp

engine = XTVEngine()
