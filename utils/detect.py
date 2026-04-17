# --- Imports ---
import re
from guessit import guessit
from utils.tmdb import tmdb
from utils.log import get_logger

logger = get_logger("utils.detect")

# === Helper Functions ===
def analyze_filename(filename):
    try:
        # Pre-process filename to handle some edge cases guessit misses
        modified_f = filename

        # Pattern 1: X.YY or XX.YY (e.g., 8.01 -> S08E01)
        match = re.search(r'(?:^|[^\d])(\d{1,2})\.(\d{2})(?:[^\d]|$)', modified_f)
        is_date = False
        if match:
            start_idx = match.start(1)
            if start_idx >= 5:
                preceding = modified_f[start_idx-5:start_idx]
                if re.match(r'\d{4}\.', preceding):  # Avoid YYYY.MM.DD
                    is_date = True
            if not is_date:
                season = match.group(1)
                episode = match.group(2)
                prefix = modified_f[:match.start(1)]
                suffix = modified_f[match.end(2):]
                modified_f = f"{prefix} S{int(season):02d}E{int(episode):02d} {suffix}"

        # Pattern 2: X_YY, XX_YY, X-YY, XX-YY, X~YY, XX~YY (e.g., 8-01 -> S08E01)
        # Avoid breaking standard formats like 2x01-02 by checking if it's preceded by 'x'
        match = re.search(r'(?:^|[^\dx])(\d{1,2})[_~-](\d{2})(?:[^\d]|$)', modified_f, re.IGNORECASE)
        is_date = False
        if match:
            start_idx = match.start(1)
            if start_idx >= 5:
                preceding = modified_f[start_idx-5:start_idx]
                if re.match(r'\d{4}[_~-]', preceding):  # Avoid YYYY-MM-DD
                    is_date = True
            if not is_date:
                season = match.group(1)
                episode = match.group(2)
                prefix = modified_f[:match.start(1)]
                suffix = modified_f[match.end(2):]
                modified_f = f"{prefix} S{int(season):02d}E{int(episode):02d} {suffix}"

        guess = guessit(modified_f)

        media_type = "movie"
        if guess.get("type") == "episode":
            media_type = "series"

        is_subtitle = False
        container = guess.get("container")
        if container in ["srt", "ass", "sub", "vtt"]:
            is_subtitle = True
        elif filename.lower().endswith((".srt", ".ass", ".sub", ".vtt")):
            is_subtitle = True

        quality = str(guess.get("screen_size", "720p"))
        if quality not in ["1080p", "720p", "2160p", "480p"]:
            if "1080" in quality:
                quality = "1080p"
            elif "2160" in quality or "4k" in quality.lower():
                quality = "2160p"
            elif "480" in quality:
                quality = "480p"
            else:
                quality = "720p"

        language = "en"
        if guess.get("language"):
            try:
                language = str(guess.get("language"))
            except (TypeError, ValueError):
                pass
        elif guess.get("subtitle_language"):
            try:
                language = str(guess.get("subtitle_language"))
            except (TypeError, ValueError):
                pass

        extracted_specials = []
        extracted_codec = []
        extracted_audio = []

        orig_name_upper = filename.upper()

        specials_keywords = ["BLURAY", "BLUERAY", "BDRIP", "WEB-DL", "WEBRIP", "HDR", "REMUX", "PROPER", "REPACK", "UNCUT"]
        for kw in specials_keywords:
            if kw in orig_name_upper:
                if kw == "WEB-DL": extracted_specials.append("WEB-DL")
                elif kw == "WEBRIP": extracted_specials.append("WEBRip")
                elif kw == "HDR": extracted_specials.append("HDR")
                elif kw == "REMUX": extracted_specials.append("REMUX")
                elif kw == "PROPER": extracted_specials.append("PROPER")
                elif kw == "REPACK": extracted_specials.append("REPACK")
                elif kw == "UNCUT": extracted_specials.append("UNCUT")
                elif kw == "BDRIP": extracted_specials.append("BDRip")
                else: extracted_specials.append("BluRay")

        extracted_specials = list(dict.fromkeys(extracted_specials))

        codec_keywords = ["X264", "X265", "HEVC"]
        for kw in codec_keywords:
            if kw in orig_name_upper:
                if kw == "X264": extracted_codec.append("x264")
                elif kw == "X265": extracted_codec.append("x265")
                elif kw == "HEVC": extracted_codec.append("HEVC")

        audio_keywords = ["DUAL", "DL", "DUBBED", "MULTI", "MICDUB", "LINEDUB", "DTS", "AC3", "ATMOS"]
        for kw in audio_keywords:
            if kw == "DL":
                if re.search(r'(?<!WEB-)\bDL\b', orig_name_upper):
                    extracted_audio.append("DL")
            else:
                if re.search(r'\b' + re.escape(kw) + r'\b', orig_name_upper):
                    if kw == "DUAL": extracted_audio.append("DUAL")
                    elif kw == "DUBBED": extracted_audio.append("Dubbed")
                    elif kw == "MULTI": extracted_audio.append("Multi")
                    elif kw == "MICDUB": extracted_audio.append("MicDub")
                    elif kw == "LINEDUB": extracted_audio.append("LineDub")
                    elif kw == "DTS": extracted_audio.append("DTS")
                    elif kw == "AC3": extracted_audio.append("AC3")
                    elif kw == "ATMOS": extracted_audio.append("Atmos")

        season_val = guess.get("season")
        episode_val = guess.get("episode")

        # Post-process list-like episodes if guessit misidentified "Show - 08 - 01" as [8, 1]
        if isinstance(episode_val, list) and len(episode_val) == 2 and not season_val:
            season_val = episode_val[0]
            episode_val = episode_val[1]

        if isinstance(season_val, list) and len(season_val) > 0:
            season_val = season_val[0]

        return {
            "title": guess.get("title"),
            "year": guess.get("year"),
            "season": season_val,
            "episode": episode_val,
            "quality": quality,
            "type": media_type,
            "is_subtitle": is_subtitle,
            "container": container,
            "language": language,
            "specials": extracted_specials,
            "codec": extracted_codec[0] if extracted_codec else "",
            "audio": extracted_audio[0] if extracted_audio else "",
        }

    except Exception as e:
        logger.error(f"Error analyzing filename '{filename}': {e}")
        return {
            "title": filename,
            "quality": "720p",
            "type": "movie",
            "is_subtitle": filename.lower().endswith((".srt", ".ass", ".sub", ".vtt")),
            "language": "en",
        }

