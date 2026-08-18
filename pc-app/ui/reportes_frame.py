import customtkinter as ctk
from tkinter import filedialog, messagebox
import keyboard
from db.local_db import (
    obtener_o_crear_borrador,
    actualizar_notas,
    agregar_evidencia,
    obtener_evidencias,
    eliminar_borrador_completo,
)
from api.client import crear_reporte, crear_evidencia_reporte, subir_archivo
from core.recorder import GrabadorPantalla, es_archivo_grabado
import os


class ReportesFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, restaurante=None, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.usuario = usuario
        # Creamos un restaurante "falso" por si el código más abajo intenta leer su nombre
        self.restaurante = restaurante or {"id": "0", "nombre": "Restaurante (Pendiente)"}

        # Carga (o crea) el borrador de HOY para este usuario+restaurante.
        # Esto es lo que hace posible continuar un reporte a medias.
        self.borrador = obtener_o_crear_borrador(usuario["id"], restaurante["id"])

        self.grabador = GrabadorPantalla()
        self.grabando = False
        self.indicador = None

        # Referencia al 'after' pendiente, para poder cancelarlo (debounce)
        self._debounce_id = None

        self._construir_ui()
        self._cargar_estado_previo()
        self._registrar_hotkeys()
        self.bind("<Destroy>", self._al_destruir)

    def _construir_ui(self):
        ctk.CTkLabel(
            self,
            text=f"{self.usuario['nombre']} — {self.restaurante['nombre']}",
            font=ctk.CTkFont(size=14),
            text_color="gray70",
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            self, text="Reporte del día", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=(0, 5))

        self.label_estado_guardado = ctk.CTkLabel(
            self, text="", text_color="gray50", font=ctk.CTkFont(size=11)
        )
        self.label_estado_guardado.pack(pady=(0, 10))

        ctk.CTkLabel(self, text="Notas finales:").pack(anchor="w", padx=30)
        self.textbox_notas = ctk.CTkTextbox(self, height=150)
        self.textbox_notas.pack(pady=(5, 15), padx=30, fill="both", expand=False)
        # Cada vez que se suelta una tecla, dispara el debounce
        self.textbox_notas.bind("<KeyRelease>", self._on_texto_cambiado)

        self.boton_grabar = ctk.CTkButton(
            self, text="🔴 Grabar evidencia (Ctrl+K+L)",
            command=self._toggle_grabacion, fg_color="#c0392b",
        )
        self.boton_grabar.pack(pady=(0, 5), padx=30, fill="x")

        ctk.CTkButton(
            self, text="📎 O adjuntar archivo existente", command=self._on_adjuntar,
            fg_color="transparent", border_width=1,
        ).pack(pady=(0, 10), padx=30, fill="x")

        ctk.CTkLabel(self, text="Evidencias agregadas:").pack(anchor="w", padx=30)
        self.frame_lista_evidencias = ctk.CTkScrollableFrame(self, height=80)
        self.frame_lista_evidencias.pack(pady=(5, 15), padx=30, fill="x")

        self.boton_finalizar = ctk.CTkButton(
            self, text="✅ Finalizar Reporte del Día", command=self._on_finalizar,
        )
        self.boton_finalizar.pack(pady=10, padx=30, fill="x")

        ctk.CTkButton(
            self, text="← Volver al menú", fg_color="transparent",
            border_width=1, command=self._on_volver,
        ).pack(pady=(15, 10))

    def _cargar_estado_previo(self):
        """Si ya había texto o evidencias guardadas, las muestra al abrir."""
        if self.borrador["notas_finales"]:
            self.textbox_notas.insert("1.0", self.borrador["notas_finales"])

        self._refrescar_lista_evidencias()

    def _refrescar_lista_evidencias(self):
        for widget in self.frame_lista_evidencias.winfo_children():
            widget.destroy()

        evidencias = obtener_evidencias(self.borrador["id"])
        if not evidencias:
            ctk.CTkLabel(
                self.frame_lista_evidencias, text="Sin evidencias todavía",
                text_color="gray50",
            ).pack(pady=10)
            return

        for ev in evidencias:
            nombre = ev["ruta_local"].split("\\")[-1].split("/")[-1]
            texto = f"{ev['orden_reproduccion']}. {nombre}"
            if ev["con_audio"]:
                texto += " 🔊"
            ctk.CTkLabel(self.frame_lista_evidencias, text=texto, anchor="w").pack(
                fill="x", padx=5, pady=2
            )

    def _on_texto_cambiado(self, event):
        """Debounce: cancela el guardado pendiente y programa uno nuevo."""
        if self._debounce_id is not None:
            self.after_cancel(self._debounce_id)

        self.label_estado_guardado.configure(text="Escribiendo...")
        self._debounce_id = self.after(1500, self._guardar_notas_ahora)

    def _guardar_notas_ahora(self):
        texto = self.textbox_notas.get("1.0", "end").strip()
        actualizar_notas(self.borrador["id"], texto)
        self.label_estado_guardado.configure(text="✅ Guardado automáticamente")
        self._debounce_id = None

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
        self.ruta_temp = self.grabador.iniciar(con_audio=False)
        self.grabando = True
        self.controlador.withdraw()
        self._mostrar_indicador_rec()

    def _detener_grabacion(self):
        ruta_final = self.grabador.detener()
        self.grabando = False
        self._ocultar_indicador_rec()
        self.controlador.deiconify()
        self.controlador.lift()

        # A diferencia de Bitácoras, aquí SÍ guardamos de inmediato en
        # SQLite local (no se sube a MinIO todavía, eso es al finalizar)
        agregar_evidencia(self.borrador["id"], ruta_final, con_audio=False)
        self._refrescar_lista_evidencias()

    def _mostrar_indicador_rec(self):
        self.indicador = ctk.CTkToplevel(self.controlador)
        self.indicador.overrideredirect(True)
        self.indicador.attributes("-topmost", True)
        ancho, alto = 190, 40
        x = self.indicador.winfo_screenwidth() - ancho - 20
        self.indicador.geometry(f"{ancho}x{alto}+{x}+20")
        ctk.CTkLabel(
            self.indicador, text="🔴 Grabando (Ctrl+K+L)",
            fg_color="#1a1a1a", text_color="white",
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
            agregar_evidencia(self.borrador["id"], ruta, con_audio=False)
            self._refrescar_lista_evidencias()

    def _on_finalizar(self):
        evidencias = obtener_evidencias(self.borrador["id"])
        notas = self.textbox_notas.get("1.0", "end").strip()

        if not notas:
            messagebox.showwarning("Falta información", "Las notas finales son obligatorias.")
            return

        respuesta = messagebox.askyesno(
            "Confirmar", f"¿Enviar el reporte con {len(evidencias)} evidencia(s)? "
                         "Esto puede tardar si hay videos pesados."
        )
        if not respuesta:
            return

        self.boton_finalizar.configure(state="disabled", text="Enviando...")
        self.update()

        # 1. Crear el reporte en el backend real
        dto_reporte = {
            "usuario_id": self.usuario["id"],
            "restaurante_id": self.restaurante["id"],
            "notas_finales": notas,
            "fecha_jornada": self.borrador["fecha_jornada"],
        }
        reporte_creado = crear_reporte(dto_reporte)

        if not reporte_creado:
            messagebox.showerror("Error", "No se pudo crear el reporte. Tu borrador sigue guardado localmente.")
            self.boton_finalizar.configure(state="normal", text="✅ Finalizar Reporte del Día")
            return

        # 2. Subir cada evidencia y registrarla contra el reporte recién creado
        for ev in evidencias:
            url_subida, error = subir_archivo(ev["ruta_local"])
            if url_subida is None:
                messagebox.showwarning(
                    "Evidencia no subida",
                    f"No se pudo subir: {ev['ruta_local']}\n\nMotivo: {error}",
                )
                continue

            crear_evidencia_reporte({
                "reporte_id": reporte_creado["id"],
                "evidencia_url": url_subida,
                "con_audio": bool(ev["con_audio"]),
                "orden_reproduccion": ev["orden_reproduccion"],
            })

            if es_archivo_grabado(ev["ruta_local"]):
                try:
                    os.remove(ev["ruta_local"])
                except OSError:
                    pass

        # 3. Todo enviado: borra el borrador local completo
        eliminar_borrador_completo(self.borrador["id"])

        messagebox.showinfo("Listo", "Reporte del día enviado correctamente.")
        self._on_volver()

    def _on_volver(self):
        from ui.menu_frame import MenuFrame
        self.controlador.mostrar_frame(
            MenuFrame, usuario=self.usuario, restaurante=self.restaurante
        )