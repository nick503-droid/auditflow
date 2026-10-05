"""Publica exclusivamente el paquete Windows del commit solicitado por el pull.

Sin dependencias Python externas. Los hooks sólo encolan; nunca bloquean el pull.
Los fallos mantienen el manifiesto anterior y la solicitud para poder reintentar.
"""

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pc-app"))
from core.pc_updates import atomic_json, package_hash, read_json, validate_manifest, verify_archive

PRIVATE = ROOT / ".auditflow-deploy"
PUBLIC = ROOT / "pc_updates"


def git(*arguments):
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments], text=True).strip()


def head():
    revision = git("rev-parse", "HEAD")
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("HEAD inválido")
    return revision


def request_publication():
    config = read_json(PRIVATE / "config.json", {})
    if not config.get("enabled"):
        return
    revision = head()
    if revision != git("rev-parse", "refs/remotes/origin/main"):
        raise ValueError("El servidor debe estar en el commit de origin/main (usar pull --ff-only)")
    atomic_json(PRIVATE / "requested.json", {"commit": revision})
    # Desacoplar del terminal de Git y no bloquear el pull durante la compilación.
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    with (PRIVATE / "publish.log").open("ab") as log:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--worker"],
            cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
            stdout=log, stderr=log, start_new_session=True,
        )
    print(f"[AuditFlow] Actualización PC solicitada para {revision[:12]}; ver .auditflow-deploy/publish.log")


class SecureRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ValueError("GitHub debe descargar mediante HTTPS")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).hostname != urllib.parse.urlsplit(newurl).hostname:
            redirected.remove_header("Authorization")
        return redirected


