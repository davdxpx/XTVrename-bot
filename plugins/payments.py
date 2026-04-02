from pyrogram import Client, filters
from pyrogram.raw.types import LabeledPrice
from config import Config
from database import db
from utils.log import get_logger

logger = get_logger("plugins.payments")

def is_public_mode():
    return Config.PUBLIC_MODE

import uuid
import re
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@Client.on_callback_query(filters.regex(r"^buy_premium_dur_(standard|deluxe)$"))
async def handle_buy_premium_dur(client, callback_query):
    if not is_public_mode():
        return

    plan = callback_query.matches[0].group(1)
    config = await db.get_public_config()

    plan_key = f"premium_{plan}"
    plan_settings = config.get(plan_key, {})
    price_string = plan_settings.get("price_string", "0 USD")

    from utils.currency import convert_to_usd_str

    match = re.search(r"([\d\.]+)\s*([A-Z]+|\$|€|£|₹|₽)?", price_string.upper())
    if not match:
        await callback_query.answer("Pricing is misconfigured.", show_alert=True)
        return

    base_price = float(match.group(1))
    currency = match.group(2) or "USD"

    discounts = config.get("discounts", {})
    d3 = discounts.get("months_3", 0)
    d12 = discounts.get("months_12", 0)

    def calc_price(months, discount):
        total = base_price * months
        if discount > 0:
            total = total * (1 - (discount / 100.0))
        return f"{total:g} {currency}"

    p1_raw = f"{base_price:g} {currency}"
    p3_raw = calc_price(3, d3)
    p12_raw = calc_price(12, d12)

    p1 = await convert_to_usd_str(p1_raw)
    p3 = await convert_to_usd_str(p3_raw)
    p12 = await convert_to_usd_str(p12_raw)

    text = (
        f"🛒 **Select Billing Cycle ({plan.capitalize()})**\n\n"
        f"Choose how long you want to subscribe. Longer cycles offer better value!\n\n"
    )

    if d3 > 0:
        text += f"**3 Months:** `{p3}` (Save {d3}%!)\n"
    else:
        text += f"**3 Months:** `{p3}`\n"

    if d12 > 0:
        text += f"**12 Months:** `{p12}` (Save {d12}%!)\n"
    else:
        text += f"**12 Months:** `{p12}`\n"

    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"1 Month ({p1})", callback_data=f"buy_premium_pay_{plan}_1")],
                [InlineKeyboardButton(f"3 Months ({p3})", callback_data=f"buy_premium_pay_{plan}_3")],
                [InlineKeyboardButton(f"12 Months ({p12})", callback_data=f"buy_premium_pay_{plan}_12")],
                [InlineKeyboardButton("← Back", callback_data="user_premium_menu")]
            ])
        )
    except Exception as e:
        logger.error(e)

@Client.on_callback_query(filters.regex(r"^buy_premium_pay_(standard|deluxe)_(\d+)$"))
async def handle_buy_premium_pay(client, callback_query):
    if not is_public_mode():
        return

    plan = callback_query.matches[0].group(1)
    months = int(callback_query.matches[0].group(2))

    config = await db.get_public_config()
    pm = config.get("payment_methods", {})

    methods_available = False
    buttons = []

    if pm.get("stars_enabled", False):
        methods_available = True
        buttons.append([InlineKeyboardButton("⭐ Pay with Telegram Stars", callback_data=f"buy_stars_{plan}_{months}")])

    if pm.get("paypal_enabled", False) and pm.get("paypal_email"):
        methods_available = True
        buttons.append([InlineKeyboardButton("💳 Pay with PayPal", callback_data=f"buy_manual_{plan}_{months}_paypal")])

    has_crypto = pm.get("crypto_usdt") or pm.get("crypto_btc") or pm.get("crypto_eth")
    if pm.get("crypto_enabled", False) and has_crypto:
        methods_available = True
        buttons.append([InlineKeyboardButton("🪙 Pay with Crypto", callback_data=f"buy_manual_{plan}_{months}_crypto")])

    if pm.get("upi_enabled", False) and pm.get("upi_id"):
        methods_available = True
        buttons.append([InlineKeyboardButton("🏦 Pay with UPI", callback_data=f"buy_manual_{plan}_{months}_upi")])

    buttons.append([InlineKeyboardButton("← Back", callback_data=f"buy_premium_dur_{plan}")])

    if not methods_available:
        await callback_query.answer("No payment methods are currently available. Please contact the administrator.", show_alert=True)
        return

    text = (
        f"💳 **Select Payment Method**\n\n"
        f"Plan: **Premium {plan.capitalize()}**\n"
        f"Duration: **{months} Month(s)**\n\n"
        f"Choose your preferred payment method below:"
    )

    try:
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(e)

