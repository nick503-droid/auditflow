"""Widgets CTk con iconos estables en lugar de glifos emoji del sistema.

No alteran comandos, variables, bindings ni disposición. Las miniaturas reales
siempre tienen prioridad; sólo se sustituyen adornos al inicio del texto.
"""
import customtkinter as ctk

from ui.icons import get_icon
from ui.theme import TEXT_PRIMARY, SURFACE_SECONDARY

PREFIX_ICONS = {
    "🗑": "trash-2", "📷": "camera", "📎": "paperclip", "⬇": "download", "↓": "download",
    "⇩": "download", "⇧": "upload", "↥": "upload", "👁": "eye", "✏": "file-text",
    "📝": "file-text", "📋": "file-text", "📄": "file-text", "≡": "file-text", "💾": "save",
    "🖼": "image", "▣": "image", "▤": "camera", "🎥": "video", "🎬": "video",
    "✅": "check", "✓": "check", "✔": "check", "☁": "cloud", "⬤": "record",
    "●": "record", "🔴": "record", "➕": "plus", "✕": "x", "✖": "x",
    "📁": "folder", "📂": "folder", "🗂": "folder", "📊": "chart", "📅": "calendar",
    "🕒": "clock", "👤": "user", "🏪": "store", "⚙": "settings", "🌐": "cloud",
    "🚪": "log-out", "🔒": "lock", "←": "arrow-left", "→": "arrow-right",
    "⎙": "copy", "⏸": "pause", "▶": "play", "⏹": "stop", "■": "stop",
    "↻": "refresh", "↺": "refresh", "⚠": "warning", "◀": "arrow-left",
}


def presentation_text(text):
    """No tocar texto de reportes/entradas: esto sólo se usa en labels/botones."""
    if not isinstance(text, str):
        return text, None
    normalized = text.replace("\ufe0f", "").lstrip()
    for prefix, icon in PREFIX_ICONS.items():
        if normalized.startswith(prefix):
            body = normalized[len(prefix):].lstrip()
            # Metadatos con varios glifos: conservar su significado como texto.
            for glyph, label in (("🕒", "Hora:"), ("🏪", "Restaurante:"), ("👤", "Autor:")):
                body = body.replace(glyph + " " + label, label)
                body = body.replace(glyph, label)
            return body, icon
    return text, None


class _IconMixin:
    def __init__(self, *args, **kwargs):
        self._visual_icon = None
        self._visual_font = kwargs.get("font")
        self._visual_height = kwargs.get("height", 60)
        self._visual_color = kwargs.get("text_color", self._default_icon_color)
        text, icon = presentation_text(kwargs.get("text", ""))
        kwargs["text"] = text
        if icon and kwargs.get("image") is None:
            self._visual_icon = icon
            kwargs["image"] = self._icon_image()
        super().__init__(*args, **kwargs)

    def _icon_image(self):
        font = self._visual_font
        size = abs(font.cget("size")) if isinstance(font, ctk.CTkFont) else 16
        if isinstance(font, (tuple, list)) and len(font) > 1:
            size = abs(font[1])
        size = max(12, min(52, int(size)))
        size = min(size, max(12, int(self._visual_height) - 6))
        return get_icon(self._visual_icon, (size, size), self._visual_color)

    def configure(self, require_redraw=False, **kwargs):
        refresh_icon = False
        if "text_color" in kwargs:
            self._visual_color = kwargs["text_color"]
            refresh_icon = True
        if "font" in kwargs:
            self._visual_font = kwargs["font"]
            refresh_icon = True
        if "image" in kwargs:
            # Las fotos/vídeos se muestran sin cambiar ni tintar sus píxeles.
            self._visual_icon = None
        if "text" in kwargs:
            kwargs["text"], icon = presentation_text(kwargs["text"])
            if "image" not in kwargs:
                if icon:
                    self._visual_icon = icon
                    refresh_icon = True
                elif self._visual_icon:
                    self._visual_icon = None
                    kwargs["image"] = None
        if refresh_icon and self._visual_icon and "image" not in kwargs:
            kwargs["image"] = self._icon_image()
        return super().configure(require_redraw=require_redraw, **kwargs)

    def destroy(self):
        # CTk 6 no retira este callback en destroy. El caché compartido no debe
        # mantener vivas tarjetas destruidas al navegar o refrescar evidencias.
        image = getattr(self, "_image", None)
        if isinstance(image, ctk.CTkImage):
            try:
                image.remove_configure_callback(self._update_image)
            except ValueError:
                pass
        super().destroy()


class IconButton(_IconMixin, ctk.CTkButton):
    _default_icon_color = "#FFFFFF"

    def __init__(self, *args, **kwargs):
        if kwargs.get("fg_color") == "transparent":
            kwargs.setdefault("hover_color", SURFACE_SECONDARY)
            kwargs.setdefault("text_color", TEXT_PRIMARY)
        super().__init__(*args, **kwargs)


class IconLabel(_IconMixin, ctk.CTkLabel):
    _default_icon_color = TEXT_PRIMARY