def github_request(url, config, accept="application/vnd.github+json"):
    request = urllib.request.Request(url, headers={
        "Accept": accept, "User-Agent": "AuditFlow-Server-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    token = os.environ.get("AUDITFLOW_GITHUB_TOKEN") or config.get("github_token")
    if token:
        # No propagar credenciales a los hosts de almacenamiento en redirecciones.
        request.add_unredirected_header("Authorization", "Bearer " + token)
    return urllib.request.build_opener(SecureRedirect()).open(request, timeout=30)


def github_release(config, revision):
    repository = config.get("repository", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Repositorio GitHub inválido")
    url = f"https://api.github.com/repos/{repository}/releases/tags/pc-{revision}"
    with github_request(url, config) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise ValueError("Respuesta de GitHub demasiado grande")
    release = json.loads(body)
    if release.get("draft") or release.get("tag_name") != f"pc-{revision}":
        raise ValueError("Release incorrecto o incompleto")
    return release


def download_asset(release, name, destination, config, max_bytes):
    asset = next((a for a in release.get("assets", []) if a.get("name") == name), None)
    if not asset:
        raise ValueError(f"El release no contiene {name}")
    url = asset.get("url", "")
    expected = f"https://api.github.com/repos/{config['repository']}/releases/assets/"
    if not url.startswith(expected) or not url[len(expected):].isdigit():
        raise ValueError("URL de asset inválida")
    count = 0
    deadline = time.monotonic() + 1200
    with github_request(url, config, "application/octet-stream") as source, Path(destination).open("wb") as output:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("Descarga de GitHub excedió 20 minutos")
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            if count > max_bytes:
                raise ValueError("Asset demasiado grande")
            output.write(chunk)
    if count != asset.get("size"):
        raise ValueError("Descarga de asset incompleta")


def request_matches(revision):
    return (
        read_json(PRIVATE / "config.json", {}).get("enabled")
        and read_json(PRIVATE / "requested.json", {}).get("commit") == revision
        and head() == revision
    )


def deployment_ready(config, revision):
    try:
        url = config.get("api_url", "http://127.0.0.1:3000").rstrip("/") + "/system/deployment"
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read(4096)).get("commit") == revision
    except (OSError, ValueError):
        return False


def deploy_backend(config, revision, snapshot):
    """Construye desde el commit exacto, aunque ocurra otro pull durante el build."""
    Path(snapshot).mkdir(parents=True, exist_ok=True)
    archive = Path(snapshot) / "source.zip"
    subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", "-o", str(archive), revision, "backend", "docker-compose.yml"], check=True)
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            parts = Path(info.filename).parts
            if ".." in parts or Path(info.filename).is_absolute():
                raise ValueError("Ruta inválida en snapshot Git")
        source.extractall(snapshot)
    override = Path(snapshot) / "override.json"
    atomic_json(override, {"services": {"backend": {"build": {"context": str(Path(snapshot) / "backend")}}}})
    docker = config.get("docker_command", ["docker"])
    if not isinstance(docker, list) or not docker or any(not isinstance(p, str) for p in docker):
        raise ValueError("docker_command debe ser una lista de argumentos")
    environment = os.environ.copy()
    environment["AUDITFLOW_DEPLOY_COMMIT"] = revision
    # DB/MinIO existentes se conservan. No se hace down ni se eliminan volúmenes.
    subprocess.run([
        *docker, "compose", "--project-directory", str(ROOT),
        "-f", str(Path(snapshot) / "docker-compose.yml"), "-f", str(override),
        "up", "-d", "--build", "--no-deps", "backend",
    ], cwd=ROOT, env=environment, check=True, timeout=1800)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if deployment_ready(config, revision):
            return
        time.sleep(3)
    raise RuntimeError("El backend actualizado no confirmó su versión; no se publica el paquete de PC")


def immutable_copy(source, target, digest):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if package_hash(target) != digest:
            raise ValueError("Un paquete publicado fue modificado; revisar almacenamiento")
        return
    # Todos los temporales están en el mismo filesystem que el destino.
    os.replace(source, target)


def publish_once(config, revision):
    if not request_matches(revision):
        return False
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", "backend", "docker-compose.yml"], stdout=subprocess.DEVNULL).returncode:
        raise ValueError("Hay cambios locales en backend/Compose: no se reemplazarán por otro commit")
    published = read_json(PUBLIC / "manifest.json", {})
    if published.get("commit") == revision and deployment_ready(config, revision):
        return True
    release = github_release(config, revision)
    with tempfile.TemporaryDirectory(prefix="release-", dir=PRIVATE) as temporary:
        temporary = Path(temporary)
        raw_manifest = temporary / "manifest.json"
        download_asset(release, "manifest.json", raw_manifest, config, 65536)
        raw = read_json(raw_manifest)
        manifest = validate_manifest(raw)
        if manifest["commit"] != revision:
            raise ValueError("El ejecutable no corresponde al commit del servidor")
        if published.get("build", 0) > manifest["build"]:
            raise ValueError("No se permite downgrade automático; publicar otra compilación")
        package = temporary / "app.zip"
        download_asset(release, "auditflow-pc.zip", package, config, manifest["size"])
        verify_archive(package, manifest)
        installer_hash = raw.get("installer_sha256", "")
        installer_size = raw.get("installer_size")
        if not re.fullmatch(r"[a-f0-9]{64}", installer_hash) or type(installer_size) is not int or not 0 < installer_size <= 2 * 1024 ** 3:
            raise ValueError("Metadatos del instalador inválidos")
        installer = temporary / "installer.zip"
        download_asset(release, "AuditFlow-Instalar.zip", installer, config, installer_size)
        if installer.stat().st_size != installer_size or package_hash(installer) != installer_hash:
            raise ValueError("El instalador no coincide con su checksum")
        if not request_matches(revision):
            return False
        if not deployment_ready(config, revision):
            deploy_backend(config, revision, temporary / "snapshot")
        if not request_matches(revision):
            return False
        immutable_copy(package, PUBLIC / "packages" / (manifest["sha256"] + ".zip"), manifest["sha256"])
        immutable_copy(installer, PUBLIC / "installers" / (installer_hash + ".zip"), installer_hash)
        manifest["installer"] = f"/pc-updates/installers/{installer_hash}.zip"
        # Publicar el puntero AL FINAL. PCs nunca ven paquetes parciales.
        atomic_json(PUBLIC / "manifest.json", manifest)
        print(f"[AuditFlow] PUBLICADO {manifest['version']} / {revision}", flush=True)
    return True


@contextlib.contextmanager
def worker_lock():
    import fcntl
    with (PRIVATE / "worker.lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def worker(once=False):
    config = read_json(PRIVATE / "config.json", {})
    if not config.get("enabled"):
        return
    try:
        with worker_lock():
            deadline = time.monotonic() + 3600
            while time.monotonic() < deadline:
                config = read_json(PRIVATE / "config.json", {})
                if not config.get("enabled"):
                    return
                revision = read_json(PRIVATE / "requested.json", {}).get("commit")
                if not revision or not re.fullmatch(r"[a-f0-9]{40}", revision):
                    return
                try:
                    if publish_once(config, revision):
                        if read_json(PRIVATE / "requested.json", {}).get("commit") == revision:
                            return
                        continue
                except urllib.error.HTTPError as error:
                    print(f"[AuditFlow] GitHub HTTP {error.code}; esperando paquete {revision[:12]}", flush=True)
                    if error.code in (401, 403):
                        print("Revisar token/permiso Contents:read o límite de consultas GitHub.", flush=True)
                        return
                except Exception as error:
                    print(f"[AuditFlow] No publicado; se conserva versión anterior: {error}", flush=True)
                if once:
                    return
                time.sleep(60)
            print("[AuditFlow] Sigue pendiente después de 1 hora. Reintentar --worker o activar timer.", flush=True)
    except BlockingIOError:
        # Otro pull ya tiene un worker; leerá la solicitud más reciente.
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        if args.request:
            request_publication()
        elif args.worker or args.once:
            worker(once=args.once)
        else:
            parser.error("Usar --request, --worker o --once")
    except Exception as error:
        print(f"[AuditFlow] No se pudo solicitar/publicar: {error}", file=sys.stderr)
        sys.exit(1)
