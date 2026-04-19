# --- Imports ---
import asyncio
import contextlib
import logging
import os

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from plugins.user_setup import track_tool_usage
from utils.media.ffmpeg_tools import execute_ffmpeg
from utils.telegram.log import get_logger
from utils.state import clear_session, get_data, get_state, set_state, update_data

logger = get_logger("tools.ImageWatermarker")

# === Handlers ===
@Client.on_callback_query(filters.regex(r"^watermarker_menu$"))
async def handle_watermarker_menu(client, callback_query):
    await track_tool_usage(callback_query.from_user.id, 'watermarker')
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_watermark_image")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "©️ **Image Watermarker**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me the **image** you want to watermark.\n"
            "> Supported: PNG, JPG, WEBP",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )

@Client.on_callback_query(filters.regex(r"^watermark_type_(text|image)$"))
async def handle_watermark_type(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    wtype = callback_query.data.split("_")[2]

    update_data(user_id, "watermark_type", wtype)
    set_state(user_id, f"awaiting_watermark_{wtype}")

    if wtype == "text":
        msg = (
            "©️ **Image Watermarker**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me the **text** you want as a watermark."
        )
    else:
        set_state(user_id, "awaiting_watermark_overlay")
        msg = (
            "©️ **Image Watermarker**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me the **image** (PNG/JPG) to use\n"
            "> as a watermark overlay."
        )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            msg,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )

@Client.on_callback_query(filters.regex(r"^wm_pos_(.*)$"))
async def handle_watermark_position(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    pos = callback_query.data.split("_")[2]
    update_data(user_id, "watermark_position", pos)

    set_state(user_id, "awaiting_watermark_size")
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "©️ **Image Watermarker**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> How large should the watermark be?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔹 Small", callback_data="wm_size_small"),
                        InlineKeyboardButton("🔸 Medium", callback_data="wm_size_medium"),
                        InlineKeyboardButton("🔶 Large", callback_data="wm_size_large"),
                    ],
                    [
                        InlineKeyboardButton("10%", callback_data="wm_size_10"),
                        InlineKeyboardButton("20%", callback_data="wm_size_20"),
                        InlineKeyboardButton("30%", callback_data="wm_size_30"),
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )

@Client.on_callback_query(filters.regex(r"^wm_size_(.*)$"))
async def handle_watermark_size(client, callback_query):
    if not get_state(callback_query.from_user.id):
        return await callback_query.answer("⚠️ Session expired. Please start again.", show_alert=True)
    await callback_query.answer()
    user_id = callback_query.from_user.id
    size = callback_query.data.split("_")[2]
    update_data(user_id, "watermark_size", size)

    session_data = get_data(user_id)
    data = {
        "type": "watermark",
        "watermark_type": session_data.get("watermark_type"),
        "watermark_content": session_data.get("watermark_content"),
        "watermark_position": session_data.get("watermark_position"),
        "watermark_size": session_data.get("watermark_size"),
        "original_name": session_data.get("original_name"),
        "file_message_id": session_data.get("file_message_id"),
        "file_chat_id": session_data.get("file_chat_id"),
        "is_auto": False,
    }

    try:
        msg = await client.get_messages(
            session_data.get("file_chat_id"), session_data.get("file_message_id")
        )
        data["file_message"] = msg
        await callback_query.message.delete()
        reply_msg = await client.send_message(
            user_id,
            "©️ **Image Watermarker**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "⏳ __Processing watermark...__\n\n"
            "> Applying your customized overlay."
        )
        from plugins.process import process_file

        asyncio.create_task(process_file(client, reply_msg, data))
    except Exception as e:
        logger.error(f"Failed to get message for watermark mode: {e}")
        await client.send_message(user_id, f"Error: {e}")

    clear_session(user_id)

# === Functions ===
async def watermark(input_path: str, output_dir: str, safe_title: str, ext: str, watermark_type: str, watermark_content: str, position: str = "bottomright", size: str = "medium", user_id: int = 0, active_client=None, progress_callback=None) -> tuple[bool, bytes, str, str]:
    """
    Applies a text or image watermark to the input media using FFmpeg.
    Returns: (success, stderr, output_path, meta_title)
    """
    final_filename = f"{safe_title}_watermarked{ext}"
    meta_title = f"{safe_title}"
    output_path = os.path.join(output_dir, final_filename)

    cmd = ["ffmpeg", "-y", "-i", input_path]

    if watermark_type == "text":
        escaped_text = watermark_content.replace("'", "\\'").replace(":", "\\:")

        if size == "small":
            fontsize = "h/20"
        elif size == "large":
            fontsize = "h/5"
        elif size in ["10", "20", "30"]:
            factor = int(size) / 100
            fontsize = f"h*{factor}"
        else:
            fontsize = "h/10"

        if position == "topleft":
            x, y = "10", "10"
        elif position == "topright":
            x, y = "w-text_w-10", "10"
        elif position == "bottomleft":
            x, y = "10", "h-text_h-10"
        elif position == "center":
            x, y = "(w-text_w)/2", "(h-text_h)/2"
        else:
            x, y = "w-text_w-10", "h-text_h-10"

        cmd.extend(
            [
                "-vf",
                f"drawtext=text='{escaped_text}':fontcolor=white@0.8:fontsize={fontsize}:x={x}:y={y}:box=1:boxcolor=black@0.5:boxborderw=5",
            ]
        )

    else:
        watermark_path = os.path.join(
            output_dir, f"{user_id}_wm_overlay.png"
        )
        if watermark_content and active_client:
            await active_client.download_media(
                watermark_content, file_name=watermark_path
            )

        if os.path.exists(watermark_path):
            if size == "small":
                scale_expr = "w='main_w*0.1':h='ow/a'"
            elif size == "large":
                scale_expr = "w='main_w*0.4':h='ow/a'"
            elif size in ["10", "20", "30"]:
                scale_expr = f"w='main_w*{int(size)/100}':h='ow/a'"
            else:
                scale_expr = "w='main_w*0.2':h='ow/a'"

            if position == "topleft":
                overlay_expr = "10:10"
            elif position == "topright":
                overlay_expr = "W-w-10:10"
            elif position == "bottomleft":
                overlay_expr = "10:H-h-10"
            elif position == "center":
                overlay_expr = "(W-w)/2:(H-h)/2"
            else:
                overlay_expr = "W-w-10:H-h-10"

            cmd.extend(
                [
                    "-i",
                    watermark_path,
                    "-filter_complex",
                    f"[1:v][0:v]scale2ref={scale_expr}[wm][vid];[vid][wm]overlay={overlay_expr}",
                ]
            )
        else:
            logger.error("Watermark overlay image missing.")

    cmd.append(output_path)
    success, stderr = await execute_ffmpeg(cmd, progress_callback=progress_callback)
    return success, stderr, output_path, meta_title

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
