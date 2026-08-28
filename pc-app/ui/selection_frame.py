import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime

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
            text="➕ Usuario",
            command=self._popup_nuevo_usuario,
            fg_color="transparent",
            hover_color=CARD_HOVER,
            border_width=1,
            border_color=CARD_COLOR,
            text_color=TEXT_SEC,
            font=ctk.CTkFont(size=12),
            width=100,
            height=32,
            corner_radius=8
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            user_box,
            text="➕ Restaurante",
            command=self._popup_nuevo_restaurante,
            fg_color="transparent",
            hover_color=CARD_HOVER,
            border_width=1,
            border_color=CARD_COLOR,
            text_color=TEXT_SEC,
            font=ctk.CTkFont(size=12),
            width=110,
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
        
        # Campo de fecha integrado dentro de la tarjeta de Bitácoras
        self.entry_fecha = ctk.CTkEntry(
            self.card_bitacoras, 
            justify="center",
            fg_color=BG_COLOR,
            border_color=CARD_HOVER,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=14),
            height=36,
            corner_radius=8
        )
        self.entry_fecha.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.entry_fecha.pack(fill="x", padx=24, pady=(0, 24), side="bottom")
        
        ctk.CTkLabel(
            self.card_bitacoras,
            text="Fecha de la jornada (YYYY-MM-DD):",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SEC
        ).pack(side="bottom", anchor="w", padx=24, pady=(0, 5))

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
                        child.unbind("<Button-1>")
                    w.unbind("<Button-1>")
            else:
                card._action_btn.configure(state="normal", fg_color=ACCENT_COLOR)
                card.configure(cursor="hand2")
                # Revincular eventos
                for w in (card, card.winfo_children()[0]):
                    for child in w.winfo_children():
                        if not isinstance(child, ctk.CTkEntry):  # No vincular click al entry
                            child.bind("<Button-1>", card._on_click)
                    w.bind("<Button-1>", card._on_click)

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
        fecha = self.entry_fecha.get().strip()
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Fecha inválida", "Usa el formato exacto: YYYY-MM-DD")
            return

        from ui.bitacoras_frame import BitacorasFrame
        self.controlador.mostrar_frame(
            BitacorasFrame,
            usuario=self.usuario_seleccionado,
            fecha=fecha
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
                self._cargar_usuarios()
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