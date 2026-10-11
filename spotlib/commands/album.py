"""
Качает альбом целиком по ссылке Spotify — даже если его нет в поиске (страница по ссылке открывается).

Метаданные (названия, длительность, номера, дата) — со страниц альбома и треков Spotify,
звук — с YouTube Music как в ytm_download.py, то, что там не нашлось, — через бота (--bot).
Скачанное пишется в albums.json: sync.py такие треки не удаляет, даже если их нет в лайках.

    python album.py https://open.spotify.com/album/... --dry-run   # показать треклист
    python album.py https://open.spotify.com/album/...             # скачать с YouTube Music
    python album.py https://open.spotify.com/album/... --bot       # докачать остальное ботом
"""
import argparse
import asyncio

from .. import state, ytmusic
from ..bot.downloader import download_queue, open_client
from ..config import Config, load_config
from ..spotify import load_album
from ..util import BLOCK_RE, Stop, clean_error, run_parallel


def via_ytm(todo, cfg: Config, workers):
    """Возвращает, сколько скачалось."""
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
        print(f"#{n} {t.label}\n    ОШИБКА: {msg}", flush=True)
        if BLOCK_RE.search(msg):
            print("\nYouTube блокирует — обнови cookies.txt и запусти снова.")
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
    ap.add_argument("url", help="ссылка на альбом Spotify")
    ap.add_argument("--dry-run", action="store_true", help="только показать треклист")
    ap.add_argument("--workers", type=int, default=3, help="параллельных загрузок с YouTube Music")
    ap.add_argument("--bot", action="store_true", help="качать через телеграм-бота, а не YouTube Music")
    ap.add_argument("--account", type=int, default=1, help="с --bot: номер телеграм-аккаунта")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cfg = load_config()

    album, tracks = load_album(args.url)
    have = state.downloaded()
    print(f"{album} ({tracks[0][0].year if tracks else ''}), треков: {len(tracks)}")
    todo = []
    for t, n in tracks:
        status = "уже есть" if t.tid in have else "в очереди"
        print(f"  #{n:>2} {t.label} [{int(t.duration) // 60}:{int(t.duration) % 60:02d}] — {status}")
        if t.tid not in have:
            todo.append((t, n))

    if args.dry_run or not todo:
        print("\n--dry-run: ничего не скачивал" if args.dry_run else "\nВесь альбом уже скачан")
        return

    print(f"\nКачаю {len(todo)} через {'бота' if args.bot else 'YouTube Music'}...\n", flush=True)
    if args.bot:
        asyncio.run(via_bot(todo, cfg, args.account))
    else:
        ok = via_ytm(todo, cfg, args.workers)
        if ok < len(todo):
            print(f"\nНе нашлось {len(todo) - ok} — докачай ботом: python album.py {args.url} --bot")
