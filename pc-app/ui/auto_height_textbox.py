"""Texto multilínea que ocupa toda su altura real, sin scroll interno ni recortes."""
import math
from tkinter import TclError
import customtkinter as ctk


class AutoHeightTextbox(ctk.CTkTextbox):
    def __init__(self, master, *, min_height=28, **kwargs):
        self._min_height = min_height
        self._resize_job = None
        self._last_text_width = None
        super().__init__(master, height=min_height, activate_scrollbars=False, **kwargs)
        self._textbox.bind("<Configure>", self._on_text_configure, add="+")
        self._textbox.bind("<<Modified>>", self._on_text_modified, add="+")
        self._textbox.edit_modified(False)
        self.programar_ajuste()

    def after(self, ms, func=None, *args):
        # CTkTextbox arranca un sondeo de scrollbars por cada instancia, incluso
        # con activate_scrollbars=False. Aquí sólo hacen falta eventos de texto/ancho.
        if func == self._check_if_scrollbars_needed:
            return None
        return super().after(ms, func, *args)

    def _check_if_scrollbars_needed(self, event=None, continue_loop=False):
        pass  # Las barras están desactivadas y no se programa un sondeo periódico.

    def _on_text_configure(self, event):
        if event.width != self._last_text_width:
            self._last_text_width = event.width
            self.programar_ajuste()

    def _on_text_modified(self, _event):
        if self._textbox.edit_modified():
            self._textbox.edit_modified(False)
            self.programar_ajuste()

    def programar_ajuste(self):
        if self._resize_job is None and self.winfo_exists():
            self._resize_job = self.after_idle(self._ajustar)

    def _ajustar(self):
        self._resize_job = None
        if not self.winfo_exists() or self._textbox.winfo_width() <= 1:
            return
        texto = self._textbox
        try:
            # -update calcula también las líneas envueltas fuera del viewport.
            # No llamar update()/update_idletasks(): provoca reentradas y parpadeo.
            pixeles = texto.count("1.0", "end", "update", "ypixels") or 0
            if isinstance(pixeles, (tuple, list)):
                pixeles = pixeles[0]
            padding = sum(int(texto.cget(name)) for name in ("pady", "borderwidth", "highlightthickness")) * 2
            margen = max(self.cget("corner_radius"), self.cget("border_width") + self.cget("border_spacing"))
            altura = max(self._min_height, math.ceil(self._reverse_widget_scaling(pixeles + padding + 2) + margen * 2))
            if self.cget("height") != altura:
                self.configure(height=altura)
            texto.yview_moveto(0)
        except TclError:
            pass  # El padre pudo destruirse al salir de la vista.

    def destroy(self):
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        super().destroy()
