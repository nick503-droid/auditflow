import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime
import keyboard
from api.client import crear_bitacora, subir_archivo
from core.recorder import GrabadorPantalla
import os
from core.recorder import es_archivo_grabado


class BitacorasFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, restaurante, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.usuario = usuario
        self.restaurante = restaurante

        self.ruta_evidencia = None
        self.grabador = GrabadorPantalla()
        self.grabando = False
        self.indicador = None

        self._construir_ui()
        self._registrar_hotkeys()

        self.bind("<Destroy>", self._al_destruir)

    def _construir_ui(self):
        ctk.CTkLabel(
            self,
            text=f"{self.usuario['nombre']} — {self.restaurante['nombre']}",
            font=ctk.CTkFont(size=14),
            text_color="gray70",
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            self, text="Nueva Bitácora", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=(0, 15))

        ctk.CTkLabel(self, text="Descripción del evento:").pack(anchor="w", padx=30)
        self.textbox_descripcion = ctk.CTkTextbox(self, height=90)
        self.textbox_descripcion.pack(pady=(5, 15), padx=30, fill="x")

        self.switch_audio = ctk.CTkSwitch(self, text="Grabar con audio")
        self.switch_audio.pack(pady=(0, 15), padx=30, anchor="w")
        self.switch_audio.deselect()

        self.boton_grabar = ctk.CTkButton(
            self,
            text="🔴 Grabar pantalla (Ctrl+K+L)",
            command=self._toggle_grabacion,
            fg_color="#c0392b",
        )
        self.boton_grabar.pack(pady=(0, 5), padx=30, fill="x")

        self.boton_adjuntar = ctk.CTkButton(
            self, text="📎 O adjuntar archivo existente", command=self._on_adjuntar,
            fg_color="transparent", border_width=1,
        )
        self.boton_adjuntar.pack(pady=(0, 5), padx=30, fill="x")

        self.label_archivo = ctk.CTkLabel(
            self, text="Sin evidencia adjuntada", text_color="gray60"
        )
        self.label_archivo.pack(pady=(0, 20))

        self.boton_guardar = ctk.CTkButton(
            self, text="Guardar Bitácora", command=self._on_guardar
        )
        self.boton_guardar.pack(pady=10, padx=30, fill="x")

        ctk.CTkButton(
            self, text="← Cambiar usuario/restaurante", fg_color="transparent",
            border_width=1, command=self._on_volver,
        ).pack(pady=(20, 10))

    def _registrar_hotkeys(self):
        keyboard.add_hotkey("ctrl+k+l", self._toggle_grabacion)

    def _al_destruir(self, event):
        keyboard.remove_hotkey("ctrl+k+l")
        self._ocultar_indicador_rec()

    def _toggle_grabacion(self):
        if self.grabando:
            self._detener_grabacion()
        else:
            self._iniciar_grabacion()

    def _iniciar_grabacion(self):
        con_audio = bool(self.switch_audio.get())
        self.ruta_evidencia = self.grabador.iniciar(con_audio=con_audio)
        self.grabando = True

        # Regla de negocio: la interfaz se oculta al grabar
        self.controlador.withdraw()
        self._mostrar_indicador_rec()

    def _detener_grabacion(self):
        self.grabador.detener()
        self.grabando = False

        self._ocultar_indicador_rec()

        # Se restaura la interfaz al detener
        self.controlador.deiconify()
        self.controlador.lift()

        nombre_archivo = self.ruta_evidencia.split("\\")[-1]
        self.label_archivo.configure(text=f"✅ Grabado: {nombre_archivo}")

    def _mostrar_indicador_rec(self):
        """Ventanita flotante, sin bordes, siempre encima, para confirmar
        que SÍ está grabando aunque la app principal esté oculta."""
        self.indicador = ctk.CTkToplevel(self.controlador)
        self.indicador.overrideredirect(True)
        self.indicador.attributes("-topmost", True)

        ancho, alto = 190, 40
        x = self.indicador.winfo_screenwidth() - ancho - 20
        y = 20
        self.indicador.geometry(f"{ancho}x{alto}+{x}+{y}")

        ctk.CTkLabel(
            self.indicador,
            text="🔴 Grabando (Ctrl+K+L)",
            fg_color="#1a1a1a",
            text_color="white",
        ).pack(fill="both", expand=True)

    def _ocultar_indicador_rec(self):
        if self.indicador is not None:
            self.indicador.destroy()
            self.indicador = None

    def _on_adjuntar(self):
        ruta = filedialog.askopenfilename(
            title="Selecciona la evidencia",
            filetypes=[("Videos e imágenes", "*.mp4 *.jpg *.jpeg *.png")],
        )
        if ruta:
            self.ruta_evidencia = ruta
            nombre_archivo = ruta.split("/")[-1].split("\\")[-1]
            self.label_archivo.configure(text=f"✅ {nombre_archivo}")

    def _on_guardar(self):
        descripcion = self.textbox_descripcion.get("1.0", "end").strip()

        if not descripcion:
            messagebox.showwarning("Falta información", "La descripción es obligatoria.")
            return

        self.boton_guardar.configure(state="disabled", text="Guardando...")
        self.update()

        evidencia_url = None
        if self.ruta_evidencia:
            evidencia_url, error = subir_archivo(self.ruta_evidencia)
            if evidencia_url is None:
                messagebox.showerror("Error", f"No se pudo subir el archivo de evidencia.\n\nMotivo: {error}")
                self.boton_guardar.configure(state="normal", text="Guardar Bitácora")
                return

        dto = {
            "usuario_id": self.usuario["id"],
            "restaurante_id": self.restaurante["id"],
            "descripcion": descripcion,
            "evidencia_url": evidencia_url,
            "con_audio": bool(self.switch_audio.get()),
            "fecha_hora_evento": datetime.now().isoformat(),
        }

        resultado = crear_bitacora(dto)

        resultado = crear_bitacora(dto)

        if resultado:
            # Limpieza: si el archivo era una grabación nuestra (no algo
            # que el usuario adjuntó de su propia PC), ya se subió a
            # MinIO con éxito, así que el local ya no hace falta
            if self.ruta_evidencia and es_archivo_grabado(self.ruta_evidencia):
                try:
                    os.remove(self.ruta_evidencia)
                except OSError:
                    pass  # si por alguna razón no se pudo borrar, no es crítico

            messagebox.showinfo("Listo", "Bitácora guardada correctamente.")
            self._resetear_formulario()
        else:
            messagebox.showerror("Error", "No se pudo guardar la bitácora.")

        self.boton_guardar.configure(state="normal", text="Guardar Bitácora")

    def _resetear_formulario(self):
        self.textbox_descripcion.delete("1.0", "end")
        self.switch_audio.deselect()
        self.ruta_evidencia = None
        self.label_archivo.configure(text="Sin evidencia adjuntada")

    def _on_volver(self):
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)