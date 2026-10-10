"""Generación y caché local de previsualizaciones ligeras para evidencias."""

import hashlib
import io
import os
import logging
import subprocess
import tempfile
import time
from urllib.parse import urlparse

from PIL import Image, ImageOps
import requests

from core.ffmpeg_path import obtener_ruta_ffmpeg

LOG = logging.getLogger("AuditFlow.Thumbnails")


CARPETA_MINIATURAS = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "AuditFlow",
    "thumbnails",
)
TAMANIO_CACHE = (160, 96)
CALIDAD_JPEG = 55
EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
EXTENSIONES_VIDEO = {".mp4", ".avi", ".mkv", ".mov", ".webm"}


def _extension(ruta_o_url: str) -> str:
    return os.path.splitext(urlparse(ruta_o_url).path)[1].lower()


def _ruta_cache(ruta_o_url: str, size: tuple[int, int]) -> str:
    version = ""
    if not ruta_o_url.startswith(("http://", "https://")):
        try:
            stat = os.stat(ruta_o_url)
            version = f"{stat.st_mtime_ns}|{stat.st_size}"
        except OSError:
            pass
    clave = hashlib.sha256(f"{ruta_o_url}|{size}|{version}".encode("utf-8")).hexdigest()
    os.makedirs(CARPETA_MINIATURAS, exist_ok=True)
    return os.path.join(CARPETA_MINIATURAS, f"{clave}.jpg")


def _convertir_a_miniatura(imagen: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Devuelve una imagen RGB de tamaño fijo y calidad económica para la UI."""
    imagen = ImageOps.exif_transpose(imagen).convert("RGB")
    return ImageOps.pad(imagen, size, method=Image.Resampling.LANCZOS, color="#1e293b")


def _guardar_cache(imagen: Image.Image, ruta_cache: str) -> None:
    temporal = None
    try:
        fd, temporal = tempfile.mkstemp(dir=os.path.dirname(ruta_cache), suffix=".jpg")
        os.close(fd)
        imagen.save(temporal, "JPEG", quality=CALIDAD_JPEG, optimize=True)
        os.replace(temporal, ruta_cache)
    except OSError:
        pass
    finally:
        if temporal and os.path.exists(temporal):
            os.remove(temporal)


def _descargar_imagen(url: str) -> Image.Image | None:
    """Descarga sólo imágenes; evita una descarga no limitada por error."""
    try:
        from api.client import normalizar_url

        limite = 15 * 1024 * 1024
        datos = bytearray()
        deadline = time.monotonic() + 12
        with requests.get(normalizar_url(url), stream=True, timeout=(3, 5)) as respuesta:
            respuesta.raise_for_status()
            if int(respuesta.headers.get("Content-Length", 0)) > limite:
                return None
            for bloque in respuesta.iter_content(chunk_size=65536):
                datos.extend(bloque)
                if len(datos) > limite or time.monotonic() > deadline:
                    return None
        with Image.open(io.BytesIO(datos)) as imagen:
            imagen.draft("RGB", (320, 192))
            pequena = ImageOps.exif_transpose(imagen)
            pequena.thumbnail((320, 192), Image.Resampling.LANCZOS)
            return pequena.copy()
    except Exception as error:
        LOG.debug("Miniatura de imagen no disponible: %s", error)
        return None


def _primer_cuadro_video(ruta_o_url: str) -> Image.Image | None:
    fuente = ruta_o_url
    if ruta_o_url.startswith(("http://", "https://")):
        try:
            from api.client import normalizar_url
            fuente = normalizar_url(ruta_o_url)
        except Exception:
            pass

    try:
        # OpenCV puede bloquear al abrir un video remoto. FFmpeg corre aislado,
        # limita lectura por red y subprocess mata/recoge el proceso al expirar.
        resultado = subprocess.run([
            obtener_ruta_ffmpeg(), "-hide_banner", "-loglevel", "error",
            "-nostdin", "-threads", "1", "-rw_timeout", "3000000",
            "-i", fuente, "-frames:v", "1", "-an", "-threads", "1",
            "-vf", "scale=160:96:force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
        ], capture_output=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if resultado.returncode == 0 and resultado.stdout:
            with Image.open(io.BytesIO(resultado.stdout)) as imagen:
                return imagen.copy()
    except (OSError, subprocess.SubprocessError) as error:
        LOG.debug("Miniatura de video no disponible: %s", error)
    return None


def generar_miniatura(ruta_o_url: str, size=TAMANIO_CACHE, *, placeholder=True) -> Image.Image | None:
    """Obtiene una miniatura cacheada de imagen/video sin bloquear la interfaz.

    Las miniaturas se guardan como JPEG de baja calidad en AppData y las llamadas
    siguientes no descargan ni decodifican otra vez la evidencia completa.
    """
    if not ruta_o_url:
        return None

    if ruta_o_url.startswith(("http://", "https://")):
        from api.client import normalizar_url
        ruta_o_url = normalizar_url(ruta_o_url)

    ruta_cache = _ruta_cache(ruta_o_url, size)
    try:
        if os.path.exists(ruta_cache):
            with Image.open(ruta_cache) as cacheada:
                return cacheada.copy()
    except OSError:
        pass

    ext = _extension(ruta_o_url)
    imagen = None
    if ext in EXTENSIONES_IMAGEN:
        if ruta_o_url.startswith(("http://", "https://")):
            imagen = _descargar_imagen(ruta_o_url)
        else:
            try:
                with Image.open(ruta_o_url) as original:
                    original.draft("RGB", (size[0] * 2, size[1] * 2))
                    imagen = ImageOps.exif_transpose(original)
                    imagen.thumbnail((size[0] * 2, size[1] * 2), Image.Resampling.LANCZOS)
            except OSError:
                pass
    elif ext in EXTENSIONES_VIDEO:
        imagen = _primer_cuadro_video(ruta_o_url)

    if imagen is None:
        if not placeholder:
            return None
        # Placeholder visible si un archivo está inaccesible; rojo para video,
        # azul para imagen/otro, de modo que no parezcan miniaturas reales.
        color = "#7f1d1d" if ext in EXTENSIONES_VIDEO else "#1e3a5f"
        # No persistir fallos de red: al volver a abrir con conexión debe
        # intentarse la miniatura real, no un placeholder eterno.
        return Image.new("RGB", size, color=color)
    else:
        imagen = _convertir_a_miniatura(imagen, size)

    _guardar_cache(imagen, ruta_cache)
    return imagen
