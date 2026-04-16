# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Feature Toggles & Access Limits admin domain.

Houses the Settings / Access & Limits top-level entry, the quick
system toggles (premium / deluxe / trial / myfiles) surfaced in that
menu, the Global Feature Toggles submenu with its individual
`admin_gtoggle_*` flips, the Per-Plan Limits submenu entry, and the
read-only `admin_global_daily_egress` display.

The rendering of the Access & Limits menu and the Feature Toggles
submenu used to be triggered via recursive `admin_callback` self-calls
(`callback_query.data = "admin_access_limits"; await admin_callback(...)`).
After the split those self-calls would cross module boundaries, so we
use local `_render_*` helpers instead.

The `admin_global_daily_egress` branch here only renders the preview
screen; the text-input flow that backs the "Change" button
(`awaiting_global_egress`) still lives in `_legacy.handle_admin_text`
for now.
"""

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from database import db
from plugins.admin.core import get_admin_access_limits_menu, is_admin


async def _render_access_limits(callback_query: CallbackQuery):
    reply_markup = await get_admin_access_limits_menu()
    try:
        await callback_query.message.edit_text(
            "🔒 **Settings & Controls**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Toggle system features on/off and configure plans, limits, and tools.",
            reply_markup=reply_markup,
        )
    except MessageNotModified:
        pass


async def _render_feature_toggles(callback_query: CallbackQuery):
    toggles = await db.get_feature_toggles()
    audio_en = toggles.get("audio_editor", True)
    conv_en = toggles.get("file_converter", True)
    wm_en = toggles.get("watermarker", True)
    sub_en = toggles.get("subtitle_extractor", True)
    trim_en = toggles.get("video_trimmer", True)
    info_en = toggles.get("media_info", True)
    voice_en = toggles.get("voice_converter", True)
    vnote_en = toggles.get("video_note_converter", True)
    yt_en = toggles.get("youtube_tool", True)
    four_k_en = toggles.get("4k_enhancement", True)
    batch_pro_en = toggles.get("batch_processing_pro", True)

    def emoji(state):
        return "✅" if state else "❌"

    text = (
        "⚙️ **Global Feature Toggles**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Enable or disable features globally (master switch).\n"
        "> Disabled features are hidden for **all** users & plans.\n"
        "> Per-plan overrides can be set in Per-Plan Settings.\n\n"
        "> **Performance Impact:**\n"
        "> • **File Converter:** High CPU & RAM\n"
        "> • **Watermarker / Trimmer:** Medium CPU\n"
        "> • **Audio Editor / Voice:** Low CPU\n"
        "> • **Media Info:** Minimal CPU\n\n"
        "Click a feature below to toggle:"
    )

    buttons = [
        [
            InlineKeyboardButton(
                f"{emoji(conv_en)} 🔀 File Converter",
                callback_data="admin_gtoggle_file_converter",
            ),
            InlineKeyboardButton(
                f"{emoji(sub_en)} 📝 Subtitle Extractor",
                callback_data="admin_gtoggle_subtitle_extractor",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{emoji(wm_en)} ©️ Watermarker",
                callback_data="admin_gtoggle_watermarker",
            ),
            InlineKeyboardButton(
                f"{emoji(audio_en)} 🎵 Audio Editor",
                callback_data="admin_gtoggle_audio_editor",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{emoji(trim_en)} ✂️ Video Trimmer",
                callback_data="admin_gtoggle_video_trimmer",
            ),
            InlineKeyboardButton(
                f"{emoji(info_en)} ℹ️ Media Info",
                callback_data="admin_gtoggle_media_info",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{emoji(voice_en)} 🎙️ Voice Converter",
                callback_data="admin_gtoggle_voice_converter",
            ),
            InlineKeyboardButton(
                f"{emoji(vnote_en)} ⭕ Video Note",
                callback_data="admin_gtoggle_video_note_converter",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{emoji(yt_en)} ▶️ YouTube Tool",
                callback_data="admin_gtoggle_youtube_tool",
            )
        ],
        [
            InlineKeyboardButton(
                f"{emoji(four_k_en)} 📺 4K Enhancement",
                callback_data="admin_gtoggle_4k_enhancement",
            ),
            InlineKeyboardButton(
                f"{emoji(batch_pro_en)} 📦 Batch Pro",
                callback_data="admin_gtoggle_batch_processing_pro",
            ),
        ],
        [
            InlineKeyboardButton(
                "← Back to Settings", callback_data="admin_access_limits"
            )
        ],
    ]

    try:
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(
    filters.regex(
        r"^(admin_access_limits$|admin_quick_toggle_(?:premium|deluxe|trial|myfiles)$"
        r"|admin_feature_toggles$|admin_gtoggle_|admin_per_plan_limits$"
        r"|admin_global_daily_egress$)"
    )
)
async def feature_toggles_cb(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    # --- Quick System Toggles (Settings menu) ---
    if data == "admin_quick_toggle_premium":
        config = await db.get_public_config()
        enabled = config.get("premium_system_enabled", False)
        await db.update_public_config("premium_system_enabled", not enabled)
        await callback_query.answer(
            f"Premium System {'Disabled' if enabled else 'Enabled'}",
            show_alert=True,
        )
        await _render_access_limits(callback_query)
        return

    if data == "admin_quick_toggle_deluxe":
        config = await db.get_public_config()
        enabled = config.get("premium_deluxe_enabled", False)
        await db.update_public_config("premium_deluxe_enabled", not enabled)
        await callback_query.answer(
            f"Deluxe Plan {'Disabled' if enabled else 'Enabled'}",
            show_alert=True,
        )
        await _render_access_limits(callback_query)
        return

    if data == "admin_quick_toggle_trial":
        config = await db.get_public_config()
        enabled = config.get("premium_trial_enabled", False)
        await db.update_public_config("premium_trial_enabled", not enabled)
        await callback_query.answer(
            f"Trial Mode {'Disabled' if enabled else 'Enabled'}",
            show_alert=True,
        )
        await _render_access_limits(callback_query)
        return

    if data == "admin_quick_toggle_myfiles":
        enabled = await db.get_setting("myfiles_enabled", default=False)
        await db.update_setting("myfiles_enabled", not enabled)
        await callback_query.answer(
            f"MyFiles System {'Disabled' if enabled else 'Enabled'}",
            show_alert=True,
        )
        await _render_access_limits(callback_query)
        return

    # --- Access & Limits root ---
    if data == "admin_access_limits":
        await callback_query.answer()
        await _render_access_limits(callback_query)
        return

    # --- Feature Toggles submenu ---
    if data == "admin_feature_toggles":
        await callback_query.answer()
        await _render_feature_toggles(callback_query)
        return

    if data.startswith("admin_gtoggle_"):
        feature = data.replace("admin_gtoggle_", "")
        toggles = await db.get_feature_toggles()
        current_state = toggles.get(feature, True)
        new_state = not current_state
        await db.update_feature_toggle(feature, new_state)
        await callback_query.answer(
            f"{'Enabled' if new_state else 'Disabled'} {feature.replace('_', ' ').title()}.",
            show_alert=True,
        )
        await _render_feature_toggles(callback_query)
        return

    # --- Per-Plan Limits entry ---
    if data == "admin_per_plan_limits":
        await callback_query.answer()
        text = (
            "⚙️ **Per-Plan Settings**\n\n"
            "> Select a subscription tier below to view its current quotas, "
            "features, pricing, and to modify its settings."
        )
        buttons = [
            [InlineKeyboardButton("🆓 Manage Free Plan", callback_data="admin_edit_plan_free")],
            [InlineKeyboardButton("🌟 Manage Standard Plan", callback_data="admin_edit_plan_standard")],
            [InlineKeyboardButton("💎 Manage Deluxe Plan", callback_data="admin_edit_plan_deluxe")],
            [InlineKeyboardButton("← Back to Settings", callback_data="admin_access_limits")],
        ]
        try:
            await callback_query.message.edit_text(
                text, reply_markup=InlineKeyboardMarkup(buttons)
            )
        except MessageNotModified:
            pass
        return

    # --- Global Daily Egress preview ---
    if data == "admin_global_daily_egress":
        await callback_query.answer()
        current_val = await db.get_global_daily_egress_limit()
        try:
            await callback_query.message.edit_text(
                f"🌍 **Edit Global Daily Egress Limit**\n\n"
                f"Current: `{current_val}` MB\n\n"
                "Click below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_global_daily_egress"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Settings",
                                callback_data="admin_access_limits",
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return
