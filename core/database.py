import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.crypto import (
    DEFAULT_ITERATIONS,
    CryptoError,
    create_auth_params,
    decrypt_text,
    encrypt_text,
    unlock_vault,
)


class DatabaseError(Exception):
    """Ошибка работы с базой данных хранилища."""


@dataclass
class VaultEntry:
    id: int
    title: str
    username: str
    url_or_pkg: str
    category: str
    secret: str
    note: str
    is_favorite: bool
    created_at: str
    updated_at: str
    last_copied_at: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VaultDatabase:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS vault_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    salt BLOB NOT NULL,
                    iterations INTEGER NOT NULL,
                    verifier_token TEXT NOT NULL,
                    auto_lock_seconds INTEGER NOT NULL DEFAULT 120,
                    clipboard_clear_seconds INTEGER NOT NULL DEFAULT 25,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    url_or_pkg TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'General',
                    secret_ciphertext TEXT NOT NULL,
                    note_ciphertext TEXT NOT NULL DEFAULT '',
                    is_favorite INTEGER NOT NULL DEFAULT 0 CHECK (is_favorite IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_copied_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_entries_title ON entries (title);
                CREATE INDEX IF NOT EXISTS idx_entries_category ON entries (category);
                CREATE INDEX IF NOT EXISTS idx_entries_favorite ON entries (is_favorite);

                CREATE TRIGGER IF NOT EXISTS trg_entries_updated_at
                AFTER UPDATE ON entries
                FOR EACH ROW
                WHEN NEW.updated_at = OLD.updated_at
                BEGIN
                    UPDATE entries
                    SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                    WHERE id = NEW.id;
                END;
                """
            )

    def is_initialized(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM vault_meta WHERE id = 1").fetchone()
            return row is not None

    def initialize_vault(self, master_password: str, iterations: int = DEFAULT_ITERATIONS) -> bytes:
        if self.is_initialized():
            raise DatabaseError("Хранилище уже инициализировано.")

        params, fernet_key = create_auth_params(master_password, iterations=iterations)
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO vault_meta (
                    id, salt, iterations, verifier_token,
                    auto_lock_seconds, clipboard_clear_seconds, created_at
                )
                VALUES (1, ?, ?, ?, 120, 25, ?)
                """,
                (params.salt, params.iterations, params.verifier_token, now),
            )
        return fernet_key

    def unlock(self, master_password: str) -> bytes:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT salt, iterations, verifier_token FROM vault_meta WHERE id = 1"
            ).fetchone()
        if row is None:
            raise DatabaseError("Хранилище ещё не инициализировано.")

        return unlock_vault(
            master_password=master_password,
            salt=bytes(row["salt"]),
            iterations=int(row["iterations"]),
            verifier_token=str(row["verifier_token"]),
        )

    def _row_to_entry(self, row: sqlite3.Row, fernet_key: bytes) -> VaultEntry:
        return VaultEntry(
            id=int(row["id"]),
            title=str(row["title"]),
            username=str(row["username"]),
            url_or_pkg=str(row["url_or_pkg"]),
            category=str(row["category"]),
            secret=decrypt_text(str(row["secret_ciphertext"]), fernet_key),
            note=decrypt_text(str(row["note_ciphertext"]), fernet_key),
            is_favorite=bool(row["is_favorite"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_copied_at=row["last_copied_at"],
        )

    def add_entry(
        self,
        fernet_key: bytes,
        title: str,
        secret: str,
        username: str = "",
        url_or_pkg: str = "",
        category: str = "General",
        note: str = "",
        is_favorite: bool = False,
    ) -> int:
        clean_title = title.strip()
        if not clean_title:
            raise DatabaseError("Название записи не может быть пустым.")
        if not secret:
            raise DatabaseError("Пароль/секрет не может быть пустым.")

        try:
            enc_secret = encrypt_text(secret, fernet_key)
            enc_note = encrypt_text(note, fernet_key) if note else ""
        except CryptoError as exc:
            raise DatabaseError("Ошибка шифрования данных записи.") from exc

        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO entries (
                    title, username, url_or_pkg, category,
                    secret_ciphertext, note_ciphertext, is_favorite,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_title,
                    username.strip(),
                    url_or_pkg.strip(),
                    category.strip() or "General",
                    enc_secret,
                    enc_note,
                    1 if is_favorite else 0,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def get_entry(self, entry_id: int, fernet_key: bytes) -> VaultEntry | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row, fernet_key)

    def list_entries(
        self,
        fernet_key: bytes,
        search: str = "",
        category: str | None = None,
        favorites_only: bool = False,
    ) -> list[VaultEntry]:
        clauses: list[str] = []
        params: list[object] = []

        if category and category != "All":
            clauses.append("category = ?")
            params.append(category)

        if favorites_only:
            clauses.append("is_favorite = 1")

        clean_search = search.strip().lower()
        if clean_search:
            like_pattern = f"%{clean_search}%"
            clauses.append("(LOWER(title) LIKE ? OR LOWER(username) LIKE ? OR LOWER(url_or_pkg) LIKE ?)")
            params.extend([like_pattern, like_pattern, like_pattern])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM entries {where_sql} ORDER BY is_favorite DESC, LOWER(title) ASC, id DESC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [self._row_to_entry(row, fernet_key) for row in rows]

    def update_entry(
        self,
        entry_id: int,
        fernet_key: bytes,
        title: str,
        secret: str,
        username: str = "",
        url_or_pkg: str = "",
        category: str = "General",
        note: str = "",
        is_favorite: bool = False,
    ) -> bool:
        clean_title = title.strip()
        if not clean_title:
            raise DatabaseError("Название записи не может быть пустым.")
        if not secret:
            raise DatabaseError("Пароль/секрет не может быть пустым.")

        try:
            enc_secret = encrypt_text(secret, fernet_key)
            enc_note = encrypt_text(note, fernet_key) if note else ""
        except CryptoError as exc:
            raise DatabaseError("Ошибка шифрования данных записи.") from exc

        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE entries
                SET title = ?,
                    username = ?,
                    url_or_pkg = ?,
                    category = ?,
                    secret_ciphertext = ?,
                    note_ciphertext = ?,
                    is_favorite = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    clean_title,
                    username.strip(),
                    url_or_pkg.strip(),
                    category.strip() or "General",
                    enc_secret,
                    enc_note,
                    1 if is_favorite else 0,
                    now,
                    entry_id,
                ),
            )
            return cur.rowcount > 0

    def delete_entry(self, entry_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            return cur.rowcount > 0

    def mark_copied(self, entry_id: int) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE entries SET last_copied_at = ? WHERE id = ?",
                (now, entry_id),
            )