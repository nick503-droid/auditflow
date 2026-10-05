"""Entrada estable AuditFlow.exe. Activa una versión sólo al volver a abrir."""

import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from core.pc_updates import (
    atomic_json, installed_path, is_installed, read_json, stage_archive,
    update_lock, updates_home, validate_manifest,
)


def select_version(root, distribution):
    """Importa el paquete inicial offline y después el pendiente más reciente."""
    previous = read_json(root / "active.json")
    if previous:
        validate_manifest(previous)
        if not is_installed(root, previous):
            raise ValueError("La versión activa está incompleta")
    bootstrap = read_json(distribution / "bootstrap.json")
    rejected = read_json(root / "rejected.json", {})
    if bootstrap and bootstrap.get("sha256") != rejected.get("sha256") and (not previous or bootstrap.get("build", 0) > previous["build"]):
        stage_archive(root, distribution / "bootstrap.zip", bootstrap)
    pending = read_json(root / "pending.json")
    if pending:
        validate_manifest(pending)
        if is_installed(root, pending) and (not previous or pending["build"] > previous["build"]):
            if previous:
                # Mantener recuperación aunque se apague la PC entre activar y abrir.
                atomic_json(root / "previous.json", previous)
            atomic_json(root / "active.json", pending)
            (root / "pending.json").unlink(missing_ok=True)
            return pending, previous
    if previous:
        fallback = read_json(root / "previous.json")
        if fallback:
            validate_manifest(fallback)
            if fallback["build"] >= previous["build"] or not is_installed(root, fallback):
                fallback = None
        return previous, fallback
    raise ValueError("Falta el paquete inicial. Extrae TODO el ZIP de instalación, no sólo AuditFlow.exe")


def run_version(root, distribution, manifest):
    application = installed_path(root, manifest)
    token = uuid.uuid4().hex
    ready = root / "health" / (token + ".json")
    environment = os.environ.copy()
    environment["AUDITFLOW_MANAGED_CLIENT"] = "1"
    environment["AUDITFLOW_READY_TOKEN"] = token
    environment["AUDITFLOW_LAUNCHER_DIR"] = str(distribution)
    try:
        child = subprocess.Popen(
            [str(application / "main.exe")], cwd=application,
            env=environment, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        return False
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if read_json(ready, {}).get("ready"):
            ready.unlink(missing_ok=True)
            return True
        if child.poll() is not None:
            return False
        time.sleep(0.2)
    # Nunca matar una aplicación que podría estar grabando/trabajando.
    return None


def restore_previous(root, failed, previous):
    with update_lock(root):
        if read_json(root / "active.json") == failed:
            atomic_json(root / "active.json", previous)
            (root / "previous.json").unlink(missing_ok=True)
        atomic_json(root / "rejected.json", {"sha256": failed["sha256"], "version": failed["version"]})


def confirm_version(root, manifest):
    with update_lock(root):
        if read_json(root / "active.json") == manifest:
            (root / "previous.json").unlink(missing_ok=True)


def main():
    if os.name != "nt":
        raise RuntimeError("El lanzador es para Windows")
    distribution = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    root = updates_home()
    with update_lock(root):
        manifest, previous = select_version(root, distribution)
    status = run_version(root, distribution, manifest)
    if status is True:
        confirm_version(root, manifest)
    elif status is False:
        if previous:
            restore_previous(root, manifest, previous)
            if run_version(root, distribution, previous) is not False:
                ctypes.windll.user32.MessageBoxW(None, "La actualización no pudo iniciar. Se restauró la versión anterior; tus datos no se han eliminado.", "AuditFlow", 0x30)
                return
        raise RuntimeError("AuditFlow no pudo iniciar. Revisa la instalación y updates.log; tus datos locales no se han eliminado")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(None, str(error), "AuditFlow - Actualización", 0x10)
