"""Show the currently playing Windows media track in the user's Discord profile."""

import asyncio
import hashlib
import io
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from PIL import Image
from pypresence import AioPresence
from pypresence.exceptions import DiscordNotFound, InvalidID, PyPresenceException
from pypresence.types import ActivityType
from winotify import Notification
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winsdk.windows.storage.streams import DataReader

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "").strip()
POLL_SECONDS = max(2, int(os.getenv("POLL_SECONDS", "5")))
handlers = [logging.FileHandler(BASE_DIR / "music_presence.log", encoding="utf-8")]
if getattr(sys, "stdout", None):
    handlers.append(logging.StreamHandler())
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=handlers,
)
log = logging.getLogger("music_presence")
COVER_CACHE = {}
MAX_COVER_BYTES = 5_000_000
NOTICE_TIMES = {}


def clean(value: Optional[str], limit: int = 120) -> str:
    return " ".join((value or "").split())[:limit]


def activity_text(value: str, fallback: str) -> str:
    value = clean(value)
    return value if len(value) >= 2 else fallback


def show_notice(title: str, message: str):
    try:
        Notification(
            app_id="Discord Music Presence",
            title=title,
            msg=message,
        ).show()
    except Exception:
        log.exception("Could not show Windows notification")


async def notify_limited(key: str, title: str, message: str, interval: int = 300):
    now = time.monotonic()
    if now - NOTICE_TIMES.get(key, 0) >= interval:
        NOTICE_TIMES[key] = now
        await asyncio.to_thread(show_notice, title, message)


