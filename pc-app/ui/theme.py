"""
theme.py - Sistema de Diseño y Tokens (Light Edition) para AuditFlow
"""

import customtkinter as ctk

# ─── 1. Colores Estructurales y Superficies ──────────────────────────────────
APP_BACKGROUND = "#F1F5F9"
SURFACE = "#FFFFFF"
SURFACE_SECONDARY = "#E2E8F0"
BORDER = "#CBD5E1"
BORDER_FOCUS = "#059669"

# ─── 2. Marca (Verde y Azul) ─────────────────────────────────────────────────
PRIMARY = "#059669"         # Emerald 600
PRIMARY_HOVER = "#047857"   # Emerald 700
PRIMARY_SOFT = "#D1FAE5"    # Emerald 100
SECONDARY = "#0284C7"       # Sky 600
SECONDARY_BG = "#E0F2FE"
TERTIARY = "#D97706"        # Amber 600
TERTIARY_HOVER = "#B45309"  # Amber 700
INVERTED_BG = "#1E293B"

# ─── 3. Tipografía y Contenido ──────────────────────────────────────────────
TEXT_PRIMARY = "#1E293B"
TEXT_SECONDARY = "#334155"
TEXT_MUTED = "#64748B"

# ─── 4. Estados Operativos ──────────────────────────────────────────────────
STATUS = {
    "success": {"text": "#059669", "bg": "#ECFDF5", "border": "#A7F3D0"},
    "warning": {"text": "#D97706", "bg": "#FFFBEB", "border": "#FDE68A"},
    "error":   {"text": "#DC2626", "bg": "#FEF2F2", "border": "#FECACA"},
    "info":    {"text": "#0284C7", "bg": "#F0F9FF", "border": "#BAE6FD"},
}

# ─── Geometría ───────────────────────────────────────────────────────────────
RADIUS_PANEL = 12
RADIUS_BUTTON = 8

# ─── Fuentes ─────────────────────────────────────────────────────────────────
FONT_FAMILY = "Plus Jakarta Sans"

def get_font(size: int, weight: str = "normal", family: str = None) -> ctk.CTkFont:
    """Retorna la fuente estándar del sistema con fallback nativo."""
    return ctk.CTkFont(family=family or FONT_FAMILY, size=size, weight=weight)
