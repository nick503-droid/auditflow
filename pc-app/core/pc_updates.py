"""Actualizaciones de PC: descargas aisladas, sin tocar datos ni cerrar la UI.

Sólo utiliza la biblioteca estándar para compartirlo con el lanzador empaquetado.
Los paquetes se activan al siguiente inicio, nunca durante una grabación.
"""

import contextlib
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import random
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile

PROTOCOL = 1
MAX_PACKAGE_SIZE = 1024 * 1024 * 1024
MAX_EXPANDED_SIZE = 3 * MAX_PACKAGE_SIZE
MAX_FILES = 30000
LOG = logging.getLogger("AuditFlow.Updates")


def updates_home():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AuditFlowClient"


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def update_lock(root):
    """Una descarga/activación por perfil; el SO libera el bloqueo si hay crash."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "update.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def validate_manifest(value):
    if not isinstance(value, dict):
        raise ValueError("Manifiesto inválido")
    if value.get("schema") != PROTOCOL or value.get("platform") != "windows-x64":
        raise ValueError("Protocolo/plataforma no compatible")
    if value.get("launcher_protocol") != PROTOCOL:
        raise ValueError("Esta versión requiere otro lanzador")
    if type(value.get("build")) is not int or value["build"] < 1:
        raise ValueError("Número de compilación inválido")
    if not isinstance(value.get("version"), str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,80}", value["version"]):
        raise ValueError("Versión inválida")
    for field, length in (("commit", 40), ("sha256", 64)):
        if not isinstance(value.get(field), str) or not re.fullmatch(r"[a-f0-9]{%d}" % length, value[field]):
            raise ValueError(f"{field} inválido")
    if type(value.get("size")) is not int or not 0 < value["size"] <= MAX_PACKAGE_SIZE:
        raise ValueError("Tamaño inválido")
    if value.get("package") != f"/pc-updates/packages/{value['sha256']}.zip":
        raise ValueError("Ruta del paquete inválida")
    # Ignorar campos de distribución (p.ej. hash del instalador) al comparar
    # una instalación bootstrap con el mismo paquete servido por la LAN.
    return {key: value[key] for key in (
        "schema", "platform", "launcher_protocol", "version", "build",
        "commit", "sha256", "size", "package",
    )}


def application_version():
    if not getattr(sys, "frozen", False):
        return None
    value = read_json(Path(sys.executable).parent / "version.json")
    return value if isinstance(value, dict) else None


def package_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path, manifest):
    manifest = validate_manifest(manifest)
    if Path(path).stat().st_size != manifest["size"] or package_hash(path) != manifest["sha256"]:
        raise ValueError("El paquete está incompleto o no coincide con su SHA-256")


def safe_extract(path, destination):
    """Rechaza zip-slip, enlaces, ADS, nombres Windows ambiguos y zip bombs."""
    destination = Path(destination).resolve()
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_EXPANDED_SIZE:
            raise ValueError("Paquete demasiado grande")
        seen = set()
        for member in members:
            name = member.filename
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != "main" or "\\" in name or name.startswith("/"):
                raise ValueError("El paquete debe contener solamente la carpeta main")
            for part in parts:
                if part in (".", "..") or part.endswith((".", " ")) or re.search(r'[<>:"|?*\x00-\x1f]', part):
                    raise ValueError("Nombre de archivo inseguro")
                if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part):
                    raise ValueError("Nombre Windows reservado")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISDIR(mode) or stat.S_ISREG(mode))):
                raise ValueError("No se permiten enlaces ni archivos especiales")
            key = "/".join(parts).casefold()
            if key in seen:
                raise ValueError("Archivo duplicado en el paquete")
            seen.add(key)
            target = destination.joinpath(*parts)
            if destination not in target.resolve().parents:
                raise ValueError("Ruta fuera de la carpeta temporal")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
    for required in ("main/main.exe", "main/_internal/ffmpeg.exe", "main/version.json"):
        if not (destination / required).is_file():
            raise ValueError(f"Falta un componente del programa: {required}")


def installed_path(root, manifest):
    manifest = validate_manifest(manifest)
    return Path(root) / "versions" / manifest["sha256"] / "main"


def is_installed(root, manifest):
    manifest = validate_manifest(manifest)
    app = installed_path(root, manifest)
    return (app / "main.exe").is_file() and read_json(app.parent / "installed.json") == manifest


def stage_archive(root, archive, manifest):
    """Llamar con update_lock. Sólo escribe dentro del almacén de versiones."""
    root = Path(root)
    manifest = validate_manifest(manifest)
    verify_archive(archive, manifest)
    if not is_installed(root, manifest):
        versions = root / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="extract-", dir=root) as temporary:
            temporary = Path(temporary)
            safe_extract(archive, temporary)
            version = read_json(temporary / "main" / "version.json")
            for key in ("build", "commit", "version", "launcher_protocol"):
                if not isinstance(version, dict) or version.get(key) != manifest[key]:
                    raise ValueError("La versión interna no coincide con el manifiesto")
            atomic_json(temporary / "installed.json", manifest)
            target = versions / manifest["sha256"]
            # Un directorio preexistente sin marcador válido no se reemplaza a ciegas.
            if target.exists():
                raise ValueError("Directorio de versión incompleto; revisar instalación")
            os.replace(temporary, target)
    atomic_json(root / "pending.json", manifest)


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        before, after = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if (before.scheme, before.netloc) != (after.scheme, after.netloc):
            raise ValueError("Redirección a otro servidor rechazada")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_and_stage(root, api_url, current, stop=None):
    """El manifiesto pequeño se consulta siempre; el ZIP sólo si falta la versión."""
    parsed = urllib.parse.urlsplit(api_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username:
        raise ValueError("Servidor de actualización inválido")
    opener = urllib.request.build_opener(SameOriginRedirect())
    base = api_url.rstrip("/")
    request = urllib.request.Request(base + "/pc-updates/manifest.json", headers={"Cache-Control": "no-cache"})
    with opener.open(request, timeout=5) as response:
        body = response.read(65537)
    if len(body) > 65536:
        raise ValueError("Manifiesto demasiado grande")
    manifest = validate_manifest(json.loads(body))
    if manifest["build"] <= current.get("build", 0):
        return None
    root = Path(root)
    with update_lock(root):
        rejected = read_json(root / "rejected.json", {})
        if rejected.get("sha256") == manifest["sha256"]:
            return None
        pending = read_json(root / "pending.json", {})
        if pending.get("build", 0) >= manifest["build"] and is_installed(root, pending):
            return pending
        if is_installed(root, manifest):
            atomic_json(root / "pending.json", manifest)
            return manifest
        with tempfile.TemporaryDirectory(prefix="download-", dir=root) as temporary:
            package = Path(temporary) / "package.zip"
            count = 0
            deadline = time.monotonic() + 1200
            with opener.open(base + manifest["package"], timeout=30) as source, package.open("wb") as output:
                while True:
                    if (stop and stop.is_set()) or time.monotonic() > deadline:
                        raise TimeoutError("Descarga cancelada; se reintentará")
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > manifest["size"]:
                        raise ValueError("El servidor envió más datos de los anunciados")
                    output.write(chunk)
            stage_archive(root, package, manifest)
    return manifest


def start_background_updates(api_url_getter):
    """No actualiza sesiones de desarrollo ni instalaciones antiguas sin lanzador."""
    current = application_version()
    if os.name != "nt" or not current or not os.environ.get("AUDITFLOW_MANAGED_CLIENT"):
        return None
    root = updates_home()
    root.mkdir(parents=True, exist_ok=True)
    if not LOG.handlers:
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(root / "updates.log", maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
        LOG.addHandler(handler)
        LOG.setLevel(logging.INFO)
    stop = threading.Event()

    def worker():
        if stop.wait(random.uniform(15, 45)):
            return
        while not stop.is_set():
            try:
                prepared = check_and_stage(root, api_url_getter(), current, stop)
                if prepared:
                    LOG.info("Versión %s preparada para el próximo inicio", prepared["version"])
            except Exception as error:
                LOG.info("No se pudo preparar la actualización; se reintentará: %s", error)
            # Evita consultas por segundo y descargas simultáneas en todas las PC.
            stop.wait(random.uniform(12 * 60, 18 * 60))

    threading.Thread(target=worker, name="ActualizacionesPC", daemon=True).start()
    return stop


def mark_application_ready():
    token = os.environ.get("AUDITFLOW_READY_TOKEN", "")
    if os.environ.get("AUDITFLOW_MANAGED_CLIENT") and re.fullmatch(r"[a-f0-9]{32}", token):
        atomic_json(updates_home() / "health" / (token + ".json"), {"ready": True})
