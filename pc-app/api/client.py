import requests
import os
import mimetypes
import json

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:3000")
CACHE_PATH = os.path.join(os.path.expanduser("~"), "AuditFlow_Temp", "cache.json")

def _guardar_cache(llave, datos):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
        else:
            cache = {}
        cache[llave] = datos
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass

def _leer_cache(llave):
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
                return cache.get(llave, [])
    except Exception:
        pass
    return []


# ─── Catálogos ────────────────────────────────────────────────────────────────

def obtener_usuarios():
    """Trae la lista de usuarios activos desde el backend con soporte OFFLINE."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/usuarios",
            timeout=3
        )
        response.raise_for_status()
        data = response.json()
        _guardar_cache("usuarios", data)
        return data
    except requests.exceptions.RequestException as e:
        print(f"Servidor inaccesible, cargando usuarios desde caché local.")
        return _leer_cache("usuarios")


def obtener_restaurantes():
    """Trae la lista de restaurantes desde el backend con soporte OFFLINE."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/restaurantes",
            timeout=3
        )
        response.raise_for_status()
        data = response.json()
        _guardar_cache("restaurantes", data)
        return data
    except requests.exceptions.RequestException as e:
        print(f"Servidor inaccesible, cargando restaurantes desde caché local.")
        return _leer_cache("restaurantes")


