"""Database migrations for XTV-MediaStudio.

Each migration module exposes a single `run_<name>_migration(db, *, dry_run=False)`
coroutine that is idempotent, advisory-locked, and safe to re-run on restart.

The current layout migration (`mediastudio_layout`) splits the legacy
`user_settings` collection into per-concern docs under `MediaStudio-Settings`
and inlines per-user settings into `MediaStudio-users`.
"""
