import pyaudiowpatch as pyaudio
import wave
import threading
import time
import os

CARPETA_TEMPORAL = os.path.join(os.path.expanduser("~"), "AuditFlow_Temp")

class GrabadorAudio:
    def __init__(self):
        self.pyaudio_instance = None
        self.stream = None
        self.frames = []
        self.grabando = False
        self.pausado = False
        self.hilo = None
        
        self.dispositivo = None
        self.identificador_base = ""
        self.indice_fragmento = 0
        self.rutas_audio_temp = []
        self.timestamps_inicio_fragmentos = []
        
        self._lock = threading.Lock()
        self._primer_frame_fragmento = False
        self.error = None
        self._listo = threading.Event()
        self._generacion = 0

    def iniciar(self, identificador_base: str):
        self.error = None
        self.identificador_base = identificador_base
        self.indice_fragmento = 0
        self.rutas_audio_temp = []
        self.timestamps_inicio_fragmentos = []
        self.frames = []
        self.grabando = True
        self.pausado = False
        self._primer_frame_fragmento = True
        self._listo.clear()
        self.hilo = threading.Thread(target=self._grabar, daemon=True)
        self.hilo.start()
        if not self._listo.wait(8):
            self.grabando = False
            raise RuntimeError("El dispositivo de audio no respondió al iniciar")
        if self.error:
            raise RuntimeError(f"No se pudo iniciar el audio: {self.error}") from self.error

    def pausar(self):
        with self._lock:
            self.pausado = True
            frames_actuales = self.frames
            self.frames = []
            indice = self.indice_fragmento
            self.indice_fragmento += 1
            self._generacion += 1
        self._guardar_fragmento(frames_actuales, indice)

    def reanudar(self):
        if self.error or not self.grabando:
            raise RuntimeError(f"El dispositivo de audio dejó de estar disponible: {self.error or 'captura cerrada'}")
        with self._lock:
            self.frames = []
            self.pausado = False
            self._primer_frame_fragmento = True

    def _asegurar_slot(self, indice):
        while len(self.rutas_audio_temp) <= indice:
            self.rutas_audio_temp.append(None)
            self.timestamps_inicio_fragmentos.append(None)

    def _guardar_fragmento(self, frames, indice):
        self._asegurar_slot(indice)
        if not frames:
            return
        ruta_salida = os.path.join(CARPETA_TEMPORAL, f"audio_{self.identificador_base}_part{indice}.wav")
        with wave.open(ruta_salida, "wb") as archivo_wav:
            archivo_wav.setnchannels(self.dispositivo["maxInputChannels"])
            archivo_wav.setsampwidth(2)  # paInt16: no depender de una instancia ya cerrada.
            archivo_wav.setframerate(int(self.dispositivo["defaultSampleRate"]))
            archivo_wav.writeframes(b"".join(frames))
        self.rutas_audio_temp[indice] = ruta_salida

    def _grabar(self):
        try:
            self._capturar()
        except Exception as exc:
            self.error = exc
        finally:
            self._listo.set()
            self.grabando = False
            for recurso, accion in ((self.stream, "stop_stream"), (self.stream, "close"),
                                     (self.pyaudio_instance, "terminate")):
                if recurso is not None:
                    try:
                        getattr(recurso, accion)()
                    except Exception:
                        pass

    def _capturar(self):
        self.pyaudio_instance = pyaudio.PyAudio()

        wasapi_info = self.pyaudio_instance.get_host_api_info_by_type(pyaudio.paWASAPI)
        salida_default = self.pyaudio_instance.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )

        if not salida_default["isLoopbackDevice"]:
            for dispositivo_loopback in self.pyaudio_instance.get_loopback_device_info_generator():
                if salida_default["name"] in dispositivo_loopback["name"]:
                    salida_default = dispositivo_loopback
                    break

        self.dispositivo = salida_default

        self.stream = self.pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=self.dispositivo["maxInputChannels"],
            rate=int(self.dispositivo["defaultSampleRate"]),
            frames_per_buffer=1024,
            input=True,
            input_device_index=self.dispositivo["index"],
        )
        self._listo.set()

        while self.grabando:
            with self._lock:
                generacion = self._generacion
                pausado = self.pausado
            datos = self.stream.read(1024, exception_on_overflow=False)
            with self._lock:
                if self.grabando and not pausado and not self.pausado and generacion == self._generacion:
                    if self._primer_frame_fragmento:
                        self._asegurar_slot(self.indice_fragmento)
                        self.timestamps_inicio_fragmentos[self.indice_fragmento] = time.monotonic() - 1024 / self.dispositivo["defaultSampleRate"]
                        self._primer_frame_fragmento = False
                    self.frames.append(datos)

        with self._lock:
            frames_actuales = self.frames
            self.frames = []
            
        if not self.pausado and frames_actuales:
            self._guardar_fragmento(frames_actuales, self.indice_fragmento)

    def detener(self):
        self.grabando = False
        if self.hilo:
            self.hilo.join(timeout=5)
            if self.hilo.is_alive():
                raise RuntimeError("El dispositivo de audio no respondió al detenerse")
        if self.error:
            raise RuntimeError(f"Falló la captura de audio: {self.error}") from self.error
