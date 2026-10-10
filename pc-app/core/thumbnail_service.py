"""Dos workers compartidos; resultados PIL entregados a Tk sólo desde su hilo."""
from collections import OrderedDict
import logging
import os
import queue
import threading
import time

from core.thumbnailer import generar_miniatura

LOG = logging.getLogger("AuditFlow.Thumbnails")


class ServicioMiniaturas:
    def __init__(self, workers=2, max_pending=32, loader=None):
        self._loader = loader or (lambda source: generar_miniatura(source, placeholder=False))
        self._cola = queue.Queue(maxsize=max_pending)
        self._lock = threading.Lock()
        self._en_curso = {}
        self._cache = OrderedDict()
        self._cerrado = False
        self._threads = [threading.Thread(target=self._worker, daemon=True,
                         name=f"Miniaturas-{i}") for i in range(workers)]
        for thread in self._threads:
            thread.start()

    def solicitar(self, source, callback):
        version = ""
        if not source.startswith(("http://", "https://")):
            try:
                stat = os.stat(source)
                version = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                pass
        key = (source, version)
        with self._lock:
            if self._cerrado:
                return False
            cached = self._cache.get(key)
            if cached is not None and cached[0] > time.monotonic():
                self._cache.move_to_end(key)
                result = cached[1]
            elif key in self._en_curso:
                self._en_curso[key].append(callback)
                return True
            else:
                # La cola es acotada, no se crea un thread por evidencia.
                self._en_curso[key] = [callback]
                try:
                    self._cola.put_nowait((key, source))
                except queue.Full:
                    self._en_curso.pop(key)
                    return False
                return True
        callback(result)
        return True

    def _worker(self):
        while True:
            job = self._cola.get()
            if job is None:
                self._cola.task_done()
                return
            key, source = job
            try:
                image = self._loader(source)
            except Exception:
                LOG.exception("Error generando miniatura")
                image = None
            with self._lock:
                callbacks = self._en_curso.pop(key, [])
                self._cache[key] = (time.monotonic() + (300 if image is not None else 15), image)
                self._cache.move_to_end(key)
                while len(self._cache) > 128:
                    self._cache.popitem(last=False)
            for callback in callbacks:
                try:
                    callback(image)
                except Exception:
                    LOG.exception("Error entregando miniatura")
            self._cola.task_done()

    def cerrar(self):
        """Para pruebas/fin de proceso; los workers de producción son daemon."""
        with self._lock:
            self._cerrado = True
        for _ in self._threads:
            self._cola.put(None)
        for thread in self._threads:
            thread.join(timeout=2)


_servicio = None
_servicio_lock = threading.Lock()


def servicio_miniaturas():
    global _servicio
    with _servicio_lock:
        if _servicio is None:
            _servicio = ServicioMiniaturas()
        return _servicio


class MiniaturasUI:
    def __init__(self, owner, servicio=None):
        self.owner = owner
        self.servicio = servicio or servicio_miniaturas()
        self._resultados = queue.Queue()
        self._callbacks = {}
        self._pendientes = {}
        self._contador = 0
        self._after = None
        self._cerrado = threading.Event()

    def solicitar(self, source, callback):
        """Llamar desde Tk. callback recibe PIL/None, nunca desde un worker."""
        if self._cerrado.is_set():
            return
        from api.client import normalizar_url
        if source.startswith(("http://", "https://")):
            source = normalizar_url(source)
        self._contador += 1
        token = self._contador
        self._callbacks[token] = (source, callback, 0)
        self._pendientes[token] = 0.0
        if self._after is None:
            self._after = self.owner.after(80, self._procesar)

    def _entregar(self, token, image):
        # No after(), winfo_exists(), CTkImage ni ninguna llamada Tcl aquí.
        if not self._cerrado.is_set():
            self._resultados.put((token, image))

    def _procesar(self):
        self._after = None
        if self._cerrado.is_set():
            return
        for _ in range(16):
            try:
                token, image = self._resultados.get_nowait()
            except queue.Empty:
                break
            entry = self._callbacks.pop(token, None)
            if entry is not None:
                source, callback, intentos = entry
                try:
                    vivo = callback(image)
                except Exception:
                    LOG.exception("Error mostrando miniatura")
                    vivo = False
                if image is None and vivo is not False and intentos < 2:
                    self._callbacks[token] = (source, callback, intentos + 1)
                    self._pendientes[token] = time.monotonic() + 20
        enviados = 0
        for token, cuando in list(self._pendientes.items()):
            if cuando > time.monotonic():
                continue
            source = self._callbacks[token][0]
            if not self.servicio.solicitar(source, lambda image, t=token: self._entregar(t, image)):
                break
            self._pendientes.pop(token)
            enviados += 1
            if enviados >= 32:
                break
        if self._callbacks:
            self._after = self.owner.after(100 if len(self._pendientes) < len(self._callbacks) else 500, self._procesar)

    def cerrar(self):
        self._cerrado.set()
        if self._after is not None:
            self.owner.after_cancel(self._after)
            self._after = None
        self._callbacks.clear()
        self._pendientes.clear()
        while not self._resultados.empty():
            try:
                self._resultados.get_nowait()
            except queue.Empty:
                break
