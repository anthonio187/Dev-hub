"""Tiny DB layer: SQLite locally, Postgres when DATABASE_URL is set (Render)."""

import os
import re
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.environ.get("SQLITE_PATH") or os.path.join(BASE_DIR, "devhub.db")

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

_NAMED = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")


def translate(sql: str) -> str:
    """sqlite-style SQL (? and :name params) -> psycopg style."""
    sql = sql.replace("%", "%%")
    sql = _NAMED.sub(r"%(\1)s", sql)
    return sql.replace("?", "%s")


def adapt_schema(sql: str) -> str:
    if not IS_PG:
        return sql
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return sql.replace(" COLLATE NOCASE", "")


class _Cursor:
    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur.fetchall())


class Conn:
    def __init__(self):
        if IS_PG:
            self.raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            self.raw = sqlite3.connect(SQLITE_PATH)
            self.raw.row_factory = sqlite3.Row
            self.raw.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql, params=()):
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

    def commit(self):
        self.raw.commit()

    def close(self):
        try:
            self.raw.close()
        except Exception:
            pass


def connect() -> Conn:
    return Conn()


def init_schema(schema_sql: str, migrations) -> None:
    """Create tables + apply (table, column, ddl) migrations. Safe to run many times."""
    schema_sql = adapt_schema(schema_sql)
    statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
    if IS_PG:
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            conn.execute("SELECT pg_advisory_lock(727274)")
            try:
                for stmt in statements:
                    conn.execute(stmt)
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower "
                    "ON users (lower(username))")
                for table, col, ddl in migrations:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ddl}")
            finally:
                conn.execute("SELECT pg_advisory_unlock(727274)")
        return
    conn = sqlite3.connect(SQLITE_PATH)
    for stmt in statements:
        conn.execute(stmt)
    for table, col, ddl in migrations:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    conn.commit()
    conn.close()
