# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Payments admin domain.

Covers the Manage Payments submenu: payment method settings (PayPal, UPI,
Crypto, Telegram Stars), crypto address editing, discount settings,
pending approval queue, and approve/reject flows.

Text-input flows (`awaiting_pay_*`) are registered with the shared
``text_dispatcher`` and routed here at runtime.
"""

import contextlib

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from database import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin


async def _render_pay_settings(client, callback_query: CallbackQuery):
    """Build and display the payment settings menu."""
    config = await db.get_public_config()
    pm = config.get("payment_methods", {})

    def emoji(state):
        return "✅" if state else "❌"

    pp = pm.get("paypal_enabled", False)
    cr = pm.get("crypto_enabled", False)
    up = pm.get("upi_enabled", False)
    st = pm.get("stars_enabled", False)

    usdt = pm.get("crypto_usdt", "Not set")
    btc = pm.get("crypto_btc", "Not set")
    eth = pm.get("crypto_eth", "Not set")

    text = (
        "⚙️ **Payment Settings**\n\n"
        "Toggle payment methods and configure their respective addresses/IDs.\n"
        "__(Users will only see the enabled methods during checkout)__\n\n"
        f"**PayPal Email:** `{pm.get('paypal_email', 'Not set')}`\n"
        f"**UPI ID:** `{pm.get('upi_id', 'Not set')}`\n\n"
        f"**Crypto Addresses:**\n"
        f"• USDT: `{usdt}`\n"
        f"• BTC: `{btc}`\n"
        f"• ETH: `{eth}`"
    )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{emoji(pp)} PayPal", callback_data="admin_pay_toggle_paypal"),
                 InlineKeyboardButton("✏️ Edit Email", callback_data="prompt_pay_paypal")],
                [InlineKeyboardButton(f"{emoji(up)} UPI", callback_data="admin_pay_toggle_upi"),
                 InlineKeyboardButton("✏️ Edit ID", callback_data="prompt_pay_upi")],
                [InlineKeyboardButton(f"{emoji(cr)} Crypto", callback_data="admin_pay_toggle_crypto"),
                 InlineKeyboardButton("✏️ Edit Addresses", callback_data="admin_pay_crypto_menu")],
                [InlineKeyboardButton(f"{emoji(st)} Telegram Stars", callback_data="admin_pay_toggle_stars")],
                [InlineKeyboardButton("← Back to Payments", callback_data="admin_payments_menu")]
            ])
        )


async def _render_pay_queue(client, callback_query: CallbackQuery):
    """Build and display the pending approvals queue."""
    pending = await db.get_all_pending_payments()
    if not pending:
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📬 **Pending Approvals Queue**\n\nNo pending payments found.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Payments", callback_data="admin_payments_menu")]]
                ),
            )
        return

    p = pending[0]
    text = (
        "📬 **Pending Approvals Queue**\n\n"
        f"**Payment ID:** `{p['_id']}`\n"
        f"**User ID:** `{p['user_id']}`\n"
        f"**Plan:** `{p['plan'].capitalize()}`\n"
        f"**Duration:** `{p['duration_months']} Months`\n"
        f"**Amount:** `{p['amount']}`\n"
        f"**Method:** `{p['method']}`\n\n"
        "Review this transaction and approve or reject it."
    )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Approve", callback_data=f"admin_pay_approve_{p['_id']}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"admin_pay_reject_{p['_id']}")],
                [InlineKeyboardButton("⏭ Skip", callback_data="admin_pay_queue")],
                [InlineKeyboardButton("← Back to Payments", callback_data="admin_payments_menu")]
            ])
        )


@Client.on_callback_query(
    filters.regex(r"^(admin_payments_menu$|admin_pay_|prompt_pay_)")
)
async def payments_cb(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    await callback_query.answer()
    data = callback_query.data

    # --- Payments menu ---
    if data == "admin_payments_menu":
        config = await db.get_public_config()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "💳 **Manage Payments**\n\nManage payment methods, discounts, and view pending transactions.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Payment Settings", callback_data="admin_pay_settings")],
                    [InlineKeyboardButton("📉 Discount Settings", callback_data="admin_pay_discounts")],
                    [InlineKeyboardButton("📬 Pending Approvals Queue", callback_data="admin_pay_queue")],
                    [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")]
                ])
            )
        return

    # --- Payment settings ---
    if data == "admin_pay_settings":
        await _render_pay_settings(client, callback_query)
        return

    # --- Crypto menu ---
    if data == "admin_pay_crypto_menu":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "🪙 **Crypto Address Settings**\n\nSelect which cryptocurrency address you want to edit:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("USDT (TRC20/ERC20)", callback_data="prompt_pay_crypto_usdt")],
                    [InlineKeyboardButton("BTC (Bitcoin)", callback_data="prompt_pay_crypto_btc")],
                    [InlineKeyboardButton("ETH (Ethereum)", callback_data="prompt_pay_crypto_eth")],
                    [InlineKeyboardButton("← Back to Payment Settings", callback_data="admin_pay_settings")]
                ])
            )
        return

    # --- Toggle payment method ---
    if data.startswith("admin_pay_toggle_"):
        method = data.replace("admin_pay_toggle_", "")
        config = await db.get_public_config()
        pm = config.get("payment_methods", {})
        current = pm.get(f"{method}_enabled", False)
        pm[f"{method}_enabled"] = not current
        await db.update_public_config("payment_methods", pm)
        await _render_pay_settings(client, callback_query)
        return

    # --- Prompt for payment method details ---
    if data.startswith("prompt_pay_"):
        method = data.replace("prompt_pay_", "")

        # Discount prompts are handled separately below
        if method.startswith("disc_"):
            months = method.replace("disc_", "")
            admin_sessions[user_id] = {
                "state": f"awaiting_pay_disc_{months}",
                "msg_id": callback_query.message.id,
            }
            with contextlib.suppress(MessageNotModified):
                await callback_query.message.edit_text(
                    f"📉 **Edit {months}-Month Discount**\n\nPlease send the new discount percentage (e.g. `10` or `15`):",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data="admin_pay_discounts")]]
                    ),
                )
            return

        # Payment method address/ID/email prompts
        admin_sessions[user_id] = {
            "state": f"awaiting_pay_{method}",
            "msg_id": callback_query.message.id,
        }

        cancel_data = "admin_pay_settings"
        if method.startswith("crypto_"):
            cancel_data = "admin_pay_crypto_menu"

        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Edit {method.replace('_', ' ').upper()} Details**\n\nPlease send the new address/ID/email:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)]]
                ),
            )
        return

    # --- Discount settings ---
    if data == "admin_pay_discounts":
        config = await db.get_public_config()
        disc = config.get("discounts", {})
        m3 = disc.get("months_3", 0)
        m12 = disc.get("months_12", 0)

        text = (
            "📉 **Discount Settings**\n\n"
            "Set the percentage discount (0-99) for longer billing cycles.\n\n"
            f"**3 Months:** `{m3}% Off`\n"
            f"**12 Months:** `{m12}% Off`\n"
        )

        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Edit 3-Month Discount", callback_data="prompt_pay_disc_3")],
                    [InlineKeyboardButton("✏️ Edit 12-Month Discount", callback_data="prompt_pay_disc_12")],
                    [InlineKeyboardButton("← Back to Payments", callback_data="admin_payments_menu")]
                ])
            )
        return

    # --- Pending approvals queue ---
    if data == "admin_pay_queue":
        await _render_pay_queue(client, callback_query)
        return

    # --- Approve payment ---
    if data.startswith("admin_pay_approve_"):
        payment_id = data.replace("admin_pay_approve_", "")
        p = await db.get_pending_payment(payment_id)
        if not p or p['status'] != 'pending':
            await callback_query.answer("Payment already processed.", show_alert=True)
        else:
            await db.update_pending_payment_status(payment_id, "approved")
            days = p['duration_months'] * 30
            await db.add_premium_user(p['user_id'], days, plan=p['plan'])
            await db.add_log("approve_payment", user_id, f"Approved {payment_id} for user {p['user_id']}")

            with contextlib.suppress(Exception):
                await client.send_message(
                    p['user_id'],
                    f"✅ **Payment Approved!**\n\nYour payment for the **Premium {p['plan'].capitalize()} Plan** ({p['duration_months']} Months) has been verified.\nYour account is now upgraded. Enjoy!"
                )

            await callback_query.answer("Payment Approved & User Upgraded!", show_alert=True)

        await _render_pay_queue(client, callback_query)
        return

    # --- Reject payment ---
    if data.startswith("admin_pay_reject_"):
        payment_id = data.replace("admin_pay_reject_", "")
        p = await db.get_pending_payment(payment_id)
        if not p or p['status'] != 'pending':
            await callback_query.answer("Payment already processed.", show_alert=True)
        else:
            await db.update_pending_payment_status(payment_id, "rejected")
            await db.add_log("reject_payment", user_id, f"Rejected {payment_id} for user {p['user_id']}")

            with contextlib.suppress(Exception):
                await client.send_message(
                    p['user_id'],
                    f"❌ **Payment Rejected**\n\nYour payment (ID: `{payment_id}`) for the Premium {p['plan'].capitalize()} Plan could not be verified. Please contact support."
                )

            await callback_query.answer("Payment Rejected.", show_alert=True)

        await _render_pay_queue(client, callback_query)
        return


# ---------------------------------------------------------------------------
# Text-input state handler (registered with text_dispatcher)
# ---------------------------------------------------------------------------
async def handle_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_pay_* states (discounts + payment method details)."""
    from pyrogram import ContinuePropagation

    user_id = message.from_user.id
    val = message.text.strip() if message.text else ""
    if not val:
        raise ContinuePropagation

    if state.startswith("awaiting_pay_disc_"):
        months = state.replace("awaiting_pay_disc_", "")
        if not val.isdigit() or not (0 <= int(val) <= 99):
            await edit_or_reply(client, message, msg_id,
                "❌ Invalid discount percentage. Must be a number between 0 and 99.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_pay_discounts")]])
            )
            return

        config = await db.get_public_config()
        disc = config.get("discounts", {})
        disc[f"months_{months}"] = int(val)
        await db.update_public_config("discounts", disc)

        await edit_or_reply(client, message, msg_id,
            f"✅ {months}-Month discount updated to `{val}%`.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Discounts", callback_data="admin_pay_discounts")]])
        )
        admin_sessions.pop(user_id, None)
        return

    # Payment method address/ID/email
    method = state.replace("awaiting_pay_", "")
    config = await db.get_public_config()
    pm = config.get("payment_methods", {})

    if method == "paypal":
        pm["paypal_email"] = val
    elif method == "upi":
        pm["upi_id"] = val
    elif method == "crypto_usdt":
        pm["crypto_usdt"] = val
    elif method == "crypto_btc":
        pm["crypto_btc"] = val
    elif method == "crypto_eth":
        pm["crypto_eth"] = val

    await db.update_public_config("payment_methods", pm)

    back_data = "admin_pay_settings"
    if method.startswith("crypto_"):
        back_data = "admin_pay_crypto_menu"

    await edit_or_reply(client, message, msg_id,
        f"✅ {method.replace('_', ' ').upper()} details updated to `{val}`.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=back_data)]])
    )
    admin_sessions.pop(user_id, None)


from plugins.admin.text_dispatcher import register as _register

_register("awaiting_pay_", handle_text)
