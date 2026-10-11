"""
Качает треки из Spotify-библиотеки через @Spotify_downloaderrr_bot.

Для каждого трека: шлёт боту ссылку -> бот сам качает (Auto Download) -> ждём аудио
-> сохраняем в out_dir. Бесплатный бот даёт 1 скачивание в ~90 сек и дневной лимит:
при упоре в лимит скрипт останавливается, завтра просто запусти снова.
Прогресс в done.json, можно прерывать и перезапускать.

    python download.py --limit 3     # тест на трёх треках
    python download.py               # всё
"""
import argparse
import asyncio

from .. import state
from ..bot.downloader import download_queue, from_history, open_client
from ..config import load_config
from ..library import load_tracks


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="download only N tracks (for testing)")
    ap.add_argument("--retry-failed", action="store_true", help="retry tracks that failed before")
    ap.add_argument("--from-history", action="store_true",
                    help="don't ask the bot, pick up audio it already sent from the chat history")
    ap.add_argument("--dry-run", action="store_true", help="with --from-history: only show matches")
    ap.add_argument("--account", type=int, default=1,
                    help="Telegram account number (each has its own session); even-numbered accounts go through the queue from the end")
    return ap.parse_args(argv)


async def run(args):
    cfg = load_config()
    cfg.require_telegram()
    tracks = load_tracks(cfg.tracks_file)
    have = state.downloaded()  # скачанное ytm_download.py и album.py боту не трогать

    if args.from_history:
        wanted = [t for t in tracks if t.tid not in have]
        async with open_client(cfg, args.account, robust=False) as client:
            bot = await client.get_entity(cfg.bot_username)
            await from_history(client, bot, wanted, cfg.out_dir, args.dry_run)
        return

    if args.retry_failed:
        state.BOT_FAILED.reset()
    failed_ids = state.BOT_FAILED.ids()
    todo = [t for t in tracks if t.tid not in have and t.tid not in failed_ids]
    if args.account % 2 == 0:
        todo.reverse()  # два аккаунта идут навстречу друг другу и не качают одно и то же
    if args.limit:
        todo = todo[: args.limit]
    print(f"Total {len(tracks)}, downloaded {len(have)}, skipped (errors) {len(failed_ids)}, queued {len(todo)}")
    print(f"About {len(todo) * cfg.cooldown / 3600:.1f} h, not counting the daily limit")

    async with open_client(cfg, args.account) as client:
        bot = await client.get_entity(cfg.bot_username)
        await download_queue(client, bot, cfg, todo, state.BOT_DONE, state.BOT_FAILED,
                             label=lambda i, t: f"[{i}/{len(todo)}] {t.label}")

    print(f"Downloaded in total: {len(state.downloaded())}. Errors are in {state.BOT_FAILED.name}")


def main(argv=None):
    asyncio.run(run(parse_args(argv)))
