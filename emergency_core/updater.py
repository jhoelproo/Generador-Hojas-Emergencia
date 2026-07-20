"""Remote release discovery and verified download helpers."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

APP_VERSION = "4.1.8"
GITHUB_REPOSITORY = "jhoelproo/Generador-Hojas-Emergencia"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
RELEASE_ARCHIVE_PATTERN = re.compile(r"^GENERADOR_DE_HOJAS_(\d+\.\d+\.\d+)\.zip$", re.IGNORECASE)


class UpdateError(RuntimeError):
    """Raised when an update cannot be safely discovered or verified."""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    name: str
    notes: str
    archive_url: str
    archive_name: str
    checksum_url: str
    html_url: str


def version_tuple(value: str) -> tuple[int, int, int]:
    clean = str(value or "").strip().lower().lstrip("v")
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", clean)
    if not match:
        raise UpdateError(f"Version no valida: {value!r}")
    return tuple(int(part) for part in match.groups())


def is_newer(candidate: str, current: str = APP_VERSION) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def _request_json(url: str, timeout: int = 12) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"GeneradorHojasEmergencia/{APP_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"No se pudo consultar GitHub: {exc}") from exc
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub devolvio una respuesta no valida.") from exc
    if not isinstance(data, dict):
        raise UpdateError("La informacion de la version no tiene el formato esperado.")
    return data


def parse_release(data: dict) -> ReleaseInfo:
    if data.get("draft") or data.get("prerelease"):
        raise UpdateError("La ultima publicacion no es una version estable.")
    version = str(data.get("tag_name") or "").strip().lstrip("v")
    version_tuple(version)
    expected_archive = f"GENERADOR_DE_HOJAS_{version}.zip"
    expected_checksum = expected_archive + ".sha256"
    assets = {str(item.get("name")): item for item in data.get("assets", []) if isinstance(item, dict)}
    archive = assets.get(expected_archive)
    checksum = assets.get(expected_checksum)
    if not archive or not checksum:
        raise UpdateError(
            f"La version {version} no contiene los dos archivos de actualizacion requeridos."
        )
    return ReleaseInfo(
        version=version,
        name=str(data.get("name") or f"Version {version}"),
        notes=str(data.get("body") or "").strip(),
        archive_url=str(archive.get("browser_download_url") or ""),
        archive_name=expected_archive,
        checksum_url=str(checksum.get("browser_download_url") or ""),
        html_url=str(data.get("html_url") or ""),
    )


def get_latest_release(api_url: str = LATEST_RELEASE_API, timeout: int = 12) -> ReleaseInfo:
    return parse_release(_request_json(api_url, timeout=timeout))


def download_file(url: str, destination: str | Path, timeout: int = 120) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"GeneradorHojasEmergencia/{APP_VERSION}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise UpdateError(f"No se pudo descargar {destination.name}: {exc}") from exc
    return destination


def parse_checksum(text: str, expected_name: str) -> str:
    for raw_line in str(text or "").splitlines():
        match = re.fullmatch(r"([A-Fa-f0-9]{64})\s+\*?(.+)", raw_line.strip())
        if match and Path(match.group(2)).name == expected_name:
            return match.group(1).lower()
    raise UpdateError("El archivo de comprobacion SHA-256 no contiene el paquete esperado.")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: str | Path, checksum_text: str) -> None:
    path = Path(path)
    expected = parse_checksum(checksum_text, path.name)
    actual = sha256_file(path)
    if actual != expected:
        raise UpdateError("El paquete descargado no supera la comprobacion SHA-256.")
