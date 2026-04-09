# --- Imports ---
import logging
import sys
from config import Config

# === Classes ===
class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    BOLD = "\033[1m"
    CYAN = "\033[36m"

class ConsoleFormatter(logging.Formatter):

    FORMATS = {
        logging.DEBUG: "🐞",
        logging.INFO: "ℹ️ ",
        logging.WARNING: "⚠️ ",
        logging.ERROR: "❌ ",
        logging.CRITICAL: "🔥 ",
    }

    COLOR_MAP = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED + Colors.BOLD,
        logging.CRITICAL: Colors.RED + Colors.BOLD,
    }

    # Cache formatters per level to avoid re-creating on every .format() call
    _cached_formatters = {}

    def format(self, record):
        if record.levelno not in self._cached_formatters:
            emoji = self.FORMATS.get(record.levelno, "")
            color = self.COLOR_MAP.get(record.levelno, Colors.RESET)
            log_fmt = (
                f"{Colors.BLUE}[%(asctime)s]{Colors.RESET} "
                f"{color}{emoji}%(levelname)-8s{Colors.RESET} :: "
                f"{color}%(message)s{Colors.RESET}"
            )
            self._cached_formatters[record.levelno] = logging.Formatter(log_fmt, datefmt="%H:%M:%S")

        return self._cached_formatters[record.levelno].format(record)

# Set third-party log levels once at module load
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("pyrogram.session.session").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Shared handler instance
_console_handler = None

# === Helper Functions ===
def get_logger(name):
    global _console_handler

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if Config.DEBUG_MODE else logging.INFO)

    if not logger.handlers:
        if _console_handler is None:
            _console_handler = logging.StreamHandler(sys.stdout)
            _console_handler.setFormatter(ConsoleFormatter())
        logger.addHandler(_console_handler)

    return logger

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
