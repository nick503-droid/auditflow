"""
reportes_frame.py — Módulo de reportes de auditoría para AuditFlow PC App (v3.0).

Arquitectura:
  · 100% Offline-First: el editor se abre SIEMPRE, sin esperar red.
  · El restaurante se elige DENTRO de este frame (no en SelectionFrame).
  · Búsqueda inteligente: barra de texto que filtra los reportes en tiempo real.
  · Polling worker cada 5 s: crea/actualiza en la nube silenciosamente.
  · Dos indicadores de sync: uno para texto (topbar) y otro para evidencias (panel).
  · Modo Zen: botón para ocultar el panel lateral y tener el textbox a pantalla completa.
  · Evidencias manuales adjuntas se copian a ~/Documents/AuditFlow/Reportes/<título>/.
  · Grabaciones van a AuditFlow_Temp (sin cambio) y se suben con prefijo de carpeta a MinIO.
  · Tipos soportados: .mp4, .webm, .mkv, .avi, .jpg, .jpeg, .png
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import keyboard
from datetime import datetime
import os
import sys
import subprocess
import threading
import time
import shutil

from db.local_db import (
    obtener_o_crear_borrador,
    actualizar_notas,
    agregar_evidencia,
    obtener_evidencias,
    eliminar_borrador_completo,
    marcar_reporte_pendiente,
    marcar_reporte_sincronizado,
    marcar_notas_pendientes,
    obtener_borrador_completo,
    ruta_evidencia_reporte,
    prefijo_nube_reporte,
    sanitizar_nombre_carpeta,
    inicializar_db,
    listar_borradores_activos,
)
from api.client import (
    crear_reporte,
    crear_evidencia_reporte,
    subir_archivo_con_destino,
    obtener_reportes,
    obtener_restaurantes,
    actualizar_reporte,
)
from core.recorder import GrabadorPantalla, es_archivo_grabado
from core.sync_helper import actualizar_indicador_reporte


# ─── Tipos de archivo soportados ─────────────────────────────────────────────
TIPOS_EVIDENCIA = [
    ("Videos e imágenes", "*.mp4;*.webm;*.mkv;*.avi;*.jpg;*.jpeg;*.png"),
    ("Video", "*.mp4;*.webm;*.mkv;*.avi"),
    ("Imagen", "*.jpg;*.jpeg;*.png"),
    ("Todos los archivos", "*.*"),
]


class ReportesFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.usuario = usuario

        # Estado de restaurante y reporte (se llenan en la pantalla de setup)
        self.restaurante = None
        self.restaurante_seleccionado = None  # dict con id y nombre
        self.restaurantes_data = {}           # nombre → dict completo

        # Estado del reporte activo
        self.titulo_reporte = None
        self.codigo_reporte = None
        self.reporte_remoto_id = None
        self._viene_de_nube = False
        self._texto_pendiente = False
        self._finalizar_pendiente = False

        # Búsqueda de reportes en nube
        self.reportes_data = {}   # titulo_clave → dict reporte
        self.reportes_filtrados = []  # lista de claves filtradas actualmente

        # Grabador y estado de grabación
        self.grabador = GrabadorPantalla()
        self.grabando = False
        self.indicador = None

        # Debounce para autoguardado
        self._debounce_id = None

        # Panel lateral visible o no
        self._panel_visible = False

        # Hilo de polling
        self.hilo_polling_activo = False

        # Borrador SQLite (se inicializa cuando se conoce el restaurante)
        self.borrador = None

        inicializar_db()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_ui_setup()
        # Cargar catálogos en background
        threading.Thread(target=self._cargar_datos_setup, daemon=True).start()

        self.bind("<Destroy>", self._al_destruir)

    # ═══════════════════════════════════════════════════════════════════════════
    # PANTALLA 1: SETUP
    # ═══════════════════════════════════════════════════════════════════════════

    def _construir_ui_setup(self):
        """
        Pantalla inicial: selección de restaurante, crear nuevo reporte o
        continuar uno existente (con buscador en tiempo real).
        """
        self.frame_setup = ctk.CTkFrame(self, fg_color="#0f172a")
        self.frame_setup.grid(row=0, column=0, sticky="nsew")
        self.frame_setup.grid_rowconfigure(0, weight=1)
        self.frame_setup.grid_columnconfigure(0, weight=1)

        # Contenedor scrollable para que quepa en ventanas pequeñas
        scroll = ctk.CTkScrollableFrame(self.frame_setup, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        contenedor = ctk.CTkFrame(scroll, fg_color="transparent")
        contenedor.grid(row=0, column=0, sticky="nsew", padx=24, pady=16)
        contenedor.grid_columnconfigure(0, weight=1)

        row = 0

        # ── Título ────────────────────────────────────────────────────────
        ctk.CTkLabel(
            contenedor,
            text="📊  Módulo de Reportes",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="white",
        ).grid(row=row, column=0, sticky="w", pady=(0, 2))
        row += 1

        ctk.CTkLabel(
            contenedor,
            text=f"Auditor: {self.usuario['nombre']}",
            font=ctk.CTkFont(size=12),
            text_color="#475569",
        ).grid(row=row, column=0, sticky="w", pady=(0, 16))
        row += 1

        # ── Selector de restaurante ───────────────────────────────────────
        ctk.CTkLabel(
            contenedor,
            text="🏪  Restaurante:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#94a3b8",
        ).grid(row=row, column=0, sticky="w", pady=(0, 4))
        row += 1

        self.dropdown_restaurante = ctk.CTkOptionMenu(
            contenedor,
            values=["Cargando..."],
            command=self._on_restaurante_seleccionado,
            fg_color="#1e293b",
            button_color="#334155",
            button_hover_color="#475569",
            height=38,
            font=ctk.CTkFont(size=13),
            dynamic_resizing=False,
        )
        self.dropdown_restaurante.grid(row=row, column=0, sticky="ew", pady=(0, 20))
        row += 1

        # ── Separador ────────────────────────────────────────────────────
        ctk.CTkFrame(contenedor, height=1, fg_color="#1e293b").grid(
            row=row, column=0, sticky="ew", pady=(0, 20)
        )
        row += 1

        # ── Crear nuevo reporte ───────────────────────────────────────────
        ctk.CTkLabel(
            contenedor,
            text="✏️  Nuevo reporte",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=row, column=0, sticky="w", pady=(0, 6))
        row += 1

        ctk.CTkLabel(
            contenedor,
            text="El título también será el nombre de la carpeta en tu equipo.",
            font=ctk.CTkFont(size=11),
            text_color="#475569",
            wraplength=360,
            justify="left",
        ).grid(row=row, column=0, sticky="w", pady=(0, 6))
        row += 1

        self.entry_titulo = ctk.CTkEntry(
            contenedor,
            placeholder_text="Ej: Riverside (08-25-2026) caso Natalie saco dinero de caja",
            font=ctk.CTkFont(size=13),
            height=40,
        )
        self.entry_titulo.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        self.boton_crear_nube = ctk.CTkButton(
            contenedor,
            text="Crear Reporte y Comenzar  →",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            state="disabled",
            fg_color="#4f46e5",
            hover_color="#4338ca",
            command=self._on_crear_reporte_inicial,
        )
        self.boton_crear_nube.grid(row=row, column=0, sticky="ew", pady=(0, 24))
        row += 1

        # ── Separador ────────────────────────────────────────────────────
        ctk.CTkFrame(contenedor, height=1, fg_color="#1e293b").grid(
            row=row, column=0, sticky="ew", pady=(0, 16)
        )
        row += 1

        # ── Buscar reporte existente ──────────────────────────────────────
        ctk.CTkLabel(
            contenedor,
            text="🔍  Continuar un reporte de la nube",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=row, column=0, sticky="w", pady=(0, 8))
        row += 1

        self.entry_buscar = ctk.CTkEntry(
            contenedor,
            placeholder_text="Buscar por título...",
            height=36,
            font=ctk.CTkFont(size=12),
        )
        self.entry_buscar.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        self.entry_buscar.bind("<KeyRelease>", self._on_buscar_cambiado)
        row += 1

        # Lista de resultados (scrollable, altura fija)
        self.lista_reportes = ctk.CTkScrollableFrame(
            contenedor,
            fg_color="#0f172a",
            height=200,
        )
        self.lista_reportes.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        self.lista_reportes.grid_columnconfigure(0, weight=1)
        row += 1

        # Label de estado para la lista
        self.lbl_lista_estado = ctk.CTkLabel(
            contenedor,
            text="Buscando reportes en la nube...",
            font=ctk.CTkFont(size=11),
            text_color="#475569",
        )
        self.lbl_lista_estado.grid(row=row, column=0, pady=(0, 20))
        row += 1

        # ── Botón volver ──────────────────────────────────────────────────
        ctk.CTkButton(
            contenedor,
            text="← Volver al menú",
            fg_color="transparent",
            border_width=1,
            command=self._volver_al_menu_directo,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 8))

    def _cargar_datos_setup(self):
        """Carga restaurantes y reportes de la nube en background."""
        # 1. Restaurantes
        restaurantes = obtener_restaurantes()
        self.after(0, lambda: self._actualizar_restaurantes(restaurantes))

        # 2. Reportes de la nube y borradores locales
        reportes = obtener_reportes()
        borradores = listar_borradores_activos()
        self.after(0, lambda: self._actualizar_lista_reportes(reportes, borradores))

    def _actualizar_restaurantes(self, restaurantes: list):
        if not self.winfo_exists() or not hasattr(self, "dropdown_restaurante"):
            return
        if restaurantes:
            self.restaurantes_data = {r["nombre"]: r for r in restaurantes}
            self.dropdown_restaurante.configure(values=list(self.restaurantes_data.keys()))
            self.dropdown_restaurante.set("Selecciona un restaurante...")
        else:
            self.dropdown_restaurante.configure(values=["Sin conexión — escribe el título igual"])
            self.dropdown_restaurante.set("Sin conexión — escribe el título igual")

    def _actualizar_lista_reportes(self, reportes: list, borradores: list = None):
        if not self.winfo_exists() or not hasattr(self, "lista_reportes"):
            return

        self.reportes_data = {}
        
        # 1. Agregar borradores locales primero (para que queden arriba)
        if borradores:
            for b in borradores:
                titulo = b.get("titulo")
                if not titulo: continue
                clave = f"💾 {titulo} (Local)"
                self.reportes_data[clave] = {
                    "id": b.get("reporte_remoto_id") or None,
                    "titulo": titulo,
                    "restaurante_id": b["restaurante_id"],
                    "restaurante": {"id": b["restaurante_id"], "nombre": "Desconocido (Offline)"},
                    "notas_finales": b.get("notas_finales", ""),
                    "fecha_jornada": b["fecha_jornada"],
                    "es_borrador_local": True,
                    "borrador_id": b["id"]
                }

        # 2. Agregar reportes de la nube
        if reportes:
            for r in reportes:
                titulo = r.get("titulo") or "Reporte sin título"
                # Evitar duplicar si ya cargamos la versión local de este reporte
                # Si el local tiene reporte_remoto_id == r["id"], lo ignoramos en la lista nube.
                ya_existe = any(
                    v.get("id") == r["id"] and v.get("es_borrador_local") 
                    for v in self.reportes_data.values()
                )
                if ya_existe:
                    continue

                clave = f"☁️ {titulo}"
                contador = 1
                while clave in self.reportes_data:
                    clave = f"☁️ {titulo} ({contador})"
                    contador += 1
                r["es_borrador_local"] = False
                self.reportes_data[clave] = r

        if self.reportes_data:
            self.lbl_lista_estado.configure(
                text=f"{len(self.reportes_data)} reporte(s) disponibles. Escribe para filtrar."
            )
        else:
            self.lbl_lista_estado.configure(
                text="Sin conexión o sin reportes previos."
            )

        self._renderizar_tarjetas_reportes(list(self.reportes_data.keys()))

    def _on_restaurante_seleccionado(self, nombre: str):
        self.restaurante_seleccionado = self.restaurantes_data.get(nombre)
        self._actualizar_estado_boton_crear()

    def _actualizar_estado_boton_crear(self):
        """El botón de crear se activa cuando hay restaurante seleccionado."""
        if self.restaurante_seleccionado and hasattr(self, "boton_crear_nube"):
            if self.boton_crear_nube.winfo_exists():
                self.boton_crear_nube.configure(state="normal")

    def _on_buscar_cambiado(self, event=None):
        """Filtra los reportes en tiempo real según el texto de búsqueda."""
        texto = self.entry_buscar.get().strip().lower()
        if texto:
            claves = [k for k in self.reportes_data if texto in k.lower()]
        else:
            claves = list(self.reportes_data.keys())
        self._renderizar_tarjetas_reportes(claves)

    def _renderizar_tarjetas_reportes(self, claves: list[str]):
        """Limpia y re-dibuja las tarjetas de reportes en la lista."""
        for widget in self.lista_reportes.winfo_children():
            widget.destroy()

        if not claves:
            ctk.CTkLabel(
                self.lista_reportes,
                text="No se encontraron reportes.",
                text_color="#475569",
                font=ctk.CTkFont(size=11),
            ).pack(pady=20)
            return

        for clave in claves:
            reporte = self.reportes_data[clave]
            self._crear_tarjeta_reporte(clave, reporte)

    def _crear_tarjeta_reporte(self, clave: str, reporte: dict):
        """Crea una tarjeta clicable para un reporte en la lista."""
        card = ctk.CTkFrame(
            self.lista_reportes,
            fg_color="#1e293b",
            corner_radius=8,
            cursor="hand2",
        )
        card.pack(fill="x", pady=3, padx=2)
        card.grid_columnconfigure(0, weight=1)

        titulo = reporte.get("titulo", "Sin título")
        restaurante_nombre = (
            reporte.get("restaurante", {}).get("nombre")
            or "Restaurante desconocido"
        )
        fecha = str(reporte.get("fecha_jornada", ""))[:10]

        ctk.CTkLabel(
            card,
            text=f"📄  {titulo}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="white",
            anchor="w",
            wraplength=320,
        ).pack(anchor="w", padx=12, pady=(8, 0))

        ctk.CTkLabel(
            card,
            text=f"{restaurante_nombre}  ·  {fecha}",
            font=ctk.CTkFont(size=10),
            text_color="#475569",
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(2, 8))

        # Hover y click
        def _hover_in(e, c=card): c.configure(fg_color="#273549")
        def _hover_out(e, c=card): c.configure(fg_color="#1e293b")
        def _click(e, r=reporte): self._on_cargar_reporte_nube(r)

        for widget in [card] + card.winfo_children():
            widget.bind("<Enter>", _hover_in)
            widget.bind("<Leave>", _hover_out)
            widget.bind("<Button-1>", _click)

    def _on_cargar_reporte_nube(self, reporte: dict):
        """Carga un reporte existente (de la nube o local) y abre el editor."""
        self.reporte_remoto_id = reporte.get("id")
        self.codigo_reporte = reporte.get("codigo", "SINCOD")
        self.titulo_reporte = reporte.get("titulo", "Reporte sin título")

        # Intentar usar el restaurante del reporte
        rest_data = reporte.get("restaurante")
        if rest_data:
            self.restaurante = rest_data
        elif self.restaurante_seleccionado:
            self.restaurante = self.restaurante_seleccionado
        else:
            self.restaurante = {"id": reporte.get("restaurante_id", "0"), "nombre": "Restaurante"}
            
        self.evidencias_nube = reporte.get("evidencias", [])

        # Crear/recuperar borrador local
        if reporte.get("es_borrador_local"):
            # Si es un borrador local, usar el borrador existente sin sobreescribirlo
            self.borrador = obtener_borrador_completo(reporte["borrador_id"])
            if self.reporte_remoto_id:
                marcar_reporte_sincronizado(self.borrador["id"], self.reporte_remoto_id)
        else:
            self.borrador = obtener_o_crear_borrador(
                self.usuario["id"], self.restaurante["id"]
            )
            # Guardamos el título real para que no quede como "Sin título" si sale sin sincronizar
            marcar_reporte_pendiente(
                self.borrador["id"],
                self.titulo_reporte,
                self.usuario["id"],
                self.restaurante["id"]
            )
            cloud_notas = reporte.get("notas_finales", "")
            if cloud_notas:
                actualizar_notas(self.borrador["id"], cloud_notas)
                self.borrador["notas_finales"] = cloud_notas
            marcar_reporte_sincronizado(self.borrador["id"], self.reporte_remoto_id)

        self._viene_de_nube = not reporte.get("es_borrador_local")

        self.frame_setup.destroy()
        self._construir_ui_editor()
        self._cargar_estado_previo()

        # Abrir panel lateral automáticamente si hay evidencias de nube para ver/descargar
        if self.evidencias_nube:
            self.after(100, self._toggle_panel_lateral)

    def _on_crear_reporte_inicial(self):
        """
        Crea un nuevo reporte (API-First).
        """
        titulo = self.entry_titulo.get().strip()
        if not titulo:
            messagebox.showwarning("Falta el título", "Escribe un nombre para el reporte.")
            return

        if not self.restaurante_seleccionado:
            messagebox.showwarning("Falta el restaurante", "Selecciona un restaurante.")
            return

        self.titulo_reporte = titulo
        self.restaurante = self.restaurante_seleccionado
        self.reporte_remoto_id = None
        self.codigo_reporte = "PENDIENTE"

        borrador_viejo = obtener_o_crear_borrador(
            self.usuario["id"], self.restaurante["id"]
        )
        eliminar_borrador_completo(borrador_viejo["id"])
        self.borrador = obtener_o_crear_borrador(
            self.usuario["id"], self.restaurante["id"]
        )
        marcar_reporte_pendiente(
            self.borrador["id"],
            titulo,
            self.usuario["id"],
            self.restaurante["id"],
        )

        self.frame_setup.destroy()
        self._construir_ui_editor()
        self._cargar_estado_previo()
        
        def _sync_init():
            try:
                dto = {
                    "usuario_id": self.usuario["id"],
                    "restaurante_id": self.restaurante["id"],
                    "titulo": self.titulo_reporte,
                    "notas_finales": "",
                    "fecha_jornada": datetime.now().strftime("%Y-%m-%d"),
                }
                resultado = crear_reporte(dto)
                if not resultado:
                    raise Exception("Fallo en API")
                
                remote_id = resultado["id"]
                codigo = resultado.get("codigo", "SINCOD")
                self.reporte_remoto_id = remote_id
                self._actualizar_codigo_ui(codigo)
                marcar_reporte_sincronizado(self.borrador["id"], remote_id)
                self.after(0, lambda: actualizar_indicador_reporte(self.label_estado_guardado, "ok"))
            except Exception:
                self.after(0, lambda: actualizar_indicador_reporte(self.label_estado_guardado, "offline"))

        self.after(0, lambda: actualizar_indicador_reporte(self.label_estado_guardado, "syncing"))
        threading.Thread(target=_sync_init, daemon=True).start()

    def _volver_al_menu_directo(self):
        self.hilo_polling_activo = False
        try:
            keyboard.remove_hotkey("ctrl+k+l")
        except Exception:
            pass
        self._ocultar_indicador_rec()
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)

    # ═══════════════════════════════════════════════════════════════════════════
    # PANTALLA 2: EDITOR
    # ═══════════════════════════════════════════════════════════════════════════

    def _construir_ui_editor(self):
        # Columnas: editor (weight=1) + panel lateral (weight=0, oculto por defecto)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # ── Frame editor ──────────────────────────────────────────────────
        self.frame_editor = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_editor.grid(row=0, column=0, sticky="nsew")
        self.frame_editor.grid_rowconfigure(0, weight=0)   # topbar
        self.frame_editor.grid_rowconfigure(1, weight=1)   # textbox
        self.frame_editor.grid_rowconfigure(2, weight=0)   # statusbar
        self.frame_editor.grid_columnconfigure(0, weight=1)

        # ── Topbar ────────────────────────────────────────────────────────
        topbar = ctk.CTkFrame(self.frame_editor, fg_color="#0a101e", height=36, corner_radius=0)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        topbar.grid_columnconfigure(0, weight=1)

        # Col 0: título del reporte (crece y cede espacio si la ventana es estrecha)
        ctk.CTkLabel(
            topbar,
            text=f"📄  {self.titulo_reporte}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, padx=(10, 4), sticky="ew")

        # Col 1: indicador de texto (ok / offline / syncing)
        _estado_inicial = "ok" if self.reporte_remoto_id else "offline"
        _texto_inicial = "☁️ En la nube" if _estado_inicial == "ok" else "💾 Guardando local"
        _color_inicial = "#4ade80" if _estado_inicial == "ok" else "#facc15"
        self.label_estado_guardado = ctk.CTkLabel(
            topbar,
            text=_texto_inicial,
            text_color=_color_inicial,
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.label_estado_guardado.grid(row=0, column=1, padx=(0, 4), sticky="e")

        # Col 2: botón zen (toggle panel)
        self.btn_toggle_panel = ctk.CTkButton(
            topbar,
            text="▶",
            width=30,
            height=24,
            fg_color="#1e293b",
            hover_color="#334155",
            font=ctk.CTkFont(size=11),
            command=self._toggle_panel_lateral,
        )
        self.btn_toggle_panel.grid(row=0, column=2, padx=(0, 8), sticky="e")

        # ── Textbox (Modo Zen) ────────────────────────────────────────────
        self.textbox_notas = ctk.CTkTextbox(
            self.frame_editor,
            font=("Consolas", 15),
            wrap="word",
            fg_color="#0f172a",
            text_color="#e2e8f0",
            border_width=0,
            corner_radius=0,
            activate_scrollbars=True,
        )
        self.textbox_notas.grid(row=1, column=0, sticky="nsew")
        self.textbox_notas.bind("<KeyRelease>", self._on_texto_cambiado)

        # ── Statusbar ────────────────────────────────────────────────────
        statusbar = ctk.CTkFrame(self.frame_editor, fg_color="#070d18", height=20, corner_radius=0)
        statusbar.grid(row=2, column=0, sticky="ew")
        statusbar.grid_propagate(False)
        restaurante_nombre = self.restaurante.get("nombre", "—") if self.restaurante else "—"
        ctk.CTkLabel(
            statusbar,
            text=f"  {self.usuario['nombre']}  ·  {restaurante_nombre}",
            font=ctk.CTkFont(size=10),
            text_color="#334155",
            anchor="w",
        ).pack(side="left", fill="y")

        # ── Panel lateral (oculto al inicio) ─────────────────────────────
        self._construir_panel_lateral()

    def _construir_panel_lateral(self):
        """Crea el panel de herramientas derecho (oculto por defecto)."""
        self.frame_side = ctk.CTkScrollableFrame(self, fg_color="#1e293b", width=248)
        self.frame_side.grid(row=0, column=1, sticky="nsew")
        self.frame_side.grid_remove()  # oculto hasta que el usuario haga clic en ▶

        # ── Código de vinculación ─────────────────────────────────────────
        caja_codigo = ctk.CTkFrame(self.frame_side, fg_color="#0284c7", corner_radius=8)
        caja_codigo.pack(pady=(14, 8), padx=14, fill="x")

        ctk.CTkLabel(
            caja_codigo,
            text="CÓDIGO DE VINCULACIÓN",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#bae6fd",
        ).pack(pady=(6, 0))

        self.label_codigo_reporte = ctk.CTkLabel(
            caja_codigo,
            text=self.codigo_reporte or "PENDIENTE",
            font=ctk.CTkFont(size=28, weight="bold", family="Consolas"),
            text_color="white",
        )
        self.label_codigo_reporte.pack(pady=(0, 6))

        # ── Grabación ─────────────────────────────────────────────────────
        self.switch_audio = ctk.CTkSwitch(
            self.frame_side, text="Grabar con audio", font=ctk.CTkFont(size=12)
        )
        self.switch_audio.pack(pady=(4, 6), padx=16, anchor="w")
        self.switch_audio.deselect()

        self.boton_grabar = ctk.CTkButton(
            self.frame_side,
            text="🔴  Grabar pantalla",
            command=self._toggle_grabacion,
            fg_color="#c0392b",
            hover_color="#922b21",
            font=ctk.CTkFont(size=12),
        )
        self.boton_grabar.pack(pady=(0, 6), padx=16, fill="x")

        self.boton_detener = ctk.CTkButton(
            self.frame_side,
            text="⏹️  Detener y Adjuntar",
            command=self._detener_grabacion,
            fg_color="#4f46e5",
            hover_color="#4338ca",
            font=ctk.CTkFont(size=12),
        )
        # Oculto inicialmente (solo visible grabando/pausado)

        ctk.CTkButton(
            self.frame_side,
            text="📎  Adjuntar archivo",
            command=self._on_adjuntar,
            fg_color="transparent",
            border_width=1,
            font=ctk.CTkFont(size=12),
        ).pack(pady=(0, 4), padx=16, fill="x")

        ctk.CTkButton(
            self.frame_side,
            text="📷  Tomar Captura",
            command=self._tomar_screenshot,
            fg_color="#0369a1",
            hover_color="#0284c7",
            font=ctk.CTkFont(size=12),
        ).pack(pady=(0, 12), padx=16, fill="x")

        # ── Lista de evidencias ───────────────────────────────────────────
        header_ev = ctk.CTkFrame(self.frame_side, fg_color="transparent")
        header_ev.pack(fill="x", padx=16)

        ctk.CTkLabel(
            header_ev,
            text="Evidencias locales",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        # Indicador de sync de evidencias (✅ / ⚠️ / ↻)
        self.label_estado_evidencias = ctk.CTkLabel(
            header_ev,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#4ade80",
        )
        self.label_estado_evidencias.pack(side="right")

        self.frame_lista_evidencias = ctk.CTkScrollableFrame(
            self.frame_side, fg_color="#0f172a", height=200
        )
        self.frame_lista_evidencias.pack(pady=6, padx=12, fill="x")

        # ── Finalizar y volver ────────────────────────────────────────────
        self.boton_finalizar = ctk.CTkButton(
            self.frame_side,
            text="✅  Enviar y Cerrar Reporte",
            command=self._on_finalizar,
            fg_color="#4f46e5",
            hover_color="#4338ca",
            height=44,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.boton_finalizar.pack(pady=(16, 6), padx=16, fill="x")

        ctk.CTkButton(
            self.frame_side,
            text="← Volver al menú",
            fg_color="transparent",
            border_width=1,
            command=self._on_volver,
        ).pack(pady=(0, 20), padx=16, fill="x")

    # ─────────────────────────────────────────────────────────────────────────
    # MODO ZEN: TOGGLE PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_panel_lateral(self):
        """Alterna el panel lateral (modo zen ↔ modo herramientas)."""
        self._panel_visible = not self._panel_visible
        if self._panel_visible:
            self.frame_side.grid()
            self.btn_toggle_panel.configure(text="◀")
        else:
            self.frame_side.grid_remove()
            self.btn_toggle_panel.configure(text="▶")

    # ═══════════════════════════════════════════════════════════════════════════
    # EDITOR: TEXTO Y AUTOGUARDADO
    # ═══════════════════════════════════════════════════════════════════════════

    def _cargar_estado_previo(self):
        if self.borrador and self.borrador.get("notas_finales"):
            self.textbox_notas.insert("1.0", self.borrador["notas_finales"])
        self._refrescar_lista_evidencias()

    def _on_texto_cambiado(self, event=None):
        if self._debounce_id is not None:
            self.after_cancel(self._debounce_id)
        actualizar_indicador_reporte(self.label_estado_guardado, "writing")
        self._debounce_id = self.after(1000, self._guardar_notas_ahora)

    def _guardar_notas_ahora(self):
        """
        API-First:
        Intenta guardar en el backend. Si falla, guarda en SQLite como Fail-safe.
        """
        texto = self.textbox_notas.get("1.0", "end").strip()

        def _sync_notas():
            try:
                if self.reporte_remoto_id:
                    res = actualizar_reporte(self.reporte_remoto_id, texto)
                    if not res:
                        raise Exception("Fallo update")
                else:
                    dto = {
                        "usuario_id": self.usuario["id"],
                        "restaurante_id": self.restaurante["id"],
                        "titulo": self.titulo_reporte,
                        "notas_finales": texto,
                        "fecha_jornada": datetime.now().strftime("%Y-%m-%d"),
                    }
                    res = crear_reporte(dto)
                    if not res:
                        raise Exception("Fallo create")
                    self.reporte_remoto_id = res["id"]
                    self._actualizar_codigo_ui(res.get("codigo", "SINCOD"))

                actualizar_notas(self.borrador["id"], texto)
                marcar_reporte_sincronizado(self.borrador["id"], self.reporte_remoto_id)
                self.after(0, lambda: actualizar_indicador_reporte(self.label_estado_guardado, "ok"))
            except Exception:
                actualizar_notas(self.borrador["id"], texto)
                marcar_notas_pendientes(self.borrador["id"])
                self.after(0, lambda: actualizar_indicador_reporte(self.label_estado_guardado, "offline"))

        threading.Thread(target=_sync_notas, daemon=True).start()
        self._debounce_id = None

    # ═══════════════════════════════════════════════════════════════════════════
    # POLLING WORKER — SINCRONIZACIÓN SILENCIOSA
    # ═══════════════════════════════════════════════════════════════════════════

    # Eliminado: POLLING WORKER y dependencias de sincronización periódica

    def _actualizar_codigo_ui(self, codigo: str):
        """Actualiza el label del código de vinculación en el hilo principal."""
        def _update():
            self.codigo_reporte = codigo
            if hasattr(self, "label_codigo_reporte") and self.label_codigo_reporte.winfo_exists():
                self.label_codigo_reporte.configure(text=codigo)
        self.after(0, _update)

    # ═══════════════════════════════════════════════════════════════════════════
    # EVIDENCIAS
    # ═══════════════════════════════════════════════════════════════════════════

    def _prefijo_nube(self) -> str:
        """Devuelve el prefijo MinIO del reporte activo."""
        codigo = self.codigo_reporte or "PENDIENTE"
        titulo = self.titulo_reporte or "sin_titulo"
        return prefijo_nube_reporte(codigo, titulo)

    def _ruta_destino_evidencia(self, nombre_archivo: str) -> str:
        """Ruta local estructurada para una evidencia de este reporte."""
        codigo = self.codigo_reporte or "PENDIENTE"
        titulo = self.titulo_reporte or "sin_titulo"
        return ruta_evidencia_reporte(codigo, titulo, nombre_archivo)

    def _refrescar_lista_evidencias(self):
        if not hasattr(self, "frame_lista_evidencias"):
            return
        for widget in self.frame_lista_evidencias.winfo_children():
            widget.destroy()

        evidencias_locales = obtener_evidencias(self.borrador["id"])
        evidencias_nube = getattr(self, "evidencias_nube", [])
        
        if not evidencias_locales and not evidencias_nube:
            ctk.CTkLabel(
                self.frame_lista_evidencias,
                text="Sin evidencias aún",
                text_color="#475569",
                font=ctk.CTkFont(size=11),
            ).pack(pady=16)
            if self.label_estado_evidencias.winfo_exists():
                self.label_estado_evidencias.configure(text="")
            return

        # 1. Evidencias en la Nube
        for i, ev in enumerate(evidencias_nube, start=1):
            url = ev.get("evidencia_url", "")
            nombre = url.split("/")[-1] if url else f"Nube_{i}"
            ev_id = ev.get("id")
            cmd = (lambda id=ev_id: self._eliminar_evidencia_nube(id)) if ev_id else None
            self._crear_tarjeta_evidencia(nombre, url, f"☁️ Nube {i}", "#64748b", delete_command=cmd)

        # 2. Evidencias Locales (pendientes de subir)
        for i, ev in enumerate(evidencias_locales, start=1):
            nombre = os.path.basename(ev["ruta_local"])
            ruta = ev["ruta_local"]
            cmd = lambda id=ev["id"]: self._eliminar_evidencia_local(id)
            self._crear_tarjeta_evidencia(nombre, ruta, f"Ev. {i}", "#38bdf8", delete_command=cmd)

    def _eliminar_evidencia_local(self, ev_id: int):
        from db.local_db import db_session
        respuesta = messagebox.askyesno("Eliminar", "¿Estás seguro de eliminar esta evidencia local?")
        if not respuesta:
            return
        
        with db_session() as conn:
            fila = conn.execute("SELECT ruta_local FROM evidencia_borrador WHERE id = ?", (ev_id,)).fetchone()
            if fila:
                try:
                    os.remove(fila["ruta_local"])
                except OSError:
                    pass
            conn.execute("DELETE FROM evidencia_borrador WHERE id = ?", (ev_id,))
            conn.commit()
            
        self._refrescar_lista_evidencias()

    def _eliminar_evidencia_nube(self, ev_id: int):
        import requests
        from api.client import API_BASE_URL
        respuesta = messagebox.askyesno("Eliminar Evidencia", "Esta acción eliminará el archivo de la nube permanentemente.\n\n¿Estás completamente seguro?")
        if respuesta:
            try:
                resp = requests.delete(f"{API_BASE_URL}/evidencias-reporte/{ev_id}", timeout=10)
                if resp.status_code in (200, 204):
                    # Actualizar cache local de la nube eliminando ese elemento
                    if hasattr(self, "evidencias_nube"):
                        self.evidencias_nube = [e for e in self.evidencias_nube if e.get("id") != ev_id]
                    self._refrescar_lista_evidencias()
                else:
                    messagebox.showerror("Error", f"No se pudo eliminar: {resp.text}")
            except Exception as e:
                messagebox.showerror("Error", f"Error de red: {e}")

    def _crear_tarjeta_evidencia(self, nombre: str, ruta_o_url: str, etiqueta: str, color_etiqueta: str, delete_command=None):
        """Tarjeta de evidencia con miniatura inline y botón de previsualización."""
        card = ctk.CTkFrame(self.frame_lista_evidencias, fg_color="#334155", corner_radius=5)
        card.pack(fill="x", pady=3, padx=2)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=8, pady=(5, 2))

        ctk.CTkLabel(
            top_row,
            text=etiqueta,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=color_etiqueta,
        ).pack(side="left")

        ctk.CTkButton(
            top_row,
            text="👁",
            width=26,
            height=18,
            fg_color="#475569",
            hover_color="#64748b",
            command=lambda r=ruta_o_url: self._previsualizar_archivo(r),
        ).pack(side="right", padx=(4, 0))

        if delete_command is not None:
            ctk.CTkButton(
                top_row,
                text="🗑️",
                width=26,
                height=18,
                fg_color="#ef4444",
                hover_color="#dc2626",
                command=delete_command,
            ).pack(side="right")

        # Fila inferior: miniatura + nombre
        body_row = ctk.CTkFrame(card, fg_color="transparent")
        body_row.pack(fill="x", padx=8, pady=(0, 5))

        # Miniatura inline para imágenes locales
        ext = os.path.splitext(nombre)[1].lower()
        es_imagen = ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp")
        if es_imagen and (ruta_o_url.startswith("http") or os.path.exists(ruta_o_url)):
            def _cargar_thumb(r=ruta_o_url, parent=body_row):
                try:
                    from PIL import Image
                    import requests
                    if r.startswith("http"):
                        img = Image.open(requests.get(r, stream=True).raw).convert("RGB")
                    else:
                        img = Image.open(r).convert("RGB")
                    img.thumbnail((54, 38))
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(54, 38))
                    lbl_thumb = ctk.CTkLabel(parent, image=ctk_img, text="", cursor="hand2")
                    lbl_thumb.image = ctk_img
                    lbl_thumb.pack(side="left", padx=(0, 6))
                    lbl_thumb.bind("<Button-1>", lambda e, ru=r: self._previsualizar_archivo(ru))
                except Exception:
                    pass  # falla silenciosa si PIL no está o el archivo es inválido
            threading.Thread(target=_cargar_thumb, daemon=True).start()
        elif ext in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
            ctk.CTkLabel(body_row, text="🎥", font=ctk.CTkFont(size=20)).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            body_row,
            text=nombre,
            font=ctk.CTkFont(size=10),
            text_color="#94a3b8",
            wraplength=130,
            justify="left",
        ).pack(side="left", anchor="w")



    def _previsualizar_archivo(self, ruta: str):
        if ruta.startswith("http"):
            import webbrowser
            webbrowser.open(ruta)
            return

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
            messagebox.showerror("Error", f"No se pudo abrir:\n{e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # CAPTURA DE PANTALLA
    # ═══════════════════════════════════════════════════════════════════════════

    def _abrir_selector_captura(self):
        """
        Abre una ventana estilo Snipping Tool: el usuario la mueve/redimensiona
        sobre el área que quiere capturar y presiona 📷 Capturar.
        """
        try:
            from PIL import ImageGrab
        except ImportError:
            messagebox.showerror("Dependencia faltante", "Instala Pillow:\n  pip install pillow")
            return

        selector = ctk.CTkToplevel(self.controlador)
        selector.title("📷  Seleccionar área a capturar")
        selector.geometry("480x320+150+150")
        selector.configure(fg_color="#0f172a")
        selector.attributes("-topmost", True)
        # Hace la ventana semi-transparente para que el usuario vea qué va a capturar
        selector.attributes("-alpha", 0.4)
        selector.resizable(True, True)

        marco = ctk.CTkFrame(selector, fg_color="transparent",
                             border_color="#4f46e5", border_width=2, corner_radius=6)
        marco.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(
            marco,
            text="Mueve y redimensiona esta ventana\nsobre el área que deseas capturar,\nluego pulsa 📷 Capturar.",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffffff",
        ).pack(expand=True)

        btn_bar = ctk.CTkFrame(selector, fg_color="#1e293b", height=52)
        btn_bar.pack(fill="x", side="bottom")
        btn_bar.pack_propagate(False)

        def _ejecutar_captura():
            selector.update_idletasks()
            x = selector.winfo_x()
            y = selector.winfo_y()
            w = selector.winfo_width()
            h = selector.winfo_height()
            selector.withdraw()
            selector.after(200, lambda: _finalizar(x, y, w, h, selector))

        def _finalizar(x, y, w, h, win):
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            except Exception as e:
                win.destroy()
                messagebox.showerror("Error de captura", str(e))
                return
            win.destroy()
            self._guardar_screenshot(img)

        ctk.CTkButton(
            btn_bar, text="📷  Capturar",
            fg_color="#4f46e5", hover_color="#4338ca",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=_ejecutar_captura,
        ).pack(side="left", padx=12, pady=10, expand=True, fill="x")

        ctk.CTkButton(
            btn_bar, text="Cancelar",
            fg_color="transparent", border_width=1, text_color="#ffffff",
            command=selector.destroy,
        ).pack(side="right", padx=12, pady=10, ipadx=10)

    def _guardar_screenshot(self, img):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre = f"screenshot_{ts}.jpg"
        ruta_destino = self._ruta_destino_evidencia(nombre)

        try:
            img.convert("RGB").save(ruta_destino, "JPEG", quality=85, optimize=True)
        except OSError as e:
            messagebox.showerror("Error al guardar", f"No se pudo guardar la captura:\n{e}")
            return

        carpeta_destino = self._prefijo_nube()
        agregar_evidencia(
            self.borrador["id"],
            ruta_destino,
            bool(self.switch_audio.get()),
            carpeta_destino=carpeta_destino,
        )
        self._refrescar_lista_evidencias()
        if self.label_estado_evidencias.winfo_exists():
            actualizar_indicador_reporte(self.label_estado_evidencias, "offline")

    def _tomar_screenshot(self):
        """Abre el selector visual de captura."""
        self._abrir_selector_captura()

    # ═══════════════════════════════════════════════════════════════════════════
    # DESCARGA MÚLTIPLE DE EVIDENCIAS
    # ═══════════════════════════════════════════════════════════════════════════

    def _on_descargar_seleccionados(self):
        """Inicia la descarga de las evidencias de nube marcadas con checkbox."""
        seleccionadas = [
            (nombre, url)
            for var, nombre, url in getattr(self, "_checkboxes_descarga", [])
            if var.get()
        ]
        if not seleccionadas:
            messagebox.showwarning("Sin selección", "Marca al menos una evidencia de nube para descargar.")
            return

        # Crear carpeta destino
        carpeta = os.path.join(os.path.expanduser("~"), "Downloads", "AuditFlow")
        os.makedirs(carpeta, exist_ok=True)

        self.boton_descargar.configure(state="disabled")
        self.lbl_progreso_descarga.configure(text=f"Preparando {len(seleccionadas)} archivos…")

        threading.Thread(
            target=self._descargar_hilo,
            args=(seleccionadas, carpeta),
            daemon=True,
        ).start()

    def _descargar_hilo(self, items: list[tuple[str, str]], carpeta: str):
        """
        Hilo secundario: descarga cada URL con requests stream=True.
        Reporta progreso al hilo principal mediante self.after(0, …).
        """
        import requests

        total = len(items)
        exitos = 0
        errores = []

        for idx, (nombre, url) in enumerate(items, start=1):
            self.after(0, self.lbl_progreso_descarga.configure,
                       {"text": f"Descargando {idx} de {total}…"})
            try:
                ruta_salida = os.path.join(carpeta, nombre)
                # Evitar sobreescritura ciega
                if os.path.exists(ruta_salida):
                    base, ext = os.path.splitext(nombre)
                    ruta_salida = os.path.join(carpeta, f"{base}_{idx}{ext}")

                with requests.get(url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(ruta_salida, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                exitos += 1
            except Exception as e:
                errores.append(f"{nombre}: {e}")

        # Notificar resultado en el hilo principal
        def _finalizar():
            self.boton_descargar.configure(state="normal")
            if errores:
                self.lbl_progreso_descarga.configure(text=f"⚠️ {exitos}/{total} descargados", text_color="#f59e0b")
                messagebox.showwarning(
                    "Descarga parcial",
                    f"Se descargaron {exitos} de {total}.\n\nErrores:\n" + "\n".join(errores),
                )
            else:
                self.lbl_progreso_descarga.configure(text=f"✅ {exitos} archivos descargados", text_color="#4ade80")
                messagebox.showinfo("Descarga completa", f"✅ {exitos} archivos guardados en:\n{carpeta}")

        self.after(0, _finalizar)

    def _on_adjuntar(self):

        """
        Permite adjuntar un archivo existente.
        Lo copia a ~/Documents/AuditFlow/Reportes/<título>/ para mantener
        la estructura de carpetas del Sprint 3.
        """
        ruta_original = filedialog.askopenfilename(
            title="Selecciona la evidencia",
            filetypes=TIPOS_EVIDENCIA,
        )
        if not ruta_original:
            return

        con_audio = bool(self.switch_audio.get())
        nombre_archivo = os.path.basename(ruta_original)
        ruta_destino = self._ruta_destino_evidencia(nombre_archivo)

        # Copiar solo si la fuente es distinta al destino
        if os.path.abspath(ruta_original) != os.path.abspath(ruta_destino):
            try:
                shutil.copy2(ruta_original, ruta_destino)
            except OSError as e:
                messagebox.showerror("Error al copiar", str(e))
                return

        carpeta_destino = self._prefijo_nube()
        agregar_evidencia(
            self.borrador["id"],
            ruta_destino,
            con_audio,
            carpeta_destino=carpeta_destino,
        )
        self._refrescar_lista_evidencias()

        # Indicar que hay evidencias sin subir
        if self.label_estado_evidencias.winfo_exists():
            actualizar_indicador_reporte(self.label_estado_evidencias, "offline")

    # ═══════════════════════════════════════════════════════════════════════════
    # GRABACIÓN DE PANTALLA
    # ═══════════════════════════════════════════════════════════════════════════

    def _al_destruir(self, event):
        self.hilo_polling_activo = False
        self._ocultar_indicador_rec()

    def _actualizar_botones_grabacion(self):
        estado = self.grabador.estado
        if estado == "detenido":
            self.boton_grabar.configure(
                text="🔴  Grabar pantalla", 
                fg_color="#c0392b", hover_color="#922b21"
            )
            self.boton_detener.pack_forget()
        elif estado == "grabando":
            self.boton_grabar.configure(
                text="⏸️  Pausar", 
                fg_color="#eab308", hover_color="#ca8a04"
            )
            self.boton_detener.pack(pady=(0, 6), padx=16, fill="x")
        elif estado == "pausado":
            self.boton_grabar.configure(
                text="▶️  Reanudar", 
                fg_color="#10b981", hover_color="#059669"
            )
            self.boton_detener.pack(pady=(0, 6), padx=16, fill="x")

    def _toggle_grabacion(self):
        if self.grabador.estado == "detenido":
            self._iniciar_grabacion()
        elif self.grabador.estado == "grabando":
            self._pausar_grabacion()
        elif self.grabador.estado == "pausado":
            self._reanudar_grabacion()

    def _iniciar_grabacion(self):
        con_audio = bool(self.switch_audio.get())
        self.grabador.iniciar(con_audio=con_audio)
        self.controlador.withdraw()
        self._mostrar_indicador_rec()
        self._actualizar_botones_grabacion()

    def _pausar_grabacion(self):
        self.grabador.pausar()
        if getattr(self, "indicador", None):
            self.lbl_dot.configure(text="⏸️", text_color="#facc15")
            self.btn_pausa_float.configure(
                text="▶️  Reanudar",
                fg_color="#10b981", hover_color="#059669",
                width=85
            )
            self.lbl_hotkeys.configure(text="En Pausa — Ctrl+K+L para reanudar", text_color="#facc15")
            if getattr(self, "_timer_id", None):
                self.after_cancel(self._timer_id)
                self._timer_id = None
        self._actualizar_botones_grabacion()

    def _reanudar_grabacion(self):
        self.grabador.reanudar()
        if getattr(self, "indicador", None):
            self.lbl_dot.configure(text="🔴", text_color="#ef4444")
            self.btn_pausa_float.configure(
                text="⏸️",
                fg_color="#eab308", hover_color="#ca8a04",
                width=35
            )
            self.lbl_hotkeys.configure(
                text="Pausar/Reanudar: Ctrl+K+L | Detener: Ctrl+F8",
                text_color="gray"
            )
            self._actualizar_crono()
        self._actualizar_botones_grabacion()

    def _detener_grabacion(self):
        ruta_final = self.grabador.detener()
        self._ocultar_indicador_rec()
        self.controlador.deiconify()
        self.controlador.lift()
        self._actualizar_botones_grabacion()

        if ruta_final and os.path.exists(ruta_final):
            con_audio = bool(self.switch_audio.get())
            carpeta_destino = self._prefijo_nube()
            agregar_evidencia(
                self.borrador["id"],
                ruta_final,
                con_audio=con_audio,
                carpeta_destino=carpeta_destino,
            )
            self._refrescar_lista_evidencias()

            if self.label_estado_evidencias.winfo_exists():
                actualizar_indicador_reporte(self.label_estado_evidencias, "offline")

    def _mostrar_indicador_rec(self):
        self._segundos_grabacion = 0
        self._timer_id = None
        
        import keyboard
        try:
            keyboard.add_hotkey("ctrl+k+l", lambda: self.after(0, self._toggle_grabacion_desde_float))
            keyboard.add_hotkey("ctrl+f8",  lambda: self.after(0, self._detener_grabacion))
        except Exception as e:
            print(f"Error al registrar hotkeys: {e}")
        
        self.indicador = ctk.CTkToplevel(self.controlador)
        self.indicador.overrideredirect(True)
        self.indicador.attributes("-topmost", True)
        self.indicador.configure(fg_color="#1e293b")
        ancho, alto = 260, 90
        x = self.indicador.winfo_screenwidth() - ancho - 40
        y = 40
        self.indicador.geometry(f"{ancho}x{alto}+{x}+{y}")
        
        self.indicador.grid_columnconfigure(1, weight=1)
        
        self.lbl_dot = ctk.CTkLabel(self.indicador, text="🔴", text_color="#ef4444", font=ctk.CTkFont(size=14))
        self.lbl_dot.grid(row=0, column=0, padx=(15, 5), pady=(15, 0))
        
        self.lbl_crono = ctk.CTkLabel(self.indicador, text="00:00", text_color="white", font=ctk.CTkFont(size=16, weight="bold", family="Consolas"))
        self.lbl_crono.grid(row=0, column=1, sticky="w", pady=(15, 0))
        
        self.btn_pausa_float = ctk.CTkButton(self.indicador, text="⏸️", width=35, height=30, fg_color="#eab308", hover_color="#ca8a04", command=self._toggle_grabacion_desde_float)
        self.btn_pausa_float.grid(row=0, column=2, padx=5, pady=(15, 0))
        
        self.btn_stop_float = ctk.CTkButton(self.indicador, text="⏹️", width=35, height=30, fg_color="#ef4444", hover_color="#dc2626", command=self._detener_grabacion)
        self.btn_stop_float.grid(row=0, column=3, padx=(0, 15), pady=(15, 0))
        
        self.lbl_hotkeys = ctk.CTkLabel(self.indicador, text="Pausar/Reanudar: Ctrl+K+L | Detener: Ctrl+F8", text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_hotkeys.grid(row=1, column=0, columnspan=4, pady=(6, 10))
        
        self._actualizar_crono()
        
    def _actualizar_crono(self):
        if getattr(self, "indicador", None) and self.grabador.estado == "grabando":
            mins, secs = divmod(self._segundos_grabacion, 60)
            self.lbl_crono.configure(text=f"{mins:02d}:{secs:02d}")
            self._segundos_grabacion += 1
            self._timer_id = self.after(1000, self._actualizar_crono)

    def _toggle_grabacion_desde_float(self):
        if self.grabador.estado == "grabando":
            self._pausar_grabacion()
        elif self.grabador.estado == "pausado":
            self._reanudar_grabacion()

    def _ocultar_indicador_rec(self):
        import keyboard
        try:
            keyboard.unhook_all()
        except Exception:
            pass

        if getattr(self, "_timer_id", None):
            self.after_cancel(self._timer_id)
            self._timer_id = None
        if getattr(self, "indicador", None) is not None:
            try:
                self.indicador.destroy()
            except Exception:
                pass
            self.indicador = None

    # ═══════════════════════════════════════════════════════════════════════════
    # FINALIZAR REPORTE
    # ═══════════════════════════════════════════════════════════════════════════

    def _intentar_finalizar_ahora(self) -> bool:
        """
        Intenta completar el cierre del reporte:
          1. Guarda las notas finales en la nube.
          2. Sube cada evidencia local a MinIO con su prefijo de carpeta correcto.
          3. Registra cada evidencia en el backend.
          4. Elimina el borrador local.

        Retorna True si todo tuvo éxito.
        """
        try:
            borrador = obtener_borrador_completo(self.borrador["id"])
            if not borrador:
                return False

            # 1. Guardar notas
            notas = borrador.get("notas_finales", "")
            if notas:
                if not actualizar_reporte(self.reporte_remoto_id, notas):
                    return False

            # 2. Subir evidencias
            evidencias = obtener_evidencias(self.borrador["id"])

            def _set_ev_estado(estado):
                if self.label_estado_evidencias.winfo_exists():
                    self.after(0, lambda: actualizar_indicador_reporte(
                        self.label_estado_evidencias, estado
                    ))

            if evidencias:
                _set_ev_estado("syncing")

            for ev in evidencias:
                prefijo = ev.get("carpeta_destino") or self._prefijo_nube()
                url_subida, _ = subir_archivo_con_destino(ev["ruta_local"], prefijo_nube=prefijo)
                if url_subida is None:
                    _set_ev_estado("offline")
                    return False

                crear_evidencia_reporte({
                    "reporte_id": self.reporte_remoto_id,
                    "evidencia_url": url_subida,
                    "con_audio": bool(ev["con_audio"]),
                    "orden_reproduccion": ev["orden_reproduccion"],
                })

                # Borrar TODAS las evidencias locales subidas
                # (todas son copias hechas por _on_adjuntar o grabaciones de AuditFlow_Temp)
                try:
                    if os.path.exists(ev["ruta_local"]):
                        os.remove(ev["ruta_local"])
                except OSError:
                    pass

            _set_ev_estado("ok")
            eliminar_borrador_completo(self.borrador["id"])
            return True

        except Exception as e:
            print(f"[intentar_finalizar] Error: {e}")
            return False

    def _on_finalizar(self):
        notas = self.textbox_notas.get("1.0", "end").strip()

        if not notas:
            messagebox.showwarning("Reporte vacío", "El reporte no tiene notas. Escribe algo primero.")
            return

        evidencias = obtener_evidencias(self.borrador["id"])
        respuesta = messagebox.askyesno(
            "Confirmar cierre",
            f"¿Enviar el reporte y subir {len(evidencias)} evidencia(s) local(es)?\n\n"
            "Las evidencias enviadas por código desde el móvil ya están vinculadas.",
        )
        if not respuesta:
            return

        self.boton_finalizar.configure(state="disabled", text="Subiendo archivos...")
        self.update()

        # Guardar notas localmente primero
        actualizar_notas(self.borrador["id"], notas)

        def _tarea():
            if not self.reporte_remoto_id:
                # Aún sin id — el polling lo creará. Encolar finalizar.
                marcar_notas_pendientes(self.borrador["id"])
                self._texto_pendiente = True
                self._finalizar_pendiente = True
                self.after(0, lambda: actualizar_indicador_reporte(
                    self.label_estado_guardado, "offline"
                ))
                self.after(0, lambda: self.boton_finalizar.configure(
                    state="normal", text="✅  Enviar y Cerrar Reporte"
                ))
                self.after(0, lambda: messagebox.showinfo(
                    "Sin conexión",
                    "Sin conexión con el servidor.\n\n"
                    "Tu reporte está guardado localmente y se enviará automáticamente\n"
                    "cuando se restaure la red.",
                ))
                return

            exito = self._intentar_finalizar_ahora()
            if exito:
                self.after(0, lambda: messagebox.showinfo("✅ Listo", "Reporte completado y enviado."))
                self.after(0, self._volver_al_menu_directo)
            else:
                self._finalizar_pendiente = True
                self.after(0, lambda: actualizar_indicador_reporte(
                    self.label_estado_guardado, "offline"
                ))
                self.after(0, lambda: self.boton_finalizar.configure(
                    state="normal", text="✅  Enviar y Cerrar Reporte"
                ))
                self.after(0, lambda: messagebox.showinfo(
                    "Sin conexión",
                    "No se pudo conectar con el servidor.\n\n"
                    "El reporte se enviará automáticamente cuando vuelva la red.",
                ))

        threading.Thread(target=_tarea, daemon=True).start()

    def _on_volver(self):
        # Asegurar que el indicador flotante de grabación se cierre al salir
        self._ocultar_indicador_rec()
        
        notas = self.textbox_notas.get("1.0", "end-1c").strip()
        evidencias = obtener_evidencias(self.borrador["id"])
        
        # 1. Si está completamente vacío (sin notas y sin evidencias locales)
        if not notas and not evidencias and not getattr(self, "evidencias_nube", []):
            eliminar_borrador_completo(self.borrador["id"])
            # Nota: Si ya se había creado en el server, quedará vacío allá. Idealmente debería eliminarse.
            self._volver_al_menu_directo()
            return

        # 2. Si tiene evidencias pero no tiene notas (faltan datos obligatorios)
        if not notas:
            respuesta = messagebox.askyesno(
                "Faltan datos",
                "Faltan datos para enviar (el reporte no tiene descripción/notas).\n\n"
                "¿Deseas cerrar de todos modos y ELIMINAR este reporte?",
                icon="warning"
            )
            if respuesta:
                eliminar_borrador_completo(self.borrador["id"])
                # Aquí si tuviéramos un endpoint para borrar, lo llamaríamos (para otra iteración).
                self._volver_al_menu_directo()
            return

        # 3. Tiene notas, procedemos a auto-guardar y auto-enviar (comportamiento inteligente)
        # Hacemos lo mismo que _on_finalizar pero de forma más silenciosa o con un mensaje de "Guardando..."
        actualizar_notas(self.borrador["id"], notas)
        self.boton_finalizar.configure(state="disabled", text="Sincronizando...")
        self.update()

        def _tarea_volver():
            if not self.reporte_remoto_id:
                # Aún sin ID en servidor, dejarlo pendiente de finalizar
                marcar_notas_pendientes(self.borrador["id"])
                self._texto_pendiente = True
                self._finalizar_pendiente = True
                self.after(0, self._volver_al_menu_directo)
                return

            exito = self._intentar_finalizar_ahora()
            if exito:
                self.after(0, self._volver_al_menu_directo)
            else:
                # Falló la subida (probablemente sin internet), se queda pendiente
                self._finalizar_pendiente = True
                self.after(0, self._volver_al_menu_directo)

        threading.Thread(target=_tarea_volver, daemon=True).start()