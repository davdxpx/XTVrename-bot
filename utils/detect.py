from guessit import guessit
from utils.tmdb import tmdb
from utils.log import get_logger

logger = get_logger("utils.detect")


def analyze_filename(filename):
    try:
        guess = guessit(filename)

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
            except:
                pass
        elif guess.get("subtitle_language"):
            try:
                language = str(guess.get("subtitle_language"))
            except:
                pass

        return {
            "title": guess.get("title"),
            "year": guess.get("year"),
            "season": guess.get("season"),
            "episode": guess.get("episode"),
            "quality": quality,
            "type": media_type,
            "is_subtitle": is_subtitle,
            "container": container,
            "language": language,
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


async def auto_match_tmdb(metadata):
    title = metadata.get("title")
    year = metadata.get("year")
    media_type = metadata.get("type")

    if not title:
        return None

    results = []
    try:
        if media_type == "series":
            results = await tmdb.search_tv(title)
        else:
            results = await tmdb.search_movie(title)

        if not results:
            return None

        best_match = results[0]
        tmdb_id = best_match["id"]

        details = await tmdb.get_details(best_match["type"], tmdb_id)

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
