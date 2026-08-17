import customtkinter as ctk


class MenuFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, restaurante, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.usuario = usuario
        self.restaurante = restaurante

        self._construir_ui()

    def _construir_ui(self):
        ctk.CTkLabel(
            self,
            text=f"{self.usuario['nombre']} — {self.restaurante['nombre']}",
            font=ctk.CTkFont(size=14),
            text_color="gray70",
        ).pack(pady=(30, 10))

        ctk.CTkLabel(
            self, text="¿Qué quieres registrar?", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=(0, 30))

        ctk.CTkButton(
            self, text="📝 Nueva Bitácora", height=50,
            command=self._ir_a_bitacoras,
        ).pack(pady=10, padx=50, fill="x")

        ctk.CTkButton(
            self, text="📋 Reporte del día", height=50,
            command=self._ir_a_reportes,
        ).pack(pady=10, padx=50, fill="x")

        ctk.CTkButton(
            self, text="← Cambiar usuario/restaurante", fg_color="transparent",
            border_width=1, command=self._on_volver,
        ).pack(pady=(30, 10))

    def _ir_a_bitacoras(self):
        from ui.bitacoras_frame import BitacorasFrame
        self.controlador.mostrar_frame(
            BitacorasFrame, usuario=self.usuario, restaurante=self.restaurante
        )

    def _ir_a_reportes(self):
        from ui.reportes_frame import ReportesFrame
        self.controlador.mostrar_frame(
            ReportesFrame, usuario=self.usuario, restaurante=self.restaurante
        )

    def _on_volver(self):
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)