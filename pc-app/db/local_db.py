import sqlite3
import os
import re
from datetime import datetime
import contextlib

# ─── Rutas de infraestructura ────────────────────────────────────────────────

# Base de datos SQLite: sigue en AuditFlow_Temp (sin cambio de v2)
RUTA_DB = os.path.join(os.path.expanduser("~"), "AuditFlow_Temp", "borradores.db")

# Raíz del almacenamiento multimedia estructurado (nueva desde v3)
RUTA_DOCS_AUDITFLOW = os.path.join(
    os.path.expanduser("~"), "Documents", "AuditFlow"
)
RUTA_BITACORAS = os.path.join(RUTA_DOCS_AUDITFLOW, "Bitacoras")
RUTA_REPORTES  = os.path.join(RUTA_DOCS_AUDITFLOW, "Reportes")


# ─── Utilidades de rutas ─────────────────────────────────────────────────────

# Caracteres que Windows no permite en nombres de carpetas/archivos
_CHARS_INVALIDOS_WIN = r'[<>:"/\\|?*\x00-\x1f]'

def sanitizar_nombre_carpeta(nombre: str, max_long: int = 120) -> str:
    """
    Convierte un título arbitrario en un nombre de carpeta válido en Windows.

    Pasos:
      1. Reemplaza caracteres inválidos (< > : " / \\ | ? *) por un espacio.
      2. Colapsa espacios múltiples en uno solo.
      3. Elimina espacios al inicio y al final.
      4. Trunca a `max_long` caracteres para no superar el límite de PATH.
      5. Si el resultado queda vacío, devuelve "_sin_nombre_".

    Ejemplo:
      "Riverside (08-25-2026): caso Natalie/dinero"
        → "Riverside (08-25-2026)  caso Natalie dinero"  [paso 1]
        → "Riverside (08-25-2026) caso Natalie dinero"   [paso 2]
    """
    limpio = re.sub(_CHARS_INVALIDOS_WIN, " ", nombre)
    limpio = re.sub(r" {2,}", " ", limpio).strip()
    limpio = limpio[:max_long].rstrip()
    return limpio if limpio else "_sin_nombre_"


def ruta_evidencia_bitacora(fecha_iso: str, nombre_archivo: str) -> str:
    """
    Devuelve la ruta completa donde debe guardarse una evidencia de bitácora.

    Parámetros
    ----------
    fecha_iso    : Fecha en formato YYYY-MM-DD (p. ej. "2026-08-25")
    nombre_archivo: Nombre del archivo con extensión (p. ej. "grabacion.mp4")

    Retorna
    -------
    Ruta absoluta: ~/Documents/AuditFlow/Bitacoras/08-25-2026/grabacion.mp4
    La carpeta se crea automáticamente si no existe.
    """
    # Convertir YYYY-MM-DD → MM-DD-YYYY para que coincida con la estructura visual
    try:
        dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
        nombre_fecha = dt.strftime("%m-%d-%Y")
    except ValueError:
        nombre_fecha = sanitizar_nombre_carpeta(fecha_iso)

    carpeta = os.path.join(RUTA_BITACORAS, nombre_fecha)
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, nombre_archivo)


def ruta_evidencia_reporte(titulo: str, nombre_archivo: str) -> str:
    """
    Devuelve la ruta completa donde debe guardarse una evidencia de un reporte.

    Parámetros
    ----------
    titulo        : Título del reporte tal como lo ingresó el usuario.
    nombre_archivo: Nombre del archivo con extensión.

    Retorna
    -------
    Ruta absoluta:
      ~/Documents/AuditFlow/Reportes/<titulo_sanitizado>/<nombre_archivo>
    La carpeta se crea automáticamente si no existe.
    """
    nombre_carpeta = sanitizar_nombre_carpeta(titulo)
    carpeta = os.path.join(RUTA_REPORTES, nombre_carpeta)
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, nombre_archivo)


