from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from emergency_core.backup import BackupManager
from emergency_core.db_migrations import (
    LATEST_SCHEMA_VERSION,
    migrate_database,
    operational_base_day,
    parse_clinical_datetime,
    valid_cedula,
    valid_nss,
    validate_database,
)


def create_legacy_v5(path: Path, *, invalid_datetime: bool = False) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_version (id INTEGER PRIMARY KEY, version INTEGER NOT NULL);
            INSERT INTO schema_version(id, version) VALUES (1, 5);
            CREATE TABLE pacientes (
                cedula TEXT, nombre TEXT NOT NULL, telefono TEXT, direccion TEXT,
                nacionalidad TEXT, ars TEXT, nss TEXT PRIMARY KEY, unidad_edad TEXT
            );
            CREATE TABLE atenciones (
                id INTEGER PRIMARY KEY, nss TEXT, nombre TEXT NOT NULL, sexo TEXT,
                edad_num INTEGER, unidad TEXT, cedula TEXT, telefono TEXT,
                direccion TEXT, nacionalidad TEXT, ars TEXT, hoja TEXT, fecha TEXT,
                hora TEXT, created_at TEXT, tipo_atencion TEXT DEFAULT 'EMERGENCIA',
                nss_clean TEXT, cedula_clean TEXT, telefono_clean TEXT,
                updated_at TEXT, turno_id INTEGER
            );
            CREATE TABLE atenciones_auditoria (
                id INTEGER PRIMARY KEY, atencion_id INTEGER NOT NULL, accion TEXT NOT NULL,
                motivo TEXT, usuario TEXT, snapshot_json TEXT NOT NULL, created_at TEXT
            );
            """
        )
        patients = [
            ("00112345678", "PACIENTE UNO", "8091111111", "DIR 1", "DOMINICANA", "ARS A", "111111111", None),
            ("00112345678", "PACIENTE DOS", "8092222222", "DIR 2", "DOMINICANA", "ARS B", "222222222", None),
            ("00312345678", "PACIENTE TRES", "8093333333", "DIR 3", "DOMINICANA", "ARS C", "333333333", None),
        ]
        conn.executemany("INSERT INTO pacientes VALUES (?,?,?,?,?,?,?,?)", patients)
        bad_fecha = "FECHA INVALIDA" if invalid_datetime else "03/01/2026"
        bad_created = "INVALIDO" if invalid_datetime else "2026-01-03 09:00:00"
        attentions = [
            (
                10,
                "333333333",
                "PACIENTE TRES",
                "Femenino",
                30,
                "Anos",
                "00312345678",
                "8093333333",
                "DIR 3",
                "DOMINICANA",
                "ARS C",
                "GENERAL",
                "02/01/2026",
                "07:59 AM",
                "2026-01-02 07:59:00",
                "EMERGENCIA",
                None,
                None,
                None,
                None,
                None,
            ),
            (
                11,
                "333333333",
                "PACIENTE TRES",
                "Femenino",
                30,
                "Anos",
                "00312345678",
                "8093333333",
                "DIR 3",
                "DOMINICANA",
                "ARS C",
                "GENERAL",
                "02/01/2026",
                "08:00 AM",
                "2026-01-02 08:00:00",
                "EMERGENCIA",
                None,
                None,
                None,
                None,
                None,
            ),
            (
                12,
                "333333333",
                "PACIENTE TRES",
                "Femenino",
                30,
                "Anos",
                "00312345678",
                "8093333333",
                "DIR 3",
                "DOMINICANA",
                "ARS C",
                "GENERAL",
                "02/01/2026",
                "10:00 AM",
                "2026-01-02 10:00:00",
                "EMERGENCIA",
                None,
                None,
                None,
                None,
                None,
            ),
            (
                20,
                "111111111",
                "IDENTIDAD CRUZADA",
                "Masculino",
                41,
                "Anos",
                "00312345678",
                "8094444444",
                "DIR X",
                "DOMINICANA",
                "ARS X",
                "GENERAL",
                "03/01/2026",
                "09:00 AM",
                "2026-01-03 09:00:00",
                "EMERGENCIA",
                None,
                None,
                None,
                None,
                None,
            ),
            (
                25,
                "",
                "SIN DOCUMENTOS",
                "Masculino",
                20,
                "Anos",
                "00000000000",
                "",
                "DIR Y",
                "DOMINICANA",
                "NO",
                "GENERAL",
                bad_fecha,
                "09:00 AM",
                bad_created,
                "EMERGENCIA",
                None,
                None,
                None,
                None,
                None,
            ),
        ]
        conn.executemany("INSERT INTO atenciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", attentions)
        conn.execute(
            "INSERT INTO atenciones_auditoria VALUES (1, 10, 'EDITAR', 'ajuste', 'operador', '{}', '2026-01-02 09:00:00')"
        )
        conn.execute(
            "INSERT INTO atenciones_auditoria VALUES (2, 999, 'EDITAR', 'huerfana', 'operador', '{}', '2026-01-02 09:01:00')"
        )
        conn.commit()


def manager_for(path: Path, root: Path) -> BackupManager:
    return BackupManager(path, root / "backups")


def test_identity_and_operational_time_helpers() -> None:
    assert valid_nss("050-724-827")
    assert not valid_nss("000000")
    assert valid_cedula("003-1234567-8")
    assert not valid_cedula("0031234567")
    before = parse_clinical_datetime("02/01/2026", "07:59 AM")
    boundary = parse_clinical_datetime("02/01/2026", "08:00 AM")
    assert operational_base_day(before).isoformat() == "2026-01-01"
    assert operational_base_day(boundary).isoformat() == "2026-01-02"
    assert parse_clinical_datetime("", "", "2026-01-02T10:11:12").hour == 10
    with pytest.raises(ValueError):
        parse_clinical_datetime("no", "sirve", "tampoco")


def test_migrate_v5_preserves_ids_links_and_marks_conflicts(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    create_legacy_v5(db)
    manager = manager_for(db, tmp_path)

    result = migrate_database(db, manager)

    assert result["migrated"] is True
    assert result["from_version"] == 5
    assert result["to_version"] == LATEST_SCHEMA_VERSION
    assert result["source_attentions"] == 5
    assert result["legacy_attention_conflicts"] == 1
    assert validate_database(db, expected_attentions=5)["version"] == LATEST_SCHEMA_VERSION
    assert manager.verify(result["backup"])["reason"] == (
        f"antes_migracion_v5_a_v{LATEST_SCHEMA_VERSION}"
    )

    with closing(sqlite3.connect(db)) as conn:
        conn.row_factory = sqlite3.Row
        assert [row[0] for row in conn.execute("SELECT id FROM atenciones ORDER BY id")] == [10, 11, 12, 20, 25]
        rows = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM atenciones")}
        assert rows[10]["paciente_id"] == 3
        assert rows[10]["es_reingreso"] == 0
        assert rows[11]["es_reingreso"] == 0
        assert rows[12]["es_reingreso"] == 1
        assert rows[12]["atencion_origen_id"] == 11
        assert rows[10]["dia_operativo_id"] != rows[11]["dia_operativo_id"]
        assert rows[11]["dia_operativo_id"] == rows[12]["dia_operativo_id"]
        assert rows[20]["paciente_id"] > 3
        assert rows[20]["requiere_revision"] == 1
        assert rows[25]["paciente_id"] > 3
        provisional = conn.execute(
            "SELECT provisional FROM pacientes WHERE id=?", (rows[25]["paciente_id"],)
        ).fetchone()[0]
        assert provisional == 1
        assert conn.execute("SELECT COUNT(*) FROM trabajos_salida").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM auditoria_tombstones").fetchone()[0] == 0
        assert (
            conn.execute("SELECT tipo FROM identidad_conflictos WHERE atencion_id=12").fetchone()[0]
            == "POSIBLE_REINGRESO"
        )
        audit = conn.execute("SELECT id,atencion_id FROM atenciones_auditoria ORDER BY id").fetchall()
        assert [(row[0], row[1]) for row in audit] == [(1, 10), (2, None)]
        conn.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO atenciones(paciente_id,dia_operativo_id,turno_id,nombre,estado,es_reingreso)
                VALUES (?,?,?,?, 'ACTIVA', 0)
                """,
                (rows[11]["paciente_id"], rows[11]["dia_operativo_id"], rows[11]["turno_id"], "DUPLICADO"),
            )

    second = migrate_database(db, manager)
    assert second["migrated"] is False
    assert len(manager.list_backups()) == 1


