"""Generación y caché local de previsualizaciones ligeras para evidencias."""

import hashlib
import io
import os
from urllib.parse import urlparse

from PIL import Image, ImageOps
import requests

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


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
    clave = hashlib.sha256(f"{ruta_o_url}|{size}".encode("utf-8")).hexdigest()
    os.makedirs(CARPETA_MINIATURAS, exist_ok=True)
    return os.path.join(CARPETA_MINIATURAS, f"{clave}.jpg")


def _convertir_a_miniatura(imagen: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Devuelve una imagen RGB de tamaño fijo y calidad económica para la UI."""
    imagen = ImageOps.exif_transpose(imagen).convert("RGB")
    return ImageOps.pad(imagen, size, method=Image.Resampling.LANCZOS, color="#1e293b")


def _guardar_cache(imagen: Image.Image, ruta_cache: str) -> None:
    try:
        imagen.save(ruta_cache, "JPEG", quality=CALIDAD_JPEG, optimize=True)
    except OSError:
        pass


def _descargar_imagen(url: str) -> Image.Image | None:
    """Descarga sólo imágenes; evita una descarga no limitada por error."""
    try:
        from api.client import normalizar_url

        respuesta = requests.get(normalizar_url(url), stream=True, timeout=(3, 10))
        respuesta.raise_for_status()
        limite = 15 * 1024 * 1024
        datos = bytearray()
        for bloque in respuesta.iter_content(chunk_size=65536):
            datos.extend(bloque)
            if len(datos) > limite:
                return None
        with Image.open(io.BytesIO(datos)) as imagen:
            return imagen.copy()
    except Exception:
        return None


def _primer_cuadro_video(ruta_o_url: str) -> Image.Image | None:
    if not CV2_AVAILABLE:
        return None

    fuente = ruta_o_url
    if ruta_o_url.startswith(("http://", "https://")):
        try:
            from api.client import normalizar_url
            fuente = normalizar_url(ruta_o_url)
        except Exception:
            pass

    cap = cv2.VideoCapture(fuente)
    try:
        exito, frame = cap.read()
        if exito:
            return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    except Exception:
        pass
    finally:
        cap.release()
    return None


def generar_miniatura(ruta_o_url: str, size=TAMANIO_CACHE) -> Image.Image | None:
    """Obtiene una miniatura cacheada de imagen/video sin bloquear la interfaz.

    Las miniaturas se guardan como JPEG de baja calidad en AppData y las llamadas
    siguientes no descargan ni decodifican otra vez la evidencia completa.
    """
    if not ruta_o_url:
        return None

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
                    imagen = original.copy()
            except OSError:
                pass
    elif ext in EXTENSIONES_VIDEO:
        imagen = _primer_cuadro_video(ruta_o_url)

    if imagen is None:
        # Placeholder visible si un archivo está inaccesible; rojo para video,
        # azul para imagen/otro, de modo que no parezcan miniaturas reales.
        color = "#7f1d1d" if ext in EXTENSIONES_VIDEO else "#1e3a5f"
        imagen = Image.new("RGB", size, color=color)
    else:
        imagen = _convertir_a_miniatura(imagen, size)

    _guardar_cache(imagen, ruta_cache)
    return imagen
