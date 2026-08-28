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
            cloud_notas = reporte.get("notas_finales", "")
            if cloud_notas:
                actualizar_notas(self.borrador["id"], cloud_notas)
                self.borrador["notas_finales"] = cloud_notas
            marcar_reporte_sincronizado(self.borrador["id"], self.reporte_remoto_id)

        self._viene_de_nube = not reporte.get("es_borrador_local")

        self.frame_setup.destroy()
        self._construir_ui_editor()
        self._cargar_estado_previo()
        self._registrar_hotkeys()
        self._iniciar_polling()

    def _on_crear_reporte_inicial(self):
        """
        Crea un nuevo reporte — SIEMPRE entra al editor sin importar si hay red.

        Flujo offline-first:
          1. Guarda el borrador en SQLite con pendiente=1.
          2. Entra al editor inmediatamente.
          3. El polling_worker intentará crear en la nube cada 5 s.
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

        # Limpiar cualquier borrador previo de hoy para este par usuario/restaurante
        # y crear uno nuevo limpio.
        borrador_viejo = obtener_o_crear_borrador(
            self.usuario["id"], self.restaurante["id"]
        )
        eliminar_borrador_completo(borrador_viejo["id"])
        self.borrador = obtener_o_crear_borrador(
            self.usuario["id"], self.restaurante["id"]
        )

        # Marcar como pendiente (offline-first: la nube es secundaria)
        marcar_reporte_pendiente(
            self.borrador["id"],
            titulo,
            self.usuario["id"],
            self.restaurante["id"],
        )

        # Entrar al editor inmediatamente — el polling_worker hará el trabajo de red
        self.frame_setup.destroy()
        self._construir_ui_editor()
        self._cargar_estado_previo()
        self._registrar_hotkeys()
        self._iniciar_polling()

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
            text="🔴  Grabar pantalla (Ctrl+K+L)",
            command=self._toggle_grabacion,
            fg_color="#c0392b",
            hover_color="#922b21",
            font=ctk.CTkFont(size=12),
        )
        self.boton_grabar.pack(pady=(0, 6), padx=16, fill="x")

        ctk.CTkButton(
            self.frame_side,
            text="📎  Adjuntar archivo",
            command=self._on_adjuntar,
            fg_color="transparent",
            border_width=1,
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
        Paso 1 (siempre): guarda en SQLite.
        Paso 2 (si hay red): sincroniza con el backend en hilo daemon.
        """
        texto = self.textbox_notas.get("1.0", "end").strip()
        actualizar_notas(self.borrador["id"], texto)

        if self.reporte_remoto_id:
            def _sync():
                res = actualizar_reporte(self.reporte_remoto_id, texto)
                if res:
                    marcar_reporte_sincronizado(self.borrador["id"], self.reporte_remoto_id)
                    self._texto_pendiente = False
                    self.after(0, lambda: actualizar_indicador_reporte(
                        self.label_estado_guardado, "ok"
                    ))
                else:
                    marcar_notas_pendientes(self.borrador["id"])
                    self._texto_pendiente = True
                    self.after(0, lambda: actualizar_indicador_reporte(
                        self.label_estado_guardado, "offline"
                    ))
            threading.Thread(target=_sync, daemon=True).start()
        else:
            marcar_notas_pendientes(self.borrador["id"])
            self._texto_pendiente = True
            actualizar_indicador_reporte(self.label_estado_guardado, "offline")

        self._debounce_id = None

    # ═══════════════════════════════════════════════════════════════════════════
    # POLLING WORKER — SINCRONIZACIÓN SILENCIOSA
    # ═══════════════════════════════════════════════════════════════════════════

    def _iniciar_polling(self):
        self.hilo_polling_activo = True
        threading.Thread(target=self._polling_worker, daemon=True).start()

    def _polling_worker(self):
        """
        Hilo daemon que corre cada 5 s mientras el editor esté abierto.

        Casos manejados:
          1. Sin reporte_remoto_id y pendiente → crear reporte en la nube.
          2. Con id pero texto pendiente       → actualizar notas en la nube.
          3. finalizar_pendiente               → subir evidencias y cerrar.
          4. Todo OK                           → mostrar ☁️ En la nube.
        """
        while self.hilo_polling_activo:
            try:
                borrador = obtener_borrador_completo(self.borrador["id"])
                if not borrador:
                    time.sleep(5)
                    continue

                # ── CASO 1: Reporte no existe en la nube todavía ──────────
                if not self.reporte_remoto_id and borrador.get("pendiente"):
                    dto = {
                        "usuario_id": borrador["usuario_id"],
                        "restaurante_id": borrador["restaurante_id"],
                        "titulo": borrador.get("titulo") or self.titulo_reporte or "Reporte sin título",
                        "notas_finales": borrador.get("notas_finales", ""),
                        "fecha_jornada": borrador.get("fecha_jornada", ""),
                    }
                    resultado = crear_reporte(dto)
                    if resultado:
                        remote_id = resultado["id"]
                        codigo = resultado.get("codigo", "SINCOD")
                        self.reporte_remoto_id = remote_id
                        marcar_reporte_sincronizado(self.borrador["id"], remote_id)
                        self._texto_pendiente = False
                        self._actualizar_codigo_ui(codigo)
                        self.after(0, lambda: actualizar_indicador_reporte(
                            self.label_estado_guardado, "ok"
                        ))
                    else:
                        self.after(0, lambda: actualizar_indicador_reporte(
                            self.label_estado_guardado, "offline"
                        ))

                # ── CASO 2: Hay id pero texto pendiente ───────────────────
                elif self.reporte_remoto_id and (
                    self._texto_pendiente or borrador.get("pendiente")
                ):
                    self.after(0, lambda: actualizar_indicador_reporte(
                        self.label_estado_guardado, "syncing"
                    ))
                    notas = borrador.get("notas_finales", "")
                    res = actualizar_reporte(self.reporte_remoto_id, notas)
                    if res:
                        marcar_reporte_sincronizado(self.borrador["id"], self.reporte_remoto_id)
                        self._texto_pendiente = False
                        self.after(0, lambda: actualizar_indicador_reporte(
                            self.label_estado_guardado, "ok"
                        ))
                    else:
                        self.after(0, lambda: actualizar_indicador_reporte(
                            self.label_estado_guardado, "offline"
                        ))

                # ── CASO 3: Finalizar quedó pendiente ─────────────────────
                elif self._finalizar_pendiente and self.reporte_remoto_id:
                    self.after(0, lambda: actualizar_indicador_reporte(
                        self.label_estado_guardado, "syncing"
                    ))
                    exito = self._intentar_finalizar_ahora()
                    if exito:
                        self._finalizar_pendiente = False
                        self.after(0, self._volver_al_menu_directo)

                # ── CASO 4: Todo sincronizado ─────────────────────────────
                elif self.reporte_remoto_id and not self._texto_pendiente:
                    self.after(0, lambda: actualizar_indicador_reporte(
                        self.label_estado_guardado, "ok"
                    ))

            except Exception as e:
                print(f"[reportes_polling] Error: {e}")

            time.sleep(5)

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
        titulo = self.titulo_reporte or "sin_titulo"
        return prefijo_nube_reporte(titulo)

    def _ruta_destino_evidencia(self, nombre_archivo: str) -> str:
        """Ruta local estructurada para una evidencia de este reporte."""
        titulo = self.titulo_reporte or "sin_titulo"
        return ruta_evidencia_reporte(titulo, nombre_archivo)

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

        # 1. Mostrar Evidencias en la Nube
        for i, ev in enumerate(evidencias_nube, start=1):
            url = ev.get("evidencia_url", "")
            nombre = url.split("/")[-1] if url else f"Nube_{i}"
            self._crear_tarjeta_evidencia(nombre, url, f"☁️ Nube {i}", "#64748b")

        # 2. Mostrar Evidencias Locales (pendientes de subir)
        for i, ev in enumerate(evidencias_locales, start=1):
            nombre = os.path.basename(ev["ruta_local"])
            ruta = ev["ruta_local"]
            self._crear_tarjeta_evidencia(nombre, ruta, f"Ev. {i}", "#38bdf8")

    def _crear_tarjeta_evidencia(self, nombre: str, ruta_o_url: str, etiqueta: str, color_etiqueta: str):
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
        ).pack(side="right")

        ctk.CTkLabel(
            card,
            text=nombre,
            font=ctk.CTkFont(size=10),
            text_color="#94a3b8",
            wraplength=180,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 5))

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

    def _registrar_hotkeys(self):
        keyboard.add_hotkey("ctrl+k+l", self._toggle_grabacion)

    def _al_destruir(self, event):
        self.hilo_polling_activo = False
        try:
            keyboard.remove_hotkey("ctrl+k+l")
        except Exception:
            pass
        self._ocultar_indicador_rec()

    def _toggle_grabacion(self):
        if self.grabando:
            self._detener_grabacion()
        else:
            self._iniciar_grabacion()

    def _iniciar_grabacion(self):
        con_audio = bool(self.switch_audio.get())
        # El grabador siempre graba en AuditFlow_Temp (sin cambio en recorder.py).
        # La ruta final se obtiene al detener — en ese momento se registra en SQLite
        # con la carpeta de destino correcta para la subida a MinIO.
        self.grabador.iniciar(con_audio=con_audio)
        self.grabando = True
        self.controlador.withdraw()
        self._mostrar_indicador_rec()

    def _detener_grabacion(self):
        ruta_final = self.grabador.detener()
        self.grabando = False
        self._ocultar_indicador_rec()
        self.controlador.deiconify()
        self.controlador.lift()

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
        self.indicador = ctk.CTkToplevel(self.controlador)
        self.indicador.overrideredirect(True)
        self.indicador.attributes("-topmost", True)
        ancho, alto = 200, 40
        x = self.indicador.winfo_screenwidth() - ancho - 20
        self.indicador.geometry(f"{ancho}x{alto}+{x}+20")
        ctk.CTkLabel(
            self.indicador,
            text="🔴  Grabando (Ctrl+K+L)",
            fg_color="#1a1a1a",
            text_color="white",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(fill="both", expand=True)

    def _ocultar_indicador_rec(self):
        if self.indicador is not None:
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
        texto = self.textbox_notas.get("1.0", "end-1c").strip()

        if texto:
            actualizar_notas(
                self.borrador["id"],
                texto,
                marcar_pendiente=bool(not self.reporte_remoto_id or self._texto_pendiente),
            )
            # Sincronización de cortesía al salir
            if self.reporte_remoto_id:
                try:
                    actualizar_reporte(self.reporte_remoto_id, texto)
                except Exception:
                    pass

        respuesta = messagebox.askyesno(
            "Salir al menú",
            "¿Volver al menú principal?\n\n"
            "Tu progreso está guardado localmente y se sincronizará automáticamente.",
        )
        if respuesta:
            self._volver_al_menu_directo()