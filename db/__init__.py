"""Database package for XTV-MediaStudio.

Re-exports the `db` singleton, `Database` class, and `SettingsCollectionShim`
so that callers keep the short `from db import db` form regardless of where
the implementation lives.

`db.core` is loaded lazily via module `__getattr__` so that importing
`db.schema` or `db.shim` (both motor-free) does not pull in the Motor
MongoDB client. Tests that only need the shim/schema can run without
installing motor.
"""

from db import schema  # noqa: F401  (ensures `db.schema` is registered)
from db.shim import SettingsCollectionShim

__all__ = ["Database", "db", "SettingsCollectionShim", "schema"]


def __getattr__(name):
    if name in ("db", "Database"):
        from db.core import Database as _Database, db as _db

        globals()["db"] = _db
        globals()["Database"] = _Database
        return globals()[name]
    raise AttributeError(f"module 'db' has no attribute {name!r}")
