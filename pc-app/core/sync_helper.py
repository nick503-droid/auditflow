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

# ─── Paleta de colores de sincronización ──────────────────────────────────────
COLOR_SYNC_OK      = "#4ade80"   # verde
COLOR_SYNC_OFFLINE = "#facc15"   # ámbar/amarillo
COLOR_SYNC_WORKING = "#60a5fa"   # azul


def actualizar_indicador_sync(label: ctk.CTkLabel, estado: str, pendientes: int = 0):
    """
    Actualiza un CTkLabel de estado de sincronización según el estado dado.

    Parámetros
    ----------
    label      : CTkLabel que muestra el estado (debe existir en la UI).
    estado     : 'ok' | 'offline' | 'syncing'
    pendientes : número de ítems pendientes (solo relevante para 'syncing').
    """
    if not label.winfo_exists():
        return

    if estado == "ok":
        label.configure(text="⬤ Sincronizado", text_color=COLOR_SYNC_OK)
    elif estado == "offline":
        label.configure(text="⬤ Sin conexión — guardando local", text_color=COLOR_SYNC_OFFLINE)
    elif estado == "syncing":
        label.configure(text=f"↻ Sincronizando {pendientes}…", text_color=COLOR_SYNC_WORKING)


def actualizar_indicador_reporte(label: ctk.CTkLabel, estado: str):
    """
    Variante con textos orientados al editor de reportes (compactos para la topbar).

    Estados:
      'ok'      → ☁️ En la nube
      'offline' → 💾 Guardando local
      'syncing' → ↻ Sincronizando…
      'writing' → Escribiendo…
    """
    if not label.winfo_exists():
        return

    if estado == "ok":
        label.configure(text="☁️ En la nube", text_color=COLOR_SYNC_OK)
    elif estado == "offline":
        label.configure(text="💾 Guardando local", text_color=COLOR_SYNC_OFFLINE)
    elif estado == "syncing":
        label.configure(text="↻ Sincronizando…", text_color=COLOR_SYNC_WORKING)
    elif estado == "writing":
        label.configure(text="Escribiendo…", text_color="gray50")
