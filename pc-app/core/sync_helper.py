"""
sync_helper.py — Utilidades compartidas de sincronización para AuditFlow PC App.

Centraliza la paleta de colores y el helper de indicador de estado de sync,
de modo que BitacorasFrame y ReportesFrame usen exactamente la misma lógica
sin duplicar código.

Estados soportados:
  'ok'      → ⬤ Sincronizado / ☁️ En la nube          (verde)
  'offline' → ⬤ Sin conexión — guardando local          (amarillo)
  'syncing' → ↻ Sincronizando N…                        (azul)
"""

import customtkinter as ctk
from ui.theme import STATUS, TEXT_MUTED

# ─── Paleta de colores de sincronización ──────────────────────────────────────
COLOR_SYNC_OK      = STATUS["success"]["text"]
COLOR_SYNC_OFFLINE = STATUS["warning"]["text"]
COLOR_SYNC_WORKING = STATUS["info"]["text"]


def actualizar_indicador_sync(label: ctk.CTkLabel, estado: str, pendientes: int = 0):
    """
    Actualiza un CTkLabel de estado de sincronización según el estado dado.

    Parámetros
    ----------
    label      : CTkLabel que muestra el estado (debe existir en la UI).
    estado     : 'ok' | 'offline' | 'syncing'
    pendientes : número de ítems pendientes (solo relevante para 'syncing').
    """
    try:
        if not label.winfo_exists():
            return
        firma = (estado, pendientes)
        if getattr(label, "_firma_sync", None) == firma:
            return
        label._firma_sync = firma

        if estado == "ok":
            label.configure(text="⬤ Sincronizado", text_color=COLOR_SYNC_OK)
        elif estado == "offline":
            label.configure(text="⬤ Sin conexión — guardando local", text_color=COLOR_SYNC_OFFLINE)
        elif estado == "syncing":
            label.configure(text=f"↻ Sincronizando {pendientes}…", text_color=COLOR_SYNC_WORKING)
    except Exception:
        pass


def actualizar_indicador_reporte(label: ctk.CTkLabel, estado: str):
    """
    Variante con textos orientados al editor de reportes (compactos para la topbar).

    Estados:
      'ok'      → ☁️ En la nube
      'offline' → 💾 Guardando local
      'syncing' → ↻ Sincronizando…
      'writing' → Escribiendo…
      'conflict' → ⚠ Integrar cambios
    """
    try:
        if not label.winfo_exists():
            return
        if getattr(label, "_firma_sync", None) == estado:
            return
        label._firma_sync = estado

        if estado == "ok":
            label.configure(text="☁️ En la nube", text_color=COLOR_SYNC_OK)
        elif estado == "offline":
            label.configure(text="💾 Guardando local", text_color=COLOR_SYNC_OFFLINE)
        elif estado == "syncing":
            label.configure(text="↻ Sincronizando…", text_color=COLOR_SYNC_WORKING)
        elif estado == "writing":
            label.configure(text="Escribiendo…", text_color=TEXT_MUTED)
        elif estado == "conflict":
            label.configure(text="⚠ Integrar cambios", text_color=COLOR_SYNC_OFFLINE)
    except Exception:
        pass
