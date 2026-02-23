"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    Developed by 𝕏0L0™ (@davdxpx)                         ║
║     © 2024 XTV Network Global. All Rights Reserved.                      ║
║                                                                          ║
║  Project: XTV Rename Bot                                                 ║
║  Author: 𝕏0L0™                                                           ║
║  Telegram: @davdxpx                                                      ║
║  Channel: @XTVbots                                                       ║
║  Network: @XTVglobal                                                     ║
║  Backup: @XTVhome                                                        ║
║                                                                          ║
║  WARNING: This code is the intellectual property of XTV Network.         ║
║  Unauthorized modification, redistribution, or removal of this credit    ║
║  is strictly prohibited. Forking and simple usage is allowed under       ║
║  the terms of the license.                                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from guessit import guessit
from utils.tmdb import tmdb
from utils.log import get_logger

logger = get_logger("utils.detect")

def analyze_filename(filename):
    """
    Uses guessit to parse the filename and extract metadata.
    """
    try:
        guess = guessit(filename)

        # Normalize type
        media_type = "movie"
        if guess.get('type') == 'episode':
            media_type = "series"

        # Check if subtitle based on extension or container
        is_subtitle = False
        container = guess.get('container')
        if container in ['srt', 'ass', 'sub', 'vtt']:
            is_subtitle = True
        elif filename.lower().endswith(('.srt', '.ass', '.sub', '.vtt')):
            is_subtitle = True

        quality = str(guess.get('screen_size', '720p'))
        if quality not in ['1080p', '720p', '2160p', '480p']:
            # Fallback to 720p if unknown or weird format, or try to detect from string
            if '1080' in quality: quality = '1080p'
            elif '2160' in quality or '4k' in quality.lower(): quality = '2160p'
            elif '480' in quality: quality = '480p'
            else: quality = '720p'

        # Extract language (for subtitles)
        language = "en"
        if guess.get('language'):
            try:
                language = str(guess.get('language'))
            except:
                pass
        elif guess.get('subtitle_language'):
             try:
                language = str(guess.get('subtitle_language'))
             except:
                pass

        return {
            "title": guess.get('title'),
            "year": guess.get('year'),
            "season": guess.get('season'),
            "episode": guess.get('episode'),
            "quality": quality,
            "type": media_type,
            "is_subtitle": is_subtitle,
            "container": container,
            "language": language
        }
    except Exception as e:
        logger.error(f"Error analyzing filename '{filename}': {e}")
        return {
            "title": filename,
            "quality": "720p",
            "type": "movie",
            "is_subtitle": filename.lower().endswith(('.srt', '.ass', '.sub', '.vtt')),
            "language": "en"
        }

async def auto_match_tmdb(metadata):
    """
    Searches TMDB based on the extracted metadata and returns the best match.
    """
    title = metadata.get("title")
    year = metadata.get("year")
    media_type = metadata.get("type") # 'movie' or 'series'

    if not title:
        return None

    results = []
    try:
        if media_type == "series":
            results = await tmdb.search_tv(title)
        else:
            results = await tmdb.search_movie(title)

        # If no results and type was movie, maybe it was a series? or vice versa?
        # For now, stick to the guessit type.

        if not results:
            # Fallback: if we searched for movie and found nothing, try series if it looks ambiguous?
            # Or just return None.
            return None

        # Select the first result
        best_match = results[0]
        tmdb_id = best_match["id"]

        # Get full details
        details = await tmdb.get_details(best_match["type"], tmdb_id)

        if not details:
            return None

        # Normalize result for our app
        final_type = "series" if best_match["type"] == "tv" else "movie"
        final_title = details.get("title") if final_type == "movie" else details.get("name")
        final_year = (details.get("release_date") if final_type == "movie" else details.get("first_air_date", ""))[:4]
        poster = f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}" if details.get("poster_path") else None

        return {
            "tmdb_id": tmdb_id,
            "title": final_title,
            "year": final_year,
            "poster": poster,
            "overview": details.get("overview", ""),
            "type": final_type
        }

    except Exception as e:
        logger.error(f"Error in auto_match_tmdb: {e}")
        return None
