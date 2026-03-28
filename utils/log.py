# --- Imports ---
import logging
import sys

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

    def format(self, record):
        emoji = self.FORMATS.get(record.levelno, "")
        color = self.COLOR_MAP.get(record.levelno, Colors.RESET)

        log_fmt = (
            f"{Colors.BLUE}[%(asctime)s]{Colors.RESET} "
            f"{color}{emoji}%(levelname)-8s{Colors.RESET} :: "
            f"{color}%(message)s{Colors.RESET}"
        )

        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)

# === Helper Functions ===
def get_logger(name):
    from config import Config
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if Config.DEBUG_MODE else logging.INFO)

    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(ConsoleFormatter())
        logger.addHandler(ch)

    logging.getLogger("pyrogram").setLevel(logging.ERROR)
    logging.getLogger("pyrogram.session.session").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
