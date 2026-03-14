from datetime import datetime
import time


class XTVEngine:
    NAME_CORE = "𝕏TV Core"
    VERSION_CORE = "3.1"

    NAME_PRO = "𝕏TV Pro"
    VERSION_PRO = "1.7"

    BUILD = "2405.1"
    DEVELOPER = "@davdxpx"
    ORGANIZATION = "@XTVglobal"

    ICON_ENGINE = "🤖"
    ICON_DEV = "👨‍💻"
    ICON_ORG = "🏢"

    @classmethod
    def get_signature(cls, mode="core"):
        if mode.lower() == "pro":
            name = cls.NAME_PRO
            version = cls.VERSION_PRO
        else:
            name = cls.NAME_CORE
            version = cls.VERSION_CORE

        return f"{cls.ICON_ENGINE} **Engine:** {name} v{version}"

    @classmethod
    def get_footer(cls):
        return (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{cls.ICON_DEV} **Developer:** {cls.DEVELOPER}\n"
            f"{cls.ICON_ORG} **Powered by:** {cls.ORGANIZATION}"
        )

    @staticmethod
    def humanbytes(size):
        if not size:
            return "0 B"
        power = 2**10
        n = 0
        dic_power = {0: " ", 1: "K", 2: "M", 3: "G", 4: "T"}
        while size > power:
            size /= power
            n += 1
        return str(round(size, 2)) + " " + dic_power[n] + "B"

    @staticmethod
    def time_formatter(milliseconds: int) -> str:
        seconds, milliseconds = divmod(int(milliseconds), 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        tmp = (
            ((str(days) + "d, ") if days else "")
            + ((str(hours) + "h, ") if hours else "")
            + ((str(minutes) + "m, ") if minutes else "")
            + ((str(seconds) + "s") if seconds else "")
        )
        return tmp[:-2] if tmp.endswith(", ") else tmp


engine = XTVEngine()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
