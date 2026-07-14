from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from emergency_core import paths
from emergency_core.io_utils import ConfigError, atomic_write_bytes, atomic_write_json, load_json_file


def test_data_root_honors_explicit_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "operational-data"
    monkeypatch.setenv("EMERGENCIAS_DATA_DIR", str(override))
    assert paths.data_root() == override.resolve()
    assert override.is_dir()


def test_frozen_data_root_uses_programdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMERGENCIAS_DATA_DIR", raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(tmp_path / "release" / "app.exe"))
    expected = tmp_path / "ProgramData" / paths.APP_VENDOR / paths.APP_NAME
    assert paths.data_root() == expected.resolve()
    assert paths.source_or_executable_dir() == (tmp_path / "release").resolve()


def test_legacy_migration_copies_once_and_never_overwrites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "new"
    legacy = tmp_path / "legacy"
    destination.mkdir()
    legacy.mkdir()
    (legacy / "pacientes.db").write_bytes(b"legacy database")
    monkeypatch.setattr(paths, "data_root", lambda: destination)
    monkeypatch.setattr(paths, "legacy_candidates", lambda: [legacy])

    copied = paths.migrate_legacy_files(("pacientes.db", "missing.json"))
    assert copied == [(legacy / "pacientes.db", destination / "pacientes.db")]
    assert (destination / "pacientes.db").read_bytes() == b"legacy database"
    assert not list(destination.glob("*.importing"))

    (legacy / "pacientes.db").write_bytes(b"changed legacy")
    assert paths.migrate_legacy_files(("pacientes.db",)) == []
    assert (destination / "pacientes.db").read_bytes() == b"legacy database"


@pytest.mark.parametrize("name", ["../secret.db", "folder/file.db", "folder\\file.db", "", "."])
def test_legacy_migration_rejects_unsafe_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setattr(paths, "data_root", lambda: tmp_path)
    with pytest.raises(ValueError, match="invalido"):
        paths.migrate_legacy_files((name,))


def test_windows_acl_command_is_restricted_to_expected_principals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if paths.os.name != "nt":
        pytest.skip("La aplicacion se distribuye en Windows")
    calls: list[list[str]] = []
    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ["whoami"]:
            return SimpleNamespace(returncode=0, stdout="DOMINIO\\usuario_prueba\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(paths.subprocess, "run", fake_run)
    assert paths.harden_windows_acl(tmp_path) is True
    command = calls[1]
    assert command[:3] == ["icacls", str(tmp_path.resolve()), "/inheritance:r"]
    assert "DOMINIO\\usuario_prueba:(OI)(CI)M" in command
    assert "*S-1-5-18:(OI)(CI)F" in command
    assert "*S-1-5-32-544:(OI)(CI)F" in command


def test_windows_acl_failure_restores_inheritance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if paths.os.name != "nt":
        pytest.skip("La aplicacion se distribuye en Windows")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ["whoami"]:
            return SimpleNamespace(returncode=0, stdout="DOMINIO\\usuario\n")
        return SimpleNamespace(returncode=1 if "/inheritance:r" in command else 0, stdout="")

    monkeypatch.setattr(paths.subprocess, "run", fake_run)
    assert paths.harden_windows_acl(tmp_path) is False
    assert any("/inheritance:e" in command for command in calls)


def test_atomic_json_io_and_validation(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "settings.json"
    atomic_write_json(target, {"nombre": "María", "activo": True})
    assert load_json_file(target, validator=lambda value: value.get("activo") is True)["nombre"] == "María"
    assert load_json_file(tmp_path / "missing.json", default={"default": True}) == {"default": True}
    with pytest.raises(ConfigError, match="no es valido"):
        load_json_file(target, validator=lambda value: False)
    target.write_text("{broken", encoding="utf-8")
    with pytest.raises(ConfigError, match="No se pudo leer"):
        load_json_file(target)


def test_failed_atomic_replace_leaves_original_and_removes_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "data.bin"
    target.write_bytes(b"original")
    monkeypatch.setattr(os, "replace", lambda source, destination: (_ for _ in ()).throw(OSError("locked")))
    with pytest.raises(OSError, match="locked"):
        atomic_write_bytes(target, b"new")
    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob(".data.bin.*.tmp"))
