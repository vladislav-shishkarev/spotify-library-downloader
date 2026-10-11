"""
Downloads a whole album by its Spotify link — even if it isn't in search (the page still opens by link).

Metadata (titles, durations, numbers, date) comes from the Spotify album and track pages,
audio comes from YouTube Music like in ytm_download.py; what isn't found there — via the bot (--bot).
Downloads are saved to albums.json: sync.py doesn't delete these tracks, even if they aren't liked.

    python album.py https://open.spotify.com/album/... --dry-run   # show the tracklist
    python album.py https://open.spotify.com/album/...             # download from YouTube Music
    python album.py https://open.spotify.com/album/... --bot       # download the rest with the bot
"""
import argparse
import asyncio

from .. import state, ytmusic
from ..bot.downloader import download_queue, open_client
from ..config import Config, load_config
from ..spotify import load_album
from ..util import BLOCK_RE, Stop, clean_error, run_parallel


def via_ytm(todo, cfg: Config, workers):
    """Returns how many tracks were downloaded."""
    ok = 0

    def on_ok(i, total, item, res):
        nonlocal ok
        t, n = item
        state.ALBUMS_DONE.set(t.tid, res.name)
        ok += 1
        print(f"#{n} {t.label}\n    {res.describe()}", flush=True)

    def on_err(i, total, item, e):
        t, n = item
        msg = clean_error(e)
        state.ALBUMS_FAILED.append(t.tid, t.label, f"{type(e).__name__}: {msg}")
        print(f"#{n} {t.label}\n    ERROR: {msg}", flush=True)
        if BLOCK_RE.search(msg):
            print("\nYouTube is blocking — refresh cookies.txt and run again.")
            raise Stop

    run_parallel(lambda item: ytmusic.process(item[0], cfg.out_dir, cfg.cookies), todo, workers, on_ok, on_err)
    return ok


async def via_bot(todo, cfg: Config, account):
    async with open_client(cfg, account) as client:
        bot = await client.get_entity(cfg.bot_username)
        nums = {t.tid: n for t, n in todo}
        await download_queue(client, bot, cfg, [t for t, _ in todo], state.ALBUMS_DONE, state.ALBUMS_FAILED,
                             label=lambda i, t: f"#{nums[t.tid]} {t.label}")


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="Spotify album link")
    ap.add_argument("--dry-run", action="store_true", help="only show the tracklist")
    ap.add_argument("--workers", type=int, default=3, help="parallel downloads from YouTube Music")
    ap.add_argument("--bot", action="store_true", help="download via the Telegram bot instead of YouTube Music")
    ap.add_argument("--account", type=int, default=1, help="with --bot: Telegram account number")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cfg = load_config()

    album, tracks = load_album(args.url)
    have = state.downloaded()
    print(f"{album} ({tracks[0][0].year if tracks else ''}), tracks: {len(tracks)}")
    todo = []
    for t, n in tracks:
        status = "already have" if t.tid in have else "queued"
        print(f"  #{n:>2} {t.label} [{int(t.duration) // 60}:{int(t.duration) % 60:02d}] — {status}")
        if t.tid not in have:
            todo.append((t, n))

    if args.dry_run or not todo:
        print("\n--dry-run: nothing downloaded" if args.dry_run else "\nThe whole album is already downloaded")
        return

    print(f"\nDownloading {len(todo)} via {'the bot' if args.bot else 'YouTube Music'}...\n", flush=True)
    if args.bot:
        asyncio.run(via_bot(todo, cfg, args.account))
    else:
        ok = via_ytm(todo, cfg, args.workers)
        if ok < len(todo):
            print(f"\n{len(todo) - ok} not found — get them with the bot: python album.py {args.url} --bot")
