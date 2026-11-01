"""Orden por incorporación: SQLite temporal y UI simulada, nunca datos reales."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc-app"))
from db import local_db as db
from ui.evidence_list import ordenar_evidencias, firma_evidencias
import test_pc_evidence_sync as sync


def remote(identifier, added, sequence=1):
    return {"id": identifier, "agregado_en": added, "secuencia_adicion": str(sequence),
            "evidencia_url": f"http://fixture.invalid/{identifier}.jpg"}


class LocalAdditionOrderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.patcher = patch.object(db, "RUTA_DB", str(Path(self.folder.name) / "fixture.db"))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        db.inicializar_db()

    def test_upload_deletion_and_reopening_never_reuse_the_addition_time(self):
        with patch.object(db.time, "time_ns", return_value=1793556000000000000):
            db.agregar_evidencia(1, "first.jpg", False)
            first = db.obtener_evidencias(1)[0]
            db.eliminar_evidencia_borrador(first["id"])
            db.inicializar_db()  # mismo archivo, como volver a abrir la aplicación
            db.agregar_evidencia(1, "second.jpg", False)
            second = db.obtener_evidencias(1)[0]
        self.assertLess(first["agregado_en"], second["agregado_en"])
        self.assertTrue(second["agregado_en"].endswith("Z"))

    def test_multiple_threads_get_distinct_dates_and_keep_first_to_last(self):
        with patch.object(db.time, "time_ns", return_value=1793556000000000000):
            with ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(lambda n: db.agregar_evidencia(1, f"{n}.jpg", False), range(20)))
        rows = db.obtener_evidencias(1)
        self.assertEqual(len({r["agregado_en"] for r in rows}), 20)
        self.assertEqual([r["id"] for r in rows], sorted(r["id"] for r in rows))
        self.assertEqual(ordenar_evidencias(rows[::-1]), rows)

    def test_bitacora_date_survives_upload_link_and_retry(self):
        identifier = db.agregar_evidencia_bitacora_pendiente("first.jpg", False, "bitacoras/test", b_id="b1", codigo="ABC123")
        first = db.obtener_evidencias_bitacora_pendientes(b_id="b1")[0]
        db.actualizar_url_evidencia_bitacora(identifier, "http://fixture.invalid/first.jpg")
        db.marcar_evidencia_bitacora_vinculada(identifier)
        after = db.obtener_evidencias_bitacora_pendientes(b_id="b1")[0]
        self.assertEqual(first["agregado_en"], after["agregado_en"])
        self.assertEqual(after["vinculada"], 1)

    def test_schema_migration_is_idempotent_and_does_not_date_legacy_rows(self):
        with db.db_session() as conn:
            conn.execute("INSERT INTO evidencia_borrador (reporte_borrador_id,ruta_local,orden_reproduccion) VALUES (1,'legacy.jpg',2)")
        db.inicializar_db()
        self.assertIsNone(db.obtener_evidencias(1)[0]["agregado_en"])


class EvidenceChronologyTests(unittest.TestCase):
    def test_seconds_apart_ignore_uuid_playback_order_and_network_arrival(self):
        first = dict(remote("z-first", "2026-11-01T10:00:00Z", 8), orden_reproduccion=99)
        second = dict(remote("a-second", "2026-11-01T10:00:03Z", 1), orden_reproduccion=0)
        self.assertEqual(ordenar_evidencias([second, first]), [first, second])

    def test_timezone_and_numeric_server_sequence_break_ties(self):
        first = remote("z-first", "2026-11-01T04:00:00-06:00", 2)
        second = remote("a-second", "2026-11-01T10:00:00Z", 10)
        self.assertEqual(ordenar_evidencias([second, first]), [first, second])

    def test_sort_is_pure_and_signature_tracks_order_metadata(self):
        rows = [remote("a", "2026-11-01T10:00:03Z"), remote("z", "2026-11-01T10:00:00Z")]
        before = list(rows)
        ordenar_evidencias(rows)
        self.assertEqual(rows, before)
        self.assertEqual(firma_evidencias(rows), firma_evidencias(rows[::-1]))
        self.assertNotEqual(firma_evidencias(rows), firma_evidencias([dict(rows[0], secuencia_adicion="2"), rows[1]]))

    def test_report_mixed_pending_and_cloud_keeps_position_when_uploaded(self):
        added = "2026-11-01T10:00:00.000Z"
        local = [{"id": 10, "ruta_local": "first.jpg", "agregado_en": added}]
        frame, _ = sync.FrameRegressionTests().report(local)
        frame.evidencias_nube = [remote("a-second", "2026-11-01T10:00:03Z")]
        frame._refrescar_lista_evidencias()
        def visible():
            return [v[2]["nombre"] for v in sorted(frame._lista_evidencias.tarjetas.values(), key=lambda v: v[3])]
        self.assertEqual(visible(), ["first.jpg", "a-second.jpg"])
        stable = frame._lista_evidencias.widgets()[1]
        local.clear()
        frame._agregar_evidencia_remota(remote("first", added, 2))
        self.assertEqual(visible(), ["first.jpg", "a-second.jpg"])
        self.assertIs(frame._lista_evidencias.widgets()[1], stable)

    def test_bitacora_one_mixed_list_keeps_position_and_selection(self):
        added = "2026-11-01T10:00:00.000Z"
        local = [{"id": 10, "ruta_local": "first.jpg", "agregado_en": added}]
        frame, _ = sync.FrameRegressionTests().bitacora(local)
        frame._agregar_chip_evidencia_local = Mock(side_effect=lambda ev, i: sync.Widget())
        frame._mostrar_panel_evidencia("TEST12", [remote("a-second", "2026-11-01T10:00:03Z")])
        def visible():
            return [v[2]["agregado_en"] for v in sorted(frame._lista_ev_tarjetas.tarjetas.values(), key=lambda v: v[3])]
        self.assertEqual(visible(), [added, "2026-11-01T10:00:03Z"])
        stable = frame._lista_ev_tarjetas.widgets()[1]
        stable._descarga[0].set(True)
        local.clear()
        frame._mostrar_panel_evidencia("TEST12", [remote("a-second", "2026-11-01T10:00:03Z"), remote("first", added, 2)])
        self.assertEqual(visible(), [added, "2026-11-01T10:00:03Z"])
        self.assertIs(frame._lista_ev_tarjetas.widgets()[1], stable)
        self.assertTrue(stable._descarga[0].get())

    def test_report_upload_sends_original_addition_date(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "first.jpg"
            path.write_bytes(b"fixture")
            added = "2026-11-01T10:00:00.000Z"
            frame, env = sync.FrameRegressionTests().report([
                {"id": 1, "ruta_local": str(path), "agregado_en": added}])
            env.update(subir_archivo_con_destino=Mock(return_value=("http://fixture.invalid/first.jpg", None)),
                       crear_evidencia_reporte=Mock(return_value=remote("first", added)),
                       eliminar_evidencia_borrador=Mock(), es_archivo_grabado=lambda ruta: False)
            self.assertTrue(frame._subir_evidencias_de_borrador(1, "r1", "reportes/test"))
            self.assertEqual(env["crear_evidencia_reporte"].call_args.args[0]["agregado_en"], added)


if __name__ == "__main__":
    unittest.main()
