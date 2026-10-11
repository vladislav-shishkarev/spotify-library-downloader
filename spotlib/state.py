"""Файлы прогресса: что скачано (json {spotify_id: имя файла}) и что упало (tsv id\\tназвание\\tошибка)."""
import json
import threading
from pathlib import Path

from .config import DATA
from .util import BLOCK_RE

_lock = threading.Lock()  # потоки ytm и запись из бота не должны писать файлы одновременно


class JsonStore:
    def __init__(self, path: Path):
        self.path = path

    @property
    def name(self):
        return self.path.name

    def load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def write(self, data: dict):
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def set(self, tid, name):
        """Перечитывает файл перед записью — другой процесс (второй аккаунт) мог дописать своё."""
        with _lock:
            data = self.load()
            data[tid] = name
            self.write(data)

    def claim(self, tid, name) -> bool:
        """Как set, но False, если трек уже записан под другим именем (успел скачать другой аккаунт)."""
        with _lock:
            data = self.load()
            if tid in data and data[tid] != name:
                return False
            data[tid] = name
            self.write(data)
            return True


class FailedLog:
    def __init__(self, path: Path):
        self.path = path

    @property
    def name(self):
        return self.path.name

    def _lines(self):
        if not self.path.exists():
            return []
        return [l for l in self.path.read_text(encoding="utf-8").splitlines() if l]

    def ids(self, skip_blocked=False) -> set:
        """skip_blocked: строки с блокировкой YouTube — не вина трека, их пробуем снова."""
        return {l.split("\t")[0] for l in self._lines() if not (skip_blocked and BLOCK_RE.search(l))}

    def append(self, tid, label, error):
        with _lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(f"{tid}\t{label}\t{error}\n")

    def _keep(self, pred):
        with _lock:
            lines = self._lines()
            keep = [l for l in lines if pred(l.split("\t")[0])]
            if len(keep) != len(lines):
                self.path.write_text("".join(l + "\n" for l in keep), encoding="utf-8")

    def drop(self, tid):
        self._keep(lambda x: x != tid)

    def prune(self, keep_ids):
        self._keep(lambda x: x in keep_ids)

    def reset(self):
        self.path.unlink(missing_ok=True)


YTM_DONE = JsonStore(DATA / "done_ytm.json")
BOT_DONE = JsonStore(DATA / "done.json")
ALBUMS_DONE = JsonStore(DATA / "albums.json")  # скачанное album.py (альбомы целиком, не только лайки)

YTM_FAILED = FailedLog(DATA / "failed_ytm.txt")
BOT_FAILED = FailedLog(DATA / "failed.txt")
ALBUMS_FAILED = FailedLog(DATA / "failed_albums.txt")


def downloaded() -> dict:
    """Всё, что уже лежит в папке, кем бы ни было скачано: {spotify_id: имя файла}."""
    return {**ALBUMS_DONE.load(), **BOT_DONE.load(), **YTM_DONE.load()}
