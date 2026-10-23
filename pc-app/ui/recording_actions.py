"""Transiciones de captura fuera de Tk; una sola operación por pantalla."""
from queue import Queue, Empty
import threading
from tkinter import messagebox


def excluir_de_captura(window):
    """WDA_EXCLUDEFROMCAPTURE requiere Windows 10 2004+, no sólo WDA_MONITOR.

    https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity
    """
    return _afinidad_ventana(window, 0x11)


def _afinidad_ventana(window, valor):
    try:
        import sys
        import ctypes
        from ctypes import wintypes
        if sys.platform != "win32" or sys.getwindowsversion().build < 19041:
            return False
        api = ctypes.windll.user32
        api.GetParent.argtypes = [wintypes.HWND]
        api.GetParent.restype = wintypes.HWND
        api.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
        api.SetWindowDisplayAffinity.restype = wintypes.BOOL
        hwnd = api.GetParent(window.winfo_id())
        return bool(api.SetWindowDisplayAffinity(hwnd, valor))
    except Exception:
        return False


def proteger_aplicacion(owner):
    if not getattr(owner, "_captura_main_protegida", False):
        owner._captura_main_protegida = excluir_de_captura(owner.controlador)


def restaurar_aplicacion(owner):
    if getattr(owner, "_captura_main_protegida", False):
        _afinidad_ventana(owner.controlador, 0)
        owner._captura_main_protegida = False


def captura_pendiente(owner):
    if getattr(owner, "_transicion_grabacion", False) or getattr(owner, "_procesando_video", False):
        return True
    return getattr(getattr(owner, "grabador", None), "estado", "detenido") != "detenido"


def preparar_salida(owner):
    if captura_pendiente(owner):
        owner._detener_grabacion()
        return False  # Primero adjuntar el video; después se puede salir.
    return True


def restaurar_tras_cierre(owner):
    if getattr(owner, "_captura_main_protegida", False):
        try:
            owner.controlador.after(0, lambda: restaurar_aplicacion(owner))
        except Exception:
            pass  # La ventana principal también puede haberse cerrado.


def ejecutar_transicion(owner, action, success, delay=0):
    if getattr(owner, "_transicion_grabacion", False) or getattr(owner, "_procesando_video", False) or owner._cerrado:
        return
    owner._transicion_grabacion = True
    results = Queue()

    def worker():
        error = None
        try:
            action()
        except Exception as exc:
            error = str(exc)
            try:
                owner.grabador.detener()
            except Exception:
                pass  # No seguir capturando audio tras un fallo de video.
        finally:
            if owner._cerrado:
                try:
                    owner.grabador.detener()
                except Exception:
                    pass  # Archivos de recuperación conservados por el grabador.
                restaurar_tras_cierre(owner)
            results.put(error)

    def recibir():
        if owner._cerrado:
            return
        try:
            error = results.get_nowait()
        except Empty:
            owner.after(40, recibir)
            return
        owner._transicion_grabacion = False
        if error:
            owner._ocultar_indicador_rec()
            restaurar_aplicacion(owner)
            owner.controlador.deiconify()
            owner._actualizar_botones_grabacion()
            messagebox.showerror("No se pudo completar la grabación", error)
        else:
            success()
        if getattr(owner, "_detener_pendiente", False):
            owner._detener_pendiente = False
            owner._detener_grabacion()

    def iniciar():
        if owner._cerrado:
            owner._transicion_grabacion = False
            return
        threading.Thread(target=worker, daemon=True, name="TransicionGrabacion").start()
        owner.after(40, recibir)

    # Permitir que Windows retire la ventana antes de capturar el primer frame.
    owner.after(delay, iniciar)
