"""QA aislada: módulos reales con API/DB/audio reemplazados por fixtures.

--smoke construye las vistas sin mainloop ni tráfico de red. Sin argumentos
abre una ventana de prueba con datos ficticios, nunca la instalación real.
"""
import ast
from pathlib import Path
import sys
import types
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pc-app"))
import customtkinter as ctk
from PIL import Image, ImageDraw
from PIL import ImageColor

for package, child in (("api", "client"), ("db", "local_db")):
    parent = types.ModuleType(package)
    parent.__path__ = []
    module = types.ModuleType(package + "." + child)
    sys.modules[package] = parent
    sys.modules[module.__name__] = module
    setattr(parent, child, module)
    names = set()
    for path in (ROOT / "pc-app/ui").glob("*.py"):
        for item in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(item, ast.ImportFrom) and item.module == module.__name__:
                names.update(alias.name for alias in item.names)
    for name in names:
        setattr(module, name, Mock(return_value=[] if name.startswith(("obtener", "listar")) else None))
    module.API_BASE_URL = "http://fixture.invalid"
    module.normalizar_url = lambda url: url
    module.limpiar_borradores_fantasma = lambda: None

api = sys.modules["api.client"]
user = {"id": "qa-user", "nombre": "Auditor de prueba", "role": "ADMIN"}
restaurant = {"id": "qa-store", "nombre": "Restaurante de prueba"}
api.obtener_usuarios.return_value = [user]
api.obtener_restaurantes.return_value = [restaurant]
keyboard = types.ModuleType("keyboard")
keyboard.add_hotkey = lambda *a, **k: None
keyboard.remove_hotkey = lambda *a, **k: None
keyboard.unhook_all_hotkeys = lambda: None
sys.modules["keyboard"] = keyboard
recorder = types.ModuleType("core.recorder")
recorder.GrabadorPantalla = lambda: types.SimpleNamespace(estado="detenido")
recorder.es_archivo_grabado = lambda path: False
sys.modules[recorder.__name__] = recorder

from ui.theme import initialize_appearance
initialize_appearance()
ctk.set_appearance_mode("Dark")
from ui import theme
from ui.main_window import MainWindow
from ui.selection_frame import SelectionFrame
from ui.reportes_frame import ReportesFrame
from ui.bitacoras_frame import BitacorasFrame
from ui.admin_frame import AdminFrame
from ui.system_admin_frame import SystemAdminFrame
import ui.admin_frame as admin_module
from core.thumbnail_service import MiniaturasUI
import session
session.set_session(user)

# Miniaturas sintéticas, sin HTTP ni archivos de evidencia.
sample = Image.new("RGB", (160, 96), "#283A55")
draw = ImageDraw.Draw(sample)
draw.rectangle((12, 12, 148, 82), outline="#38BDF8", width=2)
draw.line((18, 65, 60, 35, 95, 60, 140, 25), fill="#34D399", width=3)
MiniaturasUI.solicitar = lambda self, source, callback: callback(sample.copy())
ReportesFrame._cargar_datos_setup = lambda self: None
ReportesFrame._polling_directorio_worker = lambda self: None
BitacorasFrame._registrar_hotkeys = lambda self: None
BitacorasFrame._carga_inicial = lambda self: None
BitacorasFrame._iniciar_polling = lambda self: None
SystemAdminFrame._cargar_metricas = lambda self: None

def synthetic_preview(self, source, label):
    image = ctk.CTkImage(light_image=sample.copy(), dark_image=sample.copy(), size=(128, 72))
    label.configure(text="", image=image)
    label.image = image

AdminFrame._cargar_previsualizacion_async = synthetic_preview
app = MainWindow()
if "--smoke" in sys.argv:
    app.withdraw()
app.title("AuditFlow — QA visual (sin API ni datos reales)")
app.geometry("1180x760+50+45")
# Nunca persistir preferencias del usuario durante QA.
theme.set_appearance = lambda mode: ctk.set_appearance_mode(mode)
import ui.main_window as main_module
main_module.set_appearance = theme.set_appearance

evidence = [{"id": str(i), "evidencia_url": f"http://fixture.invalid/evidencia_{i}." + ("jpg" if i % 2 == 0 else "mp4"), "creado_en": "2026-10-16T10:02:00"} for i in range(4)]

def home():
    app.mostrar_frame(SelectionFrame)

def report():
    app.mostrar_frame(ReportesFrame, usuario=user)
    frame = app.frame_actual
    frame.frame_setup.grid_remove()
    frame.titulo_reporte = "Auditoría de prueba — vista de reportes"
    frame.codigo_reporte = "TEST12"
    frame.reporte_remoto_id = "qa-report"
    frame.restaurante = restaurant
    frame.borrador = {"id": 1}
    frame._construir_ui_editor()
    frame.textbox_notas.insert("1.0", "AUDITORÍA DE PRUEBA\n\n10:02 — Se revisan las evidencias de la jornada.\n\nEste texto es ficticio y no se envía a ningún servidor.\n\nEl tema puede cambiar sin perder el texto ni la selección de archivos.")
    frame.evidencias_nube = evidence
    frame._refrescar_lista_evidencias()
    frame._toggle_panel_lateral()
    frame._mostrar_indicador_rec()
    frame.indicador.destroy()
    frame.indicador = None