def test_current_schema_recreates_idempotent_schema_objects(tmp_path: Path) -> None:
    db = tmp_path / "current.db"
    manager = manager_for(db, tmp_path)
    migrate_database(db, manager)
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("DROP TABLE auditoria_tombstones")
        conn.commit()

    result = migrate_database(db, manager)

    assert result["migrated"] is False
    with closing(sqlite3.connect(db)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(auditoria_tombstones)")}
    assert columns == {"event_hash", "previous_hash", "purge_event_hash", "created_at", "workstation"}


def test_failed_migration_keeps_original_and_creates_verified_backup(tmp_path: Path) -> None:
    db = tmp_path / "legacy_bad.db"
    create_legacy_v5(db, invalid_datetime=True)
    manager = manager_for(db, tmp_path)

    with pytest.raises(ValueError, match="no interpretable"):
        migrate_database(db, manager)

    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT version FROM schema_version WHERE id=1").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM atenciones").fetchone()[0] == 5
    assert not db.with_suffix(".db.migrating").exists()
    backups = manager.list_backups()
    assert len(backups) == 1
    manager.verify(backups[0])


def test_new_and_empty_database_are_initialized(tmp_path: Path) -> None:
    missing = tmp_path / "new.db"
    result = migrate_database(missing, manager_for(missing, tmp_path / "one"))
    assert result["created"] is True
    assert validate_database(missing, 0)["version"] == LATEST_SCHEMA_VERSION

    empty = tmp_path / "empty.db"
    empty.touch()
    result = migrate_database(empty, manager_for(empty, tmp_path / "two"))
    assert result["created"] is True
    assert validate_database(empty, 0)["version"] == LATEST_SCHEMA_VERSION


