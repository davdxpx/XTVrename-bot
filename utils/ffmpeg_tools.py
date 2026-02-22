import asyncio
import json
import os
import logging

LANGUAGE_MAP = {
    "eng": "English", "hin": "Hindi", "spa": "Spanish", "fre": "French",
    "ger": "German", "ita": "Italian", "jpn": "Japanese", "kor": "Korean",
    "chi": "Chinese", "rus": "Russian", "tam": "Tamil", "tel": "Telugu",
    "mal": "Malayalam", "kan": "Kannada", "und": "Unknown"
}

async def probe_file(filepath):
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None

def get_language_name(code):
    return LANGUAGE_MAP.get(code, code)

async def generate_ffmpeg_command(input_path, output_path, metadata, thumbnail_path=None):
    probe = await probe_file(input_path)
    if not probe:
        return None, "Probe failed"

    cmd = ["ffmpeg", "-y", "-i", input_path]

    has_thumb = thumbnail_path and os.path.exists(thumbnail_path)
    if has_thumb:
        cmd.extend(["-i", thumbnail_path])

    # Build Maps and Metadata
    maps = []
    metadata_args = []

    input_streams = probe.get("streams", [])

    out_video_idx = 0
    out_audio_idx = 0
    out_subtitle_idx = 0

    # Iterate input streams (Input 0)
    for i, stream in enumerate(input_streams):
        disposition = stream.get("disposition", {})
        if disposition.get("attached_pic") == 1:
            continue

        # Map this stream
        maps.extend(["-map", f"0:{stream['index']}"])

        codec_type = stream["codec_type"]
        tags = stream.get("tags", {})
        lang_code = tags.get("language", "und")
        lang_name = get_language_name(lang_code)

        if lang_name == "Unknown" or lang_name == "und":
             lang_name = metadata.get("default_language", "English")

        if codec_type == "video":
            if "video_title" in metadata:
                metadata_args.extend([f"-metadata:s:v:{out_video_idx}", f"title={metadata['video_title']}"])
            out_video_idx += 1

        elif codec_type == "audio":
            if "audio_title" in metadata:
                title = metadata["audio_title"].replace("{lang}", lang_name)
                metadata_args.extend([f"-metadata:s:a:{out_audio_idx}", f"title={title}"])
            out_audio_idx += 1

        elif codec_type == "subtitle":
            if "subtitle_title" in metadata:
                title = metadata["subtitle_title"].replace("{lang}", lang_name)
                metadata_args.extend([f"-metadata:s:s:{out_subtitle_idx}", f"title={title}"])
            out_subtitle_idx += 1

    # Thumbnail Stream (Input 1)
    thumb_args = []
    if has_thumb:
        maps.extend(["-map", "1"])
        # We target the LAST video stream we just added
        # Which is at index `out_video_idx`
        # We force it to be mjpeg and attached_pic
        thumb_args.extend([f"-c:v:{out_video_idx}", "mjpeg"])
        thumb_args.extend([f"-disposition:v:{out_video_idx}", "attached_pic"])
        out_video_idx += 1

    # Global Metadata
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

    # Construct final command
    # Order: [Base] [Maps] [-c copy] [Thumb Overrides] [Metadata] [Output]

    cmd.extend(maps)
    cmd.extend(["-c", "copy"]) # Default copy
    cmd.extend(thumb_args)     # Override for thumb
    cmd.extend(metadata_args)  # Stream metadata
    cmd.extend(global_meta)    # Global metadata
    cmd.append(output_path)

    return cmd, None

async def execute_ffmpeg(cmd):
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return process.returncode == 0, stderr
