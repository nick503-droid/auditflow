"""QA aislada: módulos reales con API/DB/audio reemplazados por fixtures.

--smoke construye las vistas sin mainloop ni tráfico de red. --inspect deja
abierta Administración con datos ficticios; nunca abre la instalación real.
"""
import ast
from pathlib import Path
import sys
import types
from copy import deepcopy
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
user = {"id": "qa-user", "nombre": "Administrador de prueba", "username": "admin.demo", "role": "ADMIN", "activo": 1, "require_password_change": False}
restaurant = {"id": "qa-store", "nombre": "Restaurante de prueba"}
restaurant_other = {"id": "qa-store-2", "nombre": "Norco"}
api.obtener_usuarios.return_value = [user]
api.obtener_restaurantes.return_value = [restaurant, restaurant_other]

# CRUD de demostración exclusivamente en memoria. No importa API/SQLite reales.
qa_users = [deepcopy(user), {"id": "qa-walter", "nombre": "Walter de prueba", "username": "walter.demo", "role": "EMPLEADO", "activo": 1, "require_password_change": False},
            {"id": "qa-inactive", "nombre": "Auditor que regresa", "username": "regreso.demo", "role": "EMPLEADO", "activo": 0, "require_password_change": True}]
qa_restaurants = [{**restaurant, "activo": 1}, {**restaurant_other, "activo": 1}, {"id": "qa-closed", "nombre": "Sucursal temporalmente cerrada", "activo": 0}]
qa_passwords = {"qa-user": "demo123", "qa-walter": "demo123", "qa-inactive": "temporal123"}

def qa_save(rows, dto, identifier=None):
    row = next((r for r in rows if r["id"] == identifier), None) if identifier else None
    if identifier and row is None:
        raise RuntimeError("Registro de prueba no encontrado.")
    if rows is qa_users:
        username = dto.get("username", (row or {}).get("username"))
        if username and any(r["id"] != identifier and (r.get("username") or "").casefold() == username.casefold() for r in rows):
            raise RuntimeError("Ese usuario de inicio de sesión ya existe, incluso si está inactivo.")
        next_row = {**(row or {}), **dto}
        if row and row.get("role") == "ADMIN" and row.get("activo", 1) and (not next_row.get("activo", 1) or next_row.get("role") != "ADMIN"):
            if not any(r["id"] != identifier and r.get("role") == "ADMIN" and r.get("activo", 1) for r in rows):
                raise RuntimeError("No puedes desactivar al último administrador activo.")
    if row is None:
        row = {"id": f"qa-new-{len(rows)}", "activo": 1, "role": "EMPLEADO", "require_password_change": True}
        rows.append(row)
    changes = dict(dto)
    password = changes.pop("password", None)
    row.update(changes)
    if password:
        qa_passwords[row["id"]] = password
        row["require_password_change"] = True
    return deepcopy(row)

def qa_reset(identifier, password):
    return qa_save(qa_users, {"password": password}, identifier)

def qa_login(username, password):
    return next((deepcopy(r) for r in qa_users if r.get("activo", 1) and r.get("username") == username and qa_passwords.get(r["id"]) == password), None)

def qa_change_password(identifier, password):
    row = next(r for r in qa_users if r["id"] == identifier)
    if not row.get("activo", 1):
        raise RuntimeError("Cuenta de prueba inactiva.")
    if row.get("require_password_change") and qa_passwords.get(identifier) == password:
        raise RuntimeError("La contraseña nueva debe ser diferente de la temporal.")
    qa_passwords[identifier] = password
    row["require_password_change"] = False
    return True

api.obtener_usuarios_admin.side_effect = lambda: deepcopy(qa_users)
api.obtener_restaurantes_admin.side_effect = lambda: deepcopy(qa_restaurants)
api.guardar_usuario_admin.side_effect = lambda dto, identifier=None: qa_save(qa_users, dto, identifier)
api.guardar_restaurante_admin.side_effect = lambda dto, identifier=None: qa_save(qa_restaurants, dto, identifier)
api.restablecer_password_admin.side_effect = qa_reset
# login_frame importa estos nombres dentro de métodos: la recolección AST los incluye.
api.login.side_effect = qa_login
api.cambiar_password_con_mensaje.side_effect = qa_change_password
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
from ui.visual_widgets import IconLabel
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
qa_real_initial_load = BitacorasFrame._carga_inicial
BitacorasFrame._carga_inicial = lambda self: None
BitacorasFrame._iniciar_polling = lambda self: None
SystemAdminFrame._cargar_metricas = lambda self: self._actualizar_dashboard("Servidor de prueba · sin API", "48 GB", "256 GB", "208 GB", .19)
def qa_submit(self, operation, success, failure):
    try:
        result = operation()
    except Exception as error:
        failure(str(error))
    else:
        success(result)
