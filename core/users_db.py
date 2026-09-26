"""
User accounts, roles, and permissions (SQLite).
Stored under: ~/.exam_admin_tools/users.db
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Feature keys used across the app
FEATURES = {
    "exam_grouping": "Exam Grouping",
    "appointment_letters": "Appointment Letters",
    "mapping_converter": "Mapping Converter",
    "user_management": "User Management (Admin)",
}

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "Admin@123"


def _db_path() -> Path:
    folder = Path.home() / ".exam_admin_tools"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "users.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    # PBKDF2 – no extra packages needed
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return dk.hex(), salt


def _verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = _hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def init_db() -> None:
    """Create tables and ensure a default admin exists."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            full_name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_permissions (
            user_id INTEGER NOT NULL,
            feature_key TEXT NOT NULL,
            PRIMARY KEY (user_id, feature_key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()

    # Seed default admin if no users exist
    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        now = datetime.now(timezone.utc).isoformat()
        pw_hash, salt = _hash_password(DEFAULT_ADMIN_PASSWORD)
        cur.execute(
            """
            INSERT INTO users (
                username, full_name, password_hash, salt, is_admin, is_active,
                must_change_password, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, 1, 1, ?, ?)
            """,
            (DEFAULT_ADMIN_USERNAME, "System Administrator", pw_hash, salt, now, now),
        )
        admin_id = cur.lastrowid
        for key in FEATURES:
            cur.execute(
                "INSERT INTO user_permissions (user_id, feature_key) VALUES (?, ?)",
                (admin_id, key),
            )
        conn.commit()
    conn.close()


@dataclass
class User:
    id: int
    username: str
    full_name: str
    is_admin: bool
    is_active: bool
    must_change_password: bool
    permissions: List[str]


def _row_to_user(row: sqlite3.Row, permissions: List[str]) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        full_name=row["full_name"] or "",
        is_admin=bool(row["is_admin"]),
        is_active=bool(row["is_active"]),
        must_change_password=bool(row["must_change_password"]),
        permissions=permissions,
    )


def get_permissions(user_id: int) -> List[str]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT feature_key FROM user_permissions WHERE user_id = ?",
        (user_id,),
    )
    perms = [r["feature_key"] for r in cur.fetchall()]
    conn.close()
    return perms


def authenticate(username: str, password: str) -> Optional[User]:
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
        (username.strip(),),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    if not row["is_active"]:
        return None
    if not _verify_password(password, row["password_hash"], row["salt"]):
        return None
    perms = get_permissions(row["id"])
    if row["is_admin"]:
        # Admin always has every feature
        perms = list(FEATURES.keys())
    return _row_to_user(row, perms)


def list_users() -> List[User]:
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE")
    rows = cur.fetchall()
    conn.close()
    users = []
    for row in rows:
        perms = get_permissions(row["id"])
        if row["is_admin"]:
            perms = list(FEATURES.keys())
        users.append(_row_to_user(row, perms))
    return users


def get_user_by_id(user_id: int) -> Optional[User]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    perms = get_permissions(user_id)
    if row["is_admin"]:
        perms = list(FEATURES.keys())
    return _row_to_user(row, perms)


def create_user(
    username: str,
    full_name: str,
    password: str,
    is_admin: bool,
    permissions: List[str],
    must_change_password: bool = True,
) -> tuple[bool, str]:
    init_db()
    username = username.strip()
    if not username:
        return False, "Username is required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    now = datetime.now(timezone.utc).isoformat()
    pw_hash, salt = _hash_password(password)
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (
                username, full_name, password_hash, salt, is_admin, is_active,
                must_change_password, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                username,
                full_name.strip(),
                pw_hash,
                salt,
                1 if is_admin else 0,
                1 if must_change_password else 0,
                now,
                now,
            ),
        )
        user_id = cur.lastrowid
        # Permissions
        if is_admin:
            keys = list(FEATURES.keys())
        else:
            keys = [k for k in permissions if k in FEATURES and k != "user_management"]
        for key in keys:
            cur.execute(
                "INSERT INTO user_permissions (user_id, feature_key) VALUES (?, ?)",
                (user_id, key),
            )
        conn.commit()
        return True, "User created successfully."
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    finally:
        conn.close()


def update_user_permissions(
    user_id: int,
    is_admin: bool,
    permissions: List[str],
    is_active: bool,
    full_name: str,
) -> tuple[bool, str]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not cur.fetchone():
        conn.close()
        return False, "User not found."

    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        UPDATE users
        SET full_name = ?, is_admin = ?, is_active = ?, updated_at = ?
        WHERE id = ?
        """,
        (full_name.strip(), 1 if is_admin else 0, 1 if is_active else 0, now, user_id),
    )
    cur.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
    if is_admin:
        keys = list(FEATURES.keys())
    else:
        keys = [k for k in permissions if k in FEATURES and k != "user_management"]
    for key in keys:
        cur.execute(
            "INSERT INTO user_permissions (user_id, feature_key) VALUES (?, ?)",
            (user_id, key),
        )
    conn.commit()
    conn.close()
    return True, "User updated."


def reset_password(user_id: int, new_password: str, force_change: bool = True) -> tuple[bool, str]:
    if len(new_password) < 6:
        return False, "Password must be at least 6 characters."
    pw_hash, salt = _hash_password(new_password)
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET password_hash = ?, salt = ?, must_change_password = ?, updated_at = ?
        WHERE id = ?
        """,
        (pw_hash, salt, 1 if force_change else 0, now, user_id),
    )
    if cur.rowcount == 0:
        conn.close()
        return False, "User not found."
    conn.commit()
    conn.close()
    return True, "Password reset successfully."


def change_own_password(user_id: int, current_password: str, new_password: str) -> tuple[bool, str]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "User not found."
    if not _verify_password(current_password, row["password_hash"], row["salt"]):
        conn.close()
        return False, "Current password is incorrect."
    if len(new_password) < 6:
        conn.close()
        return False, "New password must be at least 6 characters."
    pw_hash, salt = _hash_password(new_password)
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        UPDATE users
        SET password_hash = ?, salt = ?, must_change_password = 0, updated_at = ?
        WHERE id = ?
        """,
        (pw_hash, salt, now, user_id),
    )
    conn.commit()
    conn.close()
    return True, "Password changed successfully."


def delete_user(user_id: int, acting_admin_id: int) -> tuple[bool, str]:
    if user_id == acting_admin_id:
        return False, "You cannot delete your own account."
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    if cur.rowcount == 0:
        conn.close()
        return False, "User not found."
    conn.commit()
    conn.close()
    return True, "User deleted."


def user_has_feature(user: User, feature_key: str) -> bool:
    if user.is_admin:
        return True
    return feature_key in user.permissions
