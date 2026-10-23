"""Fallos simulados: no captura pantalla/audio ni abre datos reales."""
import ast
from pathlib import Path
import os
import subprocess
import threading
import time
import uuid
from datetime import datetime
import tempfile
import types
import unittest
from unittest.mock import Mock

from test_pc_evidence_sync import load_methods

REPO = Path(__file__).resolve().parents[1]


class RecordingRecoveryTests(unittest.TestCase):
    def recorder(self, folder):
        tree = ast.parse((REPO / "pc-app/core/recorder.py").read_text(encoding="utf-8"))
        klass = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        namespace = {"subprocess": subprocess, "os": os, "threading": threading, "time": time,
                     "uuid": uuid, "datetime": datetime, "GrabadorAudio": object,
                     "CARPETA_TEMPORAL": folder, "CARPETA_LOGS": folder,
                     "obtener_ruta_ffmpeg": lambda: "fixture-ffmpeg"}
        exec(compile(ast.Module(body=[klass], type_ignores=[]), "recorder.py", "exec"), namespace)
        recorder = namespace[klass.name]()
        recorder._detener_ffmpeg_actual = Mock()
        recorder.estado = "pausado"
        recorder._identificador_base = "fixture"
        recorder.ruta_final = str(Path(folder) / "final.mp4")
        return recorder

    def test_failed_concat_retains_segments_and_resets_state(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            recorder = self.recorder(folder)
            parts = [Path(folder) / f"part{i}.mp4" for i in range(2)]
            for part in parts: part.write_bytes(b"synthetic-test-data")
            recorder.rutas_video_temp = list(map(str, parts))
            for failure in (Mock(returncode=1), subprocess.TimeoutExpired("ffmpeg", 600)):
                with patch.object(subprocess, "run", **({"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure})):
                    recorder.estado = "pausado"
                    with self.assertRaises(RuntimeError): recorder.detener()
                self.assertEqual(recorder.estado, "detenido")
                self.assertTrue(all(p.exists() for p in parts))

    def test_missing_single_segment_resets_state(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = self.recorder(folder)
            recorder.rutas_video_temp = [str(Path(folder) / "missing.mp4")]
            with self.assertRaises(RuntimeError): recorder.detener()
            self.assertEqual(recorder.estado, "detenido")

    def test_restore_callback_runs_after_video_and_audio_stop_before_export(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = self.recorder(folder)
            recorder.estado = "grabando"
            events = []
            recorder._detener_ffmpeg_actual = Mock(side_effect=lambda: events.append("video-stopped"))
            recorder.con_audio = True
            recorder.grabador_audio = types.SimpleNamespace(
                grabando=False, rutas_audio_temp=[], timestamps_inicio_fragmentos=[],
                detener=lambda: events.append("audio-stopped"))
            recorder._unir_fragmentos = lambda paths: events.append("export")
            recorder.detener(al_detener_captura=lambda: events.append("show-app"))
            self.assertEqual(events[:4], ["video-stopped", "audio-stopped", "show-app", "export"])

    def test_audio_device_failure_is_reported_and_resources_are_released(self):
        import threading
        tree = ast.parse((REPO / "pc-app/core/audio_recorder.py").read_text(encoding="utf-8"))
        klass = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        device = Mock()
        device.get_host_api_info_by_type.side_effect = OSError("fixture device unavailable")
        namespace = {"threading": threading, "pyaudio": types.SimpleNamespace(PyAudio=lambda: device, paWASAPI=13)}
        exec(compile(ast.Module(body=[klass], type_ignores=[]), "audio_recorder.py", "exec"), namespace)
        audio = namespace[klass.name]()
        audio._grabar()
        self.assertFalse(audio.grabando)
        device.terminate.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, "fixture device unavailable"):
            audio.detener()

    @unittest.skipUnless(os.name == "nt" and (REPO / "pc-app/ffmpeg.exe").exists(), "Requiere FFmpeg de Windows")
    def test_real_ffmpeg_joins_synthetic_segments(self):
        ffmpeg = str(REPO / "pc-app/ffmpeg.exe")
        with tempfile.TemporaryDirectory() as folder:
            recorder = self.recorder(folder)
            recorder._finalizar_grabacion.__func__.__globals__["obtener_ruta_ffmpeg"] = lambda: ffmpeg
            for i in range(2):
                part = Path(folder) / f"part{i}.mp4"
                subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                                "color=c=blue:s=160x90:r=15", "-t", "0.3", "-c:v", "libx264", str(part)],
                               check=True, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
                recorder.rutas_video_temp.append(str(part))
            parts = list(recorder.rutas_video_temp)
            result = recorder.detener()
            self.assertGreater(Path(result).stat().st_size, 0)
            self.assertTrue(all(not Path(p).exists() for p in parts))
            subprocess.run([ffmpeg, "-v", "error", "-i", result, "-f", "null", "-"],
                           check=True, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)

    def test_initial_loading_waits_for_layout_before_starting_polling(self):
        klass, _ = load_methods("bitacoras_frame.py", "BitacorasFrame", {"_terminar_carga_inicial", "_revelar_carga_inicial", "_detener_animacion_carga"})
        frame = klass()
        frame._cerrado = False
        description = types.SimpleNamespace(_resize_job="pending")
        frame.filas = [{"_widgets": {"descripcion": description}}]
        frame.after = Mock()
        frame._iniciar_polling = Mock()
        frame._carga_overlay = Mock()
        barra = frame._barra_carga = Mock()
        frame._terminar_carga_inicial(2)
        frame._iniciar_polling.assert_not_called()
        barra.stop.assert_not_called()
        description._resize_job = None
        frame._terminar_carga_inicial(2)
        barra.set.assert_called_once_with(1)
        frame._carga_overlay.destroy.assert_not_called()
        frame._revelar_carga_inicial()
        frame._carga_overlay.destroy.assert_called_once()
        frame._iniciar_polling.assert_called_once()
        barra.stop.assert_called_once()
        self.assertIsNone(frame._barra_carga)
        frame._cerrado = True
        frame._terminar_carga_inicial(2)
        frame._iniciar_polling.assert_called_once()

    def test_progress_counts_completed_batches_and_never_reaches_full_before_layout(self):
        klass, _ = load_methods("bitacoras_frame.py", "BitacorasFrame",
                                {"_presentar_carga_inicial", "_cargar_lote_inicial"})
        frame = klass()
        frame._cerrado = False
        frame._barra_carga = Mock()
        frame._texto_carga = Mock()
        frame._terminar_carga_inicial = Mock()
        frame._reconciliar_con_datos = Mock()
        pending = []
        frame.after = lambda delay, callback, *args: pending.append((callback, args))
        records = [{"id": str(i)} for i in range(240)]
        frame._presentar_carga_inicial(records)
        self.assertLess(frame._carga_preparadas, 240)
        while pending:
            callback, args = pending.pop(0)
            callback(*args)
        values = [call.args[0] for call in frame._barra_carga.set.call_args_list]
        self.assertEqual(values, sorted(values))
        self.assertLess(max(values), 1)
        self.assertEqual(frame._carga_preparadas, 240)
        self.assertEqual([r for call in frame._reconciliar_con_datos.call_args_list for r in call.args[0]], records)
        self.assertLessEqual(len(values), 20)
        frame._terminar_carga_inicial.assert_called_once_with(0)
        self.assertIsNone(frame._carga_datos)

    def test_stop_worker_recovers_buttons_in_both_modules_on_failure(self):
        for filename, klassname in (("bitacoras_frame.py", "BitacorasFrame"), ("reportes_frame.py", "ReportesFrame")):
            errors = Mock()
            klass, _ = load_methods(filename, klassname, {"_detener_grabacion", "_mostrar_procesamiento_video"},
                                    {"messagebox": types.SimpleNamespace(showerror=errors), "restaurar_aplicacion": Mock()})
            frame = klass()
            frame._cerrado = False
            order = []
            def stop(al_detener_captura=None):
                order.append("capture-stopped")
                raise RuntimeError("fixture failure")
            frame.grabador = types.SimpleNamespace(detener=Mock(side_effect=stop))
            frame._ocultar_indicador_rec = Mock()
            frame.controlador = Mock()
            frame.controlador.deiconify.side_effect = lambda: order.append("show-app")
            frame.boton_grabar = Mock()
            frame.boton_detener = Mock()
            frame.switch_audio = Mock()
            frame._actualizar_botones_grabacion = Mock()
            import threading
            ready = threading.Event()
            def after(delay, callback, *args):
                callback(*args)
                ready.set()
            frame.after = after
            frame._detener_grabacion()
            self.assertTrue(ready.wait(3))
            self.assertFalse(frame._procesando_video)
            frame._actualizar_botones_grabacion.assert_called_once()
            errors.assert_called_once()
            self.assertEqual(order, ["capture-stopped", "show-app"])

    def test_both_modules_hide_before_launch_and_keep_audio_choice(self):
        for filename, klassname in (("bitacoras_frame.py", "BitacorasFrame"), ("reportes_frame.py", "ReportesFrame")):
            order = []
            def transition(owner, action, success, delay=0):
                self.assertGreaterEqual(delay, 100)
                action()
                success()
            klass, _ = load_methods(filename, klassname, {"_iniciar_grabacion"},
                                    {"ejecutar_transicion": transition, "proteger_aplicacion": Mock()})
            frame = klass()
            frame.switch_audio = Mock()
            frame.switch_audio.get.return_value = True
            frame.controlador = Mock()
            frame.controlador.withdraw.side_effect = lambda: order.append("hide-app")
            frame.boton_grabar = Mock()
            frame.grabador = Mock()
            frame.grabador.iniciar.side_effect = lambda **kwargs: order.append("start-capture")
            frame._mostrar_indicador_rec = lambda: order.append("show-indicator")
            frame._actualizar_botones_grabacion = Mock()
            frame._iniciar_grabacion()
            self.assertEqual(order, ["hide-app", "start-capture", "show-indicator"])
            self.assertTrue(frame._grabacion_con_audio)

    def test_stop_during_pause_transition_is_queued_in_both_modules(self):
        for filename, klassname in (("bitacoras_frame.py", "BitacorasFrame"), ("reportes_frame.py", "ReportesFrame")):
            klass, _ = load_methods(filename, klassname, {"_detener_grabacion"})
            frame = klass()
            frame._transicion_grabacion = True
            frame.grabador = Mock()
            frame._detener_grabacion()
            self.assertTrue(frame._detener_pendiente)
            frame.grabador.detener.assert_not_called()
