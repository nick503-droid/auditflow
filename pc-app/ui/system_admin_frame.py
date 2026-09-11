from ui.theme import APP_BACKGROUND, SURFACE, SURFACE_SECONDARY, BORDER, BORDER_FOCUS, PRIMARY, PRIMARY_HOVER, PRIMARY_SOFT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, RADIUS_PANEL, RADIUS_BUTTON, get_font, STATUS
import customtkinter as ctk
from tkinter import messagebox
from api.client import obtener_system_info, crear_usuario, crear_restaurante

# ─── SISTEMA DE DISEÑO ───────────────────────────────────────────────────────
BG_COLOR = APP_BACKGROUND
CARD_COLOR = SURFACE
CARD_HOVER = SURFACE_SECONDARY
TEXT_MAIN = TEXT_PRIMARY
TEXT_SEC = TEXT_SECONDARY
ACCENT_COLOR = PRIMARY
SUCCESS_COLOR = STATUS["success"]["text"]
CORNER_RADIUS = RADIUS_PANEL

class SystemAdminFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, **kwargs):
        super().__init__(master, fg_color=BG_COLOR, **kwargs)
        self.controlador = controlador

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_ui()
        self._cargar_metricas()

    def _construir_ui(self):
        # Contenedor central
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=40, pady=40)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        # ─── HEADER ───
        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 40))
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            header_frame,
            text="← Volver",
            command=self._volver,
            fg_color="transparent",
            hover_color=CARD_HOVER,
            text_color=TEXT_SEC,
            font=get_font(size=14, weight="bold"),
            width=80
        ).pack(side="left")

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=20)
        
        ctk.CTkLabel(
            title_box, 
            text="Administración del Sistema", 
            font=get_font(size=28, weight="bold"),
            text_color=TEXT_MAIN
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box, 
            text="Métricas del servidor Ubuntu y gestión de catálogos", 
            font=get_font(size=14),
            text_color=TEXT_SEC
        ).pack(anchor="w")

        # ─── CONTENIDO (2 Columnas) ───
        content_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=1, uniform="col")
        content_frame.grid_columnconfigure(1, weight=1, uniform="col")

        # COLUMNA 1: DASHBOARD
        dash_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        dash_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Tarjeta: IP
        card_ip = ctk.CTkFrame(dash_frame, fg_color=CARD_COLOR, corner_radius=CORNER_RADIUS)
        card_ip.pack(fill="x", pady=(0, 20), ipady=20)
        
        ctk.CTkLabel(card_ip, text="🌐 Servidor de Producción", font=get_font(size=16, weight="bold"), text_color=TEXT_SEC).pack(pady=(20, 5))
        self.lbl_ip = ctk.CTkLabel(card_ip, text="Cargando...", font=get_font(size=24, weight="bold"), text_color=SUCCESS_COLOR)
        self.lbl_ip.pack(pady=(0, 10))
        
        # Tarjeta: Almacenamiento
        card_storage = ctk.CTkFrame(dash_frame, fg_color=CARD_COLOR, corner_radius=CORNER_RADIUS)
        card_storage.pack(fill="x", ipady=20)
        
        ctk.CTkLabel(card_storage, text="💾 Almacenamiento (Ubuntu)", font=get_font(size=16, weight="bold"), text_color=TEXT_SEC).pack(pady=(20, 10))
        
        self.lbl_storage_uso = ctk.CTkLabel(card_storage, text="-- / --", font=get_font(size=28, weight="bold"), text_color=TEXT_MAIN)
        self.lbl_storage_uso.pack()
        
        self.progress_storage = ctk.CTkProgressBar(card_storage, width=300, height=12, progress_color=ACCENT_COLOR, fg_color=BG_COLOR)
        self.progress_storage.pack(pady=15)
        self.progress_storage.set(0)
        
        self.lbl_storage_detalles = ctk.CTkLabel(card_storage, text="Disponible: --", font=get_font(size=14), text_color=TEXT_SEC)
        self.lbl_storage_detalles.pack()

        # COLUMNA 2: GESTIÓN DE CATÁLOGOS
        cat_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        cat_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        card_cat = ctk.CTkFrame(cat_frame, fg_color=CARD_COLOR, corner_radius=CORNER_RADIUS)
        card_cat.pack(fill="both", expand=True, ipadx=30, ipady=30)
        
        ctk.CTkLabel(card_cat, text="Gestión de Catálogos", font=get_font(size=20, weight="bold"), text_color=TEXT_MAIN).pack(pady=(20, 30))

        # Botón Nuevo Usuario
        ctk.CTkButton(
            card_cat,
            text="➕ Registrar Nuevo Auditor",
            command=self._popup_nuevo_usuario,
            fg_color=ACCENT_COLOR,
            font=get_font(size=14, weight="bold"),
            height=50,
            corner_radius=8
        ).pack(fill="x", padx=40, pady=(0, 20))

        # Botón Nuevo Restaurante
        ctk.CTkButton(
            card_cat,
            text="➕ Registrar Nuevo Restaurante",
            command=self._popup_nuevo_restaurante,
            fg_color=ACCENT_COLOR,
            font=get_font(size=14, weight="bold"),
            height=50,
            corner_radius=8
        ).pack(fill="x", padx=40)

    def _volver(self):
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)

    def _cargar_metricas(self):
        def _fetch():
            data = obtener_system_info()
            if data:
                ip = data.get("ip", "Desconocida")
                storage = data.get("storage", {})
                
                usado = storage.get("usado", "N/A")
                total = storage.get("total", "N/A")
                disponible = storage.get("disponible", "N/A")
                porcentaje_str = storage.get("porcentaje", "0%").replace("%", "")
                
                try:
                    porcentaje_val = float(porcentaje_str) / 100.0
                except ValueError:
                    porcentaje_val = 0.0

                self.after(0, lambda: self._actualizar_dashboard(ip, usado, total, disponible, porcentaje_val))
            else:
                self.after(0, lambda: self.lbl_ip.configure(text="Error de Conexión", text_color=STATUS["error"]["text"]))
        
        import threading
        threading.Thread(target=_fetch, daemon=True).start()

    def _actualizar_dashboard(self, ip, usado, total, disponible, porcentaje_val):
        self.lbl_ip.configure(text=ip)
        self.lbl_storage_uso.configure(text=f"{usado} / {total}")
        self.lbl_storage_detalles.configure(text=f"Disponible: {disponible}")
        self.progress_storage.set(porcentaje_val)
        
        if porcentaje_val > 0.85:
            self.progress_storage.configure(progress_color="#ef4444") # Rojo si está lleno
        elif porcentaje_val > 0.70:
            self.progress_storage.configure(progress_color="#eab308") # Amarillo
        else:
            self.progress_storage.configure(progress_color=SUCCESS_COLOR)

    # ─── GESTIÓN (Migrada desde selection_frame) ───
    def _popup_nuevo_usuario(self):
        """Formulario completo para crear un auditor con credenciales y rol."""
        win = ctk.CTkToplevel(self.controlador)
        win.title("Registrar Nuevo Auditor")
        win.geometry("440x550")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.grab_set()
        win.configure(fg_color=BG_COLOR)

        inner = ctk.CTkFrame(win, fg_color=CARD_COLOR, corner_radius=12)
        inner.pack(padx=20, pady=20, fill="both", expand=True)

        ctk.CTkLabel(inner, text="Nuevo Auditor", font=get_font(size=18, weight="bold"),
                     text_color=TEXT_MAIN).pack(pady=(20, 20))

        def campo(label, placeholder, show=""):
            ctk.CTkLabel(inner, text=label, font=get_font(size=12, weight="bold"),
                         text_color=TEXT_SEC, anchor="w").pack(fill="x", padx=20)
            e = ctk.CTkEntry(inner, placeholder_text=placeholder, show=show,
                             fg_color=BG_COLOR, text_color=TEXT_MAIN, height=38,
                             corner_radius=8, font=get_font(size=13))
            e.pack(fill="x", padx=20, pady=(3, 10))
            return e

        entry_nombre = campo("Nombre completo", "Ej: Juan Pérez")
        entry_user   = campo("Usuario (login)", "Ej: jperez")
        entry_pass   = campo("Contraseña", "Mínimo 6 caracteres", show="•")

        ctk.CTkLabel(inner, text="Rol", font=get_font(size=12, weight="bold"),
                     text_color=TEXT_SEC, anchor="w").pack(fill="x", padx=20)
        combo_rol = ctk.CTkOptionMenu(inner, values=["EMPLEADO", "ADMIN"],
                                      fg_color=BG_COLOR, button_color=CARD_HOVER,
                                      text_color=TEXT_MAIN, corner_radius=8)
        combo_rol.set("EMPLEADO")
        combo_rol.pack(fill="x", padx=20, pady=(3, 16))

        lbl_err = ctk.CTkLabel(inner, text="", text_color=STATUS["error"]["text"],
                               font=get_font(size=12))
        lbl_err.pack()

        def _crear():
            nombre = entry_nombre.get().strip()
            username = entry_user.get().strip()
            password = entry_pass.get()
            role = combo_rol.get()

            if not nombre or not username or not password:
                lbl_err.configure(text="⚠ Todos los campos son obligatorios.")
                return
            if len(password) < 6:
                lbl_err.configure(text="⚠ La contraseña debe tener al menos 6 caracteres.")
                return

            btn_crear.configure(state="disabled", text="Guardando...")
            res = crear_usuario({"nombre": nombre, "username": username,
                                  "password": password, "role": role})
            if res:
                win.destroy()
                messagebox.showinfo("Éxito", f"Auditor '{nombre}' registrado correctamente.\nYa puede ingresar con el usuario '{username}'.")
            else:
                btn_crear.configure(state="normal", text="Registrar")
                lbl_err.configure(text="⚠ Error al guardar. Verifica tu conexión.")

        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(10, 20))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(btn_frame, text="Cancelar", command=win.destroy,
                      fg_color="transparent", border_width=1,
                      text_color=TEXT_SEC, width=120).grid(row=0, column=0, padx=10, sticky="e")
        btn_crear = ctk.CTkButton(btn_frame, text="Registrar",
                                  command=_crear, fg_color=ACCENT_COLOR,
                                  font=get_font(size=13, weight="bold"), width=120)
        btn_crear.grid(row=0, column=1, padx=10, sticky="w")

    def _popup_nuevo_restaurante(self):
        dialog = ctk.CTkInputDialog(text="Escribe el nombre del nuevo Restaurante:", title="Nuevo Restaurante")
        nombre = dialog.get_input()
        if nombre and nombre.strip():
            res = crear_restaurante({"nombre": nombre.strip()})
            if res:
                messagebox.showinfo("Éxito", f"Restaurante '{nombre.strip()}' creado correctamente.")
            else:
                messagebox.showerror("Error", "No se pudo crear el restaurante.")
