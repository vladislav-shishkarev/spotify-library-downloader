"""ffmpeg из imageio-ffmpeg: перекодирование в Opus и уменьшение обложек."""
import subprocess
from pathlib import Path

import imageio_ffmpeg
import mutagen
from mutagen.oggopus import OggOpus

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
# бот шлёт Vorbis/MP3 320k — перекодируем в Opus: YouTube Music отдаёт ~130–160k, берём середину
OPUS_BITRATE = "144k"
COVER_SIZE = 1200  # px, до стольких уменьшаем обложку


def to_opus(src: Path) -> Path:
    """src -> src.opus (уже Opus — просто переименовываем)."""
    out = src.with_name(src.name + ".opus")
    if isinstance(mutagen.File(src), OggOpus):
        src.replace(out)
        return out
    r = subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-map", "0:a",
                        "-c:a", "libopus", "-b:a", OPUS_BITRATE, str(out)],
                       capture_output=True, text=True, errors="replace")
    if r.returncode:
        out.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg: " + r.stderr.strip()[-300:])
    return out


def shrink(jpeg: bytes) -> bytes:
    """Уменьшает обложку до COVER_SIZE px (оригинал Spotify 2000px ~1 МБ — жирно для каждого файла)."""
    r = subprocess.run(
        [FFMPEG, "-v", "error", "-i", "pipe:0",
         "-vf", f"scale='min({COVER_SIZE},iw)':-2:flags=lanczos",
         "-q:v", "2", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
        input=jpeg, capture_output=True,
    )
    return r.stdout if r.returncode == 0 and r.stdout else jpeg
