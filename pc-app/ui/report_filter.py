"""Búsqueda de reportes en memoria; no consulta API ni altera los registros."""
import unicodedata

TODOS_RESTAURANTES = "Todos los restaurantes"


def normalizar_busqueda(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "").casefold())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


def nombre_restaurante_reporte(reporte, catalogo):
    relacion = reporte.get("restaurante")
    nombre = relacion.get("nombre") if isinstance(relacion, dict) else relacion
    nombre = nombre or reporte.get("restaurante_nombre")
    if isinstance(nombre, str) and nombre.strip():
        return nombre.strip()
    restaurante_id = reporte.get("restaurante_id")
    if not restaurante_id and isinstance(relacion, dict):
        restaurante_id = relacion.get("id")
    nombre = catalogo.get(restaurante_id) or catalogo.get(str(restaurante_id))
    return str(nombre or "").strip() or "Restaurante no disponible"


def filtrar_reportes_admin(reportes, nombre, restaurante, catalogo):
    """reportes contiene pares (registro, es_local); ambos criterios son AND."""
    palabras = normalizar_busqueda(nombre).split()
    restaurante = normalizar_busqueda(restaurante)
    todos = not restaurante or restaurante == normalizar_busqueda(TODOS_RESTAURANTES)
    resultado = []
    for reporte, es_local in reportes:
        titulo = normalizar_busqueda(reporte.get("titulo") or "Sin título")
        if not all(palabra in titulo for palabra in palabras):
            continue
        if not todos and normalizar_busqueda(nombre_restaurante_reporte(reporte, catalogo)) != restaurante:
            continue
        resultado.append((reporte, es_local))
    return resultado
