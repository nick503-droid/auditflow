"""Archivos sintéticos y CTk/TkDnD real, sin red ni datos del usuario."""
from pathlib import Path
import os
import shutil
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc-app"))
import customtkinter as ctk
from ui.evidence_picker import EvidencePicker, agregar_archivos, activar_arrastre, seleccionar_evidencias
from ui.theme import PRIMARY_SOFT, SURFACE_SECONDARY
import test_pc_evidence_sync as sync


class ValidationTests(unittest.TestCase):
    def test_reentrant_click_does_not_open_another_dialog_and_flag_is_released(self):
        owner = Mock(spec=['wait_window']); owner._selector_evidencias_abierto = False
        owner.wait_window.side_effect = lambda dialog: self.assertEqual(seleccionar_evidencias(owner), ())
        with patch('ui.evidence_picker.EvidencePicker', return_value=types.SimpleNamespace(resultado=('first.jpg',))) as factory:
            self.assertEqual(seleccionar_evidencias(owner), ('first.jpg',))
            factory.assert_called_once_with(owner)
        self.assertFalse(owner._selector_evidencias_abierto)

    def test_keeps_selection_order_and_deduplicates_paths_not_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a').mkdir(); (root / 'b').mkdir()
            first, second = root / 'a' / 'igual.jpg', root / 'b' / 'igual.jpg'
            first.write_bytes(b'first'); second.write_bytes(b'second')
            rows, errors = agregar_archivos([str(second)], [first, second, first])
            self.assertEqual(rows, [str(second), str(first)])
            self.assertFalse(errors)
            self.assertEqual(first.read_bytes(), b'first')

    def test_rejects_directories_missing_and_empty_but_keeps_regular_files(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / 'empty.jpg'; empty.touch()
            document = Path(directory) / 'prueba.pdf'; document.write_bytes(b'fixture')
            rows, errors = agregar_archivos([], [directory, empty, document, 'http://fixture.invalid/test.mp4'])
            self.assertEqual(rows, [str(document)])
            self.assertEqual(len(errors), 3)


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.geometry('900x700')
        cls.root.attributes('-alpha', 0)
        cls.errors = []
        cls.root.report_callback_exception = lambda *args: cls.errors.append(str(args[1]))
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        for job in cls.root.tk.call('after', 'info'):
            cls.root.after_cancel(job)
        cls.root.destroy()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def dialog(self):
        dialog = EvidencePicker(self.root)
        self.addCleanup(lambda: dialog.destroy() if dialog.winfo_exists() else None)
        return dialog

    def files(self):
        result = [Path(self.folder.name) / name for name in ('primero con espacios.jpg', 'segundo;{área}.mp4')]
        for i, path in enumerate(result): path.write_bytes(bytes([i + 1]))
        return list(map(str, result))

    def event(self, paths):
        # Igual que CF_HDROP: una lista Tcl serializada, no split por espacios.
        data = self.root.tk.call('format', '%s', self.root.tk.call('list', *paths))
        return types.SimpleNamespace(data=data)

    def test_loads_native_tkdnd_once_without_growing_auto_path(self):
        version = activar_arrastre(self.root)
        before = self.root.tk.call('set', 'auto_path')
        self.assertEqual(activar_arrastre(self.root), version)
        self.assertEqual(self.root.tk.call('set', 'auto_path'), before)

    def test_drop_handles_spaces_braces_unicode_and_confirms_only_on_click(self):
        dialog = self.dialog()
        paths = self.files()
        self.assertGreater(len(dialog._targets), 3)
        self.assertTrue(dialog.tk.call('bind', dialog.zona._w, '<<Drop>>'))
        self.assertEqual(dialog._soltar(self.event(paths)), 'copy')
        self.assertEqual(dialog.archivos, paths)
        self.assertEqual(dialog.resultado, ())
        dialog._soltar(self.event(paths))
        self.assertEqual(dialog.archivos, paths)
        dialog.confirmar()
        self.assertEqual(dialog.resultado, tuple(paths))
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_browse_and_drop_share_the_same_list_and_cancel_does_not_confirm(self):
        dialog = self.dialog(); paths = self.files()
        with patch('ui.evidence_picker.filedialog.askopenfilenames', return_value=(paths[0],)) as browse:
            dialog.explorar()
            self.assertIs(browse.call_args.kwargs['parent'], dialog)
        dialog._soltar(self.event(paths))
        self.assertEqual(dialog.archivos, paths)
        dialog._quitar(paths[0])
        self.assertEqual(dialog.archivos, paths[1:])
        dialog.cancelar()
        self.assertEqual(dialog.resultado, ())

    def test_cancel_native_browser_keeps_the_dialog_and_existing_files(self):
        dialog = self.dialog(); paths = self.files(); dialog._agregar(paths)
        with patch('ui.evidence_picker.filedialog.askopenfilenames', return_value=()): dialog.explorar()
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(dialog.archivos, paths)

    def test_unavailable_dnd_still_allows_browse(self):
        with patch('ui.evidence_picker.activar_arrastre', side_effect=RuntimeError('fixture DLL ausente')):
            dialog = self.dialog()
        self.assertIn('Buscar', dialog.instruccion.cget('text'))
        with patch('ui.evidence_picker.filedialog.askopenfilenames', return_value=tuple(self.files())):
            dialog.explorar()
        dialog.confirmar()
        self.assertEqual(len(dialog.resultado), 2)

    def test_empty_folder_drop_gives_inline_error_and_cannot_confirm(self):
        dialog = self.dialog()
        dialog._soltar(self.event([self.folder.name]))
        self.assertIn('carpetas', dialog.estado.cget('text'))
        self.assertEqual(dialog.adjuntar.cget('state'), 'disabled')
        dialog.confirmar()
        self.assertTrue(dialog.winfo_exists())

    def test_malformed_tcl_list_is_rejected_without_changing_queue(self):
        dialog = self.dialog()
        self.assertEqual(dialog._soltar(types.SimpleNamespace(data='{lista incompleta')), 'refuse_drop')
        self.assertEqual(dialog.archivos, [])
        self.assertIn('Buscar', dialog.estado.cget('text'))

    def test_light_dark_highlight_and_cleanup_without_callback_errors(self):
        dialog = self.dialog()
        for mode in ('Light', 'Dark', 'Light', 'Dark'):
            ctk.set_appearance_mode(mode)
            self.assertEqual(dialog._entrar(), 'copy')
            self.assertEqual(dialog.zona.cget('fg_color'), PRIMARY_SOFT)
            dialog._salir()
            self.assertEqual(dialog.zona.cget('fg_color'), SURFACE_SECONDARY)
            self.root.update_idletasks()
        dialog.cancelar(); dialog.destroy()
        self.assertFalse(self.errors, self.errors)


class IntegrationTests(unittest.TestCase):
    def report(self):
        klass, env = sync.load_methods('reportes_frame.py', 'ReportesFrame', {'_on_adjuntar'},
                                      {'shutil': shutil, 'sqlite3': sqlite3, 'seleccionar_evidencias': Mock(), 'messagebox': Mock()})
        frame = klass(); frame._cerrado = False; frame.borrador = {'id': 1}
        frame.switch_audio = Mock(); frame.switch_audio.get.return_value = False
        frame.reporte_remoto_id = None
        for name in ('_registrar_evidencia_para_sincronizar', '_refrescar_lista_evidencias', '_actualizar_estado_lbl', '_solicitar_sincronizacion_evidencias'):
            setattr(frame, name, Mock())
        frame._prefijo_nube = lambda: 'reportes/test'
        return frame, env

    def test_report_batch_copies_without_overwriting_and_syncs_once(self):
        frame, env = self.report()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('a', 'b', 'out'): (root / name).mkdir()
            paths = [root / 'a' / 'igual.jpg', root / 'b' / 'igual.jpg']
            for i, path in enumerate(paths): path.write_bytes(bytes([i + 1]))
            env['seleccionar_evidencias'].return_value = tuple(map(str, paths))
            frame._ruta_destino_evidencia = lambda name: str(root / 'out' / name)
            frame._on_adjuntar()
            calls = frame._registrar_evidencia_para_sincronizar.call_args_list
            self.assertEqual(len(calls), 2)
            self.assertNotEqual(calls[0].args[0], calls[1].args[0])
            self.assertEqual([Path(c.args[0]).read_bytes() for c in calls], [b'\1', b'\2'])
            self.assertTrue(all(p.exists() for p in paths))
            for call in calls: self.assertEqual(call.kwargs, {'refrescar': False, 'iniciar_sync': False})
            frame._refrescar_lista_evidencias.assert_called_once()
            frame._solicitar_sincronizacion_evidencias.assert_called_once()

    def test_cancel_or_changed_report_never_copies_files(self):
        frame, env = self.report(); env['seleccionar_evidencias'].return_value = ()
        frame._on_adjuntar(); frame._registrar_evidencia_para_sincronizar.assert_not_called()
        def changed(owner): owner.borrador = {'id': 2}; return ('first.jpg',)
        env['seleccionar_evidencias'].side_effect = changed
        frame._on_adjuntar(); frame._registrar_evidencia_para_sincronizar.assert_not_called()

    def test_bitacora_removed_during_dialog_does_not_attach_to_another_row(self):
        frame, env = sync.FrameRegressionTests().bitacora()
        env['messagebox'] = Mock()
        frame._registrar_evidencia_local_bitacora = Mock()
        def removed(owner): owner.filas.clear(); return ('first.jpg',)
        env['seleccionar_evidencias'] = Mock(side_effect=removed)
        frame._on_adjuntar()
        frame._registrar_evidencia_local_bitacora.assert_not_called()
        env['messagebox'].showwarning.assert_called_once()

    def test_bitacora_retains_original_row_if_panel_changes_during_dialog(self):
        frame, env = sync.FrameRegressionTests().bitacora()
        frame._registrar_evidencia_local_bitacora = Mock(return_value=True)
        frame._refrescar_lista_evidencias = Mock(); frame._solicitar_sincronizacion_evidencias = Mock()
        def changed(owner): owner._b_id_panel = 'otra'; return ('first.jpg', 'second.jpg')
        env['seleccionar_evidencias'] = Mock(side_effect=changed)
        frame._on_adjuntar()
        self.assertEqual(frame._b_id_panel, 'bit-test')
        self.assertEqual([c.args[0] for c in frame._registrar_evidencia_local_bitacora.call_args_list], ['first.jpg', 'second.jpg'])
        frame._solicitar_sincronizacion_evidencias.assert_called_once()


if __name__ == '__main__': unittest.main()
