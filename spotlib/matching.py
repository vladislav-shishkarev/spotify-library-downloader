"""Scores how well a YouTube Music candidate matches a Spotify track."""
import re
import unicodedata
from difflib import SequenceMatcher

from .library import Track

MAX_DIFF = 12  # seconds: candidates with a bigger duration difference are rejected
MIN_SCORE = 55  # out of ~100: below this we treat the track as not found
SURE_SCORE = 85  # confident match — stop searching
CHECK_SCORE = 75  # below this — worth checking by ear, it may be the wrong version
VIDEO_MAX_DIFF = 3  # seconds: duration tolerance for the fallback video search
MIN_TITLE = 0.6  # minimum title similarity (0..1), below this it is surely a different track
VERSION_RE = re.compile(
    r"\b(remix|rmx|bootleg|live|acoustic|instrumental|karaoke|cover|"
    r"sped up|speed up|slowed|reverb|nightcore|8d|edit|mashup|flip|vip|"
    r"8 bit|16 bit|chiptune|emulation|tribute|style of|made famous|originally performed|"
    r"lullaby|piano version|orchestral|renditions?|"
    r"performs?|performance|session|concert|first take|unplugged)\b"
)
TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya", "і": "i", "ї": "i", "є": "e", "ґ": "g",
})


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def strip_extras(title):
    """'Song (feat. X) - 2011 Remaster' -> 'Song'"""
    t = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", title or "")
    t = re.sub(r"\s+-\s+.*$", "", t)
    return t or title


def _sim(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def sim(a, b):
    a, b = norm(a), norm(b)
    s = _sim(a, b)
    # on YTM Russian artists/titles are sometimes in Latin letters: "Дора" on Spotify = the "Dora" channel
    if s < 1.0 and (a.translate(TRANSLIT) != a or b.translate(TRANSLIT) != b):
        s = max(s, _sim(a.translate(TRANSLIT), b.translate(TRANSLIT)))
    return s


def score(c, t: Track, max_diff=MAX_DIFF, min_artist=0.5):
    """Score of candidate c (a ytmusicapi search result), or None if it is surely not our track."""
    dur = c.get("duration_seconds")
    if not c.get("videoId") or dur is None:
        return None
    diff = abs(dur - t.duration)
    if diff > max_diff:
        return None
    title_s = max(sim(c.get("title"), t.name), sim(strip_extras(c.get("title")), strip_extras(t.name)))
    # a different title means a different song, even if the artist and duration match
    # (otherwise "Original Don" ft. Fireboy DML was replaced by his "So Much Sense" of the same length)
    if title_s < MIN_TITLE:
        return None
    c_artists = [a.get("name") for a in c.get("artists") or [] if a.get("name")]
    artist_s = max((sim(a, b) for a in c_artists for b in t.artists), default=0.0)
    # our artist's name is only in the title ("8-Bit Måneskin Emulation", "in the style of ...") —
    # that is a cover; the artist must be in the list of artists
    if artist_s < min_artist:  # a different artist — a cover/bootleg, not our track
        return None
    # remix/live/sped up etc. that are not in the original title
    if set(VERSION_RE.findall(norm(c.get("title")))) != set(VERSION_RE.findall(norm(t.name))):
        return None
    s = title_s * 40 + artist_s * 30 + max(0.0, 20 - diff * 2.5)
    album = (c.get("album") or {}).get("name")
    if album and sim(album, t.album) > 0.8:
        s += 5
    if c.get("isExplicit") == t.explicit:
        s += 5
    return s
