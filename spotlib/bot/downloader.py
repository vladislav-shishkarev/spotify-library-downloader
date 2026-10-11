"""Downloading a track with the bot: send a link -> the bot downloads it (Auto Download) -> wait for audio -> Opus with tags."""
import asyncio
import time
from pathlib import Path

from telethon import TelegramClient, errors
from telethon.tl.types import DocumentAttributeAudio

from .. import state
from ..config import Config
from ..ffmpeg import to_opus
from ..library import Track
from ..state import FailedLog, JsonStore
from ..tagging import tag_full
from ..util import unique_target
from .protocol import (BUSY_RE, FAIL_RE, LIMIT_RE, WAIT_RE, DailyLimit, audio_matches, describe,
                       download_button, history_match, is_audio)

ATTEMPTS = 2  # how many times to try a track before writing it to failed


def open_client(cfg: Config, account=1, robust=True) -> TelegramClient:
    """Client for `async with`. robust: if the network drops, reconnect forever
    instead of giving up after 5 attempts."""
    cfg.require_telegram()
    extra = {"connection_retries": -1, "retry_delay": 10} if robust else {}
    return TelegramClient(cfg.session_path(account), cfg.api_id, cfg.api_hash, **extra)


def _convert(part: Path, t: Track) -> Path:
    """File from the bot -> Opus with tags and a Spotify cover, same as YouTube Music.
    Tracks without metadata (.txt with links) keep the bot's tags."""
    out = to_opus(part)
    if t.has_meta:
        tag_full(out, t)
    return out


async def save(audio, t: Track, out_dir: Path) -> str:
    if t.has_meta:
        base = t.label
    else:
        performer = title = None
        for a in audio.document.attributes:
            if isinstance(a, DocumentAttributeAudio):
                performer, title = a.performer, a.title
        base = f"{performer} - {title}" if performer and title else Path(audio.file.name or t.tid).stem
    part = out_dir / f"{t.tid}.part"  # so a broken file isn't left behind if the download stops
    try:
        await audio.download_media(file=str(part))
        opus = await asyncio.to_thread(_convert, part, t)
    finally:
        part.unlink(missing_ok=True)
    target = unique_target(out_dir, base, t.tid, ".opus")
    opus.replace(target)
    return target.name


async def process(client, bot, t: Track, out_dir: Path, timeout: float) -> str:
    """One track via the bot -> file name in out_dir."""
    sent_url = f"https://open.spotify.com/track/{t.tid}"
    for _ in range(4):  # send again after "please wait N seconds"
        sent = await client.send_message(bot, sent_url)
        print("    link sent, waiting for the file...", flush=True)
        start = time.monotonic()
        clicked = busy = False
        wait_s = None
        msgs = []
        while time.monotonic() - start < timeout:
            await asyncio.sleep(3)
            msgs = await client.get_messages(bot, limit=20, min_id=sent.id)
            card = None
            for m in reversed(msgs):  # from old to new
                if m.out:
                    continue
                if is_audio(m):
                    if audio_matches(m, t.name):
                        print("    audio received, downloading...", flush=True)
                        return await save(m, t, out_dir)
                    continue  # a late file for the previous track
                text = m.raw_text or ""
                if download_button(m):
                    card = m
                    continue
                if w := WAIT_RE.search(text):
                    wait_s = int(w.group(1))
                elif FAIL_RE.search(text):
                    raise RuntimeError("the bot failed to download: " + text.replace("\n", " ")[:150])
                elif LIMIT_RE.search(text):
                    raise DailyLimit(text.replace("\n", " ")[:300])
                elif BUSY_RE.search(text):
                    busy = True
            if wait_s is not None:
                break
            # auto-download didn't start — press the button ourselves
            if card and not busy and not clicked and time.monotonic() - start > 20:
                print("    auto-download didn't start, pressing the button...", flush=True)
                clicked = True
                try:
                    await card.click(text=download_button(card))
                except errors.BotResponseTimeoutError:
                    pass
        if wait_s is None:
            raise RuntimeError("no audio within the timeout: " + describe(msgs))
        print(f"    the bot asks to wait {wait_s} s", flush=True)
        await asyncio.sleep(wait_s + 5)
    raise RuntimeError("the bot keeps asking to wait")


async def _reconnect(client):
    while not client.is_connected():
        try:
            await client.connect()
        except (ConnectionError, OSError):
            await asyncio.sleep(30)


async def download_queue(client, bot, cfg: Config, todo, store: JsonStore, failed: FailedLog,
                         label=lambda i, t: t.label):
    """Downloads todo ([Track]) one by one, at most once every cfg.cooldown seconds.
    Successes go to store, errors go to failed. label(number, track) is the heading to print.
    Stops when the bot hits its daily limit."""
    out_dir, cooldown, timeout = cfg.out_dir, cfg.cooldown, cfg.timeout
    last_start = 0.0
    for i, t in enumerate(todo, 1):
        print(label(i, t), flush=True)
        if t.tid in state.downloaded():  # a second account or ytm_download got it first
            print("    already downloaded (by another account or from YouTube Music)")
            continue
        attempt = 0
        while attempt < ATTEMPTS:
            await asyncio.sleep(max(0.0, last_start + cooldown - time.monotonic()))
            last_start = time.monotonic()
            try:
                name = await process(client, bot, t, out_dir, timeout)
            except errors.FloodWaitError as e:
                print(f"    Telegram flood limit, waiting {e.seconds} s")
                await asyncio.sleep(e.seconds + 5)
                continue
            except DailyLimit as e:
                print(f"\nLooks like the bot's daily limit. Bot reply: {e}")
                print("Progress is saved — run again tomorrow, it will continue from this track.")
                return
            except (ConnectionError, OSError) as e:
                # a network problem, not a track problem — don't count this attempt
                print(f"    connection lost ({e}), reconnecting...", flush=True)
                await _reconnect(client)
                continue
            except Exception as e:
                attempt += 1
                if attempt == ATTEMPTS:
                    print(f"    ERROR: {e}")
                    failed.append(t.tid, t.label, e)
                else:
                    print(f"    failed ({e}), retrying")
                continue
            if store.claim(t.tid, name):
                state.YTM_FAILED.drop(t.tid)  # not found on YTM, but the bot downloaded it
                print(f"    -> {name}")
            else:  # another account already downloaded this track — we don't need a duplicate
                (out_dir / name).unlink(missing_ok=True)
                print("    already downloaded by another account, duplicate removed")
            break


async def from_history(client, bot, wanted, out_dir: Path, dry_run: bool):
    """Takes audio the bot already sent from the chat history for missing tracks."""
    left = list(wanted)
    found = 0
    print(f"Searching the chat history for {len(left)} tracks...", flush=True)
    async for m in client.iter_messages(bot):  # from new to old
        if m.out or not is_audio(m):
            continue
        for t in left:
            if history_match(m, t):
                left.remove(t)
                found += 1
                got = f"{m.file.performer} - {m.file.title}" if m.file.title else m.file.name
                print(f"  {t.label}\n    <- {got}", flush=True)
                if not dry_run:
                    state.BOT_DONE.set(t.tid, await save(m, t, out_dir))
                    state.YTM_FAILED.drop(t.tid)
                break
        if not left:
            break
    print(f"\nFound in history: {found}, still to download: {len(left)}"
          + (" (--dry-run: nothing downloaded)" if dry_run else ""))
