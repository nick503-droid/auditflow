import customtkinter as ctk
from ui.theme import APP_BACKGROUND, SURFACE, SURFACE_SECONDARY, TEXT_MUTED, get_font, set_appearance
from ui.icons import get_icon
from ui.visual_widgets import IconButton

class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AuditFlow - Control de Auditoría")

        # Calcular posición y tamaño DESPUÉS de que tkinter tenga pantalla disponible
        self.update_idletasks()

        try:
            from db.local_db import limpiar_borradores_fantasma
            limpiar_borradores_fantasma()
        except Exception as e:
            print(f"[Auto-Clean] Error limpiando borradores fantasmas: {e}")

        pantalla_w = self.winfo_screenwidth()
        pantalla_h = self.winfo_screenheight()

        # Tamaño de la ventana: Dashboard amplio para ver todas las tarjetas y paneles
        win_w = min(1280, pantalla_w - 100)
        win_h = min(800, pantalla_h - 100)

        # Posición: centrada
        pos_x = (pantalla_w - win_w) // 2
        pos_y = (pantalla_h - win_h) // 2

        self.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.minsize(800, 600)
        self.configure(fg_color=APP_BACKGROUND) # Prevenir parpadeo entre vistas

        # El frame actualmente visible. Empieza en None porque
        # todavía no hemos montado ninguno.
        self.frame_actual = None

        # Selector persistente fuera de los módulos: cambiar tema NO navega,
        # recrea editores, reinicia polling ni altera grabaciones en curso.
        self.appearance_bar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=28)
        self.appearance_bar.pack(side="bottom", fill="x")
        self.appearance_button = IconButton(
            self.appearance_bar, text="", height=24, width=138,
            fg_color="transparent", hover_color=SURFACE_SECONDARY,
            text_color=TEXT_MUTED, font=get_font(size=11), command=self._toggle_appearance,
        )
        self.appearance_button.pack(side="right", padx=10, pady=2)
        self._update_appearance_button()
        self.bind("<Control-Shift-L>", lambda event: self._toggle_appearance())

        # Import diferido para evitar import circular
        from ui.login_frame import LoginFrame
        self.mostrar_frame(LoginFrame)

    def _update_appearance_button(self):
        dark = ctk.get_appearance_mode() == "Dark"
        self.appearance_button.configure(
            text="Modo claro" if dark else "Modo oscuro",
            image=get_icon("sun" if dark else "moon", (16, 16), TEXT_MUTED),
        )

    def _toggle_appearance(self):
        set_appearance("Light" if ctk.get_appearance_mode() == "Dark" else "Dark")
        self._update_appearance_button()

    def mostrar_frame(self, frame_class, **kwargs):
        """
        Destruye el frame actual (si existe) y monta uno nuevo.
        Esto es lo más parecido que tenemos aquí a un router.push()
        de Vue Router: cambiamos qué 'pantalla' se ve, sin abrir
        una ventana nueva de Windows.
        """
        if self.frame_actual is not None:
            self.frame_actual.destroy()

        # 'self' se pasa como referencia al controlador/router,
        # para que el frame pueda pedir navegar a otra pantalla
        nuevo_frame = frame_class(self, controlador=self, **kwargs)
        nuevo_frame.pack(fill="both", expand=True)
        self.frame_actual = nuevo_frame
