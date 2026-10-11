"""
Синхронизирует папку с музыкой со свежим CSV из exportify.

1. Треки, которых больше нет в CSV (убрал лайк) -> файлы в корзину Windows, записи из прогресса.
2. Треки из CSV, чей файл пропал из папки -> будут скачаны заново.
3. Новые треки -> докачиваются как в ytm_download.py.

    python sync.py --dry-run      # только показать, что будет сделано
    python sync.py                # синхронизировать (перед удалением спросит)
    python sync.py --yes          # без вопроса
Остальные аргументы (--workers, --limit, --retry-failed) передаются в ytm_download.py.
"""
import argparse
from pathlib import Path

from mutagen.oggopus import OggOpus
from send2trash import send2trash

from .. import state
from ..config import load_config
from ..library import load_tracks
from . import ytm

MAX_REMOVE_SHARE = 0.25  # пропало больше четверти — скорее всего, CSV не тот/битый


def scan_tags(out_dir: Path):
    """{spotify_id: путь} по тегу spotify_track_id, который ставится при скачивании."""
    found = {}
    for p in out_dir.iterdir():
        if p.suffix.lower() not in (".opus", ".ogg"):
            continue
        try:
            ids = OggOpus(p).get("spotify_track_id")
        except Exception:
            continue
        if ids:
            found[ids[0]] = p
    return found


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="change nothing, only show what would happen")
    ap.add_argument("--yes", action="store_true", help="delete without asking")
    ap.add_argument("--force", action="store_true", help="delete even if suspiciously many tracks disappeared from likes")
    args, passthrough = ap.parse_known_args(argv)
    ytm.parse_args(passthrough)  # проверяем аргументы для докачки сразу, а не после удаления

    cfg = load_config()
    out_dir = cfg.out_dir
    tracks = load_tracks(cfg.tracks_file)
    if not tracks:
        raise SystemExit(f"No tracks in {cfg.tracks_file.name} — not syncing")
    liked = {t.tid for t in tracks}

    # (файл прогресса, его содержимое): у YTM и у бота свои; albums.json sync не трогает
    stores = [(s, s.load()) for s in (state.YTM_DONE, state.BOT_DONE)]
    have = {tid: name for _, d in stores for tid, name in d.items()}

    # файл ищем по тегу spotify_track_id (переживает переименование), иначе — по имени из прогресса
    on_disk = scan_tags(out_dir)
    paths = {}
    for tid, name in have.items():
        p = on_disk.get(tid) or out_dir / name
        if p.exists():
            paths[tid] = p
            have[tid] = p.name

    removed = {tid: name for tid, name in have.items() if tid not in liked}
    missing = {tid: name for tid, name in have.items() if tid in liked and tid not in paths}
    # строки с блокировкой YouTube — не «не нашлось», ytm_download их повторит сам
    failed = state.YTM_FAILED.ids(skip_blocked=True)
    # треки из albums.json (album.py) уже лежат в папке — не новые; удалять их sync не будет
    albums = state.ALBUMS_DONE.load()
    new = [t for t in tracks if t.tid not in have and t.tid not in failed and t.tid not in albums]

    print(f"Liked: {len(liked)}, downloaded: {len(have)}")
    print(f"  removed from likes: {len(removed)}")
    for name in sorted(removed.values()):
        print(f"    - {name}")
    print(f"  file missing from the folder (will re-download): {len(missing)}")
    for name in sorted(missing.values()):
        print(f"    ? {name}")
    print(f"  new / not downloaded yet: {len(new)}")
    print(f"  not found earlier ({state.YTM_FAILED.name}, retry: --retry-failed): {len(failed & liked)}")

    if args.dry_run:
        print("\n--dry-run: nothing changed")
        return

    if removed and len(removed) > MAX_REMOVE_SHARE * len(have) and not args.force:
        raise SystemExit(f"\n{len(removed)} of {len(have)} tracks disappeared from likes — suspiciously many. "
                         f"Make sure {cfg.tracks_file.name} is fresh and complete. If it is, run with --force")

    if removed and not args.yes:
        if input(f"\nMove {len(removed)} files to the recycle bin? [y/N] ").strip().lower() not in ("y", "yes", "д", "да"):
            print("Deletion skipped")
            removed = {}

    for tid in removed:
        if tid in paths:
            send2trash(str(paths[tid]))
    for store, data in stores:
        changed = False
        for tid in list(data):
            if tid in removed or tid in missing:
                del data[tid]
                changed = True
            elif data[tid] != have[tid]:  # файл переименовали — запоминаем новое имя
                data[tid] = have[tid]
                changed = True
        if changed:
            store.write(data)
    if removed or missing:
        print(f"Moved to the recycle bin: {len(removed)}, to re-download: {len(missing)}")

    state.YTM_FAILED.prune(liked)  # треки, которых больше нет в лайках

    if new or missing:
        print("\nDownloading from YouTube Music...\n", flush=True)
        ytm.main(passthrough)
    else:
        print("\nEverything is up to date, nothing to download")
