import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# YouTube не пускает ("Sign in to confirm you're not a bot") — дело не в треке, а в куках
BLOCK_RE = re.compile(r"confirm you.?re not a bot|cookies are no longer valid", re.IGNORECASE)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip().rstrip(".")
    return s[:180] or "track"


def unique_target(out_dir: Path, base: str, tid: str, suffix: str) -> Path:
    """out_dir/base.suffix, а если такой файл уже есть — с id трека в имени."""
    target = out_dir / (safe_name(base) + suffix)
    if target.exists():
        target = out_dir / f"{safe_name(base)} [{tid}]{suffix}"
    return target


def clean_error(e: Exception) -> str:
    """Текст ошибки в одну строку, без цветовых кодов yt-dlp."""
    return ANSI_RE.sub("", str(e)).replace("\n", " ")


class Stop(Exception):
    """Бросить из on_error, чтобы отменить оставшиеся задачи run_parallel."""


def run_parallel(fn, items, workers, on_ok, on_error):
    """fn(item) в пуле потоков; по мере готовности on_ok(i, total, item, result) / on_error(i, total, item, e).
    Если on_error бросает Stop — остальные задачи отменяются."""
    total = len(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, item): item for item in items}
        for i, fut in enumerate(as_completed(futures), 1):
            item = futures[fut]
            try:
                res = fut.result()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                try:
                    on_error(i, total, item, e)
                except Stop:
                    pool.shutdown(wait=False, cancel_futures=True)
                    return
                continue
            on_ok(i, total, item, res)