@Client.on_callback_query(filters.regex(r"^buy_manual_(standard|deluxe)_(\d+)_(paypal|crypto|upi)$"))
async def handle_buy_manual(client, callback_query):
    if not is_public_mode():
        return

    user_id = callback_query.from_user.id
    plan = callback_query.matches[0].group(1)
    months = int(callback_query.matches[0].group(2))
    method = callback_query.matches[0].group(3)

    config = await db.get_public_config()
    pm = config.get("payment_methods", {})

    dest = ""
    if method == "paypal":
        dest = f"`{pm.get('paypal_email', '')}`"
    elif method == "crypto":
        usdt = pm.get("crypto_usdt")
        btc = pm.get("crypto_btc")
        eth = pm.get("crypto_eth")
        dest = ""
        if usdt: dest += f"\n• USDT: `{usdt}`"
        if btc: dest += f"\n• BTC: `{btc}`"
        if eth: dest += f"\n• ETH: `{eth}`"
    elif method == "upi":
        dest = f"`{pm.get('upi_id', '')}`"

    plan_key = f"premium_{plan}"
    plan_settings = config.get(plan_key, {})
    price_string = plan_settings.get("price_string", "0 USD")

    from utils.currency import convert_to_usd_str

    match = re.search(r"([\d\.]+)\s*([A-Z]+|\$|€|£|₹|₽)?", price_string.upper())
    base_price = float(match.group(1)) if match else 0.0
    currency = (match.group(2) if match else "USD") or "USD"

    discounts = config.get("discounts", {})
    d3 = discounts.get("months_3", 0)
    d12 = discounts.get("months_12", 0)

    total = base_price * months
    if months == 3 and d3 > 0:
        total = total * (1 - (d3 / 100.0))
    elif months == 12 and d12 > 0:
        total = total * (1 - (d12 / 100.0))

    final_price_raw = f"{total:g} {currency}"
    final_price_str = await convert_to_usd_str(final_price_raw)
    payment_id = f"PAY-XTV-{str(uuid.uuid4())[:8].upper()}"

    await db.add_pending_payment(payment_id, user_id, plan, months, final_price_str, method)

    text = (
        f"📝 **Manual Payment Instructions**\n\n"
        f"**Amount Due:** `{final_price_str}`\n"
        f"**Method:** `{method.capitalize()}`\n"
        f"**Send To:**\n{dest}\n\n"
        f"⚠️ **IMPORTANT:** You MUST include this Payment ID in the transaction notes/memo:\n"
        f"`{payment_id}`\n\n"
        f"Once you have sent the money, click the button below to notify the admins."
    )

    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ I Have Paid", callback_data=f"paid_manual_{payment_id}")],
                [InlineKeyboardButton("← Cancel", callback_data=f"buy_premium_pay_{plan}_{months}")]
            ])
        )
    except Exception as e:
        logger.error(e)

@Client.on_callback_query(filters.regex(r"^paid_manual_(.*)$"))
async def handle_paid_manual(client, callback_query):
    payment_id = callback_query.matches[0].group(1)
    p = await db.get_pending_payment(payment_id)

    if not p:
        await callback_query.answer("Transaction not found.", show_alert=True)
        return

    await callback_query.answer("Admins have been notified. Please wait for approval.", show_alert=True)

    try:
        await callback_query.message.edit_text(
            "✅ **Payment Submitted for Review**\n\n"
            f"Your Payment ID `{payment_id}` has been sent to the admins.\n"
            "Your account will be upgraded automatically once the transaction is verified."
        )
    except:
        pass

    admin_ids = [Config.CEO_ID] + getattr(Config, "ADMIN_IDS", [])

    notification_text = (
        "🔔 **New Pending Payment!**\n\n"
        f"**User ID:** `{p['user_id']}`\n"
        f"**Payment ID:** `{payment_id}`\n"
        f"**Plan:** `{p['plan'].capitalize()}`\n"
        f"**Duration:** `{p['duration_months']} Months`\n"
        f"**Amount:** `{p['amount']}`\n"
        f"**Method:** `{p['method'].capitalize()}`\n\n"
        "Check your Admin Panel -> Manage Payments to approve or reject."
    )

    for aid in admin_ids:
        try:
            await client.send_message(aid, notification_text)
        except Exception:
            pass

