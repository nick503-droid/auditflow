"""Renombrado con control de versión; no hay API ni datos reales."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
import types
import requests

REPO = Path(__file__).resolve().parents[1]


class RenameTests(unittest.TestCase):
    def helper(self, states, responses):
        tree = ast.parse((REPO / "pc-app/api/client.py").read_text(encoding="utf-8-sig"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "renombrar_reporte_remoto")
        patch = Mock(side_effect=responses)
        get = Mock(side_effect=states)
        scope = {"obtener_reporte": get, "API_BASE_URL": "http://fixture.invalid",
                 "requests": types.SimpleNamespace(patch=patch, exceptions=requests.exceptions)}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "client.py", "exec"), scope)
        return scope[fn.name], get, patch

    def response(self, status=200, title="Nuevo", version=2):
        return types.SimpleNamespace(status_code=status, raise_for_status=Mock(),
                                     json=lambda: {"id": "r1", "titulo": title, "version": version})

    def test_new_report_without_version_in_list_sends_current_server_version(self):
        rename, _, patch = self.helper([{"titulo": "Original", "version": 1}], [self.response()])
        self.assertEqual(rename("r1", " Nuevo ", titulo_original="Original")["titulo"], "Nuevo")
        self.assertEqual(patch.call_args.kwargs["json"], {"titulo": "Nuevo", "version": 1})

    def test_notes_changed_since_list_do_not_cause_false_title_conflict(self):
        rename, _, patch = self.helper([{"titulo": "Original", "version": 8, "notas_finales": "Notas nuevas"}], [self.response()])
        self.assertEqual(rename("r1", "Nuevo", 1, "Original")["titulo"], "Nuevo")
        self.assertEqual(patch.call_args.kwargs["json"], {"titulo": "Nuevo", "version": 8})

    def test_concurrent_notes_save_is_retried_without_sending_notes(self):
        rename, _, patch = self.helper([{"titulo": "Original", "version": 1}, {"titulo": "Original", "version": 2}],
                                       [self.response(409), self.response(version=3)])
        self.assertEqual(rename("r1", "Nuevo", 1, "Original")["version"], 3)
        self.assertEqual([c.kwargs["json"] for c in patch.call_args_list],
                         [{"titulo": "Nuevo", "version": 1}, {"titulo": "Nuevo", "version": 2}])

    def test_other_pc_renamed_before_save_requires_user_review(self):
        rename, _, patch = self.helper([{"titulo": "Nombre de otra PC", "version": 2}], [])
        result = rename("r1", "Mi nombre", 1, "Original")
        self.assertTrue(result["__conflict__"])
        self.assertEqual(result["actual"]["titulo"], "Nombre de otra PC")
        patch.assert_not_called()

    def test_other_pc_renamed_during_save_is_not_overwritten_after_409(self):
        rename, _, patch = self.helper([{"titulo": "Original", "version": 1}, {"titulo": "Otro", "version": 2}], [self.response(409)])
        self.assertTrue(rename("r1", "Nuevo", 1, "Original")["__conflict__"])
        self.assertEqual(patch.call_count, 1)

    def test_lost_response_retry_is_idempotent(self):
        rename, _, patch = self.helper([{"titulo": "Nuevo", "version": 2}], [])
        self.assertEqual(rename("r1", "Nuevo", 1, "Original")["version"], 2)
        patch.assert_not_called()

    def test_network_failure_missing_version_and_blank_name_do_not_write(self):
        for state in (None, {"titulo": "Original"}):
            rename, _, patch = self.helper([state], [])
            self.assertIsNone(rename("r1", "Nuevo"))
            patch.assert_not_called()
        rename, get, patch = self.helper([], [])
        self.assertIsNone(rename("r1", "  "))
        get.assert_not_called()
        patch.assert_not_called()

    def test_busy_report_has_bounded_retries(self):
        rename, get, patch = self.helper([{"titulo": "Original", "version": v} for v in range(1, 4)], [self.response(409) for _ in range(3)])
        self.assertTrue(rename("r1", "Nuevo", titulo_original="Original")["__conflict__"])
        self.assertEqual(patch.call_count, 3)


if __name__ == "__main__":
    unittest.main()
