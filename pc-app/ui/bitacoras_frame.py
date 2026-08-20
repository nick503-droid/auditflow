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
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime
from PIL import Image
import io
import keyboard
import os
import threading
import time
import webbrowser

from api.client import (
    obtener_bitacoras_por_fecha,
    adjuntar_evidencia_por_codigo,
    obtener_evidencias_bitacora,
    subir_archivo,
    crear_bitacora,
    actualizar_bitacora,
    obtener_restaurantes,
    obtener_usuarios,
)
from core.recorder import GrabadorPantalla, es_archivo_grabado
from db.local_db import (
    inicializar_db,
    guardar_bitacora_local,
    marcar_bitacora_sincronizada,
    obtener_bitacoras_pendientes,
)

# ─── Paleta de colores ────────────────────────────────────────────────────────
URGENCIA_COLORES = {
    "low":      {"bg": "#1e3a2e", "fg": "#4ade80", "icono": "🟢"},
    "medium":   {"bg": "#3a2e10", "fg": "#facc15", "icono": "🟡"},
    "critical": {"bg": "#3a1010", "fg": "#f87171", "icono": "🔴"},
}
URGENCIA_CICLO = ["low", "medium", "critical"]

COLOR_FILA_PAR         = "#1a1a2e"
COLOR_FILA_IMPAR       = "#16213e"
COLOR_FILA_CRITICA     = "#2a1010"
COLOR_CODIGO_BG        = "#1e3a5e"
COLOR_CODIGO_FG        = "#93c5fd"
COLOR_BOTON_EV_OK      = "#166534"
COLOR_BOTON_EV_ADD     = "#1d4ed8"
COLOR_SYNC_OK          = "#4ade80"
COLOR_SYNC_OFFLINE     = "#facc15"
COLOR_SYNC_WORKING     = "#60a5fa"

ANCHO_REST   = 160
ANCHO_VIG    = 130
ANCHO_HORA   = 70
ANCHO_URG    = 30   # solo el ícono
ANCHO_COD    = 80
ANCHO_EV_BTN = 110

DESC_MAXLEN  = 45   # caracteres antes de truncar con "…"
DEBOUNCE_MS  = 1500


class BitacorasFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, usuario, fecha=None, **kwargs):
        super().__init__(master, **kwargs)
        self.controlador = controlador
        self.usuario_activo = usuario
        self.fecha_actual = fecha if fecha else datetime.now().strftime("%Y-%m-%d")

        self.lock = threading.Lock()
        self.editando = False
        self.hilo_polling_activo = True
        self.ultimo_hash_bd = None

        # Evidencia
        self.ruta_evidencia = None
        self.grabador = GrabadorPantalla()
        self.grabando = False
        self.indicador = None
        self._codigo_panel_activo = ""   # código de la bitácora en el panel lateral

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
        self.bind("<Destroy>", self._al_destruir)

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

        ctk.CTkLabel(
            self.top_bar,
            text=f"📋  Bitácoras: {self.fecha_actual}",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            self.top_bar, text="Vigilante a cargo:", font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(20, 5))

        nombres_usuarios = list(self.mapa_usuarios.keys()) if self.mapa_usuarios else [self.usuario_activo["nombre"]]
        self.combo_vigilante = ctk.CTkComboBox(self.top_bar, values=nombres_usuarios, width=160)
        self.combo_vigilante.set(self.usuario_activo["nombre"])
        self.combo_vigilante.pack(side="left", padx=5)

        # Indicador de conexión
        self.label_sync = ctk.CTkLabel(
            self.top_bar, text="⬤ Conectado",
            text_color=COLOR_SYNC_OK, font=ctk.CTkFont(size=11),
        )
        self.label_sync.pack(side="left", padx=(16, 0))

        ctk.CTkButton(
            self.top_bar, text="← Volver", width=80, fg_color="gray40", hover_color="gray30",
            command=self._on_volver,
        ).pack(side="right", padx=10)

        ctk.CTkButton(
            self.top_bar, text="➕ Nueva fila", width=110,
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._agregar_fila_vacia,
        ).pack(side="right", padx=5)

    def _actualizar_indicador_sync(self, estado: str, pendientes: int = 0):
        """estado: 'ok' | 'offline' | 'syncing'"""
        if estado == "ok":
            self.label_sync.configure(text="⬤ Sincronizado", text_color=COLOR_SYNC_OK)
        elif estado == "offline":
            self.label_sync.configure(text="⬤ Sin conexión — guardando local", text_color=COLOR_SYNC_OFFLINE)
        elif estado == "syncing":
            self.label_sync.configure(text=f"↻ Sincronizando {pendientes}…", text_color=COLOR_SYNC_WORKING)

    # ─── Encabezado de columnas ───────────────────────────────────────────────

    def _construir_encabezado_columnas(self):
        """Fila fija de etiquetas que sirve de cabecera visual."""
        hdr = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=0)
        hdr.grid(row=1, column=0, sticky="ew", padx=12, pady=0)

        headers = [
            ("Urg", ANCHO_URG + 4),
            ("Restaurante", ANCHO_REST),
            ("Vigilante", ANCHO_VIG),
            ("Hora", ANCHO_HORA),
            ("Descripción", 0),        # expansible
            ("Código", ANCHO_COD),
            ("Evidencia", ANCHO_EV_BTN),
        ]
        for texto, ancho in headers:
            kw = {"width": ancho} if ancho else {}
            ctk.CTkLabel(
                hdr, text=texto, font=ctk.CTkFont(size=10, weight="bold"),
                text_color="gray60", **kw,
            ).pack(side="left", padx=4, pady=4)

    # ─── Área de filas (scroll) ───────────────────────────────────────────────

    def _construir_area_filas(self):
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", label_text="")
        self.scroll_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(2, 10))
        self.scroll_frame.grid_columnconfigure(0, weight=1)

    # ─── Tarjeta de UNA línea ─────────────────────────────────────────────────

    def _construir_tarjeta(self, idx: int):
        """
        Construye (o reconstruye) la tarjeta de una sola línea horizontal
        para la fila `idx`.
        """
        fila = self.filas[idx]

        old_card = fila.get("_card_frame")
        if old_card and old_card.winfo_exists():
            old_card.destroy()

        urgencia = fila.get("urgencia", "low")
        if urgencia == "critical":
            bg_color = COLOR_FILA_CRITICA
        else:
            bg_color = COLOR_FILA_PAR if idx % 2 == 0 else COLOR_FILA_IMPAR

        card = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=bg_color,
            corner_radius=6,
        )
        card.grid(row=idx, column=0, sticky="ew", pady=1, padx=0)
        card.grid_columnconfigure(4, weight=1)   # col 4 = descripción, se expande
        fila["_card_frame"] = card

        # Col 0 — Badge de urgencia (solo ícono, click para ciclar)
        urg_data = URGENCIA_COLORES.get(urgencia, URGENCIA_COLORES["low"])
        urg_btn = ctk.CTkButton(
            card,
            text=urg_data["icono"],
            width=ANCHO_URG, height=30,
            fg_color="transparent",
            hover_color=urg_data["bg"],
            font=ctk.CTkFont(size=14),
            command=lambda i=idx: self._ciclar_urgencia(i),
        )
        urg_btn.grid(row=0, column=0, padx=(4, 2), pady=3)

        # Col 1 — Restaurante
        nombres_rests = list(self.mapa_restaurantes.keys()) if self.mapa_restaurantes else ["—"]
        rest_val = fila.get("restaurante", "")
        if rest_val not in nombres_rests:
            nombres_rests = [""] + nombres_rests

        om_rest = ctk.CTkOptionMenu(
            card,
            values=nombres_rests,
            width=ANCHO_REST, height=28,
            command=lambda v, i=idx: self._on_campo_inmediato(i, "restaurante", v),
            font=ctk.CTkFont(size=11),
            dynamic_resizing=False,
        )
        om_rest.set(rest_val if rest_val else "— Restaurante —")
        om_rest.grid(row=0, column=1, padx=2, pady=3)

        # Col 2 — Vigilante
        nombres_usrs = list(self.mapa_usuarios.keys()) if self.mapa_usuarios else [self.usuario_activo["nombre"]]
        vig_val = fila.get("vigilante", self.combo_vigilante.get())
        if vig_val not in nombres_usrs:
            vig_val = nombres_usrs[0]

        om_vig = ctk.CTkOptionMenu(
            card,
            values=nombres_usrs,
            width=ANCHO_VIG, height=28,
            command=lambda v, i=idx: self._on_campo_inmediato(i, "vigilante", v),
            font=ctk.CTkFont(size=11),
            dynamic_resizing=False,
        )
        om_vig.set(vig_val)
        om_vig.grid(row=0, column=2, padx=2, pady=3)

        # Col 3 — Hora (texto libre, NO autogenerada)
        hora_entry = ctk.CTkEntry(card, placeholder_text="HH:MM", width=ANCHO_HORA, height=28,
                                  font=ctk.CTkFont(size=11))
        hora_val = fila.get("hora", "")
        if hora_val:
            hora_entry.insert(0, hora_val)
        hora_entry.grid(row=0, column=3, padx=2, pady=3)
        hora_entry.bind("<KeyRelease>", lambda e, i=idx, w=hora_entry: self._on_keyrelease(i, "hora", w))
        hora_entry.bind("<FocusIn>",  lambda e: self._marcar_editando(True))
        hora_entry.bind("<FocusOut>", lambda e: self._marcar_editando(False))

        # Col 4 — Descripción truncada (expansible)
        desc_val = fila.get("descripcion", "")
        desc_truncada = (desc_val[:DESC_MAXLEN] + "…") if len(desc_val) > DESC_MAXLEN else desc_val

        desc_entry = ctk.CTkEntry(
            card,
            placeholder_text="Descripción…",
            height=28,
            font=ctk.CTkFont(size=11),
        )
        if desc_val:
            desc_entry.insert(0, desc_truncada)
        desc_entry.grid(row=0, column=4, padx=2, pady=3, sticky="ew")
        desc_entry.bind("<KeyRelease>", lambda e, i=idx, w=desc_entry: self._on_keyrelease(i, "descripcion", w))
        desc_entry.bind("<Double-Button-1>", lambda e, i=idx: self._expandir_descripcion(i))
        desc_entry.bind("<FocusIn>",  lambda e: self._marcar_editando(True))
        desc_entry.bind("<FocusOut>", lambda e: self._marcar_editando(False))

        # Col 5 — Badge de código (solo lectura)
        codigo = fila.get("codigo", "")
        if codigo:
            cod_btn = ctk.CTkButton(
                card,
                text=codigo,
                width=ANCHO_COD, height=28,
                fg_color=COLOR_CODIGO_BG,
                text_color=COLOR_CODIGO_FG,
                hover_color="#1e4a7e",
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                corner_radius=4,
                command=lambda c=codigo: self._copiar_codigo(c),
            )
        else:
            cod_btn = ctk.CTkLabel(
                card, text="—", width=ANCHO_COD, height=28,
                text_color="gray40", font=ctk.CTkFont(size=11),
            )
        cod_btn.grid(row=0, column=5, padx=2, pady=3)

        # Col 6 — Botón de evidencia
        evidencias = fila.get("evidencias", [])
        tiene_ev = len(evidencias) > 0 or fila.get("evidencia") == "Sí"
        if tiene_ev:
            n = len(evidencias) if evidencias else 1
            ev_text  = f"✅ {n} ev."
            ev_color = COLOR_BOTON_EV_OK
            ev_hover = "#14532d"
        else:
            ev_text  = "📹 Agregar"
            ev_color = COLOR_BOTON_EV_ADD
            ev_hover = "#1e40af"

        ev_btn = ctk.CTkButton(
            card,
            text=ev_text,
            width=ANCHO_EV_BTN, height=28,
            fg_color=ev_color, hover_color=ev_hover,
            font=ctk.CTkFont(size=11),
            command=lambda i=idx: self._on_boton_evidencia(i),
        )
        ev_btn.grid(row=0, column=6, padx=(2, 6), pady=3)

        fila["_widgets"] = {
            "restaurante": om_rest,
            "vigilante":   om_vig,
            "hora":        hora_entry,
            "descripcion": desc_entry,
            "urgencia":    urg_btn,
            "codigo":      cod_btn,
            "evidencia":   ev_btn,
        }

    def _reconstruir_tarjeta(self, idx: int):
        self._construir_tarjeta(idx)

    # ─── Expandir descripción en popup ────────────────────────────────────────

    def _expandir_descripcion(self, idx: int):
        """Abre un popup con un TextBox editable para la descripción completa."""
        fila = self.filas[idx]
        desc_actual = fila.get("descripcion", "")

        popup = ctk.CTkToplevel(self)
        popup.title("Editar descripción")
        popup.geometry("480x200")
        popup.grab_set()
        popup.resizable(False, False)

        ctk.CTkLabel(
            popup, text="Descripción completa:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(padx=16, pady=(14, 4), anchor="w")

        txt = ctk.CTkTextbox(popup, height=90, font=ctk.CTkFont(size=12), wrap="word")
        txt.pack(padx=16, pady=0, fill="x")
        txt.insert("1.0", desc_actual)
        txt.focus()

        def _confirmar():
            nuevo = txt.get("1.0", "end").strip()
            fila["descripcion"] = nuevo
            popup.destroy()
            # Actualizar widget inline con texto truncado
            w = fila.get("_widgets", {}).get("descripcion")
            if w and w.winfo_exists():
                w.delete(0, "end")
                truncada = (nuevo[:DESC_MAXLEN] + "…") if len(nuevo) > DESC_MAXLEN else nuevo
                w.insert(0, truncada)
            self._programar_guardado(idx)

        ctk.CTkButton(
            popup, text="✔ Confirmar", fg_color="#166534", hover_color="#14532d",
            command=_confirmar,
        ).pack(padx=16, pady=12, side="right")

        ctk.CTkButton(
            popup, text="Cancelar", fg_color="gray40", hover_color="gray30",
            command=popup.destroy,
        ).pack(padx=4, pady=12, side="right")

    # ─── Agregar fila vacía ───────────────────────────────────────────────────

    def _agregar_fila_vacia(self):
        vigilante_actual = self.combo_vigilante.get()
        nueva_fila = {
            "b_id": "",
            "local_id": None,
            "codigo": "",
            "hora": "",
            "restaurante": "",
            "vigilante": vigilante_actual,
            "descripcion": "",
            "urgencia": "low",
            "evidencias": [],
            "evidencia": "",   # campo legacy para compatibilidad con el reconciliador
            "_debounce_id": None,
        }
        self.filas.append(nueva_fila)
        idx = len(self.filas) - 1
        self._construir_tarjeta(idx)
        self.after(50, lambda: self.scroll_frame._parent_canvas.yview_moveto(1.0))

    # ─── Callbacks de campo ───────────────────────────────────────────────────

    def _marcar_editando(self, estado: bool):
        with self.lock:
            self.editando = estado

    def _on_campo_inmediato(self, idx: int, campo: str, valor: str):
        """Para OptionMenus (no tienen KeyRelease) — cambio registrado de inmediato."""
        self.filas[idx][campo] = valor
        self._programar_guardado(idx)

    def _on_keyrelease(self, idx: int, campo: str, widget):
        """Cada pulsación de tecla reinicia el debounce."""
        self.filas[idx][campo] = widget.get()
        self._programar_guardado(idx)

    def _ciclar_urgencia(self, idx: int):
        urg_actual = self.filas[idx].get("urgencia", "low")
        pos_actual = URGENCIA_CICLO.index(urg_actual) if urg_actual in URGENCIA_CICLO else 0
        self.filas[idx]["urgencia"] = URGENCIA_CICLO[(pos_actual + 1) % 3]
        self._programar_guardado(idx)
        self._reconstruir_tarjeta(idx)

    def _copiar_codigo(self, codigo: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(codigo)
            self.update()
            self._mostrar_toast(f"✅  Código {codigo} copiado")
        except Exception:
            pass

    def _mostrar_toast(self, mensaje: str):
        toast = ctk.CTkLabel(
            self.top_bar, text=mensaje,
            fg_color="#1e3a2e", text_color="#4ade80",
            corner_radius=6, font=ctk.CTkFont(size=11),
            padx=10, pady=4,
        )
        toast.pack(side="left", padx=10)
        self.after(2500, toast.destroy)

    # ─── Debounce + guardado ──────────────────────────────────────────────────

    def _programar_guardado(self, idx: int):
        """Cancela el timer anterior y programa uno nuevo a 1.5 s."""
        timer_id = self.filas[idx].get("_debounce_id")
        if timer_id:
            self.after_cancel(timer_id)
        self.filas[idx]["_debounce_id"] = self.after(DEBOUNCE_MS, lambda: self._procesar_modificacion(idx))

    def _procesar_modificacion(self, idx: int):
        """
        1) Guarda en SQLite local (offline-first, siempre funciona).
        2) Intenta sincronizar con el backend en un hilo daemon.
        """
        if idx >= len(self.filas):
            return
        fila = self.filas[idx]
        fila["_debounce_id"] = None

        rest_nombre = fila.get("restaurante", "").strip()
        rest_id = self.mapa_restaurantes.get(rest_nombre)
        if not rest_id:
            return   # sin restaurante, ni siquiera guardamos local

        vig_nombre = fila.get("vigilante", "").strip()
        usr_id = self.mapa_usuarios.get(vig_nombre, self.usuario_activo["id"])

        datos_locales = {
            "local_id":      fila.get("local_id"),
            "b_id":          fila.get("b_id", ""),
            "codigo":        fila.get("codigo", ""),
            "restaurante_id": rest_id,
            "usuario_id":    usr_id,
            "descripcion":   fila.get("descripcion", ""),
            "fecha":         self.fecha_actual,
            "hora":          fila.get("hora", ""),
            "urgencia":      fila.get("urgencia", "low"),
        }

        # Paso 1: SQLite local (rápido, en hilo principal)
        local_id = guardar_bitacora_local(datos_locales)
        fila["local_id"] = local_id

        # Paso 2: intentar backend en hilo daemon (no bloquea UI)
        threading.Thread(
            target=self._subir_al_servidor,
            args=(idx, local_id, datos_locales),
            daemon=True,
        ).start()

    def _subir_al_servidor(self, idx: int, local_id: int, datos: dict):
        """Hilo daemon: crea o actualiza en backend y actualiza el SQLite."""
        try:
            dto = {
                "restaurante_id": datos["restaurante_id"],
                "usuario_id":     datos["usuario_id"],
                "descripcion":    datos["descripcion"],
                "fecha":          datos["fecha"],
                "hora":           datos["hora"],
                "urgencia":       datos["urgencia"],
            }
            b_id   = datos.get("b_id", "")
            codigo = datos.get("codigo", "")

            if not b_id:
                # Solo crear si hay algún contenido además de restaurante
                if not (datos.get("hora") or datos.get("descripcion")):
                    return
                resultado = crear_bitacora(dto)
                if resultado:
                    b_id   = resultado.get("id", "")
                    codigo = resultado.get("codigo", "")
                    self.after(0, self._aplicar_resultado_creacion, idx, b_id, codigo, local_id)
                else:
                    self.after(0, self._actualizar_indicador_sync, "offline")
                    return
            else:
                resultado = actualizar_bitacora(b_id, dto)
                if resultado is None:
                    self.after(0, self._actualizar_indicador_sync, "offline")
                    return

            marcar_bitacora_sincronizada(local_id, b_id, codigo)
            self.after(0, self._actualizar_indicador_sync, "ok")
            self.ultimo_hash_bd = None

        except Exception as e:
            print(f"[subir_al_servidor] Error: {e}")
            self.after(0, self._actualizar_indicador_sync, "offline")

    def _aplicar_resultado_creacion(self, idx: int, b_id: str, codigo: str, local_id: int):
        """Llamado en el hilo principal tras crear exitosamente en el backend."""
        if idx >= len(self.filas):
            return
        self.filas[idx]["b_id"]   = b_id
        self.filas[idx]["codigo"] = codigo
        self.ultimo_hash_bd = None
        self._reconstruir_tarjeta(idx)

    # ─── Lógica del botón Evidencia ───────────────────────────────────────────

    def _on_boton_evidencia(self, idx: int):
        fila = self.filas[idx]
        rest_nombre = fila.get("restaurante", "").strip()

        if not rest_nombre or rest_nombre not in self.mapa_restaurantes:
            messagebox.showwarning(
                "Restaurante requerido",
                "Selecciona un restaurante antes de agregar evidencia.\n"
                "El código se genera al crear el registro en el servidor.",
            )
            return

        # Si la fila no tiene ID → crear en backend ahora mismo
        if not fila.get("b_id"):
            vig_nombre = fila.get("vigilante", self.usuario_activo["nombre"])
            rest_id = self.mapa_restaurantes[rest_nombre]
            usr_id  = self.mapa_usuarios.get(vig_nombre, self.usuario_activo["id"])

            dto = {
                "restaurante_id": rest_id,
                "usuario_id":     usr_id,
                "fecha":          self.fecha_actual,
                "descripcion":    fila.get("descripcion", ""),
                "hora":           fila.get("hora", ""),
                "urgencia":       fila.get("urgencia", "low"),
            }
            resultado = crear_bitacora(dto)
            if not resultado:
                messagebox.showerror("Error", "No se pudo crear el registro en el servidor.")
                return

            fila["b_id"]   = resultado.get("id", "")
            fila["codigo"] = resultado.get("codigo", "")
            self.ultimo_hash_bd = None
            self._reconstruir_tarjeta(idx)

        # Mostrar panel de evidencia
        evidencias = fila.get("evidencias", [])
        self._mostrar_panel_evidencia(fila["codigo"], evidencias)

    # ─── Carga inicial ────────────────────────────────────────────────────────

    def _carga_inicial(self):
        """Lanza una carga inmediata en hilo daemon antes del primer ciclo de polling."""
        def _worker():
            try:
                bitacoras = obtener_bitacoras_por_fecha(self.fecha_actual)
                if bitacoras is not None:
                    self.after(0, self._reconciliar_con_datos, bitacoras)
                else:
                    # Sin conexión al arrancar — agregar fila vacía para empezar
                    self.after(0, self._agregar_fila_vacia)
            except Exception as e:
                print(f"[carga_inicial] Error: {e}")
                self.after(0, self._agregar_fila_vacia)

        threading.Thread(target=_worker, daemon=True).start()

    # ─── Polling ──────────────────────────────────────────────────────────────

    def _iniciar_polling(self):
        self.hilo_polling_activo = True
        threading.Thread(target=self._polling_worker, daemon=True).start()

    def _polling_worker(self):
        while self.hilo_polling_activo:
            # Intentar sincronizar pendientes offline antes de consultar
            try:
                self._sincronizar_pendientes()
            except Exception as e:
                print(f"[sync_pendientes] Error: {e}")

            try:
                bitacoras = obtener_bitacoras_por_fecha(self.fecha_actual)
                if bitacoras is not None:
                    self.after(0, self._reconciliar_con_datos, bitacoras)
                    self.after(0, self._actualizar_indicador_sync, "ok")
                else:
                    self.after(0, self._actualizar_indicador_sync, "offline")
            except Exception as e:
                print(f"[polling] Error: {e}")
                self.after(0, self._actualizar_indicador_sync, "offline")

            time.sleep(5)

    def _sincronizar_pendientes(self):
        """Sube registros offline a medida que la conexión se restablece."""
        pendientes = obtener_bitacoras_pendientes()
        if not pendientes:
            return

        self.after(0, self._actualizar_indicador_sync, "syncing", len(pendientes))

        for p in pendientes:
            try:
                dto = {
                    "restaurante_id": p["restaurante_id"],
                    "usuario_id":     p["usuario_id"],
                    "descripcion":    p["descripcion"],
                    "fecha":          p["fecha"],
                    "hora":           p["hora"],
                    "urgencia":       p["urgencia"],
                }
                b_id   = p["b_id"]
                codigo = p["codigo"]

                if not b_id:
                    resultado = crear_bitacora(dto)
                    if resultado:
                        b_id   = resultado.get("id", "")
                        codigo = resultado.get("codigo", "")
                else:
                    resultado = actualizar_bitacora(b_id, dto)

                if resultado is not None:
                    marcar_bitacora_sincronizada(p["id"], b_id, codigo)
                    # Actualizar fila en memoria si existe
                    self.after(0, self._actualizar_fila_por_local_id, p["id"], b_id, codigo)
            except Exception as e:
                print(f"[sync_pendientes] Fila {p['id']}: {e}")
                break  # parar si hay error de red, reintentará en 5s

    def _actualizar_fila_por_local_id(self, local_id: int, b_id: str, codigo: str):
        for i, f in enumerate(self.filas):
            if f.get("local_id") == local_id:
                f["b_id"]   = b_id
                f["codigo"] = codigo
                self._reconstruir_tarjeta(i)
                break

    def _reconciliar_con_datos(self, bitacoras: list):
        """
        Sincroniza datos del backend con `self.filas` sin pisar borradores locales.
        """
        with self.lock:
            if self.editando:
                return

            nuevo_hash = hash(str(bitacoras))
            if self.ultimo_hash_bd == nuevo_hash:
                if not self.filas:
                    self.after(0, self._agregar_fila_vacia)
                return
            self.ultimo_hash_bd = nuevo_hash

        ids_bd    = {b.get("id"): b for b in bitacoras}
        ids_local = {f["b_id"]: i for i, f in enumerate(self.filas) if f.get("b_id")}

        for b_id, b in ids_bd.items():
            rest  = b.get("restaurante", {}).get("nombre", "") if isinstance(b.get("restaurante"), dict) else ""
            vig   = b.get("usuario", {}).get("nombre", "") if isinstance(b.get("usuario"), dict) else ""
            evids = b.get("evidencias", [])
            datos_nuevos = {
                "b_id":        b_id,
                "codigo":      b.get("codigo", ""),
                "hora":        b.get("hora", ""),
                "restaurante": rest,
                "vigilante":   vig,
                "descripcion": b.get("descripcion", ""),
                "urgencia":    b.get("urgencia", "low"),
                "evidencias":  evids,
                "evidencia":   "Sí" if (evids or b.get("evidencia_url")) else "",
            }
            if b_id in ids_local:
                local_idx = ids_local[b_id]
                self.filas[local_idx].update(datos_nuevos)
                self._reconstruir_tarjeta(local_idx)
            else:
                datos_nuevos["local_id"]     = None
                datos_nuevos["_debounce_id"] = None
                self.filas.append(datos_nuevos)
                self._construir_tarjeta(len(self.filas) - 1)

        # Borradores locales: asegurar que tienen tarjeta
        for i, f in enumerate(self.filas):
            if not f.get("b_id") and not f.get("_card_frame"):
                self._construir_tarjeta(i)

        if not self.filas:
            self._agregar_fila_vacia()

    # ─── Panel lateral de evidencia ───────────────────────────────────────────

    def _construir_panel_evidencia(self):
        self.frame_evidencia = ctk.CTkFrame(self, width=290, fg_color="#16213e")
        self.frame_evidencia.grid_propagate(False)
        self.frame_evidencia.grid_columnconfigure(0, weight=1)

        # Encabezado
        header = ctk.CTkFrame(self.frame_evidencia, fg_color="#0f3460")
        header.pack(fill="x")

        self.label_panel_titulo = ctk.CTkLabel(
            header, text="🎥  Evidencias",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="white",
        )
        self.label_panel_titulo.pack(side="left", padx=12, pady=10)

        ctk.CTkButton(
            header, text="✕", width=30, height=30,
            fg_color="transparent", hover_color="#c0392b",
            command=self._ocultar_panel_evidencia,
        ).pack(side="right", padx=8, pady=6)

        # Código (solo lectura)
        ctk.CTkLabel(
            self.frame_evidencia, text="Código de bitácora",
            text_color="gray70", font=ctk.CTkFont(size=11),
        ).pack(pady=(14, 2), padx=16, anchor="w")

        frame_cod = ctk.CTkFrame(self.frame_evidencia, fg_color="transparent")
        frame_cod.pack(padx=16, fill="x", pady=(0, 2))

        self.label_codigo = ctk.CTkLabel(
            frame_cod,
            text="——————",
            font=ctk.CTkFont(family="Consolas", size=20, weight="bold"),
            fg_color=COLOR_CODIGO_BG,
            text_color=COLOR_CODIGO_FG,
            corner_radius=6,
            padx=12, pady=6,
        )
        self.label_codigo.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            frame_cod, text="📋", width=32, height=32,
            fg_color="transparent", hover_color=COLOR_CODIGO_BG,
            command=lambda: self._copiar_codigo(self._codigo_panel_activo),
        ).pack(side="left", padx=(6, 0))

        # ── Área de lista de evidencias existentes ────────────────────────
        ctk.CTkFrame(self.frame_evidencia, height=1, fg_color="gray25").pack(fill="x", padx=16, pady=10)

        ctk.CTkLabel(
            self.frame_evidencia, text="Evidencias vinculadas",
            text_color="gray70", font=ctk.CTkFont(size=11),
        ).pack(padx=16, anchor="w")

        self.frame_lista_ev = ctk.CTkScrollableFrame(self.frame_evidencia, height=120, fg_color="#0d1b2a")
        self.frame_lista_ev.pack(fill="x", padx=16, pady=(4, 0))

        # ── Agregar nueva evidencia ───────────────────────────────────────
        ctk.CTkFrame(self.frame_evidencia, height=1, fg_color="gray25").pack(fill="x", padx=16, pady=10)

        self.switch_audio = ctk.CTkSwitch(self.frame_evidencia, text="Grabar con audio")
        self.switch_audio.pack(pady=(0, 8), padx=16, anchor="w")
        self.switch_audio.deselect()

        self.boton_grabar = ctk.CTkButton(
            self.frame_evidencia,
            text="🔴 Grabar pantalla\n(Ctrl+K+L)",
            command=self._toggle_grabacion,
            fg_color="#7f1d1d", hover_color="#991b1b",
            font=ctk.CTkFont(size=12),
        )
        self.boton_grabar.pack(pady=(0, 5), padx=16, fill="x")

        self.boton_adjuntar = ctk.CTkButton(
            self.frame_evidencia,
            text="📎 Adjuntar archivo",
            command=self._on_adjuntar,
            fg_color="transparent", border_width=1, border_color="gray40",
            font=ctk.CTkFont(size=12),
        )
        self.boton_adjuntar.pack(pady=(0, 8), padx=16, fill="x")

        self.label_archivo = ctk.CTkLabel(
            self.frame_evidencia, text="Sin evidencia adjunta",
            text_color="gray50", font=ctk.CTkFont(size=10), wraplength=230,
        )
        self.label_archivo.pack(pady=(0, 8), padx=16)

        self.boton_subir = ctk.CTkButton(
            self.frame_evidencia,
            text="⬆️  Subir y Vincular",
            command=self._on_subir_evidencia,
            fg_color="#166534", hover_color="#14532d",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
        )
        self.boton_subir.pack(pady=(0, 14), padx=16, fill="x")

    def _ocultar_panel_evidencia(self):
        self.frame_evidencia.grid_remove()
        self.grid_columnconfigure(1, weight=0)
        self._codigo_panel_activo = ""

    def _mostrar_panel_evidencia(self, codigo: str, evidencias: list):
        self._codigo_panel_activo = codigo
        self.grid_columnconfigure(1, minsize=300, weight=0)
        self.frame_evidencia.grid(row=1, column=1, rowspan=2, sticky="ns", padx=(0, 12), pady=10)

        # Actualizar código (solo lectura)
        self.label_codigo.configure(text=codigo if codigo else "——————")

        # Actualizar lista de evidencias
        for w in self.frame_lista_ev.winfo_children():
            w.destroy()

        if evidencias:
            for ev in evidencias:
                self._agregar_chip_evidencia(ev)
        else:
            ctk.CTkLabel(
                self.frame_lista_ev, text="Sin evidencias aún",
                text_color="gray50", font=ctk.CTkFont(size=10),
            ).pack(pady=10)

    def _agregar_chip_evidencia(self, ev: dict):
        """Agrega un chip de miniatura o ícono de video para una evidencia."""
        url = ev.get("evidencia_url", "")
        ext = url.rsplit(".", 1)[-1].lower() if "." in url else ""

        chip = ctk.CTkFrame(self.frame_lista_ev, fg_color="#1e3a5e", corner_radius=6)
        chip.pack(fill="x", pady=2, padx=2)

        es_imagen = ext in ("jpg", "jpeg", "png", "webp")

        if es_imagen:
            # Intentar cargar miniatura desde URL
            try:
                import urllib.request
                with urllib.request.urlopen(url, timeout=3) as resp:
                    datos = resp.read()
                img_pil = Image.open(io.BytesIO(datos)).convert("RGB")
                img_pil.thumbnail((60, 40))
                img_ctk = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(60, 40))
                lbl = ctk.CTkLabel(chip, image=img_ctk, text="")
                lbl.pack(side="left", padx=6, pady=4)
                lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            except Exception:
                ctk.CTkLabel(chip, text="🖼", font=ctk.CTkFont(size=18)).pack(side="left", padx=8)
        else:
            ctk.CTkLabel(chip, text="🎬", font=ctk.CTkFont(size=18)).pack(side="left", padx=8)

        nombre = url.rsplit("/", 1)[-1] if "/" in url else url
        lbl_nombre = ctk.CTkLabel(
            chip, text=nombre[:24] + "…" if len(nombre) > 24 else nombre,
            text_color="gray80", font=ctk.CTkFont(size=10),
        )
        lbl_nombre.pack(side="left", padx=4)
        lbl_nombre.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

        fecha_creada = ev.get("creado_en", "")
        if fecha_creada:
            try:
                dt = datetime.fromisoformat(fecha_creada[:19])
                fecha_str = dt.strftime("%d/%m %H:%M")
            except ValueError:
                fecha_str = ""
            ctk.CTkLabel(
                chip, text=fecha_str, text_color="gray50", font=ctk.CTkFont(size=9),
            ).pack(side="right", padx=8)

    # ─── Grabación ────────────────────────────────────────────────────────────

    def _registrar_hotkeys(self):
        keyboard.add_hotkey("ctrl+k+l", self._toggle_grabacion)

    def _al_destruir(self, event):
        self.hilo_polling_activo = False
        try:
            keyboard.remove_hotkey("ctrl+k+l")
        except Exception:
            pass
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
        nombre_archivo = self.ruta_evidencia.replace("\\", "/").split("/")[-1]
        self.label_archivo.configure(text=f"✅ Grabado:\n{nombre_archivo}")

    def _mostrar_indicador_rec(self):
        self.indicador = ctk.CTkToplevel(self.controlador)
        self.indicador.overrideredirect(True)
        self.indicador.attributes("-topmost", True)
        ancho, alto = 200, 42
        x = self.indicador.winfo_screenwidth() - ancho - 20
        self.indicador.geometry(f"{ancho}x{alto}+{x}+20")
        ctk.CTkLabel(
            self.indicador,
            text="🔴 Grabando (Ctrl+K+L)",
            fg_color="#1a1a1a", text_color="white",
        ).pack(fill="both", expand=True)

    def _ocultar_indicador_rec(self):
        if self.indicador is not None:
            self.indicador.destroy()
            self.indicador = None

    # ─── Adjuntar / Subir evidencia ───────────────────────────────────────────

    def _on_adjuntar(self):
        ruta = filedialog.askopenfilename(
            title="Selecciona la evidencia",
            filetypes=[("Videos e imágenes", "*.mp4 *.jpg *.jpeg *.png")],
        )
        if ruta:
            self.ruta_evidencia = ruta
            nombre_archivo = ruta.replace("\\", "/").split("/")[-1]
            self.label_archivo.configure(text=f"✅ Archivo:\n{nombre_archivo}")

    def _on_subir_evidencia(self):
        codigo = self._codigo_panel_activo.strip().upper()

        if not codigo or len(codigo) != 6:
            messagebox.showwarning("Atención", "No hay un código de bitácora activo.")
            return

        if not self.ruta_evidencia:
            messagebox.showwarning("Atención", "No has grabado ni adjuntado ninguna evidencia.")
            return

        self.boton_subir.configure(state="disabled", text="Subiendo…")
        self.update()

        evidencia_url, error_upload = subir_archivo(self.ruta_evidencia)

        if evidencia_url is None:
            messagebox.showerror("Error", f"No se pudo subir el archivo.\n\nMotivo: {error_upload}")
            self.boton_subir.configure(state="normal", text="⬆️  Subir y Vincular")
            return

        con_audio = bool(self.switch_audio.get())
        data, error_link = adjuntar_evidencia_por_codigo(codigo, evidencia_url, con_audio)

        if error_link:
            messagebox.showerror("Error", error_link)
        else:
            if es_archivo_grabado(self.ruta_evidencia):
                try:
                    os.remove(self.ruta_evidencia)
                except OSError:
                    pass

            self.label_archivo.configure(text="Sin evidencia adjunta")
            self.switch_audio.deselect()
            self.ruta_evidencia = None

            # Recargar lista de evidencias en el panel (el código sigue activo)
            if data:
                evidencias = data.get("evidencias", [])
                self._mostrar_panel_evidencia(codigo, evidencias)
                self._mostrar_toast(f"✅ Evidencia #{len(evidencias)} vinculada a {codigo}")
            # Forzar recarga en el siguiente polling
            self.ultimo_hash_bd = None

        self.boton_subir.configure(state="normal", text="⬆️  Subir y Vincular")

    # ─── Navegación ───────────────────────────────────────────────────────────

    def _on_volver(self):
        self.hilo_polling_activo = False
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)