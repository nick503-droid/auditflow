"""Activación inicial explícita en Ubuntu. No ejecutar en las PC Windows."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pc-app"))
from core.pc_updates import atomic_json, read_json


def install_timer():
    import shutil
    if not shutil.which("systemctl"):
        raise RuntimeError("No hay systemd; instalar sólo hooks o configurar un servicio equivalente")
    directory = Path.home() / ".config" / "systemd" / "user"
    directory.mkdir(parents=True, exist_ok=True)
    def quote(value):
        return '"' + str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'
    service = (
        "[Unit]\nDescription=Publicar actualizaciones AuditFlow pendientes de pull\n"
        "[Service]\nType=oneshot\n"
        f"WorkingDirectory={quote(ROOT)}\n"
        f"ExecStart={quote(sys.executable)} {quote(ROOT / 'deploy' / 'publish_pc_update.py')} --worker\n"
        "TimeoutStartSec=75min\n"
    )
    timer = (
        "[Unit]\nDescription=Reintentar publicaciones AuditFlow pendientes\n"
        "[Timer]\nOnBootSec=1min\nOnUnitInactiveSec=5min\n"
        "Unit=auditflow-pc-publisher.service\n[Install]\nWantedBy=timers.target\n"
    )
    for name, content in (("auditflow-pc-publisher.service", service), ("auditflow-pc-publisher.timer", timer)):
        path = directory / name
        if path.exists() and "AuditFlow" not in path.read_text(encoding="utf-8"):
            raise RuntimeError(f"Ya existe {path}; no se reemplaza")
        path.write_text(content, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "auditflow-pc-publisher.timer"], check=True)


def install(sudo_docker=False, with_timer=False):
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Ejecutar únicamente en el servidor Linux, no en desarrollo Windows")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD"]).returncode:
        raise RuntimeError("Hay cambios locales: guardarlos/revisarlos antes de activar el despliegue")
    hooks = subprocess.run(["git", "-C", str(ROOT), "config", "--get", "core.hooksPath"], capture_output=True, text=True).stdout.strip()
    if hooks and hooks != ".auditflow-deploy/hooks":
        raise RuntimeError(f"Ya existe core.hooksPath={hooks}; no se reemplaza. Integrar los hooks manualmente")
    default_hooks = Path(git("rev-parse", "--git-path", "hooks"))
    if not default_hooks.is_absolute():
        default_hooks = ROOT / default_hooks
    existing = [p.name for p in default_hooks.glob("*") if not p.name.endswith(".sample") and p.is_file()]
    if not hooks and existing:
        raise RuntimeError(f"Hay hooks existentes: {existing}. No se desactivarán; integrar manualmente")
    remote = git("remote", "get-url", "origin")
    match = re.search(r"github\.com[:/]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$", remote)
    if not match:
        raise RuntimeError("Se requiere origin en GitHub para descargar las compilaciones")
    private = ROOT / ".auditflow-deploy"
    private.mkdir(mode=0o700, exist_ok=True)
    os.chmod(private, 0o700)
    (ROOT / "pc_updates").mkdir(exist_ok=True)
    config = read_json(private / "config.json", {})
    config.setdefault("repository", match.group(1))
    config.setdefault("api_url", "http://127.0.0.1:3000")
    config.setdefault("github_token", "")
    config.setdefault("docker_command", ["sudo", "-n", "docker"] if sudo_docker else ["docker"])
    config["enabled"] = True
    command = config["docker_command"]
    result = subprocess.run([*command, "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise RuntimeError("El usuario necesita acceso no interactivo a Docker. Configurar permisos antes de activar")
    atomic_json(private / "config.json", config)
    os.chmod(private / "config.json", 0o600)
    managed_hooks = private / "hooks"
    managed_hooks.mkdir(exist_ok=True)
    for name in ("post-merge", "post-rewrite"):
        path = managed_hooks / name
        path.write_bytes((ROOT / "deploy" / "hooks" / name).read_bytes())
        os.chmod(path, 0o755)
    subprocess.run(["git", "-C", str(ROOT), "config", "--local", "core.hooksPath", ".auditflow-deploy/hooks"], check=True)
    if with_timer:
        install_timer()
    print("Activado: cada pull con cambios en origin/main solicitará el paquete PC. No se borran datos/volúmenes.")
    subprocess.run([sys.executable, str(ROOT / "deploy" / "publish_pc_update.py"), "--request"], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sudo-docker", action="store_true", help="Usar sudo -n docker (requiere permiso configurado)")
    parser.add_argument("--install-user-timer", action="store_true", help="Reintentar publicaciones tras reinicios mediante systemd de usuario")
    args = parser.parse_args()
    try:
        install(args.sudo_docker, args.install_user_timer)
    except Exception as error:
        print(f"No se activó: {error}", file=sys.stderr)
        sys.exit(1)
