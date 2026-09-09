import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime, timedelta

from api.client import obtener_usuarios, crear_usuario, crear_restaurante

# ─── SISTEMA DE DISEÑO ───────────────────────────────────────────────────────
BG_COLOR = "#0f172a"
CARD_COLOR = "#1e293b"
CARD_HOVER = "#334155"
TEXT_MAIN = "#f8fafc"
TEXT_SEC = "#94a3b8"
ACCENT_COLOR = "#4f46e5"
ACCENT_HOVER = "#4338ca"
SUCCESS_COLOR = "#10b981"
CORNER_RADIUS = 15

class SelectionFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, **kwargs):
        super().__init__(master, fg_color=BG_COLOR, **kwargs)
        self.controlador = controlador

        self.usuario_seleccionado = None
        self.usuarios_data = {}
        self.fecha_bitacora = datetime.now().strftime("%Y-%m-%d")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_ui()
        self._cargar_usuarios()

    def _construir_ui(self):
        # Contenedor central responsivo
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=40, pady=40)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        # ─── HEADER (Título y Selector de Usuario) ───
        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 40))
        header_frame.grid_columnconfigure(0, weight=1)
        header_frame.grid_columnconfigure(1, weight=0)

        # Izquierda: Título y Subtítulo
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        
        ctk.CTkLabel(
            title_box, 
            text="AuditFlow", 
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=TEXT_MAIN
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box, 
            text="Selecciona tu perfil de auditor para comenzar", 
            font=ctk.CTkFont(size=14),
            text_color=TEXT_SEC
        ).pack(anchor="w")

        # Derecha: Selector de Usuario y Botones de Gestión Rápida
        user_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        user_box.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            user_box,
            text="👤 Usuario Activo:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SEC
        ).pack(side="left", padx=(0, 10))

        self.dropdown_usuario = ctk.CTkOptionMenu(
            user_box, 
            values=["Cargando..."], 
            command=self._on_usuario_seleccionado,
            fg_color=CARD_COLOR,
            button_color=CARD_COLOR,
            button_hover_color=CARD_HOVER,
            dropdown_fg_color=CARD_COLOR,
            dropdown_hover_color=CARD_HOVER,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=13),
            corner_radius=8,
            width=200,
            height=36
        )
        self.dropdown_usuario.pack(side="left", padx=(0, 15))

        # Botones de gestión rápida
        ctk.CTkButton(
            user_box,
            text="➕ Nuevo Usuario",
            command=self._popup_nuevo_usuario,
            fg_color="transparent",
            hover_color=CARD_HOVER,
            border_width=1,
            border_color=CARD_COLOR,
            text_color=TEXT_SEC,
            font=ctk.CTkFont(size=12),
            width=120,
            height=32,
            corner_radius=8
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            user_box,
            text="➕ Nuevo Restaurante",
            command=self._popup_nuevo_restaurante,
            fg_color="transparent",
            hover_color=CARD_HOVER,
            border_width=1,
            border_color=CARD_COLOR,
            text_color=TEXT_SEC,
            font=ctk.CTkFont(size=12),
            width=140,
            height=32,
            corner_radius=8
        ).pack(side="left")

        # ─── GRID DE MÓDULOS (Tarjetas) ───
        self.cards_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.cards_frame.pack(fill="both", expand=True)
        self.cards_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")
        self.cards_frame.grid_rowconfigure(0, weight=1)

        # 1. Tarjeta: Bitácoras
        self.card_bitacoras = self._crear_tarjeta_modulo(
            parent=self.cards_frame,
            col=0,
            icono="📝",
            titulo="Bitácoras Diarias",
            descripcion="Auditorías colaborativas por restaurante. Múltiples auditores pueden adjuntar evidencias al mismo día.",
            comando=self._abrir_bitacoras
        )
        
        # Selector de Fecha en píldoras (Segmented Button)
        self.seg_fecha = ctk.CTkSegmentedButton(
            self.card_bitacoras,
            values=["Hoy", "Ayer", "📅 Otra"],
            command=self._on_fecha_cambiada,
            selected_color=ACCENT_COLOR,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_COLOR,
            unselected_hover_color=CARD_HOVER,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=12)
        )
        self.seg_fecha.set("Hoy")
        self.seg_fecha.pack(fill="x", padx=24, pady=(0, 24), side="bottom")
        
        self.lbl_fecha = ctk.CTkLabel(
            self.card_bitacoras,
            text=f"Fecha de la jornada: {self.fecha_bitacora}",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SEC
        )
        self.lbl_fecha.pack(side="bottom", anchor="center", padx=24, pady=(0, 5))

        # 2. Tarjeta: Reportes
        self.card_reportes = self._crear_tarjeta_modulo(
            parent=self.cards_frame,
            col=1,
            icono="📊",
            titulo="Reportes",
            descripcion="Redacta reportes individuales detallados con evidencias y texto. Funcionan 100% offline.",
            comando=self._abrir_reportes
        )

        # 3. Tarjeta: Administrador
        self.card_admin = self._crear_tarjeta_modulo(
            parent=self.cards_frame,
            col=2,
            icono="🗂️",
            titulo="Administrar",
            descripcion="Explora, edita o elimina todos los reportes y bitácoras de la nube y locales.",
            comando=self._abrir_administrador
        )

        # Inicialmente deshabilitar las tarjetas hasta seleccionar usuario
        self._set_estado_tarjetas("disabled")

    def _on_fecha_cambiada(self, valor):
        if valor == "Hoy":
            self.fecha_bitacora = datetime.now().strftime("%Y-%m-%d")
            self.lbl_fecha.configure(text=f"Fecha de la jornada: {self.fecha_bitacora}")
        elif valor == "Ayer":
            self.fecha_bitacora = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            self.lbl_fecha.configure(text=f"Fecha de la jornada: {self.fecha_bitacora}")
        elif valor == "📅 Otra":
            self._abrir_calendario()

    def _abrir_calendario(self):
        cal_window = ctk.CTkToplevel(self)
        cal_window.title("Seleccionar Fecha")
        cal_window.geometry("320x340")
        cal_window.attributes("-topmost", True)
        cal_window.grab_set()

        from tkcalendar import Calendar
        cal = Calendar(
            cal_window, 
            selectmode="day", 
            date_pattern="y-mm-dd",
            background=BG_COLOR,
            foreground="white",
            headersbackground=CARD_COLOR,
            headersforeground="white",
            normalbackground=CARD_COLOR,
            normalforeground="white",
            weekendbackground=CARD_COLOR,
            weekendforeground="white",
            selectbackground=ACCENT_COLOR,
            selectforeground="white"
        )
        cal.pack(pady=15, padx=15, fill="both", expand=True)

        def _on_aceptar():
            self.fecha_bitacora = cal.get_date()
            self.lbl_fecha.configure(text=f"Fecha de la jornada: {self.fecha_bitacora}")
            cal_window.destroy()
            if messagebox.askyesno("Confirmar", f"¿Abrir bitácora con fecha {self.fecha_bitacora}?"):
                if self.dropdown_usuario.get() and self.dropdown_usuario.get() != "Selecciona un usuario...":
                    self._abrir_bitacoras()
                else:
                    messagebox.showerror("Error", "Por favor selecciona un usuario antes de continuar.")

        def _on_cancelar():
            self.seg_fecha.set("Hoy")
            self._on_fecha_cambiada("Hoy")
            cal_window.destroy()
            
        cal_window.protocol("WM_DELETE_WINDOW", _on_cancelar)

        btn_frame = ctk.CTkFrame(cal_window, fg_color="transparent")
        btn_frame.pack(pady=(0, 15))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=_on_cancelar, width=100, fg_color="transparent", border_width=1).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Aceptar", command=_on_aceptar, width=100, fg_color=ACCENT_COLOR).pack(side="left", padx=10)

    def _crear_tarjeta_modulo(self, parent, col, icono, titulo, descripcion, comando):
        """Crea una tarjeta interactiva con hover effects."""
        card = ctk.CTkFrame(
            parent, 
            fg_color=CARD_COLOR, 
            corner_radius=CORNER_RADIUS,
            cursor="hand2"
        )
        card.grid(row=0, column=col, sticky="nsew", padx=10)
        card.grid_columnconfigure(0, weight=1)

        # Contenedor interno para centrar contenido
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=24, pady=32)

        # Icono gigante
        lbl_icon = ctk.CTkLabel(
            inner, 
            text=icono, 
            font=ctk.CTkFont(size=48)
        )
        lbl_icon.pack(pady=(0, 16))

        # Título
        lbl_title = ctk.CTkLabel(
            inner, 
            text=titulo, 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT_MAIN
        )
        lbl_title.pack(pady=(0, 8))

        # Descripción
        lbl_desc = ctk.CTkLabel(
            inner, 
            text=descripcion, 
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SEC,
            wraplength=220,
            justify="center"
        )
        lbl_desc.pack(pady=(0, 24))

        # Botón de acción principal
        btn = ctk.CTkButton(
            inner,
            text="Abrir Módulo  →",
            command=comando,
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            corner_radius=8
        )
        btn.pack(side="bottom", fill="x")

        # Efectos Hover
        def _hover_in(e):
            if self.usuario_seleccionado:
                card.configure(fg_color=CARD_HOVER)
        
        def _hover_out(e):
            if self.usuario_seleccionado:
                card.configure(fg_color=CARD_COLOR)

        def _on_click(e):
            if self.usuario_seleccionado:
                comando()

        for w in (card, inner, lbl_icon, lbl_title, lbl_desc):
            w.bind("<Enter>", _hover_in)
            w.bind("<Leave>", _hover_out)
            w.bind("<Button-1>", _on_click)

        # Guardar ref al botón para habilitar/deshabilitar
        card._action_btn = btn
        card._hover_in = _hover_in
        card._hover_out = _hover_out
        card._on_click = _on_click

        return card

    def _set_estado_tarjetas(self, estado: str):
        """Habilita o deshabilita los clics en las tarjetas."""
        for card in [self.card_bitacoras, self.card_reportes, self.card_admin]:
            if estado == "disabled":
                card._action_btn.configure(state="disabled", fg_color=CARD_HOVER)
                card.configure(cursor="arrow")
                # Desvincular eventos temporalmente
                for w in (card, card.winfo_children()[0]):
                    for child in w.winfo_children():
                        try:
                            child.unbind("<Button-1>")
                        except (NotImplementedError, Exception):
                            pass
                        try:
                            child.configure(state="disabled")
                        except Exception:
                            pass
                    try:
                        w.unbind("<Button-1>")
                    except (NotImplementedError, Exception):
                        pass
            else:
                card._action_btn.configure(state="normal", fg_color=ACCENT_COLOR)
                card.configure(cursor="hand2")
                # Revincular eventos
                for w in (card, card.winfo_children()[0]):
                    for child in w.winfo_children():
                        try:
                            if not isinstance(child, ctk.CTkSegmentedButton):
                                child.bind("<Button-1>", card._on_click)
                        except (NotImplementedError, Exception):
                            pass
                        try:
                            child.configure(state="normal")
                        except Exception:
                            pass
                    try:
                        w.bind("<Button-1>", card._on_click)
                    except (NotImplementedError, Exception):
                        pass

    # ─── LÓGICA DE DATOS Y NAVEGACIÓN ───

    def _cargar_usuarios(self):
        usuarios = obtener_usuarios()
        if usuarios:
            self.usuarios_data = {u["nombre"]: u for u in usuarios}
            nombres = list(self.usuarios_data.keys())
            self.dropdown_usuario.configure(values=nombres)
            # Autoseleccionar si hay uno solo, o dejar placeholder
            if len(nombres) == 1:
                self.dropdown_usuario.set(nombres[0])
                self._on_usuario_seleccionado(nombres[0])
            else:
                self.dropdown_usuario.set("Elige tu perfil...")
        else:
            self.usuarios_data = {}
            self.dropdown_usuario.configure(values=["Sin conexión al servidor"])
            self.dropdown_usuario.set("Sin conexión al servidor")

    def _on_usuario_seleccionado(self, nombre_elegido):
        self.usuario_seleccionado = self.usuarios_data.get(nombre_elegido)
        if self.usuario_seleccionado:
            self._set_estado_tarjetas("normal")

    def _abrir_bitacoras(self):
        from ui.bitacoras_frame import BitacorasFrame
        self.controlador.mostrar_frame(
            BitacorasFrame,
            usuario=self.usuario_seleccionado,
            fecha=self.fecha_bitacora
        )

    def _abrir_reportes(self):
        from ui.reportes_frame import ReportesFrame
        self.controlador.mostrar_frame(
            ReportesFrame,
            usuario=self.usuario_seleccionado
        )

    def _abrir_administrador(self):
        from ui.admin_frame import AdminFrame
        self.controlador.mostrar_frame(
            AdminFrame,
            usuario=self.usuario_seleccionado
        )

    # ─── POPUPS DE GESTIÓN RÁPIDA ───

    def _popup_nuevo_usuario(self):
        dialog = ctk.CTkInputDialog(text="Escribe el nombre del nuevo Auditor:", title="Nuevo Usuario")
        nombre = dialog.get_input()
        if nombre and nombre.strip():
            # Crear usuario en backend
            res = crear_usuario({"nombre": nombre.strip()})
            if res:
                messagebox.showinfo("Éxito", f"Usuario '{nombre.strip()}' creado correctamente.")
                self._cargar_usuarios() # Refresca UI
                self.dropdown_usuario.set(nombre.strip())
                self._on_usuario_seleccionado(nombre.strip())
            else:
                messagebox.showerror("Error", "No se pudo crear el usuario. Verifica tu conexión.")

    def _popup_nuevo_restaurante(self):
        dialog = ctk.CTkInputDialog(text="Escribe el nombre del nuevo Restaurante:", title="Nuevo Restaurante")
        nombre = dialog.get_input()
        if nombre and nombre.strip():
            # Crear restaurante en backend
            res = crear_restaurante({"nombre": nombre.strip()})
            if res:
                messagebox.showinfo("Éxito", f"Restaurante '{nombre.strip()}' creado correctamente.\nYa está disponible en todos los módulos.")
            else:
                messagebox.showerror("Error", "No se pudo crear el restaurante. Verifica tu conexión.")