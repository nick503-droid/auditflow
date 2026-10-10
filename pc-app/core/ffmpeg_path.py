"""Resolver FFmpeg sin importar el grabador ni inicializar audio/carpetas."""
import os
import sys


def obtener_ruta_ffmpeg():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "ffmpeg.exe")
    local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ffmpeg.exe")
    return local if os.path.isfile(local) else "ffmpeg"
