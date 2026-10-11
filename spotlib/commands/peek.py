"""Shows the latest messages in the bot chat (text, buttons, files) — for debugging.

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
            who = "ME " if m.out else "BOT"
            print(f"--- #{m.id} {who} {m.date:%H:%M:%S}{' (edited)' if m.edit_date else ''}")
            if m.raw_text:
                print("   ", m.raw_text.replace("\n", "\n    ")[:400])
            if m.file:
                print(f"    [file] {m.file.mime_type} {m.file.name} {m.file.size} bytes")
            for row in m.buttons or []:
                print("    [buttons]", " | ".join(f"{b.text!r}" + (f" -> {b.url}" if getattr(b, "url", None) else "")
                                              for b in row))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    asyncio.run(run(int(argv[0]) if argv else 15))
