# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
No-op callback handler for inert decorative buttons (separators, page
indicators) that must answer the callback query so Telegram doesn't keep
showing a loading spinner.
"""

import contextlib

from pyrogram import Client, filters


@Client.on_callback_query(filters.regex("^noop$"))
async def noop_cb(client, callback_query):
    with contextlib.suppress(Exception):
        await callback_query.answer()
