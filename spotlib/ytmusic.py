"""Поиск трека на YouTube Music и скачивание исходного звука без перекодирования."""
import os
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from ytmusicapi import YTMusic

from .ffmpeg import FFMPEG
from .matching import CHECK_SCORE, MIN_SCORE, SURE_SCORE, VIDEO_MAX_DIFF, score, strip_extras
from .library import Track
from .tagging import tag_full
from .util import unique_target

_local = threading.local()


def _ytm():
    if not hasattr(_local, "ytm"):
        _local.ytm = YTMusic()
    return _local.ytm


def _ensure_js_runtime():
    """deno из venv — yt-dlp нужен JS-рантайм для YouTube."""
    bin_dir = str(Path(sys.executable).parent)
    if bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


def find(t: Track):
    """(кандидат, score) или (None, лучший score)."""
    main = t.artists[0] if t.artists else ""
    queries = [f"{main} {t.name}", f"{' '.join(t.artists)} {strip_extras(t.name)}", t.name]
    best, best_s, seen = None, -1.0, set()
    for q in dict.fromkeys(queries):  # без дублей, порядок сохраняется
        for c in _ytm().search(q, filter="songs", limit=10):
            vid = c.get("videoId")
            if vid in seen:
                continue
            seen.add(vid)
            s = score(c, t)
            if s is not None and s > best_s:
                best, best_s = c, s
        if best_s >= SURE_SCORE:
            break
    if best_s >= MIN_SCORE:
        return best, best_s
    # В "песнях" YTM нет части каталога (региональные ограничения лейблов: Måneskin, Arctic Monkeys...),
    # но то же аудио часто лежит видео на канале самого артиста. Берём только его и только почти
    # точно по длительности — клипы с интро/аутро и чужие лирик-видео не проходят.
    for q in dict.fromkeys(queries[:2]):
        for c in _ytm().search(q, filter="videos", limit=10):
            s = score(c, t, max_diff=VIDEO_MAX_DIFF, min_artist=0.9)
            if s is not None and s > best_s:
                best, best_s = dict(c, from_video=True), s
        if best_s >= SURE_SCORE:
            break
    return (best, best_s) if best_s >= MIN_SCORE else (None, best_s)


def download_audio(video_id, tmp_dir: Path, cookies: Path | None):
    _ensure_js_runtime()
    opts = {
        # 251 = webm/opus ~160k; иначе лучший доступный звук
        "format": "251/bestaudio[acodec=opus]/bestaudio",
        "outtmpl": str(tmp_dir / f"{video_id}.%(ext)s"),
        "ffmpeg_location": FFMPEG,
        # 'best' = просто вытащить звук из контейнера, без перекодирования
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "best"}],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "retries": 5,
    }
    if cookies:
        # yt-dlp при закрытии перезаписывает cookiefile — даём каждой загрузке свою копию,
        # чтобы потоки не портили оригинал одновременной записью
        jar = tmp_dir / "cookies.txt"
        shutil.copyfile(cookies, jar)
        opts["cookiefile"] = str(jar)
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://music.youtube.com/watch?v={video_id}"])
    files = [p for p in tmp_dir.glob(f"{video_id}.*") if p.suffix in (".opus", ".m4a", ".ogg", ".mp3", ".aac")]
    if not files:
        raise RuntimeError("yt-dlp не создал аудиофайл")
    return files[0]


@dataclass
class YtmResult:
    name: str  # имя файла в out_dir
    score: float
    got: str  # что нашлось на YTM: "Артисты - Название"
    diff: float  # разница длительности, сек

    def describe(self):
        warn = "  <-- проверь" if self.score < CHECK_SCORE else ""
        return f"-> {self.got} (score {self.score:.0f}, Δ{self.diff:+.0f}с){warn}"


def process(t: Track, out_dir: Path, cookies: Path | None) -> YtmResult:
    cand, s = find(t)
    if not cand:
        raise LookupError(f"не найдено (лучший score {s:.0f})" if s >= 0 else "не найдено")
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        src = download_audio(cand["videoId"], Path(tmp), cookies)
        tag_full(src, t, cand)
        target = unique_target(out_dir, t.label, t.tid, src.suffix)
        src.replace(target)
    got = f"{', '.join(a['name'] for a in cand.get('artists') or [])} - {cand.get('title')}"
    if cand.get("from_video"):
        got += " [видео с канала артиста]"
    return YtmResult(target.name, s, got, cand.get("duration_seconds", 0) - t.duration)
