"""Registro acotado de excepciones y stacks cuando la interfaz deja de latir."""
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
import time


def instalar_diagnostico(app, directory=None, timeout=15):
    stop = threading.Event()
    try:
        folder = Path(directory) if directory is not None else Path(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "AuditFlow" / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / "application.log", maxBytes=1024 * 1024,
                                      backupCount=2, encoding="utf-8")
    except OSError:
        return lambda: None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"))
    logger = logging.getLogger("AuditFlow")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    previous_sys = sys.excepthook
    previous_thread = threading.excepthook
    previous_tk = app.report_callback_exception

    registrando = threading.local()

    def error(tipo, valor, tb):
        if getattr(registrando, "activo", False):
            return
        registrando.activo = True
        try:
            logger.error("Excepción no controlada", exc_info=(tipo, valor, tb))
        except Exception:
            # También puede fallar logging si Tk ya agotó la pila. No lanzar
            # otra excepción desde report_callback_exception hacia mainloop.
            try:
                os.write(2, b"AuditFlow: no se pudo registrar una excepcion de interfaz.\n")
            except Exception:
                pass
        finally:
            registrando.activo = False

    sys.excepthook = error
    threading.excepthook = lambda args: error(args.exc_type, args.exc_value, args.exc_traceback)
    app.report_callback_exception = error
    estado = {"latido": time.monotonic(), "timer": None}

    def latido():
        if not stop.is_set():
            estado["latido"] = time.monotonic()
            estado["timer"] = app.after(1000, latido)

    def vigilar():
        avisado = False
        while not stop.wait(min(5, timeout)):
            if time.monotonic() - estado["latido"] < timeout:
                avisado = False
                continue
            if avisado:
                continue
            avisado = True
            logger.warning("La interfaz lleva más de %ss sin responder; guardando stacks en hang.log", timeout)
            try:
                path = folder / "hang.log"
                if path.exists() and path.stat().st_size > 1024 * 1024:
                    os.replace(path, folder / "hang.previous.log")
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(f"\nInterfaz sin respuesta: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    stream.flush()
                    faulthandler.dump_traceback(file=stream, all_threads=True)
            except (OSError, RuntimeError):
                logger.exception("No se pudo registrar el stack")

    latido()
    threading.Thread(target=vigilar, daemon=True, name="DiagnosticoUI").start()
    logger.info("Diagnóstico de interfaz iniciado")

    def cerrar():
        stop.set()
        if estado["timer"] is not None:
            try:
                app.after_cancel(estado["timer"])
            except Exception:
                pass  # mainloop puede haber terminado después de destroy().
        sys.excepthook = previous_sys
        threading.excepthook = previous_thread
        app.report_callback_exception = previous_tk
        logger.removeHandler(handler)
        handler.close()

    return cerrar
