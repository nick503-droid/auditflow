import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime, timedelta

from api.client import obtener_usuarios
import session

from ui.theme import (
    APP_BACKGROUND, SURFACE, SURFACE_SECONDARY, BORDER, BORDER_FOCUS,
    PRIMARY, PRIMARY_HOVER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    RADIUS_PANEL, RADIUS_BUTTON, get_font, STATUS
)

class SelectionFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, **kwargs):
        super().__init__(master, fg_color=APP_BACKGROUND, **kwargs)
        self.controlador = controlador

        self.fecha_bitacora = datetime.now().strftime("%Y-%m-%d")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_ui()

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
            font=get_font(size=32, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box, 
            text="Selecciona tu perfil de auditor para comenzar", 
            font=get_font(size=14),
            text_color=TEXT_SECONDARY
        ).pack(anchor="w")

        # Derecha: Selector de Usuario y Botones de Gestión Rápida
        user_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        user_box.grid(row=0, column=1, sticky="e")

        # Saludo del usuario logueado
        nombre_activo = session.get_nombre()
        ctk.CTkLabel(
            user_box,
            text=f"Hola, {nombre_activo}",
            font=get_font(size=12),
            text_color=TEXT_SECONDARY
        ).pack(side="left", padx=(0, 15))

        # Botón de Administración del Sistema (SOLO para ADMIN)
        if session.get_role() == 'ADMIN':
            ctk.CTkButton(
                user_box,
                text="⚙️ Administrar Sistema",
                command=self._abrir_system_admin,
                fg_color="transparent",
                hover_color=SURFACE_SECONDARY,
                border_width=1,
                border_color=BORDER,
                text_color=TEXT_SECONDARY,
                font=get_font(size=12, weight="bold"),
                width=160,
                height=32,
                corner_radius=RADIUS_BUTTON
            ).pack(side="left", padx=(0, 10))

        # Botón Cerrar Sesión
        ctk.CTkButton(
            user_box,
            text="🚪 Salir",
            command=self._cerrar_sesion,
            fg_color="transparent",
            hover_color=STATUS["error"]["bg"],
            border_width=1,
            border_color=STATUS["error"]["border"],
            text_color=STATUS["error"]["text"],
            font=get_font(size=12),
            width=80,
            height=32,
            corner_radius=RADIUS_BUTTON
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
        self.seg_fecha = ctk.CTkSegmentedButton(
            self.card_bitacoras,
            values=["Hoy", "Ayer", "📅 Otra"],
            command=self._on_fecha_cambiada,
            selected_color=PRIMARY,
            selected_hover_color=PRIMARY_HOVER,
            unselected_color=APP_BACKGROUND,
            unselected_hover_color=SURFACE_SECONDARY,
            text_color=TEXT_PRIMARY,
            font=get_font(size=12)
        )
        self.seg_fecha.set("Hoy")
        self.seg_fecha.pack(fill="x", padx=24, pady=(0, 24), side="bottom")
        
        self.lbl_fecha = ctk.CTkLabel(
            self.card_bitacoras,
            text=f"Fecha de la jornada: {self.fecha_bitacora}",
            font=get_font(size=11),
            text_color=TEXT_SECONDARY
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

        # 3. Tarjeta: Administración
        self.card_admin = self._crear_tarjeta_modulo(
            parent=self.cards_frame,
            col=2,
            icono="🗂️",
            titulo="Administrar",
            descripcion="Explora, edita o elimina todos los reportes y bitácoras de la nube y locales.",
            comando=self._abrir_administrador
        )


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
            background=APP_BACKGROUND,
            foreground=TEXT_PRIMARY,
            headersbackground=SURFACE_SECONDARY,
            headersforeground=TEXT_PRIMARY,
            normalbackground=SURFACE,
            normalforeground=TEXT_PRIMARY,
            weekendbackground=SURFACE,
            weekendforeground=TEXT_PRIMARY,
            selectbackground=PRIMARY,
            selectforeground="#FFFFFF"
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
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=_on_cancelar, width=100, fg_color="transparent", border_width=1, text_color=TEXT_PRIMARY, corner_radius=RADIUS_BUTTON).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Aceptar", command=_on_aceptar, width=100, fg_color=PRIMARY, hover_color=PRIMARY_HOVER, text_color="#FFFFFF", corner_radius=RADIUS_BUTTON).pack(side="left", padx=10)

    def _crear_tarjeta_modulo(self, parent, col, icono, titulo, descripcion, comando):
        """Crea una tarjeta interactiva con hover effects."""
        card = ctk.CTkFrame(
            parent, 
            fg_color=SURFACE, 
            corner_radius=RADIUS_PANEL,
            cursor="hand2",
            border_width=1,
            border_color=BORDER
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
            font=get_font(size=48)
        )
        lbl_icon.pack(pady=(0, 16))

        # Título
        lbl_title = ctk.CTkLabel(
            inner, 
            text=titulo, 
            font=get_font(size=18, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        lbl_title.pack(pady=(0, 8))

        # Descripción
        lbl_desc = ctk.CTkLabel(
            inner, 
            text=descripcion, 
            font=get_font(size=13),
            text_color=TEXT_SECONDARY,
            wraplength=220,
            justify="center"
        )
        lbl_desc.pack(pady=(0, 24))

        # Botón de acción principal
        btn = ctk.CTkButton(
            inner,
            text="Abrir Módulo  →",
            command=comando,
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            text_color="#FFFFFF",
            font=get_font(size=13, weight="bold"),
            height=40,
            corner_radius=RADIUS_BUTTON
        )
        btn.pack(side="bottom", fill="x")

        # Efectos Hover
        def _hover_in(e):
            if self.usuario_seleccionado:
                card.configure(fg_color=SURFACE_SECONDARY)
        
        def _hover_out(e):
            if self.usuario_seleccionado:
                card.configure(fg_color=SURFACE)

        def _on_click(e):
            if self.usuario_seleccionado:
                comando()

        for w in (card, inner, lbl_icon, lbl_title, lbl_desc):
            w.bind("<Enter>", _hover_in)
            w.bind("<Leave>", _hover_out)
            w.bind("<Button-1>", _on_click)

        # Guardar ref al botón
        card._action_btn = btn
        card._hover_in = _hover_in
        card._hover_out = _hover_out
        card._on_click = _on_click
        return card

    def _set_estado_tarjetas(self, estado: str):
        pass

    # ─── LÓGICA DE DATOS Y NAVEGACIÓN ───

    def _abrir_bitacoras(self):
        from ui.bitacoras_frame import BitacorasFrame
        # Usamos la sesión directamente en lugar del dropdown
        perfil = session.get_session()
        self.controlador.mostrar_frame(
            BitacorasFrame,
            usuario=perfil,
            fecha=self.fecha_bitacora
        )

    def _abrir_reportes(self):
        from ui.reportes_frame import ReportesFrame
        perfil = session.get_session()
        self.controlador.mostrar_frame(
            ReportesFrame,
            usuario=perfil
        )

    def _abrir_system_admin(self):
        from ui.system_admin_frame import SystemAdminFrame
        self.controlador.mostrar_frame(SystemAdminFrame)

    def _cerrar_sesion(self):
        session.clear_session()
        from ui.login_frame import LoginFrame
        self.controlador.mostrar_frame(LoginFrame)

    def _abrir_administrador(self):
        from ui.admin_frame import AdminFrame
        perfil = session.get_session()
        self.controlador.mostrar_frame(
            AdminFrame,
            usuario=perfil
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