"""Produce el ZIP de actualización y el ZIP inicial (sin datos ni secretos)."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile


def package_release(app, launcher, output, commit, build):
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or build < 1:
        raise ValueError("Se requiere un commit SHA completo y build positivo")
    app, launcher, output = Path(app), Path(launcher), Path(output)
    for component in (app / "main.exe", app / "_internal" / "ffmpeg.exe", launcher):
        if not component.is_file():
            raise ValueError(f"Falta {component}")
    output.mkdir(parents=True, exist_ok=True)
    version = {
        "schema": 1, "platform": "windows-x64", "launcher_protocol": 1,
        "version": f"{build}-{commit[:12]}", "build": build, "commit": commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (app / "version.json").write_text(json.dumps(version, indent=2), encoding="utf-8")
    package = output / "auditflow-pc.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                if path.name.startswith(".env") or path.suffix in (".db", ".sqlite", ".sqlite3"):
                    raise ValueError(f"El paquete contiene datos/secretos: {path}")
                archive.write(path, "main/" + path.relative_to(app).as_posix())
    digest = hashlib.sha256()
    with package.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    version.update(sha256=digest.hexdigest(), size=package.stat().st_size)
    version["package"] = f"/pc-updates/packages/{version['sha256']}.zip"
    with zipfile.ZipFile(output / "AuditFlow-Instalar.zip", "w", zipfile.ZIP_STORED) as installer:
        installer.write(launcher, "AuditFlow.exe")
        installer.write(package, "bootstrap.zip")
        installer.writestr("bootstrap.json", json.dumps(version, indent=2))
        installer.writestr("LEEME.txt", "Extrae todos los archivos en una carpeta permanente. Abre AuditFlow.exe (no main.exe).\nLos datos y la configuracion existentes se conservan. Actualizaciones al proximo inicio.\n")
    installer_path = output / "AuditFlow-Instalar.zip"
    digest = hashlib.sha256()
    with installer_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    version.update(installer_sha256=digest.hexdigest(), installer_size=installer_path.stat().st_size)
    (output / "manifest.json").write_text(json.dumps(version, indent=2), encoding="utf-8")
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--build", type=int, required=True)
    args = parser.parse_args()
    try:
        result = package_release(args.app, args.launcher, args.output, args.commit, args.build)
        print(f"Paquete preparado: {result['version']} ({result['size']} bytes)")
    except Exception as error:
        print(f"No se pudo empaquetar: {error}", file=sys.stderr)
        sys.exit(1)
