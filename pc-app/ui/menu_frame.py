import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime, timedelta
import re
from api.client import obtener_usuarios

class SelectionFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, **kwargs):
        super().__init__(master)
        self.controlador = controlador  # referencia a MainWindow, para navegar

        self.usuario_seleccionado = None
        self.usuarios_data = {}

        self._construir_ui()
        self._cargar_catalogos()

    def _construir_ui(self):
        # 1. Hacer que este frame se expanda para llenar toda la pantalla
        self.pack(fill="both", expand=True)
        
        # 2. Crear una "Tarjeta" que flotará en el centro de la pantalla
        # Usamos place(relx=0.5, rely=0.5) para mantenerla anclada al centro absoluto
        self.tarjeta = ctk.CTkFrame(self, corner_radius=15, fg_color=("#ffffff", "#1e212b"))
        self.tarjeta.place(relx=0.5, rely=0.5, anchor="center")
        
        # --- Contenido de la Tarjeta ---

        # Título Principal y Bienvenida
        ctk.CTkLabel(
            self.tarjeta, text="👋 ¡Bienvenido a AuditFlow!", 
            font=ctk.CTkFont(size=28, weight="bold")
        ).pack(pady=(40, 5), padx=60)
        
        ctk.CTkLabel(
            self.tarjeta, text="Sistema de Control de Auditoría y Videovigilancia", 
            font=ctk.CTkFont(size=14), text_color="gray60"
        ).pack(pady=(0, 30))

        # --- SECCIÓN 1: USUARIO ---
        self.frame_usuario = ctk.CTkFrame(self.tarjeta, fg_color="transparent")
        self.frame_usuario.pack(fill="x", padx=40, pady=(0, 20))
        
        ctk.CTkLabel(
            self.frame_usuario, text="1. 👤 ¿Quién eres?", 
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", pady=(0, 10))
        
        self.dropdown_usuario = ctk.CTkOptionMenu(
            self.frame_usuario, values=["Cargando usuarios..."], 
            command=self._on_usuario_seleccionado,
            height=35, font=ctk.CTkFont(size=14), corner_radius=8
        )
        self.dropdown_usuario.pack(fill="x")

        # Separador
        ctk.CTkFrame(self.tarjeta, height=2, fg_color=("#e5e7eb", "#2d3748")).pack(fill="x", padx=40, pady=10)

        # --- SECCIÓN 2: BITÁCORAS ---
        self.frame_bitacoras = ctk.CTkFrame(self.tarjeta, fg_color="transparent")
        self.frame_bitacoras.pack(fill="x", padx=40, pady=15)
        
        ctk.CTkLabel(
            self.frame_bitacoras, text="2. 📅 Bitácoras Colaborativas", 
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", pady=(0, 10))
        
        ctk.CTkLabel(
            self.frame_bitacoras, text="Elige un día para ver o registrar eventos:", 
            font=ctk.CTkFont(size=12), text_color="gray60"
        ).pack(anchor="w", pady=(0, 5))

        # Configurar menú de fechas (Últimos 15 días)
        hoy = datetime.now()
        opciones_mostrar = []
        for i in range(15):
            dia = hoy - timedelta(days=i)
            fecha_str = dia.strftime("%Y-%m-%d")
            if i == 0: opciones_mostrar.append(f"Hoy ({fecha_str})")
            elif i == 1: opciones_mostrar.append(f"Ayer ({fecha_str})")
            else: opciones_mostrar.append(fecha_str)

        self.combo_fecha = ctk.CTkOptionMenu(
            self.frame_bitacoras, values=opciones_mostrar, 
            height=35, font=ctk.CTkFont(size=13), corner_radius=8
        )
        self.combo_fecha.set(opciones_mostrar[0]) 
        self.combo_fecha.pack(fill="x", pady=(0, 15))

        self.boton_bitacoras = ctk.CTkButton(
            self.frame_bitacoras, text="📝 Abrir Bitácora", 
            state="disabled", height=40, font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8, fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._on_bitacoras
        )
        self.boton_bitacoras.pack(fill="x")

        # Separador
        ctk.CTkFrame(self.tarjeta, height=2, fg_color=("#e5e7eb", "#2d3748")).pack(fill="x", padx=40, pady=10)

        # --- SECCIÓN 3: REPORTES ---
        self.frame_reportes = ctk.CTkFrame(self.tarjeta, fg_color="transparent")
        self.frame_reportes.pack(fill="x", padx=40, pady=(15, 40))

        ctk.CTkLabel(
            self.frame_reportes, text="3. 📊 Reportes de Auditoría", 
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", pady=(0, 10))

        self.boton_reportes = ctk.CTkButton(
            self.frame_reportes, text="Crear Reporte Individual", 
            state="disabled", height=40, font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8, fg_color="#7c3aed", hover_color="#6d28d9",
            command=self._on_reportes
        )
        self.boton_reportes.pack(fill="x")

    def _cargar_catalogos(self):
        usuarios = obtener_usuarios()
        if usuarios:
            self.usuarios_data = {u["nombre"]: u for u in usuarios}
            self.dropdown_usuario.configure(values=list(self.usuarios_data.keys()))
            self.dropdown_usuario.set("Selecciona tu nombre...")
        else:
            self.usuarios_data = {}
            self.dropdown_usuario.configure(values=["Sin conexión al servidor"])

    def _on_usuario_seleccionado(self, nombre_elegido):
        self.usuario_seleccionado = self.usuarios_data.get(nombre_elegido)
        
        # Habilitar los botones con un tono visual atractivo
        if self.usuario_seleccionado:
            self.boton_bitacoras.configure(state="normal")
            self.boton_reportes.configure(state="normal")

    def _on_bitacoras(self):
        seleccion = self.combo_fecha.get()
        match = re.search(r'\d{4}-\d{2}-\d{2}', seleccion)
        fecha_exacta = match.group() if match else datetime.now().strftime("%Y-%m-%d")

        from ui.bitacoras_frame import BitacorasFrame
        self.controlador.mostrar_frame(
            BitacorasFrame,
            usuario=self.usuario_seleccionado,
            fecha=fecha_exacta
        )

    def _on_reportes(self):
        from ui.reportes_frame import ReportesFrame
        self.controlador.mostrar_frame(
            ReportesFrame,
            usuario=self.usuario_seleccionado
        )