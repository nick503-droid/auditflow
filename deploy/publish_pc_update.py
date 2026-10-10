"""Publica exclusivamente el paquete Windows del commit solicitado por el pull.

Sin dependencias Python externas. Los hooks sólo encolan; nunca bloquean el pull.
Los fallos mantienen el manifiesto anterior y la solicitud para poder reintentar.
"""

import argparse
import contextlib
import copy
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


class DeploymentError(RuntimeError):
    """No repetir automáticamente una activación fallida del mismo código."""


def deployment_state():
    path = PRIVATE / "deployment-state.json"
    if not path.exists():
        return {}
    state = read_json(path)
    if not isinstance(state, dict) or state.get("state") not in {"retry_requested", "preflight_failed", "replacing", "recovered", "recovery_failed", "deployed"} or not re.fullmatch(r"[a-f0-9]{40}", str(state.get("commit", ""))):
        raise DeploymentError("Journal backend inválido; revisar antes de otro despliegue, no ignorarlo")
    return state


def record_deployment(revision, state, **details):
    atomic_json(PRIVATE / "deployment-state.json", {"commit": revision, "state": state, **details})


def ensure_deployment_allowed(revision):
    state = deployment_state()
    if state.get("state") in ("replacing", "recovery_failed"):
        raise DeploymentError("Hay una recuperación backend pendiente; revisar deployment-state.json antes de otro despliegue")
    if state.get("commit") == revision and state.get("state") in ("recovered", "preflight_failed"):
        raise DeploymentError("Este despliegue falló y no se repetirá por timer. Revisar logs; --request permite un reintento explícito")


def backend_clean():
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", "backend", "docker-compose.yml"], stdout=subprocess.DEVNULL).returncode:
        raise ValueError("Hay cambios locales en backend/Compose: no se reemplazarán por otro commit")


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
    state = deployment_state()
    # Un segundo pull debe encolarse aunque otro worker esté activando una
    # versión. No borrar por ello un journal de recuperación pendiente.
    if state.get("commit") == revision and state.get("state") in ("recovered", "preflight_failed"):
        record_deployment(revision, "retry_requested")
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


def deployment_commit(config):
    try:
        url = config.get("api_url", "http://127.0.0.1:3000").rstrip("/") + "/system/deployment"
        with urllib.request.urlopen(url, timeout=5) as response:
            value = json.loads(response.read(4097))
            commit = value.get("commit") if isinstance(value, dict) else None
            if isinstance(commit, str) and (commit == "development" or re.fullmatch(r"[a-f0-9]{40}", commit)):
                return commit
            return None
    except (OSError, ValueError):
        return None


def deployment_ready(config, revision):
    return deployment_commit(config) == revision


def compose_literals(value):
    """Un modelo ya resuelto no debe interpolar $ otra vez (incluye secretos)."""
    if isinstance(value, str):
        return value.replace("$", "$$")
    if isinstance(value, list):
        return [compose_literals(v) for v in value]
    if isinstance(value, dict):
        return {k: compose_literals(v) for k, v in value.items()}
    return value


def inspect_container(docker, name):
    result = subprocess.run([*docker, "inspect", name], check=True, capture_output=True, text=True, timeout=30)
    values = json.loads(result.stdout)
    if not isinstance(values, list) or len(values) != 1:
        raise ValueError("Inspección Docker inesperada")
    return values[0]