def logs():
    app.mostrar_frame(BitacorasFrame, usuario=user, fecha="2026-10-16")
    frame = app.frame_actual
    for i in range(3):
        row = {"local_id": i + 1, "b_id": str(i), "codigo": "TEST12", "restaurante": restaurant["nombre"], "hora": "10:02", "descripcion": "Anotación de prueba con evidencia adjunta.", "urgencia": ("leve", "medio", "grave")[i], "evidencias": evidence, "usuario_id": user["id"]}
        frame.filas.append(row)
        frame._construir_tarjeta(i)
    frame._mostrar_panel_evidencia("TEST12", evidence, frame.filas[0])
    frame._mostrar_indicador_rec()
    frame.indicador.destroy()
    frame.indicador = None

def admin():
    app.mostrar_frame(AdminFrame, usuario=user)
    frame = app.frame_actual
    frame._limpiar_container()
    frame._actualizar_top_bar("Detalles de Bitácora (2026-10-16)")
    frame.scroll_filas = ctk.CTkScrollableFrame(frame.container, fg_color="transparent")
    frame.scroll_filas.pack(fill="both", expand=True)
    for i in range(4):
        frame._crear_item_bitacora(frame.scroll_filas, {"id": str(i), "hora": "10:02", "descripcion": "Se revisa el área de atención. Anotación y evidencias de prueba.", "urgencia": ("comentar", "leve", "medio", "grave")[i], "restaurante": restaurant, "usuario": user, "evidencias": evidence})

def admin_dates():
    app.mostrar_frame(AdminFrame, usuario=user)
    frame = app.frame_actual
    # Recibir respuestas de forma determinista, sin threads ni mainloop.
    dates = ["2026-10-16", "2026-10-15T00:00:00.000Z", "2026-10-16", "2026-09-30", "2025-10-16"]
    with patch.object(admin_module.threading, "Thread"):
        frame._abrir_vista_bitacoras()
        original_entry = frame.entry_fecha_bitacoras
        original_scroll = frame.scroll_fechas
        frame.filtro_fecha_bitacoras.set("10/2026")  # Se puede escribir durante la carga.
        frame._mostrar_lista_fechas(original_scroll, dates, original_scroll.winfo_children()[0])
        assert frame._fechas_visibles == ["2026-10-16", "2026-10-15"]
        assert frame.lbl_resultados_fechas.cget("text") == "Fechas: 2 de 4"
        cards = tuple(frame.scroll_fechas.winfo_children())
        frame.filtro_fecha_bitacoras.set("2026-10")
        frame._aplicar_filtro_fechas()
        assert tuple(frame.scroll_fechas.winfo_children()) == cards  # Sin parpadeo.
        for query, expected in (("16/10/2026", ["2026-10-16"]), ("2025", ["2025-10-16"]), ("31/02/2026", [])):
            frame.entry_fecha_bitacoras.delete(0, "end")
            frame.entry_fecha_bitacoras.insert(0, query)
            assert frame._filtro_fecha_after is not None
            frame._aplicar_filtro_fechas()
            assert frame._fechas_visibles == expected, (query, frame._fechas_visibles)
            assert frame.entry_fecha_bitacoras is original_entry
        frame._limpiar_fecha_bitacoras()
        assert len(frame._fechas_visibles) == 4
        frame.filtro_fecha_bitacoras.set("10/2026")
        frame._aplicar_filtro_fechas()
        calls = admin_module.obtener_bitacoras_todas.call_count
        # Simular un clic en la fecha: el filtro no altera el ISO enviado al API.
        frame._abrir_bitacora_dia("2026-10-16")
        assert frame.fecha_seleccionada == "2026-10-16"
        frame._on_back()
        loading = frame.scroll_fechas.winfo_children()[0]
        # Una respuesta de una visita anterior no debe borrar el estado actual.
        frame._mostrar_lista_fechas(original_scroll, [], Mock())
        assert frame._cargando_fechas
        frame._mostrar_lista_fechas(frame.scroll_fechas, dates, loading)
        assert frame.filtro_fecha_bitacoras.get() == "10/2026"
        assert frame._fechas_visibles == ["2026-10-16", "2026-10-15"]
        assert admin_module.obtener_bitacoras_todas.call_count == calls

