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
    cerrar_bitacora_dia,
)
from core.recorder import GrabadorPantalla, es_archivo_grabado
from db.local_db import (
    inicializar_db,
    guardar_bitacora_local,
    marcar_bitacora_sincronizada,
    obtener_bitacoras_pendientes,
)

# ─── Paleta de colores ────────────────────────────────────────────────────────
# 4 niveles de urgencia: comentar (azul) < leve (verde) < medio (ámbar) < grave (rojo)
URGENCIA_COLORES = {
    "comentar": {"bg": "#1a2a3e", "fg": "#93c5fd", "tarjeta_par": "#141e2e", "tarjeta_impar": "#111827"},
    "leve":     {"bg": "#1e3a2e", "fg": "#4ade80", "tarjeta_par": "#152d22", "tarjeta_impar": "#12261d"},
    "medio":    {"bg": "#3a2e10", "fg": "#facc15", "tarjeta_par": "#2e2408", "tarjeta_impar": "#261e06"},
    "grave":    {"bg": "#3a1010", "fg": "#f87171", "tarjeta_par": "#2a0c0c", "tarjeta_impar": "#220808"},
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

COLOR_FILA_PAR         = "#1a1a2e"
COLOR_FILA_IMPAR       = "#16213e"
COLOR_CODIGO_BG        = "#1e3a5e"
COLOR_CODIGO_FG        = "#93c5fd"
COLOR_BOTON_EV_OK      = "#166534"
COLOR_BOTON_EV_ADD     = "#1d4ed8"
COLOR_SYNC_OK          = "#4ade80"
COLOR_SYNC_OFFLINE     = "#facc15"
COLOR_SYNC_WORKING     = "#60a5fa"

ANCHO_REST     = 160
ANCHO_HORA     = 70
ANCHO_COD      = 80
ANCHO_EV_BTN   = 110
ANCHO_URG_MENU = 110   # OptionMenu de urgencia

DEBOUNCE_MS    = 1500
ALTURA_DESC    = 28    # altura mínima del CTkTextbox de descripción


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

        ctk.CTkButton(
            self.top_bar, text="🔒 Cerrar día", width=110,
            fg_color="#7c3aed", hover_color="#6d28d9",
            command=self._on_cerrar_bitacora_dia,
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
        """Fila fija de etiquetas que sirve de cabecera visual.
        Orden: Restaurante | Hora | Descripción | Código | Evidencia | Urgencia
        """
        hdr = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=0)
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
            lbl = ctk.CTkLabel(
                hdr, text=texto,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="gray60", **kw,
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
            corner_radius=6,
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
            font=ctk.CTkFont(size=11),
            dynamic_resizing=False,
        )
        om_rest.set(rest_val if rest_val else "— Restaurante —")
        om_rest.grid(row=0, column=0, padx=(4, 2), pady=3)

        # ── Col 1 — Hora (texto libre) ────────────────────────────────────────
        hora_entry = ctk.CTkEntry(card, placeholder_text="HH:MM", width=ANCHO_HORA, height=28,
                                  font=ctk.CTkFont(size=11))
        hora_val = fila.get("hora", "")
        if hora_val:
            hora_entry.insert(0, hora_val)
        hora_entry.grid(row=0, column=1, padx=2, pady=3)
        hora_entry.bind("<KeyRelease>", lambda e, i=idx, w=hora_entry: self._on_keyrelease(i, "hora", w))
        hora_entry.bind("<FocusIn>",  lambda e: self._marcar_editando(True))
        hora_entry.bind("<FocusOut>", lambda e: self._marcar_editando(False))

        # ── Col 2 — Descripción (CTkTextbox responsivo) ───────────────────────
        desc_val = fila.get("descripcion", "")

        desc_box = ctk.CTkTextbox(
            card,
            height=ALTURA_DESC,
            font=ctk.CTkFont(size=11),
            wrap="word",
            activate_scrollbars=False,
        )
        if desc_val:
            desc_box.insert("1.0", desc_val)
        desc_box.grid(row=0, column=2, padx=2, pady=3, sticky="ew")
        desc_box.bind("<KeyRelease>", lambda e, i=idx, w=desc_box: self._on_keyrelease_textbox(i, w))
        desc_box.bind("<FocusIn>",   lambda e: self._marcar_editando(True))
        desc_box.bind("<FocusOut>",  lambda e: self._marcar_editando(False))
        # Ajustar altura inicial al contenido ya cargado
        self.after(50, lambda w=desc_box: self._ajustar_altura_textbox(w))

        # ── Col 3 — Badge de código (solo lectura) ────────────────────────────
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
        cod_btn.grid(row=0, column=3, padx=2, pady=3)

        # ── Col 4 — Botón de evidencia ────────────────────────────────────────
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
        ev_btn.grid(row=0, column=4, padx=2, pady=3)

        # ── Col 5 — Urgencia (OptionMenu, al final) ───────────────────────────
        urg_display = URGENCIA_VALOR_A_DISPLAY.get(urgencia, "Leve")

        urg_menu = ctk.CTkOptionMenu(
            card,
            values=URGENCIA_OPCIONES,
            width=ANCHO_URG_MENU, height=28,
            font=ctk.CTkFont(size=11),
            dynamic_resizing=False,
            fg_color=urg_info["bg"],
            text_color=urg_info["fg"],
            button_color=urg_info["bg"],
            button_hover_color=urg_info["bg"],
            command=lambda v, i=idx: self._on_cambiar_urgencia(i, v),
        )
        urg_menu.set(urg_display)
        urg_menu.grid(row=0, column=5, padx=(2, 6), pady=3)

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

    # ─── Helpers de descripción responsiva ───────────────────────────────────

    def _ajustar_altura_textbox(self, widget: ctk.CTkTextbox):
        """Ajusta la altura del CTkTextbox al número de líneas VISUALES.

        Estrategia principal: dlineinfo("end-1c") — lee la posición Y del
        último carácter ya renderizado (post word-wrap) y divide entre la
        altura de una línea para obtener el conteo visual real.
        Esto funciona con wrap="word" y activate_scrollbars=False.

        Requiere update_idletasks() para que tkinter calcule el layout y
        el word-wrap antes de consultar dlineinfo.
        """
        try:
            if not widget.winfo_exists():
                return

            # Forzar que tkinter calcule el layout y el word-wrap
            widget.update_idletasks()

            # Acceder al tk.Text interno de CTkTextbox
            tk_text = widget._textbox

            # --- Método 1: dlineinfo (más portable y preciso con word-wrap) ---
            # dlineinfo devuelve (x, y, width, height, baseline) de la
            # display-line que contiene el índice, o None si no está calculada.
            # Comparar Y de la última línea con Y de la primera da la altura
            # real del contenido ya envuelto por word-wrap.
            info_last  = tk_text.dlineinfo("end-1c")
            info_first = tk_text.dlineinfo("1.0")

            if info_last is not None and info_first is not None:
                line_height = info_last[3]          # altura px de esa línea
                y_last      = info_last[1]          # posición Y de la última línea
                y_first     = info_first[1]         # posición Y de la primera
                if line_height and line_height > 0:
                    n_display = max(1, round((y_last - y_first) / line_height) + 1)
                    nueva_altura = max(ALTURA_DESC, n_display * line_height + 10)
                    widget.configure(height=nueva_altura)
                    return

            # --- Método 2: count("displaylines") — tkinter >= 8.6 ---
            result = tk_text.count("1.0", "end", "displaylines")
            if isinstance(result, (list, tuple)):
                n_display = result[0] if result else 1
            else:
                n_display = result if result else 1
            n_display = max(1, n_display)
            widget.configure(height=max(ALTURA_DESC, n_display * 18 + 10))

        except Exception as exc:
            # --- Método 3 (fallback): contar \n literales ---
            # Menos preciso con wrap="word", pero nunca lanza excepción.
            print(f"[desc_resize] Fallback a conteo de \\n: {exc}")
            try:
                contenido = widget.get("1.0", "end-1c")
                n_lineas = max(1, contenido.count("\n") + 1)
                widget.configure(height=max(ALTURA_DESC, n_lineas * 18 + 10))
            except Exception:
                pass


    def _on_keyrelease_textbox(self, idx: int, widget: ctk.CTkTextbox):
        """Callback de tecla para CTkTextbox: guarda texto y ajusta altura."""
        try:
            texto = widget.get("1.0", "end-1c").strip()
            self.filas[idx]["descripcion"] = texto
            self._ajustar_altura_textbox(widget)
            self._programar_guardado(idx)
        except Exception:
            pass

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
            "urgencia": "leve",
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

    def _on_cambiar_urgencia(self, idx: int, display_value: str):
        """Convierte el nombre display a valor backend y reconstruye la tarjeta."""
        valor = URGENCIA_DISPLAY_A_VALOR.get(display_value, "leve")
        self.filas[idx]["urgencia"] = valor
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
        toast = ctk.CTkLabel(
            self.top_bar, text=mensaje,
            fg_color="#1e3a2e", text_color="#4ade80",
            corner_radius=6, font=ctk.CTkFont(size=11),
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
        # ELIMINADO: if not rest_id: return
        # Ahora permitimos guardar borradores sin restaurante en SQLite local.

        # Vigilante siempre del selector global — no del campo por fila
        vig_nombre = self.combo_vigilante.get().strip()
        usr_id = self.mapa_usuarios.get(vig_nombre, self.usuario_activo["id"])

        datos_locales = {
            "local_id":       fila.get("local_id"),
            "b_id":           fila.get("b_id", ""),
            "codigo":         fila.get("codigo", ""),
            "restaurante_id": rest_id,  # Puede ser None si aún no se seleccionó restaurante
            "usuario_id":     usr_id,
            "descripcion":    fila.get("descripcion", ""),
            "fecha":          self.fecha_actual,
            "hora":           fila.get("hora", ""),
            "urgencia":       fila.get("urgencia", "leve"),
        }

        # Paso 1: SQLite local (rápido, en hilo principal)
        # SIEMPRE guarda para no perder el borrador de la descripción
        local_id = guardar_bitacora_local(datos_locales)
        fila["local_id"] = local_id

        # Paso 2: intentar backend en hilo daemon (no bloquea UI)
        # Al backend SÍ le exigimos restaurante_id
        if rest_id:
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
            vig_nombre = self.combo_vigilante.get().strip()
            rest_id = self.mapa_restaurantes[rest_nombre]
            usr_id  = self.mapa_usuarios.get(vig_nombre, self.usuario_activo["id"])

            dto = {
                "restaurante_id": rest_id,
                "usuario_id":     usr_id,
                "fecha":          self.fecha_actual,
                "descripcion":    fila.get("descripcion", ""),
                "hora":           fila.get("hora", ""),
                "urgencia":       fila.get("urgencia", "leve"),
            }
            resultado = crear_bitacora(dto)
            if not resultado:
                messagebox.showerror("Error", "No se pudo crear el registro en el servidor.")
                return

            fila["b_id"]   = resultado.get("id", "")
            fila["codigo"] = resultado.get("codigo", "")
            self.ultimo_hash_bd = None
            self._reconstruir_tarjeta(idx)

        # Mostrar panel con indicador de carga, luego fetch fresco de evidencias
        codigo = fila["codigo"]
        self._mostrar_panel_evidencia(codigo, fila.get("evidencias", []))  # muestra estado cacheado mientras carga

        def _fetch_evidencias():
            evidencias_frescas = obtener_evidencias_bitacora(codigo)
            def _actualizar():
                fila["evidencias"] = evidencias_frescas   # mantiene caché local consistente
                self._mostrar_panel_evidencia(codigo, evidencias_frescas)
                # Reconstruir botón de evidencia para reflejar conteo actualizado
                self._reconstruir_tarjeta(idx)
            self.after(0, _actualizar)

        threading.Thread(target=_fetch_evidencias, daemon=True).start()

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
        Normaliza también valores legacy de urgencia (low/medium/critical).
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

            # Normalizar urgencia legacy (valores viejos antes del remapeo SQL)
            urgencia_raw = b.get("urgencia", "leve")
            urgencia = URGENCIA_LEGACY.get(urgencia_raw, urgencia_raw)

            datos_nuevos = {
                "b_id":        b_id,
                "codigo":      b.get("codigo", ""),
                "hora":        b.get("hora", ""),
                "restaurante": rest,
                "vigilante":   vig,
                "descripcion": b.get("descripcion", ""),
                "urgencia":    urgencia,
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
        """Agrega un chip de miniatura o ícono de video para una evidencia.
        - Imágenes: muestra miniatura clickeable; logguea error si falla la carga.
        - Videos: Extrae frame con OpenCV (si está instalado) o muestra ícono 🎬.
        """
        url = ev.get("evidencia_url", "")
        ext = url.rsplit(".", 1)[-1].lower() if "." in url else ""

        chip = ctk.CTkFrame(self.frame_lista_ev, fg_color="#1e3a5e", corner_radius=6)
        chip.pack(fill="x", pady=2, padx=2)

        es_imagen = ext in ("jpg", "jpeg", "png", "webp")
        es_video  = ext in ("mp4", "avi", "mov", "mkv", "webm")

        img_ctk = None

        if es_imagen:
            # Intentar cargar miniatura desde URL (bucket MinIO de lectura pública)
            try:
                import urllib.request
                with urllib.request.urlopen(url, timeout=3) as resp:
                    datos = resp.read()
                img_pil = Image.open(io.BytesIO(datos)).convert("RGB")
                img_pil.thumbnail((60, 40))
                img_ctk = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(60, 40))
            except Exception as exc:
                print(f"[evidencia] Error cargando miniatura '{url}': {exc}")

        elif es_video:
            # Intentar capturar el primer frame del video usando OpenCV
            try:
                import cv2
                # cv2.VideoCapture puede transmitir directamente desde HTTP/HTTPS
                cap = cv2.VideoCapture(url)
                ret, frame = cap.read()
                if ret:
                    # Convertir de formato BGR (OpenCV) a RGB (Pillow)
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img_pil = Image.fromarray(frame_rgb)
                    img_pil.thumbnail((60, 40))
                    img_ctk = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(60, 40))
                cap.release()
            except ImportError:
                print("[evidencia] opencv-python no instalado. Mostrando ícono por defecto.")
            except Exception as exc:
                print(f"[evidencia] Error capturando miniatura de video '{url}': {exc}")

        # Renderizar la miniatura (si se logró obtener) o el ícono fallback
        if img_ctk:
            lbl = ctk.CTkLabel(chip, image=img_ctk, text="", cursor="hand2")
            lbl.pack(side="left", padx=6, pady=4)
            lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        else:
            # Fallback a ícono según el tipo si la extracción falló
            icono_txt = "🖼" if es_imagen else "🎬"
            ico = ctk.CTkLabel(chip, text=icono_txt, font=ctk.CTkFont(size=18), cursor="hand2")
            ico.pack(side="left", padx=8)
            ico.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

        nombre = url.rsplit("/", 1)[-1] if "/" in url else url
        nombre_corto = (nombre[:24] + "…") if len(nombre) > 24 else nombre
        lbl_nombre = ctk.CTkLabel(
            chip, text=nombre_corto,
            text_color="gray80", font=ctk.CTkFont(size=10), cursor="hand2",
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