SystemAdminFrame._submit = qa_submit

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
sample_reports = [
    {"id": "qa-report", "titulo": "Auditoría de prueba — revisión del área de atención", "fecha_jornada": "2026-10-17", "restaurante": restaurant, "evidencias": evidence},
    {"id": "qa-report-2", "titulo": "Inspección de cierre — ejemplo sin datos reales", "fecha_jornada": "2026-10-16", "restaurante": restaurant_other, "evidencias": evidence[:2]},
]
sample_local_reports = [{"id": 7, "titulo": "Auditoría pendiente — revisión", "restaurante_id": restaurant["id"], "fecha_jornada": "2026-10-17"}]
api.obtener_reportes.return_value = sample_reports

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

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


def loading_logs():
    """Carga real de la UI con respuesta ficticia retenida para inspección."""
    import threading
    import ui.bitacoras_frame as module
    release = threading.Event()
    records = [
        {"id": f"qa-log-{i}", "codigo": f"QA{i:04d}", "hora": f"{8 + i // 4}:15 AM",
         "descripcion": ("Bitácora ficticia: revisión del área de atención y de las evidencias. " * (i % 3 + 1)),
         "restaurante": restaurant if i % 2 else restaurant_other, "usuario": user,
         "urgencia": "leve", "evidencias": [],
         "created_at": f"2026-10-23T14:{i:02d}:00Z", "updated_at": f"2026-10-23T14:{i:02d}:00Z"}
        for i in range(40)
    ]
    def fetch_fixture(date):
        while not release.wait(1):
            if frame._cerrado:
                return []
        return deepcopy(records)
    module.obtener_bitacoras_por_fecha = fetch_fixture
    app.mostrar_frame(BitacorasFrame, usuario=user, fecha="2026-10-23")
    frame = app.frame_actual
    qa_real_initial_load(frame)
    ctk.CTkLabel(frame._carga_overlay,
                 text="DEMO: carga pausada para inspeccionar. No hay conexión al servidor.",
                 wraplength=650).pack(pady=(8, 4))
    ctk.CTkButton(frame._carga_overlay, text="Mostrar las 40 bitácoras de prueba",
                  command=release.set).pack(pady=8)

def admin():
    app.mostrar_frame(AdminFrame, usuario=user)
    frame = app.frame_actual
    frame._limpiar_container()
    frame._actualizar_top_bar("Detalles de Bitácora (2026-10-16)")
    frame.scroll_filas = ctk.CTkScrollableFrame(frame.container, fg_color="transparent")
    frame.scroll_filas.pack(fill="both", expand=True)
    for i in range(4):
        frame._crear_item_bitacora(frame.scroll_filas, {"id": str(i), "hora": "10:02", "descripcion": "Se revisa el área de atención. Anotación y evidencias de prueba.", "urgencia": ("comentar", "leve", "medio", "grave")[i], "restaurante": restaurant, "usuario": user, "evidencias": evidence})

def admin_reports():
    app.mostrar_frame(AdminFrame, usuario=user)
    frame = app.frame_actual
    with patch.object(admin_module.threading, "Thread"):
        frame._abrir_vista_reportes()
    scroll = next(w for w in descendants(frame.container) if isinstance(w, ctk.CTkScrollableFrame))
    frame._mostrar_lista_reportes(scroll, sample_reports, sample_local_reports, scroll.winfo_children()[0])

