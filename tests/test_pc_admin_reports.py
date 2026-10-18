"""Búsqueda de Administración: sin conexiones ni datos reales."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc-app"))
from ui.report_filter import TODOS_RESTAURANTES, filtrar_reportes_admin, nombre_restaurante_reporte, normalizar_busqueda
from test_pc_evidence_sync import Variable, load_methods


class ReportSearchTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"r1": "Norco", "r2": "San Bernardino"}
        self.rows = [
            ({"id": 1, "titulo": "Auditoría pendiente — carnes", "restaurante_id": "r1"}, True),
            ({"id": "a", "titulo": "Auditoría del área de cocina", "restaurante": {"id": "r1", "nombre": "Norco"}}, False),
            ({"id": "b", "titulo": "Inspección de cierre", "restaurante_id": "r2"}, False),
            ({"id": "c", "titulo": "Cierre de cocina", "restaurante": {"nombre": "Norco Norte"}}, False),
        ]

    def test_all_records_keep_original_order_and_do_not_mutate_data(self):
        original = deepcopy(self.rows)
        self.assertEqual(filtrar_reportes_admin(self.rows, "", TODOS_RESTAURANTES, self.catalog), self.rows)
        self.assertEqual(self.rows, original)

    def test_name_search_ignores_accents_case_and_word_order(self):
        rows = filtrar_reportes_admin(self.rows, "  AREA   auditoria ", TODOS_RESTAURANTES, self.catalog)
        self.assertEqual([r["id"] for r, _ in rows], ["a"])
        self.assertEqual(normalizar_busqueda("  INSPECCIÓN  "), "inspeccion")

    def test_restaurant_matches_both_cloud_relation_and_local_catalog_id(self):
        rows = filtrar_reportes_admin(self.rows, "", "NORCO", self.catalog)
        self.assertEqual([r["id"] for r, _ in rows], [1, "a"])
        self.assertEqual([local for _, local in rows], [True, False])

    def test_filters_combine_with_and_not_or(self):
        self.assertEqual(filtrar_reportes_admin(self.rows, "cierre", "Norco", self.catalog), [])
        rows = filtrar_reportes_admin(self.rows, "cierre", "San Bernardino", self.catalog)
        self.assertEqual([r["id"] for r, _ in rows], ["b"])

    def test_missing_or_legacy_restaurant_does_not_crash(self):
        for data, expected in (
            ({"restaurante": None, "restaurante_id": "r1"}, "Norco"),
            ({"restaurante": {"id": "r2"}}, "San Bernardino"),
            ({"restaurante": "  Riverside "}, "Riverside"),
            ({"restaurante_nombre": "Covina"}, "Covina"),
            ({"restaurante": None, "restaurante_id": "missing"}, "Restaurante no disponible"),
        ):
            with self.subTest(data=data):
                self.assertEqual(nombre_restaurante_reporte(data, self.catalog), expected)
        self.assertEqual(filtrar_reportes_admin([({}, True)], "sin titulo", "", {}), [({}, True)])
        self.assertEqual(nombre_restaurante_reporte({"restaurante_id": "r1"}, {"r1": "  "}), "Restaurante no disponible")


class ReportFilterStateTests(unittest.TestCase):
    def setUp(self):
        methods = {"_programar_filtros_reportes", "_cancelar_filtros_reportes", "_mostrar_lista_reportes", "_aplicar_filtros_reportes"}
        klass, _ = load_methods("admin_frame.py", "AdminFrame", methods, {
            "TODOS_RESTAURANTES": TODOS_RESTAURANTES,
            "filtrar_reportes_admin": filtrar_reportes_admin,
            "nombre_restaurante_reporte": nombre_restaurante_reporte,
            "normalizar_busqueda": normalizar_busqueda,
        })
        self.frame = klass()
        self.frame.vista_actual = "REPORTES"
        self.frame._cargando_reportes = False
        self.frame._filtro_reportes_after = None
        self.frame.after_cancel = Mock()
        self.frame.after = Mock(side_effect=["after-1", "after-2"])
        self.frame.scroll_reportes = Mock()

    def test_typing_is_debounced_and_cancelled_when_leaving(self):
        self.frame._programar_filtros_reportes()
        self.frame._programar_filtros_reportes()
        self.frame.after_cancel.assert_called_once_with("after-1")
        self.frame.after.assert_called_with(180, self.frame._aplicar_filtros_reportes)
        self.frame._cancelar_filtros_reportes()
        self.assertIsNone(self.frame._filtro_reportes_after)

    def test_no_filter_jobs_while_loading_or_in_another_view(self):
        self.frame._cargando_reportes = True
        self.frame._programar_filtros_reportes()
        self.frame._cargando_reportes = False
        self.frame.vista_actual = "REPORTE_DETALLE"
        self.frame._programar_filtros_reportes()
        self.frame.after.assert_not_called()

    def test_stale_async_results_are_ignored(self):
        loading = Mock()
        self.frame._aplicar_filtros_reportes = Mock()
        self.frame._mostrar_lista_reportes(Mock(), [], [], loading)
        self.frame.vista_actual = "ROOT"
        self.frame._mostrar_lista_reportes(self.frame.scroll_reportes, [], [], loading)
        self.frame.vista_actual = "REPORTES"
        self.frame.scroll_reportes.winfo_exists.return_value = False
        self.frame._mostrar_lista_reportes(self.frame.scroll_reportes, [], [], loading)
        loading.destroy.assert_not_called()
        self.frame._aplicar_filtros_reportes.assert_not_called()

    def test_loaded_restaurant_choices_include_local_drafts_and_preserve_selection(self):
        cloud = [{"id": "a", "restaurante": {"nombre": "Norco"}}]
        local = [{"id": 1, "restaurante_id": "r2"}]
        self.frame.restaurantes_dict = {"r2": "Covina"}
        self.frame.filtro_restaurante_reporte = Variable("Riverside")
        self.frame.menu_restaurante_reporte = Mock()
        self.frame._aplicar_filtros_reportes = Mock()
        self.frame._mostrar_lista_reportes(self.frame.scroll_reportes, cloud, local, Mock())
        self.assertEqual(self.frame._reportes_admin, [(local[0], True), (cloud[0], False)])
        self.frame.menu_restaurante_reporte.configure.assert_called_with(values=[TODOS_RESTAURANTES, "Covina", "Norco", "Riverside"])
        self.assertEqual(self.frame.filtro_restaurante_reporte.get(), "Riverside")
        self.assertFalse(self.frame._cargando_reportes)

    def test_equivalent_filters_do_not_recreate_cards(self):
        record = {"id": 1, "titulo": "Auditoría", "restaurante_id": "r1"}
        self.frame._reportes_admin = [(record, True)]
        self.frame._reportes_visibles = ((True, 1),)
        self.frame.restaurantes_dict = {"r1": "Norco"}
        self.frame.filtro_nombre_reporte = Variable("AUDITORIA")
        self.frame.filtro_restaurante_reporte = Variable("Norco")
        self.frame.lbl_resultados_reportes = Mock()
        self.frame._crear_item_reporte = Mock()
        self.frame._aplicar_filtros_reportes()
        self.frame.lbl_resultados_reportes.configure.assert_called_with(text="Reportes: 1 de 1")
        self.frame.scroll_reportes.winfo_children.assert_not_called()
        self.frame._crear_item_reporte.assert_not_called()


if __name__ == "__main__": unittest.main()
