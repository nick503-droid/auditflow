import subprocess
import os
import signal
import time
from datetime import datetime
from core.audio_recorder import GrabadorAudio

CARPETA_TEMPORAL = os.path.join(os.path.expanduser("~"), "AuditFlow_Temp")
os.makedirs(CARPETA_TEMPORAL, exist_ok=True)

CARPETA_LOGS = os.path.join(CARPETA_TEMPORAL, "logs")
os.makedirs(CARPETA_LOGS, exist_ok=True)


class GrabadorPantalla:
    def __init__(self):
        self.proceso_video: subprocess.Popen | None = None
        self.grabador_audio: GrabadorAudio | None = None
        self.con_audio = False

        self.rutas_video_temp = []
        self.ruta_audio_temp: str | None = None
        self.ruta_final: str | None = None

        self.archivo_log = None
        # Timestamp tomado inmediatamente después de lanzar el proceso FFmpeg principal
        self.timestamp_video_inicio: float | None = None
        
        self.estado = "detenido" # detenido, grabando, pausado
        self._identificador_base = ""

    def _lanzar_ffmpeg(self) -> str:
        """Inicia un nuevo fragmento de grabación con FFmpeg."""
        idx = len(self.rutas_video_temp)
        ruta_fragmento = os.path.join(CARPETA_TEMPORAL, f"video_{self._identificador_base}_part{idx}.mp4")
        ruta_log = os.path.join(CARPETA_LOGS, f"ffmpeg_{self._identificador_base}_part{idx}.log")
        
        comando = [
            "ffmpeg", "-y",
            "-f", "gdigrab",
            "-framerate", "15",
            # Usa el reloj de pared real para timestamps de cada frame.
            "-use_wallclock_as_timestamps", "1",
            "-i", "desktop",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx265",
            "-preset", "fast",
            "-crf", "28",
            ruta_fragmento,
        ]

        self.archivo_log = open(ruta_log, "w")
        self.proceso_video = subprocess.Popen(
            comando,
            stdin=subprocess.PIPE,
            stdout=self.archivo_log,
            stderr=self.archivo_log,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        self.rutas_video_temp.append(ruta_fragmento)
        return ruta_fragmento

    def _detener_ffmpeg_actual(self):
        """Detiene de forma segura el fragmento actual de FFmpeg."""
        if self.proceso_video:
            try:
                # Enviar 'q' a stdin para finalizar limpiamente y asegurar cierre
                if self.proceso_video.stdin:
                    self.proceso_video.communicate(b"q\n", timeout=10)
                else:
                    os.kill(self.proceso_video.pid, signal.CTRL_BREAK_EVENT)
                    self.proceso_video.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Si se cuelga, matar el grupo de procesos como contingencia
                try:
                    os.kill(self.proceso_video.pid, signal.CTRL_BREAK_EVENT)
                    self.proceso_video.wait(timeout=5)
                except (subprocess.TimeoutExpired, OSError, Exception):
                    self.proceso_video.kill()
            except Exception:
                self.proceso_video.kill()
            self.proceso_video = None
            
        if self.archivo_log:
            self.archivo_log.close()
            self.archivo_log = None

    def iniciar(self, con_audio: bool = False) -> str:
        self.con_audio = con_audio
        self._identificador_base = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.rutas_video_temp = []
        
        self.ruta_final = os.path.join(CARPETA_TEMPORAL, f"bitacora_{self._identificador_base}.mp4")

        # Iniciar video
        self._lanzar_ffmpeg()
        self.timestamp_video_inicio = time.time()
        
        # Iniciar audio
        if con_audio:
            self.ruta_audio_temp = os.path.join(CARPETA_TEMPORAL, f"audio_{self._identificador_base}.wav")
            self.grabador_audio = GrabadorAudio()
            self.grabador_audio.iniciar(self.ruta_audio_temp)

        self.estado = "grabando"
        return self.ruta_final

    def pausar(self):
        if self.estado == "grabando":
            self._detener_ffmpeg_actual()
            if self.con_audio and self.grabador_audio:
                self.grabador_audio.pausar()
            self.estado = "pausado"

    def reanudar(self):
        if self.estado == "pausado":
            self._lanzar_ffmpeg()
            if self.con_audio and self.grabador_audio:
                self.grabador_audio.reanudar()
            self.estado = "grabando"

    def detener(self) -> str | None:
        if self.estado == "detenido":
            return None

        # 1. Detener el video actual (si estaba grabando)
        if self.estado == "grabando":
            self._detener_ffmpeg_actual()

        # 2. Detener el audio
        if self.con_audio and self.grabador_audio:
            self.grabador_audio.detener()

        # 3. Concatenar los fragmentos de video
        video_unificado = None
        if len(self.rutas_video_temp) == 1:
            video_unificado = self.rutas_video_temp[0]
        elif len(self.rutas_video_temp) > 1:
            # Escribir el archivo concat
            ruta_concat = os.path.join(CARPETA_TEMPORAL, f"concat_{self._identificador_base}.txt")
            with open(ruta_concat, "w", encoding="utf-8") as f:
                for ruta in self.rutas_video_temp:
                    # ffmpeg concat requiere barras normales o rutas seguras
                    ruta_segura = ruta.replace("\\", "/")
                    f.write(f"file '{ruta_segura}'\n")
            
            video_unificado = os.path.join(CARPETA_TEMPORAL, f"video_unido_{self._identificador_base}.mp4")
            comando_concat = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", ruta_concat,
                "-c", "copy",
                video_unificado
            ]
            subprocess.run(comando_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Limpiar concat list
            if os.path.exists(ruta_concat):
                os.remove(ruta_concat)

        if not video_unificado or not os.path.exists(video_unificado):
            self.estado = "detenido"
            return None

        # 4. Unir video + audio en el archivo final
        if self.con_audio and self.ruta_audio_temp and os.path.exists(self.ruta_audio_temp):
            self._unir_video_y_audio(video_unificado)
        else:
            os.replace(video_unificado, self.ruta_final)

        # 5. Limpieza general
        for fragmento in self.rutas_video_temp:
            if fragmento != video_unificado and os.path.exists(fragmento):
                os.remove(fragmento)
        if video_unificado != self.ruta_final and os.path.exists(video_unificado):
            os.remove(video_unificado)

        self.proceso_video = None
        self.grabador_audio = None
        self.estado = "detenido"
        self.rutas_video_temp = []
        
        return self.ruta_final

    def _unir_video_y_audio(self, ruta_video: str):
        """
        Combina el .mp4 (solo video) y el .wav (solo audio) en un único
        archivo final.
        """
        ts_video = self.timestamp_video_inicio or 0.0
        ts_audio = (
            self.grabador_audio.timestamp_inicio_real
            if self.grabador_audio and self.grabador_audio.timestamp_inicio_real is not None
            else 0.0
        )

        diferencia_segundos = ts_audio - ts_video
        abs_diff = abs(diferencia_segundos)

        if diferencia_segundos >= 0:
            comando = [
                "ffmpeg", "-y",
                "-i", ruta_video,
                "-itsoffset", f"{abs_diff:.6f}",
                "-i", self.ruta_audio_temp,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                self.ruta_final,
            ]
        else:
            comando = [
                "ffmpeg", "-y",
                "-itsoffset", f"{abs_diff:.6f}",
                "-i", ruta_video,
                "-i", self.ruta_audio_temp,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                self.ruta_final,
            ]

        subprocess.run(
            comando,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if os.path.exists(self.ruta_audio_temp):
            os.remove(self.ruta_audio_temp)

def es_archivo_grabado(ruta: str) -> bool:
    """
    True si el archivo vive dentro de la carpeta temporal de grabaciones.
    """
    try:
        ruta_absoluta = os.path.abspath(ruta)
        return os.path.commonpath([ruta_absoluta, CARPETA_TEMPORAL]) == CARPETA_TEMPORAL
    except ValueError:
        return False