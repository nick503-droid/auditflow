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

    def iniciar(self, identificador_base: str):
        self.identificador_base = identificador_base
        self.indice_fragmento = 0
        self.rutas_audio_temp = []
        self.timestamps_inicio_fragmentos = []
        self.frames = []
        self.grabando = True
        self.pausado = False
        self._primer_frame_fragmento = True
        self.hilo = threading.Thread(target=self._grabar, daemon=True)
        self.hilo.start()

    def pausar(self):
        with self._lock:
            self.pausado = True
            frames_actuales = self.frames
            self.frames = []
        self._guardar_fragmento(frames_actuales)
        self.indice_fragmento += 1

    def reanudar(self):
        with self._lock:
            self.frames = []
            self.pausado = False
            self._primer_frame_fragmento = True

    def _guardar_fragmento(self, frames):
        if not frames:
            return
        ruta_salida = os.path.join(CARPETA_TEMPORAL, f"audio_{self.identificador_base}_part{self.indice_fragmento}.wav")
        archivo_wav = wave.open(ruta_salida, "wb")
        archivo_wav.setnchannels(self.dispositivo["maxInputChannels"])
        archivo_wav.setsampwidth(self.pyaudio_instance.get_sample_size(pyaudio.paInt16))
        archivo_wav.setframerate(int(self.dispositivo["defaultSampleRate"]))
        archivo_wav.writeframes(b"".join(frames))
        archivo_wav.close()
        self.rutas_audio_temp.append(ruta_salida)

    def _grabar(self):
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

        while self.grabando:
            datos = self.stream.read(1024, exception_on_overflow=False)
            with self._lock:
                if not self.pausado:
                    if self._primer_frame_fragmento:
                        self.timestamps_inicio_fragmentos.append(time.time())
                        self._primer_frame_fragmento = False
                    self.frames.append(datos)

        with self._lock:
            frames_actuales = self.frames
            self.frames = []
            
        if not self.pausado and frames_actuales:
            self._guardar_fragmento(frames_actuales)

        self.stream.stop_stream()
        self.stream.close()
        self.pyaudio_instance.terminate()

    def detener(self):
        self.grabando = False
        if self.hilo:
            self.hilo.join(timeout=5)