"""Límites de red/workers, caché y despacho de miniaturas sin Tk ni servidor real."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pc-app"))
from PIL import Image
from core import thumbnailer
from core.thumbnail_service import MiniaturasUI, ServicioMiniaturas


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("Worker did not finish")
        time.sleep(0.01)


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = patch.object(thumbnailer, "CARPETA_MINIATURAS", self.temp.name)
        self.cache.start()
        self.api = patch.dict(sys.modules, {"api.client": types.SimpleNamespace(normalizar_url=lambda url: url)})
        self.api.start()

    def tearDown(self):
        self.api.stop()
        self.cache.stop()
        self.temp.cleanup()

    def test_remote_image_is_downloaded_once_and_response_is_closed(self):
        buffer = io.BytesIO()
        Image.new("RGB", (300, 200), "blue").save(buffer, "PNG")
        response = Mock(headers={"Content-Length": str(len(buffer.getvalue()))})
        response.iter_content.return_value = [buffer.getvalue()]
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch.object(thumbnailer.requests, "get", return_value=context) as download:
            first = thumbnailer.generar_miniatura("http://fixture.invalid/photo.jpg")
            second = thumbnailer.generar_miniatura("http://fixture.invalid/photo.jpg")
        self.assertEqual(first.size, (160, 96))
        self.assertEqual(second.size, (160, 96))
        download.assert_called_once_with("http://fixture.invalid/photo.jpg", stream=True, timeout=(3, 5))
        context.__exit__.assert_called_once()

    def test_oversized_image_is_rejected_before_reading(self):
        response = Mock(headers={"Content-Length": str(16 * 1024 * 1024)})
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch.object(thumbnailer.requests, "get", return_value=context):
            self.assertIsNone(thumbnailer.generar_miniatura("http://fixture.invalid/big.jpg", placeholder=False))
        response.iter_content.assert_not_called()
        context.__exit__.assert_called_once()

    def test_failed_network_does_not_persist_placeholder_and_can_recover(self):
        with patch.object(thumbnailer, "_descargar_imagen", return_value=None):
            placeholder = thumbnailer.generar_miniatura("http://fixture.invalid/photo.jpg")
        self.assertEqual(placeholder.size, (160, 96))
        self.assertEqual(list(Path(self.temp.name).glob("*.jpg")), [])
        with patch.object(thumbnailer, "_descargar_imagen", return_value=Image.new("RGB", (200, 100))) as download:
            self.assertIsNotNone(thumbnailer.generar_miniatura("http://fixture.invalid/photo.jpg", placeholder=False))
        download.assert_called_once()
        self.assertEqual(len(list(Path(self.temp.name).glob("*.jpg"))), 1)

    def test_video_has_process_and_network_timeouts_and_no_window(self):
        with patch.object(thumbnailer.subprocess, "run", side_effect=subprocess.TimeoutExpired("ffmpeg", 8)) as run:
            self.assertIsNone(thumbnailer._primer_cuadro_video("http://fixture.invalid/video.mp4"))
        args, kwargs = run.call_args
        self.assertEqual(kwargs["timeout"], 8)
        self.assertIn("-rw_timeout", args[0])
        self.assertIn("3000000", args[0])
        self.assertIn("-nostdin", args[0])
        self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_video_frame_is_cached(self):
        buffer = io.BytesIO()
        Image.new("RGB", (160, 90), "red").save(buffer, "JPEG")
        result = subprocess.CompletedProcess([], 0, stdout=buffer.getvalue())
        with patch.object(thumbnailer.subprocess, "run", return_value=result) as run:
            self.assertIsNotNone(thumbnailer.generar_miniatura("http://fixture.invalid/video.mp4"))
            self.assertIsNotNone(thumbnailer.generar_miniatura("http://fixture.invalid/video.mp4"))
        run.assert_called_once()

    def test_local_cache_invalidates_when_source_changes(self):
        path = Path(self.temp.name) / "source.png"
        Image.new("RGB", (20, 20), "red").save(path)
        first = thumbnailer._ruta_cache(str(path), (160, 96))
        Image.new("RGB", (30, 30), "blue").save(path)
        second = thumbnailer._ruta_cache(str(path), (160, 96))
        self.assertNotEqual(first, second)

    def test_ffmpeg_resolver_finds_pyinstaller_bundle(self):
        from core.ffmpeg_path import obtener_ruta_ffmpeg
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", self.temp.name, create=True):
            self.assertEqual(Path(obtener_ruta_ffmpeg()), Path(self.temp.name) / "ffmpeg.exe")


class WorkerTests(unittest.TestCase):
    def test_workers_and_waiting_queue_are_bounded(self):
        release = threading.Event()
        lock = threading.Lock()
        active = peak = 0
        completed = []
        def loader(source):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            release.wait(2)
            with lock: active -= 1
            return source
        pool = ServicioMiniaturas(workers=2, max_pending=3, loader=loader)
        try:
            accepted = [pool.solicitar(f"http://fixture.invalid/{i}", completed.append) for i in range(30)]
            self.assertLessEqual(sum(accepted), 5)
            self.assertTrue(any(not value for value in accepted))
            release.set()
            wait_until(lambda: len(completed) == sum(accepted))
            self.assertLessEqual(peak, 2)
        finally:
            release.set()
            pool.cerrar()

    def test_same_source_is_deduplicated_and_reused(self):
        release = threading.Event()
        calls = []
        results = []
        def loader(source):
            calls.append(source)
            release.wait(2)
            return "image"
        pool = ServicioMiniaturas(loader=loader)
        try:
            for _ in range(10): self.assertTrue(pool.solicitar("http://fixture.invalid/same.jpg", results.append))
            release.set()
            wait_until(lambda: len(results) == 10)
            self.assertTrue(pool.solicitar("http://fixture.invalid/same.jpg", results.append))
            self.assertEqual(calls, ["http://fixture.invalid/same.jpg"])
            self.assertEqual(len(results), 11)
        finally:
            release.set()
            pool.cerrar()

    def test_dispatcher_delivers_only_on_ui_thread_and_discards_after_close(self):
        main = threading.get_ident()
        class Owner:
            def __init__(self): self.scheduled = []
            def after(self, delay, callback):
                assert threading.get_ident() == main
                self.scheduled.append(callback)
                return callback
            def after_cancel(self, token):
                assert threading.get_ident() == main
                self.scheduled.remove(token)
        owner = Owner()
        service = Mock()
        accepted = []
        def submit(source, callback):
            accepted.append(callback)
            return True
        service.solicitar.side_effect = submit
        ui = MiniaturasUI(owner, service)
        callback = Mock(side_effect=lambda image: self.assertEqual(threading.get_ident(), main))
        with patch.dict(sys.modules, {"api.client": types.SimpleNamespace(normalizar_url=lambda url: url)}):
            ui.solicitar("http://fixture.invalid/image.jpg", callback)
        owner.scheduled.pop(0)()
        worker = threading.Thread(target=lambda: accepted[0]("image"))
        worker.start()
        worker.join()
        callback.assert_not_called()
        owner.scheduled.pop(0)()
        callback.assert_called_once_with("image")
        with patch.dict(sys.modules, {"api.client": types.SimpleNamespace(normalizar_url=lambda url: url)}):
            ui.solicitar("http://fixture.invalid/other.jpg", callback)
        owner.scheduled.pop(0)()
        ui.cerrar()
        accepted[-1]("late-image")
        self.assertTrue(ui._resultados.empty())
        self.assertFalse(owner.scheduled)
        self.assertEqual(callback.call_count, 1)


if __name__ == "__main__":
    unittest.main()
