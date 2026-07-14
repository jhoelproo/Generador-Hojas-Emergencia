from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    path = tmp_path / "pacientes.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE markers (value TEXT NOT NULL)")
        conn.execute("INSERT INTO markers(value) VALUES ('original')")
        conn.commit()
    return path
