import customtkinter as ctk
from tkinter import messagebox, simpledialog
from datetime import datetime
import os

from api.client import (
    obtener_reportes,
    obtener_bitacoras_todas,
    eliminar_reporte_remoto,
    renombrar_reporte_remoto,
    obtener_bitacoras_por_fecha,
    eliminar_bitacora_remota,
    obtener_restaurantes,
    obtener_usuarios
)
from db.local_db import (
    eliminar_borrador_y_archivos,
    obtener_reportes_pendientes
)
from ui.bitacoras_frame import URGENCIA_COLORES, URGENCIA_VALOR_A_DISPLAY

class AdminFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, **kwargs):
        super().__init__(master, **kwargs)
        self.controlador = controlador
        self.usuario_activo = usuario
        
        # Estado de navegación: ROOT -> REPORTES | BITACORAS -> BITACORA_DIA
        self.vista_actual = "ROOT"
        self.fecha_seleccionada = None
        
        # Caché de catálogos para filtros
        self.usuarios_dict = {}
        self.restaurantes_dict = {}
        self._cargar_catalogos()
        
        # Filtros de bitácoras
        self.filtro_usuario = ctk.StringVar(value="Todos")
        self.filtro_restaurante = ctk.StringVar(value="Todos")
        self.filtro_urgencia = ctk.StringVar(value="Todas")
        self.filtro_evidencia = ctk.StringVar(value="Evidencias")
        
        self.filas_bitacora = [] # Almacena las filas de la fecha seleccionada

        # Layout
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self.top_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        
        self.lbl_titulo = ctk.CTkLabel(self.top_bar, text="", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_titulo.pack(side="left", padx=10)
        
        self.btn_back = ctk.CTkButton(
            self.top_bar, text="← Volver", width=80, 
            fg_color="gray40", hover_color="gray30",
            command=self._on_back
        )
        self.btn_back.pack(side="right", padx=10)
        
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=1, column=0, sticky="nsew")
        
        self._render_root()

    def _cargar_catalogos(self):
        try:
            usrs = obtener_usuarios()
            self.usuarios_dict = {u["id"]: u["nombre"] for u in usrs}
        except Exception:
            pass
            
        try:
            rests = obtener_restaurantes()
            self.restaurantes_dict = {r["id"]: r["nombre"] for r in rests}
        except Exception:
            pass

    def _actualizar_top_bar(self, titulo: str):
        self.lbl_titulo.configure(text=titulo)
        
    def _limpiar_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def _on_back(self):
        if self.vista_actual == "ROOT":
            from ui.selection_frame import SelectionFrame
            self.controlador.mostrar_frame(SelectionFrame)
        elif self.vista_actual in ["REPORTES", "BITACORAS"]:
            self._render_root()
        elif self.vista_actual == "BITACORA_DIA":
            self._abrir_vista_bitacoras()
        elif self.vista_actual == "REPORTE_DETALLE":
            self._abrir_vista_reportes()

    # ─── VISTA RAÍZ ──────────────────────────────────────────────────────────

    def _render_root(self):
        self.vista_actual = "ROOT"
        self._actualizar_top_bar("🗂️ Administrador")
        self._limpiar_container()
        
        frame_opciones = ctk.CTkFrame(self.container, fg_color="transparent")
        frame_opciones.pack(expand=True, fill="x", padx=40)
        
        # Tarjeta Bitácoras
        card_b = ctk.CTkFrame(frame_opciones, fg_color="#0284c7", corner_radius=12, cursor="hand2")
        card_b.pack(fill="x", pady=10)
        lbl_b = ctk.CTkLabel(card_b, text="📅 Explorar Bitácoras", font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
        lbl_b.pack(pady=20)
        card_b.bind("<Button-1>", lambda e: self._abrir_vista_bitacoras())
        lbl_b.bind("<Button-1>", lambda e: self._abrir_vista_bitacoras())
        
        # Tarjeta Reportes
        card_r = ctk.CTkFrame(frame_opciones, fg_color="#7c3aed", corner_radius=12, cursor="hand2")
        card_r.pack(fill="x", pady=10)
        lbl_r = ctk.CTkLabel(card_r, text="📊 Explorar Reportes", font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
        lbl_r.pack(pady=20)
        card_r.bind("<Button-1>", lambda e: self._abrir_vista_reportes())
        lbl_r.bind("<Button-1>", lambda e: self._abrir_vista_reportes())

    # ─── VISTA REPORTES ───────────────────────────────────────────────────────

    def _abrir_vista_reportes(self):
        self.vista_actual = "REPORTES"
        self._actualizar_top_bar("📁 Reportes")
        self._limpiar_container()
        
        scroll = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        lbl_cargando = ctk.CTkLabel(scroll, text="Cargando reportes...")
        lbl_cargando.pack(pady=20)
        
        def _fetch():
            nube = obtener_reportes()
            locales = obtener_reportes_pendientes()
            self.after(0, lambda: self._mostrar_lista_reportes(scroll, nube, locales, lbl_cargando))
            
        import threading
        threading.Thread(target=_fetch, daemon=True).start()

    def _mostrar_lista_reportes(self, parent, reportes_nube, reportes_locales, lbl_cargando):
        lbl_cargando.destroy()
        
        if not reportes_nube and not reportes_locales:
            ctk.CTkLabel(parent, text="No hay reportes disponibles.").pack(pady=20)
            return
            
        # Mostrar locales primero
        for r in reportes_locales:
            self._crear_item_reporte(parent, r, es_local=True)
            
        # Mostrar de la nube
        for r in reportes_nube:
            self._crear_item_reporte(parent, r, es_local=False)

    def _crear_item_reporte(self, parent, reporte: dict, es_local: bool):
        card = ctk.CTkFrame(parent, fg_color="#1e293b", corner_radius=8)
        card.pack(fill="x", pady=4, padx=5)
        
        icono = "💾" if es_local else "☁️"
        titulo = reporte.get("titulo") or "Sin título"
        fecha = reporte.get("fecha_jornada") or ""
        if isinstance(fecha, str):
            fecha = fecha[:10]
            
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(info_frame, text=f"{icono} {titulo}", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(info_frame, text=f"Fecha: {fecha}", font=ctk.CTkFont(size=10), text_color="gray", anchor="w").pack(fill="x")
        
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=10, pady=10)
        
        # Botón Ver
        ctk.CTkButton(
            btn_frame, text="👁️ Ver", width=60, height=24,
            fg_color="#166534", hover_color="#14532d",
            command=lambda r=reporte, l=es_local: self._abrir_reporte_detalle(r, l)
        ).pack(side="left", padx=4)
        
        # Botón Renombrar (Solo nube por ahora)
        if not es_local:
            ctk.CTkButton(
                btn_frame, text="✏️ Editar", width=60, height=24,
                fg_color="#0284c7", hover_color="#0369a1",
                command=lambda r=reporte: self._renombrar_reporte(r)
            ).pack(side="left", padx=4)
            
        # Botón Eliminar
        ctk.CTkButton(
            btn_frame, text="🗑️", width=30, height=24,
            fg_color="#dc2626", hover_color="#991b1b",
            command=lambda r=reporte, l=es_local: self._eliminar_reporte(r, l)
        ).pack(side="left", padx=4)

    def _renombrar_reporte(self, reporte):
        nuevo_titulo = simpledialog.askstring("Renombrar Reporte", "Ingresa el nuevo título:", initialvalue=reporte.get("titulo", ""))
        if not nuevo_titulo or nuevo_titulo == reporte.get("titulo"):
            return
            
        res = renombrar_reporte_remoto(reporte["id"], nuevo_titulo)
        if res:
            messagebox.showinfo("Éxito", "Reporte renombrado correctamente.")
            self._abrir_vista_reportes()
        else:
            messagebox.showerror("Error", "No se pudo renombrar el reporte.")

    def _eliminar_reporte(self, reporte, es_local):
        if not messagebox.askyesno("Confirmar", "¿Eliminar este reporte permanentemente?"):
            return
            
        if es_local:
            eliminar_borrador_y_archivos(reporte["id"], eliminar_grabaciones=True)
            messagebox.showinfo("Éxito", "Borrador local eliminado.")
            self._abrir_vista_reportes()
        else:
            if eliminar_reporte_remoto(reporte["id"]):
                messagebox.showinfo("Éxito", "Reporte eliminado de la nube.")
                self._abrir_vista_reportes()
            else:
                messagebox.showerror("Error", "No se pudo eliminar el reporte.")

    # ─── VISTA BITÁCORAS ─────────────────────────────────────────────────────

    def _abrir_vista_bitacoras(self):
        self.vista_actual = "BITACORAS"
        self._actualizar_top_bar("📁 Bitácoras")
        self._limpiar_container()
        
        scroll = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        lbl_cargando = ctk.CTkLabel(scroll, text="Cargando fechas de bitácoras...")
        lbl_cargando.pack(pady=20)
        
        def _fetch():
            bitacoras = obtener_bitacoras_todas()
            fechas = sorted(list(set(b["fecha"] for b in bitacoras if b.get("fecha"))), reverse=True)
            self.after(0, lambda: self._mostrar_lista_fechas(scroll, fechas, lbl_cargando))
            
        import threading
        threading.Thread(target=_fetch, daemon=True).start()

    def _mostrar_lista_fechas(self, parent, fechas, lbl_cargando):
        lbl_cargando.destroy()
        
        if not fechas:
            ctk.CTkLabel(parent, text="No hay bitácoras disponibles.").pack(pady=20)
            return
            
        for f in fechas:
            card = ctk.CTkFrame(parent, fg_color="#1e293b", corner_radius=8, cursor="hand2")
            card.pack(fill="x", pady=4, padx=5)
            
            lbl = ctk.CTkLabel(card, text=f"📅 {f}", font=ctk.CTkFont(weight="bold"))
            lbl.pack(padx=15, pady=12, anchor="w")
            
            card.bind("<Button-1>", lambda e, d=f: self._abrir_bitacora_dia(d))
            lbl.bind("<Button-1>", lambda e, d=f: self._abrir_bitacora_dia(d))

    # ─── VISTA BITÁCORA DETALLE (DIA) ────────────────────────────────────────

    def _abrir_bitacora_dia(self, fecha: str):
        self.vista_actual = "BITACORA_DIA"
        self.fecha_seleccionada = fecha
        self._actualizar_top_bar(f"📅 Bitácora {fecha}")
        self._limpiar_container()
        
        # Filtros
        filtro_frame = ctk.CTkFrame(self.container, fg_color="#0f172a", corner_radius=0)
        filtro_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        usuarios_vals = ["Todos"] + list(self.usuarios_dict.values())
        rest_vals = ["Todos"] + list(self.restaurantes_dict.values())
        
        ctk.CTkOptionMenu(filtro_frame, variable=self.filtro_usuario, values=usuarios_vals, command=self._aplicar_filtros, width=120).pack(side="left", padx=5, pady=5)
        ctk.CTkOptionMenu(filtro_frame, variable=self.filtro_restaurante, values=rest_vals, command=self._aplicar_filtros, width=120).pack(side="left", padx=5, pady=5)
        ctk.CTkOptionMenu(filtro_frame, variable=self.filtro_urgencia, values=["Todas", "Comentar", "Leve", "Medio", "Grave"], command=self._aplicar_filtros, width=100).pack(side="left", padx=5, pady=5)
        ctk.CTkOptionMenu(filtro_frame, variable=self.filtro_evidencia, values=["Evidencias", "Sí", "No"], command=self._aplicar_filtros, width=80).pack(side="left", padx=5, pady=5)
        
        # Área de filas
        self.scroll_filas = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        self.scroll_filas.pack(fill="both", expand=True, padx=10, pady=10)
        
        lbl_cargando = ctk.CTkLabel(self.scroll_filas, text="Cargando filas...")
        lbl_cargando.pack(pady=20)
        
        def _fetch():
            self.filas_bitacora = obtener_bitacoras_por_fecha(fecha)
            self.after(0, lambda: self._aplicar_filtros(None))
            
        import threading
        threading.Thread(target=_fetch, daemon=True).start()

    def _aplicar_filtros(self, _=None):
        for w in self.scroll_filas.winfo_children():
            if isinstance(w, ctk.CTkFrame): # Solo borrar frames, no labels si se desea
                w.destroy()
        
        # Ocultar label de cargando si existe
        for w in self.scroll_filas.winfo_children():
            if isinstance(w, ctk.CTkLabel):
                w.destroy()
                
        f_usr = self.filtro_usuario.get()
        f_rst = self.filtro_restaurante.get()
        f_urg = self.filtro_urgencia.get()
        f_evi = self.filtro_evidencia.get()
        
        filas_filtradas = []
        for fila in self.filas_bitacora:
            # Match Usuario
            usr_nombre = fila.get("usuario", {}).get("nombre", "")
            if f_usr != "Todos" and f_usr != usr_nombre:
                continue
                
            # Match Restaurante
            rst_nombre = fila.get("restaurante", {}).get("nombre", "")
            if f_rst != "Todos" and f_rst != rst_nombre:
                continue
                
            # Match Urgencia
            urg_backend = fila.get("urgencia", "leve")
            urg_display = URGENCIA_VALOR_A_DISPLAY.get(urg_backend, "Leve")
            if f_urg != "Todas" and f_urg != urg_display:
                continue
                
            # Match Evidencia
            tiene_ev = len(fila.get("evidencias", [])) > 0 or bool(fila.get("evidencia_url"))
            if f_evi == "Sí" and not tiene_ev:
                continue
            if f_evi == "No" and tiene_ev:
                continue
                
            filas_filtradas.append(fila)
            
        if not filas_filtradas:
            ctk.CTkLabel(self.scroll_filas, text="No hay filas que coincidan con los filtros.").pack(pady=20)
            return
            
        for idx, fila in enumerate(filas_filtradas):
            self._crear_item_bitacora(self.scroll_filas, fila, idx)
            
    def _crear_item_bitacora(self, parent, fila, idx):
        urg = fila.get("urgencia", "leve")
        colores = URGENCIA_COLORES.get(urg, URGENCIA_COLORES["leve"])
        bg_color = colores["tarjeta_par"] if idx % 2 == 0 else colores["tarjeta_impar"]
        
        card = ctk.CTkFrame(parent, fg_color=bg_color, corner_radius=5)
        card.pack(fill="x", pady=2, padx=2)
        
        # Info básica
        hora = fila.get("hora", "--:--")
        usr = fila.get("usuario", {}).get("nombre", "Usuario")
        rst = fila.get("restaurante", {}).get("nombre", "Restaurante")
        desc = fila.get("descripcion", "")
        
        info = f"{hora} | {rst} | {usr}\n{desc}"
        
        ctk.CTkLabel(card, text=info, justify="left", anchor="w", wraplength=400).pack(side="left", padx=10, pady=10, fill="both", expand=True)
        
        # Botón eliminar
        ctk.CTkButton(
            card, text="🗑️", width=30, height=24,
            fg_color="#dc2626", hover_color="#991b1b",
            command=lambda b=fila: self._eliminar_bitacora_fila(b)
        ).pack(side="right", padx=10, pady=10)
        
        tiene_ev = len(fila.get("evidencias", [])) > 0 or bool(fila.get("evidencia_url"))
        if tiene_ev:
            ctk.CTkButton(
                card, text="👁️", width=30, height=24,
                fg_color="#166534", hover_color="#14532d",
                command=lambda b=fila: self._abrir_evidencias_bitacora(b)
            ).pack(side="right", padx=5, pady=10)
        
    def _eliminar_bitacora_fila(self, fila):
        if not messagebox.askyesno("Confirmar", "¿Eliminar esta fila de la bitácora permanentemente?"):
            return
            
        if eliminar_bitacora_remota(fila["id"]):
            # Eliminar localmente de la lista cacheada
            self.filas_bitacora = [f for f in self.filas_bitacora if f["id"] != fila["id"]]
            self._aplicar_filtros()
        else:
            messagebox.showerror("Error", "No se pudo eliminar la fila.")

    def _abrir_evidencias_bitacora(self, fila):
        urls = []
        if fila.get("evidencia_url"):
            urls.append(fila["evidencia_url"])
        for ev in fila.get("evidencias", []):
            if ev.get("evidencia_url"):
                urls.append(ev["evidencia_url"])
                
        if not urls:
            messagebox.showinfo("Info", "No se encontraron URLs de evidencia.")
            return
            
        self._mostrar_popup_evidencias(urls)

    def _mostrar_popup_evidencias(self, urls):
        import webbrowser
        from core.thumbnailer import generar_miniatura
        
        popup = ctk.CTkToplevel(self.controlador)
        popup.title("Evidencias")
        popup.geometry("600x400")
        popup.attributes("-topmost", True)
        
        scroll = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        for url in urls:
            f_ev = ctk.CTkFrame(scroll, fg_color="#1e293b", corner_radius=8)
            f_ev.pack(fill="x", pady=5, padx=5)
            
            # Placeholder label while loading
            lbl_img = ctk.CTkLabel(f_ev, text="Cargando miniatura...", width=120, height=120)
            lbl_img.pack(side="left", padx=10, pady=10)
            
            ctk.CTkLabel(f_ev, text=url.split("/")[-1][:30], anchor="w").pack(side="left", padx=10, expand=True, fill="x")
            
            ctk.CTkButton(
                f_ev, text="Abrir Original", width=100,
                command=lambda u=url: webbrowser.open(u)
            ).pack(side="right", padx=10)
            
            # Load thumbnail in background
            def _cargar_thumb(u=url, lbl=lbl_img):
                img = generar_miniatura(u, size=(120, 120))
                if img:
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    lbl.configure(text="", image=ctk_img)
                    lbl.image = ctk_img # keep ref
                else:
                    lbl.configure(text="Sin vista previa")
            
            import threading
            threading.Thread(target=_cargar_thumb, daemon=True).start()

    def _abrir_reporte_detalle(self, reporte, es_local):
        self.vista_actual = "REPORTE_DETALLE"
        titulo = reporte.get("titulo") or "Reporte"
        self._actualizar_top_bar(f"📝 {titulo}")
        self._limpiar_container()
        
        main_scroll = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        main_scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Metadata
        meta_frame = ctk.CTkFrame(main_scroll, fg_color="#1e293b", corner_radius=8)
        meta_frame.pack(fill="x", pady=(0, 20))
        
        fecha = reporte.get("fecha_jornada") or ""
        if isinstance(fecha, str): fecha = fecha[:10]
        usr = reporte.get("usuario", {}).get("nombre", "Usuario") if not es_local else "Local"
        rst = reporte.get("restaurante", {}).get("nombre", "Restaurante") if not es_local else "Local"
        
        ctk.CTkLabel(meta_frame, text=f"Fecha: {fecha} | Restaurante: {rst} | Usuario: {usr}", font=ctk.CTkFont(weight="bold")).pack(pady=10, padx=10, anchor="w")
        
        # Texto
        notas = reporte.get("notas_finales", "")
        txt = ctk.CTkTextbox(main_scroll, height=400, fg_color="#0f172a")
        txt.pack(fill="x", pady=(0, 20))
        txt.configure(state="normal")
        txt.insert("1.0", notas)
        txt.configure(state="disabled")
        
        # Evidencias
        lbl_ev = ctk.CTkLabel(main_scroll, text="Evidencias Adjuntas:", font=ctk.CTkFont(weight="bold"))
        lbl_ev.pack(anchor="w", pady=(0, 10))
        
        evidencias = reporte.get("evidencias", [])
        if not evidencias:
            ctk.CTkLabel(main_scroll, text="No hay evidencias adjuntas.", text_color="gray").pack(anchor="w")
        else:
            for ev in evidencias:
                url = ev.get("evidencia_url") or ev.get("ruta_local")
                if not url: continue
                
                f_ev = ctk.CTkFrame(main_scroll, fg_color="#1e293b")
                f_ev.pack(fill="x", pady=2)
                
                lbl_img = ctk.CTkLabel(f_ev, text="Cargando...", width=80, height=80)
                lbl_img.pack(side="left", padx=10, pady=5)
                
                ctk.CTkLabel(f_ev, text=url.split("/")[-1][:30], anchor="w").pack(side="left", padx=10, expand=True, fill="x")
                
                import webbrowser
                ctk.CTkButton(
                    f_ev, text="Abrir", width=60,
                    command=lambda u=url: webbrowser.open(u)
                ).pack(side="right", padx=10, pady=5)
                
                def _cargar_thumb_rep(u=url, lbl=lbl_img):
                    from core.thumbnailer import generar_miniatura
                    img = generar_miniatura(u, size=(80, 80))
                    if img:
                        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                        lbl.configure(text="", image=ctk_img)
                        lbl.image = ctk_img
                    else:
                        lbl.configure(text="Sin vista previa")
                
                import threading
                threading.Thread(target=_cargar_thumb_rep, daemon=True).start()
