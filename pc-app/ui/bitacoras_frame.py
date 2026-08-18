import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime
import keyboard
import os
import threading
import time

from api.client import (
    obtener_bitacoras_por_fecha, 
    adjuntar_evidencia_por_codigo, 
    subir_archivo, 
    crear_bitacora,
    obtener_restaurantes,
    obtener_usuarios
)
from core.recorder import GrabadorPantalla, es_archivo_grabado
from tksheet import Sheet

class BitacorasFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, fecha=None, **kwargs):
        super().__init__(master, **kwargs)
        self.controlador = controlador
        self.usuario_activo = usuario
        
        # Si no nos pasan una fecha desde el menú, asumimos hoy
        self.fecha_actual = fecha if fecha else datetime.now().strftime("%Y-%m-%d")
        self.lock = threading.Lock() # Candado para evitar que el polling y el usuario choquen
        
        self.ruta_evidencia = None
        self.grabador = GrabadorPantalla()
        self.grabando = False
        self.indicador = None
        self.hilo_polling_activo = True
        self.editando = False 
        self.ultimo_hash_bd = None
        
        # Mapas para traducir nombres a UUIDs
        self.mapa_restaurantes = {}
        self.mapa_usuarios = {}
        self._cargar_catalogos()
        
        # Layout: Grid dinámico
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=3) # Cuadrícula ocupa más espacio
        self.grid_columnconfigure(1, weight=0) # Panel de evidencia empieza oculto

        self._construir_top_bar()
        self._construir_ui_grid()
        self._construir_ui_evidencia()
        self._registrar_hotkeys()

        self._iniciar_polling()
        self.bind("<Destroy>", self._al_destruir)

    def _cargar_catalogos(self):
        try:
            rests = obtener_restaurantes()
            self.mapa_restaurantes = {r['nombre']: r['id'] for r in rests}
        except Exception:
            print("Error cargando restaurantes en bitácoras")
            
        try:
            usrs = obtener_usuarios()
            self.mapa_usuarios = {u['nombre']: u['id'] for u in usrs}
        except Exception:
            print("Error cargando usuarios en bitácoras")

    def _construir_top_bar(self):
        self.top_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 0))
        
        ctk.CTkLabel(
            self.top_bar, 
            text=f"Bitácoras: {self.fecha_actual}", 
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left", padx=10)
        
        # Selector global de Vigilante
        ctk.CTkLabel(self.top_bar, text="Vigilante a cargo:").pack(side="left", padx=(20, 5))
        nombres_usuarios = list(self.mapa_usuarios.keys()) if self.mapa_usuarios else [self.usuario_activo['nombre']]
        
        self.combo_vigilante = ctk.CTkComboBox(self.top_bar, values=nombres_usuarios, width=150)
        self.combo_vigilante.set(self.usuario_activo['nombre'])
        self.combo_vigilante.pack(side="left", padx=5)

        ctk.CTkButton(
            self.top_bar, text="← Volver", width=80, fg_color="gray50", command=self._on_volver
        ).pack(side="right", padx=10)
        
        ctk.CTkButton(
            self.top_bar, text="➕ Nueva Fila", width=100, command=self._agregar_fila_vacia
        ).pack(side="right", padx=10)

    def _construir_ui_grid(self):
        self.frame_grid = ctk.CTkFrame(self)
        self.frame_grid.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        self.sheet = Sheet(self.frame_grid, data=[])
        self.sheet.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.headers = ["ID (Oculto)", "Cód.", "Hora", "Restaurante", "Videovigilante", "Bitácora", "Urgencia", "Evidencia"]
        self.sheet.headers(self.headers)
        
        self.sheet.column_width(column=0, width=0)   
        self.sheet.column_width(column=1, width=70)  
        self.sheet.column_width(column=2, width=80)  
        self.sheet.column_width(column=3, width=150) 
        self.sheet.column_width(column=4, width=120) 
        self.sheet.column_width(column=5, width=350) 
        self.sheet.column_width(column=6, width=90)  
        self.sheet.column_width(column=7, width=90)  
        
        # Habilitar todas las interacciones de tksheet nativas
        self.sheet.enable_bindings("all")
        
        # Eventos extra para controlar la edición y detectar clics en "Evidencia"
        self.sheet.extra_bindings([
            ("begin_edit_cell", self._on_begin_edit),
            ("end_edit_cell", self._on_end_edit),
            ("cell_select", self._on_celda_seleccionada)
        ])

    def _on_begin_edit(self, event):
        with self.lock:
            self.editando = True

    def _on_end_edit(self, event):
        with self.lock:
            self.editando = False
        self._procesar_modificacion(event.row)

    def _construir_ui_evidencia(self):
        self.frame_evidencia = ctk.CTkFrame(self, width=250)
        self.frame_evidencia.grid_propagate(False)
        
        # Botón para cerrar el panel
        ctk.CTkButton(
            self.frame_evidencia, text="X", width=30, height=30, 
            fg_color="#c0392b", hover_color="#922b21", command=self._ocultar_panel_evidencia
        ).pack(anchor="ne", pady=5, padx=5)
        
        ctk.CTkLabel(self.frame_evidencia, text="Adjuntar Evidencia", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 5))
        ctk.CTkLabel(self.frame_evidencia, text="Código de bitácora:", text_color="gray70").pack(pady=(0, 5), padx=10)
        
        self.entry_codigo = ctk.CTkEntry(self.frame_evidencia, justify="center", font=ctk.CTkFont(size=14, weight="bold"))
        self.entry_codigo.pack(pady=5, padx=20, fill="x")

        self.switch_audio = ctk.CTkSwitch(self.frame_evidencia, text="Grabar con audio")
        self.switch_audio.pack(pady=(15, 10), padx=20, anchor="w")
        self.switch_audio.deselect()

        self.boton_grabar = ctk.CTkButton(
            self.frame_evidencia, text="🔴 Grabar pantalla\n(Ctrl+K+L)",
            command=self._toggle_grabacion, fg_color="#c0392b", hover_color="#922b21"
        )
        self.boton_grabar.pack(pady=10, padx=20, fill="x")

        self.boton_adjuntar = ctk.CTkButton(
            self.frame_evidencia, text="📎 Adjuntar archivo", 
            command=self._on_adjuntar, fg_color="transparent", border_width=1
        )
        self.boton_adjuntar.pack(pady=5, padx=20, fill="x")

        self.label_archivo = ctk.CTkLabel(self.frame_evidencia, text="Sin evidencia", text_color="gray60", wraplength=200)
        self.label_archivo.pack(pady=(5, 20), padx=10)

        self.boton_subir = ctk.CTkButton(
            self.frame_evidencia, text="Subir y Vincular", command=self._on_subir_evidencia,
            fg_color="#27ae60", hover_color="#1e8449"
        )
        self.boton_subir.pack(pady=10, padx=20, fill="x")

    def _ocultar_panel_evidencia(self):
        self.frame_evidencia.grid_remove()
        self.grid_columnconfigure(1, weight=0)

    def _mostrar_panel_evidencia(self, codigo=""):
        self.grid_columnconfigure(1, weight=1)
        self.frame_evidencia.grid(row=1, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.entry_codigo.delete(0, "end")
        self.entry_codigo.insert(0, codigo)

    def _on_celda_seleccionada(self, event):
        row = event.row
        col = event.column
        if col == 7:  # Clic en Columna Evidencia
            row_data = self.sheet.get_row_data(row)
            if row_data:
                codigo = row_data[1]
                if codigo:
                    self._mostrar_panel_evidencia(codigo)
                else:
                    messagebox.showinfo("Atención", "Termina de escribir la hora, restaurante y descripción para que se genere el código.")

    def _agregar_fila_vacia(self):
        # Forma segura (a prueba de fallos) de agregar filas sin romper tksheet
        vigilante_actual = self.combo_vigilante.get()
        # ID, Cód, Hora(Manual), Restaurante, Vigilante, Bitacora, Urgencia, Evidencia
        nueva_fila = ["", "", "", "", vigilante_actual, "", "low", "Agregar"]
        
        current_data = self.sheet.get_sheet_data()
        current_data.append(nueva_fila)
        self.sheet.set_sheet_data(current_data)
        
        total_filas = self.sheet.get_total_rows()
        if total_filas > 0:
            # Reaplicar dropdowns de forma segura
            filas_idx = tuple(range(total_filas))
            if self.mapa_restaurantes:
                self.sheet.create_dropdown(r=filas_idx, c=3, values=list(self.mapa_restaurantes.keys()), set_value="", redraw=False)
            self.sheet.create_dropdown(r=filas_idx, c=6, values=["low", "medium", "critical"], set_value="low", redraw=True)
            
        self.sheet.see(total_filas - 1, 2)

    def _procesar_modificacion(self, row):
        """Intenta guardar el borrador en el backend si los campos mínimos están llenos."""
        row_data = self.sheet.get_row_data(row)
        if not row_data:
            return
            
        b_id = row_data[0]
        
        # Si no tiene ID, es un borrador nuevo
        if not b_id:
            hora = row_data[2].strip() if isinstance(row_data[2], str) else str(row_data[2])
            rest_nombre = row_data[3].strip() if isinstance(row_data[3], str) else str(row_data[3])
            vig_nombre = row_data[4].strip() if isinstance(row_data[4], str) else str(row_data[4])
            desc = row_data[5].strip() if isinstance(row_data[5], str) else str(row_data[5])
            urg = row_data[6].strip() if isinstance(row_data[6], str) else "low"
            
            if hora and rest_nombre and desc:
                # Traducción a UUID para la base de datos
                rest_id = self.mapa_restaurantes.get(rest_nombre)
                usr_id = self.mapa_usuarios.get(vig_nombre, self.usuario_activo["id"])
                
                if not rest_id:
                    return 
                
                dto = {
                    "usuario_id": usr_id,
                    "restaurante_id": rest_id,
                    "descripcion": desc,
                    "fecha": self.fecha_actual,
                    "hora": hora,
                    "urgencia": urg
                }
                
                resultado = crear_bitacora(dto)
                if resultado:
                    self.sheet.set_cell_data(row, 0, resultado.get('id', ''))
                    self.sheet.set_cell_data(row, 1, resultado.get('codigo', ''))
                    # Al resetear la variable local, obligamos al polling a refrescar en el próximo ciclo
                    self.ultimo_hash_bd = None 

    def _iniciar_polling(self):
        self.hilo_polling_activo = True
        threading.Thread(target=self._polling_worker, daemon=True).start()

    def _polling_worker(self):
        while self.hilo_polling_activo:
            bitacoras = obtener_bitacoras_por_fecha(self.fecha_actual)
            if bitacoras is not None:
                self.after(0, self._actualizar_sheet_con_datos, bitacoras)
            time.sleep(5)

    def _actualizar_sheet_con_datos(self, bitacoras):
        # Validar con un candado que no estamos editando
        with self.lock:
            if self.editando:
                return
                
            # Generar hash para comparar cambios sin necesidad de un set_sheet_data agresivo
            nuevo_hash = hash(str(bitacoras))
            if self.ultimo_hash_bd == nuevo_hash:
                # Si está vacío por defecto, metemos una fila para que puedan empezar
                if self.sheet.get_total_rows() == 0:
                    self._agregar_fila_vacia()
                return
                
            self.ultimo_hash_bd = nuevo_hash

            current_data = []
            for b in bitacoras:
                b_id = b.get('id', '')
                cod = b.get('codigo', '')
                hora = b.get('hora', '')
                rest = b.get('restaurante', {}).get('nombre', '') if isinstance(b.get('restaurante'), dict) else ''
                vig = b.get('usuario', {}).get('nombre', '') if isinstance(b.get('usuario'), dict) else ''
                desc = b.get('descripcion', '')
                urg = b.get('urgencia', 'low')
                ev_url = "Sí" if b.get('evidencia_url') else "Agregar"
                
                current_data.append([b_id, cod, hora, rest, vig, desc, urg, ev_url])

            # Preservar las filas locales (borradores sin ID)
            datos_pantalla = self.sheet.get_sheet_data()
            local_drafts = [row for row in datos_pantalla if not row[0]]
            current_data.extend(local_drafts)
            
            # SOLO recargar si hubo cambios, esto elimina el lag y el freeze de la UI
            self.sheet.set_sheet_data(current_data)
            
            total_filas = self.sheet.get_total_rows()
            if total_filas > 0:
                filas_idx = tuple(range(total_filas))
                if self.mapa_restaurantes:
                    self.sheet.create_dropdown(r=filas_idx, c=3, values=list(self.mapa_restaurantes.keys()), set_value="", redraw=False)
                self.sheet.create_dropdown(r=filas_idx, c=6, values=["low", "medium", "critical"], set_value="low", redraw=True)

    def _registrar_hotkeys(self):
        keyboard.add_hotkey("ctrl+k+l", self._toggle_grabacion)

    def _al_destruir(self, event):
        self.hilo_polling_activo = False
        try:
            keyboard.remove_hotkey("ctrl+k+l")
        except Exception:
            pass
            
        # EVITAR FFmpeg Huérfano! Si cierran mientras graba, detenemos forzosamente
        if self.grabando:
            self._detener_grabacion()
            
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
        self.controlador.withdraw()
        self._mostrar_indicador_rec()

    def _detener_grabacion(self):
        self.grabador.detener()
        self.grabando = False
        self._ocultar_indicador_rec()
        self.controlador.deiconify()
        self.controlador.lift()

        nombre_archivo = self.ruta_evidencia.split("\\")[-1]
        self.label_archivo.configure(text=f"✅ Grabado:\n{nombre_archivo}")

    def _mostrar_indicador_rec(self):
        self.indicador = ctk.CTkToplevel(self.controlador)
        self.indicador.overrideredirect(True)
        self.indicador.attributes("-topmost", True)
        ancho, alto = 190, 40
        x = self.indicador.winfo_screenwidth() - ancho - 20
        y = 20
        self.indicador.geometry(f"{ancho}x{alto}+{x}+{y}")
        ctk.CTkLabel(
            self.indicador, text="🔴 Grabando (Ctrl+K+L)", fg_color="#1a1a1a", text_color="white"
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
            self.label_archivo.configure(text=f"✅ Archivo:\n{nombre_archivo}")

    def _on_subir_evidencia(self):
        codigo = self.entry_codigo.get().strip().upper()
        
        if not codigo or len(codigo) != 6:
            messagebox.showwarning("Atención", "Debes ingresar el código corto válido de 6 caracteres.")
            return
            
        if not self.ruta_evidencia:
            messagebox.showwarning("Atención", "No has grabado ni adjuntado ninguna evidencia.")
            return

        self.boton_subir.configure(state="disabled", text="Subiendo...")
        self.update()

        evidencia_url, error_upload = subir_archivo(self.ruta_evidencia)
        
        if evidencia_url is None:
            messagebox.showerror("Error", f"No se pudo subir el archivo.\n\nMotivo: {error_upload}")
            self.boton_subir.configure(state="normal", text="Subir y Vincular")
            return

        con_audio = bool(self.switch_audio.get())
        data, error_link = adjuntar_evidencia_por_codigo(codigo, evidencia_url, con_audio)

        if error_link:
            messagebox.showerror("Error", error_link)
        else:
            messagebox.showinfo("Éxito", f"Evidencia vinculada a la bitácora {codigo}.")
            
            if es_archivo_grabado(self.ruta_evidencia):
                try:
                    os.remove(self.ruta_evidencia)
                except OSError:
                    pass

            self._resetear_panel_evidencia()
            self._ocultar_panel_evidencia()

        self.boton_subir.configure(state="normal", text="Subir y Vincular")

    def _resetear_panel_evidencia(self):
        self.entry_codigo.delete(0, "end")
        self.switch_audio.deselect()
        self.ruta_evidencia = None
        self.label_archivo.configure(text="Sin evidencia")

    def _on_volver(self):
        self.hilo_polling_activo = False
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)