"""Gestión de catálogos online; no borra historial ni añade autenticación nueva."""
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import session
from api.client import (
    obtener_system_info, obtener_usuarios_admin, obtener_restaurantes_admin,
    guardar_usuario_admin, guardar_restaurante_admin, restablecer_password_admin,
)
from ui.visual_widgets import IconButton, IconLabel
from ui.report_filter import normalizar_busqueda
from ui.theme import (
    APP_BACKGROUND, SURFACE, SURFACE_SECONDARY, BORDER, PRIMARY, PRIMARY_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, get_font, STATUS,
)


def filtrar_catalogo(rows, query="", estado="Todos"):
    tokens = normalizar_busqueda(query).split()
    return [row for row in rows
            if (estado == "Todos" or bool(row.get("activo", 1)) == (estado == "Activos"))
            and all(token in normalizar_busqueda(f"{row.get('nombre', '')} {row.get('username') or ''}") for token in tokens)]


class SystemAdminFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, **kwargs):
        super().__init__(master, fg_color=APP_BACKGROUND, **kwargs)
        self.controlador = controlador
        self._vivo = True
        self._queue = Queue()
        self._jobs = 0
        self._pump_id = None
        self._load_id = 0
        self._conectado = False
        self._datos = {"usuarios": [], "restaurantes": []}
        self._vistas = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        if session.get_role() != "ADMIN":
            IconLabel(self, text="Este panel está disponible para administradores.", text_color=TEXT_PRIMARY).pack(pady=40)
            IconButton(self, text="← Volver", command=self._volver).pack()
            return
        self._construir_ui()
        self._cargar_metricas()
        self._cargar_catalogos()

    def _submit(self, operation, success, failure):
        """El worker no toca Tk; sólo el hilo principal procesa resultados."""
        if not self._vivo:
            return
        self._jobs += 1
        def worker():
            try:
                self._queue.put((success, operation()))
            except Exception as exc:
                self._queue.put((failure, str(exc)))
        threading.Thread(target=worker, daemon=True, name="AdminCatalogos").start()
        if self._pump_id is None:
            self._pump_id = self.after(80, self._pump)

    def _pump(self):
        self._pump_id = None
        if not self._vivo:
            return
        try:
            while self._vivo:
                callback, value = self._queue.get_nowait()
                self._jobs -= 1
                callback(value)
        except Empty:
            pass
        finally:
            # Un callback puede iniciar otra carga o destruir la vista.
            # No duplicar el timer que _submit pudo haber programado.
            if self._jobs and self._vivo and self._pump_id is None:
                self._pump_id = self.after(80, self._pump)

    def destroy(self):
        self._vivo = False
        for view in self._vistas.values():
            if view.get("filter_job") is not None:
                self.after_cancel(view["filter_job"])
        if self._pump_id is not None:
            self.after_cancel(self._pump_id)
            self._pump_id = None
        super().destroy()

    def _volver(self):
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)

    def _construir_ui(self):
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=18, pady=16)
        header = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))
        IconButton(header, text="← Volver", width=90, fg_color=SURFACE_SECONDARY, hover_color=SURFACE_SECONDARY, text_color=TEXT_PRIMARY, command=self._volver).pack(side="left", padx=(0, 12))
        title = IconLabel(header, text="Administración del Sistema", font=get_font(size=24, weight="bold"), text_color=TEXT_PRIMARY, wraplength=520)
        title.pack(side="left")
        header.bind("<Configure>", lambda event: title.configure(wraplength=max(180, event.width - 120)))
        metrics = ctk.CTkFrame(self.main_container, fg_color="transparent")
        metrics.pack(fill="x", pady=(0, 12))
        metrics.grid_columnconfigure((0, 1), weight=1, uniform="metric")
        server = ctk.CTkFrame(metrics, fg_color=SURFACE, corner_radius=12)
        server.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        IconLabel(server, text="🌐 Servidor", text_color=TEXT_SECONDARY).pack(pady=(10, 2))
        self.lbl_ip = IconLabel(server, text="Cargando…", text_color=TEXT_PRIMARY, font=get_font(size=17, weight="bold"), wraplength=300)
        self.lbl_ip.pack(padx=8, pady=(0, 10))
        server.bind("<Configure>", lambda event: self.lbl_ip.configure(wraplength=max(100, event.width - 24)))
        storage = ctk.CTkFrame(metrics, fg_color=SURFACE, corner_radius=12)
        storage.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        IconLabel(storage, text="💾 Almacenamiento", text_color=TEXT_SECONDARY).pack(pady=(8, 0))
        self.lbl_storage_uso = IconLabel(storage, text="-- / --", text_color=TEXT_PRIMARY, font=get_font(size=17, weight="bold"))
        self.lbl_storage_uso.pack()
        self.progress_storage = ctk.CTkProgressBar(storage, height=7, progress_color=PRIMARY, fg_color=APP_BACKGROUND)
        self.progress_storage.pack(fill="x", padx=20, pady=4)
        self.progress_storage.set(0)
        self.lbl_storage_detalles = IconLabel(storage, text="Disponible: --", text_color=TEXT_MUTED, font=get_font(size=11))
        self.lbl_storage_detalles.pack(pady=(0, 6))
        bar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        bar.pack(fill="x")
        self.lbl_estado = IconLabel(bar, text="Conectando al servidor…", text_color=TEXT_SECONDARY, anchor="w", wraplength=650)
        self.lbl_estado.pack(side="left", fill="x", expand=True)
        bar.bind("<Configure>", lambda event: self.lbl_estado.configure(wraplength=max(150, event.width - 125)))
        self.btn_refrescar = IconButton(bar, text="↻ Actualizar", width=100, command=self._cargar_catalogos, fg_color=SURFACE_SECONDARY, hover_color=SURFACE_SECONDARY, text_color=TEXT_PRIMARY)
        self.btn_refrescar.pack(side="right", padx=(8, 0))
        self.tabs = ctk.CTkTabview(self.main_container, fg_color=SURFACE)
        self.tabs.pack(fill="both", expand=True, pady=(6, 0))
        for tipo, label in (("usuarios", "Usuarios"), ("restaurantes", "Restaurantes")):
            self._construir_catalogo(self.tabs.add(label), tipo)

    def _construir_catalogo(self, parent, tipo):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=(8, 6))
        count = IconLabel(bar, text="Cargando…", text_color=TEXT_SECONDARY)
        count.pack(side="left")
        new = IconButton(bar, text="＋ Nuevo usuario" if tipo == "usuarios" else "＋ Nuevo restaurante", width=170,
                         fg_color=PRIMARY, hover_color=PRIMARY_HOVER, text_color="#FFFFFF", command=lambda: self._popup_editar(tipo))
        new.pack(side="right")
        filters = ctk.CTkFrame(parent, fg_color="transparent")
        filters.pack(fill="x", padx=10, pady=(0, 8))
        estado = tk.StringVar(value="Todos")
        entry = ctk.CTkEntry(filters, placeholder_text="Buscar por nombre o usuario" if tipo == "usuarios" else "Buscar restaurante",
                            text_color=TEXT_PRIMARY, fg_color=APP_BACKGROUND, border_color=BORDER)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        entry.bind("<KeyRelease>", lambda event: self._programar_filtro(tipo))
        entry.bind("<<Paste>>", lambda event: self._programar_filtro(tipo), add="+")
        menu = ctk.CTkOptionMenu(filters, values=["Todos", "Activos", "Inactivos"], variable=estado, width=115,
                               fg_color=SURFACE_SECONDARY, button_color=PRIMARY, text_color=TEXT_PRIMARY,
                               command=lambda value: self._render_catalogo(tipo))
        menu.pack(side="right")
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        scroll.grid_columnconfigure(0, weight=1)
        self._vistas[tipo] = {"count": count, "entry": entry, "estado": estado, "scroll": scroll, "new": new}
        new.configure(state="disabled")

    def _cargar_metricas(self):
        def loaded(data):
            if not data:
                self.lbl_ip.configure(text="Sin conexión", text_color=STATUS["warning"]["text"])
                return
            from api.client import API_BASE_URL
            storage = data.get("storage", {})
            try:
                ratio = float(str(storage.get("porcentaje", "0%")).replace("%", "")) / 100
            except (TypeError, ValueError):
                ratio = 0
            self._actualizar_dashboard(API_BASE_URL, storage.get("usado", "--"), storage.get("total", "--"), storage.get("disponible", "--"), ratio)
        self._submit(obtener_system_info, loaded, lambda error: loaded(None))

    def _actualizar_dashboard(self, ip, usado, total, disponible, porcentaje_val):
        self.lbl_ip.configure(text=ip, text_color=TEXT_PRIMARY)
        self.lbl_storage_uso.configure(text=f"{usado} / {total}")
        self.lbl_storage_detalles.configure(text=f"Disponible: {disponible}")
        self.progress_storage.set(max(0, min(1, porcentaje_val)))
        status = "error" if porcentaje_val > .85 else "warning" if porcentaje_val > .70 else "success"
        self.progress_storage.configure(progress_color=STATUS[status]["text"])

    def _cargar_catalogos(self):
        self._load_id += 1
        load_id = self._load_id
        self._conectado = False
        self.btn_refrescar.configure(state="disabled")
        for view in self._vistas.values():
            view["new"].configure(state="disabled")
        self.lbl_estado.configure(text="Actualizando catálogos…", text_color=TEXT_SECONDARY)
        def loaded(result):
            if load_id != self._load_id:
                return
            self._datos = result
            self._conectado = True
            self.btn_refrescar.configure(state="normal")
            offline = bool((session.get_session() or {}).get("offline_mode"))
            self.lbl_estado.configure(text="Inicia sesión online para gestionar cuentas." if offline else "Gestión online · Desactivar conserva todo el historial.", text_color=TEXT_SECONDARY)
            for tipo, view in self._vistas.items():
                view["new"].configure(state="disabled" if offline else "normal")
                self._render_catalogo(tipo)
        def failed(error):
            if load_id != self._load_id:
                return
            self.btn_refrescar.configure(state="normal")
            self.lbl_estado.configure(text=error, text_color=STATUS["error"]["text"])
            for tipo in self._vistas:
                self._render_catalogo(tipo)
        self._submit(lambda: {"usuarios": obtener_usuarios_admin(), "restaurantes": obtener_restaurantes_admin()}, loaded, failed)

    def _puede_gestionar(self):
        return session.get_role() == "ADMIN" and self._conectado and not (session.get_session() or {}).get("offline_mode")

    def _programar_filtro(self, tipo):
        view = self._vistas[tipo]
        if view.get("filter_job") is not None:
            self.after_cancel(view["filter_job"])
        view["filter_job"] = self.after(180, lambda: self._render_catalogo(tipo))

    def _render_catalogo(self, tipo):
        view = self._vistas[tipo]
        if view.get("filter_job") is not None:
            self.after_cancel(view["filter_job"])
            view["filter_job"] = None
        rows = filtrar_catalogo(self._datos[tipo], view["entry"].get(), view["estado"].get())
        view["count"].configure(text=f"{len(rows)} de {len(self._datos[tipo])} registros")
        signature = (self._puede_gestionar(), tuple((r.get("id"), r.get("nombre"), r.get("username"), r.get("role"), r.get("activo", 1), r.get("require_password_change")) for r in rows))
        if view.get("signature") == signature:
            return
        view["signature"] = signature
        for child in view["scroll"].winfo_children():
            child.destroy()
        if not rows:
            IconLabel(view["scroll"], text="No hay registros que coincidan.", text_color=TEXT_MUTED).grid(row=0, column=0, padx=12, pady=20)
        for i, row in enumerate(rows):
            self._crear_tarjeta(view["scroll"], tipo, row, i)

    def _crear_tarjeta(self, parent, tipo, row, i):
        card = ctk.CTkFrame(parent, fg_color=APP_BACKGROUND, border_width=1, border_color=BORDER, corner_radius=10)
        card.grid(row=i, column=0, sticky="ew", padx=4, pady=4)
        card.grid_columnconfigure(0, weight=1)
        title = IconLabel(card, text=row.get("nombre", "Sin nombre"), font=get_font(size=15, weight="bold"), text_color=TEXT_PRIMARY, anchor="w", wraplength=550)
        title.grid(row=0, column=0, sticky="ew", padx=12, pady=(9, 0))
        card.bind("<Configure>", lambda event: title.configure(wraplength=max(180, event.width - 130)))
        active = bool(row.get("activo", 1))
        color = STATUS["success" if active else "warning"]["text"]
        IconLabel(card, text="Activo" if active else "Inactivo", text_color=color).grid(row=0, column=1, padx=12, pady=(9, 0))
        if tipo == "usuarios":
            meta = f"Usuario: {row.get('username') or 'Sin acceso asignado'} · {row.get('role', 'EMPLEADO')}"
            if row.get("require_password_change"):
                meta += " · Cambio de contraseña pendiente"
            meta_label = IconLabel(card, text=meta, text_color=TEXT_SECONDARY, font=get_font(size=12), anchor="w", wraplength=650)
            meta_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=12)
            card.bind("<Configure>", lambda event: meta_label.configure(wraplength=max(180, event.width - 30)), add="+")
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(7, 10))
        state = "normal" if self._puede_gestionar() else "disabled"
        IconButton(actions, text="✏️ Editar", width=80, height=30, fg_color=SURFACE_SECONDARY, hover_color=SURFACE_SECONDARY, text_color=TEXT_PRIMARY,
                   state=state, command=lambda: self._popup_editar(tipo, row)).pack(side="left", padx=(0, 6))
        if tipo == "usuarios":
            IconButton(actions, text="Restablecer contraseña", width=160, height=30, fg_color=SURFACE_SECONDARY, hover_color=SURFACE_SECONDARY, text_color=TEXT_PRIMARY,
                       state=state if row.get("username") else "disabled", command=lambda: self._popup_password(row)).pack(side="left", padx=(0, 6))
        own = tipo == "usuarios" and row["id"] == (session.get_session() or {}).get("id")
        IconButton(actions, text="Desactivar" if active else "Activar", width=100, height=30,
                   fg_color=SURFACE_SECONDARY if active else PRIMARY, text_color=TEXT_PRIMARY if active else "#FFFFFF",
                   hover_color=SURFACE_SECONDARY if active else PRIMARY_HOVER,
                   state="disabled" if own else state, command=lambda: self._confirmar_estado(tipo, row)).pack(side="left")

    def _dialogo(self, title, height=470):
        win = ctk.CTkToplevel(self.controlador)
        win.title(title)
        win.geometry(f"460x{height}")
        win.minsize(420, height)
        win.configure(fg_color=APP_BACKGROUND)
        win.transient(self.controlador)
        win.grab_set()
        win._pending = False
        win.protocol("WM_DELETE_WINDOW", lambda: None if win._pending else win.destroy())
        inner = ctk.CTkScrollableFrame(win, fg_color=SURFACE)
        inner.pack(fill="both", expand=True, padx=16, pady=16)
        IconLabel(inner, text=title, font=get_font(size=20, weight="bold"), text_color=TEXT_PRIMARY, wraplength=360).pack(pady=(5, 12))
        return win, inner

    def _campo(self, parent, label, value="", password=False):
        IconLabel(parent, text=label, text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", padx=10)
        entry = ctk.CTkEntry(parent, height=36, fg_color=APP_BACKGROUND, text_color=TEXT_PRIMARY, border_color=BORDER, show="•" if password else "")
        entry.pack(fill="x", padx=10, pady=(3, 10))
        entry.insert(0, value)
        return entry

    def _acciones_dialogo(self, win, inner, operation, success):
        error = IconLabel(inner, text="", text_color=STATUS["error"]["text"], wraplength=350)
        error.pack(fill="x", padx=10, pady=(2, 6))
        buttons = ctk.CTkFrame(inner, fg_color="transparent")
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        cancel = IconButton(buttons, text="Cancelar", fg_color=SURFACE_SECONDARY, hover_color=SURFACE_SECONDARY, text_color=TEXT_PRIMARY, width=110, command=win.destroy)
        cancel.pack(side="left")
        def save():
            if win._pending:
                return
            if not self._puede_gestionar():
                error.configure(text="Se necesita conexión al servidor y una sesión de administrador online.")
                return
            try:
                job = operation()
            except ValueError as exc:
                error.configure(text=str(exc))
                return
            win._pending = True
            button.configure(state="disabled", text="Guardando…")
            cancel.configure(state="disabled")
            error.configure(text="")
            def done(data):
                if not win.winfo_exists():
                    return
                success(data)
                win.destroy()
                self._cargar_catalogos()
            def failed(message):
                if not win.winfo_exists():
                    return
                win._pending = False
                button.configure(state="normal", text="Guardar")
                cancel.configure(state="normal")
                error.configure(text=message)
            self._submit(job, done, failed)
        button = IconButton(buttons, text="Guardar", width=130, fg_color=PRIMARY, hover_color=PRIMARY_HOVER, text_color="#FFFFFF", command=save)
        button.pack(side="right")
        return save

    def _popup_editar(self, tipo, row=None):
        if not self._puede_gestionar():
            return
        user = tipo == "usuarios"
        title = ("Editar " if row else "Nuevo ") + ("usuario" if user else "restaurante")
        win, inner = self._dialogo(title, 520 if user else 290)
        name = self._campo(inner, "Nombre completo" if user else "Nombre del restaurante", (row or {}).get("nombre", ""))
        username = password = role = None
        if user:
            username = self._campo(inner, "Usuario de inicio de sesión", (row or {}).get("username") or "")
            IconLabel(inner, text="Rol", text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", padx=10)
            role = ctk.CTkOptionMenu(inner, values=["EMPLEADO", "ADMIN"], fg_color=SURFACE_SECONDARY, button_color=PRIMARY, text_color=TEXT_PRIMARY)
            role.set((row or {}).get("role", "EMPLEADO"))
            role.pack(fill="x", padx=10, pady=(3, 12))
            if row and row["id"] == (session.get_session() or {}).get("id"):
                role.configure(state="disabled")
            if not row:
                password = self._campo(inner, "Contraseña temporal (mínimo 6 caracteres)", password=True)
            else:
                IconLabel(inner, text="La contraseña no se modifica al editar estos datos.", text_color=TEXT_MUTED, wraplength=350).pack(pady=6)
        def operation():
            dto = {"nombre": name.get().strip()}
            if not dto["nombre"] or len(dto["nombre"]) > 255:
                raise ValueError("Escribe un nombre de hasta 255 caracteres.")
            if user:
                dto.update(username=username.get().strip(), role=role.get())
                if not dto["username"] or any(c.isspace() for c in dto["username"]) or len(dto["username"]) > 255:
                    raise ValueError("Escribe un usuario sin espacios, de hasta 255 caracteres.")
                if password:
                    dto["password"] = password.get()
                    self._validar_password(dto["password"])
            fn = guardar_usuario_admin if user else guardar_restaurante_admin
            identifier = row["id"] if row else None
            return lambda: fn(dto, identifier)
        def done(data):
            if user and data["id"] == (session.get_session() or {}).get("id"):
                session.set_session({**session.get_session(), **data})
        self._acciones_dialogo(win, inner, operation, done)
        name.focus_set()
        return win

    @staticmethod
    def _validar_password(value):
        if len(value.strip()) < 6 or len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña debe tener al menos 6 caracteres y no superar 72 bytes.")

    def _popup_password(self, row):
        if not self._puede_gestionar():
            return
        win, inner = self._dialogo("Restablecer contraseña", 470)
        IconLabel(inner, text=f"Cuenta: {row.get('username')}\nEl usuario deberá elegir una contraseña nueva al iniciar sesión online. No se recupera la contraseña anterior.",
                  text_color=TEXT_SECONDARY, wraplength=350).pack(padx=10, pady=(0, 12))
        password = self._campo(inner, "Contraseña temporal", password=True)
        confirmation = self._campo(inner, "Confirmar contraseña temporal", password=True)
        def operation():
            value = password.get()
            self._validar_password(value)
            if value != confirmation.get():
                raise ValueError("Las contraseñas no coinciden.")
            return lambda: restablecer_password_admin(row["id"], value)
        def done(data):
            messagebox.showinfo("Contraseña restablecida", "Entrega la contraseña temporal al usuario. Deberá cambiarla antes de entrar.\nLas PC offline conocerán el cambio al sincronizar.", parent=self.controlador)
        self._acciones_dialogo(win, inner, operation, done)
        password.focus_set()
        return win

    def _confirmar_estado(self, tipo, row):
        if not self._puede_gestionar():
            return
        if tipo == "usuarios" and row["id"] == (session.get_session() or {}).get("id"):
            messagebox.showwarning("Acción no disponible", "No puedes desactivar tu propia cuenta.", parent=self.controlador)
            return
        active = 0 if row.get("activo", 1) else 1
        verb = "Activar" if active else "Desactivar"
        if not messagebox.askyesno(verb, f"¿{verb} '{row.get('nombre')}'?\n\nSe conservarán los reportes, bitácoras y evidencias.\nLas PC desconectadas recibirán el estado al sincronizar.", parent=self.controlador):
            return
        self._conectado = False
        for kind in self._vistas:
            self._vistas[kind]["new"].configure(state="disabled")
            self._render_catalogo(kind)
        fn = guardar_usuario_admin if tipo == "usuarios" else guardar_restaurante_admin
        self.lbl_estado.configure(text=f"{verb}: guardando…", text_color=TEXT_SECONDARY)
        self._submit(lambda: fn({"activo": active}, row["id"]), lambda result: self._cargar_catalogos(), self._error_estado)

    def _error_estado(self, error):
        messagebox.showerror("No se confirmó el cambio", error, parent=self.controlador)
        self._cargar_catalogos()
