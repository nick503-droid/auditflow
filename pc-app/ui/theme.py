"""Paleta claro/oscuro. Sólo presentación; no contiene estado de negocio."""
import json
import os
from pathlib import Path

import customtkinter as ctk

# Cada par es (claro, oscuro). CTk cambia los widgets existentes in-place.
# Oscuro basado en la paleta HTML del usuario: carbón, pizarra e índigo suave.
APP_BACKGROUND = ("#F1F5F9", "#121214")
SURFACE = ("#FFFFFF", "#1E1E24")
SURFACE_SECONDARY = ("#E2E8F0", "#282830")
BORDER = ("#CBD5E1", "#32323D")
BORDER_FOCUS = ("#046C4E", "#818CF8")
PRIMARY = ("#047857", "#5558D9")
PRIMARY_HOVER = ("#065F46", "#494BC2")
PRIMARY_SOFT = ("#D1FAE5", "#2A2947")
SECONDARY = ("#0369A1", "#0369A1")
SECONDARY_BG = ("#E0F2FE", "#173343")
TERTIARY = ("#B45309", "#92400E")
TERTIARY_HOVER = ("#92400E", "#78350F")
INVERTED_BG = ("#1E293B", "#35343F")
TEXT_PRIMARY = ("#1E293B", "#E4E4E7")
TEXT_SECONDARY = ("#334155", "#B5B5C0")
TEXT_MUTED = ("#526277", "#A1A1AA")

# Separar texto pastel de fondo sólido evita letras blancas sobre menta/ámbar.
STATUS = {
    "success": {"text": ("#046C4E", "#34D399"), "bg": ("#ECFDF5", "#18352C"),
                "border": ("#A7F3D0", "#28634E"), "solid": ("#047857", "#047857"), "hover": ("#065F46", "#065F46")},
    "warning": {"text": ("#9A4708", "#FBBF24"), "bg": ("#FFFBEB", "#382E1C"),
                "border": ("#FDE68A", "#725827"), "solid": ("#B45309", "#92400E"), "hover": ("#92400E", "#78350F")},
    "error": {"text": ("#B91C1C", "#F87171"), "bg": ("#FEF2F2", "#3C252B"),
              "border": ("#FECACA", "#78404B"), "solid": ("#B91C1C", "#B91C1C"), "hover": ("#991B1B", "#991B1B")},
    "info": {"text": ("#0369A1", "#38BDF8"), "bg": ("#F0F9FF", "#173343"),
             "border": ("#BAE6FD", "#285D77"), "solid": SECONDARY, "hover": ("#075985", "#075985")},
}
STATUS["success"]["hover_bg"] = ("#D1FAE5", "#204738")
STATUS["info"]["hover_bg"] = ("#E0F2FE", "#1D3D51")
STATUS["error"]["hover_bg"] = ("#FEE2E2", "#4A2930")
RADIUS_PANEL = 12
RADIUS_BUTTON = 8
FONT_FAMILY = "Segoe UI"


def get_font(size: int, weight: str = "normal", family: str = None) -> ctk.CTkFont:
    return ctk.CTkFont(family=family or FONT_FAMILY, size=size, weight=weight)


def resolve_color(value, mode=None):
    """Color nativo para tkcalendar/Tk, que no aceptan pares CTk."""
    if isinstance(value, (tuple, list)):
        return value[1 if (mode or ctk.get_appearance_mode()).lower() == "dark" else 0]
    return value


def calendar_colors(mode=None):
    """tkcalendar usa colores nativos, no pares de CustomTkinter."""
    colors = {
        "background": APP_BACKGROUND, "foreground": TEXT_PRIMARY,
        "headersbackground": SURFACE_SECONDARY, "headersforeground": TEXT_PRIMARY,
        "normalbackground": SURFACE, "normalforeground": TEXT_PRIMARY,
        "weekendbackground": SURFACE, "weekendforeground": TEXT_PRIMARY,
        "othermonthbackground": SURFACE_SECONDARY, "othermonthforeground": TEXT_MUTED,
        "othermonthwebackground": SURFACE_SECONDARY, "othermonthweforeground": TEXT_MUTED,
        "bordercolor": BORDER, "selectbackground": PRIMARY, "selectforeground": "#FFFFFF",
    }
    return {key: resolve_color(value, mode) for key, value in colors.items()}


def follow_calendar_appearance(calendar):
    def update(mode):
        if calendar.winfo_exists():
            calendar.configure(**calendar_colors(mode))

    def cleanup(event):
        if event.widget is calendar:
            ctk.AppearanceModeTracker.remove(update)

    ctk.AppearanceModeTracker.add(update, calendar)
    calendar.bind("<Destroy>", cleanup, add="+")


def preference_path():
    base = Path(os.environ.get("APPDATA") or (Path.home() / ".config"))
    return base / "AuditFlow" / "appearance.json"


def load_appearance(path=None):
    try:
        value = json.loads(Path(path or preference_path()).read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("mode") in ("Light", "Dark"):
            return value["mode"]
    except (OSError, ValueError):
        pass
    return "Light"


def set_appearance(mode, path=None):
    if mode not in ("Light", "Dark"):
        raise ValueError("Modo visual inválido")
    ctk.set_appearance_mode(mode)
    target = Path(path or preference_path())
    temporary = target.with_suffix(".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps({"mode": mode}), encoding="utf-8")
        os.replace(temporary, target)
        return True
    except OSError:
        return False


def initialize_appearance():
    ctk.set_default_color_theme(str(Path(__file__).with_name("auditflow_theme.json")))
    ctk.set_appearance_mode(load_appearance())
