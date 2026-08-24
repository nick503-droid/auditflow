import customtkinter as ctk
from tkinter import filedialog, messagebox
import keyboard
from datetime import datetime
import os
import sys
import subprocess
import threading

from db.local_db import (
    obtener_o_crear_borrador,
    actualizar_notas,
    agregar_evidencia,
    obtener_evidencias,
    eliminar_borrador_completo,
)
from api.client import (
    crear_reporte, 
    crear_evidencia_reporte, 
    subir_archivo, 
    obtener_reportes,
    actualizar_reporte
)
from core.recorder import GrabadorPantalla, es_archivo_grabado

class ReportesFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, restaurante=None, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.usuario = usuario
        self.restaurante = restaurante or {"id": "0", "nombre": "Restaurante (Pendiente)"}

        # Carga el borrador local (SQLite)
        self.borrador = obtener_o_crear_borrador(usuario["id"], restaurante["id"])

        self.grabador = GrabadorPantalla()
        self.grabando = False
        self.indicador = None
        self._debounce_id = None
        
        # Datos del reporte en la nube
        self.reporte_remoto_id = None
        self.codigo_reporte = None
        self.titulo_reporte = None
        self.reportes_data = {} 

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_ui_setup()
        self._cargar_reportes_nube() 
        self.bind("<Destroy>", self._al_destruir)

    # ==========================================
    # PANTALLA 1: SETUP (Título y Nube)
    # ==========================================
    def _construir_ui_setup(self):
        self.frame_setup = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_setup.grid(row=0, column=0, sticky="nsew")
        
        self.frame_setup.grid_rowconfigure(0, weight=1)
        self.frame_setup.grid_rowconfigure(2, weight=1)
        self.frame_setup.grid_columnconfigure(0, weight=1)
        self.frame_setup.grid_columnconfigure(2, weight=1)
        
        center_container = ctk.CTkFrame(self.frame_setup, fg_color="transparent")
        center_container.grid(row=1, column=1, sticky="nsew", padx=20)

        ctk.CTkLabel(
            center_container, 
            text="📝 Nuevo Reporte de Auditoría", 
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            center_container, 
            text="Asigna un nombre para crear el registro en la base de datos y obtener tu código de evidencias.", 
            text_color="gray50", font=ctk.CTkFont(size=13),
            wraplength=350 
        ).pack(pady=(0, 20))

        self.entry_titulo = ctk.CTkEntry(
            center_container, 
            placeholder_text="Ej: Reporte 2 de julio (Caso Riverside)",
            font=ctk.CTkFont(size=14),
            height=40,
            width=350
        )
        self.entry_titulo.pack(pady=(0, 15)) 

        self.boton_crear_nube = ctk.CTkButton(
            center_container, 
            text="Crear Reporte y Comenzar →", 
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            width=350,
            command=self._on_crear_reporte_inicial
        )
        self.boton_crear_nube.pack(pady=(0, 10))

        # --- SEPARADOR VISUAL ---
        ctk.CTkFrame(center_container, height=2, width=350, fg_color="#334155").pack(pady=20)

        # --- BUSCAR REPORTE EXISTENTE EN LA NUBE ---
        # (Esto reemplaza el botón de "Continuar Borrador Local" para que la Nube sea la fuente de la verdad)
        ctk.CTkLabel(
            center_container,
            text="🔍 Continuar un reporte de la nube:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(pady=(0, 10))

        self.dropdown_reportes = ctk.CTkOptionMenu(
            center_container,
            values=["Buscando reportes..."],
            font=ctk.CTkFont(size=13),
            height=35, width=350,
            fg_color="#1e293b", button_color="#334155"
        )
        self.dropdown_reportes.pack(pady=(0, 10))

        self.boton_cargar_nube = ctk.CTkButton(
            center_container,
            text="Descargar y Continuar ↓",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=35, width=350, fg_color="#10b981", hover_color="#059669",
            command=self._on_cargar_reporte_nube
        )
        self.boton_cargar_nube.pack(pady=(0, 20))

        # --- Botón de regresar ---
        self.boton_volver_setup = ctk.CTkButton(
            center_container, text="← Volver al menú", fg_color="transparent",
            border_width=1, command=self._volver_al_menu_directo
        )
        self.boton_volver_setup.pack(pady=(5, 0))

    def _cargar_reportes_nube(self):
        """Descarga los reportes del backend para llenar el combobox (SOLO NOMBRES)."""
        try:
            reportes = obtener_reportes()
            mis_reportes = [r for r in reportes if r.get("restaurante", {}).get("id") == self.restaurante["id"] or r.get("restaurante_id") == self.restaurante["id"]]

            if mis_reportes:
                self.reportes_data = {}
                for r in mis_reportes:
                    titulo = r.get("titulo") or "Reporte sin título"
                    clave = titulo
                    contador = 1
                    while clave in self.reportes_data:
                        clave = f"{titulo} ({contador})"
                        contador += 1
                        
                    self.reportes_data[clave] = r
                
                self.dropdown_reportes.configure(values=list(self.reportes_data.keys()))
                self.dropdown_reportes.set("Selecciona un reporte...")
            else:
                self.dropdown_reportes.configure(values=["No hay reportes previos"], state="disabled")
                self.boton_cargar_nube.configure(state="disabled")
        except Exception as e:
            self.dropdown_reportes.configure(values=["Error de conexión"], state="disabled")
            self.boton_cargar_nube.configure(state="disabled")

    def _on_cargar_reporte_nube(self):
        seleccion = self.dropdown_reportes.get()
        if seleccion not in self.reportes_data:
            return

        reporte = self.reportes_data[seleccion]

        self.reporte_remoto_id = reporte["id"]
        self.codigo_reporte = reporte.get("codigo", "SINCOD")
        self.titulo_reporte = reporte.get("titulo", "Reporte de Auditoría")

        # Limpiamos el rastro local para no mezclar evidencias de otros reportes
        eliminar_borrador_completo(self.borrador["id"])
        self.borrador = obtener_o_crear_borrador(self.usuario["id"], self.restaurante["id"])

        cloud_notas = reporte.get("notas_finales", "")
        if cloud_notas:
            actualizar_notas(self.borrador["id"], cloud_notas)
            self.borrador["notas_finales"] = cloud_notas 

        self._viene_de_nube = True 

        self.frame_setup.destroy()
        self._construir_ui_editor()
        self._cargar_estado_previo()
        self._registrar_hotkeys()

    def _on_crear_reporte_inicial(self):
        titulo = self.entry_titulo.get().strip()
        if not titulo:
            messagebox.showwarning("Atención", "Debes ingresar un título para el reporte.")
            return

        self.boton_crear_nube.configure(state="disabled", text="Creando en la nube...")
        self.update()

        # LIMPIEZA CRÍTICA: Borramos el borrador viejo local para que el texto "waos" no contamine este reporte nuevo
        eliminar_borrador_completo(self.borrador["id"])
        self.borrador = obtener_o_crear_borrador(self.usuario["id"], self.restaurante["id"])

        dto_inicial = {
            "usuario_id": self.usuario["id"],
            "restaurante_id": self.restaurante["id"],
            "titulo": titulo,
            "notas_finales": "", 
            "fecha_jornada": self.borrador["fecha_jornada"],
        }
        
        reporte_creado = crear_reporte(dto_inicial)

        if not reporte_creado:
            messagebox.showerror("Error", "No se pudo conectar con el servidor. Revisa tu conexión.")
            self.boton_crear_nube.configure(state="normal", text="Crear Reporte y Comenzar →")
            return

        self.reporte_remoto_id = reporte_creado.get("id")
        self.codigo_reporte = reporte_creado.get("codigo", "SINCOD")
        self.titulo_reporte = titulo
        self._viene_de_nube = True

        self.frame_setup.destroy()
        self._construir_ui_editor()
        self._cargar_estado_previo()
        self._registrar_hotkeys()

    def _volver_al_menu_directo(self):
        try: keyboard.remove_hotkey("ctrl+k+l")
        except: pass
        self._ocultar_indicador_rec()
        
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)

    # ==========================================
    # PANTALLA 2: EDITOR (El Bloc de Notas)
    # ==========================================
    def _construir_ui_editor(self):
        self.grid_columnconfigure(0, weight=1) 
        self.grid_columnconfigure(1, weight=0) 

        self.frame_editor = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_editor.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        # --- ENCABEZADO ---
        header_frame = ctk.CTkFrame(self.frame_editor, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header_frame, text=f"📄 {self.titulo_reporte}", 
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(side="left")

        # Estado de Sincronización
        self.label_estado_guardado = ctk.CTkLabel(
            header_frame, text="☁️ En la nube", text_color="#38bdf8", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.label_estado_guardado.pack(side="right", pady=5)

        ctk.CTkLabel(
            self.frame_editor,
            text=f"Auditor: {self.usuario['nombre']} | Sucursal: {self.restaurante['nombre']}",
            font=ctk.CTkFont(size=14), text_color="#38bdf8",
        ).pack(anchor="w", pady=(0, 10))

        # --- ÁREA DE TEXTO ---
        self.textbox_notas = ctk.CTkTextbox(
            self.frame_editor, font=("Consolas", 15), wrap="word",
            fg_color="#0f172a", text_color="#e2e8f0", border_width=1, border_color="#334155"
        )
        self.textbox_notas.pack(fill="both", expand=True)
        
        self.textbox_notas.bind("<KeyRelease>", self._on_texto_cambiado)
        self.textbox_notas.bind("<Control-h>", self._insertar_hora)
        self.textbox_notas.bind("<Control-H>", self._insertar_hora)

        ctk.CTkLabel(
            self.frame_editor,
            text="Tip: Presiona Ctrl + H mientras escribes para insertar la hora actual automáticamente.",
            font=ctk.CTkFont(size=11), text_color="gray50",
        ).pack(anchor="w", pady=(5, 0))

        # --- PANEL LATERAL ---
        self.frame_side = ctk.CTkScrollableFrame(self, width=260, fg_color="#1e293b")
        self.frame_side.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)

        caja_codigo = ctk.CTkFrame(self.frame_side, fg_color="#0284c7", corner_radius=8)
        caja_codigo.pack(pady=20, padx=20, fill="x")
        
        ctk.CTkLabel(caja_codigo, text="CÓDIGO DE VINCULACIÓN", font=ctk.CTkFont(size=10, weight="bold"), text_color="#bae6fd").pack(pady=(10,0))
        ctk.CTkLabel(caja_codigo, text=self.codigo_reporte, font=ctk.CTkFont(size=32, weight="bold", family="Consolas"), text_color="white").pack(pady=(0,10))
        
        self.switch_audio = ctk.CTkSwitch(self.frame_side, text="Grabar con audio", font=ctk.CTkFont(size=12))
        self.switch_audio.pack(pady=(0, 10), padx=20, anchor="w")
        self.switch_audio.deselect()

        self.boton_grabar = ctk.CTkButton(
            self.frame_side, text="🔴 Grabar pantalla (Ctrl+K+L)",
            command=self._toggle_grabacion, fg_color="#c0392b", hover_color="#922b21"
        )
        self.boton_grabar.pack(pady=(0, 10), padx=20, fill="x")

        ctk.CTkButton(
            self.frame_side, text="📎 Adjuntar archivo local", command=self._on_adjuntar,
            fg_color="transparent", border_width=1,
        ).pack(pady=(0, 15), padx=20, fill="x")

        ctk.CTkLabel(self.frame_side, text="Evidencias Locales:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20)
        
        self.frame_lista_evidencias = ctk.CTkScrollableFrame(self.frame_side, fg_color="#0f172a")
        self.frame_lista_evidencias.pack(pady=5, padx=15, fill="both", expand=True)

        self.boton_finalizar = ctk.CTkButton(
            self.frame_side, text="✅ Enviar y Cerrar Reporte", command=self._on_finalizar,
            fg_color="#27ae60", hover_color="#1e8449", height=45, font=ctk.CTkFont(weight="bold")
        )
        self.boton_finalizar.pack(pady=(15, 10), padx=20, fill="x")

        ctk.CTkButton(
            self.frame_side, text="← Volver al menú", fg_color="transparent",
            border_width=1, command=self._on_volver,
        ).pack(pady=(0, 20), padx=20, fill="x")

    # ==========================================
    # LÓGICA DEL EDITOR Y AUTOGUARDADO EN LA NUBE
    # ==========================================
    def _insertar_hora(self, event=None):
        hora_actual = datetime.now().strftime("%I:%M %p").lower()
        contenido_actual = self.textbox_notas.get("1.0", "end-1c")
        prefijo = "\n\n" if len(contenido_actual.strip()) > 0 else ""
        
        self.textbox_notas.insert("insert", f"{prefijo}{hora_actual} ")
        self.textbox_notas.focus_set()
        self._on_texto_cambiado(None)
        return "break" 

    def _cargar_estado_previo(self):
        if self.borrador["notas_finales"]:
            self.textbox_notas.insert("1.0", self.borrador["notas_finales"])
        self._refrescar_lista_evidencias()

    def _on_texto_cambiado(self, event):
        if self._debounce_id is not None:
            self.after_cancel(self._debounce_id)

        self.label_estado_guardado.configure(text="Escribiendo...", text_color="gray50")
        self._debounce_id = self.after(1000, self._guardar_notas_ahora)

    def _guardar_notas_ahora(self):
        texto = self.textbox_notas.get("1.0", "end").strip()
        
        # 1. Guarda en SQLite por seguridad local
        actualizar_notas(self.borrador["id"], texto)
        
        # 2. Envía a la NUBE en segundo plano (para que la app no se congele mientras escribes)
        if self.reporte_remoto_id:
            def tarea_nube():
                res = actualizar_reporte(self.reporte_remoto_id, texto)
                if res:
                    self.label_estado_guardado.configure(text="☁️ Guardado en la nube", text_color="#38bdf8")
                else:
                    self.label_estado_guardado.configure(text="💾 Guardado localmente (Sin red)", text_color="#22c55e")
            
            threading.Thread(target=tarea_nube, daemon=True).start()
            
        self._debounce_id = None

    # ==========================================
    # LÓGICA DE EVIDENCIAS Y PREVISUALIZACIÓN
    # ==========================================
    def _refrescar_lista_evidencias(self):
        for widget in self.frame_lista_evidencias.winfo_children():
            widget.destroy()

        evidencias = obtener_evidencias(self.borrador["id"])
        if not evidencias:
            ctk.CTkLabel(self.frame_lista_evidencias, text="No hay evidencias locales", text_color="gray50", font=ctk.CTkFont(size=11)).pack(pady=20)
            return

        for i, ev in enumerate(evidencias, start=1):
            nombre = ev["ruta_local"].split("\\")[-1].split("/")[-1]
            ruta = ev["ruta_local"]
            
            card = ctk.CTkFrame(self.frame_lista_evidencias, fg_color="#334155", corner_radius=5)
            card.pack(fill="x", pady=3, padx=2)
            
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=8, pady=(5,2))
            
            ctk.CTkLabel(top_row, text=f"Evidencia {i}", font=ctk.CTkFont(size=11, weight="bold"), text_color="#38bdf8").pack(side="left")
            
            ctk.CTkButton(
                top_row, text="👁", width=30, height=20, fg_color="#475569", hover_color="#64748b",
                command=lambda r=ruta: self._previsualizar_archivo(r)
            ).pack(side="right")
            
            ctk.CTkLabel(card, text=nombre, font=ctk.CTkFont(size=10), text_color="gray70", wraplength=180, justify="left").pack(anchor="w", padx=8, pady=(0,5))

    def _previsualizar_archivo(self, ruta):
        if not os.path.exists(ruta):
            messagebox.showerror("Error", "El archivo ya no existe en esa ruta.")
            return
            
        try:
            if sys.platform == "win32":
                os.startfile(ruta)
            elif sys.platform == "darwin":
                subprocess.call(["open", ruta])
            else:
                subprocess.call(["xdg-open", ruta])
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo previsualizar:\n{e}")

    # ==========================================
    # GRABACIÓN DE PANTALLA
    # ==========================================
    def _registrar_hotkeys(self):
        keyboard.add_hotkey("ctrl+k+l", self._toggle_grabacion)

    def _al_destruir(self, event):
        try: keyboard.remove_hotkey("ctrl+k+l")
        except: pass
        self._ocultar_indicador_rec()

    def _toggle_grabacion(self):
        if self.grabando: self._detener_grabacion()
        else: self._iniciar_grabacion()

    def _iniciar_grabacion(self):
        con_audio = bool(self.switch_audio.get())
        self.ruta_temp = self.grabador.iniciar(con_audio=con_audio)
        self.grabando = True
        self.controlador.withdraw()
        self._mostrar_indicador_rec()

    def _detener_grabacion(self):
        ruta_final = self.grabador.detener()
        self.grabando = False
        self._ocultar_indicador_rec()
        self.controlador.deiconify()
        self.controlador.lift()

        con_audio = bool(self.switch_audio.get())
        agregar_evidencia(self.borrador["id"], ruta_final, con_audio=con_audio)
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
            con_audio = bool(self.switch_audio.get())
            agregar_evidencia(self.borrador["id"], ruta, con_audio=con_audio)
            self._refrescar_lista_evidencias()

    # ==========================================
    # FINALIZAR REPORTE O VOLVER
    # ==========================================
    def _on_finalizar(self):
        evidencias = obtener_evidencias(self.borrador["id"])
        notas = self.textbox_notas.get("1.0", "end").strip()

        if not notas:
            messagebox.showwarning("Falta información", "El reporte está en blanco.")
            return

        respuesta = messagebox.askyesno(
            "Confirmar Cierre", 
            f"¿Terminar el reporte y subir {len(evidencias)} evidencia(s) local(es)?\n\n"
            "Nota: Las evidencias enviadas por código desde tu móvil ya están vinculadas en la nube."
        )
        if not respuesta:
            return

        self.boton_finalizar.configure(state="disabled", text="Subiendo archivos...")
        self.update()

        # Guardado final de texto
        if self.reporte_remoto_id:
            actualizar_reporte(self.reporte_remoto_id, notas)

        # Subimos evidencias locales
        for ev in evidencias:
            url_subida, error = subir_archivo(ev["ruta_local"])
            if url_subida is None:
                messagebox.showwarning("Evidencia no subida", f"No se pudo subir: {ev['ruta_local']}\nMotivo: {error}")
                continue

            crear_evidencia_reporte({
                "reporte_id": self.reporte_remoto_id,
                "evidencia_url": url_subida,
                "con_audio": bool(ev["con_audio"]),
                "orden_reproduccion": ev["orden_reproduccion"],
            })

            if es_archivo_grabado(ev["ruta_local"]):
                try: os.remove(ev["ruta_local"])
                except OSError: pass

        eliminar_borrador_completo(self.borrador["id"])
        messagebox.showinfo("Listo", f"Reporte completado y enviado.")
        self._volver_al_menu_directo()

    def _on_volver(self):
        texto = self.textbox_notas.get("1.0", "end-1c").strip()
        
        # Guardado forzoso a la nube antes de salir por seguridad
        if texto and self.reporte_remoto_id:
            actualizar_notas(self.borrador["id"], texto)
            actualizar_reporte(self.reporte_remoto_id, texto)
            
        respuesta = messagebox.askyesno(
            "Salir al Menú", 
            "¿Deseas volver al menú principal?\n\nTu texto se ha guardado en la nube automáticamente."
        )
        if respuesta:
            self._volver_al_menu_directo()