def recovery_model(model, container):
    """Rollback limitado al backend actual, con los MISMOS montajes/red/puertos.

    Rechaza cambios de topología/configuración avanzada en vez de improvisar una
    recuperación incompleta. Nunca crea ni elimina volúmenes o dependencias.
    """
    service = model["services"]["backend"]
    allowed = {"build", "image", "pull_policy", "container_name", "environment", "ports", "volumes", "depends_on", "networks", "restart", "working_dir", "entrypoint", "command", "user", "expose", "labels"}
    if set(service) - allowed:
        raise ValueError("Configuración backend avanzada: preparar recuperación manual antes de desplegar")
    labels = container["Config"].get("Labels") or {}
    if labels.get("com.docker.compose.project") != model["name"] or labels.get("com.docker.compose.service") != "backend" or not container["State"].get("Running"):
        raise ValueError("No hay un backend Compose activo identificable para recuperar")
    host = container["HostConfig"]
    if host.get("Privileged") or host.get("ReadonlyRootfs") or host.get("CapAdd") or host.get("CapDrop") or host.get("Devices") or host.get("SecurityOpt"):
        raise ValueError("Backend con opciones especiales: requiere plan de recuperación manual")
    expected_mounts = set()
    for volume in service.get("volumes", []):
        if volume.get("volume") or (set(volume.get("bind", {})) - {"create_host_path"}):
            raise ValueError("Opciones avanzadas de montaje: requiere recuperación manual")
        source = volume.get("source")
        if volume["type"] == "volume":
            source = model.get("volumes", {}).get(source, {}).get("name")
        if not source or volume["type"] not in ("bind", "volume"):
            raise ValueError("Montaje no recuperable automáticamente")
        expected_mounts.add((volume["type"], source, volume["target"], not volume.get("read_only", False)))
    actual_mounts = {(m["Type"], m.get("Name") if m["Type"] == "volume" else m["Source"], m["Destination"], m["RW"]) for m in container.get("Mounts", [])}
    if expected_mounts != actual_mounts:
        raise ValueError("Cambió el almacenamiento backend; no se reemplaza automáticamente")
    expected_ports = {(str(p["target"]) + "/" + p.get("protocol", "tcp"), str(p["published"]), p.get("host_ip", "")) for p in service.get("ports", [])}
    actual_ports = {(target, p["HostPort"], p.get("HostIp", "")) for target, ports in (host.get("PortBindings") or {}).items() for p in (ports or [])}
    if expected_ports != actual_ports:
        raise ValueError("Cambiaron los puertos backend; requiere revisión manual")
    network_names = {model["networks"][key]["name"] for key in service.get("networks", {"default": None})}
    if any(options for options in service.get("networks", {}).values()) or any(options.get("IPAMConfig") for options in container["NetworkSettings"]["Networks"].values()):
        raise ValueError("Red con opciones avanzadas: requiere recuperación manual")
    if network_names != set(container["NetworkSettings"]["Networks"]):
        raise ValueError("Cambió la red backend; requiere revisión manual")
    previous = copy.deepcopy(service)
    for key in ("build", "depends_on", "labels", "expose"):
        previous.pop(key, None)
    previous.update(image=container["Image"], pull_policy="never",
                    environment=dict(item.split("=", 1) for item in container["Config"].get("Env", [])),
                    command=container["Config"].get("Cmd") or [],
                    entrypoint=container["Config"].get("Entrypoint") or [],
                    working_dir=container["Config"].get("WorkingDir") or "/",
                    user=container["Config"].get("User") or "0")
    restart = host.get("RestartPolicy", {})
    previous["restart"] = restart.get("Name") or "no"
    if previous["restart"] == "on-failure" and restart.get("MaximumRetryCount"):
        previous["restart"] += ":" + str(restart["MaximumRetryCount"])
    networks = {key: {"external": True, "name": model["networks"][key]["name"]} for key in service.get("networks", {"default": None})}
    volumes = {key: {"external": True, "name": value["name"]} for key, value in model.get("volumes", {}).items()}
    return {"name": model["name"], "services": {"backend": previous}, "networks": networks, "volumes": volumes}


