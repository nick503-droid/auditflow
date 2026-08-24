import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from api.client import obtener_usuarios, obtener_restaurantes

class SelectionFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, **kwargs):
        super().__init__(master, fg_color="#0f172a") # Fondo web oscuro moderno
        self.controlador = controlador  

        # Variables de estado
        self.usuario_seleccionado = None
        self.usuarios_data = {}
        
        self.restaurante_seleccionado = None
        self.restaurantes_data = {}

        self._construir_ui()
        self._cargar_catalogos()

    def _construir_ui(self):
        # Configurar un layout de Grid tipo Dashboard Web
        self.grid_columnconfigure(0, weight=0, minsize=280) # Sidebar izquierda (fija)
        self.grid_columnconfigure(1, weight=1)              # Área principal (expansible)
        self.grid_rowconfigure(0, weight=1)                 # Ocupar todo el alto

        # ==========================================
        # SIDEBAR (Barra lateral izquierda)
        # ==========================================
        self.sidebar = ctk.CTkFrame(self, fg_color="#1e293b", corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Logo / Marca
        ctk.CTkLabel(
            self.sidebar, 
            text="AuditFlow", 
            font=ctk.CTkFont(size=28, weight="bold"), 
            text_color="#38bdf8"
        ).pack(pady=(40, 5))
        
        ctk.CTkLabel(
            self.sidebar, 
            text="Control de Auditoría", 
            font=ctk.CTkFont(size=12), 
            text_color="gray60"
        ).pack(pady=(0, 40))

        # Selector de Usuario
        ctk.CTkLabel(
            self.sidebar, 
            text="👤 Selecciona tu usuario:", 
            font=ctk.CTkFont(weight="bold", size=13),
            text_color="gray80"
        ).pack(anchor="w", padx=30, pady=(10, 5))
        
        self.dropdown_usuario = ctk.CTkOptionMenu(
            self.sidebar, 
            values=["Cargando..."], 
            command=self._on_usuario_seleccionado,
            fg_color="#334155", button_color="#475569", button_hover_color="#64748b",
            height=35
        )
        self.dropdown_usuario.pack(padx=30, fill="x", pady=(0, 20))

        # (SE ELIMINÓ EL SELECTOR DE RESTAURANTE DE AQUÍ)

        # Versión en el fondo de la sidebar
        ctk.CTkLabel(
            self.sidebar, 
            text="Versión 2.0.2", 
            font=ctk.CTkFont(size=10), 
            text_color="gray40"
        ).pack(side="bottom", pady=20)


        # ==========================================
        # MAIN AREA (Área de contenido derecha)
        # ==========================================
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=50, pady=50)

        # Saludo Dinámico
        self.lbl_saludo = ctk.CTkLabel(
            self.main_area, 
            text="¡Hola! 👋", 
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color="white"
        )
        self.lbl_saludo.pack(anchor="w", pady=(0, 5))

        ctk.CTkLabel(
            self.main_area, 
            text="Selecciona tu perfil en la barra lateral y luego elige a dónde quieres ir.", 
            font=ctk.CTkFont(size=14),
            text_color="gray50"
        ).pack(anchor="w", pady=(0, 40))

        # --- Contenedor de Tarjetas (Grid) ---
        self.cards_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.cards_frame.pack(fill="both", expand=True)
        self.cards_frame.grid_columnconfigure(0, weight=1, uniform="card")
        self.cards_frame.grid_columnconfigure(1, weight=1, uniform="card")

        # TARJETA 1: Bitácoras
        self.card_bitacoras = ctk.CTkFrame(self.cards_frame, fg_color="#1e293b", corner_radius=12)
        self.card_bitacoras.grid(row=0, column=0, sticky="nsew", padx=(0, 15))

        ctk.CTkLabel(self.card_bitacoras, text="📅", font=ctk.CTkFont(size=40)).pack(pady=(25, 10))
        ctk.CTkLabel(self.card_bitacoras, text="Bitácoras", font=ctk.CTkFont(size=18, weight="bold")).pack()
        ctk.CTkLabel(self.card_bitacoras, text="Registro colaborativo del día", text_color="gray50").pack(pady=(0, 15))

        # Selector de Fecha (Dropdown Inteligente)
        self.fechas_disponibles = self._generar_fechas_recientes()
        self.dropdown_fecha = ctk.CTkOptionMenu(
            self.card_bitacoras,
            values=[f["display"] for f in self.fechas_disponibles],
            fg_color="#0f172a", button_color="#334155", button_hover_color="#475569"
        )
        self.dropdown_fecha.pack(pady=10, padx=30, fill="x")

        self.boton_bitacoras = ctk.CTkButton(
            self.card_bitacoras, 
            text="Abrir Bitácoras", 
            state="disabled", 
            command=self._abrir_bitacoras,
            height=40,
            fg_color="#0284c7", hover_color="#0369a1"
        )
        self.boton_bitacoras.pack(pady=(10, 25), padx=30, fill="x", side="bottom")


        # TARJETA 2: Reportes
        self.card_reportes = ctk.CTkFrame(self.cards_frame, fg_color="#1e293b", corner_radius=12)
        self.card_reportes.grid(row=0, column=1, sticky="nsew", padx=(15, 0))

        ctk.CTkLabel(self.card_reportes, text="📊", font=ctk.CTkFont(size=40)).pack(pady=(25, 10))
        ctk.CTkLabel(self.card_reportes, text="Reportes", font=ctk.CTkFont(size=18, weight="bold")).pack()
        ctk.CTkLabel(self.card_reportes, text="Auditorías individuales", text_color="gray50").pack(pady=(0, 15))

        # NUEVO: Selector de Restaurante movido aquí adentro
        self.dropdown_restaurante = ctk.CTkOptionMenu(
            self.card_reportes, 
            values=["Cargando..."], 
            command=self._on_restaurante_seleccionado,
            fg_color="#0f172a", button_color="#334155", button_hover_color="#475569",
            height=35
        )
        self.dropdown_restaurante.pack(pady=10, padx=30, fill="x")

        self.boton_reportes = ctk.CTkButton(
            self.card_reportes, 
            text="Crear / Continuar Reporte", 
            state="disabled", 
            command=self._abrir_reportes,
            height=40,
            fg_color="#7c3aed", hover_color="#6d28d9" # Morado moderno
        )
        self.boton_reportes.pack(pady=(10, 25), padx=30, fill="x", side="bottom")

    def _generar_fechas_recientes(self):
        """Genera una lista de las últimas 14 fechas para viajar en el tiempo fácilmente."""
        import datetime
        fechas = []
        hoy = datetime.date.today()
        
        for i in range(14):
            dia = hoy - datetime.timedelta(days=i)
            valor_iso = dia.strftime("%Y-%m-%d")
            
            if i == 0:
                display = f"Hoy ({valor_iso})"
            elif i == 1:
                display = f"Ayer ({valor_iso})"
            else:
                display = valor_iso
                
            fechas.append({"display": display, "valor": valor_iso})
            
        return fechas

    def _cargar_catalogos(self):
        # Cargar Usuarios
        usuarios = obtener_usuarios()
        if usuarios:
            self.usuarios_data = {u["nombre"]: u for u in usuarios}
            self.dropdown_usuario.configure(values=list(self.usuarios_data.keys()))
            self.dropdown_usuario.set("Selecciona...")
        else:
            self.usuarios_data = {}
            self.dropdown_usuario.configure(values=["Sin conexión"])

        # Cargar Restaurantes
        restaurantes = obtener_restaurantes()
        if restaurantes:
            self.restaurantes_data = {r["nombre"]: r for r in restaurantes}
            self.dropdown_restaurante.configure(values=list(self.restaurantes_data.keys()))
            self.dropdown_restaurante.set("Selecciona...")
        else:
            self.restaurantes_data = {}
            self.dropdown_restaurante.configure(values=["Sin conexión"])

    def _on_usuario_seleccionado(self, nombre_elegido):
        self.usuario_seleccionado = self.usuarios_data.get(nombre_elegido)
        if self.usuario_seleccionado:
            nombre = self.usuario_seleccionado["nombre"].split(" ")[0] # Primer nombre
            self.lbl_saludo.configure(text=f"¡Hola, {nombre}! 👋")
        self._validar_modulos()

    def _on_restaurante_seleccionado(self, nombre_elegido):
        self.restaurante_seleccionado = self.restaurantes_data.get(nombre_elegido)
        self._validar_modulos()

    def _validar_modulos(self):
        # Bitácoras ahora SOLO requiere usuario (el restaurante se elige en cada fila)
        if self.usuario_seleccionado:
            self.boton_bitacoras.configure(state="normal")
        else:
            self.boton_bitacoras.configure(state="disabled")

        # Reportes requiere AMBOS (Usuario + Restaurante de la tarjeta)
        if self.usuario_seleccionado and self.restaurante_seleccionado:
            self.boton_reportes.configure(state="normal")
        else:
            self.boton_reportes.configure(state="disabled")

    def _abrir_bitacoras(self):
        seleccion_display = self.dropdown_fecha.get()
        fecha_valor = next((f["valor"] for f in self.fechas_disponibles if f["display"] == seleccion_display), None)
        
        from ui.bitacoras_frame import BitacorasFrame
        self.controlador.mostrar_frame(
            BitacorasFrame,
            usuario=self.usuario_seleccionado,
            fecha=fecha_valor
        )

    def _abrir_reportes(self):
        from ui.reportes_frame import ReportesFrame
        self.controlador.mostrar_frame(
            ReportesFrame,
            usuario=self.usuario_seleccionado,
            restaurante=self.restaurante_seleccionado # Se envía el restaurante
        )