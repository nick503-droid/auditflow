from ui.theme import APP_BACKGROUND, SURFACE, SURFACE_SECONDARY, BORDER, BORDER_FOCUS, PRIMARY, PRIMARY_HOVER, PRIMARY_SOFT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, RADIUS_PANEL, RADIUS_BUTTON, get_font, STATUS
import tkinter as tk
import customtkinter as ctk
from PIL import ImageGrab, Image
import tempfile
import os
from datetime import datetime
from tkinter import messagebox

class SnippingTool:
    def __init__(self, parent, on_capture_callback):
        """
        on_capture_callback: function that takes (img_pil: Image, temp_path: str)
        """
        self.parent = parent
        self.on_capture_callback = on_capture_callback
        self.snip_surface = None
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        self._start_snipping()

    def _start_snipping(self):
        self.snip_surface = ctk.CTkToplevel(self.parent)
        # Quitar los bordes y hacer fullscreen para la experiencia "Snipping Tool"
        self.snip_surface.overrideredirect(True)
        self.snip_surface.state('zoomed')
        
        # Transparencia oscura (funciona muy bien en Windows)
        self.snip_surface.attributes('-alpha', 0.4)
        self.snip_surface.attributes('-topmost', True)
        self.snip_surface.configure(cursor="crosshair")
        
        # Usar un Canvas puro de tk para poder dibujar dinámicamente con fluidez
        self.canvas = tk.Canvas(self.snip_surface, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.canvas.bind("<ButtonPress-1>", self._on_button_press)
        self.canvas.bind("<B1-Motion>", self._on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self._on_button_release)
        
        # ESC para cancelar
        self.snip_surface.bind("<Escape>", lambda e: self.snip_surface.destroy())
        
    def _on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        # Creamos el rectángulo inicial
        self.current_rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, 1, 1, outline='#ef4444', width=2, fill="white"
        )

    def _on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)
        # Actualizamos las coordenadas del rectángulo mientras se arrastra
        self.canvas.coords(self.current_rect, self.start_x, self.start_y, cur_x, cur_y)

    def _on_button_release(self, event):
        end_x, end_y = (event.x, event.y)
        self.snip_surface.destroy()
        
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)
        
        if x2 - x1 < 10 or y2 - y1 < 10:
            # Seleccionó un área muy pequeña, ignorar
            return
            
        # Darle 300ms a la interfaz para que el Canvas oscuro desaparezca completamente de la pantalla
        self.parent.after(300, lambda: self._take_screenshot(x1, y1, x2, y2))
        
    def _take_screenshot(self, x1, y1, x2, y2):
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo tomar la captura: {e}")
            return
            
        self._show_preview(img)
        
    def _show_preview(self, img: Image.Image):
        preview_win = ctk.CTkToplevel(self.parent)
        preview_win.title("Vista previa de la captura")
        preview_win.geometry("640x500")
        preview_win.attributes("-topmost", True)
        preview_win.grab_set()
        
        # Escalar imagen para la vista previa
        img_w, img_h = img.size
        scale = min(560/img_w, 380/img_h)
        if scale < 1:
            prev_img = img.resize((int(img_w * scale), int(img_h * scale)), Image.Resampling.LANCZOS)
        else:
            prev_img = img
            
        tk_img = ctk.CTkImage(light_image=prev_img, dark_image=prev_img, size=prev_img.size)
        
        lbl = ctk.CTkLabel(preview_win, text="", image=tk_img)
        lbl.pack(pady=20, expand=True)
        
        btn_frame = ctk.CTkFrame(preview_win, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)
        
        def _aceptar():
            preview_win.destroy()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            ruta_temp = os.path.join(tempfile.gettempdir(), f"screenshot_{ts}.jpg")
            try:
                img.convert("RGB").save(ruta_temp, "JPEG", quality=85, optimize=True)
            except OSError as e:
                messagebox.showerror("Error al guardar", str(e))
                return
            self.on_capture_callback(img, ruta_temp)
            
        def _reintentar():
            preview_win.destroy()
            self._start_snipping()
            
        ctk.CTkButton(
            btn_frame, text="✅ Usar Captura", command=_aceptar, 
            fg_color=STATUS["success"]["text"], hover_color=PRIMARY
        ).pack(side="left", expand=True, padx=10)
        
        ctk.CTkButton(
            btn_frame, text="🔄 Volver a Capturar", command=_reintentar, 
            fg_color="#3b82f6", hover_color="#2563eb"
        ).pack(side="left", expand=True, padx=10)
        
        ctk.CTkButton(
            btn_frame, text="❌ Cancelar", command=preview_win.destroy, 
            fg_color="transparent", border_width=1, hover_color=STATUS["error"]["text"]
        ).pack(side="left", expand=True, padx=10)

def open_snipping_tool(parent, on_capture_callback):
    SnippingTool(parent, on_capture_callback)
