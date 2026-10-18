"""Orden de bitácoras y cursor basados en metadatos del servidor, no del PC."""
from datetime import datetime, timezone


def instante_servidor(valor):
    if not valor:
        return None
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        # Nest serializa fechas ISO con Z. Compatibilidad con respuestas UTC sin Z.
        if instante.tzinfo is None:
            instante = instante.replace(tzinfo=timezone.utc)
        return instante.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def clave_orden_bitacora(fila, posicion=0):
    remoto_id = fila.get("b_id") or fila.get("id")
    if remoto_id:
        creado = instante_servidor(fila.get("created_at"))
        return (0, creado or datetime.min.replace(tzinfo=timezone.utc), str(remoto_id))
    # Los pendientes no inventan una fecha del servidor. El ID SQLite mantiene
    # la secuencia local aunque se editen o cambie el reloj; los vacíos van al final.
    local_id = fila.get("local_id")
    return (1, 0 if local_id else 1, local_id or posicion)


def cursor_bitacoras_servidor(registros, anterior=None):
    instantes = [instante_servidor(b.get("updated_at")) for b in registros]
    validos = [dt for dt in instantes if dt is not None]
    if not validos:
        return anterior
    # /since recibe milisegundos con > estricto. Solapar 1 ms evita perder
    # ediciones del mismo milisegundo; la UI ignora deltas sin cambios reales.
    cursor = int(max(validos).timestamp() * 1000) - 1
    return max(anterior, cursor) if anterior is not None else cursor
