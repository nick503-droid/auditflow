"""Regresiones de UI/polling aisladas: no abren Tk, audio ni datos del usuario."""
import ast
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pc-app"))
from ui.evidence_list import ListaEvidencias, firma_evidencias, ordenar_evidencias
from ui.recording_actions import captura_pendiente


class Widget:
    def __init__(self, *args, **kwargs):
        self.options = dict(kwargs)
        self.destroyed = False
        self.grid_calls = 0
        self.configure_calls = 0

    def winfo_exists(self): return not self.destroyed
    def grid_columnconfigure(self, *args, **kwargs): pass
    def pack(self, *args, **kwargs): pass
    def pack_forget(self): pass
    def bind(self, *args, **kwargs): pass
    def grid(self, *args, **kwargs): self.grid_calls += 1
    def configure(self, **kwargs):
        self.configure_calls += 1
        self.options.update(kwargs)
    def destroy(self): self.destroyed = True


class Variable:
    def __init__(self, value=False): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


CTK = types.SimpleNamespace(**{name: Widget for name in
    ("CTkFrame", "CTkLabel", "CTkButton", "CTkCheckBox", "CTkTextbox", "CTkImage")}, BooleanVar=Variable)


def load_methods(filename, class_name, method_names, extra=None):
    tree = ast.parse((REPO / "pc-app" / "ui" / filename).read_text(encoding="utf-8-sig"))
    source = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    definition = ast.ClassDef(name="Probe", bases=[], keywords=[], decorator_list=[],
        body=[n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in method_names])
    namespace = {"ctk": CTK, "IconButton": Widget, "IconLabel": Widget, "ListaEvidencias": ListaEvidencias,
        "firma_evidencias": firma_evidencias, "ordenar_evidencias": ordenar_evidencias,
        "get_font": lambda **kwargs: None, "os": __import__("os"), "captura_pendiente": captura_pendiente,
        "get_icon": lambda *args, **kwargs: None,
        "SURFACE_SECONDARY": "#eee", "BORDER": "#ddd", "TEXT_PRIMARY": "#333", "TEXT_SECONDARY": "#777", "TEXT_MUTED": "#777",
        "PRIMARY": "#047857", "PRIMARY_HOVER": "#065F46",
        "STATUS": {name: {"text": "#333", "bg": "#fff", "border": "#ddd", "solid": "#333", "hover": "#222", "hover_bg": "#eee"} for name in ("error", "success", "info")},
        "URGENCIA_LEGACY": {}, "threading": threading}
    namespace.update(extra or {})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[definition], type_ignores=[])), filename, "exec"), namespace)
    return namespace["Probe"], namespace


def evidence(count=6):
    return [{"id": str(i), "evidencia_url": f"http://fixture.invalid/{i}." + ("jpg" if i % 2 == 0 else "mp4")}
            for i in range(count)]


class EvidenceListTests(unittest.TestCase):
    def test_add_remove_reorder_preserves_other_widgets_and_selection(self):
        view = ListaEvidencias(Widget())
        factory = Mock(side_effect=lambda data: Widget())
        items = [(str(i), str(i), {"name": str(i)}) for i in range(3)]
        view.actualizar(items, factory)
        originals = view.widgets()
        originals[1].selection = True
        for _ in range(30): view.actualizar(items, factory)
        self.assertEqual(factory.call_count, 3)
        self.assertEqual(view.widgets(), originals)
        view.actualizar([items[1], items[2], ("3", "3", {})], factory)
        self.assertTrue(originals[0].destroyed)
        self.assertIs(view.widgets()[0], originals[1])
        self.assertTrue(view.widgets()[0].selection)
        self.assertEqual(factory.call_count, 4)

    def test_only_changed_source_is_recreated(self):
        view = ListaEvidencias(Widget())
        factory = Mock(side_effect=lambda data: Widget())
        view.actualizar([("a", "url1", {}), ("b", "url2", {})], factory)
        first, second = view.widgets()
        view.actualizar([("a", "url3", {}), ("b", "url2", {})], factory)
        self.assertTrue(first.destroyed)
        self.assertIs(view.widgets()[1], second)
        self.assertEqual(factory.call_count, 3)

    def test_signature_ignores_order_and_unrelated_metadata(self):
        rows = evidence()
        changed = [{**row, "updated_at": "later"} for row in reversed(rows)]
        self.assertEqual(firma_evidencias(rows), firma_evidencias(changed))
        self.assertEqual(ordenar_evidencias(rows), ordenar_evidencias(list(reversed(rows))))
        changed[0]["evidencia_url"] = "different.jpg"
        self.assertNotEqual(firma_evidencias(rows), firma_evidencias(changed))


