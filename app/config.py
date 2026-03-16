from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _parse_admin_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            # silently ignore bad values
            continue
    return out


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    db_path: str


def load_settings() -> Settings:
    load_dotenv(override=False)

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Create .env (see README.md)")

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS"))
    db_path = os.getenv("DB_PATH", "").strip() or os.path.abspath("inventory.sqlite3")

    return Settings(bot_token=bot_token, admin_ids=admin_ids, db_path=db_path)

