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
        
        # Campo de fecha pre-llenado con la fecha de hoy
        self.entry_fecha = ctk.CTkEntry(self.frame_bitacoras, justify="center")
        self.entry_fecha.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.entry_fecha.pack(fill="x", pady=(0, 10))

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
        fecha = self.entry_fecha.get().strip()
        
        # Validar que la fecha tenga el formato correcto para no romper el backend
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Fecha inválida", "Por favor usa el formato exacto: YYYY-MM-DD")
            return

        from ui.bitacoras_frame import BitacorasFrame

        # Navegar a la pantalla de Bitácoras pasándole el usuario y la fecha validada
        self.controlador.mostrar_frame(
            BitacorasFrame,
            usuario=self.usuario_seleccionado,
            fecha=fecha
        )

    def _on_reportes(self):
        from ui.reportes_frame import ReportesFrame
        
        # Navegar a la pantalla de Reportes
        self.controlador.mostrar_frame(
            ReportesFrame,
            usuario=self.usuario_seleccionado
        )