def prefijo_nube_bitacora(fecha_iso: str) -> str:
    """
    Devuelve el prefijo de carpeta que se enviará al backend para que MinIO
    guarde el archivo bajo  bitacoras/MM-DD-YYYY/  en lugar de en la raíz.

    Parámetros
    ----------
    fecha_iso : "2026-08-25"

    Retorna
    -------
    "bitacoras/08-25-2026"
    """
    try:
        dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
        nombre_fecha = dt.strftime("%m-%d-%Y")
    except ValueError:
        nombre_fecha = fecha_iso
    return f"bitacoras/{nombre_fecha}"


def prefijo_nube_reporte(titulo: str) -> str:
    """
    Devuelve el prefijo de carpeta para MinIO del reporte dado.

    Parámetros
    ----------
    titulo : "Riverside (08-25-2026) caso Natalie saco dinero de caja"

    Retorna
    -------
    "reportes/Riverside (08-25-2026) caso Natalie saco dinero de caja"
    (sanitizado, máx 120 chars)
    """
    nombre_carpeta = sanitizar_nombre_carpeta(titulo)
    return f"reportes/{nombre_carpeta}"


# ─── Conexión SQLite ──────────────────────────────────────────────────────────

def _conectar():
    """
    Abre una conexión nueva cada vez que se llama. SQLite es distinto a
    MySQL/TypeORM: no mantenemos una conexión persistente abierta durante
    toda la vida de la app, se abre y cierra rápido por operación —
    es liviano y evita problemas de bloqueo de archivo en Windows.
    """
    os.makedirs(os.path.dirname(RUTA_DB), exist_ok=True)
    conn = sqlite3.connect(RUTA_DB, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

@contextlib.contextmanager
def db_session():
    conn = _conectar()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


# ─── Inicialización de tablas ─────────────────────────────────────────────────

def inicializar_db():
    """Crea las tablas si no existen. Se llama una vez al arrancar la app."""
    with db_session() as conexion:

        # ─── Reportes ────────────────────────────────────────────────────────────
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

        # ─── Bitácoras offline ───────────────────────────────────────────────────
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS bitacora_pendiente (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                b_id TEXT DEFAULT '',
                codigo TEXT DEFAULT '',
                restaurante_id TEXT NOT NULL,
                usuario_id TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                fecha TEXT NOT NULL,
                hora TEXT DEFAULT '',
                urgencia TEXT DEFAULT 'low',
                pendiente INTEGER DEFAULT 1,
                actualizado_en TEXT NOT NULL
            )
        """)
        conexion.commit()

        # ─── Migraciones idempotentes ─────────────────────────────────────────
        # SQLite no admite IF NOT EXISTS en ALTER TABLE, así que ignoramos el
        # error "duplicate column name" en bases de datos ya existentes.

        # v2: columnas offline de reporte_borrador
        _migraciones_reporte = [
            "ALTER TABLE reporte_borrador ADD COLUMN titulo TEXT DEFAULT ''",
            "ALTER TABLE reporte_borrador ADD COLUMN reporte_remoto_id TEXT DEFAULT ''",
            "ALTER TABLE reporte_borrador ADD COLUMN pendiente INTEGER DEFAULT 0",
        ]
        for sql in _migraciones_reporte:
            try:
                conexion.execute(sql)
            except Exception:
                pass  # columna ya existe — ignorar

        # v3: carpeta_destino en evidencia_borrador (para que AdminFrame sepa dónde buscar)
        _migraciones_evidencia = [
            "ALTER TABLE evidencia_borrador ADD COLUMN carpeta_destino TEXT DEFAULT ''",
        ]
        for sql in _migraciones_evidencia:
            try:
                conexion.execute(sql)
            except Exception:
                pass  # columna ya existe — ignorar

        conexion.commit()


# ─── Reportes ──────────────────────────────────────────────────────────────────

def obtener_o_crear_borrador(usuario_id: str, restaurante_id: str) -> dict:
    """
    Busca si ya existe un borrador de HOY para este usuario+restaurante.
    Si existe, lo regresa. Si no, crea uno vacío y lo regresa.
    Esto es lo que permite cerrar la app a medio reporte y que al volver
    a abrir, continúe donde quedó.
    """
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    with db_session() as conexion:

        fila = conexion.execute(
            """SELECT * FROM reporte_borrador
               WHERE usuario_id = ? AND restaurante_id = ? AND fecha_jornada = ?""",
            (usuario_id, restaurante_id, fecha_hoy),
        ).fetchone()

        if fila:
            return dict(fila)

        cursor = conexion.execute(
            """INSERT INTO reporte_borrador (usuario_id, restaurante_id, notas_finales, fecha_jornada, actualizado_en)
               VALUES (?, ?, '', ?, ?)""",
            (usuario_id, restaurante_id, fecha_hoy, datetime.now().isoformat()),
        )
        conexion.commit()

        nuevo_id = cursor.lastrowid

        return {
            "id": nuevo_id,
            "usuario_id": usuario_id,
            "restaurante_id": restaurante_id,
            "notas_finales": "",
            "fecha_jornada": fecha_hoy,
            "actualizado_en": datetime.now().isoformat(),
        }


def actualizar_notas(borrador_id: int, notas: str, marcar_pendiente: bool = False):
    """
    Autoguardado del texto — se llama con debounce desde la UI.

    Si marcar_pendiente=True, también activa el flag de sincronización
    pendiente (usado cuando el backend no estuvo disponible al guardar).
    """
    with db_session() as conexion:
        if marcar_pendiente:
            conexion.execute(
                "UPDATE reporte_borrador SET notas_finales = ?, pendiente = 1, actualizado_en = ? WHERE id = ?",
                (notas, datetime.now().isoformat(), borrador_id),
            )
        else:
            conexion.execute(
                "UPDATE reporte_borrador SET notas_finales = ?, actualizado_en = ? WHERE id = ?",
                (notas, datetime.now().isoformat(), borrador_id),
            )
        conexion.commit()


def agregar_evidencia(
    borrador_id: int,
    ruta_local: str,
    con_audio: bool,
    carpeta_destino: str = "",
):
    """
    Registra una evidencia en la cola local.

    Parámetros
    ----------
    borrador_id     : ID del borrador al que pertenece.
    ruta_local      : Ruta absoluta del archivo en disco.
    con_audio       : True si el archivo fue grabado con audio.
    carpeta_destino : Subcarpeta relativa dentro de AuditFlow/ donde se guardó
                      el archivo (p. ej. "Reportes/Riverside (08-25-2026)...").
                      Usado por AdminFrame para navegar los archivos.
    """
    with db_session() as conexion:

        # El siguiente número de orden es "cuántas evidencias ya tiene, + 1"
        cantidad = conexion.execute(
            "SELECT COUNT(*) as total FROM evidencia_borrador WHERE reporte_borrador_id = ?",
            (borrador_id,),
        ).fetchone()["total"]

        conexion.execute(
            """INSERT INTO evidencia_borrador
               (reporte_borrador_id, ruta_local, con_audio, orden_reproduccion, carpeta_destino)
               VALUES (?, ?, ?, ?, ?)""",
            (borrador_id, ruta_local, int(con_audio), cantidad + 1, carpeta_destino),
        )
        conexion.commit()


def obtener_evidencias(borrador_id: int) -> list[dict]:
    with db_session() as conexion:
        filas = conexion.execute(
            "SELECT * FROM evidencia_borrador WHERE reporte_borrador_id = ? ORDER BY orden_reproduccion",
            (borrador_id,),
        ).fetchall()
        return [dict(f) for f in filas]


def eliminar_borrador_completo(borrador_id: int):
    """Se llama SOLO después de que el reporte se envió exitosamente al backend."""
    with db_session() as conexion:
        conexion.execute("DELETE FROM evidencia_borrador WHERE reporte_borrador_id = ?", (borrador_id,))
        conexion.execute("DELETE FROM reporte_borrador WHERE id = ?", (borrador_id,))
        conexion.commit()


def eliminar_borrador_y_archivos(borrador_id: int, eliminar_grabaciones: bool = True):
    """
    Elimina el borrador de la base de datos Y opcionalmente borra del disco
    los archivos de evidencia que fueron generados por el grabador de pantalla
    (es decir, archivos temporales en AuditFlow_Temp, NO los de la nueva
    estructura ~/Documents/AuditFlow/ que son permanentes).

    Usado por AdminFrame cuando el usuario elige eliminar un reporte local.

    Parámetros
    ----------
    borrador_id          : ID del borrador a eliminar.
    eliminar_grabaciones : Si True, intenta borrar del disco los archivos
                           cuya ruta apunte a AuditFlow_Temp (grabaciones temp).
                           Los archivos en ~/Documents/AuditFlow/ los gestiona
                           el AdminFrame directamente.
    """
    from core.recorder import es_archivo_grabado

    evidencias = obtener_evidencias(borrador_id)

    if eliminar_grabaciones:
        for ev in evidencias:
            ruta = ev.get("ruta_local", "")
            if ruta and es_archivo_grabado(ruta) and os.path.exists(ruta):
                try:
                    os.remove(ruta)
                except OSError:
                    pass  # Si no se puede borrar (bloqueado, etc.) seguimos

    with db_session() as conexion:
        conexion.execute("DELETE FROM evidencia_borrador WHERE reporte_borrador_id = ?", (borrador_id,))
        conexion.execute("DELETE FROM reporte_borrador WHERE id = ?", (borrador_id,))
        conexion.commit()


# ─── Reportes offline ─────────────────────────────────────────────────────────

def marcar_reporte_pendiente(
    borrador_id: int,
    titulo: str,
    usuario_id: str,
    restaurante_id: str,
) -> None:
    """
    Marca el borrador como pendiente de creación en el backend.
    Se llama cuando crear_reporte() falla (sin conexión) para que
    el polling_worker lo reintente más tarde.
    """
    with db_session() as conexion:
        conexion.execute(
            """UPDATE reporte_borrador
               SET titulo=?, usuario_id=?, restaurante_id=?, pendiente=1, actualizado_en=?
               WHERE id=?""",
            (titulo, usuario_id, restaurante_id, datetime.now().isoformat(), borrador_id),
        )
        conexion.commit()


def marcar_reporte_sincronizado(borrador_id: int, reporte_remoto_id: str) -> None:
    """
    Guarda el UUID remoto asignado por el backend y limpia el flag pendiente.
    Se llama una vez que crear_reporte() o actualizar_reporte() tuvo éxito.
    """
    with db_session() as conexion:
        conexion.execute(
            "UPDATE reporte_borrador SET reporte_remoto_id=?, pendiente=0, actualizado_en=? WHERE id=?",
            (reporte_remoto_id, datetime.now().isoformat(), borrador_id),
        )
        conexion.commit()


def marcar_notas_pendientes(borrador_id: int) -> None:
    """
    Activa el flag de sincronización sin cambiar el texto ni los metadatos.
    Se llama cuando actualizar_reporte() falla (el reporte ya existe en el
    backend pero no se pudo enviar el texto nuevo).
    """
    with db_session() as conexion:
        conexion.execute(
            "UPDATE reporte_borrador SET pendiente=1, actualizado_en=? WHERE id=?",
            (datetime.now().isoformat(), borrador_id),
        )
        conexion.commit()


def obtener_borrador_completo(borrador_id: int) -> dict | None:
    """
    Devuelve todos los campos del borrador (incluidos los nuevos de offline)
    o None si no existe.
    """
    with db_session() as conexion:
        fila = conexion.execute(
            "SELECT * FROM reporte_borrador WHERE id=?", (borrador_id,)
        ).fetchone()
        return dict(fila) if fila else None

def obtener_reportes_pendientes() -> list[dict]:
    """
    Devuelve todos los borradores de reportes guardados localmente.
    Esto permite listarlos en el Administrador y en la UI de reportes.
    """
    with db_session() as conexion:
        filas = conexion.execute(
            "SELECT * FROM reporte_borrador ORDER BY actualizado_en DESC"
        ).fetchall()
    
        # Marcamos cada uno con 'es_borrador_local' = True para que la UI 
        # sepa que es un borrador.
        resultados = []
        for f in filas:
            d = dict(f)
            d["es_borrador_local"] = True
            d["borrador_id"] = d["id"]
            resultados.append(d)
        
        return resultados

def listar_borradores_activos() -> list[dict]:
    """
    Devuelve todos los borradores que existen en SQLite, ordenados por
    fecha de actualización descendente. Usado por ReportesFrame para
    mostrar la lista de reportes locales en progreso.
    """
    with db_session() as conexion:
        filas = conexion.execute(
            "SELECT * FROM reporte_borrador ORDER BY actualizado_en DESC"
        ).fetchall()
        return [dict(f) for f in filas]


# ─── Bitácoras offline ─────────────────────────────────────────────────────────

def guardar_bitacora_local(datos: dict) -> int:
    """
    Guarda o actualiza un registro de bitácora en la cola local.
    Si `datos` contiene `local_id`, actualiza ese registro.
    Si no, inserta uno nuevo y devuelve su rowid.

    Esta función es el primer paso de todo guardado — se llama siempre,
    incluso cuando hay conexión, para garantizar durabilidad ante cortes.
    """
    with db_session() as conexion:
        ahora = datetime.now().isoformat()
        local_id = datos.get("local_id")

        if local_id:
            conexion.execute(
                """UPDATE bitacora_pendiente
                   SET b_id=?, codigo=?, restaurante_id=?, usuario_id=?,
                       descripcion=?, fecha=?, hora=?, urgencia=?,
                       pendiente=1, actualizado_en=?
                   WHERE id=?""",
                (
                    datos.get("b_id", ""),
                    datos.get("codigo", ""),
                    datos["restaurante_id"],
                    datos["usuario_id"],
                    datos.get("descripcion", ""),
                    datos["fecha"],
                    datos.get("hora", ""),
                    datos.get("urgencia", "low"),
                    ahora,
                    local_id,
                ),
            )
            conexion.commit()
            return local_id

        cursor = conexion.execute(
            """INSERT INTO bitacora_pendiente
               (b_id, codigo, restaurante_id, usuario_id, descripcion, fecha, hora, urgencia, pendiente, actualizado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                datos.get("b_id", ""),
                datos.get("codigo", ""),
                datos["restaurante_id"],
                datos["usuario_id"],
                datos.get("descripcion", ""),
                datos["fecha"],
                datos.get("hora", ""),
                datos.get("urgencia", "low"),
                ahora,
            ),
        )
        conexion.commit()
        nuevo_id = cursor.lastrowid
        return nuevo_id


def marcar_bitacora_sincronizada(local_id: int, b_id: str, codigo: str):
    """
    Se llama cuando el backend confirmó el guardado.
    Guarda el UUID y el código definitivos del servidor,
    y marca el registro como no-pendiente.
    """
    with db_session() as conexion:
        conexion.execute(
            "UPDATE bitacora_pendiente SET b_id=?, codigo=?, pendiente=0 WHERE id=?",
            (b_id, codigo, local_id),
        )
        conexion.commit()


def obtener_bitacoras_pendientes() -> list[dict]:
    """
    Devuelve todos los registros que aún no se han sincronizado con el backend.
    El `_polling_worker` los recorre para intentar subirlos.
    """
    with db_session() as conexion:
        filas = conexion.execute(
            "SELECT * FROM bitacora_pendiente WHERE pendiente=1 ORDER BY actualizado_en"
        ).fetchall()
        return [dict(f) for f in filas]


def borrar_bitacora_local(local_id: int):
    """Se puede llamar para limpiar registros ya sincronizados muy viejos."""
    with db_session() as conexion:
        conexion.execute("DELETE FROM bitacora_pendiente WHERE id=?", (local_id,))
        conexion.commit()
