"""Список треков: CSV из exportify или .txt со ссылками на треки."""
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

TRACK_ID_RE = re.compile(r"track[:/]([A-Za-z0-9]{22})")


@dataclass
class Track:
    tid: str
    name: str = ""
    artists: list = field(default_factory=list)
    album: str = ""
    year: str = ""
    duration: float = 0.0  # сек
    explicit: bool = False
    # False — трек из .txt со ссылками: метаданных нет, остаются теги, которые прислал бот
    has_meta: bool = True
    source_line: str = ""  # для .txt — сама строка, показывается вместо названия

    @property
    def label(self):
        if not self.has_meta:
            return self.source_line or self.tid
        return f"{', '.join(self.artists)} - {self.name}"


def _from_csv(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            m = TRACK_ID_RE.search(row.get("Track URI") or "") or TRACK_ID_RE.search(
                " ".join(v or "" for v in row.values() if isinstance(v, str))
            )
            if not m:
                continue
            yield Track(
                tid=m.group(1),
                name=row.get("Track Name") or "",
                artists=[a.strip() for a in (row.get("Artist Name(s)") or "").split(";") if a.strip()],
                album=row.get("Album Name") or "",
                year=(row.get("Release Date") or "")[:4],
                duration=int(row.get("Duration (ms)") or 0) / 1000,
                explicit=(row.get("Explicit") or "").lower() == "true",
            )


def _from_txt(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := TRACK_ID_RE.search(line):
            yield Track(tid=m.group(1), has_meta=False, source_line=line.strip())


def load_tracks(path: Path):
    """[Track] без дублей, в порядке файла."""
    if not path.exists():
        raise SystemExit(f"Нет файла {path.name} — выгрузи библиотеку с exportify.net")
    rows = _from_csv(path) if path.suffix.lower() == ".csv" else _from_txt(path)
    tracks, seen = [], set()
    for t in rows:
        if t.tid not in seen:
            seen.add(t.tid)
            tracks.append(t)
    return tracks
