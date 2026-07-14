import hashlib

import pytest

from emergency_core.updater import UpdateError, is_newer, parse_checksum, parse_release, verify_archive


def release_payload(version="4.2.0"):
    archive = f"GENERADOR_DE_HOJAS_{version}.zip"
    return {
        "tag_name": version,
        "name": f"Version {version}",
        "body": "Cambios",
        "draft": False,
        "prerelease": False,
        "html_url": "https://example.invalid/release",
        "assets": [
            {"name": archive, "browser_download_url": "https://example.invalid/app.zip"},
            {"name": archive + ".sha256", "browser_download_url": "https://example.invalid/app.sha256"},
        ],
    }


def test_release_requires_archive_and_checksum():
    result = parse_release(release_payload())
    assert result.version == "4.2.0"
    assert result.archive_name == "GENERADOR_DE_HOJAS_4.2.0.zip"

    payload = release_payload()
    payload["assets"].pop()
    with pytest.raises(UpdateError):
        parse_release(payload)


def test_semantic_version_comparison_is_numeric():
    assert is_newer("4.10.0", "4.9.9")
    assert not is_newer("4.1.0", "4.1.0")
    with pytest.raises(UpdateError):
        is_newer("latest", "4.1.0")


def test_archive_checksum_must_match(tmp_path):
    archive = tmp_path / "GENERADOR_DE_HOJAS_4.2.0.zip"
    archive.write_bytes(b"verified release")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = f"{digest} *{archive.name}\n"
    assert parse_checksum(checksum, archive.name) == digest
    verify_archive(archive, checksum)

    with pytest.raises(UpdateError):
        verify_archive(archive, ("0" * 64) + f" *{archive.name}\n")
