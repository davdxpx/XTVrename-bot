# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Legacy monolithic admin handlers — **fully retired**.

All callback handlers and text-input state handlers have been migrated
to their respective domain modules.  This file is kept temporarily for
backward compatibility with ``__init__.py`` but contains no active code.
It will be deleted in Schritt 16.

Migration summary:
- Callback dispatcher → domain modules (panel, general, feature_toggles, ...)
- handle_admin_text   → text_dispatcher.py routes to domain handle_text fns
- handle_admin_photo  → thumbnails.py
- Dashboard           → dashboard.py
- User moderation     → users_mod.py
- Noop                → noop.py
"""

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
