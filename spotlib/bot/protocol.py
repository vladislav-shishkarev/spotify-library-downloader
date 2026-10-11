"""Parsing bot messages: what it replied and whether it sent the right track."""
import re

from ..library import Track

WAIT_RE = re.compile(r"wait\s+(\d+)\s*sec", re.I)  # "please wait 22 seconds"
LIMIT_RE = re.compile(r"\blimit|daily|today|quota|per day", re.I)  # daily limit (the exact text is unknown)
# "⚠️ Failed to download X. Try again later or /upgrade to premium!" — the bot will not give this track
FAIL_RE = re.compile(r"failed to download|could ?n.?t download|unable to download", re.I)
BUSY_RE = re.compile(r"being downloaded|downloading|uploading|queue", re.I)
EXTRAS_RE = re.compile(r"\(.*?\)|\[.*?\]| - .*")  # (feat. ...), [Live], " - Remastered"
VERSION_WORDS = {"remix", "rmx", "mix", "live", "acoustic", "instrumental", "edit", "vip", "bootleg",
                 "slowed", "sped", "reverb", "nightcore", "cover", "version", "remaster", "remastered"}


class DailyLimit(Exception):
    pass


def words(s):
    return set(re.findall(r"\w+", (s or "").lower()))


def _file_words(msg):
    return words(msg.file.name) | words(msg.file.title) | words(msg.file.performer)


def audio_matches(msg, title):
    """Rough check that this is our track and not a late file for the previous one."""
    want = words(EXTRAS_RE.sub("", title or ""))
    if not want:
        return True
    return len(want & _file_words(msg)) >= max(1, len(want) // 2)


def history_match(msg, t: Track):
    """Strict check for the history search: all title words, the artist and the same version."""
    want = words(EXTRAS_RE.sub("", t.name))
    got = _file_words(msg)
    artist = words(" ".join(t.artists))
    return (bool(want) and want <= got and bool(artist & got)
            and VERSION_WORDS & got == VERSION_WORDS & words(t.name))


def download_button(msg):
    """Text of the download button in the card: 'Download Track' (search) or 'Download Song' (link)."""
    for row in msg.buttons or []:
        for b in row:
            low = b.text.lower()
            if "download" in low and ("track" in low or "song" in low):
                return b.text
    return None


def is_audio(msg):
    return bool(msg.audio or (msg.document and (msg.file.mime_type or "").startswith("audio")))


def describe(msgs):
    """Short description of the bot's latest messages — for debugging after a timeout."""
    parts = [f"[{(m.raw_text or '').replace(chr(10), ' ')[:120]}]" for m in msgs[:3] if not m.out]
    return " | ".join(parts) or "the bot did not reply"
