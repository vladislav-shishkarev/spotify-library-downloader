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
    print(f"[{i}/{total}] {item[1].name}\n    ERROR: {e}", flush=True)


def fix_covers(tracks, out_dir, workers):
    items = _existing(tracks, state.YTM_DONE.load(), out_dir)
    print(f"Re-tagging covers: {len(items)} files", flush=True)

    def one(item):
        t, path = item
        cover = get_cover(t)
        if not cover:
            raise RuntimeError("cover download failed")
        tag(path, t, cover, spotify.track_number(t.tid))
        return path.name

    run_parallel(one, items, workers, _print_ok, _print_err)


def fix_track_numbers(tracks, out_dir, workers):
    """Дописывает номер трека в альбоме в уже скачанные файлы, остальные теги не трогает."""
    items = _existing(tracks, {**state.BOT_DONE.load(), **state.YTM_DONE.load()}, out_dir)
    print(f"Setting track numbers: {len(items)} files", flush=True)

    def one(item):
        t, path = item
        track = spotify.track_number(t.tid)
        if not track:
            raise RuntimeError("track number not found on the Spotify page")
        set_track_number(path, track)
        return f"#{track} {path.name}"

    run_parallel(one, items, workers, _print_ok, _print_err)


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only N tracks (for testing)")
    ap.add_argument("--workers", type=int, default=3, help="parallel downloads")
    ap.add_argument("--retry-failed", action="store_true", help="retry tracks that weren't found or failed")
    ap.add_argument("--fix-covers", action="store_true",
                    help="rewrite tags and Spotify album covers in already downloaded files")
    ap.add_argument("--fix-track-numbers", action="store_true",
                    help="add album track numbers to already downloaded files (including the bot's)")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cfg = load_config()
    out_dir = cfg.out_dir
    if cfg.cookies:
        print(f"Cookies: {cfg.cookies_name}")
    else:
        print(f"Cookies not found (data/{cfg.cookies_name}) — YouTube may block downloads")

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
    print(f"Total {len(tracks)}, already have {len(have)}, "
          f"skipped (errors) {len(failed_ids)}, queued {len(todo)}", flush=True)

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
            print(f"{prefix}\n    YouTube is blocking: {msg[:200]}", flush=True)
            print("\nStopping. Export fresh cookies.txt (preferably from a private window) and run again.")
            raise Stop
        counts["fail"] += 1
        state.YTM_FAILED.append(t.tid, t.label, f"{type(e).__name__}: {msg}")
        print(f"{prefix}\n    ERROR: {msg}", flush=True)

    run_parallel(lambda t: ytmusic.process(t, out_dir, cfg.cookies), todo, args.workers, on_ok, on_err)

    print(f"\nDone: downloaded {counts['ok']}, errors {counts['fail']}. "
          f"Total in library: {len(state.downloaded())}")
    if counts["fail"]:
        print(f"Tracks not found are listed in {state.YTM_FAILED.name}; get them with the bot or retry with --retry-failed")
