import sqlite3
import os
from datetime import datetime

RUTA_DB = os.path.join(os.path.expanduser("~"), "AuditFlow_Temp", "borradores.db")


def _conectar():
    """
    Abre una conexión nueva cada vez que se llama. SQLite es distinto a
    MySQL/TypeORM: no mantenemos una conexión persistente abierta durante
    toda la vida de la app, se abre y cierra rápido por operación —
    es liviano y evita problemas de bloqueo de archivo en Windows.
    """
    conexion = sqlite3.connect(RUTA_DB)
    conexion.row_factory = sqlite3.Row  # permite acceder a columnas por nombre, no solo índice
    return conexion


def inicializar_db():
    """Crea las tablas si no existen. Se llama una vez al arrancar la app."""
    conexion = _conectar()
    conexion.execute("""
        CREATE TABLE IF NOT EXISTS reporte_borrador (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT NOT NULL,
            restaurante_id TEXT NOT NULL,
            notas_finales TEXT DEFAULT '',
            fecha_jornada TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        )
    """)
    conexion.execute("""
        CREATE TABLE IF NOT EXISTS evidencia_borrador (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporte_borrador_id INTEGER NOT NULL,
            ruta_local TEXT NOT NULL,
            con_audio INTEGER DEFAULT 0,
            orden_reproduccion INTEGER NOT NULL,
            FOREIGN KEY (reporte_borrador_id) REFERENCES reporte_borrador(id)
        )
    """)
    conexion.commit()
    conexion.close()


def obtener_o_crear_borrador(usuario_id: str, restaurante_id: str) -> dict:
    """
    Busca si ya existe un borrador de HOY para este usuario+restaurante.
    Si existe, lo regresa. Si no, crea uno vacío y lo regresa.
    Esto es lo que permite cerrar la app a medio reporte y que al volver
    a abrir, continúe donde quedó.
    """
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    conexion = _conectar()

    fila = conexion.execute(
        """SELECT * FROM reporte_borrador
           WHERE usuario_id = ? AND restaurante_id = ? AND fecha_jornada = ?""",
        (usuario_id, restaurante_id, fecha_hoy),
    ).fetchone()

    if fila:
        conexion.close()
        return dict(fila)

    cursor = conexion.execute(
        """INSERT INTO reporte_borrador (usuario_id, restaurante_id, notas_finales, fecha_jornada, actualizado_en)
           VALUES (?, ?, '', ?, ?)""",
        (usuario_id, restaurante_id, fecha_hoy, datetime.now().isoformat()),
    )
    conexion.commit()

    nuevo_id = cursor.lastrowid
    conexion.close()

    return {
        "id": nuevo_id,
        "usuario_id": usuario_id,
        "restaurante_id": restaurante_id,
        "notas_finales": "",
        "fecha_jornada": fecha_hoy,
        "actualizado_en": datetime.now().isoformat(),
    }


def actualizar_notas(borrador_id: int, notas: str):
    """Autoguardado del texto — se llama con debounce desde la UI."""
    conexion = _conectar()
    conexion.execute(
        "UPDATE reporte_borrador SET notas_finales = ?, actualizado_en = ? WHERE id = ?",
        (notas, datetime.now().isoformat(), borrador_id),
    )
    conexion.commit()
    conexion.close()


def agregar_evidencia(borrador_id: int, ruta_local: str, con_audio: bool):
    conexion = _conectar()

    # El siguiente número de orden es "cuántas evidencias ya tiene, + 1"
    cantidad = conexion.execute(
        "SELECT COUNT(*) as total FROM evidencia_borrador WHERE reporte_borrador_id = ?",
        (borrador_id,),
    ).fetchone()["total"]

    conexion.execute(
        """INSERT INTO evidencia_borrador (reporte_borrador_id, ruta_local, con_audio, orden_reproduccion)
           VALUES (?, ?, ?, ?)""",
        (borrador_id, ruta_local, int(con_audio), cantidad + 1),
    )
    conexion.commit()
    conexion.close()


def obtener_evidencias(borrador_id: int) -> list[dict]:
    conexion = _conectar()
    filas = conexion.execute(
        "SELECT * FROM evidencia_borrador WHERE reporte_borrador_id = ? ORDER BY orden_reproduccion",
        (borrador_id,),
    ).fetchall()
    conexion.close()
    return [dict(f) for f in filas]


def eliminar_borrador_completo(borrador_id: int):
    """Se llama SOLO después de que el reporte se envió exitosamente al backend."""
    conexion = _conectar()
    conexion.execute("DELETE FROM evidencia_borrador WHERE reporte_borrador_id = ?", (borrador_id,))
    conexion.execute("DELETE FROM reporte_borrador WHERE id = ?", (borrador_id,))
    conexion.commit()
    conexion.close()