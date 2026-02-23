from datetime import datetime
import time

class XTVEngine:
    """
    Core definitions for the XTV Rename Engine.
    This class serves as the central point for branding, versioning, and developer credits.
    It formalizes the 'XTV Core v2.0' identity requested by the CEO.
    """

    NAME = "XTV Core"
    VERSION = "2.0"
    BUILD = "2405.1" # YearMonth.Revision
    DEVELOPER = "@davdxpx"
    ORGANIZATION = "@XTVglobal"

    # Visual Branding
    ICON_ENGINE = "🤖"
    ICON_DEV = "👨‍💻"
    ICON_ORG = "🏢"

    @classmethod
    def get_signature(cls):
        """Returns the official engine signature string."""
        return f"{cls.ICON_ENGINE} **Engine:** {cls.NAME} v{cls.VERSION}"

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
