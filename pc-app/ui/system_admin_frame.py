import customtkinter as ctk
from tkinter import messagebox
from api.client import obtener_system_info, crear_usuario, crear_restaurante

# ─── SISTEMA DE DISEÑO ───────────────────────────────────────────────────────
BG_COLOR = "#0f172a"
CARD_COLOR = "#1e293b"
CARD_HOVER = "#334155"
TEXT_MAIN = "#f8fafc"
TEXT_SEC = "#94a3b8"
ACCENT_COLOR = "#4f46e5"
SUCCESS_COLOR = "#10b981"
CORNER_RADIUS = 15

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
            font=ctk.CTkFont(size=14, weight="bold"),
            width=80
        ).pack(side="left")

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=20)
        
        ctk.CTkLabel(
            title_box, 
            text="Administración del Sistema", 
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=TEXT_MAIN
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box, 
            text="Métricas del servidor Ubuntu y gestión de catálogos", 
            font=ctk.CTkFont(size=14),
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
        
        ctk.CTkLabel(card_ip, text="🌐 Servidor de Producción", font=ctk.CTkFont(size=16, weight="bold"), text_color=TEXT_SEC).pack(pady=(20, 5))
        self.lbl_ip = ctk.CTkLabel(card_ip, text="Cargando...", font=ctk.CTkFont(size=24, weight="bold"), text_color=SUCCESS_COLOR)
        self.lbl_ip.pack(pady=(0, 10))
        
        # Tarjeta: Almacenamiento
        card_storage = ctk.CTkFrame(dash_frame, fg_color=CARD_COLOR, corner_radius=CORNER_RADIUS)
        card_storage.pack(fill="x", ipady=20)
        
        ctk.CTkLabel(card_storage, text="💾 Almacenamiento (Ubuntu)", font=ctk.CTkFont(size=16, weight="bold"), text_color=TEXT_SEC).pack(pady=(20, 10))
        
        self.lbl_storage_uso = ctk.CTkLabel(card_storage, text="-- / --", font=ctk.CTkFont(size=28, weight="bold"), text_color=TEXT_MAIN)
        self.lbl_storage_uso.pack()
        
        self.progress_storage = ctk.CTkProgressBar(card_storage, width=300, height=12, progress_color=ACCENT_COLOR, fg_color=BG_COLOR)
        self.progress_storage.pack(pady=15)
        self.progress_storage.set(0)
        
        self.lbl_storage_detalles = ctk.CTkLabel(card_storage, text="Disponible: --", font=ctk.CTkFont(size=14), text_color=TEXT_SEC)
        self.lbl_storage_detalles.pack()

        # COLUMNA 2: GESTIÓN DE CATÁLOGOS
        cat_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        cat_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        card_cat = ctk.CTkFrame(cat_frame, fg_color=CARD_COLOR, corner_radius=CORNER_RADIUS)
        card_cat.pack(fill="both", expand=True, ipadx=30, ipady=30)
        
        ctk.CTkLabel(card_cat, text="Gestión de Catálogos", font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT_MAIN).pack(pady=(20, 30))

        # Botón Nuevo Usuario
        ctk.CTkButton(
            card_cat,
            text="➕ Registrar Nuevo Auditor",
            command=self._popup_nuevo_usuario,
            fg_color=ACCENT_COLOR,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=50,
            corner_radius=8
        ).pack(fill="x", padx=40, pady=(0, 20))

        # Botón Nuevo Restaurante
        ctk.CTkButton(
            card_cat,
            text="➕ Registrar Nuevo Restaurante",
            command=self._popup_nuevo_restaurante,
            fg_color=ACCENT_COLOR,
            font=ctk.CTkFont(size=14, weight="bold"),
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
                self.after(0, lambda: self.lbl_ip.configure(text="Error de Conexión", text_color="#ef4444"))
        
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
        dialog = ctk.CTkInputDialog(text="Escribe el nombre del nuevo Auditor:", title="Nuevo Usuario")
        nombre = dialog.get_input()
        if nombre and nombre.strip():
            res = crear_usuario({"nombre": nombre.strip()})
            if res:
                messagebox.showinfo("Éxito", f"Usuario '{nombre.strip()}' creado correctamente.")
            else:
                messagebox.showerror("Error", "No se pudo crear el usuario. Verifica tu conexión.")

    def _popup_nuevo_restaurante(self):
        dialog = ctk.CTkInputDialog(text="Escribe el nombre del nuevo Restaurante:", title="Nuevo Restaurante")
        nombre = dialog.get_input()
        if nombre and nombre.strip():
            res = crear_restaurante({"nombre": nombre.strip()})
            if res:
                messagebox.showinfo("Éxito", f"Restaurante '{nombre.strip()}' creado correctamente.")
            else:
                messagebox.showerror("Error", "No se pudo crear el restaurante.")
