import customtkinter as ctk
import os
import threading
import sys
from dotenv import load_dotenv

# Cargar variables de entorno ANTES de importar los módulos internos
_launcher_dir = os.environ.get("AUDITFLOW_LAUNCHER_DIR")
if _launcher_dir:
    # La configuración no se copia dentro de cada versión del programa.
    load_dotenv(os.path.join(_launcher_dir, ".env"))
else:
    load_dotenv()

from ui.main_window import MainWindow
from db.local_db import inicializar_db

ctk.set_appearance_mode("light")
_theme_path = os.path.join(os.path.dirname(__file__), "ui", "auditflow_theme.json")
if os.path.exists(_theme_path):
    ctk.set_default_color_theme(_theme_path)
else:
    ctk.set_default_color_theme("green")

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        # Verifica el bundle sin abrir datos del usuario, red, audio ni grabación.
        from core.pc_updates import atomic_json
        from pathlib import Path
        import subprocess
        try:
            import cv2
            import keyboard
            import pyaudiowpatch
            from tkcalendar import Calendar
            from core.recorder import obtener_ruta_ffmpeg
            result = subprocess.run(
                [obtener_ruta_ffmpeg(), "-version"], capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=15,
            )
            if result.returncode:
                raise RuntimeError("FFmpeg empaquetado no inicia")
            probe = ctk.CTk()
            probe.withdraw()
            Calendar(probe)
            probe.update_idletasks()
            probe.destroy()
            atomic_json(Path(sys.executable).parent / "self-test.json", {"ok": True})
        except Exception as error:
            atomic_json(Path(sys.executable).parent / "self-test.json", {"ok": False, "error": str(error)})
            sys.exit(1)
        sys.exit(0)

    inicializar_db()
    from api.client import (
        iniciar_limpiador_cache,
        obtener_restaurantes,
        obtener_usuarios,
        sincronizar_directorio_offline,
    )
    # Iniciamos el limpiador de caché al arrancar la app
    # Eliminará archivos que lleven más de 24 horas sin abrirse.
    iniciar_limpiador_cache(horas_vida=24.0)

    def _sincronizar_catalogos_pc():
        """Mantiene preparada la caché de PC; no interviene en Android."""
        while True:
            sincronizar_directorio_offline()
            obtener_usuarios()
            obtener_restaurantes()
            # Es una consulta pequeña por minuto, suficiente para propagar
            # usuarios/restaurantes sin cargar el servidor local.
            threading.Event().wait(60)

    threading.Thread(
        target=_sincronizar_catalogos_pc,
        daemon=True,
        name="CatalogosOfflinePC",
    ).start()
    
    app = MainWindow()
    from core.pc_updates import mark_application_ready, start_background_updates
    from api import client

    def _iniciar_actualizador():
        # El lanzador sólo considera sano el arranque después de crear la UI/DB.
        mark_application_ready()
        app._pc_update_stop = start_background_updates(lambda: client.API_BASE_URL)
        if app._pc_update_stop:
            from core.pc_updates import application_version, read_json, updates_home
            current = application_version()

            def _mostrar_version():
                pending = read_json(updates_home() / "pending.json", {})
                suffix = " | Actualización lista al volver a abrir" if pending.get("build", 0) > current["build"] else ""
                title = f"AuditFlow - Control de Auditoría | v{current['version']}{suffix}"
                if app.title() != title:
                    app.title(title)
                app.after(30000, _mostrar_version)

            _mostrar_version()

    app.after(0, _iniciar_actualizador)
    app.mainloop()
    if getattr(app, "_pc_update_stop", None):
        app._pc_update_stop.set()
