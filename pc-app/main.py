import customtkinter as ctk
import os
import threading
from dotenv import load_dotenv

# Cargar variables de entorno ANTES de importar los módulos internos
load_dotenv()

from ui.main_window import MainWindow
from db.local_db import inicializar_db

inicializar_db()

ctk.set_appearance_mode("light")
_theme_path = os.path.join(os.path.dirname(__file__), "ui", "auditflow_theme.json")
if os.path.exists(_theme_path):
    ctk.set_default_color_theme(_theme_path)
else:
    ctk.set_default_color_theme("green")

if __name__ == "__main__":
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
    app.mainloop()
