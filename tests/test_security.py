from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from emergency_core.security import AdminSecurity, SecurityError


@pytest.fixture
def security(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AdminSecurity:
    monkeypatch.setattr(AdminSecurity, "ITERATIONS", 100_000)
    return AdminSecurity(tmp_path / "security.json", tmp_path / "audit.jsonl")


@pytest.mark.parametrize("pin", ["", "12345", "abcdef", "000000", "111111", "123456", "654321", "9" * 65])
def test_weak_or_invalid_pins_are_rejected(security: AdminSecurity, pin: str) -> None:
    with pytest.raises(SecurityError):
        security.setup(pin)
    assert not security.config_path.exists()


def test_setup_hashes_pin_and_cannot_silently_overwrite(security: AdminSecurity) -> None:
    security.setup("849261", actor="ADMIN")
    raw = security.config_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    assert "849261" not in raw
    assert data["iterations"] == 100_000
    assert len(data["salt"]) == 64
    assert len(data["password_hash"]) == 64
    assert security.is_configured()
    with pytest.raises(SecurityError, match="ya esta configurada"):
        security.setup("951753")
    assert security.verify("849261") is True


def test_failed_attempts_lock_access_and_success_resets_counter(security: AdminSecurity) -> None:
    security.setup("849261")
    assert security.verify("000001") is False
    assert json.loads(security.config_path.read_text(encoding="utf-8"))["failed_attempts"] == 1
    assert security.verify("849261") is True
    assert json.loads(security.config_path.read_text(encoding="utf-8"))["failed_attempts"] == 0

    for _ in range(security.MAX_FAILURES):
        assert security.verify("000001") is False
    locked = json.loads(security.config_path.read_text(encoding="utf-8"))
    assert locked["failed_attempts"] == 0
    assert locked["locked_until"]
    with pytest.raises(SecurityError, match="Acceso bloqueado"):
        security.verify("849261")


def test_missing_or_corrupt_security_configuration_is_explicit(tmp_path: Path) -> None:
    security = AdminSecurity(tmp_path / "security.json", tmp_path / "audit.jsonl")
    with pytest.raises(SecurityError, match="no esta configurada"):
        security.verify("849261")
    security.config_path.write_text('{"format":1,"salt":"bad"}', encoding="utf-8")
    with pytest.raises(SecurityError, match="danada"):
        security.is_configured()
    with pytest.raises(SecurityError, match="danada"):
        security.verify("849261")
    security.config_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(SecurityError, match="danada"):
        security.is_configured()
    security.config_path.write_text("[]", encoding="utf-8")
    with pytest.raises(SecurityError, match="danada"):
        security.setup("849261")


def test_audit_chain_is_linked_and_detects_tampering(security: AdminSecurity) -> None:
    security.setup("849261", actor="María")
    assert security.verify("849261", actor="María", action="PURGA")
    security.audit("EXPORTAR", actor="María", success=True, detail="turno 2")

    assert security.verify_audit_chain() == 3
    lines = security.audit_path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert records[0]["previous_hash"] == ""
    assert records[1]["previous_hash"] == records[0]["hash"]
    records[1]["actor"] = "OTRA PERSONA"
    lines[1] = json.dumps(records[1], ensure_ascii=False, sort_keys=True)
    security.audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(SecurityError, match="hash de auditoria"):
        security.verify_audit_chain()


def test_concurrent_audit_appends_keep_a_valid_chain(security: AdminSecurity) -> None:
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda number: security.audit("EVENT", actor=str(number), success=True), range(40)))
    assert security.verify_audit_chain() == 40


def test_empty_audit_chain_is_valid(security: AdminSecurity) -> None:
    assert security.verify_audit_chain() == 0
