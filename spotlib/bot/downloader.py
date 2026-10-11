"""Скачивание трека ботом: шлём ссылку -> бот сам качает (Auto Download) -> ждём аудио -> Opus с тегами."""
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

ATTEMPTS = 2  # сколько раз пробовать трек, прежде чем записать в failed


def open_client(cfg: Config, account=1, robust=True) -> TelegramClient:
    """Клиент для `async with`. robust: при пропаже сети переподключаться бесконечно,
    а не сдаваться после 5 попыток."""
    cfg.require_telegram()
    extra = {"connection_retries": -1, "retry_delay": 10} if robust else {}
    return TelegramClient(cfg.session_path(account), cfg.api_id, cfg.api_hash, **extra)


def _convert(part: Path, t: Track) -> Path:
    """Файл от бота -> Opus с тегами и обложкой из Spotify, как у YouTube Music.
    Для треков без метаданных (.txt со ссылками) остаются теги бота."""
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
    part = out_dir / f"{t.tid}.part"  # чтобы при обрыве не оставался битый файл
    try:
        await audio.download_media(file=str(part))
        opus = await asyncio.to_thread(_convert, part, t)
    finally:
        part.unlink(missing_ok=True)
    target = unique_target(out_dir, base, t.tid, ".opus")
    opus.replace(target)
    return target.name


async def process(client, bot, t: Track, out_dir: Path, timeout: float) -> str:
    """Один трек через бота -> имя файла в out_dir."""
    sent_url = f"https://open.spotify.com/track/{t.tid}"
    for _ in range(4):  # повторная отправка после "please wait N seconds"
        sent = await client.send_message(bot, sent_url)
        print("    отправил ссылку, жду файл...", flush=True)
        start = time.monotonic()
        clicked = busy = False
        wait_s = None
        msgs = []
        while time.monotonic() - start < timeout:
            await asyncio.sleep(3)
            msgs = await client.get_messages(bot, limit=20, min_id=sent.id)
            card = None
            for m in reversed(msgs):  # от старых к новым
                if m.out:
                    continue
                if is_audio(m):
                    if audio_matches(m, t.name):
                        print("    аудио пришло, качаю...", flush=True)
                        return await save(m, t, out_dir)
                    continue  # опоздавший предыдущий трек
                text = m.raw_text or ""
                if download_button(m):
                    card = m
                    continue
                if w := WAIT_RE.search(text):
                    wait_s = int(w.group(1))
                elif FAIL_RE.search(text):
                    raise RuntimeError("бот не смог скачать: " + text.replace("\n", " ")[:150])
                elif LIMIT_RE.search(text):
                    raise DailyLimit(text.replace("\n", " ")[:300])
                elif BUSY_RE.search(text):
                    busy = True
            if wait_s is not None:
                break
            # авто-загрузка не стартовала — жмём кнопку сами
            if card and not busy and not clicked and time.monotonic() - start > 20:
                print("    авто-загрузка не началась, жму кнопку...", flush=True)
                clicked = True
                try:
                    await card.click(text=download_button(card))
                except errors.BotResponseTimeoutError:
                    pass
        if wait_s is None:
            raise RuntimeError("нет аудио за отведённое время: " + describe(msgs))
        print(f"    бот просит подождать {wait_s} сек", flush=True)
        await asyncio.sleep(wait_s + 5)
    raise RuntimeError("бот всё время просит подождать")


async def _reconnect(client):
    while not client.is_connected():
        try:
            await client.connect()
        except (ConnectionError, OSError):
            await asyncio.sleep(30)


async def download_queue(client, bot, cfg: Config, todo, store: JsonStore, failed: FailedLog,
                         label=lambda i, t: t.label):
    """Качает todo ([Track]) по очереди, не чаще одного раза в cfg.cooldown секунд.
    Успех пишется в store, ошибки — в failed. label(номер, трек) — заголовок для вывода.
    При дневном лимите бота останавливается."""
    out_dir, cooldown, timeout = cfg.out_dir, cfg.cooldown, cfg.timeout
    last_start = 0.0
    for i, t in enumerate(todo, 1):
        print(label(i, t), flush=True)
        if t.tid in state.downloaded():  # второй аккаунт или ytm_download успели раньше
            print("    уже скачан другим аккаунтом")
            continue
        attempt = 0
        while attempt < ATTEMPTS:
            await asyncio.sleep(max(0.0, last_start + cooldown - time.monotonic()))
            last_start = time.monotonic()
            try:
                name = await process(client, bot, t, out_dir, timeout)
            except errors.FloodWaitError as e:
                print(f"    флуд-лимит телеги, жду {e.seconds} сек")
                await asyncio.sleep(e.seconds + 5)
                continue
            except DailyLimit as e:
                print(f"\nПохоже, дневной лимит бота. Ответ бота: {e}")
                print("Прогресс сохранён — запусти завтра ещё раз, продолжит с этого трека.")
                return
            except (ConnectionError, OSError) as e:
                # проблема с сетью, а не с треком — попытку не засчитываем
                print(f"    обрыв связи ({e}), переподключаюсь...", flush=True)
                await _reconnect(client)
                continue
            except Exception as e:
                attempt += 1
                if attempt == ATTEMPTS:
                    print(f"    ОШИБКА: {e}")
                    failed.append(t.tid, t.label, e)
                else:
                    print(f"    не вышло ({e}), ещё попытка")
                continue
            if store.claim(t.tid, name):
                state.YTM_FAILED.drop(t.tid)  # не нашлось на YTM, но бот скачал
                print(f"    -> {name}")
            else:  # тот же трек успел скачать другой аккаунт — дубль не нужен
                (out_dir / name).unlink(missing_ok=True)
                print("    уже скачан другим аккаунтом, дубль удалён")
            break


async def from_history(client, bot, wanted, out_dir: Path, dry_run: bool):
    """Забирает из истории чата с ботом уже присланные аудио для недостающих треков."""
    left = list(wanted)
    found = 0
    print(f"Ищу в истории чата {len(left)} треков...", flush=True)
    async for m in client.iter_messages(bot):  # от новых к старым
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
    print(f"\nНайдено в истории: {found}, осталось скачать: {len(left)}"
          + (" (--dry-run: ничего не скачивал)" if dry_run else ""))
