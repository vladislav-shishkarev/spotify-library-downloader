"""Показывает последние сообщения в чате с ботом (текст, кнопки, файлы) — для отладки.

    python peek.py 15
"""
import asyncio
import sys

from ..bot.downloader import open_client
from ..config import load_config


async def run(n):
    cfg = load_config()
    async with open_client(cfg, robust=False) as client:
        bot = await client.get_entity(cfg.bot_username)
        for m in reversed(await client.get_messages(bot, limit=n)):
            who = "Я " if m.out else "БОТ"
            print(f"--- #{m.id} {who} {m.date:%H:%M:%S}{' (изм.)' if m.edit_date else ''}")
            if m.raw_text:
                print("   ", m.raw_text.replace("\n", "\n    ")[:400])
            if m.file:
                print(f"    [файл] {m.file.mime_type} {m.file.name} {m.file.size} байт")
            for row in m.buttons or []:
                print("    [кнопки]", " | ".join(f"{b.text!r}" + (f" -> {b.url}" if getattr(b, "url", None) else "")
                                              for b in row))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    asyncio.run(run(int(argv[0]) if argv else 15))
