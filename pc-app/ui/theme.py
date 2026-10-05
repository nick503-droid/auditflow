"""
theme.py - Sistema de Diseño y Tokens (Light Edition) para AuditFlow
"""

import customtkinter as ctk

# ─── 1. Colores Estructurales y Superficies ──────────────────────────────────
APP_BACKGROUND = "#F1F5F9"
SURFACE = "#FFFFFF"
SURFACE_SECONDARY = "#E2E8F0"
BORDER = "#CBD5E1"
BORDER_FOCUS = "#047857"

# ─── 2. Marca (Verde y Azul) ─────────────────────────────────────────────────
PRIMARY = "#047857"         # Emerald 700, buen contraste con texto blanco
PRIMARY_HOVER = "#065F46"   # Emerald 800
PRIMARY_SOFT = "#D1FAE5"    # Emerald 100
SECONDARY = "#0369A1"       # Blue 700, buen contraste con texto blanco
SECONDARY_BG = "#E0F2FE"
TERTIARY = "#B45309"        # Amber 700, buen contraste con texto blanco
TERTIARY_HOVER = "#92400E"  # Amber 800
INVERTED_BG = "#1E293B"

# ─── 3. Tipografía y Contenido ──────────────────────────────────────────────
TEXT_PRIMARY = "#1E293B"
TEXT_SECONDARY = "#334155"
TEXT_MUTED = "#64748B"

# ─── 4. Estados Operativos ──────────────────────────────────────────────────
STATUS = {
    "success": {"text": "#047857", "bg": "#ECFDF5", "border": "#A7F3D0"},
    "warning": {"text": "#B45309", "bg": "#FFFBEB", "border": "#FDE68A"},
    "error":   {"text": "#B91C1C", "bg": "#FEF2F2", "border": "#FECACA"},
    "info":    {"text": "#0369A1", "bg": "#F0F9FF", "border": "#BAE6FD"},
}

# ─── Geometría ───────────────────────────────────────────────────────────────
RADIUS_PANEL = 12
RADIUS_BUTTON = 8

# ─── Fuentes ─────────────────────────────────────────────────────────────────
FONT_FAMILY = "Plus Jakarta Sans"

def get_font(size: int, weight: str = "normal", family: str = None) -> ctk.CTkFont:
    """Retorna la fuente estándar del sistema con fallback nativo."""
    return ctk.CTkFont(family=family or FONT_FAMILY, size=size, weight=weight)
