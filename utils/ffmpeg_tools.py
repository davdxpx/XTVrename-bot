import asyncio
import json
import os
import logging

LANGUAGE_MAP = {
    "eng": "English",
    "hin": "Hindi",
    "spa": "Spanish",
    "fre": "French",
    "ger": "German",
    "ita": "Italian",
    "jpn": "Japanese",
    "kor": "Korean",
    "chi": "Chinese",
    "rus": "Russian",
    "tam": "Tamil",
    "tel": "Telugu",
    "mal": "Malayalam",
    "kan": "Kannada",
    "und": "Unknown",
}


async def probe_file(filepath):
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        filepath,
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        error_msg = stderr.decode().strip() or "ffprobe process failed"
        return None, error_msg
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as e:
        return None, f"JSON Decode Error: {e}"


def get_language_name(code):
    return LANGUAGE_MAP.get(code, code)


async def generate_ffmpeg_command(
    input_path, output_path, metadata, thumbnail_path=None
):
    probe, err = await probe_file(input_path)
    if not probe:
        return None, f"Probe failed: {err}"

    cmd = ["ffmpeg", "-y", "-i", input_path]

    has_thumb = thumbnail_path and os.path.exists(thumbnail_path)
    if has_thumb:
        cmd.extend(["-i", thumbnail_path])

    maps = []
    metadata_args = []

    input_streams = probe.get("streams", [])

    out_video_idx = 0
    out_audio_idx = 0
    out_subtitle_idx = 0

    is_subtitle_output = output_path.endswith(".srt")

    for i, stream in enumerate(input_streams):
        disposition = stream.get("disposition", {})
        if disposition.get("attached_pic") == 1:
            continue

        codec_type = stream["codec_type"]

        if is_subtitle_output and codec_type != "subtitle":
            continue

        maps.extend(["-map", f"0:{stream['index']}"])

        tags = stream.get("tags", {})
        lang_code = tags.get("language", "und")
        lang_name = get_language_name(lang_code)

        if lang_name == "Unknown" or lang_name == "und":
            lang_name = metadata.get("default_language", "English")

        if codec_type == "video":
            if "video_title" in metadata:
                metadata_args.extend(
                    [
                        f"-metadata:s:v:{out_video_idx}",
                        f"title={metadata['video_title']}",
                    ]
                )
            out_video_idx += 1

        elif codec_type == "audio":
            if "audio_title" in metadata:
                title = metadata["audio_title"].replace("{lang}", lang_name)
                metadata_args.extend(
                    [f"-metadata:s:a:{out_audio_idx}", f"title={title}"]
                )
            out_audio_idx += 1

        elif codec_type == "subtitle":
            if "subtitle_title" in metadata:
                title = metadata["subtitle_title"].replace("{lang}", lang_name)
                metadata_args.extend(
                    [f"-metadata:s:s:{out_subtitle_idx}", f"title={title}"]
                )
            out_subtitle_idx += 1

    thumb_args = []
    if has_thumb:
        maps.extend(["-map", "1"])
        thumb_args.extend([f"-c:v:{out_video_idx}", "mjpeg"])
        thumb_args.extend([f"-disposition:v:{out_video_idx}", "attached_pic"])
        out_video_idx += 1

    global_meta = []
    if "title" in metadata:
        global_meta.extend(["-metadata", f"title={metadata['title']}"])
    if "author" in metadata:
        global_meta.extend(["-metadata", f"author={metadata['author']}"])
    if "artist" in metadata:
        global_meta.extend(["-metadata", f"artist={metadata['artist']}"])
    if "encoded_by" in metadata:
        global_meta.extend(["-metadata", f"encoded_by={metadata['encoded_by']}"])
    if "copyright" in metadata:
        global_meta.extend(["-metadata", f"copyright={metadata['copyright']}"])

    cmd.extend(maps)

    if is_subtitle_output:
        cmd.extend(["-c", "srt"])
    else:
        cmd.extend(["-c", "copy"])

    cmd.extend(thumb_args)
    cmd.extend(metadata_args)
    cmd.extend(global_meta)
    cmd.append(output_path)

    return cmd, None


async def execute_ffmpeg(cmd):
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await process.communicate()
        return process.returncode == 0, stderr
    except asyncio.CancelledError:
        logging.getLogger("ffmpeg_tools").warning("FFmpeg process cancelled, terminating...")
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
        raise


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
