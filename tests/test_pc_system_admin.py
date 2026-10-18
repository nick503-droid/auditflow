"""Administración aislada: sin HTTP, Tk ni datos del usuario."""
import ast
import base64
import hashlib
import importlib.util
from pathlib import Path
from queue import Queue, Empty
import sys
import tempfile
import unittest
from unittest.mock import Mock
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pc-app"))
from ui.report_filter import normalizar_busqueda
from test_pc_evidence_sync import load_methods, Variable


def functions(path, names, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class AdminApiTests(unittest.TestCase):
    def setUp(self):
        self.http = Mock()
        self.http.exceptions.RequestException = requests.RequestException
        self.response = Mock(ok=True, status_code=200)
        self.response.json.return_value = {"id": "u", "require_password_change": True}
        self.http.request.return_value = self.response
        self.ns = functions(ROOT / "pc-app/api/client.py", {
            "_peticion_catalogo_admin", "_lista_catalogo_admin", "_refrescar_cache_admin",
            "guardar_usuario_admin", "guardar_restaurante_admin", "restablecer_password_admin",
            "cambiar_password_con_mensaje", "obtener_usuarios_admin", "obtener_restaurantes_admin",
        }, {"requests": self.http, "API_BASE_URL": "http://fixture.invalid", "sincronizar_directorio_offline": Mock(), "obtener_usuarios": Mock(), "obtener_restaurantes": Mock()})

    def test_edits_and_status_use_patch_not_delete(self):
        self.ns["guardar_usuario_admin"]({"activo": 0}, "u")
        self.http.request.assert_called_once_with("PATCH", "http://fixture.invalid/usuarios/u", json={"activo": 0}, timeout=10)
        self.ns["sincronizar_directorio_offline"].assert_called_once()

    def test_create_and_restaurant_reactivation_refresh_active_catalogs(self):
        self.ns["guardar_usuario_admin"]({"nombre": "Walter"})
        self.assertEqual(self.http.request.call_args.args[0], "POST")
        self.ns["guardar_restaurante_admin"]({"activo": 1}, "r")
        self.ns["obtener_restaurantes"].assert_called_once()

    def test_local_cache_failure_does_not_report_remote_write_as_failed(self):
        self.ns["sincronizar_directorio_offline"].side_effect = RuntimeError("SQLite ocupado")
        self.assertEqual(self.ns["guardar_usuario_admin"]({"nombre": "Nuevo"}, "u")["id"], "u")
        self.ns["obtener_usuarios"].assert_called_once()

    def test_reset_is_separate_and_requires_server_confirmation(self):
        self.ns["restablecer_password_admin"]("u", "temporal123")
        self.assertIn("/reset-password", self.http.request.call_args.args[1])
        self.response.json.return_value = {"id": "u", "require_password_change": False}
        with self.assertRaisesRegex(RuntimeError, "obligatorio"):
            self.ns["restablecer_password_admin"]("u", "temporal123")

    def test_password_finalization_checks_success(self):
        self.response.json.return_value = {"success": True}
        self.assertTrue(self.ns["cambiar_password_con_mensaje"]("u", "definitiva123"))
        self.assertTrue(self.http.request.call_args.args[1].endswith("/password"))

    def test_duplicate_or_password_error_is_not_misrepresented_as_connection_error(self):
        self.response.ok = False
        self.response.status_code = 409
        self.response.json.return_value = {"message": "Ese usuario ya existe."}
        with self.assertRaisesRegex(RuntimeError, "ya existe"):
            self.ns["guardar_usuario_admin"]({"username": "duplicado"}, "u")

    def test_timeout_is_not_silent_and_does_not_retry_mutation(self):
        self.http.request.side_effect = requests.Timeout()
        with self.assertRaisesRegex(RuntimeError, "No se confirmó"):
            self.ns["guardar_usuario_admin"]({"activo": 0}, "u")
        self.http.request.assert_called_once()

    def test_old_backend_response_does_not_enable_admin(self):
        self.response.json.return_value = None
        with self.assertRaisesRegex(RuntimeError, "backend"):
            self.ns["obtener_usuarios_admin"]()


class CatalogUiTests(unittest.TestCase):
    def test_filters_combine_state_and_name_without_mutation(self):
        ns = functions(ROOT / "pc-app/ui/system_admin_frame.py", {"filtrar_catalogo"}, {"normalizar_busqueda": normalizar_busqueda})
        rows = [{"id": 1, "nombre": "José", "username": "walter", "activo": 1}, {"id": 2, "nombre": "Auditor", "username": "regreso", "activo": 0}]
        self.assertEqual(ns["filtrar_catalogo"](rows, "JOSE wal", "Activos"), [rows[0]])
        self.assertEqual(ns["filtrar_catalogo"](rows, "", "Inactivos"), [rows[1]])
        self.assertEqual(len(rows), 2)

    def test_only_online_admin_can_modify_and_password_validation_matches_backend(self):
        session = Mock()
        klass, _ = load_methods("system_admin_frame.py", "SystemAdminFrame", {"_puede_gestionar", "_validar_password"}, {"session": session})
        frame = klass(); frame._conectado = True
        session.get_role.return_value = "ADMIN"; session.get_session.return_value = {}
        self.assertTrue(frame._puede_gestionar())
        session.get_session.return_value = {"offline_mode": True}
        self.assertFalse(frame._puede_gestionar())
        session.get_session.return_value = {}; session.get_role.return_value = "EMPLEADO"
        self.assertFalse(frame._puede_gestionar())
        for value in ("123", "       ", "á" * 40):
            with self.assertRaises(ValueError): frame._validar_password(value)

    def test_completed_jobs_are_delivered_on_pump_and_stop_when_idle(self):
        klass, _ = load_methods("system_admin_frame.py", "SystemAdminFrame", {"_pump"}, {"Empty": Empty})
        frame = klass(); frame._vivo = True; frame._queue = Queue(); frame._jobs = 1
        callback = Mock(); frame._queue.put((callback, {"id": "u"})); frame.after = Mock()
        frame._pump()
        callback.assert_called_once_with({"id": "u"})
        self.assertEqual(frame._jobs, 0); frame.after.assert_not_called()

    def test_existing_offline_log_keeps_restaurant_uuid_after_rename_or_deactivation(self):
        save = Mock(return_value=8)
        klass, _ = load_methods("bitacoras_frame.py", "BitacorasFrame", {"_asegurar_bitacora_local"}, {"guardar_bitacora_local": save})
        frame = klass(); frame.mapa_restaurantes = {}; frame.mapa_usuarios = {}
        frame.usuario_activo = {"id": "u", "nombre": "Walter"}; frame.fecha_actual = "2026-10-17"
        row = {"restaurante": "Nombre anterior", "restaurante_id": "stable-uuid", "descripcion": "No perder este pendiente"}
        self.assertEqual(frame._asegurar_bitacora_local(row), 8)
        self.assertEqual(save.call_args.args[0]["restaurante_id"], "stable-uuid")

    def test_pump_does_not_duplicate_timer_when_success_starts_another_load(self):
        klass, _ = load_methods("system_admin_frame.py", "SystemAdminFrame", {"_pump"}, {"Empty": Empty})
        frame = klass(); frame._vivo = True; frame._queue = Queue(); frame._jobs = 1; frame.after = Mock()
        def callback(value):
            frame._jobs += 1
            frame._pump_id = "already-scheduled"
        frame._queue.put((callback, None))
        frame._pump()
        frame.after.assert_not_called()

    def test_pending_restaurant_selection_protects_both_name_and_id_from_old_delta(self):
        import threading
        klass, _ = load_methods("bitacoras_frame.py", "BitacorasFrame", {"_actualizar_fila_remota"})
        frame = klass(); frame.lock = threading.Lock(); frame.campos_editando = {}
        frame.filas = [{"restaurante": "Nuevo", "restaurante_id": "new-id", "_campos_pendientes": {"restaurante"}}]
        frame._actualizar_widgets_fila_in_place = Mock()
        frame._actualizar_fila_remota(0, {"restaurante": "Anterior", "restaurante_id": "old-id"})
        self.assertEqual(frame.filas[0]["restaurante_id"], "new-id")
        frame._actualizar_widgets_fila_in_place.assert_not_called()


class OfflineAccountTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        spec = importlib.util.spec_from_file_location("isolated_admin_db", ROOT / "pc-app/db/local_db.py")
        self.db = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.db)
        self.db.RUTA_DB = str(Path(self.folder.name) / "test.db")
        self.db.inicializar_db()

    def tearDown(self): self.folder.cleanup()

    def account(self, username="walter", password="definitiva123", temporary=False):
        salt = b"synthetic-test-salt"
        return {"id": "u", "nombre": "Walter", "username": username, "role": "EMPLEADO", "salt": base64.b64encode(salt).decode(),
                "verifier": base64.b64encode(hashlib.pbkdf2_hmac("sha512", password.encode(), salt, 1000, dklen=32)).decode(), "iterations": 1000, "require_password_change": temporary}

    def test_renaming_and_deactivation_remove_old_offline_login_after_sync(self):
        self.db.actualizar_directorio_offline([self.account()])
        self.assertIsNotNone(self.db.validar_acceso_offline("walter", "definitiva123")[0])
        self.db.actualizar_directorio_offline([self.account(username="walter.nuevo")])
        self.assertIsNone(self.db.validar_acceso_offline("walter", "definitiva123")[0])
        self.assertIsNotNone(self.db.validar_acceso_offline("walter.nuevo", "definitiva123")[0])
        self.db.actualizar_directorio_offline([])
        self.assertIsNone(self.db.validar_acceso_offline("walter.nuevo", "definitiva123")[0])

    def test_reset_blocks_offline_until_permanent_password_is_synced(self):
        self.db.actualizar_directorio_offline([self.account(password="temporal123", temporary=True)])
        self.assertIn("contraseña temporal", self.db.validar_acceso_offline("walter", "temporal123")[1])
        self.db.actualizar_directorio_offline([self.account()])
        self.assertIsNotNone(self.db.validar_acceso_offline("walter", "definitiva123")[0])
        self.assertIsNone(self.db.validar_acceso_offline("walter", "temporal123")[0])


if __name__ == "__main__": unittest.main()
