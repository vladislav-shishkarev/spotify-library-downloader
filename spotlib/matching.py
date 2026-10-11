"""Оценка, насколько кандидат с YouTube Music совпадает с треком из Spotify."""
import re
import unicodedata
from difflib import SequenceMatcher

from .library import Track

MAX_DIFF = 12  # сек: кандидаты с большей разницей по длительности отбрасываются
MIN_SCORE = 55  # из ~100: ниже — считаем, что не нашли
SURE_SCORE = 85  # уверенное совпадение — дальше не ищем
CHECK_SCORE = 75  # ниже — стоит глянуть глазами, вдруг не та версия
VIDEO_MAX_DIFF = 3  # сек: допуск по длительности для запасного поиска по видео
MIN_TITLE = 0.6  # минимальная похожесть названия (0..1), ниже — точно не тот трек
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
    # на YTM русские артисты/названия бывают латиницей: "Дора" в Spotify = канал "Dora"
    if s < 1.0 and (a.translate(TRANSLIT) != a or b.translate(TRANSLIT) != b):
        s = max(s, _sim(a.translate(TRANSLIT), b.translate(TRANSLIT)))
    return s


def score(c, t: Track, max_diff=MAX_DIFF, min_artist=0.5):
    """Очки кандидата c (результат поиска ytmusicapi) или None, если это точно не наш трек."""
    dur = c.get("duration_seconds")
    if not c.get("videoId") or dur is None:
        return None
    diff = abs(dur - t.duration)
    if diff > max_diff:
        return None
    title_s = max(sim(c.get("title"), t.name), sim(strip_extras(c.get("title")), strip_extras(t.name)))
    # другое название = другая песня, даже если совпали исполнитель и длительность
    # (иначе "Original Don" ft. Fireboy DML подменялся его же "So Much Sense" той же длины)
    if title_s < MIN_TITLE:
        return None
    c_artists = [a.get("name") for a in c.get("artists") or [] if a.get("name")]
    artist_s = max((sim(a, b) for a in c_artists for b in t.artists), default=0.0)
    # имя нашего артиста только в названии ("8-Bit Måneskin Emulation", "in the style of ...") —
    # это кавер; нужен совпадающий исполнитель в списке артистов
    if artist_s < min_artist:  # чужой исполнитель — кавер/бутлег, не наш трек
        return None
    # ремикс/лайв/sped up и т.п., которых нет в оригинальном названии
    if set(VERSION_RE.findall(norm(c.get("title")))) != set(VERSION_RE.findall(norm(t.name))):
        return None
    s = title_s * 40 + artist_s * 30 + max(0.0, 20 - diff * 2.5)
    album = (c.get("album") or {}).get("name")
    if album and sim(album, t.album) > 0.8:
        s += 5
    if c.get("isExplicit") == t.explicit:
        s += 5
    return s