@Client.on_callback_query(filters.regex(r"^buy_stars_(standard|deluxe)_(\d+)$"))
async def handle_buy_stars(client, callback_query):
    if not is_public_mode():
        return

    plan = callback_query.matches[0].group(1)
    months = int(callback_query.matches[0].group(2))
    user_id = callback_query.from_user.id

    config = await db.get_public_config()

    plan_key = f"premium_{plan}"
    plan_settings = config.get(plan_key, {})
    base_stars = plan_settings.get("stars_price", 0)

    if base_stars <= 0:
        await callback_query.answer("❌ Stars payment is not configured for this plan.", show_alert=True)
        return

    discounts = config.get("discounts", {})
    d3 = discounts.get("months_3", 0)
    d12 = discounts.get("months_12", 0)

    total_stars = base_stars * months
    if months == 3 and d3 > 0:
        total_stars = int(total_stars * (1 - (d3 / 100.0)))
    elif months == 12 and d12 > 0:
        total_stars = int(total_stars * (1 - (d12 / 100.0)))

    title = f"Premium {plan.capitalize()} Plan ({months} Months)"
    description = f"Purchase the Premium {plan.capitalize()} Plan for {months} month(s) via Telegram Stars. You will enjoy enhanced limits and exclusive features."
    payload = f"buy_premium_{plan}_{months}_{user_id}"
    currency = "XTR"

    try:
        from pyrogram.raw.functions.messages import SendMedia
        from pyrogram.raw.types import InputMediaInvoice, Invoice, InputPeerUser, DataJSON

        peer = await client.resolve_peer(user_id)

        invoice = Invoice(
            test=False,
            name_requested=False,
            phone_requested=False,
            email_requested=False,
            shipping_address_requested=False,
            flexible=False,
            phone_to_provider=False,
            email_to_provider=False,
            currency=currency,
            prices=[LabeledPrice(label=title, amount=total_stars)]
        )

        input_media = InputMediaInvoice(
            title=title,
            description=description,
            invoice=invoice,
            payload=payload.encode('utf-8'),
            provider="",
            provider_data=DataJSON(data="{}")
        )

        from pyrogram.raw.functions.messages import SendMedia
        await client.invoke(
            SendMedia(
                peer=peer,
                media=input_media,
                message="",
                random_id=client.rnd_id()
            )
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Failed to send invoice: {e}")
        await callback_query.answer(f"❌ Error generating invoice.", show_alert=True)

@Client.on_raw_update(group=-2)
async def raw_update_handler(client, update, users, chats):
    from pyrogram.raw.types import UpdateBotPrecheckoutQuery, UpdateMessageID

    if isinstance(update, UpdateBotPrecheckoutQuery):
        try:
            from pyrogram.raw.functions.messages import SetBotPrecheckoutResults

            await client.invoke(
                SetBotPrecheckoutResults(
                    query_id=update.query_id,
                    success=True
                )
            )
            logger.info(f"Successfully answered pre-checkout query for {update.user_id}")
        except Exception as e:
            logger.error(f"Failed to answer pre-checkout query: {e}")

def check_payment_message(_, __, message):
    if getattr(message, "successful_payment", None):
        return True
    if hasattr(message, "action") and message.action:
        action_str = str(message.action)
        if "Payment" in action_str or "payment" in action_str:
            return True
        if "PaymentSuccessful" in type(message.action).__name__:
            return True
    return False

payment_filter = filters.create(check_payment_message)

@Client.on_message(payment_filter & filters.private)
async def handle_successful_payment(client, message):
    if not is_public_mode():
        return

    is_payment = False
    payload = ""
    amount = 0

    if getattr(message, "successful_payment", None):
        is_payment = True
        payment_info = message.successful_payment
        payload = getattr(payment_info, "invoice_payload", "")
        amount = getattr(payment_info, "total_amount", 0)
    elif hasattr(message, "action") and message.action:
        action_type = type(message.action).__name__
        if "PaymentSuccessful" in action_type or "Payment" in str(message.action) or "payment" in str(message.action):
            is_payment = True
            payload_raw = getattr(message.action, "invoice_payload", b"")
            if isinstance(payload_raw, bytes):
                payload = payload_raw.decode('utf-8', errors='ignore')
            else:
                payload = str(payload_raw)
            amount = getattr(message.action, "total_amount", 0)

    if is_payment and payload:
        if payload.startswith("buy_premium_"):
            parts = payload.split("_")
            if len(parts) >= 5:
                plan = parts[2]
                months = int(parts[3])
                target_user_id = int(parts[4])

                days = months * 30
                await db.add_premium_user(target_user_id, days=days, plan=plan)

                await message.reply_text(
                    f"✅ **Payment Successful!**\n\n"
                    f"Thank you for purchasing the **Premium {plan.capitalize()} Plan**.\n\n"
                    f"Your account has been upgraded for {months} Month(s). Enjoy!"
                )

                await db.add_log("stars_payment", Config.CEO_ID, f"User {target_user_id} paid for {plan} plan ({months} months)")