def crear_usuario(dto: dict) -> dict | None:
    """
    Crea un nuevo usuario en el backend.

    Parámetros
    ----------
    dto : dict con al menos {"nombre": str}

    Retorna
    -------
    El objeto usuario creado por el backend, o None si hubo error.
    """
    try:
        response = requests.post(
            f"{API_BASE_URL}/usuarios",
            json=dto,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al crear usuario: {e}")
        if getattr(e, "response", None) is not None:
            print(f"Respuesta del servidor: {e.response.text}")
        return None


def crear_restaurante(dto: dict) -> dict | None:
    """
    Crea un nuevo restaurante en el backend.

    Parámetros
    ----------
    dto : dict con al menos {"nombre": str}

    Retorna
    -------
    El objeto restaurante creado por el backend, o None si hubo error.
    """
    try:
        response = requests.post(
            f"{API_BASE_URL}/restaurantes",
            json=dto,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al crear restaurante: {e}")
        if getattr(e, "response", None) is not None:
            print(f"Respuesta del servidor: {e.response.text}")
        return None


# ─── Bitácoras ────────────────────────────────────────────────────────────────

def crear_bitacora(dto):
    """Crea una nueva bitácora en el backend."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/bitacoras",
            json=dto,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al crear bitácora: {e}")
        if getattr(e, "response", None) is not None:
            print(f"Respuesta del servidor: {e.response.text}")
        return None


def actualizar_bitacora(id: str, dto: dict):
    """Actualiza una bitácora en el backend."""
    try:
        response = requests.patch(
            f"{API_BASE_URL}/bitacoras/{id}",
            json=dto,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al actualizar bitácora: {e}")
        if getattr(e, "response", None) is not None:
            print(f"Respuesta del servidor: {e.response.text}")
        return None


def eliminar_bitacora_remota(b_id: str) -> bool:
    """
    Elimina una bitácora del backend (y sus evidencias de MinIO vía cascade
    configurado en el servicio NestJS).

    Parámetros
    ----------
    b_id : UUID de la bitácora en el backend.

    Retorna
    -------
    True si el DELETE tuvo éxito (2xx), False si hubo error.
    """
    try:
        response = requests.delete(
            f"{API_BASE_URL}/bitacoras/{b_id}",
            timeout=10
        )
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"[eliminar_bitacora] Error al eliminar {b_id}: {e}")
        if getattr(e, "response", None) is not None:
            print(f"Respuesta del servidor: {e.response.text}")
        return False


def obtener_evidencias_bitacora(codigo: str) -> list:
    """
    Devuelve la lista fresca de evidencias de una bitácora usando su
    código corto (6 chars). Llama directamente al backend — no usa caché.
    Regresa [] si hay error de red o el código no existe.
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/bitacoras/codigo/{codigo}/evidencias",
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[evidencias] Error al obtener evidencias del código {codigo}: {e}")
        return []


def cerrar_bitacora_dia(fecha: str) -> dict | None:
    """
    Cierra todas las bitácoras abiertas de una fecha (formato YYYY-MM-DD).
    Retorna { 'cerradas': <int> } si tuvo éxito, o None si hubo error.
    """
    try:
        response = requests.patch(
            f"{API_BASE_URL}/bitacoras/fecha/{fecha}/cerrar",
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[cerrar_dia] Error al cerrar bitácoras de {fecha}: {e}")
        if getattr(e, "response", None) is not None:
            print(f"Respuesta del servidor: {e.response.text}")
        return None


def obtener_bitacoras_por_fecha(fecha: str):
    """
    Trae todas las bitácoras de una fecha específica (formato YYYY-MM-DD).
    Utilizado para actualizar la cuadrícula general.
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/bitacoras/fecha/{fecha}",
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener bitácoras para la fecha {fecha}: {e}")
        return []


def obtener_bitacoras_todas():
    """
    Trae todas las bitácoras almacenadas en el backend (ordenadas por fecha descendente).
    Utilizado por el Administrador para agrupar y mostrar las carpetas por fecha.
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/bitacoras",
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener todas las bitácoras: {e}")
        return []


def adjuntar_evidencia_por_codigo(codigo: str, evidencia_url: str, con_audio: bool):
    """
    Vincula una evidencia a una bitácora existente usando el código corto.
    Retorna (data, error) para facilitar el manejo en la UI.
    """
    try:
        payload = {
            "evidencia_url": evidencia_url,
            "con_audio": con_audio
        }
        response = requests.patch(
            f"{API_BASE_URL}/bitacoras/codigo/{codigo}/evidencia",
            json=payload,
            timeout=10
        )

        # Si el código no existe, capturar el 404 explícitamente para la UI
        if response.status_code == 404:
            return None, f"El código '{codigo}' no existe o ya expiró."

        response.raise_for_status()
        return response.json(), None

    except requests.exceptions.RequestException as e:
        print(f"Error de red al adjuntar evidencia al código {codigo}: {e}")
        return None, f"Error de comunicación con el servidor."


# ─── Uploads / Evidencias ─────────────────────────────────────────────────────

def subir_archivo(ruta_local: str) -> tuple[str | None, str | None]:
    """
    Sube un archivo al endpoint /uploads (sin prefijo de carpeta).
    Regresa una tupla: (url, error).

    Compatibilidad hacia atrás: la firma anterior no tenía prefijo_nube.
    Para subir con prefijo de carpeta usa `subir_archivo_con_destino()`.
    """
    return subir_archivo_con_destino(ruta_local, prefijo_nube=None)


def subir_archivo_con_destino(
    ruta_local: str,
    prefijo_nube: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Sube un archivo al endpoint /uploads y le indica al backend en qué
    subcarpeta de MinIO debe guardarlo.

    Parámetros
    ----------
    ruta_local   : Ruta absoluta del archivo en disco local.
    prefijo_nube : Prefijo de carpeta en MinIO, sin slash al final.
                   Ejemplos:
                     "bitacoras/08-25-2026"
                     "reportes/Riverside (08-25-2026) caso Natalie"
                   Si es None o vacío, el backend usa la raíz del bucket
                   (comportamiento legado).

    Retorna
    -------
    (url_publica, None)     → éxito
    (None, mensaje_error)   → fallo
    """
    try:
        nombre_archivo = os.path.basename(ruta_local)
        tipo_mime, _ = mimetypes.guess_type(ruta_local)
        tipo_mime = tipo_mime or "application/octet-stream"

        with open(ruta_local, "rb") as f:
            files = {"file": (nombre_archivo, f, tipo_mime)}
            data  = {}
            if prefijo_nube:
                data["prefijo_nube"] = prefijo_nube

            response = requests.post(
                f"{API_BASE_URL}/uploads",
                files=files,
                data=data,
                timeout=60,
            )
            response.raise_for_status()
            return response.json().get("evidencia_url"), None

    except Exception as e:
        mensaje_error = f"{type(e).__name__}: {e}"
        print(f"Error al subir '{ruta_local}': {mensaje_error}", flush=True)
        return None, mensaje_error


# ─── Reportes ─────────────────────────────────────────────────────────────────

def obtener_reportes():
    """Trae la lista de todos los reportes desde el backend."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/reportes",
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener reportes: {e}")
        return []


def crear_reporte(dto: dict):
    try:
        response = requests.post(f"{API_BASE_URL}/reportes", json=dto, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al crear reporte: {e}")
        return None


def actualizar_reporte(reporte_id: str, notas_finales: str):
    """
    Actualiza las notas finales de un reporte existente.
    """
    try:
        response = requests.patch(
            f"{API_BASE_URL}/reportes/{reporte_id}",
            json={"notas_finales": notas_finales},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al actualizar reporte: {e}")
        return None


def renombrar_reporte_remoto(reporte_id: str, nuevo_titulo: str) -> dict | None:
    """
    Cambia el título de un reporte en el backend.

    Parámetros
    ----------
    reporte_id   : UUID del reporte en el backend.
    nuevo_titulo : Nuevo título limpio ingresado por el usuario.

    Retorna
    -------
    El reporte actualizado, o None si hubo error.
    """
    try:
        response = requests.patch(
            f"{API_BASE_URL}/reportes/{reporte_id}",
            json={"titulo": nuevo_titulo},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[renombrar_reporte] Error al renombrar {reporte_id}: {e}")
        if getattr(e, "response", None) is not None:
            print(f"Respuesta del servidor: {e.response.text}")
        return None


def eliminar_reporte_remoto(reporte_id: str) -> bool:
    """
    Elimina un reporte del backend.
    El servicio NestJS se encarga de borrar también las evidencias
    asociadas de la base de datos. El cliente Python elimina los
    archivos locales de forma independiente.

    Parámetros
    ----------
    reporte_id : UUID del reporte en el backend.

    Retorna
    -------
    True si el DELETE tuvo éxito (2xx), False si hubo error.
    """
    try:
        response = requests.delete(
            f"{API_BASE_URL}/reportes/{reporte_id}",
            timeout=10
        )
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"[eliminar_reporte] Error al eliminar {reporte_id}: {e}")
        if getattr(e, "response", None) is not None:
            print(f"Respuesta del servidor: {e.response.text}")
        return False


def crear_evidencia_reporte(dto: dict):
    try:
        response = requests.post(f"{API_BASE_URL}/evidencias-reporte", json=dto, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al crear evidencia de reporte: {e}")
        return None