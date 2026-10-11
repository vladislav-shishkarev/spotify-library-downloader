"""Настройки из config.ini."""
import configparser
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# личные файлы: прогресс, ошибки, сессии телеги, куки, CSV из exportify — всё, что не код
DATA = ROOT / "data"


@dataclass
class Config:
    tracks_file: Path
    out_dir: Path
    cookies: Path | None  # cookies.txt (Netscape) для YouTube, None — если файла нет
    cookies_name: str
    api_id: int
    api_hash: str
    bot_username: str
    cooldown: float  # минимум секунд между скачиваниями ботом
    timeout: float  # сколько ждать файл от бота

    def require_telegram(self):
        if not self.api_id or "PASTE" in self.api_hash:
            raise SystemExit("Заполни api_id / api_hash в config.ini (https://my.telegram.org)")

    @staticmethod
    def session_path(account: int) -> str:
        """У каждого телеграм-аккаунта своя сессия: session, session2, ..."""
        return str(DATA / ("session" if account == 1 else f"session{account}"))


def load_config() -> Config:
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";",))
    if not cfg.read(ROOT / "config.ini", encoding="utf-8"):
        raise SystemExit("Нет config.ini — скопируй config.example.ini в config.ini и заполни")
    DATA.mkdir(exist_ok=True)
    out_dir = ROOT / cfg.get("run", "out_dir", fallback="music")
    out_dir.mkdir(exist_ok=True)
    # tracks_file и cookies — относительно data/, out_dir — относительно корня проекта
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
