import customtkinter as ctk
from api.client import obtener_usuarios, obtener_restaurantes


class SelectionFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, **kwargs):
        super().__init__(master)
        self.controlador = controlador  # referencia a MainWindow, para navegar

        self.usuario_seleccionado = None
        self.restaurante_seleccionado = None

        self._construir_ui()
        self._cargar_catalogos()

    def _construir_ui(self):
        ctk.CTkLabel(
            self, text="AuditFlow", font=ctk.CTkFont(size=24, weight="bold")
        ).pack(pady=(30, 20))

        ctk.CTkLabel(self, text="Selecciona tu nombre:").pack(pady=(10, 0))
        self.dropdown_usuario = ctk.CTkOptionMenu(
            self, values=["Cargando..."], command=self._on_usuario_seleccionado
        )
        self.dropdown_usuario.pack(pady=10, padx=40, fill="x")

        ctk.CTkLabel(self, text="Selecciona el restaurante:").pack(pady=(10, 0))
        self.dropdown_restaurante = ctk.CTkOptionMenu(
            self, values=["Cargando..."], command=self._on_restaurante_seleccionado
        )
        self.dropdown_restaurante.pack(pady=10, padx=40, fill="x")

        self.boton_continuar = ctk.CTkButton(
            self, text="Continuar", state="disabled", command=self._on_continuar
        )
        self.boton_continuar.pack(pady=30)

    def _cargar_catalogos(self):
        usuarios = obtener_usuarios()
        restaurantes = obtener_restaurantes()

        if usuarios:
            self.usuarios_data = {u["nombre"]: u for u in usuarios}
            self.dropdown_usuario.configure(values=list(self.usuarios_data.keys()))
            self.dropdown_usuario.set("Selecciona...")
        else:
            self.usuarios_data = {}
            self.dropdown_usuario.configure(values=["Sin conexión al servidor"])

        if restaurantes:
            self.restaurantes_data = {r["nombre"]: r for r in restaurantes}
            self.dropdown_restaurante.configure(values=list(self.restaurantes_data.keys()))
            self.dropdown_restaurante.set("Selecciona...")
        else:
            self.restaurantes_data = {}
            self.dropdown_restaurante.configure(values=["Sin conexión al servidor"])

    def _on_usuario_seleccionado(self, nombre_elegido):
        self.usuario_seleccionado = self.usuarios_data.get(nombre_elegido)
        self._validar_seleccion_completa()

    def _on_restaurante_seleccionado(self, nombre_elegido):
        self.restaurante_seleccionado = self.restaurantes_data.get(nombre_elegido)
        self._validar_seleccion_completa()

    def _validar_seleccion_completa(self):
        if self.usuario_seleccionado and self.restaurante_seleccionado:
            self.boton_continuar.configure(state="normal")

    def _on_continuar(self):
        from ui.menu_frame import MenuFrame

        self.controlador.mostrar_frame(
            MenuFrame,
            usuario=self.usuario_seleccionado,
            restaurante=self.restaurante_seleccionado,
        )