def wait_backend(config, revision, docker, name, image, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if deployment_ready(config, revision):
            active = inspect_container(docker, name)
            if active["Image"] == image and active["State"].get("Running"):
                return True
        time.sleep(3)
    return False


def deploy_backend(config, revision, snapshot):
    """Construye desde el commit exacto, aunque ocurra otro pull durante el build."""
    ensure_deployment_allowed(revision)
    backend_clean()
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Commit de despliegue inválido")
    snapshot = Path(snapshot)
    snapshot.mkdir(parents=True, exist_ok=True)
    archive = Path(snapshot) / "source.zip"
    subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", "-o", str(archive), revision, "backend", "docker-compose.yml"], check=True)
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            parts = Path(info.filename).parts
            if ".." in parts or Path(info.filename).is_absolute():
                raise ValueError("Ruta inválida en snapshot Git")
        source.extractall(snapshot)
    override = Path(snapshot) / "override.json"
    image = "auditflow-backend:" + revision
    atomic_json(override, compose_literals({"services": {"backend": {
        "image": image, "pull_policy": "never",
        "build": {"context": str(snapshot / "backend"), "args": {"AUDITFLOW_DEPLOY_COMMIT": revision}},
    }}}))
    docker = config.get("docker_command", ["docker"])
    if not isinstance(docker, list) or not docker or any(not isinstance(p, str) for p in docker):
        raise ValueError("docker_command debe ser una lista de argumentos")
    environment = os.environ.copy()
    environment["AUDITFLOW_DEPLOY_COMMIT"] = revision
    compose = [
        *docker, "compose", "--project-directory", str(ROOT),
        "-f", str(Path(snapshot) / "docker-compose.yml"), "-f", str(override),
    ]
    try:
        result = subprocess.run([*compose, "config", "--format", "json"], cwd=ROOT, env=environment, check=True, capture_output=True, text=True, timeout=30)
        model = json.loads(result.stdout)
        name = model["services"]["backend"]["container_name"]
        previous = inspect_container(docker, name)
        rollback = recovery_model(model, previous)
        old_commit = deployment_commit(config)
        if not old_commit:
            raise ValueError("El backend anterior no responde; revisar su estado antes de reemplazarlo")
        recovery = PRIVATE / "recovery" / revision
        recovery.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(recovery, 0o700)
        backup = recovery / "compose.json"
        atomic_json(backup, compose_literals(rollback))
        os.chmod(backup, 0o600)  # Puede contener variables privadas del contenedor.
        # Construir/verificar sin sustituir el contenedor activo ni montar datos.
        subprocess.run([*compose, "build", "backend"], cwd=ROOT, env=environment, check=True, timeout=1800)
        built = subprocess.run([*docker, "image", "inspect", image], check=True, capture_output=True, text=True, timeout=30)
        candidate = json.loads(built.stdout)[0]
        if candidate["Config"].get("Labels", {}).get("org.opencontainers.image.revision") != revision:
            raise ValueError("La imagen construida no identifica el commit solicitado")
        subprocess.run([*docker, "run", "--rm", "--network", "none", "--read-only",
                        "-e", "AUDITFLOW_EXPECTED_COMMIT=" + revision, "--entrypoint", "node",
                        candidate["Id"], "scripts/verify-production.cjs"], check=True, timeout=60)
        # Activar por ID inmutable, no por un tag que otro build pueda mover.
        override_model = read_json(override)
        override_model["services"]["backend"]["image"] = candidate["Id"]
        atomic_json(override, override_model)
        backend_clean()
        if not request_matches(revision):
            return False
        current = inspect_container(docker, name)
        if current["Id"] != previous["Id"] or current["Image"] != previous["Image"]:
            raise ValueError("El backend cambió durante el build; no se sustituye")
    except Exception as error:
        record_deployment(revision, "preflight_failed")
        raise DeploymentError(f"Falló validación previa; backend no reemplazado: {error}") from error
    record_deployment(revision, "replacing", previous_image=previous["Image"], recovery=str(backup))
    try:
        subprocess.run([*compose, "up", "-d", "--no-build", "--pull", "never", "--no-deps", "backend"], cwd=ROOT, env=environment, check=True, timeout=180)
        if not wait_backend(config, revision, docker, name, candidate["Id"]):
            raise RuntimeError("El backend actualizado no confirmó su versión/imagen")
    except Exception as error:
        try:
            subprocess.run([*docker, "compose", "--project-directory", str(ROOT), "-p", model["name"], "-f", str(backup),
                            "up", "-d", "--force-recreate", "--no-build", "--pull", "never", "--no-deps", "backend"],
                           cwd=ROOT, check=True, timeout=180)
            if not wait_backend(config, old_commit, docker, name, previous["Image"]):
                raise RuntimeError("El backend anterior tampoco confirmó recuperación")
            record_deployment(revision, "recovered", previous_image=previous["Image"], recovery=str(backup))
        except Exception as recovery_error:
            record_deployment(revision, "recovery_failed", previous_image=previous["Image"], recovery=str(backup))
            raise DeploymentError(f"Falló despliegue y recuperación; intervención necesaria: {recovery_error}") from error
        raise DeploymentError(f"No publicado; imagen/configuración backend anterior recuperada. Revisar antes de reintentar: {error}") from error
    record_deployment(revision, "deployed", image=candidate["Id"])
    return True


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
    ensure_deployment_allowed(revision)
    backend_clean()
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
            if deploy_backend(config, revision, temporary / "snapshot") is False:
                return False
        if not request_matches(revision):
            return False
        if not deployment_ready(config, revision):
            raise DeploymentError("El backend dejó de confirmar el SHA antes de publicar; se conserva el manifiesto PC")
        backend_clean()
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
                except DeploymentError as error:
                    print(f"[AuditFlow] Publicación detenida: {error}", flush=True)
                    return
                except urllib.error.HTTPError as error:
                    print(f"[AuditFlow] GitHub HTTP {error.code}; esperando paquete {revision[:12]}", flush=True)
                    if error.code in (401, 403):
                        print("Revisar token/permiso Contents:read o límite de consultas GitHub.", flush=True)
                        return
                except Exception as error:
                    print(f"[AuditFlow] No publicado; se conserva manifiesto PC anterior: {error}", flush=True)
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
