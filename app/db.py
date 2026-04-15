from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterable

import aiosqlite


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Tool:
    id: int
    name: str
    serial: str | None
    is_active: bool
    current_object_id: int | None


@dataclass(frozen=True)
class Obj:
    id: int
    name: str


class Database:
    def __init__(self, db_path: str):
        self._db_path = db_path

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        db = await aiosqlite.connect(self._db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")
        try:
            yield db
        finally:
            await db.close()

    async def init(self) -> None:
        async with self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    tg_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS tools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    serial TEXT UNIQUE,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    current_object_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(current_object_id) REFERENCES objects(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tools_active ON tools(is_active);
                CREATE INDEX IF NOT EXISTS idx_tools_current_object ON tools(current_object_id);

                CREATE TABLE IF NOT EXISTS moves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id INTEGER NOT NULL,
                    from_object_id INTEGER,
                    to_object_id INTEGER,
                    moved_by_tg_id INTEGER NOT NULL,
                    moved_at TEXT NOT NULL,
                    note TEXT,
                    FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE,
                    FOREIGN KEY(from_object_id) REFERENCES objects(id) ON DELETE SET NULL,
                    FOREIGN KEY(to_object_id) REFERENCES objects(id) ON DELETE SET NULL,
                    FOREIGN KEY(moved_by_tg_id) REFERENCES users(tg_id) ON DELETE CASCADE
                );
                """
            )
            await db.execute(
                """
                UPDATE tools
                SET current_object_id = NULL
                WHERE is_active = 0 AND current_object_id IS NOT NULL;
                """
            )
            await db.commit()

    async def upsert_user(
        self, tg_id: int, full_name: str | None, username: str | None, is_admin: bool
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO users (tg_id, full_name, username, is_admin, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET
                  full_name=excluded.full_name,
                  username=excluded.username,
                  is_admin=excluded.is_admin;
                """,
                (tg_id, full_name, username, int(is_admin), _utcnow_iso()),
            )
            await db.commit()

    async def is_admin(self, tg_id: int) -> bool:
        async with self.connect() as db:
            cur = await db.execute("SELECT is_admin FROM users WHERE tg_id = ?;", (tg_id,))
            row = await cur.fetchone()
            return bool(row["is_admin"]) if row else False

    # ---- tools ----
    async def count_tools(
        self,
        *,
        with_serial: bool = False,
        only_active: bool = True,
        current_object_id: int | None = None,
    ) -> int:
        where = []
        if only_active:
            where.append("is_active = 1")
        if with_serial:
            where.append("serial IS NOT NULL AND serial <> ''")
        if current_object_id is not None:
            if current_object_id == -1:
                where.append("current_object_id IS NULL")
            else:
                where.append("current_object_id = ?")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        async with self.connect() as db:
            params: list[Any] = []
            if current_object_id is not None and current_object_id != -1:
                params.append(current_object_id)
            cur = await db.execute(f"SELECT COUNT(*) AS c FROM tools {where_sql};", params)
            row = await cur.fetchone()
            return int(row["c"])

    async def list_tools(
        self,
        *,
        offset: int,
        limit: int,
        with_serial: bool = False,
        only_active: bool = True,
        current_object_id: int | None = None,
        order_by: str = "name",
    ) -> list[Tool]:
        order_sql = {
            "name": "t.name COLLATE NOCASE ASC",
            "serial": "t.serial COLLATE NOCASE ASC, t.name COLLATE NOCASE ASC",
        }.get(order_by, "t.name COLLATE NOCASE ASC")

        where = []
        params: list[Any] = []
        if only_active:
            where.append("t.is_active = 1")
        if with_serial:
            where.append("t.serial IS NOT NULL AND t.serial <> ''")
        if current_object_id is not None:
            if current_object_id == -1:
                where.append("t.current_object_id IS NULL")
            else:
                where.append("t.current_object_id = ?")
                params.append(current_object_id)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
        SELECT t.id, t.name, t.serial, t.is_active, t.current_object_id
        FROM tools t
        {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?;
        """
        params.extend([limit, offset])
        async with self.connect() as db:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [
                Tool(
                    id=int(r["id"]),
                    name=str(r["name"]),
                    serial=str(r["serial"]) if r["serial"] is not None else None,
                    is_active=bool(r["is_active"]),
                    current_object_id=int(r["current_object_id"]) if r["current_object_id"] is not None else None,
                )
                for r in rows
            ]

    async def get_tool_by_serial(self, serial: str) -> Tool | None:
        serial = serial.strip()
        async with self.connect() as db:
            cur = await db.execute(
                "SELECT id, name, serial, is_active, current_object_id FROM tools WHERE serial=?;",
                (serial,),
            )
            r = await cur.fetchone()
            if not r:
                return None
            return Tool(
                id=int(r["id"]),
                name=str(r["name"]),
                serial=str(r["serial"]) if r["serial"] is not None else None,
                is_active=bool(r["is_active"]),
                current_object_id=int(r["current_object_id"]) if r["current_object_id"] is not None else None,
            )

    async def get_tool_by_id(self, tool_id: int) -> Tool | None:
        async with self.connect() as db:
            cur = await db.execute(
                "SELECT id, name, serial, is_active, current_object_id FROM tools WHERE id=?;",
                (tool_id,),
            )
            r = await cur.fetchone()
            if not r:
                return None
            return Tool(
                id=int(r["id"]),
                name=str(r["name"]),
                serial=str(r["serial"]) if r["serial"] is not None else None,
                is_active=bool(r["is_active"]),
                current_object_id=int(r["current_object_id"]) if r["current_object_id"] is not None else None,
            )

    async def create_or_update_tool(self, *, name: str, serial: str | None) -> int:
        name = name.strip()
        serial = serial.strip() if serial is not None else None
        if serial == "":
            serial = None
        async with self.connect() as db:
            # if serial exists: update name, set active
            if serial is not None:
                cur = await db.execute("SELECT id FROM tools WHERE serial = ?;", (serial,))
                row = await cur.fetchone()
                if row:
                    tool_id = int(row["id"])
                    await db.execute(
                        "UPDATE tools SET name=?, is_active=1 WHERE id=?;",
                        (name, tool_id),
                    )
                    await db.commit()
                    return tool_id

            cur = await db.execute(
                "INSERT INTO tools(name, serial, is_active, created_at) VALUES (?, ?, 1, ?);",
                (name, serial, _utcnow_iso()),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def set_tool_active(self, tool_id: int, is_active: bool) -> None:
        async with self.connect() as db:
            if is_active:
                await db.execute("UPDATE tools SET is_active=1 WHERE id=?;", (tool_id,))
            else:
                await db.execute(
                    "UPDATE tools SET is_active=0, current_object_id=NULL WHERE id=?;",
                    (tool_id,),
                )
            await db.commit()

    # ---- objects ----
    async def count_objects(self) -> int:
        async with self.connect() as db:
            cur = await db.execute("SELECT COUNT(*) AS c FROM objects;")
            row = await cur.fetchone()
            return int(row["c"])

    async def list_objects(self, *, offset: int, limit: int) -> list[Obj]:
        async with self.connect() as db:
            cur = await db.execute(
                """
                SELECT id, name FROM objects
                ORDER BY name COLLATE NOCASE ASC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            )
            rows = await cur.fetchall()
            return [Obj(id=int(r["id"]), name=str(r["name"])) for r in rows]

    async def create_object(self, name: str) -> int:
        name = name.strip()
        async with self.connect() as db:
            cur = await db.execute("INSERT INTO objects(name) VALUES (?);", (name,))
            await db.commit()
            return int(cur.lastrowid)

    async def rename_object(self, object_id: int, name: str) -> None:
        name = name.strip()
        async with self.connect() as db:
            await db.execute("UPDATE objects SET name=? WHERE id=?;", (name, object_id))
            await db.commit()

    async def get_object(self, object_id: int) -> Obj | None:
        async with self.connect() as db:
            cur = await db.execute("SELECT id, name FROM objects WHERE id=?;", (object_id,))
            r = await cur.fetchone()
            return Obj(id=int(r["id"]), name=str(r["name"])) if r else None

    # рџ‘‡ РќРћР’Р«Р™ РњР•РўРћР” - РґРѕР±Р°РІР»РµРЅ СЃСЋРґР°, РїРѕСЃР»Рµ get_object
    async def delete_object(self, object_id: int) -> tuple[bool, str]:
        """
        РЈРґР°Р»СЏРµС‚ РѕР±СЉРµРєС‚, РµСЃР»Рё РѕРЅ РЅРµ СЃРѕРґРµСЂР¶РёС‚ РёРЅСЃС‚СЂСѓРјРµРЅС‚РѕРІ.
        
        Returns:
            (success: bool, message: str)
        """
        async with self.connect() as db:
            # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё РёРЅСЃС‚СЂСѓРјРµРЅС‚С‹ РЅР° СЌС‚РѕРј РѕР±СЉРµРєС‚Рµ
            cur = await db.execute(
                "SELECT COUNT(*) as cnt FROM tools WHERE current_object_id = ? AND is_active = 1;",
                (object_id,)
            )
            row = await cur.fetchone()
            if row and row["cnt"] > 0:
                return False, f"РќРµР»СЊР·СЏ СѓРґР°Р»РёС‚СЊ: РЅР° РѕР±СЉРµРєС‚Рµ РЅР°С…РѕРґРёС‚СЃСЏ {row['cnt']} РёРЅСЃС‚СЂСѓРјРµРЅС‚(РѕРІ). РЎРЅР°С‡Р°Р»Р° РїРµСЂРµРјРµСЃС‚РёС‚Рµ РёС…."
            
            # РџСЂРѕРІРµСЂСЏРµРј, РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ Р»Рё РѕР±СЉРµРєС‚ РІ РёСЃС‚РѕСЂРёРё РїРµСЂРµРјРµС‰РµРЅРёР№
            cur = await db.execute(
                "SELECT COUNT(*) as cnt FROM moves WHERE from_object_id = ? OR to_object_id = ?;",
                (object_id, object_id)
            )
            row = await cur.fetchone()
            has_history = row and row["cnt"] > 0
            
            # РЈРґР°Р»СЏРµРј РѕР±СЉРµРєС‚
            await db.execute("DELETE FROM objects WHERE id = ?;", (object_id,))
            await db.commit()
            
            if has_history:
                return True, "РћР±СЉРµРєС‚ СѓРґР°Р»С‘РЅ. РџСЂРёРјРµС‡Р°РЅРёРµ: РѕРЅ РѕСЃС‚Р°Р»СЃСЏ РІ РёСЃС‚РѕСЂРёРё РїРµСЂРµРјРµС‰РµРЅРёР№ (СЃРѕРіР»Р°СЃРЅРѕ РЅР°СЃС‚СЂРѕР№РєР°Рј РІРЅРµС€РЅРёС… РєР»СЋС‡РµР№)."
            else:
                return True, "РћР±СЉРµРєС‚ СѓСЃРїРµС€РЅРѕ СѓРґР°Р»С‘РЅ."

    # ---- move tool ----
    async def move_tool(
        self,
        *,
        tool_id: int,
        to_object_id: int | None,
        moved_by_tg_id: int,
        note: str | None = None,
    ) -> None:
        async with self.connect() as db:
            cur = await db.execute("SELECT current_object_id FROM tools WHERE id=?;", (tool_id,))
            row = await cur.fetchone()
            if not row:
                raise ValueError("Tool not found")
            from_object_id = int(row["current_object_id"]) if row["current_object_id"] is not None else None

            await db.execute(
                "UPDATE tools SET current_object_id=? WHERE id=?;",
                (to_object_id, tool_id),
            )
            await db.execute(
                """
                INSERT INTO moves(tool_id, from_object_id, to_object_id, moved_by_tg_id, moved_at, note)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (tool_id, from_object_id, to_object_id, moved_by_tg_id, _utcnow_iso(), note),
            )
            await db.commit()

    # ---- CSV export helpers ----
    async def export_tools_rows(self) -> Iterable[tuple[Any, ...]]:
        async with self.connect() as db:
            cur = await db.execute(
                """
                SELECT t.id, t.name, t.serial, t.is_active, o.name AS object_name
                FROM tools t
                LEFT JOIN objects o ON o.id = t.current_object_id
                ORDER BY t.name COLLATE NOCASE ASC;
                """
            )
            rows = await cur.fetchall()
            for r in rows:
                yield (r["id"], r["name"], r["serial"], r["is_active"], r["object_name"])
