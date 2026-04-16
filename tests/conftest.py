"""Shared pytest fixtures and environment bootstrap for the test suite."""

import os
import sys
from pathlib import Path

# config.py calls Config.validate() on import and will SystemExit without these.
os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "test-hash")
os.environ.setdefault("MAIN_URI", "mongodb://localhost/test")
os.environ.setdefault("CEO_ID", "1")
os.environ.setdefault("PUBLIC_MODE", "false")

# Let tests import top-level modules (database, database_shim, ...) without
# installing the project.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
