"""Diseño aislado: no toca API, audio, credenciales ni datos del usuario."""
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pc-app"))
from ui import theme
from ui.icons import ICON_NAMES, get_icon, render_icon, _cached_icon
from ui.visual_widgets import IconButton, IconLabel, presentation_text
import customtkinter as ctk
from PIL import Image


def contrast(a, b):
    def luminance(value):
        channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
    x, y = sorted((luminance(a), luminance(b)))
    return (y + .05) / (x + .05)


class PaletteTests(unittest.TestCase):
    def test_text_has_aa_contrast_on_surfaces_in_both_modes(self):
        for mode in ("Light", "Dark"):
            for text in (theme.TEXT_PRIMARY, theme.TEXT_SECONDARY, theme.TEXT_MUTED):
                for surface in (theme.APP_BACKGROUND, theme.SURFACE, theme.SURFACE_SECONDARY):
                    with self.subTest(mode=mode, text=text, surface=surface):
                        self.assertGreaterEqual(contrast(theme.resolve_color(text, mode), theme.resolve_color(surface, mode)), 4.5)

    def test_buttons_and_status_text_have_aa_contrast(self):
        for mode in ("Light", "Dark"):
            for name, state in theme.STATUS.items():
                with self.subTest(mode=mode, state=name):
                    self.assertGreaterEqual(contrast(theme.resolve_color(state["text"], mode), theme.resolve_color(state["bg"], mode)), 4.5)
                    if "hover_bg" in state:
                        self.assertGreaterEqual(contrast(theme.resolve_color(state["text"], mode), theme.resolve_color(state["hover_bg"], mode)), 4.5)
                    self.assertGreaterEqual(contrast("#FFFFFF", theme.resolve_color(state["solid"], mode)), 4.5)
                    for surface in (theme.APP_BACKGROUND, theme.SURFACE, theme.SURFACE_SECONDARY):
                        self.assertGreaterEqual(contrast(theme.resolve_color(state["text"], mode), theme.resolve_color(surface, mode)), 4.5)
            self.assertGreaterEqual(contrast("#FFFFFF", theme.resolve_color(theme.PRIMARY, mode)), 4.5)

    def test_theme_is_packaged_and_complete(self):
        path = REPO / "pc-app/ui/auditflow_theme.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        ctk.set_default_color_theme(str(path))
        for name in ("CTk", "CTkButton", "CTkLabel", "CTkEntry", "CTkTextbox", "DropdownMenu"):
            self.assertIn(name, data)
        self.assertEqual(data["CTk"]["fg_color"], list(theme.APP_BACKGROUND))
        self.assertIn("ui/auditflow_theme.json", (REPO / "pc-app/main.spec").read_text())

    def test_calendar_uses_native_colors(self):
        for mode in ("Light", "Dark"):
            palette = theme.calendar_colors(mode)
            self.assertTrue(all(isinstance(value, str) and value.startswith("#") for value in palette.values()))
            self.assertEqual(palette["foreground"], theme.resolve_color(theme.TEXT_PRIMARY, mode))

    def test_preference_is_separate_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "appearance.json"
            with patch.object(ctk, "set_appearance_mode") as setter:
                self.assertEqual(theme.load_appearance(target), "Light")
                self.assertTrue(theme.set_appearance("Dark", target))
                setter.assert_called_once_with("Dark")
            self.assertEqual(theme.load_appearance(target), "Dark")
            self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_invalid_or_readonly_preferences_do_not_break_ui(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "appearance.json"
            for contents in ("broken", "[]", '{"mode":"invalid"}'):
                target.write_text(contents)
                self.assertEqual(theme.load_appearance(target), "Light")
            with patch.object(ctk, "set_appearance_mode"), patch.object(Path, "write_text", side_effect=PermissionError):
                self.assertFalse(theme.set_appearance("Dark", target))
            with self.assertRaises(ValueError): theme.set_appearance("unknown", target)


class IconTests(unittest.TestCase):
    def test_every_icon_has_transparent_background_and_a_real_shape(self):
        for name in ICON_NAMES:
            with self.subTest(icon=name):
                image = render_icon(name, "#38BDF8")
                self.assertEqual(image.mode, "RGBA")
                alpha = image.getchannel("A")
                self.assertIsNotNone(alpha.getbbox())
                self.assertEqual(alpha.getpixel((0, 0)), 0)
                self.assertLess(sum(alpha.histogram()[1:]), image.width * image.height * .6)

    def test_icons_reuse_cache_and_have_two_colors(self):
        first = get_icon("eye", color=theme.TEXT_PRIMARY)
        second = get_icon("eye", color=list(theme.TEXT_PRIMARY))
        self.assertIs(first, second)
        self.assertNotEqual(first.cget("light_image").tobytes(), first.cget("dark_image").tobytes())
        self.assertIsNone(get_icon("does-not-exist"))
        self.assertEqual(_cached_icon.cache_info().maxsize, 256)

    def test_labels_keep_their_meaning_without_emoji_fonts(self):
        self.assertEqual(presentation_text("🗑️ Eliminar"), ("Eliminar", "trash-2"))
        self.assertEqual(presentation_text("⬇️ Descargar Selección"), ("Descargar Selección", "download"))
        self.assertEqual(presentation_text("🕒 12:30 · 🏪 Local · 👤 Auditor"), ("12:30 · Restaurante: Local · Autor: Auditor", "clock"))
        self.assertEqual(presentation_text("Texto sin adornos"), ("Texto sin adornos", None))
        self.assertEqual(presentation_text("🕒 Fecha: hoy · 🏪 Restaurante: Local · 👤 Autor: Auditor"), ("Fecha: hoy · Restaurante: Local · Autor: Auditor", "clock"))


@unittest.skipIf(sys.platform != "win32" and not os.environ.get("DISPLAY"), "Requiere una sesión gráfica")
class WidgetThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _cached_icon.cache_clear()
        theme.initialize_appearance()
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        for job in cls.root.tk.call("after", "info"):
            cls.root.after_cancel(job)
        cls.root.destroy()
        _cached_icon.cache_clear()
        gc.collect()

    def test_theme_switch_does_not_recreate_widgets_or_change_user_state(self):
        frame = ctk.CTkFrame(self.root, fg_color=theme.SURFACE)
        entry = ctk.CTkTextbox(frame)
        entry.insert("1.0", "Reporte pendiente: sin modificar.")
        entry.mark_set("insert", "1.7")
        selected = ctk.BooleanVar(value=True)
        checkbox = ctk.CTkCheckBox(frame, text="Evidencia", variable=selected)
        callback = Mock()
        button = IconButton(frame, text="👁️ Abrir", command=callback)
        children = tuple(frame.winfo_children())
        for mode in ("Dark", "Light") * 10:
            ctk.set_appearance_mode(mode)
            self.root.update_idletasks()
            self.assertEqual(tuple(frame.winfo_children()), children)
            self.assertEqual(entry.get("1.0", "end-1c"), "Reporte pendiente: sin modificar.")
            self.assertEqual(entry.index("insert"), "1.7")
            self.assertTrue(selected.get())
        button.invoke()
        callback.assert_called_once_with()
        frame.destroy()

    def test_dynamic_icons_and_photographs_are_not_confused(self):
        label = IconLabel(self.root, text="🖼", text_color=theme.TEXT_PRIMARY)
        self.assertIsNotNone(label.cget("image"))
        photo = ctk.CTkImage(light_image=Image.new("RGB", (20, 20), "red"), size=(20, 20))
        label.configure(text="", image=photo)
        label.configure(text_color=theme.TEXT_SECONDARY)
        self.assertIs(label.cget("image"), photo)
        button = IconButton(self.root, text="⏸️ Pausar")
        button.configure(text="▶️ Reanudar")
        self.assertEqual(button.cget("text"), "Reanudar")
        self.assertEqual(button._visual_icon, "play")
        button.configure(text="Procesando video…", state="disabled")
        self.assertIsNone(button.cget("image"))
        label.destroy()
        button.destroy()

    def test_transparent_buttons_do_not_use_solid_button_hover(self):
        button = IconButton(self.root, text="Adjuntar archivo", fg_color="transparent")
        self.assertEqual(button.cget("hover_color"), theme.SURFACE_SECONDARY)
        self.assertEqual(button.cget("text_color"), theme.TEXT_PRIMARY)
        button.destroy()

    def test_label_reserves_separate_space_for_icon_and_text_at_all_scales(self):
        label = IconLabel(self.root, text="📁 Directorio de Reportes",
                          font=theme.get_font(size=24, weight="bold"), anchor="w")
        plain = ctk.CTkLabel(self.root, text=label.cget("text"), font=label.cget("font"), padx=0)
        label.pack()
        plain.pack()
        try:
            for scale in (1, 1.25, 1.5, 2):
                ctk.set_widget_scaling(scale)
                for mode in ("Light", "Dark"):
                    ctk.set_appearance_mode(mode)
                    self.root.update_idletasks()
                    native = label._label
                    image_width = int(native.tk.call("image", "width", native.cget("image")))
                    self.assertEqual(label.cget("compound"), "left")
                    self.assertGreaterEqual(native.winfo_reqwidth(), plain._label.winfo_reqwidth() + image_width + 4)
        finally:
            label.destroy()
            plain.destroy()
            ctk.set_widget_scaling(1)

    def test_dynamic_label_removes_old_icon_pixels_and_can_add_a_new_icon(self):
        label = IconLabel(self.root, text="☁ En la nube")
        self.assertTrue(str(label._label.cget("image")))
        label.configure(text="Guardado local")
        self.assertIsNone(label.cget("image"))
        self.assertEqual(str(label._label.cget("image")), "")
        with patch.object(label._label, "configure", wraps=label._label.configure) as native_configure:
            label.configure(text="Guardado local", text_color=theme.TEXT_SECONDARY)
            self.assertFalse(any("image" in call.kwargs for call in native_configure.call_args_list))
        label.configure(text="📁 Directorio de Bitácoras")
        self.assertTrue(str(label._label.cget("image")))
        self.assertEqual(label.cget("compound"), "left")
        label.destroy()

    def test_explicit_image_layout_is_preserved_and_removal_is_not_ghosted(self):
        photo = ctk.CTkImage(light_image=Image.new("RGB", (24, 24), "red"), size=(24, 24))
        label = IconLabel(self.root, text="Fotografía", image=photo, compound="top", padx=8)
        self.assertEqual(label.cget("compound"), "top")
        self.assertEqual(int(label.cget("padx")), 8)
        label.configure(text="", image=None)
        self.assertEqual(str(label._label.cget("image")), "")
        label.destroy()

    def test_icon_only_labels_and_dynamic_button_sizes_still_work(self):
        label = IconLabel(self.root, text="📁", font=theme.get_font(size=48))
        self.assertEqual(label.cget("text"), "")
        self.assertIsNotNone(label.cget("image"))
        button = IconButton(self.root, text="📷 Captura", font=theme.get_font(size=24), height=40)
        self.assertEqual(button.cget("image").cget("size"), (24, 24))
        button.configure(height=24)
        self.assertEqual(button.cget("image").cget("size"), (18, 18))
        label.destroy()
        button.destroy()

    def test_destroyed_widgets_do_not_accumulate_icon_callbacks(self):
        image = get_icon("trash-2", (16, 16), "#FFFFFF")
        initial = len(image._configure_callback_list)
        for _ in range(50):
            button = IconButton(self.root, text="🗑", font=("Segoe UI", 16))
            button.destroy()
        self.assertEqual(len(image._configure_callback_list), initial)

    def test_full_modules_in_isolated_process_without_real_data(self):
        with tempfile.TemporaryDirectory() as folder:
            environment = {**os.environ, "APPDATA": folder}
            result = subprocess.run(
                [sys.executable, "-B", str(REPO / "tests/pc_appearance_fixture.py"), "--smoke", "--contrast"],
                capture_output=True, text=True, timeout=45, env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Full UI smoke OK", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn("CONTRAST", result.stdout)


if __name__ == "__main__":
    unittest.main()
