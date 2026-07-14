"""External updater for Generador de Hojas de Emergencia."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from emergency_core.updater import UpdateError, download_file, get_latest_release, is_newer, verify_archive


def wait_for_process(pid: int, timeout: int = 90) -> None:
    if pid <= 0:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.5)
    raise UpdateError("La aplicacion no se cerro a tiempo. Cierrela e intente nuevamente.")


def safe_extract(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise UpdateError("El paquete contiene una ruta no segura.")
        zipped.extractall(destination)
    entries = [item for item in destination.iterdir() if item.name != "__MACOSX"]
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else destination


def replace_release(source: Path, install_dir: Path) -> None:
    allowed = {
        "GENERADOR DE HOJAS 4.1.exe",
        "ACTUALIZADOR.exe",
        "RELEASE_NOTES_4.1.md",
        "THIRD_PARTY_NOTICES.txt",
        "SHA256SUMS.txt",
        "LICENSES",
    }
    unexpected = [item.name for item in source.iterdir() if item.name not in allowed]
    if unexpected:
        raise UpdateError("El paquete contiene archivos inesperados: " + ", ".join(unexpected))
    app_exe = source / "GENERADOR DE HOJAS 4.1.exe"
    if not app_exe.is_file():
        raise UpdateError("El paquete no contiene el ejecutable principal.")
    install_dir.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = install_dir / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            temporary = target.with_suffix(target.suffix + ".new")
            shutil.copy2(item, temporary)
            os.replace(temporary, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--current-version", required=True)
    parser.add_argument("--wait-pid", type=int, default=0)
    args = parser.parse_args()
    install_dir = Path(args.install_dir).resolve()
    try:
        release = get_latest_release()
        if not is_newer(release.version, args.current_version):
            return 0
        with tempfile.TemporaryDirectory(prefix="generador_actualizacion_") as temp_name:
            temp = Path(temp_name)
            archive = download_file(release.archive_url, temp / release.archive_name)
            checksum = download_file(release.checksum_url, temp / (release.archive_name + ".sha256"))
            verify_archive(archive, checksum.read_text(encoding="ascii"))
            extracted = safe_extract(archive, temp / "extraido")
            wait_for_process(args.wait_pid)
            replace_release(extracted, install_dir)
        subprocess.Popen([str(install_dir / "GENERADOR DE HOJAS 4.1.exe")], cwd=str(install_dir))
        return 0
    except Exception as exc:
        message = f"No se pudo completar la actualizacion:\n\n{exc}"
        try:
            import tkinter.messagebox as messagebox

            messagebox.showerror("Actualizacion", message)
        except Exception:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
