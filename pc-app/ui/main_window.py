import customtkinter as ctk

class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AuditFlow - Control de Auditoría")

        # Calcular posición y tamaño DESPUÉS de que tkinter tenga pantalla disponible
        self.update_idletasks()

        pantalla_w = self.winfo_screenwidth()
        pantalla_h = self.winfo_screenheight()

        # Tamaño de la ventana: ancho fijo tipo "panel lateral derecho", alto casi completo
        win_w = 480
        win_h = pantalla_h - 80          # deja margen para la barra de tareas

        # Posición: pegada al borde derecho con 16 px de margen
        pos_x = pantalla_w - win_w - 16
        pos_y = 40

        self.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.minsize(360, 380)
        # (sin state('zoomed') — el usuario puede moverla/redimensionarla libremente)

        # El frame actualmente visible. Empieza en None porque
        # todavía no hemos montado ninguno.
        self.frame_actual = None

        # Import diferido para evitar import circular
        # (SelectionFrame necesita conocer a MainWindow, y viceversa)
        from ui.selection_frame import SelectionFrame
        self.mostrar_frame(SelectionFrame)

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