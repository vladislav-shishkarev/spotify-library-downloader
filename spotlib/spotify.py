"""Public Spotify pages (no API): covers, track numbers, album tracklists."""
import html
import json
import re
import urllib.request

from .ffmpeg import shrink
from .library import Track

ALBUM_ID_RE = re.compile(r"album[:/]([A-Za-z0-9]{22})")
TRACK_NO_RE = re.compile(r'<meta name="music:album:track" content="(\d+)"')


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def page(url) -> str:
    return fetch(url).decode("utf-8", "replace")


def meta(page_html, name):
    return [html.unescape(v) for v in
            re.findall(rf'<meta (?:name|property)="{re.escape(name)}" content="([^"]*)"', page_html)]


def cover(tid):
    """Album cover by track id — always the album from the CSV, not a single. None if it fails."""
    try:
        url = json.loads(fetch(f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{tid}"))[
            "thumbnail_url"]
    except Exception:
        return None
    # ab67616d00001e02 = 300px, ab67616d000082c1 = original (usually 2000px), ab67616d0000b273 = 640px
    for size_id in ("ab67616d000082c1", "ab67616d0000b273", None):
        try:
            return shrink(fetch(url.replace("ab67616d00001e02", size_id) if size_id else url))
        except Exception:
            continue
    return None


def track_number(tid):
    """Track number in the album — from the track page (the exportify CSV doesn't have it)."""
    try:
        m = TRACK_NO_RE.search(page(f"https://open.spotify.com/track/{tid}"))
        return m.group(1) if m else None
    except Exception:
        return None


def load_album(url):
    """(album title, [(Track, number)]) for an album link."""
    m = ALBUM_ID_RE.search(url)
    if not m:
        raise SystemExit(f"Doesn't look like a Spotify album link: {url}")
    p = page(f"https://open.spotify.com/album/{m.group(1)}")
    title = (meta(p, "og:title") or [""])[0]
    album = re.sub(r" - (?:Album|Single|EP|Compilation) by .*$", "", title).strip() or title
    year = (meta(p, "music:release_date") or [""])[0][:4]
    tids = [re.search(r"track/(\w{22})", u).group(1) for u in meta(p, "music:song")]
    nums = meta(p, "music:song:track")
    if not tids:
        raise SystemExit("No tracks found on the album page — Spotify may have changed its layout")

    out = []
    for i, tid in enumerate(tids):
        tp = page(f"https://open.spotify.com/track/{tid}")
        name = (meta(tp, "og:title") or [""])[0]
        # "FACE · REVENGE · Song · 2017" — the artists come before the album title
        desc = (meta(tp, "og:description") or [""])[0].split(" · ")
        artists_part = desc[: desc.index(album)] if album in desc else desc[:1]
        artists = [a.strip() for a in ", ".join(artists_part).split(",") if a.strip()]
        duration = float((meta(tp, "music:duration") or ["0"])[0])
        t = Track(tid=tid, name=name, artists=artists, album=album, year=year, duration=duration)
        out.append((t, nums[i] if i < len(nums) else str(i + 1)))
    return album, out
