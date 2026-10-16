"""Filtro de fechas de Administración: sin API, DB ni ventanas reales."""
from datetime import datetime
import unittest
from unittest.mock import Mock

from test_pc_evidence_sync import Variable, load_methods


class AdminDateFilterTests(unittest.TestCase):
    def setUp(self):
        methods = ["_fecha_coincide", "_programar_filtro_fechas", "_cancelar_filtro_fecha",
                   "_mostrar_lista_fechas", "_aplicar_filtro_fechas"]
        probe, _ = load_methods("admin_frame.py", "AdminFrame", methods, {"datetime": datetime})
        self.frame = probe()
        self.frame.vista_actual = "BITACORAS"
        self.frame._cargando_fechas = False
        self.frame._filtro_fecha_after = None
        self.frame.after_cancel = Mock()
        self.frame.after = Mock(side_effect=["after-1", "after-2", "after-3"])

    def test_iso_localized_dates_month_and_year(self):
        for query in ("2026-10-16", "16/10/2026", "16-10-2026", "10/2026", "2026-10", "2026", " 16 / 10 / 2026 ", ""):
            with self.subTest(query=query):
                self.assertTrue(self.frame._fecha_coincide("2026-10-16", query))
        for query in ("2025", "15/10/2026", "31/02/2026", "09/2026", "abc"):
            with self.subTest(query=query):
                self.assertFalse(self.frame._fecha_coincide("2026-10-16", query))

    def test_invalid_dates_and_leap_year(self):
        for date in (None, "", "garbage", "2026-02-29"):
            self.assertFalse(self.frame._fecha_coincide(date, ""))
        self.assertTrue(self.frame._fecha_coincide("2024-02-29", "29/02/2024"))

    def test_unpadded_dates_do_not_match_other_days_or_months(self):
        for query in ("1/1/2026", "2026-1-1", "1/2026", "2026-1"):
            with self.subTest(query=query):
                self.assertTrue(self.frame._fecha_coincide("2026-01-01", query))
                self.assertFalse(self.frame._fecha_coincide("2026-11-11", query))
        self.assertFalse(self.frame._fecha_coincide("2026-10-11", "1/10/2026"))

    def test_typing_is_debounced_without_http(self):
        self.frame._programar_filtro_fechas()
        self.frame._programar_filtro_fechas()
        self.assertEqual(self.frame.after.call_count, 2)
        self.frame.after.assert_called_with(180, self.frame._aplicar_filtro_fechas)
        self.frame.after_cancel.assert_called_once_with("after-1")
        self.assertEqual(self.frame._filtro_fecha_after, "after-2")
        self.frame._cancelar_filtro_fecha()
        self.assertIsNone(self.frame._filtro_fecha_after)

    def test_no_timer_while_loading_or_on_another_view(self):
        self.frame._cargando_fechas = True
        self.frame._programar_filtro_fechas()
        self.frame._cargando_fechas = False
        self.frame.vista_actual = "ROOT"
        self.frame._programar_filtro_fechas()
        self.frame.after.assert_not_called()

    def test_response_sorts_deduplicates_and_keeps_day_without_timezone_conversion(self):
        parent, loading = Mock(), Mock()
        self.frame.scroll_fechas = parent
        self.frame._aplicar_filtro_fechas = Mock()
        self.frame._mostrar_lista_fechas(parent, ["2026-10-15T23:00:00-06:00", "2026-10-16", "2026-10-15", "2025-12-31"], loading)
        self.assertEqual(self.frame._fechas_bitacoras, ["2026-10-16", "2026-10-15", "2025-12-31"])
        loading.destroy.assert_called_once_with()
        self.frame._aplicar_filtro_fechas.assert_called_once_with()

    def test_stale_responses_do_not_touch_widgets_or_cache(self):
        current, old, loading = Mock(), Mock(), Mock()
        self.frame.scroll_fechas = current
        self.frame._aplicar_filtro_fechas = Mock()
        self.frame._mostrar_lista_fechas(old, ["2026-10-16"], loading)
        self.frame.vista_actual = "BITACORA_DIA"
        self.frame._mostrar_lista_fechas(current, ["2026-10-16"], loading)
        self.frame.vista_actual = "BITACORAS"
        current.winfo_exists.return_value = False
        self.frame._mostrar_lista_fechas(current, [], loading)
        loading.destroy.assert_not_called()
        self.frame._aplicar_filtro_fechas.assert_not_called()

    def test_equivalent_searches_do_not_rebuild_cards(self):
        self.frame.filtro_fecha_bitacoras = Variable("10/2026")
        self.frame._fechas_bitacoras = ["2026-10-16", "2026-09-30"]
        self.frame._fechas_visibles = ["2026-10-16"]
        self.frame.lbl_resultados_fechas = Mock()
        self.frame.scroll_fechas = Mock()
        self.frame._aplicar_filtro_fechas()
        self.frame.lbl_resultados_fechas.configure.assert_called_with(text="Fechas: 1 de 2")
        self.frame.scroll_fechas.winfo_children.assert_not_called()


if __name__ == "__main__":
    unittest.main()
