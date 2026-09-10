import customtkinter as ctk
from tkinter import messagebox
import threading
from api.client import login
import session

from ui.theme import (
    APP_BACKGROUND, SURFACE, SURFACE_SECONDARY, BORDER, BORDER_FOCUS,
    PRIMARY, PRIMARY_HOVER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    RADIUS_PANEL, RADIUS_BUTTON, get_font, STATUS
)


class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, controlador, **kwargs):
        super().__init__(master, fg_color=APP_BACKGROUND, **kwargs)
        self.controlador = controlador

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_ui()

    def _construir_ui(self):
        # Tarjeta central (ancho fijo, centrada)
        card = ctk.CTkFrame(
            self,
            fg_color=SURFACE,
            corner_radius=RADIUS_PANEL,
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
            font=get_font(size=52)
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            inner,
            text="AuditFlow",
            font=get_font(size=28, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack()

        ctk.CTkLabel(
            inner,
            text="Inicia sesión para continuar",
            font=get_font(size=13),
            text_color=TEXT_SECONDARY
        ).pack(pady=(2, 30))

        # Campo usuario
        ctk.CTkLabel(inner, text="Usuario", font=get_font(size=13, weight="bold"),
                     text_color=TEXT_SECONDARY, anchor="w").pack(fill="x")
        self.entry_user = ctk.CTkEntry(
            inner,
            placeholder_text="Ingresa tu usuario",
            fg_color=APP_BACKGROUND,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            height=42,
            corner_radius=RADIUS_BUTTON,
            font=get_font(size=14)
        )
        self.entry_user.pack(fill="x", pady=(4, 16))
        self.entry_user.bind("<Return>", lambda e: self.entry_pass.focus())

        # Campo contraseña
        ctk.CTkLabel(inner, text="Contraseña", font=get_font(size=13, weight="bold"),
                     text_color=TEXT_SECONDARY, anchor="w").pack(fill="x")
        self.entry_pass = ctk.CTkEntry(
            inner,
            placeholder_text="••••••••",
            show="•",
            fg_color=APP_BACKGROUND,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            height=42,
            corner_radius=RADIUS_BUTTON,
            font=get_font(size=14)
        )
        self.entry_pass.pack(fill="x", pady=(4, 6))
        self.entry_pass.bind("<Return>", lambda e: self._on_login())

        # Mensaje de error (oculto por defecto)
        self.lbl_error = ctk.CTkLabel(
            inner,
            text="",
            font=get_font(size=12),
            text_color=STATUS["error"]["text"]
        )
        self.lbl_error.pack(pady=(0, 10))

        # Botón de login
        self.btn_login = ctk.CTkButton(
            inner,
            text="Ingresar →",
            command=self._on_login,
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            font=get_font(size=14, weight="bold"),
            text_color="#FFFFFF",
            height=46,
            corner_radius=RADIUS_BUTTON
        )
        self.btn_login.pack(fill="x")

        # Footer
        ctk.CTkLabel(
            inner,
            text="AuditFlow v1.0 — Sistema de Auditoría",
            font=get_font(size=11),
            text_color=TEXT_MUTED
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
        win.configure(fg_color=APP_BACKGROUND)
        win.grab_set()

        def _on_close():
            self.entry_pass.delete(0, "end")
            win.destroy()
        
        win.protocol("WM_DELETE_WINDOW", _on_close)
        
        ctk.CTkLabel(
            win, text="Cambio Requerido", 
            font=get_font(size=22, weight="bold"), text_color=TEXT_PRIMARY
        ).pack(pady=(30, 5))
        
        ctk.CTkLabel(
            win, text="Por razones de seguridad, debes cambiar tu\ncontraseña temporal para continuar.", 
            font=get_font(size=12), text_color=TEXT_SECONDARY
        ).pack(pady=(0, 20))
        
        # Nueva Contraseña
        entry_new = ctk.CTkEntry(win, placeholder_text="Nueva contraseña", show="•", width=300, height=40, fg_color=SURFACE, border_color=BORDER, text_color=TEXT_PRIMARY)
        entry_new.pack(pady=10)
        
        # Confirmar
        entry_conf = ctk.CTkEntry(win, placeholder_text="Confirmar contraseña", show="•", width=300, height=40, fg_color=SURFACE, border_color=BORDER, text_color=TEXT_PRIMARY)
        entry_conf.pack(pady=10)
        
        # Error Label
        lbl_err = ctk.CTkLabel(win, text="", text_color=STATUS["error"]["text"], font=get_font(size=12))
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
            fg_color=PRIMARY, hover_color=PRIMARY_HOVER,
            text_color="#FFFFFF", font=get_font(size=14, weight="bold"),
            corner_radius=RADIUS_BUTTON, command=_on_guardar
        )
        btn_guardar.pack(pady=(10, 0))

    def _mostrar_error(self, mensaje: str):
        self.lbl_error.configure(text=f"⚠ {mensaje}")
