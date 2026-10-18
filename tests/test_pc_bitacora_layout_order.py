"""Regresiones de orden, reloj y descripción. Nunca usa API ni DB del usuario."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import sys
import threading
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pc-app"))
from core.bitacora_order import clave_orden_bitacora, cursor_bitacoras_servidor, instante_servidor
from ui.auto_height_textbox import AutoHeightTextbox
from test_pc_evidence_sync import load_methods
import customtkinter as ctk


class Card:
    def __init__(self, row): self.row, self.moves = row, 0
    def winfo_exists(self): return True
    def grid_info(self): return {"row": self.row}
    def grid_configure(self, *, row): self.row, self.moves = row, self.moves + 1


def remote(identifier, created, hora="10:00", **extra):
    return {"id": identifier, "created_at": created, "hora": hora,
            "updated_at": "2026-10-17T20:00:00Z", **extra}


class CreationOrderTests(unittest.TestCase):
    def frame(self):
        methods = {"_ordenar_tarjetas_por_creacion", "_aplicar_deltas", "_reconciliar_con_datos", "_actualizar_fila_remota"}
        klass, _ = load_methods("bitacoras_frame.py", "BitacorasFrame", methods,
                                {"clave_orden_bitacora": clave_orden_bitacora})
        frame = klass()
        frame.filas = []
        frame.lock = threading.Lock()
        frame.campos_editando = {}
        frame._cerrado = False
        frame.ultimo_hash_bd = None
        frame._codigo_panel_activo = ""
        frame.after = Mock()
        frame._actualizar_widgets_fila_in_place = Mock()
        frame._construir_tarjeta = lambda idx: frame.filas[idx].update(_card_frame=Card(idx))
        return frame

    def test_sort_ignores_entered_hour_and_last_edit_time(self):
        rows = [remote("new", "2026-10-17T20:00:01Z", "8:55 AM"),
                remote("old", "2026-10-17T20:00:00Z", "1:35 pm", updated_at="2099-01-01T00:00:00Z")]
        self.assertEqual([r["id"] for r in sorted(rows, key=clave_orden_bitacora)], ["old", "new"])
        for r in rows: r["hora"], r["updated_at"] = "23:59", "1900-01-01T00:00:00Z"
        self.assertEqual([r["id"] for r in sorted(reversed(rows), key=clave_orden_bitacora)], ["old", "new"])

    def test_timezone_normalization_and_tied_or_legacy_dates_are_deterministic(self):
        self.assertEqual(instante_servidor("2026-10-17T14:00:00-06:00"), instante_servidor("2026-10-17T20:00:00Z"))
        rows = [remote("b", "2026-10-17T20:00:00Z"), remote("a", "2026-10-17T14:00:00-06:00")]
        self.assertEqual([r["id"] for r in sorted(rows, key=clave_orden_bitacora)], ["a", "b"])
        for r in rows: r.pop("created_at")
        self.assertEqual([r["id"] for r in sorted(rows, key=clave_orden_bitacora)], ["a", "b"])

    def test_initial_load_and_reopening_match_even_if_payload_order_changes(self):
        records = [remote("c", "2026-10-17T20:00:02Z"), remote("a", "2026-10-17T20:00:00Z"), remote("b", "2026-10-17T20:00:01Z")]
        for payload in (records, records[::-1]):
            frame = self.frame()
            frame._reconciliar_con_datos(payload)
            visible = sorted(frame.filas, key=lambda r: r["_card_frame"].row)
            self.assertEqual([r["b_id"] for r in visible], ["a", "b", "c"])

    def test_late_delta_moves_only_cards_not_array_indices_or_controls(self):
        frame = self.frame()
        frame._aplicar_deltas([remote("c", "2026-10-17T20:00:02Z")])
        first = frame.filas[0]
        first["_widgets"] = {"descripcion": Mock()}
        control = first["_widgets"]["descripcion"]
        frame.campos_editando = {0: {"descripcion"}}
        frame._aplicar_deltas([remote("a", "2026-10-17T20:00:00Z")])
        self.assertIs(frame.filas[0], first)
        self.assertIs(first["_widgets"]["descripcion"], control)
        self.assertEqual(first["_card_frame"].row, 1)
        self.assertEqual(frame.campos_editando, {0: {"descripcion"}})
        moves = first["_card_frame"].moves
        frame._aplicar_deltas([remote("c", "2026-10-17T20:00:02Z", updated_at="2026-10-18T20:00:00Z")])
        self.assertEqual(first["_card_frame"].moves, moves)

    def test_delta_matches_inflight_client_id_without_creating_duplicate(self):
        frame = self.frame()
        local = {"b_id": "", "local_id": 7, "client_id": "client-7", "descripcion": "Sigo escribiendo", "_campos_pendientes": {"descripcion"}, "_card_frame": Card(0)}
        frame.filas = [local]
        frame._aplicar_deltas([remote("server-7", "2026-10-17T20:00:02Z", client_id="client-7", descripcion="Versión anterior")])
        self.assertEqual(len(frame.filas), 1)
        self.assertIs(frame.filas[0], local)
        self.assertEqual(local["b_id"], "server-7")
        self.assertEqual(local["descripcion"], "Sigo escribiendo")

    def test_local_pending_rows_follow_remote_rows_in_sqlite_sequence(self):
        rows = [{"local_id": 12}, {"local_id": 8}, {"b_id": "server", "created_at": "2026-10-17T20:00:00Z"}, {}]
        ordered = sorted(enumerate(rows), key=lambda item: clave_orden_bitacora(item[1], item[0]))
        self.assertEqual([i for i, _ in ordered], [2, 1, 0, 3])

    def test_sqlite_pending_queue_does_not_sort_by_pc_clock_or_last_edit(self):
        # Ejecutar la función real contra SQLite :memory:, no borradores.db.
        import ast
        tree = ast.parse((REPO / "pc-app/db/local_db.py").read_text(encoding="utf-8-sig"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "obtener_bitacoras_pendientes")
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE bitacora_pendiente(id INTEGER, pendiente INTEGER, actualizado_en TEXT)")
        conn.executemany("INSERT INTO bitacora_pendiente VALUES (?, ?, ?)", [(2, 1, "1900"), (1, 1, "2099"), (3, 0, "1800")])
        @contextmanager
        def db_session(): yield conn
        env = {"db_session": db_session}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "local_db.py", "exec"), env)
        try: self.assertEqual([r["id"] for r in env[fn.name]()], [1, 2])
        finally: conn.close()


class ServerCursorTests(unittest.TestCase):
    def test_cursor_uses_latest_server_update_not_creation_or_pc_clock(self):
        rows = [remote("a", "2099-01-01T00:00:00Z", updated_at="2026-10-17T20:00:00.123Z"),
                remote("b", "1900-01-01T00:00:00Z", updated_at="2026-10-17T20:00:01.456Z")]
        expected = int(instante_servidor(rows[1]["updated_at"]).timestamp() * 1000) - 1
        with patch("time.time", return_value=9999999999):
            self.assertEqual(cursor_bitacoras_servidor(rows), expected)

    def test_empty_and_repeated_deltas_keep_cursor_without_skipping_same_ms(self):
        rows = [remote("a", "2026-10-17T20:00:00Z")]
        cursor = cursor_bitacoras_servidor(rows)
        self.assertIsNone(cursor_bitacoras_servidor([]))
        self.assertEqual(cursor_bitacoras_servidor([], cursor), cursor)
        self.assertEqual(cursor_bitacoras_servidor(rows, cursor), cursor)
        self.assertEqual(cursor_bitacoras_servidor([{"updated_at": "invalid"}], cursor), cursor)

    def test_polling_uses_server_cursor_with_a_pc_clock_in_the_future(self):
        data = [remote("a", "2026-10-17T20:00:00Z")]
        fetch = Mock(return_value=data)
        delta = Mock(return_value=[])
        klass, _ = load_methods("bitacoras_frame.py", "BitacorasFrame", {"_polling_worker"}, {
            "cursor_bitacoras_servidor": cursor_bitacoras_servidor,
            "obtener_bitacoras_por_fecha": fetch, "obtener_bitacoras_delta": delta,
        })
        frame = klass()
        frame.fecha_actual = "2026-10-17"
        frame._sincronizar_pendientes = Mock()
        frame._reconciliar_con_datos = Mock()
        frame._aplicar_deltas = Mock()
        frame._actualizar_indicador_sync = Mock()
        frame.after = Mock()
        for previous in (None, cursor_bitacoras_servidor(data)):
            frame.timestamp_ultimo_sync = previous
            frame.stop_event = Mock()
            frame.stop_event.is_set.side_effect = [False, False, True]
            with patch("time.time", side_effect=AssertionError("No usar reloj PC")):
                frame._polling_worker()
            self.assertEqual(frame.timestamp_ultimo_sync, cursor_bitacoras_servidor(data))
            frame.stop_event.wait.assert_called_once_with(5)
        fetch.assert_called_once_with("2026-10-17")
        delta.assert_called_once_with("2026-10-17", cursor_bitacoras_servidor(data))


@unittest.skipIf(sys.platform != "win32" and not os.environ.get("DISPLAY"), "Requiere Tk gráfico")
class FlexibleDescriptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        # Ventana QA mapeada para geometría real, pero transparente y sin datos.
        cls.root.attributes("-alpha", 0)
        cls.root.geometry("900x700")
        cls.root.report_callback_exception = lambda *args: cls.errors.append(str(args[1]))
        cls.errors = []
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        for job in cls.root.tk.call("after", "info"):
            cls.root.after_cancel(job)
        cls.root.destroy()

    def setUp(self):
        self.box = AutoHeightTextbox(self.root, width=420, wrap="word", font=("Segoe UI", 13))
        self.box.pack()
        self.addCleanup(self.box.destroy)

    def settle(self):
        for _ in range(4): self.root.update()
        self.assertFalse(self.errors, self.errors)

    def assert_content_fits(self):
        text = self.box._textbox
        pixels = text.count("1.0", "end", "update", "ypixels")
        self.assertGreaterEqual(text.winfo_height(), pixels + int(text.cget("pady")) * 2)
        self.assertIsNotNone(text.dlineinfo("1.0"))
        last = text.dlineinfo("end-1c")
        self.assertIsNotNone(last)
        self.assertLessEqual(last[1] + last[3], text.winfo_height())

    def test_wrapped_multiline_paste_and_remote_replacement_grow_and_shrink(self):
        content = "Descripción con acentos: el área está abierta. " * 18 + "\nSegunda línea.\nÚltima línea."
        self.box.insert("1.0", content)
        self.settle()
        self.assert_content_fits()
        tall = self.box.cget("height")
        self.box.delete("1.0", "end")
        self.box.insert("1.0", "Corto")
        self.settle()
        self.assert_content_fits()
        self.assertLess(self.box.cget("height"), tall)

    def test_resizing_and_both_themes_preserve_text_cursor_and_selection(self):
        content = "Una descripción larga para verificar ajuste al cambiar el ancho. " * 7
        self.box.insert("1.0", content)
        self.box.mark_set("insert", "1.12")
        self.box.tag_add("sel", "1.2", "1.6")
        self.settle()
        wide = self.box.cget("height")
        self.box.configure(width=250)
        self.settle()
        narrow = self.box.cget("height")
        self.assertGreater(narrow, wide)
        for mode in ("Dark", "Light"):
            ctk.set_appearance_mode(mode)
            self.settle()
            self.assert_content_fits()
            self.assertEqual(self.box.get("1.0", "end-1c"), content)
            self.assertEqual(self.box.index("insert"), "1.12")
            self.assertEqual(tuple(map(str, self.box.tag_ranges("sel"))), ("1.2", "1.6"))
        self.box.configure(width=600)
        self.settle()
        self.assertLess(self.box.cget("height"), narrow)

    def test_dpi_scaling_does_not_clip_lines(self):
        self.box.insert("1.0", "Prueba de escala y ajuste de varias líneas. " * 8)
        try:
            for scale in (1, 1.25, 1.5, 2, 1):
                ctk.set_widget_scaling(scale)
                self.settle()
                self.assert_content_fits()
        finally: ctk.set_widget_scaling(1)

    def test_pending_resize_is_cancelled_on_destroy(self):
        box = AutoHeightTextbox(self.root)
        job = box._resize_job
        self.assertIsNotNone(job)
        box.destroy()
        self.assertNotIn(job, self.root.tk.call("after", "info"))

    def test_long_description_uses_outer_table_scroll_not_an_inner_clipped_view(self):
        scroll = ctk.CTkScrollableFrame(self.root, width=600, height=200)
        scroll.pack()
        scroll.grid_columnconfigure(0, weight=1)
        box = AutoHeightTextbox(scroll, wrap="word")
        box.grid(row=0, column=0, sticky="ew")
        box.insert("1.0", "\n".join(f"Línea {i}: descripción completa." for i in range(100)))
        try:
            self.settle()
            self.assertGreater(box.winfo_height(), scroll._parent_canvas.winfo_height())
            self.assertIsNotNone(box._textbox.dlineinfo("end-1c"))
            self.assertEqual(box._textbox.yview(), (0.0, 1.0))
        finally: scroll.destroy()

    def test_no_periodic_scrollbar_poll_per_description(self):
        self.assertIsNone(self.box.after(50, self.box._check_if_scrollbars_needed))
        self.assertFalse(any("_check_if_scrollbars_needed" in command for command in self.box._tclCommands))


if __name__ == "__main__": unittest.main()
