"""
theme.py - Sistema de Diseño y Tokens (Light Edition) para AuditFlow
"""

import customtkinter as ctk

# ─── 1. Colores Estructurales y Superficies ──────────────────────────────────
APP_BACKGROUND = "#F8FAFC"
SURFACE = "#FFFFFF"
SURFACE_SECONDARY = "#F1F5F9"
BORDER = "#E2E8F0"
BORDER_FOCUS = "#059669"

# ─── 2. Colores de Marca y Acción ──────────────────────────────────────────
PRIMARY = "#059669"
PRIMARY_HOVER = "#047857"
PRIMARY_SOFT = "#ECFDF5"

# ─── 3. Tipografía y Contenido ──────────────────────────────────────────────
TEXT_PRIMARY = "#0F172A"
TEXT_SECONDARY = "#475569"
TEXT_MUTED = "#94A3B8"

# ─── 4. Estados Operativos ──────────────────────────────────────────────────
STATUS = {
    "success": {"text": "#059669", "bg": "#ECFDF5", "border": "#A7F3D0"},
    "warning": {"text": "#B45309", "bg": "#FFFBEB", "border": "#FDE68A"},
    "error":   {"text": "#B91C1C", "bg": "#FEF2F2", "border": "#FECACA"},
    "info":    {"text": "#0369A1", "bg": "#F0F9FF", "border": "#BAE6FD"},
}

# ─── Geometría ───────────────────────────────────────────────────────────────
RADIUS_PANEL = 12
RADIUS_BUTTON = 8

# ─── Fuentes ─────────────────────────────────────────────────────────────────
FONT_FAMILY = "Plus Jakarta Sans"

def get_font(size: int, weight: str = "normal") -> ctk.CTkFont:
    """Retorna la fuente estándar del sistema con fallback nativo."""
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
