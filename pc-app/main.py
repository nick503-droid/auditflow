import customtkinter as ctk
from dotenv import load_dotenv
import os
from ui.main_window import MainWindow
from db.local_db import inicializar_db

load_dotenv()
inicializar_db()

ctk.set_appearance_mode("light")
_theme_path = os.path.join(os.path.dirname(__file__), "ui", "auditflow_theme.json")
if os.path.exists(_theme_path):
    ctk.set_default_color_theme(_theme_path)
else:
    ctk.set_default_color_theme("green")

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()