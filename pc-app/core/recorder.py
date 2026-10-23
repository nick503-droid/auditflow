import subprocess
import os
import time
from datetime import datetime
from core.audio_recorder import GrabadorAudio
import uuid
import threading
from core.ffmpeg_path import obtener_ruta_ffmpeg


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
        self._lock = threading.RLock()
        self._monitor_video = None

    def _entrada_video(self):
        return ["-f", "gdigrab", "-framerate", "30", "-i", "desktop"]

    def _calidad_video(self):
        # Resolución nativa (sin reducir ni inventar píxeles), H.264 compatible.
        return ["-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
                "-crf", "20", "-pix_fmt", "yuv420p"]

    def _lanzar_ffmpeg(self) -> str:
        """Inicia un nuevo fragmento de grabación con FFmpeg."""
        idx = len(self.rutas_video_temp)
        ruta_fragmento = os.path.join(CARPETA_TEMPORAL, f"video_{self._identificador_base}_part{idx}.mp4")
        ruta_log = os.path.join(CARPETA_LOGS, f"ffmpeg_{self._identificador_base}_part{idx}.log")
        self._ultimo_log_video = ruta_log
        
        comando = [obtener_ruta_ffmpeg(), "-y", "-nostats", "-stats_period", "0.1",
                   "-progress", "pipe:1", *self._entrada_video(),
                   "-vf", "setpts=PTS-STARTPTS,pad=ceil(iw/2)*2:ceil(ih/2)*2",
                   *self._calidad_video(), "-movflags", "+faststart", ruta_fragmento]

        self.archivo_log = open(ruta_log, "w")
        try:
            self.proceso_video = subprocess.Popen(
                comando, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.archivo_log,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            self.archivo_log.close()
            self.archivo_log = None
            raise
        self.rutas_video_temp.append(ruta_fragmento)
        listo = threading.Event()
        inicio = []
        def monitor():
            datos = {}
            try:
                for linea in iter(self.proceso_video.stdout.readline, b""):
                    key, _, value = linea.decode("utf-8", errors="replace").strip().partition("=")
                    datos[key] = value
                    if key == "progress" and not inicio and int(datos.get("frame", "0")) > 0:
                        inicio.append(time.monotonic() - max(0, int(datos.get("out_time_us", "0"))) / 1_000_000)
                        listo.set()
            finally:
                listo.set()
        self._monitor_video = threading.Thread(target=monitor, daemon=True, name="FFmpegProgress")
        self._monitor_video.start()
        if not listo.wait(8) or not inicio:
            self._detener_ffmpeg_actual()
            raise RuntimeError(f"FFmpeg no pudo iniciar el tramo {idx + 1}. Consulta {ruta_log}")
        self.timestamps_video_inicio.append(inicio[0])
        return ruta_fragmento

    def _detener_ffmpeg_actual(self):
        """Detiene de forma segura el fragmento actual de FFmpeg."""
        proceso = self.proceso_video
        if proceso:
            try:
                # Enviar 'q' a stdin para finalizar limpiamente y asegurar cierre
                if proceso.poll() is None and proceso.stdin:
                    proceso.stdin.write(b"q\n")
                    proceso.stdin.flush()
                proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait(timeout=5)
            except (BrokenPipeError, OSError):
                if proceso.poll() is None:
                    proceso.kill()
                proceso.wait(timeout=5)
            finally:
                if self._monitor_video:
                    self._monitor_video.join(timeout=2)
                    self._monitor_video = None
                for stream in (proceso.stdin, proceso.stdout):
                    if stream:
                        stream.close()
                self.proceso_video = None
            
        if self.archivo_log:
            self.archivo_log.close()
            self.archivo_log = None
        if proceso is not None and proceso.returncode not in (0, None):
            raise RuntimeError(f"Falló el capturador de pantalla. Consulta {self._ultimo_log_video}")

    def iniciar(self, con_audio: bool = False) -> str:
        with self._lock:
            return self._iniciar_seguro(con_audio)

    def _iniciar_seguro(self, con_audio=False):
        if self.estado != "detenido":
            raise RuntimeError("Ya hay una grabación en curso")
        try:
            return self._iniciar_captura(con_audio)
        except Exception:
            self._detener_ffmpeg_actual()
            if self.grabador_audio:
                try:
                    self.grabador_audio.detener()
                except Exception:
                    pass
            self.estado = "detenido"
            raise

    def _iniciar_captura(self, con_audio: bool = False) -> str:
        self.con_audio = con_audio
        self._identificador_base = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        self.rutas_video_temp = []
        self.timestamps_video_inicio = []
        
        self.ruta_final = os.path.join(CARPETA_TEMPORAL, f"bitacora_{self._identificador_base}.mp4")

        # Iniciar audio
        if con_audio:
            self.grabador_audio = GrabadorAudio()
            self.grabador_audio.iniciar(self._identificador_base)

        self._lanzar_ffmpeg()

        self.estado = "grabando"
        return self.ruta_final

    def pausar(self):
        with self._lock:
            return self._pausar_seguro()

    def _pausar_seguro(self):
        if self.estado == "grabando":
            # Cortar primero el audio evita que siga agregando muestras mientras
            # FFmpeg termina de cerrar el video actual.
            if self.con_audio and self.grabador_audio:
                self.grabador_audio.pausar()
            self._detener_ffmpeg_actual()
            self.estado = "pausado"

    def reanudar(self):
        with self._lock:
            return self._reanudar_seguro()

    def _reanudar_seguro(self):
        if self.estado == "pausado":
            # Reiniciar primero el capturador de audio conserva el orden de los
            # fragmentos; los timestamps reales corrigen la latencia de arranque.
            if self.con_audio and self.grabador_audio:
                self.grabador_audio.reanudar()
            self._lanzar_ffmpeg()
            self.estado = "grabando"

    def detener(self, al_detener_captura=None) -> str | None:
        with self._lock:
            return self._detener_seguro(al_detener_captura)

    def _detener_seguro(self, al_detener_captura=None):
        try:
            return self._finalizar_grabacion(al_detener_captura)
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo completar el video: {exc}. Los fragmentos se conservan en {CARPETA_TEMPORAL}"
            ) from exc
        finally:
            try:
                self._detener_ffmpeg_actual()
            finally:
                if self.grabador_audio and self.grabador_audio.grabando:
                    try:
                        self.grabador_audio.detener()
                    except Exception:
                        pass
                self.estado = "detenido"

    def _finalizar_grabacion(self, al_detener_captura=None) -> str | None:
        if self.estado == "detenido":
            return None

        # 1. Detener el video actual (si estaba grabando)
        if self.estado == "grabando":
            self._detener_ffmpeg_actual()

        # 2. Detener el audio
        if self.con_audio and self.grabador_audio:
            self.grabador_audio.detener()

        # A partir de aquí ningún frame nuevo puede contener la UI restaurada.
        if al_detener_captura:
            try:
                al_detener_captura()
            except Exception:
                pass  # Cerrar la ventana no debe interrumpir la exportación.

        # 3. Muxing por fragmento
        rutas_para_concat = []
        if self.con_audio and self.grabador_audio:
            for i, ruta_vid in enumerate(self.rutas_video_temp):
                ruta_aud = self.grabador_audio.rutas_audio_temp[i] if i < len(self.grabador_audio.rutas_audio_temp) else None
                ts_vid = self.timestamps_video_inicio[i] if i < len(self.timestamps_video_inicio) else 0
                ts_aud = self.grabador_audio.timestamps_inicio_fragmentos[i] if i < len(self.grabador_audio.timestamps_inicio_fragmentos) else None
                diff = (ts_aud if ts_aud is not None else ts_vid) - ts_vid
                ruta_mux = os.path.join(CARPETA_TEMPORAL, f"mux_{self._identificador_base}_part{i}.mp4")
                entrada_audio = ["-i", ruta_aud] if ruta_aud else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                audio_filter = (f"atrim=start={-diff:.6f},asetpts=PTS-STARTPTS" if diff < 0 else
                                f"asetpts=PTS-STARTPTS,adelay={round(diff * 1000)}:all=1")
                # Cada tramo lleva la misma pista AAC, incluso si la pausa fue
                # tan rápida que no hubo muestras. apad impide que -shortest
                # corte el segundo video al terminar antes su audio.
                comando = [obtener_ruta_ffmpeg(), "-y", "-i", ruta_vid, *entrada_audio,
                           "-filter_complex", f"[0:v]setpts=PTS-STARTPTS[v];[1:a]{audio_filter},aresample=48000,apad[a]",
                           "-map", "[v]", "-map", "[a]", *self._calidad_video(),
                           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                           "-shortest", "-movflags", "+faststart", ruta_mux]
                ruta_log_mux = os.path.join(CARPETA_LOGS, f"mux_{self._identificador_base}_part{i}.log")
                with open(ruta_log_mux, "w", encoding="utf-8") as log_mux:
                    resultado = subprocess.run(comando, stdout=log_mux, stderr=log_mux,
                                              creationflags=subprocess.CREATE_NO_WINDOW, timeout=600)
                if resultado.returncode != 0 or not os.path.exists(ruta_mux) or os.path.getsize(ruta_mux) == 0:
                    raise RuntimeError(f"Falló la unión de audio/video; consulta {ruta_log_mux}")
                rutas_para_concat.append(ruta_mux)
        else:
            rutas_para_concat = self.rutas_video_temp

        return self._unir_fragmentos(rutas_para_concat)

    def _unir_fragmentos(self, rutas_para_concat):
        # 4. Concatenar los fragmentos de video
        if len(rutas_para_concat) == 1:
            os.replace(rutas_para_concat[0], self.ruta_final)
        elif len(rutas_para_concat) > 1:
            # Escribir el archivo concat
            ruta_concat = os.path.join(CARPETA_TEMPORAL, f"concat_{self._identificador_base}.txt")
            with open(ruta_concat, "w", encoding="utf-8") as f:
                for ruta in rutas_para_concat:
                    # ffmpeg concat requiere barras normales o rutas seguras
                    ruta_segura = ruta.replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{ruta_segura}'\n")
            
            comando_concat = [
                obtener_ruta_ffmpeg(), "-y",
                "-f", "concat",
                "-safe", "0",
                "-fflags", "+genpts",
                "-i", ruta_concat,
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-movflags", "+faststart",
                self.ruta_final
            ]
            ruta_log_concat = os.path.join(CARPETA_LOGS, f"concat_{self._identificador_base}.log")
            with open(ruta_log_concat, "w", encoding="utf-8") as log_concat:
                resultado = subprocess.run(
                    comando_concat, stdout=log_concat, stderr=log_concat,
                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=600,
                )
            if resultado.returncode != 0:
                raise RuntimeError(f"Falló la unión de segmentos; consulta {ruta_log_concat}")
            
            # Limpiar concat list
            if os.path.exists(ruta_concat):
                os.remove(ruta_concat)

        if not self.ruta_final or not os.path.isfile(self.ruta_final) or os.path.getsize(self.ruta_final) == 0:
            raise RuntimeError("FFmpeg no generó un video final válido")

        # 5. Limpiar únicamente después de confirmar la salida satisfactoria.
        for fragmento in self.rutas_video_temp:
            if fragmento != self.ruta_final and os.path.exists(fragmento):
                os.remove(fragmento)
                
        if self.con_audio and self.grabador_audio:
            for fragmento_aud in self.grabador_audio.rutas_audio_temp:
                if fragmento_aud and os.path.exists(fragmento_aud):
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