class FrameRegressionTests(unittest.TestCase):
    def report(self, local=None):
        pending = Mock(side_effect=lambda draft_id: local if local is not None else [])
        klass, env = load_methods("reportes_frame.py", "ReportesFrame", {
            "_refrescar_lista_evidencias", "_crear_tarjeta_evidencia", "_aplicar_estado_remoto",
            "_solicitar_sincronizacion_evidencias", "_terminar_sincronizacion_evidencias", "_agregar_evidencia_remota",
            "_subir_evidencias_de_borrador",
        }, {"obtener_evidencias": pending, "actualizar_indicador_reporte": Mock()})
        frame = klass()
        frame._cerrado = False
        frame.borrador = {"id": 1}
        frame.reporte_remoto_id = "report-test"
        frame.reporte_version = 1
        frame.frame_lista_evidencias = Widget()
        frame.label_estado_evidencias = Widget()
        frame.textbox_notas = Widget()
        frame._lista_evidencias = None
        frame.evidencias_nube = evidence()
        frame._texto_base_remoto = ""
        frame._guardando_texto = False
        frame._miniaturas = types.SimpleNamespace(solicitar=Mock())
        frame._lock_sync_evidencias = threading.Lock()
        frame._previsualizar_archivo = Mock()
        frame._eliminar_evidencia_nube = Mock()
        frame._eliminar_evidencia_local = Mock()
        return frame, env

    def bitacora(self, local=None):
        pending = Mock(side_effect=lambda **kwargs: local if local is not None else [])
        klass, env = load_methods("bitacoras_frame.py", "BitacorasFrame", {
            "_mostrar_panel_evidencia", "_refrescar_lista_evidencias", "_agregar_chip_evidencia",
            "_agregar_chip_evidencia_local", "_solicitar_sincronizacion_evidencias", "_on_adjuntar",
            "_actualizar_fila_remota", "_actualizar_boton_evidencia", "_actualizar_evidencias_fila",
            "_finalizar_sincronizacion_evidencias",
            "_continuar_evidencia",
        }, {"obtener_evidencias_bitacora_pendientes": pending,
             "datetime": __import__("datetime").datetime})
        frame = klass()
        frame._cerrado = False
        frame._codigo_panel_activo = "TEST12"
        frame._bitacora_local_id_panel = 1
        frame._b_id_panel = "bit-test"
        frame._panel_ev_visible = False
        frame._codigo_mostrado = None
        frame._firma_panel_evidencias = None
        frame._lista_ev_tarjetas = None
        frame._lista_local_tarjetas = None
        frame.frame_evidencia = Widget()
        frame.label_codigo = Widget()
        frame.frame_lista_ev = Widget()
        frame.frame_lista_local = Widget()
        frame.label_archivo = Widget()
        frame.boton_subir = Widget()
        frame.grid_columnconfigure = Mock()
        frame._miniaturas = types.SimpleNamespace(solicitar=Mock())
        frame._lock_sync_evidencias = threading.Lock()
        frame._actualizar_indicador_sync = Mock()
        frame._actualizar_boton_evidencia_de_fila_activa = Mock()
        frame._cantidad_evidencias_locales = Mock(return_value=len(local or []))
        frame._mostrar_toast = Mock()
        frame._eliminar_evidencia_nube = Mock()
        frame.lock = threading.Lock()
        frame.campos_editando = {}
        frame.filas = [{"codigo": "TEST12", "b_id": "bit-test", "local_id": 1,
                        "evidencias": evidence(), "_widgets": {"evidencia": Widget()}}]
        return frame, env

    def test_report_idle_polling_does_not_start_sync_or_recreate_cards(self):
        frame, env = self.report()
        frame._refrescar_lista_evidencias()
        original = frame._lista_evidencias.widgets()
        env["threading"] = types.SimpleNamespace(Thread=Mock(side_effect=AssertionError("Unexpected worker")))
        for _ in range(30):
            frame._aplicar_estado_remoto({"notas_finales": "", "evidencias": list(reversed(evidence())), "version": 1})
            frame._solicitar_sincronizacion_evidencias()
        self.assertEqual(frame._lista_evidencias.widgets(), original)
        self.assertEqual(frame._miniaturas.solicitar.call_count, 3)
        env["threading"].Thread.assert_not_called()

    def test_report_new_and_deleted_evidence_preserve_other_cards(self):
        frame, _ = self.report()
        frame._refrescar_lista_evidencias()
        original = frame._lista_evidencias.widgets()
        frame._agregar_evidencia_remota({"id": "new", "evidencia_url": "http://fixture.invalid/new.jpg"})
        self.assertEqual(frame._lista_evidencias.widgets()[:6], original)
        frame.evidencias_nube = frame.evidencias_nube[1:]
        frame._refrescar_lista_evidencias()
        self.assertTrue(original[0].destroyed)
        self.assertEqual(frame._lista_evidencias.widgets()[:5], original[1:])

    def test_local_offline_evidence_remains_visible(self):
        local = [{"id": 10, "ruta_local": "pending.mp4"}]
        frame, _ = self.report(local)
        frame.reporte_remoto_id = None
        frame._refrescar_lista_evidencias()
        frame._solicitar_sincronizacion_evidencias()
        self.assertEqual(len(frame._lista_evidencias.widgets()), 7)
        self.assertEqual(local, [{"id": 10, "ruta_local": "pending.mp4"}])

    def test_bitacora_empty_sync_and_repeated_refresh_keep_cards_and_checkboxes(self):
        frame, env = self.bitacora()
        frame._refrescar_lista_evidencias()
        original = frame._lista_ev_tarjetas.widgets()
        selected = frame._checkboxes_desc_bit[0][0]
        selected.set(True)
        env["threading"] = types.SimpleNamespace(Thread=Mock(side_effect=AssertionError("Unexpected worker")))
        for _ in range(12):
            frame._solicitar_sincronizacion_evidencias()
            frame._mostrar_panel_evidencia("TEST12", list(reversed(evidence())))
        self.assertEqual(frame._lista_ev_tarjetas.widgets(), original)
        self.assertIs(frame._checkboxes_desc_bit[0][0], selected)
        self.assertTrue(selected.get())
        self.assertEqual(frame._miniaturas.solicitar.call_count, 6)
        frame._actualizar_indicador_sync.assert_not_called()

    def test_bitacora_upload_adds_one_card_without_resetting_selection(self):
        frame, _ = self.bitacora()
        frame._refrescar_lista_evidencias()
        original = frame._lista_ev_tarjetas.widgets()
        frame._checkboxes_desc_bit[0][0].set(True)
        frame._finalizar_sincronizacion_evidencias({"TEST12": {"evidencias": [*evidence(), {"id": "new", "evidencia_url": "http://fixture.invalid/new.jpg"}]}}, 1)
        self.assertEqual(frame._lista_ev_tarjetas.widgets()[:6], original)
        self.assertTrue(frame._checkboxes_desc_bit[0][0].get())
        self.assertEqual(frame._miniaturas.solicitar.call_count, 7)

    def test_bitacora_batch_refreshes_once_and_starts_one_sync(self):
        frame, env = self.bitacora()
        env["filedialog"] = types.SimpleNamespace(askopenfilenames=lambda **kwargs: ["one.jpg", "two.jpg", "three.mp4"])
        frame._registrar_evidencia_local_bitacora = Mock(return_value=True)
        frame._refrescar_lista_evidencias = Mock()
        frame._solicitar_sincronizacion_evidencias = Mock()
        frame._on_adjuntar()
        frame._refrescar_lista_evidencias.assert_called_once()
        frame._solicitar_sincronizacion_evidencias.assert_called_once()
        for call in frame._registrar_evidencia_local_bitacora.call_args_list:
            self.assertFalse(call.kwargs["refrescar"])
            self.assertFalse(call.kwargs["iniciar_sync"])

    def test_bitacora_delta_updates_in_place_and_protects_local_edit(self):
        frame, _ = self.bitacora()
        frame.filas[0].update(descripcion="local edit", hora="10:00", version=1)
        frame.campos_editando = {0: {"descripcion"}}
        frame._actualizar_widgets_fila_in_place = Mock()
        frame._reconstruir_tarjeta = Mock(side_effect=AssertionError("Row should survive"))
        frame._actualizar_fila_remota(0, {"descripcion": "remote text", "hora": "11:00", "version": 2, "evidencias": evidence(7)})
        self.assertEqual(frame.filas[0]["descripcion"], "local edit")
        self.assertEqual(frame.filas[0]["hora"], "11:00")
        changes = frame._actualizar_widgets_fila_in_place.call_args.args[1]
        self.assertNotIn("descripcion", changes)
        self.assertIn("evidencias", changes)

    def test_bitacora_identical_delta_does_not_touch_widgets(self):
        frame, _ = self.bitacora()
        frame._actualizar_widgets_fila_in_place = Mock()
        frame._actualizar_fila_remota(0, {"codigo": "TEST12", "evidencias": list(reversed(evidence()))})
        frame._actualizar_widgets_fila_in_place.assert_not_called()

    def test_closed_frames_ignore_late_evidence_callbacks(self):
        report, _ = self.report()
        report._cerrado = True
        report._refrescar_lista_evidencias = Mock()
        report._agregar_evidencia_remota(evidence(1)[0])
        report._terminar_sincronizacion_evidencias(True)
        report._refrescar_lista_evidencias.assert_not_called()
        bitacora, _ = self.bitacora()
        bitacora._cerrado = True
        bitacora._refrescar_lista_evidencias = Mock()
        bitacora._finalizar_sincronizacion_evidencias({}, 0)
        bitacora._refrescar_lista_evidencias.assert_not_called()

    def test_report_failed_link_keeps_local_queue_for_reconnection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.mp4"
            path.write_bytes(b"fixture video")
            local = [{"id": 10, "ruta_local": str(path), "carpeta_destino": "reports/test"}]
            frame, env = self.report(local)
            env["subir_archivo_con_destino"] = Mock(return_value=("http://fixture.invalid/upload.mp4", None))
            env["crear_evidencia_reporte"] = Mock(return_value=None)
            env["eliminar_evidencia_borrador"] = Mock(side_effect=lambda ev_id: local.clear())
            env["es_archivo_grabado"] = lambda ruta: False
            self.assertFalse(frame._subir_evidencias_de_borrador(1, "report-test", "reports/test"))
            self.assertTrue(path.exists())
            env["eliminar_evidencia_borrador"].assert_not_called()
            env["crear_evidencia_reporte"].return_value = {"id": "new", "evidencia_url": "http://fixture.invalid/upload.mp4"}
            self.assertTrue(frame._subir_evidencias_de_borrador(1, "report-test", "reports/test"))
            self.assertFalse(local)
            env["eliminar_evidencia_borrador"].assert_called_once_with(10)

    def test_bitacora_rechecks_queue_under_lock_before_upload(self):
        # La comprobación inicial vio una evidencia, pero otro intento terminó
        # antes de adquirir el lock: no debe publicarla de nuevo.
        frame, env = self.bitacora()
        env["obtener_evidencias_bitacora_pendientes"] = Mock(side_effect=[
            [{"id": 1, "codigo": "TEST12", "ruta_local": "pending.mp4"}], []])
        env["adjuntar_evidencia_por_codigo"] = Mock(side_effect=AssertionError("Duplicate upload"))
        class ImmediateThread:
            def __init__(self, target, **kwargs): self.target = target
            def start(self): self.target()
        env["threading"] = types.SimpleNamespace(Thread=ImmediateThread)
        frame.after = Mock()
        frame._solicitar_sincronizacion_evidencias()
        env["adjuntar_evidencia_por_codigo"].assert_not_called()
        self.assertFalse(frame._lock_sync_evidencias.locked())

    def test_offline_fetch_does_not_clear_last_known_evidence(self):
        frame, env = self.bitacora()
        frame._refrescar_lista_evidencias()
        originals = frame._lista_ev_tarjetas.widgets()
        env["obtener_evidencias_bitacora"] = Mock(return_value=None)
        class ImmediateThread:
            def __init__(self, target, **kwargs): self.target = target
            def start(self): self.target()
        env["threading"] = types.SimpleNamespace(Thread=ImmediateThread)
        frame.after = Mock()
        frame._continuar_evidencia(0)
        self.assertEqual(frame.filas[0]["evidencias"], evidence())
        self.assertEqual(frame._lista_ev_tarjetas.widgets(), originals)
        frame.after.assert_not_called()

    def test_api_distinguishes_empty_evidence_from_failed_request(self):
        tree = ast.parse((REPO / "pc-app" / "api" / "client.py").read_text(encoding="utf-8-sig"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "obtener_evidencias_bitacora")
        requests = types.SimpleNamespace(get=Mock(side_effect=ConnectionError("fixture offline")),
                                         exceptions=types.SimpleNamespace(RequestException=ConnectionError))
        env = {"requests": requests, "API_BASE_URL": "http://fixture.invalid"}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), "client.py", "exec"), env)
        self.assertIsNone(env[function.name]("TEST12"))
        response = Mock()
        response.json.return_value = []
        requests.get.side_effect = None
        requests.get.return_value = response
        self.assertEqual(env[function.name]("TEST12"), [])


if __name__ == "__main__":
    unittest.main()
