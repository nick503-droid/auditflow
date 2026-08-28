import os
from PIL import Image
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
import tempfile
import requests

def generar_miniatura(ruta_o_url: str, size=(120, 120)) -> Image.Image | None:
    """
    Genera un objeto PIL Image a partir de una ruta de imagen o video local, o URL.
    """
    es_url = ruta_o_url.startswith("http://") or ruta_o_url.startswith("https://")
    ruta_local = ruta_o_url
    
    # Si es URL, descargamos temporalmente
    temp_file = None
    if es_url:
        try:
            resp = requests.get(ruta_o_url, stream=True, timeout=5)
            resp.raise_for_status()
            ext = os.path.splitext(ruta_o_url)[1].lower()
            if not ext:
                ext = ".mp4" if "mp4" in ruta_o_url else ".jpg"
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            for chunk in resp.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_file.close()
            ruta_local = temp_file.name
        except Exception:
            return None

    img = None
    ext = os.path.splitext(ruta_local)[1].lower()
    
    if ext in [".jpg", ".jpeg", ".png", ".bmp"]:
        try:
            img = Image.open(ruta_local).copy()
            img.thumbnail(size)
        except Exception:
            pass
    elif ext in [".mp4", ".avi", ".mkv", ".mov", ".webm"]:
        if CV2_AVAILABLE:
            try:
                cap = cv2.VideoCapture(ruta_local)
                success, frame = cap.read()
                cap.release()
                if success:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)
                    img.thumbnail(size)
            except Exception:
                pass
                
    # Retorno seguro si falla todo (Devuelve un color base como placeholder)
    if not img:
        img = Image.new("RGB", size, color="#1e293b")
            
    # Limpiar archivo temporal si lo creamos
    if temp_file and os.path.exists(temp_file.name):
        try:
            os.remove(temp_file.name)
        except:
            pass
            
    return img
