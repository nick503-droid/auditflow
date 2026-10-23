"""Transiciones UI simuladas: no graban pantalla ni abren dispositivos."""
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc-app'))
from ui.recording_actions import ejecutar_transicion, proteger_aplicacion, restaurar_aplicacion, preparar_salida, restaurar_tras_cierre


class TransitionTests(unittest.TestCase):
    def test_closed_view_restores_exclusion_using_main_window_not_destroyed_frame(self):
        owner = types.SimpleNamespace(controlador=Mock(), _captura_main_protegida=True)
        with patch('ui.recording_actions._afinidad_ventana') as affinity:
            restaurar_tras_cierre(owner)
            delay, callback = owner.controlador.after.call_args.args
            self.assertEqual(delay, 0)
            callback()
            affinity.assert_called_once_with(owner.controlador, 0)
            self.assertFalse(owner._captura_main_protegida)

    def test_processing_blocks_new_pause_or_resume_action(self):
        owner, queue = self.owner()
        owner._procesando_video = True
        action, success = Mock(), Mock()
        ejecutar_transicion(owner, action, success)
        action.assert_not_called()
        self.assertEqual(queue, [])

    def test_bitacora_keeps_original_offline_row_during_export(self):
        from test_pc_evidence_sync import load_methods
        klass, _ = load_methods('bitacoras_frame.py', 'BitacorasFrame', {'_mostrar_panel_evidencia'})
        frame = klass()
        frame._cerrado = False
        frame._procesando_video = True
        frame._codigo_panel_activo = ''
        frame._bitacora_local_id_panel = 1
        frame._b_id_panel = ''
        frame._mostrar_panel_evidencia('', [], fila={'local_id': 2})
        self.assertEqual(frame._bitacora_local_id_panel, 1)

    def test_leaving_view_waits_for_video_attachment(self):
        owner, _ = self.owner()
        owner._procesando_video = True
        self.assertFalse(preparar_salida(owner))
        owner._detener_grabacion.assert_called_once()
        owner._procesando_video = False
        owner.grabador.estado = 'detenido'
        self.assertTrue(preparar_salida(owner))

    def test_main_window_exclusion_is_temporary_and_restored(self):
        owner = types.SimpleNamespace(controlador=object())
        with patch('ui.recording_actions._afinidad_ventana', return_value=True) as affinity:
            proteger_aplicacion(owner)
            proteger_aplicacion(owner)
            self.assertTrue(owner._captura_main_protegida)
            restaurar_aplicacion(owner)
            restaurar_aplicacion(owner)
            self.assertFalse(owner._captura_main_protegida)
            self.assertEqual([c.args[1] for c in affinity.call_args_list], [0x11, 0])

    def owner(self):
        queue = []
        owner = types.SimpleNamespace(_cerrado=False, grabador=Mock(), controlador=Mock(),
                                      _ocultar_indicador_rec=Mock(), _actualizar_botones_grabacion=Mock(),
                                      _detener_grabacion=Mock())
        owner.after = lambda delay, callback: queue.append(callback)
        return owner, queue

    def test_stop_requested_while_transition_is_queued_after_success(self):
        owner, queue = self.owner()
        done = threading.Event()
        success = Mock()
        ejecutar_transicion(owner, done.set, success)
        self.assertTrue(owner._transicion_grabacion)
        queue.pop(0)()
        self.assertTrue(done.wait(2))
        owner._detener_pendiente = True
        while queue and not success.called:
            queue.pop(0)()
        success.assert_called_once()
        owner._detener_grabacion.assert_called_once()
        self.assertFalse(owner._transicion_grabacion)

    def test_error_closes_capture_and_restores_controls(self):
        owner, queue = self.owner()
        done = threading.Event()
        owner.grabador.detener.side_effect = done.set
        success = Mock()
        with patch('ui.recording_actions.messagebox.showerror') as error:
            ejecutar_transicion(owner, Mock(side_effect=RuntimeError('fixture')), success)
            queue.pop(0)()
            self.assertTrue(done.wait(2))
            while queue and not error.called:
                queue.pop(0)()
            error.assert_called_once()
        self.assertFalse(owner._transicion_grabacion)
        success.assert_not_called()
        owner.controlador.deiconify.assert_called_once()
        owner.grabador.detener.assert_called_once()

    def test_closing_view_while_starting_does_not_leave_capture_running(self):
        owner, queue = self.owner()
        entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
        def action():
            entered.set()
            release.wait(2)
        owner.grabador.detener.side_effect = stopped.set
        success = Mock()
        ejecutar_transicion(owner, action, success)
        queue.pop(0)()
        self.assertTrue(entered.wait(2))
        owner._cerrado = True
        release.set()
        self.assertTrue(stopped.wait(2))
        queue.pop(0)()
        success.assert_not_called()
