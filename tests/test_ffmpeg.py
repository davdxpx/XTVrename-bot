import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Add root to path
sys.path.append(os.getcwd())

from utils.ffmpeg_tools import generate_ffmpeg_command

async def test_ffmpeg():
    # Mock probe result
    mock_probe = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "tags": {"language": "eng"},
                "disposition": {"attached_pic": 0}
            },
            {
                "index": 1,
                "codec_type": "audio",
                "tags": {"language": "jpn"},
                "disposition": {"attached_pic": 0}
            },
            {
                "index": 2,
                "codec_type": "subtitle",
                "tags": {"language": "jpn"},
                "disposition": {"attached_pic": 0}
            }
        ]
    }

    metadata = {
        "title": "@XTVglobal - My Movie",
        "author": "@XTVglobal",
        "artist": "By:- @XTVglobal",
        "video_title": "Encoded By:- @XTVglobal",
        "audio_title": "Audio By:- @XTVglobal - {lang}",
        "subtitle_title": "Subtitled By:- @XTVglobal - {lang}",
        "default_language": "English"
    }

    # Create dummy thumb
    with open("thumb.jpg", "w") as f:
        f.write("dummy")

    try:
        # Patch probe_file with AsyncMock returning mock_probe
        with patch("utils.ffmpeg_tools.probe_file", new_callable=AsyncMock) as mock_probe_func:
            mock_probe_func.return_value = mock_probe

            cmd, err = await generate_ffmpeg_command(
                "input.mkv", "output.mkv", metadata, thumbnail_path="thumb.jpg"
            )

            print("Generated Command:")
            print(" ".join(cmd))

            # Assertions
            cmd_str = " ".join(cmd)
            assert "-i thumb.jpg" in cmd_str
            assert "-map 0:0" in cmd_str
            assert "-map 0:1" in cmd_str
            assert "-map 0:2" in cmd_str
            assert "-map 1" in cmd_str # Thumb
            # Thumb is 2nd video stream (idx 1)
            # -c:v:1 mjpeg -disposition:v:1 attached_pic
            assert "-c:v:1 mjpeg" in cmd_str
            assert "-disposition:v:1 attached_pic" in cmd_str

            # Metadata check
            # Video: 0:0 -> -metadata:s:v:0 title="Encoded By..."
            assert '-metadata:s:v:0 title=Encoded By:- @XTVglobal' in cmd_str

            # Audio: 0:1 -> -metadata:s:a:0 title="Audio By... - Japanese"
            assert '-metadata:s:a:0 title=Audio By:- @XTVglobal - Japanese' in cmd_str

            # Subtitle: 0:2 -> -metadata:s:s:0 title="Subtitled By... - Japanese"
            assert '-metadata:s:s:0 title=Subtitled By:- @XTVglobal - Japanese' in cmd_str

            # Global Metadata
            assert '-metadata title=@XTVglobal - My Movie' in cmd_str

    finally:
        if os.path.exists("thumb.jpg"):
            os.remove("thumb.jpg")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(test_ffmpeg())
    print("\nTest Passed!")
