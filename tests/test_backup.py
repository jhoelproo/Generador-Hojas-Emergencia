from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from emergency_core.backup import BackupError, BackupManager


def read_marker(path: Path) -> str:
    with closing(sqlite3.connect(path)) as conn:
        return str(conn.execute("SELECT value FROM markers").fetchone()[0])


def set_marker(path: Path, value: str) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("UPDATE markers SET value=?", (value,))
        conn.commit()


def test_create_verify_and_detect_file_tampering(sqlite_db: Path, tmp_path: Path) -> None:
    config = tmp_path / "settings.json"
    config.write_text('{"theme":"dark"}', encoding="utf-8")
    manager = BackupManager(sqlite_db, tmp_path / "backups", [config])

    folder = manager.create("manual con espacios", label="antes de prueba")
    manifest = manager.verify(folder)

    assert folder.name.endswith("manual_con_espacios")
    assert manifest["label"] == "antes de prueba"
    assert {item["name"] for item in manifest["files"]} == {sqlite_db.name, config.name}
    (folder / config.name).write_text("alterado", encoding="utf-8")
    with pytest.raises(BackupError, match="Falta o cambio|hash no coincide"):
        manager.verify(folder)


def test_manifest_cannot_escape_backup_directory(sqlite_db: Path, tmp_path: Path) -> None:
    manager = BackupManager(sqlite_db, tmp_path / "backups")
    folder = manager.create("manual")
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database"] = "../pacientes.db"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BackupError, match="fuera del respaldo"):
        manager.verify(folder)


def test_duplicate_related_names_are_rejected(sqlite_db: Path, tmp_path: Path) -> None:
    first = tmp_path / "one" / "same.json"
    second = tmp_path / "two" / "same.json"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("1", encoding="utf-8")
    second.write_text("2", encoding="utf-8")
    manager = BackupManager(sqlite_db, tmp_path / "backups", [first, second])
    with pytest.raises(BackupError, match="mismo nombre"):
        manager.create("manual")
    assert list((tmp_path / "backups").iterdir()) == []


def test_restore_is_verified_and_keeps_pre_restore_safety_copy(sqlite_db: Path, tmp_path: Path) -> None:
    manager = BackupManager(sqlite_db, tmp_path / "backups", retention_days=7)
    original = manager.create("original")
    set_marker(sqlite_db, "modified")

    safety = manager.restore_database(original)

    assert read_marker(sqlite_db) == "original"
    assert read_marker(safety / sqlite_db.name) == "modified"
    assert manager.verify(safety)["reason"] == "antes_de_restaurar"


def test_restore_stages_old_backup_before_retention_prunes_it(sqlite_db: Path, tmp_path: Path) -> None:
    manager = BackupManager(sqlite_db, tmp_path / "backups", retention_days=7)
    selected = manager.create("selected")
    manifest_path = selected / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_at"] = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    set_marker(sqlite_db, "newer")

    manager.restore_database(selected)

    assert read_marker(sqlite_db) == "original"
    assert not selected.exists()


def test_corrupt_backup_never_changes_live_database(sqlite_db: Path, tmp_path: Path) -> None:
    manager = BackupManager(sqlite_db, tmp_path / "backups")
    folder = manager.create("manual")
    (folder / sqlite_db.name).write_bytes(b"not sqlite")
    set_marker(sqlite_db, "live")
    before_count = len(manager.list_backups())

    with pytest.raises(BackupError):
        manager.restore_database(folder)

    assert read_marker(sqlite_db) == "live"
    assert len(manager.list_backups()) == before_count
    assert not sqlite_db.with_suffix(".db.restore.tmp").exists()


def test_daily_backup_is_idempotent_and_ignores_bad_manifest(sqlite_db: Path, tmp_path: Path) -> None:
    manager = BackupManager(sqlite_db, tmp_path / "backups")
    broken = manager.backup_root / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text("{invalid", encoding="utf-8")

    created = manager.ensure_daily()
    assert created is not None
    assert manager.ensure_daily() is None
    assert manager.verify(created)["reason"] == "respaldo_diario"


def test_non_sqlite_database_and_invalid_manifest_are_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"plain text")
    with pytest.raises(BackupError, match="No se pudo abrir"):
        BackupManager.check_database(bad)
