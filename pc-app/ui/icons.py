"""Trazos propios transparentes, offline y adaptados a claro/oscuro."""
from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw
import customtkinter as ctk

from ui.theme import TEXT_PRIMARY

ICON_NAMES = (
    "trash-2", "camera", "paperclip", "download", "upload", "eye", "file-text",
    "save", "image", "video", "check", "wifi-off", "plus", "x", "cloud",
    "layout-dashboard", "folder", "chart", "calendar", "clock", "user",
    "store", "settings", "log-out", "lock", "arrow-left", "arrow-right",
    "copy", "pause", "play", "stop", "record", "refresh", "warning", "sun", "moon",
)


def render_icon(name, color, pixels=96):
    """PIL RGBA puro. Alta resolución para bordes suaves y soporte HiDPI."""
    if name not in ICON_NAMES:
        raise ValueError(f"Icono desconocido: {name}")
    image = Image.new("RGBA", (pixels, pixels))
    draw = ImageDraw.Draw(image)
    scale = pixels / 24
    ink = ImageColor.getrgb(color) + (255,)
    width = max(1, round(1.7 * scale))

    def points(values): return [tuple(round(v * scale) for v in p) for p in values]
    def line(*values): draw.line(points(values), fill=ink, width=width, joint="curve")
    def box(rect, radius=0):
        draw.rounded_rectangle(tuple(round(v * scale) for v in rect), radius=round(radius * scale), outline=ink, width=width)
    def circle(rect, fill=False):
        draw.ellipse(tuple(round(v * scale) for v in rect), outline=ink, width=width, fill=ink if fill else None)
    def arc(rect, start, end):
        draw.arc(tuple(round(v * scale) for v in rect), start, end, fill=ink, width=width)

    if name == "trash-2":
        line((3, 6), (21, 6)); line((9, 6), (9, 3), (15, 3), (15, 6))
        line((6, 7), (7, 21), (17, 21), (18, 7)); line((10, 10), (10, 17)); line((14, 10), (14, 17))
    elif name == "camera":
        line((3, 7), (7, 7), (9, 4), (15, 4), (17, 7), (21, 7), (21, 20), (3, 20), (3, 7)); circle((8, 9, 16, 17))
    elif name == "paperclip":
        line((8, 16), (16, 8)); arc((12, 4, 20, 12), 180, 360)
        line((20, 8), (20, 13), (12, 21), (7, 21), (3, 17), (3, 12), (12, 3))
        line((16, 10), (9, 17), (7, 15), (14, 8))
    elif name in ("download", "upload"):
        box((3, 16, 21, 21), 1)
        if name == "download": line((12, 3), (12, 15)); line((7, 10), (12, 15), (17, 10))
        else: line((12, 15), (12, 3)); line((7, 8), (12, 3), (17, 8))
    elif name == "eye":
        line((2, 12), (6, 7), (12, 5), (18, 7), (22, 12), (18, 17), (12, 19), (6, 17), (2, 12)); circle((9, 9, 15, 15))
    elif name == "file-text":
        line((5, 2), (14, 2), (20, 8), (20, 22), (5, 22), (5, 2)); line((14, 2), (14, 8), (20, 8))
        line((8, 12), (16, 12)); line((8, 16), (16, 16))
    elif name == "save":
        line((3, 3), (18, 3), (21, 6), (21, 21), (3, 21), (3, 3)); box((7, 3, 16, 9)); box((7, 14, 17, 21))
    elif name == "image":
        box((3, 3, 21, 21), 2); circle((7, 6, 11, 10)); line((4, 19), (10, 13), (14, 17), (17, 12), (21, 17))
    elif name == "video":
        box((2, 5, 16, 19), 2); line((16, 10), (22, 6), (22, 18), (16, 14))
    elif name == "check": line((4, 12), (9, 17), (20, 6))
    elif name == "x": line((5, 5), (19, 19)); line((19, 5), (5, 19))
    elif name == "plus": line((12, 4), (12, 20)); line((4, 12), (20, 12))
    elif name == "cloud":
        arc((2, 10, 12, 20), 90, 270); arc((6, 4, 18, 16), 180, 335); arc((13, 10, 23, 20), 265, 90); line((7, 20), (18, 20))
    elif name == "wifi-off":
        arc((2, 3, 22, 23), 225, 315); arc((6, 8, 18, 20), 225, 315); circle((11, 18, 13, 20), True); line((3, 3), (21, 21))
    elif name == "layout-dashboard":
        for rect in ((3, 3, 10, 10), (14, 3, 21, 10), (3, 14, 10, 21), (14, 14, 21, 21)): box(rect, 1)
    elif name == "folder":
        line((3, 6), (3, 3), (10, 3), (13, 6), (21, 6), (21, 21), (3, 21), (3, 6), (21, 6))
    elif name == "chart":
        line((3, 3), (3, 21), (22, 21)); box((7, 12, 10, 20)); box((13, 6, 16, 20)); box((19, 9, 22, 20))
    elif name == "calendar":
        box((3, 5, 21, 21), 2); line((3, 10), (21, 10)); line((8, 2), (8, 7)); line((16, 2), (16, 7))
        for x, y in ((8, 14), (13, 14), (8, 18), (13, 18)): circle((x, y, x + 1, y + 1), True)
    elif name == "clock": circle((3, 3, 21, 21)); line((12, 6), (12, 12), (16, 14))
    elif name == "user": circle((8, 3, 16, 11)); arc((4, 13, 20, 29), 180, 360); line((4, 21), (20, 21))
    elif name == "store":
        box((4, 9, 20, 21)); box((9, 14, 15, 21)); line((2, 9), (5, 3), (19, 3), (22, 9), (2, 9)); line((8, 3), (7, 9)); line((16, 3), (17, 9))
    elif name == "settings":
        circle((5, 5, 19, 19)); circle((9, 9, 15, 15))
        for a, b in (((12, 2), (12, 5)), ((12, 19), (12, 22)), ((2, 12), (5, 12)), ((19, 12), (22, 12)), ((5, 5), (7, 7)), ((17, 17), (19, 19)), ((5, 19), (7, 17)), ((17, 7), (19, 5))): line(a, b)
    elif name == "log-out":
        line((10, 3), (4, 3), (4, 21), (10, 21)); line((10, 12), (22, 12)); line((17, 7), (22, 12), (17, 17))
    elif name == "lock":
        box((5, 10, 19, 22), 2); arc((8, 2, 16, 18), 180, 360); line((8, 6), (8, 10)); line((16, 6), (16, 10)); circle((11, 14, 13, 16), True)
    elif name in ("arrow-left", "arrow-right"):
        line((3, 12), (21, 12))
        if name == "arrow-left": line((9, 6), (3, 12), (9, 18))
        else: line((15, 6), (21, 12), (15, 18))
    elif name == "copy": box((8, 8, 21, 21), 2); line((16, 5), (16, 3), (3, 3), (3, 16), (5, 16))
    elif name == "pause": box((6, 4, 9, 20), 1); box((15, 4, 18, 20), 1)
    elif name == "play": line((7, 3), (21, 12), (7, 21), (7, 3))
    elif name == "stop": box((5, 5, 19, 19), 2)
    elif name == "record": circle((6, 6, 18, 18), True)
    elif name == "refresh": arc((4, 4, 20, 20), 35, 320); line((20, 3), (20, 8), (15, 8))
    elif name == "warning": line((12, 2), (23, 21), (1, 21), (12, 2)); line((12, 8), (12, 14)); circle((11, 17, 13, 19), True)
    elif name == "sun":
        circle((7, 7, 17, 17))
        for a, b in (((12, 1), (12, 4)), ((12, 20), (12, 23)), ((1, 12), (4, 12)), ((20, 12), (23, 12)), ((4, 4), (6, 6)), ((18, 18), (20, 20)), ((4, 20), (6, 18)), ((18, 6), (20, 4))): line(a, b)
    elif name == "moon":
        arc((3, 3, 21, 21), 45, 285); arc((10, 1, 24, 15), 80, 230)
    return image


@lru_cache(maxsize=256)
def _cached_icon(name, size, colors):
    pixels = max(48, max(size) * 3)
    return ctk.CTkImage(light_image=render_icon(name, colors[0], pixels),
                        dark_image=render_icon(name, colors[1], pixels), size=size)


def get_icon(name: str, size=(20, 20), color=None):
    if name not in ICON_NAMES:
        return None
    color = color or TEXT_PRIMARY
    colors = tuple(color) if isinstance(color, (list, tuple)) else (color, color)
    return _cached_icon(name, tuple(size), colors)
