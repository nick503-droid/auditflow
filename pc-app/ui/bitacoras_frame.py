from ui.visual_widgets import IconButton, IconLabel
"""
BitacorasFrame — Módulo de bitácoras para AuditFlow PC App.

Refinamientos implementados:
  1. Tarjeta de UNA sola línea horizontal (todos los campos en un renglón).
  2. Carga inmediata al abrir la pantalla (no espera el primer ciclo de polling).
  3. Previsualización de evidencia (miniaturas de imagen / chips de video).
  4. Código de 6 chars de solo lectura en el panel de evidencia.
  5. Múltiples evidencias por bitácora (backend ahora admite N).
  6. Debounce de 1.5 s en el autoguardado.
  7. Persistencia offline en SQLite — escribe local primero, sube después.
  8. Vigilante tomado del selector global superior (no por fila individual).
  9. Urgencia como OptionMenu con 4 niveles; tarjeta cambia de color.
 10. Descripción responsiva con CTkTextbox que crece verticalmente.
 11. Botón "Cerrar bitácora del día" con validación de filas completas.
 12. Fetch fresco de evidencias al abrir el panel lateral.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime
import keyboard
import os
import shutil
import threading
import time
import webbrowser
import uuid

from api.client import (
    obtener_bitacoras_por_fecha,
    obtener_bitacoras_delta,
    adjuntar_evidencia_por_codigo,
    obtener_evidencias_bitacora,
    subir_archivo_con_destino,
    crear_bitacora,
    actualizar_bitacora,
    obtener_restaurantes,
    obtener_usuarios,
    cerrar_bitacora_dia,
)
from core.recorder import GrabadorPantalla
from core.sync_helper import actualizar_indicador_sync
from core.thumbnail_service import MiniaturasUI
from core.bitacora_order import clave_orden_bitacora, cursor_bitacoras_servidor
from ui.evidence_list import ListaEvidencias, firma_evidencias, ordenar_evidencias
from ui.auto_height_textbox import AutoHeightTextbox
from db.local_db import (
    inicializar_db,
    guardar_bitacora_local,
    obtener_bitacora_local,
    marcar_bitacora_sincronizada,
    obtener_bitacoras_pendientes,
    prefijo_nube_bitacora,
    ruta_evidencia_bitacora,
    agregar_evidencia_bitacora_pendiente,
    obtener_evidencias_bitacora_pendientes,
    actualizar_url_evidencia_bitacora,
    marcar_evidencia_bitacora_vinculada,
    eliminar_evidencia_bitacora_pendiente,
)

from ui.theme import (
    APP_BACKGROUND, SURFACE, SURFACE_SECONDARY, BORDER, BORDER_FOCUS,
    PRIMARY, PRIMARY_HOVER, SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    RADIUS_PANEL, RADIUS_BUTTON, get_font, STATUS, INVERTED_BG
)
from ui.icons import get_icon

# ─── SISTEMA DE DISEÑO (Fase 5) ───────────────────────────────────────────────
BG_COLOR = APP_BACKGROUND
CARD_COLOR = SURFACE
CARD_HOVER = SURFACE_SECONDARY
TEXT_MAIN = TEXT_PRIMARY
TEXT_SEC = TEXT_SECONDARY
ACCENT_COLOR = PRIMARY
ACCENT_HOVER = PRIMARY_HOVER
SUCCESS_COLOR = STATUS["success"]["text"]
WARN_COLOR = STATUS["warning"]["text"]
DANGER_COLOR = STATUS["error"]["text"]
DANGER_HOVER = STATUS["error"]["hover"]

URGENCIA_COLORES = {
    "comentar": {"bg": STATUS["info"]["bg"],    "fg": STATUS["info"]["text"],    "tarjeta_par": SURFACE, "tarjeta_impar": SURFACE_SECONDARY},
    "leve":     {"bg": STATUS["success"]["bg"], "fg": STATUS["success"]["text"], "tarjeta_par": SURFACE, "tarjeta_impar": SURFACE_SECONDARY},
    "medio":    {"bg": STATUS["warning"]["bg"], "fg": STATUS["warning"]["text"], "tarjeta_par": SURFACE, "tarjeta_impar": SURFACE_SECONDARY},
    "grave":    {"bg": STATUS["error"]["bg"],   "fg": STATUS["error"]["text"],   "tarjeta_par": SURFACE, "tarjeta_impar": SURFACE_SECONDARY},
}
URGENCIA_OPCIONES = ["Comentar", "Leve", "Medio", "Grave"]

# Mapeo nombre display → valor backend (y viceversa)
URGENCIA_DISPLAY_A_VALOR = {
    "Comentar": "comentar",
    "Leve":     "leve",
    "Medio":    "medio",
    "Grave":    "grave",
}
URGENCIA_VALOR_A_DISPLAY = {v: k for k, v in URGENCIA_DISPLAY_A_VALOR.items()}

# Mapeo de valores legacy del backend (antes del remapeo SQL)
URGENCIA_LEGACY = {
    "low":      "leve",
    "medium":   "medio",
    "critical": "grave",
}

COLOR_CODIGO_BG        = BG_COLOR
COLOR_CODIGO_FG        = TEXT_SEC
COLOR_BOTON_EV_OK      = SUCCESS_COLOR
COLOR_BOTON_EV_ADD     = ACCENT_COLOR
COLOR_SYNC_OK          = SUCCESS_COLOR
COLOR_SYNC_OFFLINE     = WARN_COLOR
COLOR_SYNC_WORKING     = STATUS["info"]["text"]

ANCHO_REST     = 160
ANCHO_HORA     = 70
ANCHO_COD      = 80
ANCHO_EV_BTN   = 110
ANCHO_URG_MENU = 110   # OptionMenu de urgencia

DEBOUNCE_MS    = 1500
ALTURA_DESC    = 28    # altura mínima del CTkTextbox de descripción


class BitacorasFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, fecha=None, **kwargs):
        super().__init__(master, fg_color=BG_COLOR, **kwargs)
        self.controlador = controlador
        self.usuario_activo = usuario
        self.fecha_actual = fecha if fecha else datetime.now().strftime("%Y-%m-%d")

        self.lock = threading.Lock()
        self.filas_editando = set()
        self.campos_editando = {}
        # Evita que el guardado por debounce y el sincronizador de pendientes
        # creen a la vez la misma bitácora local.
        self._creaciones_en_curso = set()
        # --- DETENCIÓN LIMPIA DE HILOS ---
        # threading.Event es la herramienta correcta para señalar a un hilo
        # que debe detenerse. A diferencia de un bool, wait() libera el GIL
        # mientras duerme y responde al set() de inmediato (sin esperar 5 s).
        self.stop_event = threading.Event()
        self._hilo_polling: threading.Thread | None = None
        self.ultimo_hash_bd = None
        # Cursor de updated_at del servidor, nunca del reloj local.
        # None = todavía no se recibió ningún registro con metadatos de sync.
        self.timestamp_ultimo_sync: int | None = None

        # Evidencia
        self.evidencias_locales_panel = []
        self.ruta_evidencia_actual = None
        self.grabador = GrabadorPantalla()
        self.grabando = False
        self._grabacion_con_audio = False
        self.indicador = None
        self._codigo_panel_activo = ""   # código de la bitácora en el panel lateral
        self._bitacora_local_id_panel = None
        self._b_id_panel = ""
        self._lock_sync_evidencias = threading.Lock()
        self._cerrado = False
        self._miniaturas = MiniaturasUI(self)
        self._lista_ev_tarjetas = None
        self._lista_local_tarjetas = None
        self._panel_ev_visible = False
        self._codigo_mostrado = None
        self._firma_panel_evidencias = None

        # Catálogos
        self.mapa_restaurantes = {}
        self.mapa_usuarios = {}
        self._cargar_catalogos()

        # Lista de dicts con datos + refs a widgets de cada fila
        self.filas: list[dict] = []

        # Asegurar que la tabla offline existe
        inicializar_db()

        # Layout principal
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)   # encabezado de columnas
        self.grid_rowconfigure(2, weight=1)   # área de filas
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        self._construir_top_bar()
        self._construir_encabezado_columnas()
        self._construir_area_filas()
        self._construir_panel_evidencia()
        self._registrar_hotkeys()

        # Carga inmediata + polling
        self._carga_inicial()
        self._iniciar_polling()

    # ─── Catálogos ────────────────────────────────────────────────────────────

    def _cargar_catalogos(self):
        try:
            rests = obtener_restaurantes()
            self.mapa_restaurantes = {r["nombre"]: r["id"] for r in rests}
        except Exception:
            print("Error cargando restaurantes en bitácoras")

        if not self.mapa_restaurantes:
            messagebox.showwarning(
                "Sin restaurantes",
                "No se pudo cargar la lista de restaurantes desde el servidor.\n\n"
                "La columna 'Restaurante' quedará vacía hasta que esto se resuelva.\n"
                "Revisa que el backend esté corriendo y accesible (API_BASE_URL).",
            )

        try:
            usrs = obtener_usuarios()
            self.mapa_usuarios = {u["nombre"]: u["id"] for u in usrs}
        except Exception:
            print("Error cargando usuarios en bitácoras")

    # ─── Top bar ─────────────────────────────────────────────────────────────

    def _construir_top_bar(self):
        self.top_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 4))

        IconLabel(
            self.top_bar,
            text=f"📋  Bitácoras: {self.fecha_actual}",
            font=get_font(size=18, weight="bold"),
        ).pack(side="left", padx=10)

        IconLabel(
            self.top_bar, text="Vigilante a cargo:", font=get_font(size=12)
        ).pack(side="left", padx=(20, 5))

        # Texto estático ahora que el login es centralizado
        IconLabel(
            self.top_bar, text=self.usuario_activo["nombre"], font=get_font(size=12, weight="bold")
        ).pack(side="left", padx=5)

        # Indicador de conexión
        self.label_sync = IconLabel(
            self.top_bar, text="⬤ Conectado",
            text_color=COLOR_SYNC_OK, font=get_font(size=11),
        )
        self.label_sync.pack(side="left", padx=(16, 0))

        IconButton(
            self.top_bar, text="\u2190 Volver", width=80,
            fg_color="transparent", hover_color=SURFACE_SECONDARY,
            border_width=1, border_color=BORDER, text_color=TEXT_PRIMARY,
            font=get_font(size=12),
            command=self._on_volver,
        ).pack(side="right", padx=10)

        IconButton(
            self.top_bar, text="+ Nueva fila", width=110,
            fg_color=PRIMARY, hover_color=PRIMARY_HOVER,
            text_color="#FFFFFF", font=get_font(size=12, weight="bold"),
            command=self._agregar_fila_vacia,
        ).pack(side="right", padx=5)

        IconButton(
            self.top_bar, text="\U0001F512 Cerrar día", width=120,
            fg_color=STATUS["error"]["solid"], hover_color=DANGER_HOVER,
            text_color="#FFFFFF", font=get_font(size=12, weight="bold"),
            command=self._on_cerrar_bitacora_dia,
        ).pack(side="right", padx=5)

    def _actualizar_indicador_sync(self, estado: str, pendientes: int = 0):
        """Delega a sync_helper para mantener la paleta centralizada."""
        actualizar_indicador_sync(self.label_sync, estado, pendientes)

    # ─── Encabezado de columnas ───────────────────────────────────────────────

    def _construir_encabezado_columnas(self):
        """Fila fija de etiquetas que sirve de cabecera visual.
        Orden: Restaurante | Hora | Descripción | Código | Evidencia | Urgencia
        """
        hdr = ctk.CTkFrame(self, fg_color=SECONDARY, corner_radius=0)
        hdr.grid(row=1, column=0, sticky="ew", padx=12, pady=0)

        # La columna de descripción es expansible → se llena con grid para
        # mantener alineación exacta con las tarjetas.
        hdr.grid_columnconfigure(2, weight=1)

        headers = [
            ("Restaurante", ANCHO_REST,     False),
            ("Hora",        ANCHO_HORA,     False),
            ("Descripción", 0,              True),   # expansible
            ("Código",      ANCHO_COD,      False),
            ("Evidencia",   ANCHO_EV_BTN,   False),
            ("Urgencia",    ANCHO_URG_MENU, False),
        ]
        for col_idx, (texto, ancho, expandir) in enumerate(headers):
            kw = {} if expandir else {"width": ancho}
            lbl = IconLabel(
                hdr, text=texto,
                font=get_font(size=12, weight="bold"),
                text_color="#FFFFFF", **kw,
            )
            sticky = "ew" if expandir else "w"
            lbl.grid(row=0, column=col_idx, padx=4, pady=4, sticky=sticky)

    # ─── Área de filas (scroll) ───────────────────────────────────────────────

    def _construir_area_filas(self):
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", label_text="")
        self.scroll_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(2, 10))
        self.scroll_frame.grid_columnconfigure(0, weight=1)

    # ─── Tarjeta de UNA línea ─────────────────────────────────────────────────

    def _construir_tarjeta(self, idx: int):
        """
        Construye (o reconstruye) la tarjeta horizontal para la fila `idx`.

        Columnas (sin Vigilante por fila):
          col 0 — Restaurante (OptionMenu, ANCHO_REST)
          col 1 — Hora        (Entry, ANCHO_HORA)
          col 2 — Descripción (CTkTextbox, weight=1, expansible)
          col 3 — Código      (badge solo-lectura, ANCHO_COD)
          col 4 — Evidencia   (botón, ANCHO_EV_BTN)
          col 5 — Urgencia    (OptionMenu, ANCHO_URG_MENU)
        """
        fila = self.filas[idx]

        old_card = fila.get("_card_frame")
        if old_card and old_card.winfo_exists():
            old_card.destroy()

        # Color de fondo según urgencia
        urgencia = fila.get("urgencia", "leve")
        urgencia = URGENCIA_LEGACY.get(urgencia, urgencia)   # normalizar legacy
        urg_info = URGENCIA_COLORES.get(urgencia, URGENCIA_COLORES["leve"])
        
        bg_color = urg_info["tarjeta_par"] if idx % 2 == 0 else urg_info["tarjeta_impar"]

        card = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=bg_color,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        card.grid(row=idx, column=0, sticky="ew", pady=1, padx=0)
        card.grid_columnconfigure(2, weight=1)   # col 2 = descripción, se expande
        fila["_card_frame"] = card

        # ── Col 0 — Restaurante ───────────────────────────────────────────────
        nombres_rests = list(self.mapa_restaurantes.keys()) if self.mapa_restaurantes else ["—"]
        rest_val = fila.get("restaurante", "")
        if rest_val not in nombres_rests:
            nombres_rests = [""] + nombres_rests

        om_rest = ctk.CTkOptionMenu(
            card,
            values=nombres_rests,
            width=ANCHO_REST, height=28,
            command=lambda v, i=idx: self._on_campo_inmediato(i, "restaurante", v),
            font=get_font(size=11),
            dynamic_resizing=False,
        )
        om_rest.set(rest_val if rest_val else "— Restaurante —")
        om_rest.grid(row=0, column=0, padx=(4, 2), pady=3)
        om_rest.bind(
            "<Return>",
            lambda event, w=om_rest: self._abrir_selector_restaurante(event, w),
        )
        om_rest.bind(
            "<Down>",
            lambda event, w=om_rest: self._abrir_selector_restaurante(event, w),
        )
        om_rest.bind("<FocusIn>", lambda e=None, i=idx: self._marcar_editando(i, True, "restaurante"))
        om_rest.bind("<FocusOut>", lambda e=None, i=idx: self._marcar_editando(i, False, "restaurante"))

        # ── Col 1 — Hora (texto libre) ────────────────────────────────────────
        hora_entry = ctk.CTkEntry(card, placeholder_text="HH:MM", width=ANCHO_HORA, height=28,
                                  font=get_font(size=11, weight="bold"), text_color=STATUS["info"]["text"])
        hora_val = fila.get("hora", "")
        if hora_val:
            hora_entry.insert(0, hora_val)
        hora_entry.grid(row=0, column=1, padx=2, pady=3)
        hora_entry.bind("<KeyRelease>", lambda e=None, i=idx, w=hora_entry: self._on_keyrelease(i, "hora", w))
        hora_entry.bind("<FocusIn>",  lambda e=None, i=idx: self._marcar_editando(i, True, "hora"))
        hora_entry.bind("<FocusOut>", lambda e=None, i=idx: self._marcar_editando(i, False, "hora"))
        hora_entry.bind(
            "<Return>",
            lambda event, i=idx, w=hora_entry: self._on_enter_hora(event, i, w),
        )

        # ── Col 2 — Descripción (CTkTextbox responsivo) ───────────────────────
        desc_val = fila.get("descripcion", "")

        desc_box = AutoHeightTextbox(
            card, min_height=ALTURA_DESC, font=get_font(size=13),
            fg_color=BG_COLOR, border_width=1, border_color=BORDER, wrap="word"
        )
        if desc_val:
            desc_box.insert("1.0", desc_val)
        desc_box.grid(row=0, column=2, padx=2, pady=3, sticky="ew")
        desc_box.bind("<KeyRelease>", lambda e=None, i=idx, w=desc_box: self._on_keyrelease_textbox(i, w))
        desc_box.bind(
            "<Return>",
            lambda event, i=idx, w=desc_box: self._on_enter_descripcion(event, i, w),
        )
        desc_box.bind(
            "<Shift-Return>",
            lambda event, i=idx, w=desc_box: self._on_shift_enter_descripcion(i, w),
        )
        desc_box.bind("<FocusIn>",   lambda e=None, i=idx: self._marcar_editando(i, True, "descripcion"))
        desc_box.bind("<FocusOut>",  lambda e=None, i=idx: self._marcar_editando(i, False, "descripcion"))
        # Ajustar altura inicial al contenido ya cargado
        self._ajustar_altura_textbox(desc_box)

        # ── Col 3 — Badge de código (solo lectura) ────────────────────────────
        codigo = fila.get("codigo", "")
        if codigo:
            cod_btn = IconButton(
                card,
                text=codigo,
                width=ANCHO_COD, height=28,
                fg_color=STATUS["info"]["bg"],
                text_color=STATUS["info"]["text"],
                hover_color=SURFACE_SECONDARY,
                font=get_font(family="Consolas", size=12, weight="bold"),
                corner_radius=4,
                command=lambda c=codigo: self._copiar_codigo(c),
            )
        else:
            cod_btn = IconLabel(
                card, text="—", width=ANCHO_COD, height=28,
                text_color=TEXT_MUTED, font=get_font(size=11),
            )
        cod_btn.grid(row=0, column=3, padx=2, pady=3)

        # ── Col 4 — Botón de evidencia ────────────────────────────────────────
        evidencias = fila.get("evidencias", [])
        cantidad_local = self._cantidad_evidencias_locales(fila)
        cantidad_total = len(evidencias) + cantidad_local
        tiene_ev = cantidad_total > 0 or fila.get("evidencia") == "Sí"
        if tiene_ev:
            n = cantidad_total or 1
            ev_text  = f" {n} ev."
            ev_icon  = get_icon("check", size=(16, 16), color=STATUS["success"]["text"])
            ev_color = STATUS["success"]["bg"]
            ev_text_color = STATUS["success"]["text"]
            ev_hover = STATUS["success"]["hover_bg"]
        else:
            ev_text  = " Adjuntar"
            ev_icon  = get_icon("paperclip", size=(16, 16), color=STATUS["info"]["text"])
            ev_color = STATUS["info"]["bg"]
            ev_text_color = STATUS["info"]["text"]
            ev_hover = STATUS["info"]["hover_bg"]

        ev_btn = IconButton(
            card,
            text=ev_text,
            image=ev_icon,
            width=ANCHO_EV_BTN, height=28,
            fg_color=ev_color, hover_color=ev_hover,
            text_color=ev_text_color,
            font=get_font(size=11),
            command=lambda i=idx: self._on_boton_evidencia(i),
        )
        ev_btn.grid(row=0, column=4, padx=2, pady=3)
        ev_btn._estado_evidencias = (tiene_ev, cantidad_total or (1 if tiene_ev else 0))

        # ── Col 5 — Urgencia (OptionMenu, al final) ───────────────────────────
        urg_display = URGENCIA_VALOR_A_DISPLAY.get(urgencia, "Leve")

        urg_menu = ctk.CTkOptionMenu(
            card,
            values=URGENCIA_OPCIONES,
            width=ANCHO_URG_MENU, height=28,
            font=get_font(size=11),
            dynamic_resizing=False,
            fg_color=urg_info["bg"],
            text_color=urg_info["fg"],
            button_color=urg_info["bg"],
            button_hover_color=urg_info["bg"],
            command=lambda v, i=idx: self._on_cambiar_urgencia(i, v),
        )
        urg_menu.set(urg_display)
        urg_menu.grid(row=0, column=5, padx=(2, 6), pady=3)

        # ── Col 6 — Eliminar ──────────────────────────────────────────────────
        btn_eliminar = IconButton(
            card, text="🗑️", width=32, height=28,
            fg_color="transparent", hover_color=STATUS["error"]["bg"],
            text_color=STATUS["error"]["text"], font=get_font(size=14),
            command=lambda i=idx: self._on_eliminar_bitacora(i)
        )
        btn_eliminar.grid(row=0, column=6, padx=(0, 6), pady=3)

        fila["_widgets"] = {
            "restaurante": om_rest,
            "hora":        hora_entry,
            "descripcion": desc_box,
            "urgencia":    urg_menu,
            "codigo":      cod_btn,
            "evidencia":   ev_btn,
        }

    def _reconstruir_tarjeta(self, idx: int):
        self._construir_tarjeta(idx)

    def _cantidad_evidencias_locales(self, fila: dict) -> int:
        return len(obtener_evidencias_bitacora_pendientes(
            bitacora_local_id=fila.get("local_id"),
            b_id=fila.get("b_id") or None,
        ))

    def _actualizar_boton_evidencia(self, idx: int):
        """Refresca únicamente el chip de evidencias, sin perder el foco de la fila."""
        if idx < 0 or idx >= len(self.filas):
            return

        fila = self.filas[idx]
        ev_btn = fila.get("_widgets", {}).get("evidencia")
        if not ev_btn or not ev_btn.winfo_exists():
            return

        evidencias = fila.get("evidencias", [])
        cantidad_local = self._cantidad_evidencias_locales(fila)
        cantidad_total = len(evidencias) + cantidad_local
        tiene_ev = cantidad_total > 0 or fila.get("evidencia") == "Sí"
        estado = (tiene_ev, cantidad_total or (1 if tiene_ev else 0))
        if getattr(ev_btn, "_estado_evidencias", None) == estado:
            return
        ev_btn._estado_evidencias = estado
        if tiene_ev:
            cantidad = cantidad_total or 1
            ev_btn.configure(
                text=f" {cantidad} ev.",
                image=get_icon("check", size=(16, 16), color=STATUS["success"]["text"]),
                fg_color=STATUS["success"]["bg"],
                hover_color=STATUS["success"]["hover_bg"],
                text_color=STATUS["success"]["text"],
            )
        else:
            ev_btn.configure(
                text=" Adjuntar",
                image=get_icon("paperclip", size=(16, 16), color=STATUS["info"]["text"]),
                fg_color=STATUS["info"]["bg"],
                hover_color=STATUS["info"]["hover_bg"],
                text_color=STATUS["info"]["text"],
            )

    def _actualizar_evidencias_fila(self, codigo: str, evidencias: list, *, refrescar_panel=True):
        """Inyecta las evidencias recibidas del servidor y actualiza su chip in-place."""
        for idx, fila in enumerate(self.filas):
            if fila.get("codigo") != codigo:
                continue

            fila["evidencias"] = evidencias or []
            fila["evidencia"] = "Sí" if fila["evidencias"] else ""
            self._actualizar_boton_evidencia(idx)

            if refrescar_panel and self._codigo_panel_activo == codigo:
                self._mostrar_panel_evidencia(codigo, fila["evidencias"])
            return

    # ─── Helpers de descripción responsiva ───────────────────────────────────

    def _on_eliminar_bitacora(self, idx: int):
        from tkinter import messagebox
        if not messagebox.askyesno("Confirmar", "¿Seguro que deseas eliminar este registro?"):
            return
            
        fila = self.filas[idx]
        b_id = fila.get("b_id")
        
        # Eliminar del backend
        if b_id:
            from api.client import eliminar_registro
            res = eliminar_registro(f"bitacoras/{b_id}")
            if not res:
                messagebox.showerror("Error", "No se pudo eliminar el registro del servidor.")
                return
                
        # Eliminar localmente
        import db.local_db as local_db
        try:
            local_db.eliminar_bitacora(b_id or fila.get("local_id"))
        except Exception:
            pass
        
        # Eliminar visualmente y actualizar lista
        old_card = fila.get("_card_frame")
        if old_card:
            old_card.destroy()
            
        self.filas.pop(idx)
        
        # Reconstruir las filas siguientes para actualizar sus índices
        for i in range(idx, len(self.filas)):
            self._reconstruir_tarjeta(i)
        self._ordenar_tarjetas_por_creacion()

    def _ajustar_altura_textbox(self, widget: ctk.CTkTextbox):
        """Coalescer cambios de texto/ancho; medir sin reentrar al mainloop."""
        if widget.winfo_exists():
            widget.programar_ajuste()

    def _on_keyrelease_textbox(self, idx: int, widget: ctk.CTkTextbox):
        """Callback de tecla para CTkTextbox: guarda texto y ajusta altura."""
        try:
            texto = widget.get("1.0", "end-1c").strip()
            self.filas[idx]["descripcion"] = texto
            self._marcar_campo_pendiente(idx, "descripcion")
            self._ajustar_altura_textbox(widget)
            self._programar_guardado(idx)
        except Exception:
            pass

    # ─── Agregar fila vacía ───────────────────────────────────────────────────

    def _agregar_fila_vacia(self, restaurante: str = "", enfocar_restaurante: bool = False):
        vigilante_actual = self.usuario_activo["nombre"]
        nueva_fila = {
            "b_id": "",
            "local_id": None,
            "codigo": "",
            "hora": "",
            "restaurante": restaurante,
            "vigilante": vigilante_actual,
            "descripcion": "",
            "urgencia": "leve",
            "evidencias": [],
            "evidencia": "",   # campo legacy para compatibilidad con el reconciliador
            "_debounce_id": None,
            "_creando_en_nube": False,
            "client_id": str(uuid.uuid4()), # UUID único para idempotencia
        }
        self.filas.append(nueva_fila)
        idx = len(self.filas) - 1
        self._construir_tarjeta(idx)
        self._ordenar_tarjetas_por_creacion()
        self.after(50, lambda: self.scroll_frame._parent_canvas.yview_moveto(1.0))
        if enfocar_restaurante:
            self.after_idle(lambda i=idx: self._enfocar_selector_restaurante(i, abrir=True))
        return idx

    # ─── Callbacks de campo ───────────────────────────────────────────────────

    def _marcar_editando(self, idx: int, estado: bool, campo: str | None = None):
        with self.lock:
            if estado:
                self.filas_editando.add(idx)
                if campo:
                    self.campos_editando.setdefault(idx, set()).add(campo)
            else:
                campos = self.campos_editando.get(idx, set())
                if campo:
                    campos.discard(campo)
                if not campos:
                    self.campos_editando.pop(idx, None)
                    self.filas_editando.discard(idx)

    def _marcar_campo_pendiente(self, idx: int, campo: str):
        if 0 <= idx < len(self.filas):
            self.filas[idx].setdefault("_campos_pendientes", set()).add(campo)

    def _on_campo_inmediato(self, idx: int, campo: str, valor: str):
        """Para OptionMenus (no tienen KeyRelease) — cambio registrado de inmediato."""
        if idx >= len(self.filas):
            return
        self.filas[idx][campo] = valor
        self._marcar_campo_pendiente(idx, campo)
        self._programar_guardado(idx)
        if campo == "restaurante":
            self.filas[idx]["restaurante_id"] = self.mapa_restaurantes.get(valor)
            widgets = self.filas[idx].get("_widgets", {})
            hora_entry = widgets.get("hora")
            if hora_entry and hora_entry.winfo_exists() and valor in self.mapa_restaurantes:
                self.after_idle(hora_entry.focus_set)

    def _abrir_selector_restaurante(self, event, widget):
        """Abre el menú para que pueda recorrerse con flechas y confirmarse con Enter."""
        try:
            if widget._dropdown_menu.winfo_viewable():
                return "break"
            widget._open_dropdown_menu()
            valor_actual = widget.get()
            valores = widget.cget("values")
            if valor_actual in valores:
                widget._dropdown_menu.activate(valores.index(valor_actual))
        except Exception:
            pass
        return "break"

    def _enfocar_selector_restaurante(self, idx: int, abrir: bool = False):
        if idx < 0 or idx >= len(self.filas):
            return
        selector = self.filas[idx].get("_widgets", {}).get("restaurante")
        if not selector or not selector.winfo_exists():
            return
        selector.focus_set()
        if abrir:
            self._abrir_selector_restaurante(None, selector)

    def _on_enter_hora(self, event, idx: int, widget):
        if idx < len(self.filas):
            self.filas[idx]["hora"] = widget.get()
            self._marcar_campo_pendiente(idx, "hora")
            self._programar_guardado(idx)
            descripcion = self.filas[idx].get("_widgets", {}).get("descripcion")
            if descripcion and descripcion.winfo_exists():
                descripcion.focus_set()
        return "break"

    def _on_enter_descripcion(self, event, idx: int, widget):
        """Enter termina la línea actual y prepara inmediatamente la siguiente."""
        if idx >= len(self.filas):
            return "break"

        texto = widget.get("1.0", "end-1c").strip()
        self.filas[idx]["descripcion"] = texto
        self._marcar_campo_pendiente(idx, "descripcion")
        self._programar_guardado(idx)
        if not texto:
            return "break"

        restaurante = self.filas[idx].get("restaurante", "")
        siguiente = next(
            (
                i for i in range(idx + 1, len(self.filas))
                if not self.filas[i].get("b_id")
                and not self.filas[i].get("hora")
                and not self.filas[i].get("descripcion")
                and not self.filas[i].get("evidencias")
            ),
            None,
        )
        if siguiente is None:
            siguiente = self._agregar_fila_vacia(restaurante, enfocar_restaurante=True)
        else:
            fila_siguiente = self.filas[siguiente]
            if not fila_siguiente.get("restaurante"):
                fila_siguiente["restaurante"] = restaurante
                selector = fila_siguiente.get("_widgets", {}).get("restaurante")
                if selector and selector.winfo_exists():
                    selector.set(restaurante or "— Restaurante —")
            self.after_idle(lambda i=siguiente: self._enfocar_selector_restaurante(i, abrir=True))
        return "break"

    def _on_shift_enter_descripcion(self, idx: int, widget):
        """Permite un salto de línea manual sin abandonar el flujo de Enter."""
        if idx < len(self.filas):
            widget.insert("insert", "\n")
            self._on_keyrelease_textbox(idx, widget)
        return "break"

    def _on_keyrelease(self, idx: int, campo: str, widget):
        """Cada pulsación de tecla reinicia el debounce."""
        self.filas[idx][campo] = widget.get()
        self._marcar_campo_pendiente(idx, campo)
        self._programar_guardado(idx)

    def _on_cambiar_urgencia(self, idx: int, display_value: str):
        """Convierte el nombre display a valor backend y reconstruye la tarjeta."""
        valor = URGENCIA_DISPLAY_A_VALOR.get(display_value, "leve")
        self.filas[idx]["urgencia"] = valor
        self._marcar_campo_pendiente(idx, "urgencia")
        self._programar_guardado(idx)
        self._reconstruir_tarjeta(idx)   # reconstruir para cambiar bg_color

    def _copiar_codigo(self, codigo: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(codigo)
            self.update()
            self._mostrar_toast(f"✅  Código {codigo} copiado")
        except Exception:
            pass

    def _mostrar_toast(self, mensaje: str):
        toast = IconLabel(
            self.top_bar, text=mensaje,
            fg_color=STATUS["success"]["bg"], text_color=STATUS["success"]["text"],
            corner_radius=6, font=get_font(size=11),
            padx=10, pady=4,
        )
        toast.pack(side="left", padx=10)
        self.after(2500, toast.destroy)

    # ─── Cerrar bitácora del día ──────────────────────────────────────────────

    def _on_cerrar_bitacora_dia(self):
        """
        Valida que todas las filas con b_id tengan restaurante, hora y descripción.
        Si pasan la validación, llama al backend para marcar la bitácora como cerrada.
        """
        incompletas = []
        for i, fila in enumerate(self.filas):
            # Solo validar filas que ya tienen ID en el backend
            if not fila.get("b_id"):
                continue
            faltantes = []
            if not fila.get("restaurante", "").strip():
                faltantes.append("restaurante")
            if not fila.get("hora", "").strip():
                faltantes.append("hora")
            if not fila.get("descripcion", "").strip():
                faltantes.append("descripción")
            if faltantes:
                codigo = fila.get("codigo", f"fila #{i+1}")
                incompletas.append(f"  • {codigo}: falta {', '.join(faltantes)}")

        if incompletas:
            messagebox.showwarning(
                "Filas incompletas",
                "No se puede cerrar la bitácora del día.\n"
                "Las siguientes filas están incompletas:\n\n"
                + "\n".join(incompletas)
                + "\n\nCompleta o elimina esas filas antes de cerrar.",
            )
            return

        if not messagebox.askyesno(
            "Confirmar cierre",
            f"¿Cerrar la bitácora del día {self.fecha_actual}?\n\n"
            "Esta acción marcará todas las filas como cerradas en el servidor.",
        ):
            return

        def _worker():
            resultado = cerrar_bitacora_dia(self.fecha_actual)
            if resultado is not None:
                cerradas = resultado.get("cerradas", 0)
                self.after(0, self._mostrar_toast, f"✅  Bitácora cerrada ({cerradas} filas)")
                self.after(0, self._actualizar_indicador_sync, "ok")
            else:
                self.after(
                    0,
                    messagebox.showerror,
                    "Error",
                    "No se pudo cerrar la bitácora en el servidor.\nRevisa la conexión.",
                )

        threading.Thread(target=_worker, daemon=True).start()

    # ─── Debounce + guardado ──────────────────────────────────────────────────

    def _programar_guardado(self, idx: int):
        """Cancela el timer anterior y programa uno nuevo a 1.5 s."""
        if idx < 0 or idx >= len(self.filas):
            return
        timer_id = self.filas[idx].get("_debounce_id")
        if timer_id:
            self.after_cancel(timer_id)
        self.filas[idx]["_debounce_id"] = self.after(DEBOUNCE_MS, lambda: self._procesar_modificacion(idx))

    def _reservar_creacion(self, local_id: int) -> bool:
        """Reserva una fila local para que sólo un worker pueda hacer su POST."""
        if local_id is None:
            return False
        with self.lock:
            if local_id in self._creaciones_en_curso:
                return False
            self._creaciones_en_curso.add(local_id)
            return True

    def _liberar_creacion(self, local_id: int):
        if local_id is None:
            return
        with self.lock:
            self._creaciones_en_curso.discard(local_id)

    def _marcar_creacion_fallida(self, local_id: int):
        for fila in self.filas:
            if fila.get("local_id") == local_id:
                fila["_creando_en_nube"] = False
                break
        self._liberar_creacion(local_id)

    def _procesar_modificacion(self, idx: int):
        """
        API-First:
        1) Intenta sincronizar con el backend directo en un hilo daemon.
        2) Si falla, usa SQLite local como contingencia.
        """
        if idx >= len(self.filas):
            return
        fila = self.filas[idx]

        # Evitar crear duplicados si ya hay una petición POST en vuelo.
        if fila.get("_creando_en_nube") and not fila.get("b_id"):
            self._programar_guardado(idx)
            return

        fila["_debounce_id"] = None

        rest_nombre = fila.get("restaurante", "").strip()
        rest_id = fila.get("restaurante_id") or self.mapa_restaurantes.get(rest_nombre)

        # Vigilante siempre del selector global — no del campo por fila
        vig_nombre = self.usuario_activo["nombre"].strip()
        usr_id = self.mapa_usuarios.get(vig_nombre, self.usuario_activo["id"])

        if not rest_id or not usr_id:
            return

        datos_locales = {
            "local_id":       fila.get("local_id"),
            "b_id":           fila.get("b_id", ""),
            "codigo":         fila.get("codigo", ""),
            "restaurante_id": rest_id,
            "usuario_id":     usr_id,
            "descripcion":    fila.get("descripcion", ""),
            "fecha":          self.fecha_actual,
            "hora":           fila.get("hora", ""),
            "urgencia":       fila.get("urgencia", "leve"),
            "client_id":      fila.get("client_id", ""),
        }
        campos_enviados = {
            campo: fila.get(campo)
            for campo in ("restaurante", "hora", "descripcion", "urgencia")
        }

        # SQLite siempre recibe primero la última versión de la fila. Además de
        # proteger el texto ante cortes, esto da un ID estable a las evidencias
        # si la bitácora todavía no ha podido crearse en el servidor.
        try:
            local_id = guardar_bitacora_local(datos_locales)
            datos_locales["local_id"] = local_id
            fila["local_id"] = local_id
        except Exception as e:
            print(f"[bitacoras] No se pudo guardar la fila localmente: {e}")
            self.after(0, self._actualizar_indicador_sync, "offline")
            return

        crear_nueva = not fila.get("b_id") and bool(
            datos_locales.get("hora") or datos_locales.get("descripcion")
        )
        if crear_nueva:
            if not self._reservar_creacion(local_id):
                # El worker de pendientes ya tomó esta fila. La dejamos
                # programada para que aplique cualquier edición posterior.
                self._programar_guardado(idx)
                return
            fila["_creando_en_nube"] = True

        def _sync_bitacora():
            try:
                dto = {
                    "restaurante_id": datos_locales["restaurante_id"],
                    "usuario_id":     datos_locales["usuario_id"],
                    "descripcion":    datos_locales["descripcion"],
                    "fecha":          datos_locales["fecha"],
                    "hora":           datos_locales["hora"],
                    "urgencia":       datos_locales["urgencia"],
                    "client_id":      datos_locales["client_id"],
                }
                b_id   = datos_locales.get("b_id", "")
                
                if not b_id:
                    if not (datos_locales.get("hora") or datos_locales.get("descripcion")):
                        return
                    
                    resultado = crear_bitacora(dto)
                    if not resultado:
                        raise Exception("Fallo en API")
                    
                    b_id = resultado.get("id", "")
                    codigo = resultado.get("codigo", "")
                    if not b_id:
                        raise Exception("El servidor no devolvió el ID de la bitácora creada")
                    marcar_bitacora_sincronizada(local_id, b_id, codigo)
                    self.after(0, self._aplicar_resultado_creacion, b_id, codigo, local_id, resultado.get("created_at"))
                else:
                    resultado = actualizar_bitacora(b_id, dto, version=datos_locales.get("version"))
                    if resultado and isinstance(resultado, dict) and resultado.get("__conflict__"):
                        self.after(0, lambda r=resultado: messagebox.showwarning("Conflicto", r["mensaje"]))
                        return
                    if not resultado:
                        raise Exception("Fallo en API")
                    
                    marcar_bitacora_sincronizada(local_id, b_id, datos_locales.get("codigo", ""))

                self.after(0, self._limpiar_campos_guardados, local_id, campos_enviados)
                
                self.after(0, self._actualizar_indicador_sync, "ok")
            except Exception:
                # Fallback to local DB (Fail-safe)
                if crear_nueva:
                    self.after(0, self._marcar_creacion_fallida, local_id)
                self.after(0, self._actualizar_indicador_sync, "offline")

        self.after(0, self._actualizar_indicador_sync, "syncing")
        threading.Thread(target=_sync_bitacora, daemon=True).start()

    def _actualizar_codigo_fila(self, idx: int):
        """Actualiza sólo el código; evita reconstruir controles con foco."""
        if idx < 0 or idx >= len(self.filas):
            return
        fila = self.filas[idx]
        card = fila.get("_card_frame")
        if not card or not card.winfo_exists():
            return

        widgets = fila.setdefault("_widgets", {})
        codigo = fila.get("codigo", "")
        actual = widgets.get("codigo")
        if actual and actual.winfo_exists() and isinstance(actual, ctk.CTkButton):
            actual.configure(text=codigo, command=lambda c=codigo: self._copiar_codigo(c))
            return
        if actual and actual.winfo_exists():
            actual.destroy()

        boton = IconButton(
            card,
            text=codigo,
            width=ANCHO_COD,
            height=28,
            fg_color=STATUS["info"]["bg"],
            text_color=STATUS["info"]["text"],
            hover_color=SURFACE_SECONDARY,
            font=get_font(family="Consolas", size=12, weight="bold"),
            corner_radius=4,
            command=lambda c=codigo: self._copiar_codigo(c),
        )
        boton.grid(row=0, column=3, padx=2, pady=3)
        widgets["codigo"] = boton

    def _aplicar_resultado_creacion(self, b_id: str, codigo: str, local_id: int, created_at=None):
        """Vincula el ID sin reconstruir la fila ni quitar el foco al usuario."""
        idx = next(
            (i for i, fila in enumerate(self.filas) if fila.get("local_id") == local_id),
            None,
        )
        if idx is None:
            self._liberar_creacion(local_id)
            return

        # El delta polling puede llegar antes que la respuesta del POST y
        # materializar el mismo registro como una segunda tarjeta. Consolidar
        # ambas por el ID definitivo antes de actualizar el borrador local.
        duplicados = [
            i for i, fila in enumerate(self.filas)
            if i != idx and fila.get("b_id") == b_id
        ]
        for duplicado in reversed(duplicados):
            created_at = created_at or self.filas[duplicado].get("created_at")
            card = self.filas[duplicado].get("_card_frame")
            if card and card.winfo_exists():
                card.destroy()
            self.filas.pop(duplicado)
            if duplicado < idx:
                idx -= 1
        fila = self.filas[idx]
        fila["b_id"] = b_id
        fila["codigo"] = codigo
        if created_at:
            fila["created_at"] = created_at
        fila["_creando_en_nube"] = False
        self._actualizar_codigo_fila(idx)
        self.ultimo_hash_bd = None
        self._liberar_creacion(local_id)
        self._ordenar_tarjetas_por_creacion()

    def _ordenar_tarjetas_por_creacion(self):
        """Sólo cambia la posición visual; índices/callbacks y foco siguen vivos."""
        ordenadas = sorted(enumerate(self.filas), key=lambda item: clave_orden_bitacora(item[1], item[0]))
        for posicion, (_, fila) in enumerate(ordenadas):
            card = fila.get("_card_frame")
            if card and card.winfo_exists():
                if int(card.grid_info().get("row", -1)) != posicion:
                    card.grid_configure(row=posicion)

    def _asegurar_bitacora_local(self, fila: dict) -> int | None:
        """Asegura un ID local estable para guardar evidencias sin conexión."""
        if fila.get("b_id"):
            return fila.get("local_id")

        if fila.get("local_id"):
            existente = obtener_bitacora_local(fila["local_id"])
            if existente and existente.get("b_id"):
                # El worker de polling pudo sincronizarla mientras esta ventana
                # seguía mostrando el estado local anterior.
                fila["b_id"] = existente["b_id"]
                fila["codigo"] = existente.get("codigo", "")
                return fila["local_id"]

        rest_nombre = fila.get("restaurante", "").strip()
        rest_id = fila.get("restaurante_id") or self.mapa_restaurantes.get(rest_nombre)
        vig_nombre = self.usuario_activo["nombre"].strip()
        usr_id = self.mapa_usuarios.get(vig_nombre, self.usuario_activo["id"])
        if not rest_id or not usr_id:
            return None

        datos = {
            "local_id": fila.get("local_id"),
            "b_id": "",
            "codigo": "",
            "restaurante_id": rest_id,
            "usuario_id": usr_id,
            "descripcion": fila.get("descripcion", ""),
            "fecha": self.fecha_actual,
            "hora": fila.get("hora", ""),
            "urgencia": fila.get("urgencia", "leve"),
            "client_id": fila.get("client_id", ""),
        }
        local_id = guardar_bitacora_local(datos)
        fila["local_id"] = local_id
        return local_id

    # ─── Lógica del botón Evidencia ───────────────────────────────────────────

    def _on_boton_evidencia(self, idx: int):
        fila = self.filas[idx]
        rest_nombre = fila.get("restaurante", "").strip()

        if not rest_nombre or (not fila.get("restaurante_id") and rest_nombre not in self.mapa_restaurantes):
            messagebox.showwarning(
                "Restaurante requerido",
                "Selecciona un restaurante antes de agregar evidencia.\n"
                "El código se genera al crear el registro en el servidor.",
            )
            return

        # Una fila que todavía no existe en el servidor se conserva primero en
        # SQLite. La sincronización del padre le asignará código y luego subirá
        # cualquier evidencia que quede asociada a su local_id.
        if not fila.get("b_id"):
            try:
                if self._asegurar_bitacora_local(fila) is None:
                    raise ValueError("No se pudo identificar el restaurante o usuario.")
            except Exception as e:
                messagebox.showerror("Error local", f"No se pudo guardar la bitácora localmente:\n{e}")
                return

        codigo = fila.get("codigo", "")
        if fila.get("b_id"):
            self._continuar_evidencia(idx)
        else:
            self._mostrar_panel_evidencia(codigo, fila.get("evidencias", []), fila=fila)

    def _continuar_evidencia(self, idx: int):
        fila = self.filas[idx]
        codigo = fila["codigo"]
        if not codigo:
            self._mostrar_panel_evidencia("", fila.get("evidencias", []), fila=fila)
            return
        self._mostrar_panel_evidencia(codigo, fila.get("evidencias", []), fila=fila)  # muestra caché mientras carga

        def _fetch_evidencias():
            try:
                evidencias_frescas = obtener_evidencias_bitacora(codigo)
                if evidencias_frescas is None:
                    return  # Un corte de red no significa que se borraron las evidencias.
                def _actualizar():
                    if not self._cerrado:
                        self._actualizar_evidencias_fila(codigo, evidencias_frescas)
                self.after(0, _actualizar)
            except Exception:
                pass
        threading.Thread(target=_fetch_evidencias, daemon=True).start()

    # ─── Carga inicial ────────────────────────────────────────────────────────

    def _carga_inicial(self):
        """Full-fetch al arrancar. Establece el cursor de timestamp para los deltas posteriores."""
        def _worker():
            try:
                bitacoras = obtener_bitacoras_por_fecha(self.fecha_actual)
                if bitacoras is not None:
                    self.timestamp_ultimo_sync = cursor_bitacoras_servidor(bitacoras)
                    self.after(0, self._reconciliar_con_datos, bitacoras)
                else:
                    self.after(0, self._agregar_fila_vacia)
            except Exception as e:
                print(f"[carga_inicial] Error: {e}")
                self.after(0, self._agregar_fila_vacia)

        threading.Thread(target=_worker, daemon=True).start()

    # ─── Polling ──────────────────────────────────────────────────────────────

    def _iniciar_polling(self):
        self.stop_event.clear()  # Asegurar que el event esté limpio al (re)iniciar
        self._hilo_polling = threading.Thread(
            target=self._polling_worker, daemon=True, name="BitacorasPolling"
        )
        self._hilo_polling.start()

    def _polling_worker(self):
        while not self.stop_event.is_set():
            # Intentar sincronizar pendientes offline antes de consultar
            try:
                self._sincronizar_pendientes()
            except Exception as e:
                print(f"[sync_pendientes] Error: {e}")

            try:
                ts_cursor = self.timestamp_ultimo_sync
                if ts_cursor is None:
                    # Sin full-fetch previo, hacemos uno completo ahora
                    bitacoras = obtener_bitacoras_por_fecha(self.fecha_actual)
                    if self.stop_event.is_set():
                        break
                    if bitacoras is not None:
                        self.timestamp_ultimo_sync = cursor_bitacoras_servidor(bitacoras)
                        self.after(0, self._reconciliar_con_datos, bitacoras)
                        self.after(0, self._actualizar_indicador_sync, "ok")
                    else:
                        self.after(0, self._actualizar_indicador_sync, "offline")
                else:
                    # Delta-fetch: solo pedir lo que cambio desde el cursor
                    deltas = obtener_bitacoras_delta(self.fecha_actual, ts_cursor)
                    if self.stop_event.is_set():
                        break
                    if deltas is None:
                        # Error de red
                        self.after(0, self._actualizar_indicador_sync, "offline")
                    elif len(deltas) > 0:
                        # Hay cambios: aplicarlos in-place y avanzar cursor
                        self.timestamp_ultimo_sync = cursor_bitacoras_servidor(deltas, ts_cursor)
                        self.after(0, self._aplicar_deltas, deltas)
                        self.after(0, self._actualizar_indicador_sync, "ok")
                    else:
                        # Sin cambios: conservar el cursor DEL SERVIDOR, no el reloj PC.
                        self.after(0, self._actualizar_indicador_sync, "ok")
            except Exception as e:
                print(f"[polling] Error: {e}")
                self.after(0, self._actualizar_indicador_sync, "offline")

            self.stop_event.wait(5)

    def _sincronizar_pendientes(self):
        """Sube registros offline a medida que la conexión se restablece."""
        pendientes = obtener_bitacoras_pendientes()
        if pendientes:
            self.after(0, self._actualizar_indicador_sync, "syncing", len(pendientes))

        for p in pendientes:
            reserva_creacion = None
            try:
                dto = {
                    "restaurante_id": p["restaurante_id"],
                    "usuario_id":     p["usuario_id"],
                    "descripcion":    p["descripcion"],
                    "fecha":          p["fecha"],
                    "hora":           p["hora"],
                    "urgencia":       p["urgencia"],
                    "client_id":      p.get("client_id"),
                }
                b_id   = p["b_id"]
                codigo = p["codigo"]

                if not b_id:
                    # Una fila vacía puede tener evidencia en cola, pero primero
                    # debe completar los datos mínimos para crear el padre.
                    if not (p.get("hora") or p.get("descripcion")):
                        continue
                    reserva_creacion = p["id"]
                    if not self._reservar_creacion(reserva_creacion):
                        reserva_creacion = None
                        continue
                    resultado = crear_bitacora(dto)
                    if resultado:
                        b_id   = resultado.get("id", "")
                        codigo = resultado.get("codigo", "")
                        if not b_id:
                            raise Exception("El servidor no devolvió el ID de la bitácora creada")
                else:
                    version = p.get("version")
                    resultado = actualizar_bitacora(b_id, dto, version=version)
                    if resultado and isinstance(resultado, dict) and resultado.get("__conflict__"):
                        self.after(0, lambda r=resultado: messagebox.showwarning("Conflicto Sincronización", r["mensaje"]))
                        continue

                if resultado is not None:
                    marcar_bitacora_sincronizada(p["id"], b_id, codigo)
                    nombre_restaurante = next(
                        (
                            nombre for nombre, rest_id in self.mapa_restaurantes.items()
                            if rest_id == p["restaurante_id"]
                        ),
                        None,
                    )
                    self.after(
                        0,
                        self._limpiar_campos_guardados,
                        p["id"],
                        {
                            "restaurante": nombre_restaurante,
                            "hora": p.get("hora", ""),
                            "descripcion": p.get("descripcion", ""),
                            "urgencia": p.get("urgencia", "leve"),
                        },
                    )
                    # Actualizar fila en memoria si existe
                    self.after(0, self._actualizar_fila_por_local_id, p["id"], b_id, codigo, resultado.get("created_at"))
                    # El callback libera la reserva cuando ya enlazó el b_id.
                    reserva_creacion = None
            except Exception as e:
                print(f"[sync_pendientes] Fila {p['id']}: {e}")
                break  # parar si hay error de red, reintentará en 5s
            finally:
                if reserva_creacion is not None:
                    self._liberar_creacion(reserva_creacion)

        # Las evidencias de filas ya sincronizadas también se reintentan aunque
        # no haya registros padre pendientes.
        self._solicitar_sincronizacion_evidencias()

    def _actualizar_fila_por_local_id(self, local_id: int, b_id: str, codigo: str, created_at=None):
        for f in self.filas:
            if f.get("local_id") == local_id:
                self._aplicar_resultado_creacion(b_id, codigo, local_id, created_at)
                if self._bitacora_local_id_panel == local_id:
                    self._mostrar_panel_evidencia(codigo, f.get("evidencias", []), fila=f)
                return
        self._liberar_creacion(local_id)

    def _actualizar_fila_remota(self, idx: int, datos_nuevos: dict):
        """Fusiona un delta sin tocar los campos que el usuario está editando."""
        if idx < 0 or idx >= len(self.filas):
            return
        fila = self.filas[idx]
        with self.lock:
            campos_activos = set(self.campos_editando.get(idx, set()))
        campos_pendientes = set(fila.get("_campos_pendientes", set()))
        campos_protegidos = campos_activos | campos_pendientes
        if "restaurante" in campos_protegidos:
            campos_protegidos.add("restaurante_id")
        cambios = {k: v for k, v in datos_nuevos.items()
                   if k not in campos_protegidos and fila.get(k) != v}
        if "evidencias" in cambios and firma_evidencias(fila.get("evidencias", [])) == firma_evidencias(cambios["evidencias"]):
            cambios.pop("evidencias")
        valores_locales = {campo: fila.get(campo) for campo in campos_protegidos}
        fila.update(datos_nuevos)
        fila.update(valores_locales)

        # Incluso sin foco, una evidencia nueva no debe destruir toda la fila.
        if cambios:
            self._actualizar_widgets_fila_in_place(idx, cambios, campos_protegidos)

    def _actualizar_widgets_fila_in_place(self, idx: int, datos: dict, protegidos: set):
        fila = self.filas[idx]
        widgets = fila.get("_widgets", {})

        if "restaurante" in datos and "restaurante" not in protegidos:
            selector = widgets.get("restaurante")
            if selector and selector.winfo_exists():
                selector.set(datos["restaurante"] or "— Restaurante —")

        if "hora" in datos and "hora" not in protegidos:
            entry = widgets.get("hora")
            if entry and entry.winfo_exists():
                entry.delete(0, "end")
                if datos["hora"]:
                    entry.insert(0, datos["hora"])

        if "descripcion" in datos and "descripcion" not in protegidos:
            textbox = widgets.get("descripcion")
            if textbox and textbox.winfo_exists():
                textbox.delete("1.0", "end")
                if datos["descripcion"]:
                    textbox.insert("1.0", datos["descripcion"])
                self._ajustar_altura_textbox(textbox)

        if "urgencia" in datos and "urgencia" not in protegidos:
            urgencia = URGENCIA_LEGACY.get(datos["urgencia"], datos["urgencia"])
            info = URGENCIA_COLORES.get(urgencia, URGENCIA_COLORES["leve"])
            menu = widgets.get("urgencia")
            card = fila.get("_card_frame")
            if menu and menu.winfo_exists():
                menu.set(URGENCIA_VALOR_A_DISPLAY.get(urgencia, "Leve"))
                menu.configure(
                    fg_color=info["bg"],
                    text_color=info["fg"],
                    button_color=info["bg"],
                    button_hover_color=info["bg"],
                )
            if card and card.winfo_exists():
                color = info["tarjeta_par"] if idx % 2 == 0 else info["tarjeta_impar"]
                card.configure(fg_color=color)

        if "codigo" in datos and fila.get("codigo"):
            self._actualizar_codigo_fila(idx)
        if "evidencias" in datos or "evidencia" in datos:
            self._actualizar_boton_evidencia(idx)

    def _limpiar_campos_guardados(self, local_id: int, enviados: dict):
        """Libera sólo los campos que siguen iguales a la versión ya sincronizada."""
        for fila in self.filas:
            if fila.get("local_id") != local_id:
                continue
            pendientes = fila.get("_campos_pendientes", set())
            for campo in tuple(pendientes):
                if campo in enviados and enviados[campo] is not None and fila.get(campo) == enviados[campo]:
                    pendientes.discard(campo)
            break

    def _aplicar_deltas(self, deltas: list):
        """
        Actualiza la UI in-place con los registros cambiados recibidos del servidor.
        Reglas:
          - Si el delta trae deleted_at != None → retirar la tarjeta de la UI.
          - Si el b_id ya está en self.filas → actualizar sólo controles cambiados.
          - Si es nuevo → construir la tarjeta y añadirla.
        Nunca limpia la lista completa; la limpieza sólo ocurre al cambiar de fecha.
        """
        if self._cerrado:
            return
        ids_local = {f["b_id"]: i for i, f in enumerate(self.filas) if f.get("b_id")}
        ids_cliente = {f["client_id"]: i for i, f in enumerate(self.filas) if f.get("client_id")}

        for b in deltas:
            b_id       = b.get("id")
            eliminado  = b.get("deleted_at") is not None

            if eliminado:
                if b_id in ids_local:
                    idx = ids_local[b_id]
                    card = self.filas[idx].get("_card_frame")
                    if card and card.winfo_exists():
                        card.destroy()
                    self.filas.pop(idx)
                    # Reconstruir índices para tarjetas por debajo
                    for j in range(idx, len(self.filas)):
                        self._reconstruir_tarjeta(j)
                    # Actualizar mapa local después de pop
                    ids_local = {f["b_id"]: i for i, f in enumerate(self.filas) if f.get("b_id")}
                    ids_cliente = {f["client_id"]: i for i, f in enumerate(self.filas) if f.get("client_id")}
                continue

            rest  = b.get("restaurante", {}).get("nombre", "") if isinstance(b.get("restaurante"), dict) else ""
            vig   = b.get("usuario", {}).get("nombre", "") if isinstance(b.get("usuario"), dict) else ""
            evids = b.get("evidencias", [])
            urgencia_raw = b.get("urgencia", "leve")
            urgencia = URGENCIA_LEGACY.get(urgencia_raw, urgencia_raw)

            datos_nuevos = {
                "b_id":        b_id,
                "codigo":      b.get("codigo", ""),
                "hora":        b.get("hora", ""),
                "restaurante": rest,
                "restaurante_id": b.get("restaurante_id") or (b.get("restaurante") if isinstance(b.get("restaurante"), dict) else {}).get("id"),
                "vigilante":   vig,
                "descripcion": b.get("descripcion", ""),
                "urgencia":    urgencia,
                "evidencias":  evids,
                "evidencia":   "Sí" if (evids or b.get("evidencia_url")) else "",
                "version":     b.get("version"),
                "created_at":  b.get("created_at"),
                "client_id":   b.get("client_id") or "",
            }

            idx = ids_local.get(b_id, ids_cliente.get(b.get("client_id")))
            if idx is not None:
                self._actualizar_fila_remota(idx, datos_nuevos)
                ids_local[b_id] = idx

                if self._codigo_panel_activo and self._codigo_panel_activo == datos_nuevos["codigo"]:
                    self._mostrar_panel_evidencia(datos_nuevos["codigo"], evids)
            else:
                datos_nuevos["local_id"]     = None
                datos_nuevos["_debounce_id"] = None
                self.filas.append(datos_nuevos)
                nuevo_idx = len(self.filas) - 1
                self._construir_tarjeta(nuevo_idx)
                ids_local[b_id] = nuevo_idx
                if b.get("client_id"):
                    ids_cliente[b["client_id"]] = nuevo_idx

        self._ordenar_tarjetas_por_creacion()
        if not self.filas:
            self._agregar_fila_vacia()

    def _reconciliar_con_datos(self, bitacoras: list):
        """
        Sincroniza datos del backend con `self.filas` sin pisar borradores locales.
        Normaliza también valores legacy de urgencia (low/medium/critical).
        """
        with self.lock:
            nuevo_hash = hash(str(bitacoras))
            if self.ultimo_hash_bd == nuevo_hash:
                if not self.filas:
                    self.after(0, self._agregar_fila_vacia)
                return
            self.ultimo_hash_bd = nuevo_hash

        ids_bd    = {b.get("id"): b for b in bitacoras}
        ids_local = {f["b_id"]: i for i, f in enumerate(self.filas) if f.get("b_id")}
        ids_cliente = {f["client_id"]: i for i, f in enumerate(self.filas) if f.get("client_id")}

        for b_id, b in ids_bd.items():
            rest  = b.get("restaurante", {}).get("nombre", "") if isinstance(b.get("restaurante"), dict) else ""
            vig   = b.get("usuario", {}).get("nombre", "") if isinstance(b.get("usuario"), dict) else ""
            evids = b.get("evidencias", [])

            # Normalizar urgencia legacy (valores viejos antes del remapeo SQL)
            urgencia_raw = b.get("urgencia", "leve")
            urgencia = URGENCIA_LEGACY.get(urgencia_raw, urgencia_raw)

            datos_nuevos = {
                "b_id":        b_id,
                "codigo":      b.get("codigo", ""),
                "hora":        b.get("hora", ""),
                "restaurante": rest,
                "restaurante_id": b.get("restaurante_id") or (b.get("restaurante") if isinstance(b.get("restaurante"), dict) else {}).get("id"),
                "vigilante":   vig,
                "descripcion": b.get("descripcion", ""),
                "urgencia":    urgencia,
                "evidencias":  evids,
                "evidencia":   "Sí" if (evids or b.get("evidencia_url")) else "",
                "version":     b.get("version"),
                "created_at":  b.get("created_at"),
                "client_id":   b.get("client_id") or "",
            }
            local_idx = ids_local.get(b_id, ids_cliente.get(b.get("client_id")))
            if local_idx is not None:
                
                # Performance fix (Diffing): Solo reconstruir la tarjeta si los datos
                # relevantes de renderizado cambiaron.
                cambios = False
                for k, v in datos_nuevos.items():
                    if k in ["b_id", "local_id", "_debounce_id"]: 
                        continue
                    if self.filas[local_idx].get(k) != v:
                        cambios = True
                        break

                if cambios:
                    self._actualizar_fila_remota(local_idx, datos_nuevos)
                
                # Auto-refresco del panel lateral de evidencias si está abierto para esta fila
                if self._codigo_panel_activo and self._codigo_panel_activo == datos_nuevos["codigo"]:
                    self.after(0, lambda c=datos_nuevos["codigo"], evs=evids: self._mostrar_panel_evidencia(c, evs))
            else:
                datos_nuevos["local_id"]     = None
                datos_nuevos["_debounce_id"] = None
                self.filas.append(datos_nuevos)
                self._construir_tarjeta(len(self.filas) - 1)

            ids_local[b_id] = local_idx if local_idx is not None else len(self.filas) - 1
            if b.get("client_id"):
                ids_cliente[b["client_id"]] = ids_local[b_id]

        # Borradores locales: asegurar que tienen tarjeta
        for i, f in enumerate(self.filas):
            if not f.get("b_id") and not f.get("_card_frame"):
                self._construir_tarjeta(i)

        self._ordenar_tarjetas_por_creacion()
        if not self.filas:
            self._agregar_fila_vacia()

    # ─── Panel lateral de evidencia ───────────────────────────────────────────

    def _construir_panel_evidencia(self):
        self.frame_evidencia = ctk.CTkFrame(self, width=290, fg_color=SURFACE, border_width=1, border_color=BORDER)
        self.frame_evidencia.grid_propagate(False)
        self.frame_evidencia.grid_columnconfigure(0, weight=1)

        # Encabezado
        header = ctk.CTkFrame(self.frame_evidencia, fg_color=PRIMARY, corner_radius=0)
        header.pack(fill="x")

        self.label_panel_titulo = IconLabel(
            header, text="\u25A3  Evidencias",
            font=get_font(size=14, weight="bold"), text_color="#FFFFFF",
        )
        self.label_panel_titulo.pack(side="left", padx=12, pady=10)

        IconButton(
            header, text="\u2715", width=30, height=30,
            fg_color="transparent", hover_color=PRIMARY_HOVER, text_color="#FFFFFF",
            command=self._ocultar_panel_evidencia,
        ).pack(side="right", padx=8, pady=6)

        # Código (solo lectura)
        IconLabel(
            self.frame_evidencia, text="Código de bitácora",
            text_color=TEXT_MUTED, font=get_font(size=11),
        ).pack(pady=(14, 2), padx=16, anchor="w")

        frame_cod = ctk.CTkFrame(self.frame_evidencia, fg_color="transparent")
        frame_cod.pack(padx=16, fill="x", pady=(0, 2))

        self.label_codigo = IconLabel(
            frame_cod,
            text="——————",
            font=get_font(family="Consolas", size=20, weight="bold"),
            fg_color=STATUS["info"]["bg"],
            text_color=STATUS["info"]["text"],
            corner_radius=6,
            padx=12, pady=6,
        )
        self.label_codigo.pack(side="left", fill="x", expand=True)

        IconButton(
            frame_cod, text="\u2399", width=32, height=32,
            fg_color="transparent", hover_color=SURFACE_SECONDARY,
            text_color=TEXT_SECONDARY,
            command=lambda: self._copiar_codigo(self._codigo_panel_activo),
        ).pack(side="left", padx=(6, 0))

        # ── Área de lista de evidencias existentes ────────────────────────
        ctk.CTkFrame(self.frame_evidencia, height=1, fg_color=BORDER).pack(fill="x", padx=16, pady=10)

        IconLabel(
            self.frame_evidencia, text="Evidencias vinculadas",
            text_color=TEXT_MUTED, font=get_font(size=11),
        ).pack(padx=16, anchor="w")

        self.frame_lista_ev = ctk.CTkScrollableFrame(self.frame_evidencia, height=120, fg_color=SURFACE_SECONDARY)
        self.frame_lista_ev.pack(fill="x", padx=16, pady=(4, 0))

        # ── Agregar nueva evidencia ───────────────────────────────────────
        ctk.CTkFrame(self.frame_evidencia, height=1, fg_color=BORDER).pack(fill="x", padx=16, pady=10)

        self.switch_audio = ctk.CTkSwitch(self.frame_evidencia, text="Grabar con audio")
        self.switch_audio.pack(pady=(0, 8), padx=16, anchor="w")
        self.switch_audio.deselect()

        self.boton_grabar = IconButton(
            self.frame_evidencia,
            text="\u25CF  Grabar pantalla  (Ctrl+K+L)",
            command=self._toggle_grabacion,
            fg_color=STATUS["error"]["solid"], hover_color=STATUS["error"]["hover"],
            text_color="#FFFFFF",
            font=get_font(size=12, weight="bold"),
        )
        self.boton_grabar.pack(pady=(0, 5), padx=16, fill="x")

        self.boton_detener = IconButton(
            self.frame_evidencia,
            text="\u25A0  Detener y Adjuntar",
            command=self._detener_grabacion,
            fg_color=INVERTED_BG, hover_color="#475569",
            text_color="#FFFFFF",
            font=get_font(size=12),
        )

        self.boton_adjuntar = IconButton(
            self.frame_evidencia,
            text="\u21A5  Adjuntar archivo",
            command=self._on_adjuntar,
            fg_color="transparent", border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=get_font(size=12),
        )
        self.boton_adjuntar.pack(pady=(0, 4), padx=16, fill="x")

        self.boton_screenshot_bit = IconButton(
            self.frame_evidencia,
            text="\u25A4  Tomar Captura",
            command=self._tomar_screenshot,
            fg_color=SECONDARY, hover_color="#0c4a6e",
            text_color="#FFFFFF",
            font=get_font(size=12),
        )
        self.boton_screenshot_bit.pack(pady=(0, 8), padx=16, fill="x")

        self.label_archivo = IconLabel(
            self.frame_evidencia, text="Sin evidencia adjunta",
            text_color=TEXT_MUTED, font=get_font(size=10), wraplength=230,
        )
        self.label_archivo.pack(pady=(0, 4), padx=16)

        self.frame_lista_local = ctk.CTkScrollableFrame(self.frame_evidencia, height=80, fg_color=SURFACE_SECONDARY)
        # Por defecto no se muestra hasta que haya evidencias locales
        # self.frame_lista_local.pack(fill="x", padx=16, pady=(0, 8))

        self.boton_subir = IconButton(
            self.frame_evidencia,
            text="\u2713  Subir y Vincular",
            command=self._on_subir_evidencia,
            fg_color=PRIMARY, hover_color=PRIMARY_HOVER,
            text_color="#FFFFFF",
            font=get_font(size=13, weight="bold"),
            height=44,
        )
        self.boton_subir.pack(pady=(0, 14), padx=16, fill="x")

    def _ocultar_panel_evidencia(self):
        self.frame_evidencia.grid_remove()
        self._panel_ev_visible = False
        self.grid_columnconfigure(1, minsize=0, weight=0)
        self._codigo_panel_activo = ""
        self._bitacora_local_id_panel = None
        self._b_id_panel = ""

    def _mostrar_panel_evidencia(self, codigo: str, evidencias: list, fila: dict | None = None):
        if self._cerrado:
            return
        self._codigo_panel_activo = codigo or ""
        if fila is None and codigo:
            fila = next((f for f in self.filas if f.get("codigo") == codigo), None)
        if fila is not None:
            self._bitacora_local_id_panel = fila.get("local_id")
            self._b_id_panel = fila.get("b_id", "")
        elif codigo:
            self._bitacora_local_id_panel = None
            self._b_id_panel = ""

        self.evidencias_locales_panel = obtener_evidencias_bitacora_pendientes(
            bitacora_local_id=self._bitacora_local_id_panel,
            b_id=self._b_id_panel or None,
        )
        if not self._panel_ev_visible:
            self.grid_columnconfigure(1, minsize=300, weight=0)
            self.frame_evidencia.grid(row=1, column=1, rowspan=2, sticky="ns", padx=(0, 12), pady=10)
            self._panel_ev_visible = True

        # Actualizar código (solo lectura)
        if self._codigo_mostrado != codigo:
            self.label_codigo.configure(text=codigo if codigo else "Pendiente")
            self._codigo_mostrado = codigo
        firma_panel = (
            codigo, self._bitacora_local_id_panel, self._b_id_panel,
            firma_evidencias(evidencias), firma_evidencias(self.evidencias_locales_panel),
        )
        if firma_panel == self._firma_panel_evidencias:
            return
        self._firma_panel_evidencias = firma_panel
        if self._lista_ev_tarjetas is None:
            self._lista_ev_tarjetas = ListaEvidencias(self.frame_lista_ev)
            self._lista_local_tarjetas = ListaEvidencias(self.frame_lista_local)
        
        hay_local = bool(self.evidencias_locales_panel)

        items_nube = [
            (ev.get("id") or ev.get("evidencia_url"), firma_evidencias([ev]), ev)
            for ev in ordenar_evidencias(evidencias)
        ]
        self._lista_ev_tarjetas.actualizar(
            items_nube, self._agregar_chip_evidencia,
            vacio=lambda: IconLabel(
                self.frame_lista_ev, text="Sin evidencias aún",
                text_color=TEXT_MUTED, font=get_font(size=10),
            ),
        )
        self._checkboxes_desc_bit = [card._descarga for card in self._lista_ev_tarjetas.widgets()
                                     if hasattr(card, "_descarga")]
        items_locales = [
            (ev["id"], ev.get("ruta_local", ""), {"evidencia": ev, "indice": idx})
            for idx, ev in enumerate(self.evidencias_locales_panel, start=1)
        ]
        self._lista_local_tarjetas.actualizar(
            items_locales,
            lambda datos: self._agregar_chip_evidencia_local(datos["evidencia"], datos["indice"]),
            actualizar=lambda card, datos: card._label_etiqueta.configure(text=f"Ev. Local {datos['indice']}"),
        )
        if not hay_local:
            self.frame_lista_local.pack_forget()
        else:
            self.frame_lista_local.pack(fill="x", padx=16, pady=(0, 8))

        if hay_local:
            self.label_archivo.configure(
                text=f"Guardadas localmente: {len(self.evidencias_locales_panel)} · pendientes de nube"
            )
        else:
            self.label_archivo.configure(text="Sin evidencia adjunta")

    def _refrescar_lista_evidencias(self):
        if not self._codigo_panel_activo and self._bitacora_local_id_panel is None:
            return
        
        fila_actual = None
        for fila in self.filas:
            if (
                (self._bitacora_local_id_panel is not None
                 and fila.get("local_id") == self._bitacora_local_id_panel)
                or (self._b_id_panel and fila.get("b_id") == self._b_id_panel)
                or (self._codigo_panel_activo and fila.get("codigo") == self._codigo_panel_activo)
            ):
                fila_actual = fila
                break

        self._mostrar_panel_evidencia(
            self._codigo_panel_activo,
            fila_actual.get("evidencias", []) if fila_actual else [],
            fila=fila_actual,
        )

    def _eliminar_evidencia_local(self, evidencia_id: int):
        if self._lock_sync_evidencias.locked():
            messagebox.showwarning("Sincronización en curso", "Espera a que termine la sincronización antes de eliminar esta evidencia.")
            return
        respuesta = messagebox.askyesno("Eliminar", "¿Seguro que quieres borrar esta evidencia local?")
        if not respuesta:
            return
        item = next(
            (ev for ev in self.evidencias_locales_panel if ev["id"] == evidencia_id),
            None,
        )
        if not item:
            return
        ruta = item.get("ruta_local", "")
        try:
            if ruta and os.path.exists(ruta):
                os.remove(ruta)
            eliminar_evidencia_bitacora_pendiente(evidencia_id)
        except OSError as e:
            messagebox.showerror("Error", f"No se pudo eliminar el archivo local:\n{e}")
            return
        self._actualizar_boton_evidencia_de_fila_activa()
        self._refrescar_lista_evidencias()

    def _actualizar_boton_evidencia_de_fila_activa(self):
        for idx, fila in enumerate(self.filas):
            if (
                (self._bitacora_local_id_panel is not None
                 and fila.get("local_id") == self._bitacora_local_id_panel)
                or (self._b_id_panel and fila.get("b_id") == self._b_id_panel)
            ):
                self._actualizar_boton_evidencia(idx)
                break

    def _agregar_chip_evidencia_local(self, evidencia: dict, idx: int):
        ruta = evidencia.get("ruta_local", "")
        nombre = os.path.basename(ruta)
        chip = ctk.CTkFrame(self.frame_lista_local, fg_color=SURFACE_SECONDARY, corner_radius=6, border_width=1, border_color=BORDER)
        
        top_row = ctk.CTkFrame(chip, fg_color="transparent")
        top_row.pack(fill="x", padx=4, pady=2)
        
        chip._label_etiqueta = IconLabel(top_row, text=f"Ev. Local {idx}", font=get_font(size=10, weight="bold"), text_color=STATUS["info"]["text"])
        chip._label_etiqueta.pack(side="left")
        
        IconButton(
            top_row, text="🗑️", width=26, height=18, fg_color=STATUS["error"]["solid"], hover_color=STATUS["error"]["hover"],
            command=lambda evidencia_id=evidencia["id"]: self._eliminar_evidencia_local(evidencia_id)
        ).pack(side="right")
        
        IconLabel(chip, text=nombre, font=get_font(size=10), text_color=TEXT_MUTED, justify="left").pack(side="left", padx=4, pady=(0,4))
        return chip

    def _agregar_chip_evidencia(self, ev: dict):
        """Agrega un chip de miniatura o ícono de video para una evidencia.
        - Imágenes: muestra miniatura clickeable; logguea error si falla la carga.
        - Videos: Extrae frame con OpenCV (si está instalado) o muestra ícono 🎬.
        """
        url = ev.get("evidencia_url", "")
        ext = url.rsplit(".", 1)[-1].lower() if "." in url else ""

        chip = ctk.CTkFrame(self.frame_lista_ev, fg_color=STATUS["info"]["bg"], corner_radius=6)

        es_imagen = ext in ("jpg", "jpeg", "png", "webp")
        es_video  = ext in ("mp4", "avi", "mov", "mkv", "webm")

        # Configurar UI Inicial (Cargando)
        ico = IconLabel(chip, text="🖼" if es_imagen else "🎬", font=get_font(size=18), cursor="hand2")
        ico.pack(side="left", padx=8)
        ico.bind("<Button-1>", lambda e, u=url: __import__("api.client").client.descargar_y_abrir_evidencia(u))

        import re
        nombre_crudo = url.rsplit("/", 1)[-1] if "/" in url else url
        nombre_limpio = re.sub(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}_?', '', nombre_crudo)
        nombre_corto = (nombre_limpio[:24] + "…") if len(nombre_limpio) > 24 else nombre_limpio
        lbl_nombre = IconLabel(
            chip, text=nombre_corto,
            text_color=TEXT_PRIMARY, font=get_font(size=10), cursor="hand2",
        )
        lbl_nombre.pack(side="left", padx=4)
        lbl_nombre.bind("<Button-1>", lambda e, u=url: __import__("api.client").client.descargar_y_abrir_evidencia(u))

        def aplicar(imagen):
            if not chip.winfo_exists():
                return False
            if imagen is not None:
                img_ctk = ctk.CTkImage(light_image=imagen, dark_image=imagen, size=(60, 40))
                ico.configure(image=img_ctk, text="")
                ico.image = img_ctk
            return True

        if es_imagen or es_video:
            self._miniaturas.solicitar(url, aplicar)

        fecha_creada = ev.get("creado_en", "")
        if fecha_creada:
            try:
                dt = datetime.fromisoformat(fecha_creada[:19])
                fecha_str = dt.strftime("%d/%m %H:%M")
            except ValueError:
                fecha_str = ""
            IconLabel(
                chip, text=fecha_str, text_color=TEXT_MUTED, font=get_font(size=9),
            ).pack(side="right", padx=8)

        # Checkbox para descarga múltiple y botón de eliminar (lado derecho)
        if url and url.startswith("http"):
            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(chip, text="", variable=var, width=20, height=20)
            cb.pack(side="right", padx=(0, 4))
            
            ev_id = ev.get("id")
            if ev_id:
                IconButton(
                    chip, text="🗑️", width=26, height=18, fg_color=STATUS["error"]["solid"], hover_color=STATUS["error"]["hover"],
                    command=lambda id=ev_id: self._eliminar_evidencia_nube(id)
                ).pack(side="right", padx=(4, 8))
                
            nombre_desc = url.rsplit("/", 1)[-1] if "/" in url else url
            chip._descarga = (var, nombre_desc, url)
        return chip

    def _eliminar_evidencia_nube(self, ev_id: int):
        from tkinter import messagebox
        import requests
        import threading
        from api.client import API_BASE_URL
        
        respuesta = messagebox.askyesno("Eliminar Evidencia", "Esta acción eliminará el archivo de la nube permanentemente.\n\n¿Estás completamente seguro?")
        if respuesta:
            def _eliminar_worker():
                try:
                    resp = requests.delete(f"{API_BASE_URL}/bitacoras/evidencia/{ev_id}", timeout=10)
                    if resp.status_code in (200, 204):
                        def _on_success():
                            self.ultimo_hash_bd = None
                            self._polling_bitacoras_job()
                        self.after(0, _on_success)
                    else:
                        self.after(0, lambda: messagebox.showerror("Error", f"No se pudo eliminar: {resp.text}"))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Error de red", f"Error de red: {e}"))
            
            threading.Thread(target=_eliminar_worker, daemon=True).start()

    # ─── Screenshot (selector estilo Snipping Tool) ────────────────────────

    def _tomar_screenshot(self):
        """Abre el selector visual de área (estilo Snipping Tool) para captura."""
        self._abrir_selector_captura()

    def _abrir_selector_captura(self):
        try:
            from ui.snipping_tool import open_snipping_tool
        except ImportError:
            from tkinter import messagebox
            messagebox.showerror("Error", "No se encontró snipping_tool.py")
            return
            
        def _on_capture(img, ruta_temp):
            self._registrar_evidencia_local_bitacora(
                ruta_temp, con_audio=False, origen_generado=True
            )
                
        open_snipping_tool(self.controlador, _on_capture)

    def _guardar_screenshot_bit(self, img):
        """Guarda la captura en temp y la adjunta como evidencia pendiente."""
        import tempfile
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta_temp = os.path.join(tempfile.gettempdir(), f"screenshot_bit_{ts}.jpg")
        try:
            img.convert("RGB").save(ruta_temp, "JPEG", quality=85, optimize=True)
        except OSError as e:
            from tkinter import messagebox
            messagebox.showerror("Error al guardar", str(e))
            return
        self._registrar_evidencia_local_bitacora(
            ruta_temp, con_audio=False, origen_generado=True
        )

    def _registrar_evidencia_local_bitacora(
        self,
        ruta_origen: str,
        con_audio: bool = False,
        *,
        origen_generado: bool = False,
        iniciar_sync: bool = True,
        refrescar: bool = True,
    ) -> bool:
        """Copia y registra la evidencia antes de cualquier intento de red."""
        fila = None
        for candidata in self.filas:
            if (
                (self._bitacora_local_id_panel is not None
                 and candidata.get("local_id") == self._bitacora_local_id_panel)
                or (self._b_id_panel and candidata.get("b_id") == self._b_id_panel)
                or (self._codigo_panel_activo
                    and candidata.get("codigo") == self._codigo_panel_activo)
            ):
                fila = candidata
                break
        if fila is None:
            messagebox.showwarning("Bitácora requerida", "Selecciona primero la fila a la que pertenece la evidencia.")
            return False

        rest_nombre = fila.get("restaurante", "").strip()
        if not rest_nombre or (not fila.get("restaurante_id") and rest_nombre not in self.mapa_restaurantes):
            messagebox.showwarning("Restaurante requerido", "Selecciona el restaurante de la bitácora antes de guardar evidencia.")
            return False
        if not ruta_origen or not os.path.isfile(ruta_origen):
            messagebox.showerror("Archivo no encontrado", f"No se encontró la evidencia local:\n{ruta_origen}")
            return False

        try:
            local_id = self._asegurar_bitacora_local(fila) if not fila.get("b_id") else fila.get("local_id")
            if not fila.get("b_id") and local_id is None:
                raise ValueError("No se pudo guardar el registro padre de la bitácora.")

            fecha_iso = str(fila.get("fecha") or self.fecha_actual).split("T")[0]
            nombre_original = os.path.basename(ruta_origen)
            nombre_base, extension = os.path.splitext(nombre_original)
            nombre_local = (
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
                f"{uuid.uuid4().hex[:8]}_{nombre_base[:120]}{extension[:16]}"
            )
            ruta_local = ruta_evidencia_bitacora(fecha_iso, nombre_local)
            if os.path.abspath(ruta_origen) != os.path.abspath(ruta_local):
                shutil.copy2(ruta_origen, ruta_local)

            try:
                agregar_evidencia_bitacora_pendiente(
                    ruta_local,
                    con_audio,
                    prefijo_nube_bitacora(fecha_iso),
                    bitacora_local_id=local_id,
                    b_id=fila.get("b_id", ""),
                    codigo=fila.get("codigo", ""),
                )
                if local_id is not None:
                    estado_local = obtener_bitacora_local(local_id)
                    if estado_local and estado_local.get("b_id"):
                        fila["b_id"] = estado_local["b_id"]
                        fila["codigo"] = estado_local.get("codigo", "")
            except Exception:
                if os.path.exists(ruta_local):
                    os.remove(ruta_local)
                raise

            if origen_generado and os.path.abspath(ruta_origen) != os.path.abspath(ruta_local):
                try:
                    os.remove(ruta_origen)
                except OSError:
                    pass

            if refrescar:
                self._mostrar_panel_evidencia(
                    fila.get("codigo", ""), fila.get("evidencias", []), fila=fila
                )
                self._actualizar_boton_evidencia_de_fila_activa()
            if fila.get("codigo"):
                self.label_archivo.configure(text="Evidencia local guardada; sincronizando…")
            else:
                self.label_archivo.configure(text="Evidencia guardada en esta PC; se subirá al sincronizar la bitácora")

            if iniciar_sync and fila.get("codigo"):
                self._solicitar_sincronizacion_evidencias()
            return True
        except Exception as e:
            messagebox.showerror("Error al guardar evidencia", f"No se pudo guardar la evidencia localmente:\n{e}")
            return False

    # ─── Descarga múltiple de evidencias (bitácoras) ─────────────────────────

    def _on_descargar_seleccionados_bit(self):
        """Inicia la descarga de evidencias de nube marcadas con checkbox."""
        import threading
        seleccionadas = [
            (nombre, url)
            for var, nombre, url in getattr(self, "_checkboxes_desc_bit", [])
            if var.get()
        ]
        if not seleccionadas:
            from tkinter import messagebox
            messagebox.showwarning("Sin selección", "Marca al menos una evidencia para descargar.")
            return

        carpeta = os.path.join(os.path.expanduser("~"), "Downloads", "AuditFlow")
        os.makedirs(carpeta, exist_ok=True)

        self.boton_descargar_ev.configure(state="disabled")
        self.lbl_progreso_desc_bit.configure(text=f"Preparando {len(seleccionadas)} archivos…")

        threading.Thread(
            target=self._descargar_hilo_bit,
            args=(seleccionadas, carpeta),
            daemon=True,
        ).start()

    def _descargar_hilo_bit(self, items: list, carpeta: str):
        """Hilo secundario que descarga con requests stream=True."""
        import requests
        from tkinter import messagebox

        total = len(items)
        exitos = 0
        errores = []

        for idx, (nombre, url) in enumerate(items, start=1):
            self.after(0, self.lbl_progreso_desc_bit.configure, {"text": f"Descargando {idx} de {total}…"})
            try:
                ruta_salida = os.path.join(carpeta, nombre)
                if os.path.exists(ruta_salida):
                    base, ext = os.path.splitext(nombre)
                    ruta_salida = os.path.join(carpeta, f"{base}_{idx}{ext}")

                from api.client import normalizar_url
                url_norm = normalizar_url(url)
                with requests.get(url_norm, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(ruta_salida, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                exitos += 1
            except Exception as e:
                errores.append(f"{nombre}: {e}")

        def _finalizar():
            self.boton_descargar_ev.configure(state="normal")
            if errores:
                self.lbl_progreso_desc_bit.configure(text=f"⚠️ {exitos}/{total} descargados", text_color=STATUS["warning"]["text"])
                messagebox.showwarning("Descarga parcial",
                    f"Se descargaron {exitos} de {total}.\n\nErrores:\n" + "\n".join(errores))
            else:
                self.lbl_progreso_desc_bit.configure(text=f"✅ {exitos} archivos descargados", text_color=STATUS["success"]["text"])
                messagebox.showinfo("Descarga completa", f"✅ {exitos} archivos guardados en:\n{carpeta}")

        self.after(0, _finalizar)

    # ─── Grabación ────────────────────────────────────────────────────────────

    def _registrar_hotkeys(self):
        keyboard.add_hotkey("ctrl+k+l", self._toggle_grabacion)

    def destroy(self):
        if not self._cerrado:
            self._cerrado = True
            self._al_destruir(None)
        super().destroy()

    def _al_destruir(self, event):
        if getattr(event, "widget", self) is not self:
            return
        self._miniaturas.cerrar()
        # Señalar al hilo de polling que debe detenerse.
        # stop_event.set() despierta inmediatamente el stop_event.wait(5)
        # del worker, evitando que el hilo quede vivo hasta el próximo ciclo.
        self.stop_event.set()
        try:
            keyboard.remove_hotkey("ctrl+k+l")
        except Exception:
            pass
        if getattr(self, "grabador", None) and self.grabador.estado != "detenido":
            self._detener_grabacion()
        self._ocultar_indicador_rec()

    def _actualizar_botones_grabacion(self):
        estado = self.grabador.estado
        if estado == "detenido":
            self.boton_grabar.configure(
                text="\u25CF  Grabar pantalla  (Ctrl+K+L)",
                fg_color=STATUS["error"]["solid"], hover_color=STATUS["error"]["hover"],
                text_color="#FFFFFF", state="normal"
            )
            self.boton_detener.pack_forget()
        elif estado == "grabando":
            self.boton_grabar.configure(
                text="\u23F8  Pausar",
                fg_color=STATUS["warning"]["solid"], hover_color=STATUS["warning"]["hover"],
                text_color="#FFFFFF", state="normal"
            )
            self.boton_detener.configure(state="normal")
            self.boton_detener.pack(after=self.boton_grabar, pady=(0, 8), padx=16, fill="x")
        elif estado == "pausado":
            self.boton_grabar.configure(
                text="\u25B6  Reanudar",
                fg_color=STATUS["success"]["solid"], hover_color=PRIMARY_HOVER,
                text_color="#FFFFFF", state="normal"
            )
            self.boton_detener.configure(state="normal")
            self.boton_detener.pack(after=self.boton_grabar, pady=(0, 8), padx=16, fill="x")

    def _toggle_grabacion(self):
        if self.grabador.estado == "detenido":
            self._iniciar_grabacion()
        elif self.grabador.estado == "grabando":
            self._pausar_grabacion()
        elif self.grabador.estado == "pausado":
            self._reanudar_grabacion()

    def _iniciar_grabacion(self):
        con_audio = bool(self.switch_audio.get())
        self._grabacion_con_audio = con_audio
        self.grabador.iniciar(con_audio=con_audio)
        self.controlador.withdraw()
        self._mostrar_indicador_rec()
        self._actualizar_botones_grabacion()

    def _pausar_grabacion(self):
        self.grabador.pausar()
        if getattr(self, "indicador", None):
            # Cambiar dot a ámbar y texto del botón a ▶️ (indica "click para reanudar")
            self.lbl_dot.configure(text="⏸️", text_color=STATUS["warning"]["text"])
            self.btn_pausa_float.configure(
                text="▶️  Reanudar", 
                fg_color=STATUS["success"]["solid"], hover_color=PRIMARY_HOVER,
                width=85
            )
            # Cambiar fondo del panel y hotkey label
            self.lbl_hotkeys.configure(text="En Pausa — Ctrl+K+L para reanudar", text_color=STATUS["warning"]["text"])
            # Detener el cronómetro
            if getattr(self, "_timer_id_rec", None):
                self.after_cancel(self._timer_id_rec)
                self._timer_id_rec = None
        self._actualizar_botones_grabacion()

    def _reanudar_grabacion(self):
        self.grabador.reanudar()
        if getattr(self, "indicador", None):
            # Restaurar estado visual a "Grabando"
            self.lbl_dot.configure(text="🔴", text_color=STATUS["error"]["text"])
            self.btn_pausa_float.configure(
                text="⏸️",
                fg_color=STATUS["warning"]["solid"], hover_color=STATUS["warning"]["hover"],
                width=35
            )
            self.lbl_hotkeys.configure(
                text="Pausar/Reanudar: Ctrl+K+L | Detener: Ctrl+F8",
                text_color=TEXT_MUTED
            )
            # Reanudar el cronómetro
            self._actualizar_crono_rec()
        self._actualizar_botones_grabacion()

    def _detener_grabacion(self):
        # Ocultar el indicador de inmediato
        self._ocultar_indicador_rec()
        self.controlador.deiconify()
        self.controlador.lift()
        self.boton_grabar.configure(state="disabled", text="Procesando video…")
        self.boton_detener.configure(state="disabled")

        # Ejecutar FFmpeg (unión de video/audio) en un hilo para no congelar la UI
        def procesar_video():
            ruta_final = self.grabador.detener()
            if ruta_final and os.path.exists(ruta_final):
                self.after(0, self._adjuntar_video_grabado, ruta_final)
            else:
                self.after(0, self._actualizar_botones_grabacion)

        import threading
        threading.Thread(target=procesar_video, daemon=True).start()

    def _adjuntar_video_grabado(self, ruta_final: str):
        """Persiste el video y lo sincroniza cuando exista conexión."""
        self._actualizar_botones_grabacion()
        self._registrar_evidencia_local_bitacora(
            ruta_final,
            con_audio=self._grabacion_con_audio,
            origen_generado=True,
        )

    def _mostrar_indicador_rec(self):
        self._segundos_grabacion = 0
        self._timer_id_rec = None

        import keyboard
        try:
            keyboard.add_hotkey("ctrl+k+l", lambda: self.after(0, self._toggle_grabacion))
            keyboard.add_hotkey("ctrl+f8",  lambda: self.after(0, self._detener_grabacion))
        except Exception as e:
            print(f"[bitacoras] Error al registrar hotkeys: {e}")

        self.indicador = ctk.CTkToplevel(self.controlador)
        self.indicador.overrideredirect(True)
        self.indicador.attributes("-topmost", True)
        self.indicador.configure(fg_color=SURFACE)
        
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.indicador.winfo_id())
            # 0x00000011 = WDA_EXCLUDEFROMCAPTURE (solo Windows)
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
        except Exception:
            pass
        ancho, alto = 260, 90
        x = self.indicador.winfo_screenwidth() - ancho - 40
        self.indicador.geometry(f"{ancho}x{alto}+{x}+40")

        self.indicador.grid_columnconfigure(1, weight=1)

        self.lbl_dot = IconLabel(self.indicador, text="🔴", text_color=STATUS["error"]["text"], font=get_font(size=14))
        self.lbl_dot.grid(row=0, column=0, padx=(15, 5), pady=(15, 0))

        self.lbl_crono = IconLabel(self.indicador, text="00:00", text_color=TEXT_PRIMARY,
                                       font=get_font(size=16, weight="bold", family="Consolas"))
        self.lbl_crono.grid(row=0, column=1, sticky="w", pady=(15, 0))

        self.btn_pausa_float = IconButton(
            self.indicador, text="⏸️", width=35, height=30,
            fg_color=STATUS["warning"]["solid"], hover_color=STATUS["warning"]["hover"],
            command=self._toggle_grabacion
        )
        self.btn_pausa_float.grid(row=0, column=2, padx=5, pady=(15, 0))

        self.btn_stop_float = IconButton(
            self.indicador, text="⏹️", width=35, height=30,
            fg_color=STATUS["error"]["solid"], hover_color=STATUS["error"]["hover"],
            command=self._detener_grabacion
        )
        self.btn_stop_float.grid(row=0, column=3, padx=(0, 15), pady=(15, 0))

        self.lbl_hotkeys = IconLabel(
            self.indicador,
            text="Pausar/Reanudar: Ctrl+K+L | Detener: Ctrl+F8",
            text_color=TEXT_MUTED, font=get_font(size=11)
        )
        self.lbl_hotkeys.grid(row=1, column=0, columnspan=4, pady=(6, 10))

        self._actualizar_crono_rec()

    def _actualizar_crono_rec(self):
        if getattr(self, "indicador", None) and self.grabador.estado == "grabando":
            mins, secs = divmod(self._segundos_grabacion, 60)
            self.lbl_crono.configure(text=f"{mins:02d}:{secs:02d}")
            self._segundos_grabacion += 1
            self._timer_id_rec = self.after(1000, self._actualizar_crono_rec)

    def _ocultar_indicador_rec(self):
        import keyboard
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if getattr(self, "_timer_id_rec", None):
            self.after_cancel(self._timer_id_rec)
            self._timer_id_rec = None
        if getattr(self, "indicador", None):
            try:
                self.indicador.destroy()
            except Exception:
                pass
            self.indicador = None

    # ─── Adjuntar / Subir evidencia ───────────────────────────────────────────

    def _on_adjuntar(self):
        rutas = filedialog.askopenfilenames(
            title="Selecciona las evidencias",
            filetypes=[("Todos los archivos", "*.*")],
        )
        if not rutas:
            return
        agregadas = 0
        for ruta in rutas:
            agregadas += bool(self._registrar_evidencia_local_bitacora(
                ruta, con_audio=False, iniciar_sync=False, refrescar=False
            ))
        if agregadas:
            self._refrescar_lista_evidencias()
            self._actualizar_boton_evidencia_de_fila_activa()
            self._solicitar_sincronizacion_evidencias()

    def _on_subir_evidencia(self):
        pendientes = obtener_evidencias_bitacora_pendientes(
            bitacora_local_id=self._bitacora_local_id_panel,
            b_id=self._b_id_panel or None,
        )
        if not pendientes:
            messagebox.showwarning("Atención", "No has grabado ni adjuntado ninguna evidencia.")
            return

        self.boton_subir.configure(state="disabled", text="Sincronizando…")
        self.label_archivo.configure(text="La evidencia está guardada localmente; sincronizando…")
        self._solicitar_sincronizacion_evidencias()

    def _solicitar_sincronizacion_evidencias(self):
        """Ejecuta un único worker para toda la cola local de evidencias."""
        if self._cerrado:
            return
        pendientes = obtener_evidencias_bitacora_pendientes()
        if not any(item.get("vinculada") or item.get("codigo") for item in pendientes):
            return
        if not self._lock_sync_evidencias.acquire(blocking=False):
            return
        self.after(0, self._actualizar_indicador_sync, "syncing")

        def _worker():
            vinculadas: dict[str, dict] = {}
            cantidad_subida = 0
            try:
                # Releer bajo el lock: otro worker pudo vaciar la cola después
                # de la comprobación inicial y antes de adquirirlo.
                pendientes = obtener_evidencias_bitacora_pendientes()
                for item in pendientes:
                    codigo = (item.get("codigo") or "").strip().upper()
                    ruta = item.get("ruta_local", "")
                    if not item.get("vinculada") and not codigo:
                        # El padre también está offline: la cola esperará a que
                        # _sincronizar_pendientes le asigne su código remoto.
                        continue
                    if not item.get("vinculada") and (not ruta or not os.path.isfile(ruta)):
                        print(f"[bitacoras-evidencia] Archivo local no encontrado: {ruta}")
                        continue

                    if item.get("vinculada"):
                        url = item.get("evidencia_url", "")
                    else:
                        url = item.get("evidencia_url", "")
                        if not url:
                            url, error = subir_archivo_con_destino(
                                ruta,
                                prefijo_nube=item.get("carpeta_destino") or None,
                            )
                            if not url:
                                print(f"[bitacoras-evidencia] No se pudo subir {ruta}: {error}")
                                continue
                            actualizar_url_evidencia_bitacora(item["id"], url)

                        data, error = adjuntar_evidencia_por_codigo(
                            codigo, url, bool(item.get("con_audio"))
                        )
                        if error:
                            print(f"[bitacoras-evidencia] No se pudo vincular {ruta}: {error}")
                            continue
                        marcar_evidencia_bitacora_vinculada(item["id"])
                        item["vinculada"] = 1
                        if isinstance(data, dict):
                            vinculadas[codigo] = data
                        cantidad_subida += 1

                    # Eliminar sólo la copia administrada por AuditFlow y sólo
                    # después de confirmar el vínculo remoto. Si falla el borrado,
                    # queda marcada como vinculada y el siguiente ciclo sólo
                    # reintenta la limpieza, no vuelve a adjuntarla.
                    try:
                        if ruta and os.path.exists(ruta):
                            os.remove(ruta)
                        eliminar_evidencia_bitacora_pendiente(item["id"])
                    except OSError as e:
                        print(f"[bitacoras-evidencia] No se pudo limpiar {ruta}: {e}")
            except Exception as e:
                print(f"[bitacoras-evidencia] Error de sincronización: {e}")
            finally:
                self._lock_sync_evidencias.release()
                if not self._cerrado:
                    self.after(0, self._finalizar_sincronizacion_evidencias, vinculadas, cantidad_subida)

        threading.Thread(target=_worker, daemon=True, name="BitacorasEvidenciasSync").start()

    def _finalizar_sincronizacion_evidencias(self, vinculadas: dict, cantidad_subida: int):
        if self._cerrado:
            return
        for codigo, data in vinculadas.items():
            self._actualizar_evidencias_fila(codigo, data.get("evidencias", []), refrescar_panel=False)

        pendientes = obtener_evidencias_bitacora_pendientes(
            bitacora_local_id=self._bitacora_local_id_panel,
            b_id=self._b_id_panel or None,
        )
        pendientes_totales = obtener_evidencias_bitacora_pendientes()
        self._actualizar_indicador_sync("offline" if pendientes_totales else "ok")
        self._refrescar_lista_evidencias()
        self._actualizar_boton_evidencia_de_fila_activa()
        if cantidad_subida:
            self._mostrar_toast(f"✅ {cantidad_subida} evidencia(s) sincronizada(s)")
        if pendientes:
            sin_codigo = any(not item.get("codigo") for item in pendientes)
            texto = (
                "Guardada localmente; esperando a que se sincronice la bitácora"
                if sin_codigo
                else f"Guardadas localmente: {len(pendientes)} · reintento automático pendiente"
            )
            self.label_archivo.configure(text=texto)
        elif not cantidad_subida:
            self.label_archivo.configure(text="Sin evidencia adjunta")
        if self.boton_subir.winfo_exists():
            self.boton_subir.configure(state="normal", text="✓  Subir y Vincular")
        if cantidad_subida:
            self.ultimo_hash_bd = None

    # ─── Navegación ───────────────────────────────────────────────────────────

    def _on_volver(self):
        self._ocultar_indicador_rec()
        self.stop_event.set()
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)
