"""Selector compartido de evidencias. No copia, sube ni ejecuta archivos."""
import logging
import os
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ui.theme import (SURFACE, SURFACE_SECONDARY, BORDER, PRIMARY, PRIMARY_HOVER,
                      PRIMARY_SOFT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, STATUS, get_font)
from ui.visual_widgets import IconButton, IconLabel
from ui.icons import get_icon

FILE_TYPES = [
    ("Imágenes y videos", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.mp4 *.avi *.mkv *.webm *.mov *.m4v"),
    ("Todos los archivos", "*.*"),
]


def activar_arrastre(root):
    """Carga tkdnd en el intérprete CTk existente, sin otra raíz/mainloop."""
    from tkinterdnd2 import TkinterDnD
    try:
        return root.tk.call("package", "present", "tkdnd")
    except tk.TclError:
        pass
    return TkinterDnD.require(root)


def agregar_archivos(actuales, nuevos):
    """Valida y deduplica sin ordenar por nombre ni alterar los originales."""
    resultado = list(actuales)
    vistos = {os.path.normcase(os.path.realpath(p)) for p in resultado}
    errores = []
    for ruta in nuevos:
        try:
            ruta = os.path.abspath(os.fspath(ruta))
            clave = os.path.normcase(os.path.realpath(ruta))
            if clave in vistos:
                continue
            if not os.path.isfile(ruta):
                raise ValueError("no es un archivo disponible; no se admiten carpetas")
            if os.path.getsize(ruta) == 0:
                raise ValueError("el archivo está vacío")
            resultado.append(ruta)
            vistos.add(clave)
        except (OSError, ValueError, TypeError) as error:
            errores.append(f"{os.path.basename(str(ruta)) or str(ruta)}: {error}")
    return resultado, errores


class EvidencePicker(ctk.CTkToplevel):
    def __init__(self, owner):
        super().__init__(owner.winfo_toplevel())
        self.owner = owner
        self.resultado = ()
        self.archivos = []
        self._targets = []
        self._finalizado = False
        self._grab_anterior = self.grab_current()
        self.title("Adjuntar evidencia")
        self.configure(fg_color=SURFACE)
        self.transient(owner.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancelar)
        self.bind("<Escape>", lambda event: self.cancelar())
        self.bind("<Control-Return>", lambda event: self.confirmar())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        ancho = min(600, self.winfo_screenwidth() - 40)
        alto = min(600, self.winfo_screenheight() - 80)
        self.geometry(f"{ancho}x{alto}")
        self.minsize(min(460, ancho), min(430, alto))

        IconLabel(self, text="Adjuntar evidencia", font=get_font(21, "bold"),
                  text_color=TEXT_PRIMARY, anchor="w").grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        IconLabel(self, text="Busca archivos o arrástralos y suéltalos aquí.",
                  text_color=TEXT_SECONDARY, font=get_font(12), anchor="w").grid(row=1, column=0, sticky="ew", padx=24)

        self.zona = ctk.CTkFrame(self, fg_color=SURFACE_SECONDARY, border_color=BORDER,
                                 border_width=2, corner_radius=12)
        self.zona.grid(row=2, column=0, sticky="ew", padx=24, pady=(16, 10))
        self.zona.grid_columnconfigure(0, weight=1)
        self.icono = IconLabel(self.zona, text="", image=get_icon("upload", (32, 32), PRIMARY))
        self.icono.grid(row=0, column=0, pady=(18, 4))
        self.instruccion = IconLabel(self.zona, text="Arrastra y suelta uno o varios archivos",
                                     text_color=TEXT_PRIMARY, font=get_font(14, "bold"), wraplength=420)
        self.instruccion.grid(row=1, column=0, padx=12, pady=4)
        self.buscar = IconButton(self.zona, text="Buscar archivos", image=get_icon("folder", (18, 18), "#FFFFFF"),
                                 fg_color=PRIMARY, hover_color=PRIMARY_HOVER, text_color="#FFFFFF",
                                 height=36, command=self.explorar)
        self.buscar.grid(row=2, column=0, pady=(8, 18))

        self.lista = ctk.CTkScrollableFrame(self, fg_color=SURFACE_SECONDARY, corner_radius=8)
        self.lista.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 8))
        self.lista.grid_columnconfigure(0, weight=1)
        self.estado = IconLabel(self, text="", text_color=TEXT_MUTED, font=get_font(11),
                               anchor="w", justify="left", wraplength=360)
        self.estado.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 8))
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=5, column=0, sticky="ew", padx=24, pady=(0, 20))
        footer.grid_columnconfigure(0, weight=1)
        IconButton(footer, text="Cancelar", command=self.cancelar, fg_color=SURFACE_SECONDARY,
                   hover_color=BORDER, text_color=TEXT_PRIMARY, width=100).grid(row=0, column=0, sticky="w")
        self.adjuntar = IconButton(footer, text="Adjuntar", state="disabled", command=self.confirmar,
                                   fg_color=PRIMARY, hover_color=PRIMARY_HOVER, text_color="#FFFFFF", width=170)
        self.adjuntar.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self._renderizar()
        self._activar_drop()
        self.update_idletasks()
        root = owner.winfo_toplevel()
        x = max(0, min(root.winfo_rootx() + (root.winfo_width() - ancho) // 2, self.winfo_screenwidth() - ancho))
        y = max(0, min(root.winfo_rooty() + (root.winfo_height() - alto) // 2, self.winfo_screenheight() - alto))
        self.geometry(f"+{x}+{y}")
        self.wait_visibility()
        self.grab_set()
        self.buscar.focus_set()

    def _activar_drop(self):
        try:
            from tkinterdnd2 import DND_FILES
            activar_arrastre(self)
            def registrar(widget):
                widget.drop_target_register(DND_FILES)
                self._targets.append(widget)
                widget.dnd_bind("<<DropEnter>>", self._entrar)
                widget.dnd_bind("<<DropPosition>>", lambda event: "copy")
                widget.dnd_bind("<<DropLeave>>", self._salir)
                widget.dnd_bind("<<Drop>>", self._soltar)
                for child in widget.winfo_children():
                    registrar(child)
            # Registrar también los subwidgets nativos de CTk: icono, texto,
            # botón y fondo deben responder igual al Explorador de Windows.
            registrar(self.zona)
        except (ImportError, RuntimeError, tk.TclError, OSError) as error:
            logging.getLogger(__name__).warning("Arrastrar evidencia no disponible: %s", error)
            self.instruccion.configure(text="Usa Buscar archivos para adjuntar")
            self.estado.configure(text="Arrastrar no está disponible en esta instalación. Buscar archivos sigue funcionando.")

    def _entrar(self, event=None):
        self.zona.configure(fg_color=PRIMARY_SOFT, border_color=PRIMARY)
        self.instruccion.configure(text="Suelta aquí para añadir a la lista")
        return "copy"  # Nunca mover ni borrar el archivo del Explorador.

    def _salir(self, event=None):
        self.zona.configure(fg_color=SURFACE_SECONDARY, border_color=BORDER)
        self.instruccion.configure(text="Arrastra y suelta uno o varios archivos")
        return "copy"

    def _soltar(self, event):
        self._salir()
        if self._finalizado:
            return "refuse_drop"
        try:
            rutas = self.tk.splitlist(event.data)
        except tk.TclError:
            self.estado.configure(text="No se pudo leer la selección. Prueba con Buscar archivos.", text_color=STATUS["error"]["text"])
            return "refuse_drop"
        self._agregar(rutas)
        return "copy"

    def explorar(self):
        rutas = filedialog.askopenfilenames(parent=self, title="Selecciona las evidencias", filetypes=FILE_TYPES)
        if rutas:
            self._agregar(rutas)

    def _agregar(self, rutas):
        self.archivos, errores = agregar_archivos(self.archivos, rutas)
        self._renderizar()
        self.estado.configure(text=("\n".join(errores[:2]) + (f"\nY {len(errores)-2} archivo(s) no disponible(s)." if len(errores) > 2 else ""))
                              if errores else "Se copiarán los archivos; los originales no se moverán. También funciona sin conexión.",
                              text_color=STATUS["error"]["text"] if errores else TEXT_MUTED)

    def _quitar(self, ruta):
        self.archivos.remove(ruta)
        self._renderizar()

    def _renderizar(self):
        for child in self.lista.winfo_children():
            child.destroy()
        if not self.archivos:
            IconLabel(self.lista, text="Aún no has seleccionado archivos.", text_color=TEXT_MUTED).grid(row=0, column=0, padx=12, pady=18)
        for i, ruta in enumerate(self.archivos, 1):
            row = ctk.CTkFrame(self.lista, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(0, weight=1)
            IconLabel(row, text=f"{i}. {os.path.basename(ruta)}", text_color=TEXT_PRIMARY,
                      anchor="w", justify="left", wraplength=260).grid(row=0, column=0, sticky="ew", padx=(4, 8))
            IconButton(row, text="Quitar", width=68, command=lambda p=ruta: self._quitar(p),
                       fg_color="transparent", hover_color=SURFACE, text_color=STATUS["error"]["text"]).grid(row=0, column=1)
        self.adjuntar.configure(text=f"Adjuntar {len(self.archivos)} archivo(s)" if self.archivos else "Adjuntar",
                               state="normal" if self.archivos else "disabled")

    def confirmar(self):
        if self.archivos and not self._finalizado:
            self.resultado = tuple(self.archivos)
            self.destroy()

    def cancelar(self):
        self.resultado = ()
        self.destroy()

    def destroy(self):
        if self._finalizado:
            return
        self._finalizado = True
        for widget in self._targets:
            try:
                widget.drop_target_unregister()
            except tk.TclError:
                pass
        self.grab_release()
        super().destroy()
        try:
            if self._grab_anterior and self._grab_anterior.winfo_exists():
                self._grab_anterior.grab_set()
        except tk.TclError:
            pass


def seleccionar_evidencias(owner):
    if getattr(owner, "_selector_evidencias_abierto", False):
        return ()
    owner._selector_evidencias_abierto = True
    try:
        dialog = EvidencePicker(owner)
        owner.wait_window(dialog)
        return dialog.resultado
    finally:
        owner._selector_evidencias_abierto = False
