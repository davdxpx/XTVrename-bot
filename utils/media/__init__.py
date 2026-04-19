# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""utils.media — media probing, ffmpeg, archive helpers.

Re-exports the most commonly used entry points of the sibling modules.
"""

from utils.media.archive import check_password_protected, extract_archive, is_archive
from utils.media.detect import (
    analyze_filename,
    apply_autofill,
    auto_match_tmdb,
    probe_audio_streams,
    template_key_for,
)
from utils.media.ffmpeg_tools import (
    LANGUAGE_MAP,
    clear_probe_cache,
    execute_ffmpeg,
    generate_ffmpeg_command,
    get_language_name,
    probe_file,
    sanitize_metadata,
)

__all__ = [
    "LANGUAGE_MAP",
    "analyze_filename",
    "apply_autofill",
    "auto_match_tmdb",
    "check_password_protected",
    "clear_probe_cache",
    "execute_ffmpeg",
    "extract_archive",
    "generate_ffmpeg_command",
    "get_language_name",
    "is_archive",
    "probe_audio_streams",
    "probe_file",
    "sanitize_metadata",
    "template_key_for",
]
