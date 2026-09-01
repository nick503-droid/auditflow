import customtkinter as ctk
from tkinter import messagebox, simpledialog
from datetime import datetime
import os
import threading
import webbrowser
import requests

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
from core.thumbnailer import generar_miniatura

# ─── SISTEMA DE DISEÑO ───────────────────────────────────────────────────────
BG_COLOR = "#0f172a"
CARD_COLOR = "#1e293b"
CARD_HOVER = "#334155"
TEXT_MAIN = "#f8fafc"
TEXT_SEC = "#94a3b8"
ACCENT_COLOR = "#4f46e5"
ACCENT_HOVER = "#4338ca"
SUCCESS_COLOR = "#10b981"
SUCCESS_HOVER = "#059669"
WARN_COLOR = "#f59e0b"
DANGER_COLOR = "#ef4444"
DANGER_HOVER = "#dc2626"
CORNER_RADIUS = 15

# Paleta específica para urgencias en admin
URGENCIA_COLORS_ADMIN = {
    "comentar": {"bg": "#1e293b", "border": "#3b82f6"}, # Slate 800, borde azul
    "leve":     {"bg": "#1e293b", "border": "#10b981"}, # Borde verde
    "medio":    {"bg": "#1e293b", "border": "#f59e0b"}, # Borde ámbar
    "grave":    {"bg": "#1e293b", "border": "#ef4444"}, # Borde rojo
}
URGENCIA_VALOR_A_DISPLAY = {
    "comentar": "Comentar",
    "leve": "Leve",
    "medio": "Medio",
    "grave": "Grave"
}


class AdminFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, **kwargs):
        super().__init__(master, fg_color=BG_COLOR, **kwargs)
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
        self.top_bar.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 10))
        
        self.lbl_titulo = ctk.CTkLabel(
            self.top_bar, 
            text="", 
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=TEXT_MAIN
        )
        self.lbl_titulo.pack(side="left")
        
        self.btn_back = ctk.CTkButton(
            self.top_bar, 
            text="← Volver", 
            width=100, height=36,
            fg_color="transparent", 
            hover_color=CARD_HOVER,
            border_width=1,
            border_color=CARD_COLOR,
            text_color=TEXT_SEC,
            font=ctk.CTkFont(size=13),
            command=self._on_back
        )
        self.btn_back.pack(side="right")
        
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        
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
        self._actualizar_top_bar("🗂️ Explorador de Archivos")
        self._limpiar_container()
        
        frame_opciones = ctk.CTkFrame(self.container, fg_color="transparent")
        frame_opciones.pack(expand=True, fill="both")
        frame_opciones.grid_columnconfigure((0, 1), weight=1, uniform="col")
        frame_opciones.grid_rowconfigure(0, weight=1)
        
        # Función auxiliar para tarjetas de módulo
        def crear_tarjeta_admin(parent, col, icono, titulo, desc, comando):
            card = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=CORNER_RADIUS, cursor="hand2")
            card.grid(row=0, column=col, sticky="nsew", padx=12, pady=12)
            
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(expand=True)
            
            lbl_icon = ctk.CTkLabel(inner, text=icono, font=ctk.CTkFont(size=48))
            lbl_icon.pack(pady=(0, 12))
            
            lbl_tit = ctk.CTkLabel(inner, text=titulo, font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_MAIN)
            lbl_tit.pack(pady=(0, 6))
            
            lbl_desc = ctk.CTkLabel(inner, text=desc, font=ctk.CTkFont(size=13), text_color=TEXT_SEC)
            lbl_desc.pack()
            
            def hover_in(e): card.configure(fg_color=CARD_HOVER)
            def hover_out(e): card.configure(fg_color=CARD_COLOR)
            def on_click(e): comando()
            
            for w in (card, inner, lbl_icon, lbl_tit, lbl_desc):
                w.bind("<Enter>", hover_in)
                w.bind("<Leave>", hover_out)
                w.bind("<Button-1>", on_click)
                
            return card

        # Tarjeta Bitácoras
        crear_tarjeta_admin(
            frame_opciones, 0, "📅", "Explorar Bitácoras", 
            "Busca anotaciones diarias por fecha y aplica filtros.", 
            self._abrir_vista_bitacoras
        )
        
        # Tarjeta Reportes
        crear_tarjeta_admin(
            frame_opciones, 1, "📊", "Explorar Reportes", 
            "Edita o elimina reportes completos (nube y borradores).", 
            self._abrir_vista_reportes
        )

    # ─── VISTA REPORTES ───────────────────────────────────────────────────────

    def _abrir_vista_reportes(self):
        self.vista_actual = "REPORTES"
        self._actualizar_top_bar("📁 Directorio de Reportes")
        self._limpiar_container()
        
        scroll = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        lbl_cargando = ctk.CTkLabel(scroll, text="Cargando reportes...", text_color=TEXT_SEC)
        lbl_cargando.pack(pady=40)
        
        def _fetch():
            nube = obtener_reportes()
            locales = obtener_reportes_pendientes()
            self.after(0, lambda: self._mostrar_lista_reportes(scroll, nube, locales, lbl_cargando))
            
        threading.Thread(target=_fetch, daemon=True).start()

    def _mostrar_lista_reportes(self, parent, reportes_nube, reportes_locales, lbl_cargando):
        lbl_cargando.destroy()
        
        if not reportes_nube and not reportes_locales:
            ctk.CTkLabel(parent, text="No hay reportes disponibles.", text_color=TEXT_SEC).pack(pady=40)
            return
            
        # Mostrar locales primero
        for r in reportes_locales:
            self._crear_item_reporte(parent, r, es_local=True)
            
        # Mostrar de la nube
        for r in reportes_nube:
            self._crear_item_reporte(parent, r, es_local=False)

    def _crear_item_reporte(self, parent, reporte: dict, es_local: bool):
        card = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=10)
        card.pack(fill="x", pady=6)
        
        icono = "💾 [Borrador]" if es_local else "☁️ [Nube]"
        titulo = reporte.get("titulo") or "Sin título"
        fecha = reporte.get("fecha_jornada") or ""
        if isinstance(fecha, str):
            fecha = fecha[:10]
            
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=20, pady=16)
        
        ctk.CTkLabel(
            info_frame, 
            text=titulo, 
            font=ctk.CTkFont(size=15, weight="bold"), 
            text_color=TEXT_MAIN,
            anchor="w"
        ).pack(fill="x")
        
        ctk.CTkLabel(
            info_frame, 
            text=f"{icono}   ·   Fecha: {fecha}", 
            font=ctk.CTkFont(size=12), 
            text_color=TEXT_SEC, 
            anchor="w"
        ).pack(fill="x", pady=(2, 0))
        
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=20, pady=16)
        
        # Botón Ver
        ctk.CTkButton(
            btn_frame, text="👁️ Ver", width=70, height=32,
            fg_color=SUCCESS_COLOR, hover_color=SUCCESS_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda r=reporte, l=es_local: self._abrir_reporte_detalle(r, l)
        ).pack(side="left", padx=4)
        
        # Botón Renombrar (Solo nube por ahora)
        if not es_local:
            ctk.CTkButton(
                btn_frame, text="✏️ Editar", width=80, height=32,
                fg_color="transparent", hover_color=CARD_HOVER,
                border_width=1, border_color=TEXT_SEC, text_color=TEXT_MAIN,
                font=ctk.CTkFont(size=12),
                command=lambda r=reporte: self._renombrar_reporte(r)
            ).pack(side="left", padx=4)
            
        # Botón Eliminar
        ctk.CTkButton(
            btn_frame, text="🗑️ Eliminar", width=80, height=32,
            fg_color="transparent", hover_color=DANGER_HOVER,
            border_width=1, border_color=DANGER_COLOR, text_color=DANGER_COLOR,
            font=ctk.CTkFont(size=12),
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
        if not messagebox.askyesno("Confirmar Peligro", "¿Eliminar este reporte permanentemente?\nEsta acción no se puede deshacer."):
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
        self._actualizar_top_bar("📁 Directorio de Bitácoras")
        self._limpiar_container()
        
        scroll = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        lbl_cargando = ctk.CTkLabel(scroll, text="Cargando fechas de bitácoras...", text_color=TEXT_SEC)
        lbl_cargando.pack(pady=40)
        
        def _fetch():
            bitacoras = obtener_bitacoras_todas()
            fechas = sorted(list(set(b["fecha"] for b in bitacoras if b.get("fecha"))), reverse=True)
            self.after(0, lambda: self._mostrar_lista_fechas(scroll, fechas, lbl_cargando))
            
        threading.Thread(target=_fetch, daemon=True).start()

    def _mostrar_lista_fechas(self, parent, fechas, lbl_cargando):
        lbl_cargando.destroy()
        
        if not fechas:
            ctk.CTkLabel(parent, text="No hay bitácoras disponibles.", text_color=TEXT_SEC).pack(pady=40)
            return
            
        # Grid layout for dates
        row, col = 0, 0
        for f in fechas:
            card = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=10, cursor="hand2")
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            
            lbl_icon = ctk.CTkLabel(card, text="📁", font=ctk.CTkFont(size=32))
            lbl_icon.pack(pady=(16, 4))
            
            lbl_tit = ctk.CTkLabel(card, text=f, font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN)
            lbl_tit.pack(padx=24, pady=(0, 16))
            
            def hover_in(e, c=card): c.configure(fg_color=CARD_HOVER)
            def hover_out(e, c=card): c.configure(fg_color=CARD_COLOR)
            def on_click(e, d=f): self._abrir_bitacora_dia(d)
            
            for w in (card, lbl_icon, lbl_tit):
                w.bind("<Enter>", hover_in)
                w.bind("<Leave>", hover_out)
                w.bind("<Button-1>", on_click)
                
            col += 1
            if col > 3:
                col = 0
                row += 1

    # ─── VISTA BITÁCORA DETALLE (DIA) ────────────────────────────────────────

    def _abrir_bitacora_dia(self, fecha: str):
        self.vista_actual = "BITACORA_DIA"
        self.fecha_seleccionada = fecha
        self._actualizar_top_bar(f"📅 Detalles de Bitácora ({fecha})")
        self._limpiar_container()
        
        # Filtros
        filtro_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        filtro_frame.pack(fill="x", pady=(0, 10))
        
        usuarios_vals = ["Todos"] + list(self.usuarios_dict.values())
        rest_vals = ["Todos"] + list(self.restaurantes_dict.values())
        
        # Configuración visual de OptionMenus
        om_kwargs = dict(
            fg_color=CARD_COLOR,
            button_color=CARD_COLOR,
            button_hover_color=CARD_HOVER,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=12)
        )
        
        ctk.CTkLabel(filtro_frame, text="Usuario:", text_color=TEXT_SEC, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        ctk.CTkOptionMenu(filtro_frame, variable=self.filtro_usuario, values=usuarios_vals, command=self._aplicar_filtros, width=130, **om_kwargs).pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(filtro_frame, text="Restaurante:", text_color=TEXT_SEC, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        ctk.CTkOptionMenu(filtro_frame, variable=self.filtro_restaurante, values=rest_vals, command=self._aplicar_filtros, width=130, **om_kwargs).pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(filtro_frame, text="Urgencia:", text_color=TEXT_SEC, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        ctk.CTkOptionMenu(filtro_frame, variable=self.filtro_urgencia, values=["Todas", "Comentar", "Leve", "Medio", "Grave"], command=self._aplicar_filtros, width=100, **om_kwargs).pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(filtro_frame, text="Evidencias:", text_color=TEXT_SEC, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        ctk.CTkOptionMenu(filtro_frame, variable=self.filtro_evidencia, values=["Evidencias", "Sí", "No"], command=self._aplicar_filtros, width=90, **om_kwargs).pack(side="left")
        
        # Área de filas
        self.scroll_filas = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        self.scroll_filas.pack(fill="both", expand=True)
        
        lbl_cargando = ctk.CTkLabel(self.scroll_filas, text="Cargando anotaciones...", text_color=TEXT_SEC)
        lbl_cargando.pack(pady=40)
        
        def _fetch():
            self.filas_bitacora = obtener_bitacoras_por_fecha(fecha)
            self.after(0, lambda: self._aplicar_filtros(None))
            
        threading.Thread(target=_fetch, daemon=True).start()

    def _aplicar_filtros(self, _=None):
        for w in self.scroll_filas.winfo_children():
            if isinstance(w, ctk.CTkFrame):
                w.destroy()
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
            if f_usr != "Todos" and f_usr != usr_nombre: continue
                
            # Match Restaurante
            rst_nombre = fila.get("restaurante", {}).get("nombre", "")
            if f_rst != "Todos" and f_rst != rst_nombre: continue
                
            # Match Urgencia
            urg_backend = fila.get("urgencia", "leve")
            urg_display = URGENCIA_VALOR_A_DISPLAY.get(urg_backend, "Leve")
            if f_urg != "Todas" and f_urg != urg_display: continue
                
            # Match Evidencia
            tiene_ev = len(fila.get("evidencias", [])) > 0 or bool(fila.get("evidencia_url"))
            if f_evi == "Sí" and not tiene_ev: continue
            if f_evi == "No" and tiene_ev: continue
                
            filas_filtradas.append(fila)
            
        if not filas_filtradas:
            ctk.CTkLabel(self.scroll_filas, text="No hay anotaciones que coincidan con los filtros.", text_color=TEXT_SEC).pack(pady=40)
            return
            
        for fila in filas_filtradas:
            self._crear_item_bitacora(self.scroll_filas, fila)
            
    def _crear_item_bitacora(self, parent, fila):
        urg = fila.get("urgencia", "leve")
        estilo = URGENCIA_COLORS_ADMIN.get(urg, URGENCIA_COLORS_ADMIN["leve"])
        
        card = ctk.CTkFrame(
            parent, 
            fg_color=estilo["bg"], 
            border_width=2, 
            border_color=estilo["border"],
            corner_radius=10
        )
        card.pack(fill="x", pady=6)
        
        # Info básica
        hora = fila.get("hora", "--:--")
        usr = fila.get("usuario", {}).get("nombre", "Usuario")
        rst = fila.get("restaurante", {}).get("nombre", "Restaurante")
        desc = fila.get("descripcion", "")
        
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=20, pady=16)
        
        header = ctk.CTkLabel(
            info_frame, 
            text=f"🕒 {hora}   ·   🏪 {rst}   ·   👤 {usr}", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SEC,
            anchor="w"
        )
        header.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(
            info_frame, 
            text=desc, 
            justify="left", 
            anchor="w", 
            wraplength=600,
            font=ctk.CTkFont(size=14),
            text_color=TEXT_MAIN
        ).pack(fill="x")
        
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=20, pady=16)
        
        tiene_ev = len(fila.get("evidencias", [])) > 0 or bool(fila.get("evidencia_url"))
        if tiene_ev:
            ctk.CTkButton(
                btn_frame, text="👁️ Evidencias", width=100, height=32,
                fg_color="transparent", hover_color=CARD_HOVER,
                border_width=1, border_color=ACCENT_COLOR, text_color=ACCENT_COLOR,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda b=fila: self._abrir_evidencias_bitacora(b)
            ).pack(side="left", padx=8)
            
        # Botón eliminar
        ctk.CTkButton(
            btn_frame, text="🗑️", width=40, height=32,
            fg_color="transparent", hover_color=DANGER_HOVER,
            border_width=1, border_color=DANGER_COLOR, text_color=DANGER_COLOR,
            command=lambda b=fila: self._eliminar_bitacora_fila(b)
        ).pack(side="left")
        
    def _eliminar_bitacora_fila(self, fila):
        if not messagebox.askyesno("Confirmar Peligro", "¿Eliminar esta fila de la bitácora permanentemente?"):
            return
            
        if eliminar_bitacora_remota(fila["id"]):
            self.filas_bitacora = [f for f in self.filas_bitacora if f["id"] != fila["id"]]
            self._aplicar_filtros()
        else:
            messagebox.showerror("Error", "No se pudo eliminar la fila.")

    def _abrir_evidencias_bitacora(self, fila):
        evidencias_list = []
        if fila.get("evidencia_url"):
            evidencias_list.append({"url": fila["evidencia_url"], "id": None, "tipo": "legacy"})
        for ev in fila.get("evidencias", []):
            if ev.get("evidencia_url"):
                evidencias_list.append({"url": ev["evidencia_url"], "id": ev["id"], "tipo": "bitacora"})
                
        if not evidencias_list:
            messagebox.showinfo("Info", "No se encontraron URLs de evidencia validas.")
            return

        # Construir nombre de carpeta identificable: fecha / texto_12chars
        fecha = fila.get("fecha_jornada") or fila.get("fecha", "")
        if isinstance(fecha, str): fecha = fecha[:10]
        texto = fila.get("descripcion") or fila.get("notas") or fila.get("observacion") or ""
        texto_corto = texto.strip()[:12].replace("/", "-").replace("\\", "-") if texto else "bitacora"
        # Estructura: fecha/texto_12chars
        nombre_fecha = self._sanitizar_nombre_carpeta(fecha) if fecha else "sin-fecha"
        nombre_sub = self._sanitizar_nombre_carpeta(texto_corto)

        def _nombre_carpeta_bit():
            """Devuelve (carpeta_raiz_fecha, subcarpeta_info)."""
            return nombre_fecha, nombre_sub

        self._mostrar_popup_evidencias(evidencias_list, nombre_fecha, nombre_sub)

    def _mostrar_popup_evidencias(self, evidencias_list, nombre_fecha="sin-fecha", nombre_sub="bitacora"):
        # Carpeta destino: Documents/AuditFlow/Bitacoras/fecha/info_12chars/
        carpeta_descarga = os.path.join(
            os.path.expanduser("~"), "Documents", "AuditFlow", "Bitacoras",
            self._sanitizar_nombre_carpeta(nombre_fecha),
            self._sanitizar_nombre_carpeta(nombre_sub),
        )
        popup = ctk.CTkToplevel(self.controlador)
        popup.title("Visor de Evidencias")
        popup.geometry("900x600")
        popup.minsize(800, 560)
        popup.resizable(True, True)
        popup.configure(fg_color=BG_COLOR)
        popup.attributes("-topmost", True)

        # Barra superior con descarga múltiple
        top_bar = ctk.CTkFrame(popup, fg_color=CARD_COLOR, height=44)
        top_bar.pack(fill="x", padx=20, pady=(16, 0))
        top_bar.pack_propagate(False)

        lbl_prog = ctk.CTkLabel(top_bar, text="", font=ctk.CTkFont(size=11), text_color=TEXT_SEC)
        lbl_prog.pack(side="left", padx=14)

        checkboxes: list[tuple[ctk.BooleanVar, str]] = []

        def _descargar_todos():
            selec = [(nombre, url) for var, url in checkboxes for nombre in [url.rsplit("/", 1)[-1]] if var.get()]
            if not selec:
                messagebox.showwarning("Sin selección", "Marca al menos una evidencia.", parent=popup)
                return
            os.makedirs(carpeta_descarga, exist_ok=True)
            btn_dl_todos.configure(state="disabled")
            threading.Thread(target=self._descargar_lote_admin,
                             args=(selec, carpeta_descarga, lbl_prog, btn_dl_todos, popup), daemon=True).start()

        btn_dl_todos = ctk.CTkButton(
            top_bar, text="⬇️ Descargar Selección", width=160, height=30,
            fg_color="#0f766e", hover_color="#0d9488", font=ctk.CTkFont(size=11),
            command=_descargar_todos
        )
        btn_dl_todos.pack(side="right", padx=14, pady=7)

        scroll = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)
        
        for item in evidencias_list:
            url = item["url"]
            f_ev = ctk.CTkFrame(scroll, fg_color=CARD_COLOR, corner_radius=10)
            f_ev.pack(fill="x", pady=8)
            
            # Checkbox
            var = ctk.BooleanVar(value=False)
            checkboxes.append((var, url))
            ctk.CTkCheckBox(f_ev, text="", variable=var, width=24).pack(side="left", padx=(14, 4), pady=16)

            lbl_img = ctk.CTkLabel(f_ev, text="Cargando...", width=140, height=90, fg_color=BG_COLOR, corner_radius=8)
            lbl_img.pack(side="left", padx=8, pady=12)
            
            nombre_arch = url.rsplit("/", 1)[-1]
            nombre_corto = (nombre_arch[:38] + "...") if len(nombre_arch) > 38 else nombre_arch
            ctk.CTkLabel(
                f_ev, text=f"{nombre_fecha}/{nombre_sub} — {nombre_corto}",
                font=ctk.CTkFont(size=12), text_color=TEXT_MAIN, anchor="w"
            ).pack(side="left", padx=10, expand=True, fill="x")

            # Botón descarga individual
            def _dl_individual(u=url):
                os.makedirs(carpeta_descarga, exist_ok=True)
                nombre_f = u.rsplit("/", 1)[-1]
                lbl_prog.configure(text=f"Descargando {nombre_f[:20]}…")
                threading.Thread(target=self._descargar_lote_admin,
                                 args=([(nombre_f, u)], carpeta_descarga, lbl_prog, None, popup), daemon=True).start()

            ctk.CTkButton(
                f_ev, text="⬇️", width=36, height=32,
                fg_color="#0f766e", hover_color="#0d9488",
                command=_dl_individual
            ).pack(side="right", padx=4)

            ctk.CTkButton(
                f_ev, text="Abrir", width=70, height=32,
                fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda u=url: webbrowser.open(u)
            ).pack(side="right", padx=(4, 8))

            if item["id"]:
                def _del_ev(i=item, w=f_ev):
                    self._eliminar_evidencia_admin(i, w)
                ctk.CTkButton(
                    f_ev, text="🗑️", width=36, height=32,
                    fg_color="#ef4444", hover_color="#dc2626",
                    command=_del_ev
                ).pack(side="right", padx=(4, 0))
            
            # Load thumbnail in background
            def _cargar_thumb(u=url, lbl=lbl_img):
                try:
                    img = generar_miniatura(u, size=(140, 90))
                    if img:
                        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                        lbl.configure(text="", image=ctk_img)
                        lbl.image = ctk_img
                    else:
                        lbl.configure(text="Sin vista previa", text_color=TEXT_SEC)
                except Exception:
                    lbl.configure(text="Sin vista previa", text_color=TEXT_SEC)
            
            threading.Thread(target=_cargar_thumb, daemon=True).start()

    # ─── VISTA REPORTE DETALLE ───────────────────────────────────────────────

    def _abrir_reporte_detalle(self, reporte, es_local):
        self.vista_actual = "REPORTE_DETALLE"
        titulo = reporte.get("titulo") or "Reporte"
        self._actualizar_top_bar(f"📝 {titulo}")
        self._limpiar_container()
        
        main_scroll = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        main_scroll.pack(fill="both", expand=True)
        
        # Metadata
        meta_frame = ctk.CTkFrame(main_scroll, fg_color=CARD_COLOR, corner_radius=10)
        meta_frame.pack(fill="x", pady=(0, 20))
        
        fecha = reporte.get("fecha_jornada") or ""
        if isinstance(fecha, str): fecha = fecha[:10]
        usr = reporte.get("usuario", {}).get("nombre", "Usuario") if not es_local else "Local"
        rst = reporte.get("restaurante", {}).get("nombre", "Restaurante") if not es_local else "Local"
        
        ctk.CTkLabel(
            meta_frame, 
            text=f"🕒 Fecha: {fecha}   ·   🏪 Restaurante: {rst}   ·   👤 Autor: {usr}", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_SEC,
            anchor="w"
        ).pack(pady=16, padx=20, fill="x")
        
        # Texto
        notas = reporte.get("notas_finales", "")
        txt = ctk.CTkTextbox(
            main_scroll, 
            height=300, 
            fg_color=BG_COLOR, 
            text_color=TEXT_MAIN,
            border_width=1,
            border_color=CARD_COLOR,
            corner_radius=10,
            font=("Consolas", 14)
        )
        txt.pack(fill="x", pady=(0, 24))
        txt.configure(state="normal")
        txt.insert("1.0", notas)
        txt.configure(state="disabled")
        
        # Evidencias
        header_ev_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        header_ev_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            header_ev_frame, 
            text="Evidencias Adjuntas", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_MAIN
        ).pack(side="left")

        evidencias = reporte.get("evidencias", [])
        urls_ev = [ev.get("evidencia_url") or ev.get("ruta_local") for ev in evidencias if ev.get("evidencia_url") or ev.get("ruta_local")]

        # Carpeta: Documents/AuditFlow/Reportes/titulo - evidencias/
        nombre_carpeta_rep = self._sanitizar_nombre_carpeta(f"{titulo} - evidencias")
        carpeta_rep = os.path.join(os.path.expanduser("~"), "Documents", "AuditFlow", "Reportes", nombre_carpeta_rep)
        lbl_prog_rep = ctk.CTkLabel(header_ev_frame, text="", font=ctk.CTkFont(size=11), text_color=TEXT_SEC)
        lbl_prog_rep.pack(side="left", padx=14)

        checkboxes_rep: list[tuple[ctk.BooleanVar, str]] = []

        def _dl_todos_rep():
            selec = [(url.rsplit("/", 1)[-1], url) for var, url in checkboxes_rep if var.get()]
            if not selec:
                messagebox.showwarning("Sin selección", "Marca al menos una evidencia.")
                return
            os.makedirs(carpeta_rep, exist_ok=True)
            btn_dl_rep.configure(state="disabled")
            threading.Thread(target=self._descargar_lote_admin,
                             args=(selec, carpeta_rep, lbl_prog_rep, btn_dl_rep, None), daemon=True).start()

        btn_dl_rep = ctk.CTkButton(
            header_ev_frame, text="⬇️ Descargar Selección", width=160, height=30,
            fg_color="#0f766e", hover_color="#0d9488", font=ctk.CTkFont(size=11),
            command=_dl_todos_rep
        )
        btn_dl_rep.pack(side="right")
        
        if not evidencias:
            ctk.CTkLabel(main_scroll, text="No hay evidencias adjuntas a este reporte.", text_color=TEXT_SEC).pack(anchor="w")
        else:
            for ev in evidencias:
                url = ev.get("evidencia_url") or ev.get("ruta_local")
                if not url: continue
                
                f_ev = ctk.CTkFrame(main_scroll, fg_color=CARD_COLOR, corner_radius=10)
                f_ev.pack(fill="x", pady=6)

                # Checkbox
                var = ctk.BooleanVar(value=False)
                checkboxes_rep.append((var, url))
                ctk.CTkCheckBox(f_ev, text="", variable=var, width=24).pack(side="left", padx=(14, 4), pady=12)
                
                lbl_img = ctk.CTkLabel(f_ev, text="Cargando...", width=100, height=80, fg_color=BG_COLOR, corner_radius=8)
                lbl_img.pack(side="left", padx=8, pady=10)
                
                nombre_arch = url.rsplit("/", 1)[-1]
                nombre_corto = (nombre_arch[:35] + "...") if len(nombre_arch) > 35 else nombre_arch
                ctk.CTkLabel(
                    f_ev, 
                    text=f"{titulo[:25]} — {nombre_corto}",
                    font=ctk.CTkFont(size=12),
                    text_color=TEXT_MAIN,
                    anchor="w"
                ).pack(side="left", padx=10, expand=True, fill="x")

                # Botón descarga individual
                def _dl_ind(u=url):
                    os.makedirs(carpeta_rep, exist_ok=True)
                    nf = u.rsplit("/", 1)[-1]
                    lbl_prog_rep.configure(text=f"Descargando {nf[:20]}…")
                    threading.Thread(target=self._descargar_lote_admin,
                                     args=([(nf, u)], carpeta_rep, lbl_prog_rep, None, None), daemon=True).start()

                ctk.CTkButton(
                    f_ev, text="⬇️", width=36, height=30,
                    fg_color="#0f766e", hover_color="#0d9488",
                    command=_dl_ind
                ).pack(side="right", padx=4)

                ctk.CTkButton(
                    f_ev, text="Abrir", width=70, height=30,
                    fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=lambda u=url: webbrowser.open(u)
                ).pack(side="right", padx=(4, 8))
                
                ev_id = ev.get("id")
                is_nube = ev.get("evidencia_url") is not None
                if ev_id and is_nube:
                    def _del_rep_ev(id=ev_id, w=f_ev):
                        self._eliminar_evidencia_admin({"id": id, "tipo": "reporte"}, w)
                    ctk.CTkButton(
                        f_ev, text="🗑️", width=36, height=30,
                        fg_color="#ef4444", hover_color="#dc2626",
                        command=_del_rep_ev
                    ).pack(side="right", padx=(4, 0))
                
                def _cargar_thumb_rep(u=url, lbl=lbl_img):
                    try:
                        img = generar_miniatura(u, size=(100, 80))
                        if img:
                            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                            lbl.configure(text="", image=ctk_img)
                            lbl.image = ctk_img
                        else:
                            lbl.configure(text="Sin previa", text_color=TEXT_SEC)
                    except Exception:
                        lbl.configure(text="Sin previa", text_color=TEXT_SEC)
                
                threading.Thread(target=_cargar_thumb_rep, daemon=True).start()

    # ─── Utilidades de descarga ──────────────────────────────────────────────────────

    @staticmethod
    def _sanitizar_nombre_carpeta(nombre: str) -> str:
        """Elimina caracteres inválidos y saltos de línea para nombres de carpeta en Windows/Linux."""
        nombre = nombre.replace("\n", " ").replace("\r", "")
        for ch in r'<>:"/\|?*':
            nombre = nombre.replace(ch, "-")
        return nombre.strip()[:80] or "AuditFlow"

    def _descargar_lote_admin(
        self,
        items: list[tuple[str, str]],
        carpeta: str,
        lbl_prog,
        btn_reactivar,
        parent_win,
    ):
        """
        Hilo secundario: descarga cada (nombre, url) con requests stream=True.
        Informa progreso mediante self.after(0, ...).
        """
        total = len(items)
        exitos = 0
        errores = []

        for idx, (nombre, url) in enumerate(items, start=1):
            self.after(0, lbl_prog.configure, {"text": f"Descargando {idx}/{total}…"})
            try:
                ruta_salida = os.path.join(carpeta, nombre)
                # Saltar si el archivo ya existe (validación de duplicados)
                if os.path.exists(ruta_salida):
                    exitos += 1  # contar como éxito si ya está descargado
                    continue

                with requests.get(url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(ruta_salida, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                exitos += 1
            except Exception as e:
                errores.append(f"{nombre}: {e}")

        if btn_reactivar:
            self.after(0, btn_reactivar.configure, {"state": "normal"})

        def _fin():
            msg = f"Descarga terminada: {exitos} exitosos."
            if errores:
                msg += f"\n\nErrores ({len(errores)}):\n" + "\n".join(errores[:5])
                if len(errores) > 5:
                    msg += "\n..."
            lbl_prog.configure(text=msg)
            if not errores:
                messagebox.showinfo("Descarga completa",
                    f"✅ {exitos} archivos guardados en:\n{carpeta}")
            else:
                messagebox.showwarning("Descarga parcial",
                    f"Se descargaron {exitos} de {total}.\n\nErrores:\n" + "\n".join(errores))

        self.after(0, _fin)

    def _eliminar_evidencia_admin(self, item: dict, widget: ctk.CTkFrame):
        popup_window = widget.winfo_toplevel()
        respuesta = messagebox.askyesno(
            "Eliminar Evidencia", 
            "Esta acción eliminará el archivo permanentemente del servidor.\n\n¿Deseas continuar?",
            parent=popup_window
        )
        if not respuesta:
            return
            
        try:
            import requests
            from api.client import API_BASE_URL
            
            tipo = item["tipo"]
            ev_id = item["id"]
            endpoint = f"{API_BASE_URL}/bitacoras/evidencia/{ev_id}" if tipo == "bitacora" else f"{API_BASE_URL}/evidencias-reporte/{ev_id}"
            
            resp = requests.delete(endpoint, timeout=10)
            if resp.status_code in (200, 204):
                widget.destroy() # Feedback visual
                self.ultimo_hash_bitacoras = None # Forzar recarga de bitácoras si aplica
            else:
                messagebox.showerror("Error", f"No se pudo eliminar: {resp.text}", parent=popup_window)
        except Exception as e:
            messagebox.showerror("Error", f"Error de red: {e}", parent=popup_window)
