"""
Качает библиотеку по CSV из exportify через YouTube Music — без Spotify API и без лимитов.

Для каждого трека:
  1. ищет среди *песен* YouTube Music (не клипов) по исполнителю и названию;
  2. выбирает кандидата по длительности (сверка со Spotify), названию, исполнителю, альбому;
  3. качает исходный звук без перекодирования (обычно Opus ~160 kbps -> .opus);
  4. прописывает теги из CSV и квадратную обложку альбома.

Прогресс в done_ytm.json (треки из done.json бота и albums.json тоже пропускаются), ошибки — в failed_ytm.txt.

    python ytm_download.py --limit 5        # тест
    python ytm_download.py                  # всё
    python ytm_download.py --retry-failed   # повторить ненайденное
"""
import argparse

from .. import spotify, state, ytmusic
from ..config import load_config
from ..library import load_tracks
from ..tagging import get_cover, set_track_number, tag
from ..util import BLOCK_RE, Stop, clean_error, run_parallel


def _existing(tracks, done, out_dir):
    """[(Track, путь)] для уже скачанных файлов, которые лежат в папке."""
    by_id = {t.tid: t for t in tracks}
    return [(by_id[tid], out_dir / name) for tid, name in done.items()
            if tid in by_id and (out_dir / name).exists()]


def _print_ok(i, total, item, res):
    print(f"[{i}/{total}] {res}", flush=True)


def _print_err(i, total, item, e):
    print(f"[{i}/{total}] {item[1].name}\n    ОШИБКА: {e}", flush=True)


def fix_covers(tracks, out_dir, workers):
    items = _existing(tracks, state.YTM_DONE.load(), out_dir)
    print(f"Перешиваю обложки: {len(items)} файлов", flush=True)

    def one(item):
        t, path = item
        cover = get_cover(t)
        if not cover:
            raise RuntimeError("обложка не скачалась")
        tag(path, t, cover, spotify.track_number(t.tid))
        return path.name

    run_parallel(one, items, workers, _print_ok, _print_err)


def fix_track_numbers(tracks, out_dir, workers):
    """Дописывает номер трека в альбоме в уже скачанные файлы, остальные теги не трогает."""
    items = _existing(tracks, {**state.BOT_DONE.load(), **state.YTM_DONE.load()}, out_dir)
    print(f"Проставляю номера треков: {len(items)} файлов", flush=True)

    def one(item):
        t, path = item
        track = spotify.track_number(t.tid)
        if not track:
            raise RuntimeError("номер не нашёлся на странице Spotify")
        set_track_number(path, track)
        return f"#{track} {path.name}"

    run_parallel(one, items, workers, _print_ok, _print_err)


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="только N треков (для теста)")
    ap.add_argument("--workers", type=int, default=3, help="параллельных загрузок")
    ap.add_argument("--retry-failed", action="store_true", help="повторить то, что не нашлось/упало")
    ap.add_argument("--fix-covers", action="store_true",
                    help="перешить теги и альбомные обложки из Spotify в уже скачанные файлы")
    ap.add_argument("--fix-track-numbers", action="store_true",
                    help="дописать номер трека в альбоме в уже скачанные файлы (и от бота тоже)")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cfg = load_config()
    out_dir = cfg.out_dir
    if cfg.cookies:
        print(f"Куки: {cfg.cookies_name}")
    else:
        print(f"Куки не найдены ({cfg.cookies_name}) — YouTube может не дать качать")

    tracks = load_tracks(cfg.tracks_file)
    if args.fix_track_numbers:
        return fix_track_numbers(tracks, out_dir, args.workers)
    if args.fix_covers:
        return fix_covers(tracks, out_dir, args.workers)

    if args.retry_failed:
        state.YTM_FAILED.reset()
    failed_ids = state.YTM_FAILED.ids(skip_blocked=True)
    have = state.downloaded()
    todo = [t for t in tracks if t.tid not in have and t.tid not in failed_ids]
    if args.limit:
        todo = todo[: args.limit]
    print(f"Всего {len(tracks)}, уже есть {len(have)}, "
          f"пропущено (ошибки) {len(failed_ids)}, в очереди {len(todo)}", flush=True)

    counts = {"ok": 0, "fail": 0}

    def on_ok(i, total, t, res):
        state.YTM_DONE.set(t.tid, res.name)
        counts["ok"] += 1
        print(f"[{i}/{total}] {t.label}\n    {res.describe()}", flush=True)

    def on_err(i, total, t, e):
        msg = clean_error(e)
        prefix = f"[{i}/{total}] {t.label}"
        if BLOCK_RE.search(msg):
            # дальше всё будет падать так же — не засоряем failed, останавливаемся
            print(f"{prefix}\n    YouTube блокирует: {msg[:200]}", flush=True)
            print("\nОстанавливаюсь. Выгрузи свежие cookies.txt (лучше из приватного окна) и запусти снова.")
            raise Stop
        counts["fail"] += 1
        state.YTM_FAILED.append(t.tid, t.label, f"{type(e).__name__}: {msg}")
        print(f"{prefix}\n    ОШИБКА: {msg}", flush=True)

    run_parallel(lambda t: ytmusic.process(t, out_dir, cfg.cookies), todo, args.workers, on_ok, on_err)

    print(f"\nГотово: скачано {counts['ok']}, ошибок {counts['fail']}. "
          f"Всего в библиотеке: {len(state.downloaded())}")
    if counts["fail"]:
        print(f"Ненайденное — в {state.YTM_FAILED.name}; можно докачать ботом или повторить --retry-failed")
