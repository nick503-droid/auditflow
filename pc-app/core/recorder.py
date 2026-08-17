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

        self.ruta_video_temp: str | None = None
        self.ruta_audio_temp: str | None = None
        self.ruta_final: str | None = None

        self.archivo_log = None
        # Timestamp tomado inmediatamente después de lanzar el proceso FFmpeg
        # (aproximación del inicio real de gdigrab; el inicio verdadero no es
        # observable desde Python, pero sirve como referencia base).
        self.timestamp_video_inicio: float | None = None

    def iniciar(self, con_audio: bool = False) -> str:
        self.con_audio = con_audio
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Mientras graba, video y audio (si aplica) quedan en archivos
        # SEPARADOS. Se unen hasta que detengas la grabación.
        self.ruta_video_temp = os.path.join(CARPETA_TEMPORAL, f"video_{timestamp}.mp4")
        self.ruta_final = os.path.join(CARPETA_TEMPORAL, f"bitacora_{timestamp}.mp4")
        ruta_log = os.path.join(CARPETA_LOGS, f"ffmpeg_{timestamp}.log")

        comando = [
            "ffmpeg", "-y",
            "-f", "gdigrab",
            "-framerate", "15",
            # Usa el reloj de pared real para timestamps de cada frame.
            # Evita drift acumulativo en grabaciones largas con gdigrab,
            # donde FFmpeg asume framerate perfecto si no se especifica esto.
            "-use_wallclock_as_timestamps", "1",
            "-i", "desktop",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx265",
            "-preset", "fast",
            "-crf", "28",
            self.ruta_video_temp,
        ]

        self.archivo_log = open(ruta_log, "w")
        self.proceso_video = subprocess.Popen(
            comando,
            stdout=self.archivo_log,
            stderr=self.archivo_log,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        # Aproximación del inicio real de gdigrab. FFmpeg aún no capturó
        # el primer frame en este punto, pero la diferencia suele ser
        # pequeña y constante (~0.1-0.5 s), aceptable como referencia base.
        self.timestamp_video_inicio = time.time()

        if con_audio:
            self.ruta_audio_temp = os.path.join(CARPETA_TEMPORAL, f"audio_{timestamp}.wav")
            self.grabador_audio = GrabadorAudio()
            self.grabador_audio.iniciar(self.ruta_audio_temp)

        return self.ruta_final

    def detener(self) -> str | None:
        if self.proceso_video is None:
            return None

        # 1. Detener el video (mismo mecanismo de antes, ya probado)
        self.proceso_video.send_signal(signal.CTRL_BREAK_EVENT)
        try:
            self.proceso_video.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proceso_video.kill()

        if self.archivo_log:
            self.archivo_log.close()
            self.archivo_log = None

        # 2. Detener el audio, si estaba grabando
        if self.con_audio and self.grabador_audio:
            self.grabador_audio.detener()

        # 3. Unir video + audio en un solo archivo final, o si no había
        # audio, simplemente renombrar el video como el archivo final
        if self.con_audio and self.ruta_audio_temp and os.path.exists(self.ruta_audio_temp):
            self._unir_video_y_audio()
        else:
            os.replace(self.ruta_video_temp, self.ruta_final)

        self.proceso_video = None
        self.grabador_audio = None
        return self.ruta_final

    def _unir_video_y_audio(self):
        """
        Combina el .mp4 (solo video) y el .wav (solo audio) en un único
        archivo final. '-c:v copy' significa 'no vuelvas a comprimir el
        video, solo cópialo tal cual' — por eso este paso es casi
        instantáneo, sin importar cuánto dure el video.

        Aplica '-itsoffset' para compensar el desfase de inicio entre
        gdigrab (proceso externo, arranca más lento) y el hilo de audio
        (arranca más rápido). El offset se calcula con timestamps reales
        tomados en cada stream al momento de su primer dato capturado.
        """
        # --- Cálculo del offset de sincronización ---
        ts_video = self.timestamp_video_inicio or 0.0
        ts_audio = (
            self.grabador_audio.timestamp_inicio_real
            if self.grabador_audio and self.grabador_audio.timestamp_inicio_real is not None
            else 0.0
        )

        diferencia_segundos = ts_audio - ts_video
        print(f"[AuditFlow] Offset audio-video medido: {diferencia_segundos:+.4f} s "
              f"(video_t0={ts_video:.4f}, audio_t0={ts_audio:.4f})")

        # --- Construcción del comando de muxing con offset ---
        # Caso más común: audio empezó DESPUÉS del video (diferencia > 0).
        #   → retrasamos el audio con -itsoffset positivo sobre el input de audio.
        # Caso inverso: audio empezó ANTES del video (diferencia < 0).
        #   → retrasamos el video con -itsoffset positivo sobre el input de video.
        abs_diff = abs(diferencia_segundos)

        if diferencia_segundos >= 0:
            # El audio llegó tarde: lo adelantamos en la línea de tiempo
            # retrasándolo (paradoja de itsoffset: offset positivo = retraso
            # del stream de entrada siguiente)
            comando = [
                "ffmpeg", "-y",
                "-i", self.ruta_video_temp,
                "-itsoffset", f"{abs_diff:.6f}",
                "-i", self.ruta_audio_temp,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                self.ruta_final,
            ]
        else:
            # El video llegó tarde: aplicamos offset al input de video
            comando = [
                "ffmpeg", "-y",
                "-itsoffset", f"{abs_diff:.6f}",
                "-i", self.ruta_video_temp,
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

        # Limpieza: ya no necesitamos los archivos intermedios
        if os.path.exists(self.ruta_video_temp):
            os.remove(self.ruta_video_temp)
        if os.path.exists(self.ruta_audio_temp):
            os.remove(self.ruta_audio_temp)


def es_archivo_grabado(ruta: str) -> bool:
    """
    True si el archivo vive dentro de la carpeta temporal de grabaciones
    (fue generado por esta app), False si es un archivo que el usuario
    adjunto manualmente desde otra ubicacion.
    """
    try:
        ruta_absoluta = os.path.abspath(ruta)
        return os.path.commonpath([ruta_absoluta, CARPETA_TEMPORAL]) == CARPETA_TEMPORAL
    except ValueError:
        return False