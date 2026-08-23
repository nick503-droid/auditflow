import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
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
        # Título Principal
        ctk.CTkLabel(
            self, text="AuditFlow - Inicio", font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=(30, 20))

        # 1. Selección de Videovigilante
        ctk.CTkLabel(self, text="1. Selecciona tu usuario:", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0))
        self.dropdown_usuario = ctk.CTkOptionMenu(
            self, values=["Cargando..."], command=self._on_usuario_seleccionado
        )
        self.dropdown_usuario.pack(pady=10, padx=40, fill="x")

        # Separador visual
        ctk.CTkFrame(self, height=2, fg_color="gray80").pack(fill="x", padx=40, pady=20)

        # 2. Módulo de Bitácoras (Requiere Fecha)
        self.frame_bitacoras = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_bitacoras.pack(pady=10, fill="x", padx=40)
        
        ctk.CTkLabel(
            self.frame_bitacoras, text="2. Módulo de Bitácoras colaborativas:"
        ).pack(anchor="w", pady=(0, 5))
        
        # ELIMINADO: Campo de texto manual para la fecha
        # AÑADIDO: Menú desplegable dinámico con los últimos 15 días
        from datetime import timedelta
        hoy = datetime.now()
        
        self.fechas_disponibles = []
        opciones_mostrar = []
        
        for i in range(15):  # Mostrar historial de los últimos 15 días
            dia = hoy - timedelta(days=i)
            fecha_str = dia.strftime("%Y-%m-%d")
            self.fechas_disponibles.append(fecha_str)
            
            # Formatear bonito para el usuario
            if i == 0:
                opciones_mostrar.append(f"Hoy ({fecha_str})")
            elif i == 1:
                opciones_mostrar.append(f"Ayer ({fecha_str})")
            else:
                opciones_mostrar.append(fecha_str)

        self.combo_fecha = ctk.CTkOptionMenu(
            self.frame_bitacoras, 
            values=opciones_mostrar,
            dropdown_font=ctk.CTkFont(size=12)
        )
        self.combo_fecha.set(opciones_mostrar[0]) # Por defecto "Hoy"
        self.combo_fecha.pack(fill="x", pady=(0, 10))

        self.boton_bitacoras = ctk.CTkButton(
            self.frame_bitacoras, 
            text="📝 Abrir Bitácoras", 
            state="disabled", 
            command=self._on_bitacoras
        )
        self.boton_bitacoras.pack(fill="x")

        # Separador visual
        ctk.CTkFrame(self, height=2, fg_color="gray80").pack(fill="x", padx=40, pady=20)

        # 3. Módulo de Reportes
        self.frame_reportes = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_reportes.pack(pady=10, fill="x", padx=40)

        ctk.CTkLabel(
            self.frame_reportes, text="3. Módulo de Reportes individuales:"
        ).pack(anchor="w", pady=(0, 5))

        self.boton_reportes = ctk.CTkButton(
            self.frame_reportes, 
            text="📊 Crear Reporte", 
            state="disabled", 
            command=self._on_reportes,
            fg_color="#8e44ad", hover_color="#732d91"
        )
        self.boton_reportes.pack(fill="x")

    def _cargar_catalogos(self):
        usuarios = obtener_usuarios()

        if usuarios:
            self.usuarios_data = {u["nombre"]: u for u in usuarios}
            self.dropdown_usuario.configure(values=list(self.usuarios_data.keys()))
            self.dropdown_usuario.set("Selecciona...")
        else:
            self.usuarios_data = {}
            self.dropdown_usuario.configure(values=["Sin conexión al servidor"])

    def _on_usuario_seleccionado(self, nombre_elegido):
        self.usuario_seleccionado = self.usuarios_data.get(nombre_elegido)
        
        # Habilitar los botones de los módulos solo cuando se elige un usuario válido
        if self.usuario_seleccionado:
            self.boton_bitacoras.configure(state="normal")
            self.boton_reportes.configure(state="normal")

    def _on_bitacoras(self):
        # Obtener el texto que seleccionó el usuario ("Hoy...", "Ayer...", etc)
        seleccion = self.combo_fecha.get()
        
        # Extraer la fecha real "YYYY-MM-DD" del texto seleccionado usando expresiones regulares
        import re
        match = re.search(r'\d{4}-\d{2}-\d{2}', seleccion)
        
        if match:
            fecha_exacta = match.group()
        else:
            fecha_exacta = datetime.now().strftime("%Y-%m-%d")

        from ui.bitacoras_frame import BitacorasFrame

        # Navegar a la pantalla de Bitácoras pasándole el usuario y la fecha exacta seleccionada
        self.controlador.mostrar_frame(
            BitacorasFrame,
            usuario=self.usuario_seleccionado,
            fecha=fecha_exacta
        )

    def _on_reportes(self):
        from ui.reportes_frame import ReportesFrame
        
        # Navegar a la pantalla de Reportes
        self.controlador.mostrar_frame(
            ReportesFrame,
            usuario=self.usuario_seleccionado
        )