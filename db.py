"""Database layer: Postgres (Neon) when DATABASE_URL is set, SQLite otherwise.

All queries are written with '?' placeholders; they are translated to '%s'
automatically for Postgres. Every table has an integer `id` primary key so
inserts can always return the new id.
"""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.environ.get("SQLITE_PATH") or os.path.join(BASE_DIR, "devx.db")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
IS_PG = DATABASE_URL.startswith("postgresql://")

if IS_PG:
    import psycopg
    from psycopg.rows import dict_row

    IntegrityError = (psycopg.IntegrityError, sqlite3.IntegrityError)
else:
    IntegrityError = (sqlite3.IntegrityError,)


def translate(sql: str) -> str:
    """SQLite-style SQL (? placeholders) -> psycopg style."""
    sql = sql.replace("%", "%%")
    return sql.replace("?", "%s")


def adapt_schema(sql: str) -> str:
    if not IS_PG:
        return sql
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return sql.replace(" BLOB", " BYTEA")


class _Cursor:
    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class Conn:
    def __init__(self):
        if IS_PG:
            self.raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            self.raw = sqlite3.connect(SQLITE_PATH)
            self.raw.row_factory = sqlite3.Row
            self.raw.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql, params=()):
        params = tuple(params)
        if not IS_PG:
            cur = self.raw.execute(sql, params)
            return _Cursor(cur, cur.lastrowid)
        sql = translate(sql)
        is_insert = sql.lstrip().upper().startswith("INSERT")
        if is_insert and "RETURNING" not in sql.upper():
            sql += " RETURNING id"
        cur = self.raw.execute(sql, params)
        lastrowid = None
        if is_insert:
            row = cur.fetchone()
            lastrowid = row["id"] if row else None
        return _Cursor(cur, lastrowid)

    def script(self, statements):
        for stmt in statements:
            stmt = adapt_schema(stmt.strip())
            if stmt:
                self.raw.execute(stmt)
        self.commit()

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        try:
            self.raw.close()
        except Exception:  # pragma: no cover
            pass
