import customtkinter as ctk
from dotenv import load_dotenv
from ui.main_window import MainWindow
from db.local_db import inicializar_db

load_dotenv()
inicializar_db() 

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()