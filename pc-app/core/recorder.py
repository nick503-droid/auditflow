import subprocess
import os
import signal
import time
from datetime import datetime
from core.audio_recorder import GrabadorAudio
import sys

def obtener_ruta_ffmpeg() -> str:
    """Retorna la ruta segura a ffmpeg, ya sea empaquetado por PyInstaller o local."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, 'ffmpeg.exe')
    
    # Fallback desarrollo: Raíz del proyecto o PATH
    ruta_raiz = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ffmpeg.exe')
    if os.path.exists(ruta_raiz):
        return ruta_raiz
        
    return 'ffmpeg'


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
        self.ruta_final: str | None = None

        self.archivo_log = None
        self.timestamps_video_inicio = []
        
        self.estado = "detenido" # detenido, grabando, pausado
        self._identificador_base = ""

    def _lanzar_ffmpeg(self) -> str:
        """Inicia un nuevo fragmento de grabación con FFmpeg."""
        idx = len(self.rutas_video_temp)
        ruta_fragmento = os.path.join(CARPETA_TEMPORAL, f"video_{self._identificador_base}_part{idx}.mp4")
        ruta_log = os.path.join(CARPETA_LOGS, f"ffmpeg_{self._identificador_base}_part{idx}.log")
        
        comando = [
            obtener_ruta_ffmpeg(), "-y",
            "-f", "gdigrab",
            "-framerate", "15",
            # Cada segmento debe iniciar en PTS 0. Usar el reloj de pared aquí
            # deja timestamps absolutos distintos en cada pausa y rompe el
            # concat de audio/video en algunos equipos.
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
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
        )
        self.timestamps_video_inicio.append(time.time())
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
        self.timestamps_video_inicio = []
        
        self.ruta_final = os.path.join(CARPETA_TEMPORAL, f"bitacora_{self._identificador_base}.mp4")

        # Iniciar video
        self._lanzar_ffmpeg()
        
        # Iniciar audio
        if con_audio:
            self.grabador_audio = GrabadorAudio()
            self.grabador_audio.iniciar(self._identificador_base)

        self.estado = "grabando"
        return self.ruta_final

    def pausar(self):
        if self.estado == "grabando":
            # Cortar primero el audio evita que siga agregando muestras mientras
            # FFmpeg termina de cerrar el video actual.
            if self.con_audio and self.grabador_audio:
                self.grabador_audio.pausar()
            self._detener_ffmpeg_actual()
            self.estado = "pausado"

    def reanudar(self):
        if self.estado == "pausado":
            # Reiniciar primero el capturador de audio conserva el orden de los
            # fragmentos; los timestamps reales corrigen la latencia de arranque.
            if self.con_audio and self.grabador_audio:
                self.grabador_audio.reanudar()
            self._lanzar_ffmpeg()
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

        # 3. Muxing por fragmento
        rutas_para_concat = []
        if self.con_audio and self.grabador_audio:
            for i, ruta_vid in enumerate(self.rutas_video_temp):
                if i < len(self.grabador_audio.rutas_audio_temp):
                    ruta_aud = self.grabador_audio.rutas_audio_temp[i]
                    ts_vid = self.timestamps_video_inicio[i] if i < len(self.timestamps_video_inicio) else 0
                    ts_aud = self.grabador_audio.timestamps_inicio_fragmentos[i] if i < len(self.grabador_audio.timestamps_inicio_fragmentos) else 0
                    
                    diff = ts_aud - ts_vid
                    abs_diff = abs(diff)
                    ruta_mux = os.path.join(CARPETA_TEMPORAL, f"mux_{self._identificador_base}_part{i}.mp4")
                    
                    # Reiniciar PTS de ambas pistas es crítico: al pausar se
                    # crean procesos nuevos y sus timestamps no son compatibles
                    # para copiar/concatenar directamente. El desfase medido se
                    # aplica como silencio/frames negros, nunca con itsoffset.
                    if diff >= 0:
                        filtro = (
                            "[0:v]setpts=PTS-STARTPTS[v];"
                            f"[1:a]asetpts=PTS-STARTPTS,adelay={round(abs_diff * 1000)}:all=1[a]"
                        )
                    else:
                        filtro = (
                            f"[0:v]setpts=PTS-STARTPTS,"
                            f"tpad=start_duration={abs_diff:.6f}:start_mode=add[v];"
                            "[1:a]asetpts=PTS-STARTPTS[a]"
                        )

                    comando = [
                        obtener_ruta_ffmpeg(), "-y",
                        "-i", ruta_vid,
                        "-i", ruta_aud,
                        "-filter_complex", filtro,
                        "-map", "[v]",
                        "-map", "[a]",
                        # Re-encode por fragmento deja PTS 0 y codecs idénticos;
                        # stream copy conservaba los timestamps inválidos.
                        "-c:v", "libx265",
                        "-preset", "fast",
                        "-crf", "28",
                        "-pix_fmt", "yuv420p",
                        "-c:a", "aac",
                        "-shortest",
                        "-movflags", "+faststart",
                        ruta_mux,
                    ]

                    ruta_log_mux = os.path.join(
                        CARPETA_LOGS, f"mux_{self._identificador_base}_part{i}.log"
                    )
                    with open(ruta_log_mux, "w", encoding="utf-8") as log_mux:
                        resultado = subprocess.run(
                            comando,
                            stdout=log_mux,
                            stderr=log_mux,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                    # Si un codec/dispositivo concreto falla, conservar el video
                    # en lugar de generar una grabación final corrupta.
                    rutas_para_concat.append(ruta_mux if resultado.returncode == 0 and os.path.exists(ruta_mux) else ruta_vid)
                else:
                    rutas_para_concat.append(ruta_vid)
        else:
            rutas_para_concat = self.rutas_video_temp

        # 4. Concatenar los fragmentos de video
        if len(rutas_para_concat) == 1:
            os.replace(rutas_para_concat[0], self.ruta_final)
        elif len(rutas_para_concat) > 1:
            # Escribir el archivo concat
            ruta_concat = os.path.join(CARPETA_TEMPORAL, f"concat_{self._identificador_base}.txt")
            with open(ruta_concat, "w", encoding="utf-8") as f:
                for ruta in rutas_para_concat:
                    # ffmpeg concat requiere barras normales o rutas seguras
                    ruta_segura = ruta.replace("\\", "/")
                    f.write(f"file '{ruta_segura}'\n")
            
            comando_concat = [
                obtener_ruta_ffmpeg(), "-y",
                "-f", "concat",
                "-safe", "0",
                "-fflags", "+genpts",
                "-i", ruta_concat,
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                self.ruta_final
            ]
            subprocess.run(
                comando_concat, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Limpiar concat list
            if os.path.exists(ruta_concat):
                os.remove(ruta_concat)

        # 5. Limpieza general
        for fragmento in self.rutas_video_temp:
            if fragmento != self.ruta_final and os.path.exists(fragmento):
                os.remove(fragmento)
                
        if self.con_audio and self.grabador_audio:
            for fragmento_aud in self.grabador_audio.rutas_audio_temp:
                if os.path.exists(fragmento_aud):
                    os.remove(fragmento_aud)
            for mux_vid in rutas_para_concat:
                if mux_vid != self.ruta_final and os.path.exists(mux_vid):
                    os.remove(mux_vid)

        self.proceso_video = None
        self.grabador_audio = None
        self.estado = "detenido"
        self.rutas_video_temp = []
        
        return self.ruta_final

def es_archivo_grabado(ruta: str) -> bool:
    """
    True si el archivo vive dentro de la carpeta temporal de grabaciones.
    """
    try:
        ruta_absoluta = os.path.abspath(ruta)
        return os.path.commonpath([ruta_absoluta, CARPETA_TEMPORAL]) == CARPETA_TEMPORAL
    except ValueError:
        return False