async def auto_match_tmdb(metadata, language="en-US"):
    # If no TMDB key is configured, auto-matching is disabled. Callers
    # already treat None as "no match" and fall back to General Mode, so
    # this short-circuit keeps the rest of the pipeline untouched.
    from utils.tmdb_gate import is_tmdb_available

    if not is_tmdb_available():
        return None

    title = metadata.get("title")
    year = metadata.get("year")
    media_type = metadata.get("type")

    if not title:
        return None

    results = []
    try:
        if media_type == "series":
            results = await tmdb.search_tv(title, language=language)
        else:
            results = await tmdb.search_movie(title, language=language)

        if not results:
            return None

        best_match = results[0]
        tmdb_id = best_match["id"]

        details = await tmdb.get_details(best_match["type"], tmdb_id, language=language)

        if not details:
            return None

        final_type = "series" if best_match["type"] == "tv" else "movie"
        final_title = (
            details.get("title") if final_type == "movie" else details.get("name")
        )
        final_year = (
            details.get("release_date")
            if final_type == "movie"
            else details.get("first_air_date", "")
        )[:4]
        poster = (
            f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}"
            if details.get("poster_path")
            else None
        )

        return {
            "tmdb_id": tmdb_id,
            "title": final_title,
            "year": final_year,
            "poster": poster,
            "overview": details.get("overview", ""),
            "type": final_type,
        }

    except Exception as e:
        logger.error(f"Error in auto_match_tmdb: {e}")
        return None

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