def admin_report_search():
    admin_reports()
    frame = app.frame_actual
    entry = frame.entry_nombre_reporte
    scroll = frame.scroll_reportes
    frame.filtro_nombre_reporte.set("REVISION")
    frame._aplicar_filtros_reportes()
    assert frame.lbl_resultados_reportes.cget("text") == "Reportes: 2 de 3"
    cards = tuple(scroll.winfo_children())
    frame.filtro_nombre_reporte.set("Revisión")
    frame._aplicar_filtros_reportes()
    assert tuple(scroll.winfo_children()) == cards
    frame.filtro_restaurante_reporte.set("Norco")
    frame._aplicar_filtros_reportes()
    assert frame.lbl_resultados_reportes.cget("text") == "Reportes: 0 de 3"
    assert scroll.winfo_children()[0].cget("text") == "No hay reportes que coincidan con la búsqueda."
    frame.filtro_nombre_reporte.set("cierre")
    frame._aplicar_filtros_reportes()
    assert frame.lbl_resultados_reportes.cget("text") == "Reportes: 1 de 3"
    assert frame.entry_nombre_reporte is entry
    calls = admin_module.obtener_reportes.call_count
    frame._abrir_reporte_detalle({**sample_reports[1], "evidencias": []}, False)
    with patch.object(admin_module.threading, "Thread"):
        frame._on_back()
    loading = frame.scroll_reportes.winfo_children()[0]
    frame._mostrar_lista_reportes(scroll, [], [], Mock())  # Respuesta de la vista anterior.
    assert frame._cargando_reportes
    frame._mostrar_lista_reportes(frame.scroll_reportes, sample_reports, sample_local_reports, loading)
    assert frame.filtro_nombre_reporte.get() == "cierre"
    assert frame.filtro_restaurante_reporte.get() == "Norco"
    assert frame.lbl_resultados_reportes.cget("text") == "Reportes: 1 de 3"
    frame._limpiar_filtros_reportes()
    assert frame.lbl_resultados_reportes.cget("text") == "Reportes: 3 de 3"
    assert admin_module.obtener_reportes.call_count == calls  # Ninguna petición por filtrar.

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
    session.set_session(deepcopy(user))
    app.mostrar_frame(SystemAdminFrame)

def demo_login():
    from ui.login_frame import LoginFrame
    app.mostrar_frame(LoginFrame)

def system_admin_dialogs():
    system_admin()
    frame = app.frame_actual
    # Construir formularios reales, sin peticiones ni tocar preferencias/datos reales.
    for tipo, row in (("usuarios", None), ("usuarios", qa_users[1]), ("restaurantes", None), ("restaurantes", qa_restaurants[0])):
        dialog = frame._popup_editar(tipo, row)
        app.update_idletasks()
        assert dialog.winfo_exists()
        dialog.destroy()
    dialog = frame._popup_password(qa_users[1])
    app.update_idletasks()
    dialog.destroy()
    for state, count in (("Todos", 3), ("Activos", 2), ("Inactivos", 1)):
        frame._vistas["usuarios"]["estado"].set(state)
        frame._render_catalogo("usuarios")
        assert frame._vistas["usuarios"]["count"].cget("text") == f"{count} de 3 registros"
    frame._vistas["usuarios"]["estado"].set("Todos")
    frame._render_catalogo("usuarios")

def system_admin_mutations():
    backup = deepcopy((qa_users, qa_restaurants, qa_passwords))
    try:
        system_admin()
        frame = app.frame_actual
        def fill_and_save(dialog, values):
            entries = [c for c in descendants(dialog) if isinstance(c, ctk.CTkEntry)]
            assert len(entries) == len(values)
            for entry, value in zip(entries, values):
                entry.delete(0, "end"); entry.insert(0, value)
            save = next(c for c in descendants(dialog) if isinstance(c, ctk.CTkButton) and c.cget("text") == "Guardar")
            save.invoke()
            assert not dialog.winfo_exists(), "El formulario válido debe cerrar después de guardar"
        fill_and_save(frame._popup_editar("usuarios"), ["Auditor nuevo", "nuevo.demo", "temporal123"])
        created = deepcopy(qa_users[-1])
        assert created["require_password_change"] and created["username"] == "nuevo.demo"
        fill_and_save(frame._popup_editar("usuarios", created), ["Nombre editado", "editado.demo"])
        assert qa_users[-1]["id"] == created["id"] and qa_users[-1]["nombre"] == "Nombre editado"
        with patch("ui.system_admin_frame.messagebox.askyesno", return_value=True):
            frame._confirmar_estado("usuarios", qa_users[-1])
        assert qa_users[-1]["activo"] == 0
        with patch("ui.system_admin_frame.messagebox.askyesno", return_value=True):
            frame._confirmar_estado("usuarios", qa_users[-1])
        assert qa_users[-1]["activo"] == 1
        with patch("ui.system_admin_frame.messagebox.showinfo"):
            fill_and_save(frame._popup_password(qa_users[-1]), ["otraTemporal123", "otraTemporal123"])
        assert qa_login("editado.demo", "temporal123") is None
        assert qa_login("editado.demo", "otraTemporal123")["require_password_change"]
        qa_change_password(created["id"], "definitiva456")
        assert not qa_login("editado.demo", "definitiva456")["require_password_change"]
        fill_and_save(frame._popup_editar("restaurantes"), ["Sucursal nueva"])
        new_restaurant = deepcopy(qa_restaurants[-1])
        fill_and_save(frame._popup_editar("restaurantes", new_restaurant), ["Sucursal renombrada"])
        assert qa_restaurants[-1]["id"] == new_restaurant["id"]
        with patch("ui.system_admin_frame.messagebox.askyesno", return_value=True):
            frame._confirmar_estado("restaurantes", qa_restaurants[-1])
        assert qa_restaurants[-1]["activo"] == 0
    finally:
        qa_users[:] = backup[0]; qa_restaurants[:] = backup[1]
        qa_passwords.clear(); qa_passwords.update(backup[2])
        system_admin()

