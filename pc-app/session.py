"""
Gestor de sesión global (Singleton en memoria).
Se limpia al cerrar la aplicación.
"""

_sesion: dict | None = None


def set_session(data: dict) -> None:
    """Guarda el perfil del usuario logueado."""
    global _sesion
    _sesion = data


def get_session() -> dict | None:
    """Retorna el perfil activo o None si no hay sesión."""
    return _sesion


def get_role() -> str | None:
    """Retorna el rol del usuario activo ('ADMIN', 'EMPLEADO') o None."""
    if _sesion:
        return _sesion.get("role")
    return None


def get_nombre() -> str:
    """Retorna el nombre del usuario activo."""
    if _sesion:
        return _sesion.get("nombre", "Usuario")
    return "Usuario"


def clear_session() -> None:
    """Limpia la sesión activa (logout)."""
    global _sesion
    _sesion = None
