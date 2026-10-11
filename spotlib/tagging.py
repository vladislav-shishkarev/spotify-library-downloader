"""Tags and covers in .opus/.ogg and .m4a."""
import base64
import re
from pathlib import Path

from mutagen.flac import Picture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus

from . import spotify
from .ffmpeg import COVER_SIZE
from .library import Track


def get_cover(t: Track, ytm_candidate=None):
    """Album cover from Spotify; the YouTube Music cover is the fallback."""
    if cover := spotify.cover(t.tid):
        return cover
    c = ytm_candidate or {}
    thumbs = c.get("thumbnails") or []
    if thumbs and not c.get("from_video"):  # a video has a 16:9 thumbnail, not a cover
        url = re.sub(r"=w\d+-h\d+.*$", f"=w{COVER_SIZE}-h{COVER_SIZE}-l90-rj", thumbs[-1]["url"])
        try:
            return spotify.fetch(url)
        except Exception:
            pass
    return None


def set_track_number(path: Path, track):
    if path.suffix in (".opus", ".ogg"):
        a = OggOpus(path)
        a["tracknumber"] = track
    else:
        a = MP4(path)
        a["trkn"] = [(int(track), 0)]
    a.save()


def tag(path: Path, t: Track, cover, track=None):
    artist = ", ".join(t.artists)
    if path.suffix in (".opus", ".ogg"):
        a = OggOpus(path)
        a.delete()
        a["title"], a["artist"], a["album"] = t.name, artist, t.album
        a["albumartist"] = t.artists[0] if t.artists else artist
        if track:
            a["tracknumber"] = track
        if t.year:
            a["date"] = t.year
        a["spotify_track_id"] = t.tid
        if cover:
            pic = Picture()
            pic.type, pic.mime, pic.desc, pic.data = 3, "image/jpeg", "Cover", cover
            a["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
        a.save()
    elif path.suffix == ".m4a":
        a = MP4(path)
        a["\xa9nam"], a["\xa9ART"], a["\xa9alb"] = t.name, artist, t.album
        a["aART"] = t.artists[0] if t.artists else artist
        if track:
            a["trkn"] = [(int(track), 0)]
        if t.year:
            a["\xa9day"] = t.year
        if cover:
            a["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
        a.save()


def tag_full(path: Path, t: Track, ytm_candidate=None):
    """Tags + cover + track number — everything we can get for the track."""
    tag(path, t, get_cover(t, ytm_candidate), spotify.track_number(t.tid))