def calendar():
    home()
    app.frame_actual._abrir_calendario()
    import tkcalendar
    app._qa_calendar = next(c for c in descendants(app) if isinstance(c, tkcalendar.Calendar))

toolbar = ctk.CTkFrame(app.appearance_bar, fg_color="transparent")
toolbar.pack(side="left", padx=10)
qa_views = {
    "Inicio": home, "Editor de reportes": report, "Editor de bitácoras": logs,
    "Carga de bitácoras": loading_logs,
    "Administrar reportes": admin_reports, "Buscar bitácoras": admin_dates,
    "Detalle de bitácoras": admin, "Visor de evidencias": viewer, "Sistema": system_admin,
    "Probar acceso temporal": demo_login,
}
ctk.CTkLabel(toolbar, text="Vista de prueba:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 6))
selector_qa = ctk.CTkOptionMenu(toolbar, values=list(qa_views), command=lambda value: qa_views[value](), width=192, height=24)
selector_qa.pack(side="left")
ctk.CTkLabel(toolbar, text="Datos ficticios · sin API", font=("Segoe UI", 11)).pack(side="left", padx=12)
ctk.CTkLabel(toolbar, text="Demo: walter.demo / demo123", font=("Segoe UI", 11)).pack(side="left")
if "--smoke" in sys.argv:
    errors = []
    app.report_callback_exception = lambda *args: errors.append(str(args[1]))
    screens = [home, report, logs, admin, admin_reports, admin_report_search, admin_dates, viewer, system_admin, system_admin_dialogs, system_admin_mutations]
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
        has_report_filters = screen in (admin_reports, admin_report_search)
        if has_report_filters:
            report_query = (original_frame.filtro_nombre_reporte.get(), original_frame.filtro_restaurante_reporte.get())
            report_cards = tuple(original_frame.scroll_reportes.winfo_children())
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
            if has_report_filters:
                assert (original_frame.filtro_nombre_reporte.get(), original_frame.filtro_restaurante_reporte.get()) == report_query
                assert tuple(original_frame.scroll_reportes.winfo_children()) == report_cards
            app.update_idletasks()
            if "--contrast" in sys.argv:
                from test_pc_appearance import contrast
                def inspect_colors(widget):
                    if isinstance(widget, (ctk.CTkLabel, ctk.CTkButton)) and widget.winfo_manager():
                        text = widget.cget("text")
                        if isinstance(widget, IconLabel) and text and widget.cget("image"):
                            assert widget.cget("compound") != "center", (screen.__name__, text, "icon/text overlap")
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
    if "--inspect" in sys.argv:
        app.title("AuditFlow — Inspección (DATOS DE PRUEBA)")
        ctk.set_appearance_mode("Light")
        app._update_appearance_button()
        if "--loading" in sys.argv:
            app.title("AuditFlow — Carga animada (DATOS DE PRUEBA)")
            selector_qa.set("Carga de bitácoras")
            loading_logs()
        else:
            selector_qa.set("Sistema")
            system_admin()
    else:
        home()
        app.after(900000, app.destroy)
    app.mainloop()
