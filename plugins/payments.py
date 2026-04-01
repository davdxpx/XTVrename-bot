from pyrogram import Client, filters
from pyrogram.types import LabeledPrice
from config import Config
from database import db
from utils.log import get_logger

logger = get_logger("plugins.payments")

def is_public_mode():
    return Config.PUBLIC_MODE

@Client.on_callback_query(filters.regex(r"^buy_stars_(standard|deluxe)$"))
async def handle_buy_stars(client, callback_query):
    if not is_public_mode():
        return

    plan = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id

    config = await db.get_public_config()

    plan_key = f"premium_{plan}"
    plan_settings = config.get(plan_key, {})
    stars_price = plan_settings.get("stars_price", 0)

    if stars_price <= 0:
        await callback_query.answer("❌ Stars payment is not configured for this plan.", show_alert=True)
        return

    title = f"Premium {plan.capitalize()} Plan"
    description = f"Purchase the Premium {plan.capitalize()} Plan via Telegram Stars. You will enjoy enhanced limits and features."
    payload = f"buy_premium_{plan}_{user_id}"
    currency = "XTR"
    prices = [LabeledPrice(label=title, amount=stars_price)]

    try:
        await client.send_invoice(
            chat_id=user_id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # Stars provider token is empty string
            currency=currency,
            prices=prices,
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Failed to send invoice: {e}")
        await callback_query.answer(f"❌ Error generating invoice.", show_alert=True)

@Client.on_raw_update()
async def raw_update_handler(client, update, users, chats):
    from pyrogram.raw.types import UpdateBotPrecheckoutQuery
    if isinstance(update, UpdateBotPrecheckoutQuery):
        try:
            await client.answer_pre_checkout_query(
                pre_checkout_query_id=update.query_id,
                ok=True
            )
        except Exception as e:
            logger.error(f"Failed to answer pre-checkout query: {e}")

@Client.on_message(filters.service & filters.private)
async def handle_successful_payment(client, message):
    if not is_public_mode():
        return

    if getattr(message, "successful_payment", None):
        payment_info = message.successful_payment
        payload = payment_info.invoice_payload

        if payload.startswith("buy_premium_"):
            parts = payload.split("_")
            if len(parts) >= 4:
                plan = parts[2]
                target_user_id = int(parts[3])

                # Default hardcoded period is 30 days
                # Add 30 days for Stars payment
                await db.add_premium_user(target_user_id, days=30, plan=plan)

                await message.reply_text(
                    f"✅ **Payment Successful!**\n\n"
                    f"Thank you for purchasing the **Premium {plan.capitalize()} Plan** using {payment_info.total_amount} Telegram Stars.\n\n"
                    f"Your account has been upgraded. Enjoy!"
                )

                await db.add_log("stars_payment", Config.CEO_ID, f"User {target_user_id} paid {payment_info.total_amount} Stars for {plan} plan")