def normalize_text(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def title_variants(title: str) -> set[str]:
    variants = {normalize_text(title)}
    # Many user-edited MP3/Telegram titles append mix labels that aren't in catalogues.
    base = re.sub(
        r"\s*[([{][^)]*(?:speed\s*up|sped\s*up|bass\s*boost|nightcore|slowed|reverb|8d)[^)]*[)\]}]\s*",
        " ",
        title,
        flags=re.IGNORECASE,
    )
    variants.add(normalize_text(base))
    return {value for value in variants if value}


def find_cover(title: str, artist: str) -> Optional[str]:
    """Return public album art only when both title and artist match."""
    try:
        response = requests.get(
            "https://itunes.apple.com/search",
            params={"term": f"{artist} {title}", "entity": "song", "limit": 25},
            headers={"User-Agent": "DiscordMusicPresence/1.0"},
            timeout=5,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        wanted_titles = title_variants(title)
        wanted_artist = normalize_text(artist)
        match = next((
            item for item in results
            if normalize_text(clean(item.get("trackName"))) in wanted_titles
            and normalize_text(clean(item.get("artistName"))) == wanted_artist
        ), None)
        url = match.get("artworkUrl100") if match else None
        return url.replace("100x100", "600x600") if url else None
    except (requests.RequestException, ValueError) as exc:
        log.debug("Could not look up album art: %s", exc)
        return None


async def read_embedded_cover(thumbnail_ref):
    """Read the cover image Windows exposes for the currently playing media."""
    if thumbnail_ref is None:
        return None, None
    stream = None
    reader = None
    try:
        stream = await thumbnail_ref.open_read_async()
        size = int(stream.size)
        if size <= 0 or size > MAX_COVER_BYTES:
            log.warning("Player supplied an empty or oversized artwork image (%s bytes)", size)
            return None, None
        reader = DataReader(stream.get_input_stream_at(0))
        await reader.load_async(size)
        length = int(reader.unconsumed_buffer_length)
        if length <= 0:
            log.warning("Windows returned an empty media artwork stream")
            return None, None
        data = bytearray(length)
        reader.read_bytes(data)
        log.info("Read embedded media cover (%s bytes, %s)", length, stream.content_type)
        return bytes(data), clean(stream.content_type, 80).lower()
    except Exception as exc:
        log.warning("Could not read the player's embedded cover: %s", exc)
        return None, None
    finally:
        if reader:
            reader.close()
        if stream:
            stream.close()


def upload_cover(image: bytes, content_type: str) -> Optional[str]:
    """Temporarily publish only the artwork so other Discord clients can fetch it."""
    if image.startswith(b"BM") or content_type == "image/bmp":
        try:
            with Image.open(io.BytesIO(image)) as bitmap:
                if bitmap.format != "BMP" or bitmap.width * bitmap.height > 16_000_000:
                    log.warning("The BMP cover is invalid or too large to convert")
                    return None
                converted = io.BytesIO()
                if "A" in bitmap.getbands():
                    bitmap.convert("RGBA").save(converted, format="PNG", optimize=True)
                    image = converted.getvalue()
                    content_type = "image/png"
                else:
                    bitmap.convert("RGB").save(converted, format="JPEG", quality=92, optimize=True)
                    image = converted.getvalue()
                    content_type = "image/jpeg"
            log.info("Converted the embedded BMP cover to %s", content_type)
        except Exception as exc:
            log.warning("Could not convert the embedded BMP cover: %s", exc)
            return None

    signatures = (
        (b"\xff\xd8\xff", "image/jpeg", "cover.jpg"),
        (b"\x89PNG\r\n\x1a\n", "image/png", "cover.png"),
        (b"GIF87a", "image/gif", "cover.gif"),
        (b"GIF89a", "image/gif", "cover.gif"),
        (b"RIFF", "image/webp", "cover.webp"),
    )
    detected = next((item for item in signatures if image.startswith(item[0])), None)
    if detected and detected[1] == "image/webp" and image[8:12] != b"WEBP":
        detected = None
    if detected is None or len(image) > MAX_COVER_BYTES:
        log.warning("The player thumbnail is not a supported image format")
        return None
    _, content_type, filename = detected
    digest = hashlib.sha256(image).hexdigest()
    cached = COVER_CACHE.get(digest)
    if cached and time.monotonic() < cached[1]:
        return cached[0]

    providers = (
        (
            "Litterbox",
            "https://litterbox.catbox.moe/resources/internals/api.php",
            {"reqtype": "fileupload", "time": "72h"},
            {"fileToUpload": (filename, image, content_type)},
            lambda response: response.text.strip(),
            lambda host: host == "litter.catbox.moe",
            70 * 60 * 60,
        ),
        (
            "Uguu",
            "https://uguu.se/upload",
            {},
            {"files[]": (filename, image, content_type)},
            lambda response: response.json()["files"][0]["url"],
            lambda host: host == "uguu.se" or host.endswith(".uguu.se"),
            2 * 60 * 60,
        ),
    )
    for name, endpoint, fields, files, get_url, valid_host, cache_seconds in providers:
        try:
            response = requests.post(endpoint, data=fields, files=files, timeout=20)
            response.raise_for_status()
            url = get_url(response).strip()
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname or not valid_host(parsed.hostname):
                raise ValueError("host returned an unexpected URL")
            COVER_CACHE[digest] = (url, time.monotonic() + cache_seconds)
            # Keep the in-memory cache bounded during long sessions.
            for old_digest, (_, expires) in list(COVER_CACHE.items()):
                if time.monotonic() >= expires:
                    del COVER_CACHE[old_digest]
            log.info("Uploaded embedded cover to %s temporary hosting", name)
            return url
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            log.warning("Could not publish cover to %s: %s", name, exc)
    return None


async def current_track():
    manager = await SessionManager.request_async()
    current = manager.get_current_session()
    sessions = list(manager.get_sessions() or [])
    if current is not None:
        sessions = [current] + [session for session in sessions if session != current]
    for session in sessions:
        try:
            playback = session.get_playback_info()
            if playback.playback_status != PlaybackStatus.PLAYING:
                continue
            props = await session.try_get_media_properties_async()
            title = clean(props.title)
            artist = clean(props.artist) or clean(props.album_artist)
            if title:
                if props.thumbnail is None:
                    log.info("Windows media session has no thumbnail for: %s", title)
                return title, artist, clean(props.album_title), props.thumbnail
        except Exception as exc:
            log.debug("Skipping media session: %s", exc)
    return None


async def disconnect_rpc(rpc, *, clear: bool = False):
    """Close the RPC pipe without closing asyncio.run()'s event loop."""
    if rpc is None:
        return
    if clear:
        try:
            await rpc.clear()
        except Exception:
            pass
    writer = getattr(rpc, "sock_writer", None)
    if writer is not None:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def run():
    rpc = None
    last_track = None
    cover = None
    last_cover_lookup = 0.0
    while True:
        try:
            if rpc is None:
                rpc = AioPresence(CLIENT_ID)
                await rpc.connect()
                log.info("Connected to Discord desktop app")
                await notify_limited(
                    "connected",
                    "Discord Music Presence",
                    "Успішно підключено. Увімкни музику — і вона з’явиться у профілі.",
                    interval=60,
                )

            track = await current_track()
            if track is None:
                if last_track is not None:
                    await rpc.clear()
                    log.info("Playback stopped; cleared Discord activity")
                last_track = None
                cover = None
            else:
                title, artist, album, thumbnail_ref = track
                track_key = (title, artist, album)
                if track_key != last_track:
                    now = time.monotonic()
                    cover_bytes, cover_type = await read_embedded_cover(thumbnail_ref)
                    cover = await asyncio.to_thread(upload_cover, cover_bytes, cover_type) if cover_bytes else None
                    if cover is None and now - last_cover_lookup >= 2:
                        cover = find_cover(title, artist) if artist else None
                        last_cover_lookup = now
                    state = (
                        f"{artist} · {album}" if artist and album
                        else f"By {artist}" if artist
                        else album
                    )
                    await rpc.update(
                        details=activity_text(title, "Unknown track"),
                        state=activity_text(state, "Now playing"),
                        large_image=cover,
                        large_text=activity_text(f"{artist} — {title}" if artist else title, "Now playing"),
                        activity_type=ActivityType.LISTENING,
                    )
                    log.info("Now playing: %s — %s", artist or "Unknown artist", title)
                    last_track = track_key
        except (DiscordNotFound, InvalidID) as exc:
            log.error("Discord desktop is not available, or the Application ID is invalid: %s", exc)
            if isinstance(exc, InvalidID):
                await notify_limited(
                    "invalid_id",
                    "Помилка налаштувань",
                    "Перевір DISCORD_CLIENT_ID у файлі .env.",
                )
            else:
                await notify_limited(
                    "discord_missing",
                    "Discord не запущений",
                    "Відкрий Discord для Windows і переконайся, що ти увійшов у свій акаунт.",
                )
            if rpc:
                await disconnect_rpc(rpc)
                rpc = None
        except PyPresenceException as exc:
            log.warning("Could not connect to Discord Rich Presence: %s", exc)
            await notify_limited(
                "presence_error",
                "Помилка Discord Music Presence",
                "Не вдалось оновити активність. Деталі записані у music_presence.log.",
            )
            if rpc:
                await disconnect_rpc(rpc)
                rpc = None
        except (ConnectionError, OSError) as exc:
            log.warning("Waiting for Discord/media session: %s", exc)
            await notify_limited(
                "connection_error",
                "Помилка підключення",
                "Перевір Discord та інтернет. Деталі записані у music_presence.log.",
            )
            if rpc:
                await disconnect_rpc(rpc)
                rpc = None
            last_track = None
        except Exception:
            log.exception("Could not update the music activity")
            await notify_limited(
                "unexpected_error",
                "Помилка Discord Music Presence",
                "Сталася помилка. Деталі записані у music_presence.log.",
            )
            if rpc:
                await disconnect_rpc(rpc)
                rpc = None
            last_track = None
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    if not CLIENT_ID.isdigit():
        log.error("DISCORD_CLIENT_ID is missing or invalid")
        show_notice(
            "Помилка налаштувань",
            "Вкажи Application ID після DISCORD_CLIENT_ID= у файлі .env.",
        )
        raise SystemExit(
            "Missing DISCORD_CLIENT_ID. See music_presence.log for details."
        )
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Stopped")
