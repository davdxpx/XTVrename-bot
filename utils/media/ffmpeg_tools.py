# --- Imports ---
import asyncio
import contextlib
import json
import logging
import os
import time

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

# === Helper Functions ===
def sanitize_metadata(value: str, max_length: int = 500) -> str:
    """Strip control characters and limit length for safe FFmpeg metadata injection."""
    if not isinstance(value, str):
        value = str(value)
    value = value[:max_length]
    # Remove null bytes and control characters (keep printable + newline)
    return ''.join(c for c in value if c == '\n' or (ord(c) >= 32 and ord(c) != 127))


_probe_cache = {}  # filepath -> (timestamp, result)
_PROBE_CACHE_TTL = 300  # 5 minutes


def clear_probe_cache(filepath=None):
    """Clear probe cache for a specific file or all files."""
    if filepath:
        _probe_cache.pop(filepath, None)
    else:
        _probe_cache.clear()


async def probe_file(filepath):
    # Check cache first
    now = time.time()
    if filepath in _probe_cache:
        cached_time, cached_result = _probe_cache[filepath]
        if now - cached_time < _PROBE_CACHE_TTL:
            return cached_result, None
        del _probe_cache[filepath]

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
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
        if process.returncode != 0:
            error_msg = stderr.decode().strip() or "ffprobe process failed"
            return None, error_msg
        try:
            result = json.loads(stdout)
            # Cache successful probes
            _probe_cache[filepath] = (now, result)
            # Evict old entries if cache grows too large
            if len(_probe_cache) > 100:
                expired = [k for k, (t, _) in _probe_cache.items() if now - t > _PROBE_CACHE_TTL]
                for k in expired:
                    del _probe_cache[k]
            return result, None
        except json.JSONDecodeError as e:
            return None, f"JSON Decode Error: {e}"
    except asyncio.TimeoutError:
        logging.getLogger("ffmpeg_tools").warning("ffprobe process timed out, killing...")
        with contextlib.suppress(Exception):
            process.kill()
        return None, "ffprobe process timed out"
    except asyncio.CancelledError:
        logging.getLogger("ffmpeg_tools").warning("ffprobe process cancelled, killing...")
        with contextlib.suppress(Exception):
            process.kill()
        raise

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

    for _i, stream in enumerate(input_streams):
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
                        f"title={sanitize_metadata(metadata['video_title'])}",
                    ]
                )
            out_video_idx += 1

        elif codec_type == "audio":
            if "audio_title" in metadata:
                title = sanitize_metadata(metadata["audio_title"]).replace("{lang}", lang_name)
                metadata_args.extend(
                    [f"-metadata:s:a:{out_audio_idx}", f"title={title}"]
                )
            out_audio_idx += 1

        elif codec_type == "subtitle":
            if "subtitle_title" in metadata:
                title = sanitize_metadata(metadata["subtitle_title"]).replace("{lang}", lang_name)
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
        global_meta.extend(["-metadata", f"title={sanitize_metadata(metadata['title'])}"])
    if "author" in metadata:
        global_meta.extend(["-metadata", f"author={sanitize_metadata(metadata['author'])}"])
    if "artist" in metadata:
        global_meta.extend(["-metadata", f"artist={sanitize_metadata(metadata['artist'])}"])
    if "encoded_by" in metadata:
        global_meta.extend(["-metadata", f"encoded_by={sanitize_metadata(metadata['encoded_by'])}"])
    if "copyright" in metadata:
        global_meta.extend(["-metadata", f"copyright={sanitize_metadata(metadata['copyright'])}"])

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

import re


async def execute_ffmpeg(cmd, progress_callback=None):
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stderr_lines = []

    async def read_stderr():

        buffer = ""
        while True:
            chunk = await process.stderr.read(1024)
            if not chunk:
                break

            chunk_str = chunk.decode('utf-8', errors='replace')
            buffer += chunk_str

            lines = re.split(r'[\r\n]+', buffer)

            buffer = lines.pop()

            for line_str in lines:
                if line_str.strip():
                    stderr_lines.append(line_str + "\n")

                    if progress_callback:

                        time_match = re.search(r"time=(\d{2}:\d{2}:\d{2}[\.\d]*)", line_str)
                        if time_match:
                            await progress_callback(time_match.group(1))

        if buffer.strip():
            stderr_lines.append(buffer + "\n")
            if progress_callback:
                time_match = re.search(r"time=(\d{2}:\d{2}:\d{2}[\.\d]*)", buffer)
                if time_match:
                    await progress_callback(time_match.group(1))

    wait_task = asyncio.create_task(process.wait())
    read_task = asyncio.create_task(read_stderr())

    try:
        await asyncio.gather(wait_task, read_task)
        stderr_str = "".join(stderr_lines).encode()
        return process.returncode == 0, stderr_str
    except asyncio.CancelledError:
        logging.getLogger("ffmpeg_tools").warning("FFmpeg process cancelled, terminating...")
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logging.getLogger("ffmpeg_tools").warning("FFmpeg process did not terminate, killing...")
                try:
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except Exception as e:
                    logging.getLogger("ffmpeg_tools").error(f"Failed to kill FFmpeg process: {e}")
        wait_task.cancel()
        read_task.cancel()
        raise

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
