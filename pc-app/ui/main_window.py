import customtkinter as ctk


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AuditFlow - Control de Auditoría")
        self.geometry("500x450")

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