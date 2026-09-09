import customtkinter as ctk
from tkinter import messagebox
import threading
from api.client import login
import session

# ─── SISTEMA DE DISEÑO ───────────────────────────────────────────────────────
BG_COLOR    = "#0f172a"
CARD_COLOR  = "#1e293b"
CARD_HOVER  = "#334155"
TEXT_MAIN   = "#f8fafc"
TEXT_SEC    = "#94a3b8"
ACCENT_COLOR = "#4f46e5"
ACCENT_HOVER = "#4338ca"
ERROR_COLOR  = "#ef4444"


class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, **kwargs):
        super().__init__(master, fg_color=BG_COLOR, **kwargs)
        self.controlador = controlador

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_ui()

    def _construir_ui(self):
        # Tarjeta central (ancho fijo, centrada)
        card = ctk.CTkFrame(
            self,
            fg_color=CARD_COLOR,
            corner_radius=20,
            width=420
        )
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.grid_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=50, pady=50, fill="both")

        # Logo / Título
        ctk.CTkLabel(
            inner,
            text="🔒",
            font=ctk.CTkFont(size=52)
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            inner,
            text="AuditFlow",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=TEXT_MAIN
        ).pack()

        ctk.CTkLabel(
            inner,
            text="Inicia sesión para continuar",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SEC
        ).pack(pady=(2, 30))

        # Campo usuario
        ctk.CTkLabel(inner, text="Usuario", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_SEC, anchor="w").pack(fill="x")
        self.entry_user = ctk.CTkEntry(
            inner,
            placeholder_text="Ingresa tu usuario",
            fg_color=BG_COLOR,
            border_color=CARD_HOVER,
            text_color=TEXT_MAIN,
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=14)
        )
        self.entry_user.pack(fill="x", pady=(4, 16))
        self.entry_user.bind("<Return>", lambda e: self.entry_pass.focus())

        # Campo contraseña
        ctk.CTkLabel(inner, text="Contraseña", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_SEC, anchor="w").pack(fill="x")
        self.entry_pass = ctk.CTkEntry(
            inner,
            placeholder_text="••••••••",
            show="•",
            fg_color=BG_COLOR,
            border_color=CARD_HOVER,
            text_color=TEXT_MAIN,
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=14)
        )
        self.entry_pass.pack(fill="x", pady=(4, 6))
        self.entry_pass.bind("<Return>", lambda e: self._on_login())

        # Mensaje de error (oculto por defecto)
        self.lbl_error = ctk.CTkLabel(
            inner,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=ERROR_COLOR
        )
        self.lbl_error.pack(pady=(0, 10))

        # Botón de login
        self.btn_login = ctk.CTkButton(
            inner,
            text="Ingresar →",
            command=self._on_login,
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=46,
            corner_radius=10
        )
        self.btn_login.pack(fill="x")

        # Footer
        ctk.CTkLabel(
            inner,
            text="AuditFlow v1.0 — Sistema de Auditoría",
            font=ctk.CTkFont(size=11),
            text_color=CARD_HOVER
        ).pack(pady=(24, 0))

        self.entry_user.focus()

    def _on_login(self):
        username = self.entry_user.get().strip()
        password = self.entry_pass.get()

        if not username or not password:
            self._mostrar_error("Por favor completa todos los campos.")
            return

        # Deshabilitar botón y mostrar estado de carga
        self.btn_login.configure(state="disabled", text="Verificando...")
        self.lbl_error.configure(text="")

        def _hacer_login():
            perfil = login(username, password)
            self.after(0, lambda: self._procesar_resultado(perfil))

        threading.Thread(target=_hacer_login, daemon=True).start()

    def _procesar_resultado(self, perfil: dict | None):
        self.btn_login.configure(state="normal", text="Ingresar →")
        if perfil:
            if perfil.get("require_password_change"):
                self._popup_cambiar_password(perfil)
            else:
                self._finalizar_login(perfil)
        else:
            self._mostrar_error("Usuario o contraseña incorrectos.")
            self.entry_pass.delete(0, "end")
            self.entry_pass.focus()

    def _finalizar_login(self, perfil):
        session.set_session(perfil)
        from ui.selection_frame import SelectionFrame
        self.controlador.mostrar_frame(SelectionFrame)

    def _popup_cambiar_password(self, perfil):
        # Modal para forzar el cambio
        win = ctk.CTkToplevel(self.controlador)
        win.title("Cambio de contraseña obligatorio")
        win.geometry("400x380")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.grab_set()

        def _on_close():
            self.entry_pass.delete(0, "end")
            win.destroy()
        
        win.protocol("WM_DELETE_WINDOW", _on_close)
        
        ctk.CTkLabel(
            win, text="Cambio Requerido", 
            font=ctk.CTkFont(size=22, weight="bold"), text_color=TEXT_MAIN
        ).pack(pady=(30, 5))
        
        ctk.CTkLabel(
            win, text="Por razones de seguridad, debes cambiar tu\ncontraseña temporal para continuar.", 
            font=ctk.CTkFont(size=12), text_color=TEXT_SEC
        ).pack(pady=(0, 20))
        
        # Nueva Contraseña
        entry_new = ctk.CTkEntry(win, placeholder_text="Nueva contraseña", show="•", width=300, height=40)
        entry_new.pack(pady=10)
        
        # Confirmar
        entry_conf = ctk.CTkEntry(win, placeholder_text="Confirmar contraseña", show="•", width=300, height=40)
        entry_conf.pack(pady=10)
        
        # Error Label
        lbl_err = ctk.CTkLabel(win, text="", text_color=ERROR_COLOR, font=ctk.CTkFont(size=12))
        lbl_err.pack(pady=5)
        
        def _on_guardar():
            p1 = entry_new.get()
            p2 = entry_conf.get()
            
            if len(p1) < 6:
                lbl_err.configure(text="Mínimo 6 caracteres.")
                return
            if p1 != p2:
                lbl_err.configure(text="Las contraseñas no coinciden.")
                return
                
            btn_guardar.configure(state="disabled", text="Guardando...")
            
            from api.client import cambiar_password
            def _task():
                res = cambiar_password(perfil["id"], p1)
                def _ui():
                    if res:
                        messagebox.showinfo("Éxito", "Contraseña actualizada. Bienvenido.")
                        win.destroy()
                        perfil["require_password_change"] = False
                        self._finalizar_login(perfil)
                    else:
                        btn_guardar.configure(state="normal", text="Actualizar Contraseña")
                        lbl_err.configure(text="Error de conexión.")
                self.after(0, _ui)
            threading.Thread(target=_task, daemon=True).start()
            
        btn_guardar = ctk.CTkButton(
            win, text="Actualizar Contraseña", width=300, height=40,
            fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER,
            command=_on_guardar
        )
        btn_guardar.pack(pady=(10, 0))

    def _mostrar_error(self, mensaje: str):
        self.lbl_error.configure(text=f"⚠ {mensaje}")