def test_future_or_unknown_schema_is_never_replaced(tmp_path: Path) -> None:
    future = tmp_path / "future.db"
    with closing(sqlite3.connect(future)) as conn:
        conn.execute("CREATE TABLE schema_version(id INTEGER PRIMARY KEY, version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version VALUES (1, ?)", (LATEST_SCHEMA_VERSION + 1,))
        conn.execute("CREATE TABLE atenciones(id INTEGER PRIMARY KEY)")
        conn.commit()
    future_bytes = future.read_bytes()
    future_manager = manager_for(future, tmp_path / "future_root")
    with pytest.raises(sqlite3.DatabaseError, match="esquema futuro"):
        migrate_database(future, future_manager)
    assert future.read_bytes() == future_bytes
    assert future_manager.list_backups() == []

    unknown = tmp_path / "unknown.db"
    with closing(sqlite3.connect(unknown)) as conn:
        conn.execute("CREATE TABLE datos_irremplazables(value TEXT)")
        conn.execute("INSERT INTO datos_irremplazables VALUES ('conservar')")
        conn.commit()
    unknown_manager = manager_for(unknown, tmp_path / "unknown_root")
    with pytest.raises(sqlite3.DatabaseError, match="no contiene la tabla atenciones"):
        migrate_database(unknown, unknown_manager)
    with closing(sqlite3.connect(unknown)) as conn:
        assert conn.execute("SELECT value FROM datos_irremplazables").fetchone()[0] == "conservar"


def test_backup_manager_must_target_same_database(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    other = tmp_path / "b.db"
    with pytest.raises(ValueError, match="no corresponde"):
        migrate_database(db, BackupManager(other, tmp_path / "backups"))


def test_migrate_v11_to_v12_adds_resolution_columns_and_backup(tmp_path: Path) -> None:
    db = tmp_path / "v11.db"
    manager = manager_for(db, tmp_path / "v11_root")
    assert migrate_database(db, manager)["created"] is True
    with closing(sqlite3.connect(db)) as conn:
        for column in ("resolucion", "motivo_resolucion", "resuelto_por", "resuelto_at"):
            conn.execute(f"ALTER TABLE identidad_conflictos DROP COLUMN {column}")
        conn.execute("UPDATE schema_version SET version=11 WHERE id=1")
        conn.commit()

    result = migrate_database(db, manager)

    assert result["migrated"] is True
    assert result["from_version"] == 11
    assert result["to_version"] == 12
    assert manager.verify(result["backup"])["reason"] == "antes_migracion_v11_a_v12"
    with closing(sqlite3.connect(db)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(identidad_conflictos)")}
        assert {"resolucion", "motivo_resolucion", "resuelto_por", "resuelto_at"} <= columns
