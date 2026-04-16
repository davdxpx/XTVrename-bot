# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Premium admin domain.

Covers per-plan settings (edit plan limits, features, pricing),
premium system toggles, trial system, per-plan feature toggles
(media tools, perks, privacy), daily egress/file limits for
free and premium plans, and currency selection.

Text-input flows (awaiting_premium_*, awaiting_trial_days,
awaiting_public_daily_*) are registered with the shared
``text_dispatcher`` and routed here at runtime.
"""

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin


# ── Shared tool definitions ────────────────────────────────────────────

TOOL_DEFS = [
    ("subtitle_extractor", "🎬 Subtitle Extractor"),
    ("watermarker", "🖼 Watermarker"),
    ("file_converter", "🔄 Converter"),
    ("audio_editor", "🎵 Audio Editor"),
    ("video_trimmer", "✂️ Video Trimmer"),
    ("media_info", "ℹ️ Media Info"),
    ("voice_converter", "🎙️ Voice Converter"),
    ("video_note_converter", "⭕ Video Note"),
    ("youtube_tool", "▶️ YouTube Tool"),
    ("4k_enhancement", "📺 4K Enhancement"),
    ("batch_processing_pro", "📦 Batch Pro"),
]

TOOL_CHECKS = [
    ("subtitle_extractor", "💬 Subtitle Extractor"),
    ("watermarker", "🎨 Image Watermarker"),
    ("file_converter", "🔄 File Converter"),
    ("audio_editor", "🎵 Audio Editor"),
    ("video_trimmer", "✂️ Video Trimmer"),
    ("media_info", "ℹ️ Media Info"),
    ("voice_converter", "🎙️ Voice Converter"),
    ("video_note_converter", "⭕ Video Note"),
    ("youtube_tool", "▶️ YouTube Tool"),
    ("4k_enhancement", "📺 4K Enhancement"),
    ("batch_processing_pro", "📦 Batch Pro"),
]


def _emoji(state):
    return "✅" if state else "❌"


def _fmt(v):
    return "Unlimited" if v == -1 else v


# ── Render helpers (replace recursive self-calls) ──────────────────────


async def _render_edit_plan(callback_query: CallbackQuery, plan_name: str):
    """Build and display the plan settings view."""
    config = await db.get_public_config()
    limits = config.get("myfiles_limits", {})
    plan_lm = limits.get(plan_name, {})

    global_toggles = await db.get_feature_toggles()

    def get_features_str(plan_key):
        plan_settings = config.get(plan_key, {})
        features = plan_settings.get("features", {})
        feat_list = []

        for feat_key, label in TOOL_CHECKS:
            global_on = global_toggles.get(feat_key, True)
            plan_on = features.get(feat_key, global_on)
            if global_on and plan_on:
                feat_list.append(label)

        if features.get("priority_queue", False):
            feat_list.append("🚀 Priority Queue")
        if features.get("batch_sharing", False):
            feat_list.append("🔗 Batch Sharing")
        if features.get("xtv_pro_4gb", False):
            feat_list.append("⚡ XTV Pro 4GB Bypass")

        return "\n".join([f"  • {feat}" for feat in feat_list]) if feat_list else "  • None"

    if plan_name == "free":
        plan_emoji = "🆓"
        plan_title = "Free Plan"
        egress_mb = config.get("daily_egress_mb", 0)
        file_count = config.get("daily_file_count", 0)
        features_text = get_features_str('free_placeholder')
        price_text = ""
    else:
        plan_emoji = "🌟" if plan_name == "standard" else "💎"
        plan_title = f"{plan_name.capitalize()} Plan"
        plan_settings = config.get(f"premium_{plan_name}", {})
        egress_mb = plan_settings.get("daily_egress_mb", 0)
        file_count = plan_settings.get("daily_file_count", 0)
        features_text = get_features_str(f"premium_{plan_name}")
        price_text = (
            f"\n💵 **Price (Fiat):** `{plan_settings.get('price_string', '0 USD')}`\n"
            f"⭐ **Price (Stars):** `{plan_settings.get('stars_price', 0)}` Stars\n"
        )

    text = (
        f"⚙️ **Edit {plan_title} Settings**\n\n"
        f"> Configure the quotas, features, and prices for this tier.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{plan_emoji} **{plan_title}**\n\n"
        f"📌 Permanent Slots : `{_fmt(plan_lm.get('permanent_limit', 0))}`\n"
        f"📁 Custom Folders  : `{_fmt(plan_lm.get('folder_limit', 0))}`\n"
        f"⏳ Temp Expiration : `{_fmt(plan_lm.get('expiry_days', 0))} days`\n"
        f"📦 Daily Egress: `{_fmt(egress_mb)}` MB\n"
        f"📄 Daily Files: `{_fmt(file_count)}` files\n\n"
        f"✨ **Features:**\n"
        f"{features_text}\n"
        f"{price_text}"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [InlineKeyboardButton("📌 Edit Permanent Limit", callback_data=f"prompt_myfiles_lim_{plan_name}_permanent")],
        [InlineKeyboardButton("📁 Edit Folder Limit", callback_data=f"prompt_myfiles_lim_{plan_name}_folder")],
        [InlineKeyboardButton("⏳ Edit Expiry Days", callback_data=f"prompt_myfiles_lim_{plan_name}_expiry")]
    ]

    if plan_name == "free":
        buttons.append([InlineKeyboardButton("📦 Edit Egress Limit", callback_data="admin_daily_egress")])
        buttons.append([InlineKeyboardButton("📄 Edit File Limit", callback_data="admin_daily_files")])
    else:
        buttons.append([InlineKeyboardButton("📦 Edit Egress Limit", callback_data=f"prompt_premium_{plan_name}_egress")])
        buttons.append([InlineKeyboardButton("📄 Edit File Limit", callback_data=f"prompt_premium_{plan_name}_files")])
        buttons.append([
            InlineKeyboardButton("💵 Edit Fiat Price", callback_data=f"prompt_premium_{plan_name}_price"),
            InlineKeyboardButton("⭐ Edit Stars Price", callback_data=f"prompt_premium_{plan_name}_stars")
        ])

    buttons.append([InlineKeyboardButton("⚙️ Configure Features", callback_data=f"admin_premium_features_{plan_name}")])
    buttons.append([InlineKeyboardButton("← Back to Plan Settings", callback_data="admin_per_plan_limits")])

    try:
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except MessageNotModified:
        pass


async def _render_premium_settings(callback_query: CallbackQuery):
    """Build and display the premium settings menu."""
    config = await db.get_public_config()
    enabled = config.get("premium_system_enabled", False)
    deluxe_enabled = config.get("premium_deluxe_enabled", False)
    trial_enabled = config.get("premium_trial_enabled", False)
    trial_days = config.get("premium_trial_days", 0)

    status_emoji = "✅ ON" if enabled else "❌ OFF"
    deluxe_status_emoji = "✅ ON" if deluxe_enabled else "❌ OFF"
    trial_status_emoji = "✅ ON" if trial_enabled else "❌ OFF"

    text = (
        f"💎 **Premium Settings**\n\n"
        f"System Status: {status_emoji}\n"
        f"Deluxe Plan: {deluxe_status_emoji}\n\n"
        f"⏳ **Trial System (Standard Plan Only)**\n"
        f"Status: {trial_status_emoji}\n"
        f"Duration: `{trial_days}` days\n\n"
        "Select a setting to edit:"
    )

    buttons = [
        [InlineKeyboardButton(f"Toggle System: {status_emoji}", callback_data="admin_premium_toggle")]
    ]

    if enabled:
        buttons.append([InlineKeyboardButton(f"Toggle Deluxe Plan: {deluxe_status_emoji}", callback_data="admin_premium_deluxe_toggle")])
        buttons.append([InlineKeyboardButton(f"Toggle Trial System: {trial_status_emoji}", callback_data="admin_trial_toggle")])
        if trial_enabled:
            buttons.append([InlineKeyboardButton("⏱ Edit Trial Duration", callback_data="prompt_trial_days")])

    buttons.append([InlineKeyboardButton("← Back to Settings", callback_data="admin_access_limits")])

    try:
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except MessageNotModified:
        pass


async def _render_features_media(callback_query: CallbackQuery, plan_name: str):
    """Build and display the media tools toggle menu for a plan."""
    config = await db.get_public_config()
    plan_key = f"premium_{plan_name}"
    plan_settings = config.get(plan_key, {})
    features = plan_settings.get("features", {})
    global_toggles = await db.get_feature_toggles()

    buttons = []
    if plan_name == "free":
        for i in range(0, len(TOOL_DEFS), 2):
            row = []
            for j in range(i, min(i + 2, len(TOOL_DEFS))):
                feat_key, label = TOOL_DEFS[j]
                state = global_toggles.get(feat_key, True)
                row.append(InlineKeyboardButton(
                    f"{_emoji(state)} {label}",
                    callback_data=f"admin_toggle_{feat_key}_{plan_name}"
                ))
            buttons.append(row)
    else:
        for i in range(0, len(TOOL_DEFS), 2):
            row = []
            for j in range(i, min(i + 2, len(TOOL_DEFS))):
                feat_key, label = TOOL_DEFS[j]
                plan_state = features.get(feat_key, True)
                global_state = global_toggles.get(feat_key, True)
                effective = plan_state and global_state
                suffix = " ⛔" if not global_state else ""
                row.append(InlineKeyboardButton(
                    f"{_emoji(effective)} {label}{suffix}",
                    callback_data=f"admin_premium_feat_{plan_name}_{feat_key}"
                ))
            buttons.append(row)

    buttons.append([InlineKeyboardButton("← Back to Feature Categories", callback_data=f"admin_premium_features_{plan_name}")])

    if plan_name == "free":
        text = (
            f"🛠️ **Media Tools (Free)**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Toggle media tools for free users.\n"
            f"> These are the **global** toggles (apply to all non-premium users)."
        )
    else:
        text = (
            f"🛠️ **Media Tools ({plan_name.capitalize()})**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Toggle media tools for this plan.\n"
            f"> ⛔ = Globally disabled (enable in Feature Toggles first)\n"
            f"> Per-plan toggles control access within this tier."
        )

    try:
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except MessageNotModified:
        pass


async def _render_features_perks(callback_query: CallbackQuery, plan_name: str):
    """Build and display the account perks toggle menu for a plan."""
    config = await db.get_public_config()
    plan_key = f"premium_{plan_name}"
    plan_settings = config.get(plan_key, {})
    features = plan_settings.get("features", {})

    pq = features.get("priority_queue", False)
    bs = features.get("batch_sharing", False)
    access_4gb = features.get("xtv_pro_4gb", False)

    buttons = [
        [InlineKeyboardButton(f"{_emoji(access_4gb)} 🚀 4GB Access", callback_data=f"admin_premium_feat_{plan_name}_xtv_pro_4gb")],
        [InlineKeyboardButton(f"{_emoji(pq)} ⚡ Priority Queue", callback_data=f"admin_premium_feat_{plan_name}_priority_queue"),
         InlineKeyboardButton(f"{_emoji(bs)} 📦 Batch Sharing", callback_data=f"admin_premium_feat_{plan_name}_batch_sharing")],
        [InlineKeyboardButton("← Back to Feature Categories", callback_data=f"admin_premium_features_{plan_name}")]
    ]

    text = f"🌟 **Account Perks ({plan_name.capitalize()})**\n\nConfigure account perks for this tier:"

    try:
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except MessageNotModified:
        pass


async def _render_privacy_menu(callback_query: CallbackQuery, plan_name: str):
    """Build and display the privacy settings menu for a plan."""
    config = await db.get_public_config()
    plan_key = f"premium_{plan_name}"
    plan_settings = config.get(plan_key, {})
    features = plan_settings.get("features", {})
    privacy = features.get("privacy", {})

    ps = features.get("privacy_settings", False)

    buttons = [
        [InlineKeyboardButton(f"{_emoji(ps)} 🔒 Enable Privacy Settings", callback_data=f"admin_premium_feat_{plan_name}_privacy_settings")],
    ]

    if ps:
        hdn = privacy.get('hide_display_name', False)
        hft = privacy.get('hide_forward_tags', False)
        la = privacy.get('link_anonymity', False)
        hu = privacy.get('hide_username', False)
        ael = privacy.get('auto_expire_links', False)

        buttons.extend([
            [InlineKeyboardButton("━━━ 🔒 Available Controls ━━━", callback_data="noop")],
            [InlineKeyboardButton(f"{_emoji(hdn)} 👤 Hide Display Name", callback_data=f"admin_privacy_toggle_{plan_name}_hide_display_name")],
            [InlineKeyboardButton(f"{_emoji(hft)} 🏷️ Hide Forward Tags", callback_data=f"admin_privacy_toggle_{plan_name}_hide_forward_tags")],
            [InlineKeyboardButton(f"{_emoji(la)} 🔗 Link Anonymity (UUID)", callback_data=f"admin_privacy_toggle_{plan_name}_link_anonymity")],
            [InlineKeyboardButton(f"{_emoji(hu)} 🙈 Hide Username", callback_data=f"admin_privacy_toggle_{plan_name}_hide_username")],
            [InlineKeyboardButton(f"{_emoji(ael)} ⏳ Auto-Expire Links", callback_data=f"admin_privacy_toggle_{plan_name}_auto_expire_links")],
        ])

    buttons.append([InlineKeyboardButton("← Back to Feature Categories", callback_data=f"admin_premium_features_{plan_name}")])

    text = (
        f"🔒 **Privacy Settings ({plan_name.capitalize()})**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Toggle which privacy controls are **available** for users on this plan to configure in their /settings:\n\n"
    )
    if ps:
        text += (
            f"> 👤 **Hide Display Name:** {'Enabled' if privacy.get('hide_display_name', False) else 'Disabled'}\n"
            f"> __Users can hide their name on shared files__\n"
            f"> 🏷️ **Hide Forward Tags:** {'Enabled' if privacy.get('hide_forward_tags', False) else 'Disabled'}\n"
            f"> __Remove 'Forwarded from' on shares__\n"
            f"> 🔗 **Link Anonymity:** {'Enabled' if privacy.get('link_anonymity', False) else 'Disabled'}\n"
            f"> __Use anonymous hash in share links__\n"
            f"> 🙈 **Hide Username:** {'Enabled' if privacy.get('hide_username', False) else 'Disabled'}\n"
            f"> __Hide username on shared content__\n"
            f"> ⏳ **Auto-Expire Links:** {'Enabled' if privacy.get('auto_expire_links', False) else 'Disabled'}\n"
            f"> __Share links expire automatically__\n"
        )
    else:
        text += "> ⚠️ __Privacy settings are disabled for this plan.__\n"

    try:
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except MessageNotModified:
        pass


# ── Handler ────────────────────────────────────────────────────────────


@Client.on_callback_query(
    filters.regex(
        r"^(admin_edit_plan_|admin_toggle_"
        r"|admin_premium_|admin_trial_|admin_features_|admin_privacy_"
        r"|admin_daily_|prompt_premium_|prompt_trial_"
        r"|prompt_global_daily_egress$|prompt_prem_egress_custom_"
        r"|set_prem_egress_|admin_prem_cur_|set_daily_egress_"
        r"|prompt_daily_)"
    )
)
async def premium_cb(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    await callback_query.answer()
    data = callback_query.data

    # --- Edit plan settings ---
    if data.startswith("admin_edit_plan_"):
        plan_name = data.replace("admin_edit_plan_", "")
        await _render_edit_plan(callback_query, plan_name)
        return

    # --- Per-plan free toggles: admin_toggle_{feature}_{plan} ---
    if data.startswith("admin_toggle_"):
        suffix = data.replace("admin_toggle_", "")
        plan_name = None
        for plan_suffix in ("_free", "_standard", "_deluxe"):
            if suffix.endswith(plan_suffix):
                plan_name = plan_suffix.lstrip("_")
                feature = suffix[: -len(plan_suffix)]
                break
        if plan_name is None:
            feature = suffix
            plan_name = "free"

        toggles = await db.get_feature_toggles()
        current_state = toggles.get(feature, True)
        new_state = not current_state
        await db.update_feature_toggle(feature, new_state)
        await callback_query.answer(
            f"{'Enabled' if new_state else 'Disabled'} {feature.replace('_', ' ').title()}.",
            show_alert=True,
        )
        await _render_features_media(callback_query, plan_name)
        return

    # --- Premium settings menu ---
    if data == "admin_premium_settings":
        if not Config.PUBLIC_MODE:
            return
        await _render_premium_settings(callback_query)
        return

    # --- Toggle premium system ---
    if data == "admin_premium_toggle":
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        enabled = config.get("premium_system_enabled", False)
        await db.update_public_config("premium_system_enabled", not enabled)
        await callback_query.answer("Toggled Premium System", show_alert=True)
        await _render_premium_settings(callback_query)
        return

    # --- Toggle trial system ---
    if data == "admin_trial_toggle":
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        enabled = config.get("premium_trial_enabled", False)
        await db.update_public_config("premium_trial_enabled", not enabled)
        await callback_query.answer("Toggled Premium Trial System", show_alert=True)
        await _render_premium_settings(callback_query)
        return

    # --- Toggle deluxe plan ---
    if data == "admin_premium_deluxe_toggle":
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        enabled = config.get("premium_deluxe_enabled", False)
        await db.update_public_config("premium_deluxe_enabled", not enabled)
        await callback_query.answer("Toggled Premium Deluxe System", show_alert=True)
        await _render_premium_settings(callback_query)
        return

    # --- Feature categories menu ---
    if data.startswith("admin_premium_features_"):
        if not Config.PUBLIC_MODE:
            return
        plan_name = data.replace("admin_premium_features_", "")

        buttons = [
            [InlineKeyboardButton("🌟 Account Perks", callback_data=f"admin_features_perks_{plan_name}")],
            [InlineKeyboardButton("🛠️ Media Tools", callback_data=f"admin_features_media_{plan_name}")],
            [InlineKeyboardButton("🔒 Privacy Settings", callback_data=f"admin_features_privacy_{plan_name}")],
            [InlineKeyboardButton("📁 MyFiles Limits", callback_data=f"admin_edit_plan_{plan_name}")],
            [InlineKeyboardButton("← Back to Plan Settings", callback_data=f"admin_edit_plan_{plan_name}")]
        ]

        if plan_name == "free":
            text = (
                "⚙️ **Free Plan Features**\n\n"
                "Select a category to configure features for this plan.\n"
                "> __Free plan media tools use the global toggles.__\n"
                "> __Per-plan overrides are available for premium tiers.__"
            )
        else:
            text = (
                f"⚙️ **{plan_name.capitalize()} Plan Features**\n\n"
                "Select a category to configure features for this plan.\n"
                "> Each tool can be individually enabled or disabled."
            )

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    # --- Account perks ---
    if data.startswith("admin_features_perks_"):
        if not Config.PUBLIC_MODE:
            return
        plan_name = data.replace("admin_features_perks_", "")
        await _render_features_perks(callback_query, plan_name)
        return

    # --- Media tools ---
    if data.startswith("admin_features_media_"):
        if not Config.PUBLIC_MODE:
            return
        plan_name = data.replace("admin_features_media_", "")
        await _render_features_media(callback_query, plan_name)
        return

    # --- Privacy routing ---
    if data.startswith("admin_features_privacy_"):
        if not Config.PUBLIC_MODE:
            return
        plan_name = data.replace("admin_features_privacy_", "")
        await _render_privacy_menu(callback_query, plan_name)
        return

    # --- Toggle individual feature ---
    if data.startswith("admin_premium_feat_"):
        if not Config.PUBLIC_MODE:
            return
        parts = data.replace("admin_premium_feat_", "").split("_", 1)
        plan_name = parts[0]
        feature_name = parts[1]

        config = await db.get_public_config()
        plan_key = f"premium_{plan_name}"
        plan_settings = config.get(plan_key, {})
        features = plan_settings.get("features", {})

        current = features.get(feature_name, False)
        features[feature_name] = not current
        plan_settings["features"] = features

        await db.update_public_config(plan_key, plan_settings)

        # Deep routing to stay inside the appropriate sub-menu
        if feature_name in ["xtv_pro_4gb", "priority_queue", "batch_sharing"]:
            await _render_features_perks(callback_query, plan_name)
        elif feature_name == "privacy_settings":
            await _render_privacy_menu(callback_query, plan_name)
        else:
            await _render_features_media(callback_query, plan_name)
        return

    # --- Privacy menu ---
    if data.startswith("admin_privacy_menu_"):
        if not Config.PUBLIC_MODE:
            return
        plan_name = data.replace("admin_privacy_menu_", "")
        await _render_privacy_menu(callback_query, plan_name)
        return

    # --- Privacy toggle ---
    if data.startswith("admin_privacy_toggle_"):
        if not Config.PUBLIC_MODE:
            return
        parts = data.replace("admin_privacy_toggle_", "").split("_", 1)
        plan_name = parts[0]
        feature_name = parts[1]

        config = await db.get_public_config()
        plan_key = f"premium_{plan_name}"
        plan_settings = config.get(plan_key, {})
        features = plan_settings.get("features", {})
        privacy = features.get("privacy", {})

        current = privacy.get(feature_name, False)
        privacy[feature_name] = not current
        features["privacy"] = privacy
        plan_settings["features"] = features

        await db.update_public_config(plan_key, plan_settings)

        await _render_privacy_menu(callback_query, plan_name)
        return

    # --- Premium prompts (egress, price, files, stars) ---
    if data.startswith("prompt_premium_"):
        if not Config.PUBLIC_MODE:
            return
        parts = data.replace("prompt_premium_", "").split("_")
        if len(parts) >= 2 and parts[0] in ["standard", "deluxe"]:
            plan_name = parts[0]
            field = parts[1]

            if field == "egress":
                try:
                    await callback_query.message.edit_text(
                        f"📦 **Edit Daily Egress Limit** ({plan_name.capitalize()} Plan)\n\n"
                        f"Select a predefined size or click **Change Custom** to enter a value manually (e.g. `20 GB` or `512 MB`):",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("512 MB", callback_data=f"set_prem_egress_{plan_name}_512"),
                             InlineKeyboardButton("1 GB", callback_data=f"set_prem_egress_{plan_name}_1024")],
                            [InlineKeyboardButton("2 GB", callback_data=f"set_prem_egress_{plan_name}_2048"),
                             InlineKeyboardButton("4 GB", callback_data=f"set_prem_egress_{plan_name}_4096")],
                            [InlineKeyboardButton("✏️ Change Custom", callback_data=f"prompt_prem_egress_custom_{plan_name}")],
                            [InlineKeyboardButton("← Back to Plan Settings", callback_data=f"admin_edit_plan_{plan_name}")],
                        ]),
                    )
                except MessageNotModified:
                    pass
                return

            if field == "price":
                try:
                    await callback_query.message.edit_text(
                        "💵 **Select Currency**\n\nFirst, select the fiat currency you want to use for this plan:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("USD ($)", callback_data=f"admin_prem_cur_{plan_name}_USD"),
                             InlineKeyboardButton("EUR (€)", callback_data=f"admin_prem_cur_{plan_name}_EUR"),
                             InlineKeyboardButton("GBP (£)", callback_data=f"admin_prem_cur_{plan_name}_GBP")],
                            [InlineKeyboardButton("INR (₹)", callback_data=f"admin_prem_cur_{plan_name}_INR"),
                             InlineKeyboardButton("RUB (₽)", callback_data=f"admin_prem_cur_{plan_name}_RUB"),
                             InlineKeyboardButton("BRL (R$)", callback_data=f"admin_prem_cur_{plan_name}_BRL")],
                            [InlineKeyboardButton("← Back to Plan Settings", callback_data=f"admin_edit_plan_{plan_name}")]
                        ])
                    )
                except MessageNotModified:
                    pass
                return

            admin_sessions[user_id] = {
                "state": f"awaiting_premium_{plan_name}_{field}",
                "msg_id": callback_query.message.id,
            }

            prompts = {
                "files": "📄 **Send the new daily file limit.**\nSend `0` to disable.",
            }

            if field == "stars":
                from utils.currency import convert_to_usd_str
                config = await db.get_public_config()
                plan_settings = config.get(f"premium_{plan_name}", {})
                current_fiat = plan_settings.get("price_string", "0 USD")
                usd_str = await convert_to_usd_str(current_fiat)

                try:
                    usd_val = float(usd_str.replace("$", ""))
                    recommended_stars = int(usd_val / 0.015)
                    star_prompt = (
                        f"⭐ **Send the new Telegram Stars price (integer).**\n\n"
                        f"Your fiat price converts to roughly `{usd_str}`.\n"
                        f"We recommend setting this to `{recommended_stars}` Stars (assuming ~$0.015 per Star)."
                    )
                except (ValueError, TypeError):
                    star_prompt = "⭐ **Send the new Telegram Stars price (integer).**"

                prompts["stars"] = star_prompt

            cancel_cb = f"admin_edit_plan_{plan_name}"

            try:
                await callback_query.message.edit_text(
                    prompts.get(field, "Enter new value:"),
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data=cancel_cb)]]
                    ),
                )
            except MessageNotModified:
                pass
            return

    # --- Custom egress prompt ---
    if data.startswith("prompt_prem_egress_custom_"):
        plan_name = data.replace("prompt_prem_egress_custom_", "")
        admin_sessions[user_id] = {
            "state": f"awaiting_premium_{plan_name}_egress",
            "msg_id": callback_query.message.id,
        }
        try:
            await callback_query.message.edit_text(
                "📦 **Send the new daily egress limit.**\n\n"
                "You can send the value in MB (e.g., `2048`) or use `GB` format (e.g., `2 GB` or `5.5 GB`).\n"
                "Send `0` to disable.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_edit_plan_{plan_name}")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Set premium egress preset ---
    if data.startswith("set_prem_egress_"):
        parts = data.replace("set_prem_egress_", "").split("_")
        if len(parts) >= 2:
            plan_name = parts[0]
            val = int(parts[1])

            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            plan_settings["daily_egress_mb"] = val
            await db.update_public_config(plan_key, plan_settings)

            await callback_query.answer(
                f"{plan_name.capitalize()} Egress limit updated to {val} MB.",
                show_alert=True,
            )
            await _render_edit_plan(callback_query, plan_name)
        return

    # --- Currency selection ---
    if data.startswith("admin_prem_cur_"):
        parts = data.replace("admin_prem_cur_", "").split("_")
        plan_name = parts[0]
        currency = parts[1]

        admin_sessions[user_id] = {
            "state": f"awaiting_premium_{plan_name}_price",
            "currency": currency,
            "msg_id": callback_query.message.id,
        }

        try:
            await callback_query.message.edit_text(
                f"💵 **Set Price in {currency}**\n\nPlease enter the numeric amount (e.g., `9.99` or `500`):",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Trial duration prompt ---
    if data == "prompt_trial_days":
        admin_sessions[user_id] = {
            "state": "awaiting_trial_days",
            "msg_id": callback_query.message.id,
        }
        try:
            await callback_query.message.edit_text(
                "⏱ **Send the new PREMIUM TRIAL duration in days (e.g., 7).**\nSend `0` to disable.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_premium_settings")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Global daily egress prompt ---
    if data == "prompt_global_daily_egress":
        admin_sessions[user_id] = {
            "state": "awaiting_global_daily_egress",
            "msg_id": callback_query.message.id,
        }
        try:
            await callback_query.message.edit_text(
                "🌍 **Send the new global daily egress limit in MB (e.g., 102400 for 100GB).**\nSend `0` to disable.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_access_limits")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Daily egress (free plan) ---
    if data == "admin_daily_egress":
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        current_val = config.get("daily_egress_mb", 0)
        try:
            await callback_query.message.edit_text(
                f"📦 **Edit Daily Egress Limit** (Free Plan)\n\n"
                f"Current: `{current_val}` MB\n\n"
                f"Select a predefined size or click **Change Custom** to enter a value manually (e.g. `20 GB` or `512 MB`):",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("512 MB", callback_data="set_daily_egress_512"),
                     InlineKeyboardButton("1 GB", callback_data="set_daily_egress_1024")],
                    [InlineKeyboardButton("2 GB", callback_data="set_daily_egress_2048"),
                     InlineKeyboardButton("4 GB", callback_data="set_daily_egress_4096")],
                    [InlineKeyboardButton("✏️ Change Custom", callback_data="prompt_daily_egress")],
                    [InlineKeyboardButton("← Back to Plan Settings", callback_data="admin_edit_plan_free")],
                ]),
            )
        except MessageNotModified:
            pass
        return

    # --- Set daily egress preset (free plan) ---
    if data.startswith("set_daily_egress_"):
        if not Config.PUBLIC_MODE:
            return
        val = int(data.replace("set_daily_egress_", ""))
        await db.update_public_config("daily_egress_mb", val)
        await callback_query.answer(f"Egress limit updated to {val} MB.", show_alert=True)
        await _render_edit_plan(callback_query, "free")
        return

    # --- Daily file limit (free plan) ---
    if data == "admin_daily_files":
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        current_val = config.get("daily_file_count", 0)
        try:
            await callback_query.message.edit_text(
                f"📄 **Edit Daily File Limit** (Free Plan)\n\nCurrent: `{current_val}` files\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change", callback_data="prompt_daily_files")],
                    [InlineKeyboardButton("← Back to Plan Settings", callback_data="admin_edit_plan_free")],
                ]),
            )
        except MessageNotModified:
            pass
        return

    # --- Prompt daily egress/files (free plan text input setup) ---
    if data.startswith("prompt_daily_"):
        if not Config.PUBLIC_MODE:
            return
        field = data.replace("prompt_daily_", "daily_")
        admin_sessions[user_id] = {
            "state": f"awaiting_public_{field}",
            "msg_id": callback_query.message.id,
        }

        if field == "daily_egress":
            text = (
                "📦 **Send the new daily egress limit.**\n\n"
                "You can send the value in MB (e.g., `2048`) or use `GB` format (e.g., `2 GB` or `5.5 GB`).\n"
                "Send `0` to disable."
            )
        elif field == "daily_files":
            text = "📄 **Send the new daily file limit.**\nSend `0` to disable."
        else:
            text = "Send the new value:"
        cancel_btn = "admin_edit_plan_free"

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data=cancel_btn)]]
                ),
            )
        except MessageNotModified:
            pass
        return


# ---------------------------------------------------------------------------
# Text-input state handlers (registered with text_dispatcher)
# ---------------------------------------------------------------------------
async def _handle_global_daily_egress(client, message, state, state_obj, msg_id):
    """Handle awaiting_global_daily_egress state."""
    user_id = message.from_user.id
    val = message.text.strip() if message.text else ""
    if not val.isdigit():
        await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="admin_access_limits")]]
            ),
        )
        return
    await db.update_global_daily_egress_limit(float(val))
    await edit_or_reply(client, message, msg_id,
        f"✅ Global daily egress limit updated to `{val}` MB.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back to Settings", callback_data="admin_access_limits")]]
        ),
    )
    admin_sessions.pop(user_id, None)


async def _handle_premium_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_premium_* states (string and dict variants)."""
    user_id = message.from_user.id

    # Dict state variant (state_obj is dict with extra fields like currency)
    if isinstance(state_obj, dict) and isinstance(state, str) and state.startswith("awaiting_premium_"):
        parts = state.replace("awaiting_premium_", "").split("_")
        if len(parts) >= 2 and parts[0] in ["standard", "deluxe"]:
            plan_name = parts[0]
            field = parts[1]
            val = message.text.strip() if message.text else ""

            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})

            if field == "price":
                try:
                    float_val = float(val.replace(",", "."))
                except ValueError:
                    await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_edit_plan_{plan_name}")]])
                    )
                    return
                currency = state_obj.get("currency", "USD")
                formatted_price = f"{float_val:g} {currency}"
                plan_settings["price_string"] = formatted_price
                await db.update_public_config(plan_key, plan_settings)
                await edit_or_reply(client, message, msg_id,
                    f"✅ {plan_name.capitalize()} fiat price updated to `{formatted_price}`.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Plan Settings", callback_data=f"admin_edit_plan_{plan_name}")]])
                )
                admin_sessions.pop(user_id, None)
                return

            if field in ["egress", "files", "stars"]:
                val_num = 0
                if field == "egress":
                    val_lower = val.lower().strip()
                    if "gb" in val_lower:
                        try:
                            gb_val = float(val_lower.replace("gb", "").strip())
                            val_num = int(gb_val * 1024)
                        except ValueError:
                            await edit_or_reply(client, message, msg_id, "❌ Invalid GB format. Please use something like `2 GB`.",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_edit_plan_{plan_name}")]])
                            )
                            return
                    else:
                        try:
                            val_num = int(float(val_lower.replace("mb", "").strip()))
                        except ValueError:
                            await edit_or_reply(client, message, msg_id, "❌ Invalid number format. Try again.",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_edit_plan_{plan_name}")]])
                            )
                            return
                    plan_settings["daily_egress_mb"] = val_num
                elif field == "files":
                    if not val.isdigit():
                        await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
                        )
                        return
                    val_num = int(val)
                    plan_settings["daily_file_count"] = val_num
                elif field == "stars":
                    if not val.isdigit():
                        await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
                        )
                        return
                    val_num = int(val)
                    plan_settings["stars_price"] = val_num

                await db.update_public_config(plan_key, plan_settings)
                await edit_or_reply(client, message, msg_id,
                    f"✅ **Success!**\n\nThe {field.capitalize()} Limit for the **{plan_name.capitalize()} Plan** has been successfully updated to **{val_num}**.\n\nChanges have been saved and applied globally.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=f"admin_edit_plan_{plan_name}")]])
                )
                admin_sessions.pop(user_id, None)
                return


async def _handle_trial_days(client, message, state, state_obj, msg_id):
    """Handle awaiting_trial_days state."""
    user_id = message.from_user.id
    val = message.text.strip() if message.text else ""
    if not val.isdigit():
        await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_premium_settings")]])
        )
        return
    await db.update_public_config("premium_trial_days", int(val))
    await edit_or_reply(client, message, msg_id,
        f"✅ Premium trial duration updated to `{val}` days.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Premium Settings", callback_data="admin_premium_settings")]])
    )
    admin_sessions.pop(user_id, None)


from plugins.admin.text_dispatcher import register as _register
_register("awaiting_global_daily_egress", _handle_global_daily_egress)
_register("awaiting_premium_", _handle_premium_text)
_register("awaiting_trial_days", _handle_trial_days)
