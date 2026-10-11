"""Settings from config.ini."""
import configparser
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# personal files: progress, errors, Telegram sessions, cookies, CSV from exportify — everything that is not code
DATA = ROOT / "data"


@dataclass
class Config:
    tracks_file: Path
    out_dir: Path
    cookies: Path | None  # cookies.txt (Netscape) for YouTube, None if the file doesn't exist
    cookies_name: str
    api_id: int
    api_hash: str
    bot_username: str
    cooldown: float  # minimum seconds between bot downloads
    timeout: float  # how long to wait for a file from the bot

    def require_telegram(self):
        if not self.api_id or "PASTE" in self.api_hash:
            raise SystemExit("Fill in api_id / api_hash in config.ini (https://my.telegram.org)")

    @staticmethod
    def session_path(account: int) -> str:
        """Each Telegram account has its own session: session, session2, ..."""
        return str(DATA / ("session" if account == 1 else f"session{account}"))


def load_config() -> Config:
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";",))
    if not cfg.read(ROOT / "config.ini", encoding="utf-8"):
        raise SystemExit("config.ini not found — copy config.example.ini to config.ini and fill it in")
    DATA.mkdir(exist_ok=True)
    out_dir = ROOT / cfg.get("run", "out_dir", fallback="music")
    out_dir.mkdir(exist_ok=True)
    # tracks_file and cookies are relative to data/, out_dir is relative to the project root
    cookies = DATA / cfg.get("run", "cookies", fallback="cookies.txt")
    return Config(
        tracks_file=DATA / cfg.get("run", "tracks_file", fallback="liked_songs.csv"),
        out_dir=out_dir,
        cookies=cookies if cookies.is_file() else None,
        cookies_name=cookies.name,
        api_id=cfg.getint("telegram", "api_id", fallback=0),
        api_hash=cfg.get("telegram", "api_hash", fallback=""),
        bot_username=cfg.get("bot", "username", fallback=""),
        cooldown=cfg.getfloat("run", "cooldown", fallback=95),
        timeout=cfg.getfloat("run", "timeout", fallback=600),
    )
