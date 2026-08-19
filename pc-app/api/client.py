import requests
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:3000")


def obtener_usuarios():
    """Trae la lista de usuarios activos desde el backend."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/usuarios",
            timeout=5
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error al obtener usuarios: {e}")
        return []


def obtener_restaurantes():
    """Trae la lista de restaurantes desde el backend."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/restaurantes",
            timeout=5
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error al obtener restaurantes: {e}")
        return []


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


def subir_archivo(ruta_local: str):
    """
    Sube un archivo al endpoint /uploads. Regresa una tupla:
    (url, error) — si tuvo éxito, error es None; si falló, url es None
    y error trae el mensaje real, para poder mostrarlo en la UI sin
    depender de revisar la consola.
    """
    try:
        with open(ruta_local, "rb") as archivo:
            files = {"file": archivo}
            response = requests.post(f"{API_BASE_URL}/uploads", files=files, timeout=60)
            response.raise_for_status()
            return response.json().get("evidencia_url"), None
    except Exception as e:
        # Exception genérico a propósito: captura también errores que
        # NO son de red, como el archivo no existir, permisos, etc.
        # (antes solo capturábamos requests.exceptions.RequestException,
        # que se queda callado ante estos otros casos)
        mensaje_error = f"{type(e).__name__}: {e}"
        print(f"Error al subir '{ruta_local}': {mensaje_error}", flush=True)
        return None, mensaje_error


def crear_reporte(dto: dict):
    try:
        response = requests.post(f"{API_BASE_URL}/reportes", json=dto, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al crear reporte: {e}")
        return None


def crear_evidencia_reporte(dto: dict):
    try:
        response = requests.post(f"{API_BASE_URL}/evidencias-reporte", json=dto, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al crear evidencia de reporte: {e}")
        return None