def admin_date_calendar():
    admin_dates()
    frame = app.frame_actual
    frame.filtro_fecha_bitacoras.set("15/10/2026")
    frame._aplicar_filtro_fechas()
    frame._elegir_fecha_bitacoras()
    import tkcalendar
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    app._qa_calendar = next(c for c in descendants(frame) if isinstance(c, tkcalendar.Calendar))
    assert str(app._qa_calendar.selection_get()) == "2026-10-15"
    # Probar selección y botón Buscar, no sólo la construcción del diálogo.
    from datetime import date
    app._qa_calendar.selection_set(date(2026, 9, 30))
    button = next(c for c in descendants(frame) if isinstance(c, ctk.CTkButton) and c.cget("text") == "Buscar")
    button.invoke()
    assert frame.filtro_fecha_bitacoras.get() == "30/09/2026"
    assert frame._fechas_visibles == ["2026-09-30"]
    frame._elegir_fecha_bitacoras()
    app._qa_calendar = next(c for c in descendants(frame) if isinstance(c, tkcalendar.Calendar))

def viewer():
    if not isinstance(app.frame_actual, AdminFrame):
        app.mostrar_frame(AdminFrame, usuario=user)
    app.frame_actual._mostrar_popup_evidencias([{"url": e["evidencia_url"], "id": e["id"]} for e in evidence], "2026-10-16", "Prueba")

def system_admin():
    app.mostrar_frame(SystemAdminFrame)

def calendar():
    home()
    app.frame_actual._abrir_calendario()
    import tkcalendar
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    app._qa_calendar = next(c for c in descendants(app) if isinstance(c, tkcalendar.Calendar))

toolbar = ctk.CTkFrame(app.appearance_bar, fg_color="transparent")
toolbar.pack(side="left", padx=10)
for name, callback in (("Inicio QA", home), ("Reportes QA", report), ("Bitácoras QA", logs), ("Administrar QA", admin_dates), ("Visor QA", viewer)):
    ctk.CTkButton(toolbar, text=name, command=callback, width=100, height=24).pack(side="left", padx=2)
if "--smoke" in sys.argv:
    errors = []
    app.report_callback_exception = lambda *args: errors.append(str(args[1]))
    screens = [home, report, logs, admin, admin_dates, viewer, system_admin]
    try:
        import tkcalendar
        screens.extend([calendar, admin_date_calendar])
    except ImportError:
        pass
    for screen in screens:
        screen()
        original_frame = app.frame_actual
        has_calendar = screen in (calendar, admin_date_calendar)
        selected_date = app._qa_calendar.selection_get() if has_calendar else None
        has_date_filter = screen in (admin_dates, admin_date_calendar)
        if has_date_filter:
            date_query = original_frame.filtro_fecha_bitacoras.get()
            date_cards = tuple(original_frame.scroll_fechas.winfo_children())
        for mode in ("Light", "Dark", "Light", "Dark"):
            ctk.set_appearance_mode(mode)
            app._toggle_appearance()
            app._toggle_appearance()
            assert app.frame_actual is original_frame
            if has_calendar:
                assert app._qa_calendar.selection_get() == selected_date
            if has_date_filter:
                assert original_frame.filtro_fecha_bitacoras.get() == date_query
                assert tuple(original_frame.scroll_fechas.winfo_children()) == date_cards
            app.update_idletasks()
            if "--contrast" in sys.argv:
                from test_pc_appearance import contrast
                def inspect_colors(widget):
                    if isinstance(widget, (ctk.CTkLabel, ctk.CTkButton)) and widget.winfo_manager():
                        text = widget.cget("text")
                        if text or getattr(widget, "_visual_icon", None):
                            color = theme.resolve_color(widget.cget("text_color"))
                            parent = widget
                            background = "transparent"
                            while background == "transparent" and parent is not None:
                                try: background = theme.resolve_color(parent.cget("fg_color"))
                                except Exception: pass
                                parent = parent.master
                            if background != "transparent":
                                def hex_color(value): return "#%02x%02x%02x" % ImageColor.getrgb(value)
                                ratio = contrast(hex_color(color), hex_color(background))
                                if ratio < 4.5:
                                    print("CONTRAST", screen.__name__, ctk.get_appearance_mode(), repr(text), color, background, round(ratio, 2))
                                if isinstance(widget, ctk.CTkButton):
                                    hover = theme.resolve_color(widget.cget("hover_color"))
                                    if hover and hover != "transparent":
                                        ratio = contrast(hex_color(color), hex_color(hover))
                                        if ratio < 4.5:
                                            print("CONTRAST hover", screen.__name__, ctk.get_appearance_mode(), repr(text), color, hover, round(ratio, 2))
                    for child in widget.winfo_children(): inspect_colors(child)
                inspect_colors(app)
        for child in list(app.winfo_children()):
            if isinstance(child, ctk.CTkToplevel):
                child.destroy()
    assert not errors, errors
    app.destroy()
    print("Full UI smoke OK:", len(screens), "screens; both themes.")
else:
    home()
    app.after(900000, app.destroy)
    app.mainloop()
