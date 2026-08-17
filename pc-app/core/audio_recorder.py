import pyaudiowpatch as pyaudio
import wave
import threading
import time


class GrabadorAudio:
    """
    Captura el audio que suena en el sistema (no el micrófono) usando
    WASAPI Loopback nativo de Windows, corriendo en un hilo aparte
    para no bloquear la grabación de video que ocurre al mismo tiempo.
    """

    def __init__(self):
        self.pyaudio_instance = None
        self.stream = None
        self.frames = []
        self.grabando = False
        self.hilo = None
        self.ruta_salida = None
        self.dispositivo = None
        # Timestamp del primer read() real — se fija DENTRO del hilo de captura
        # para medir cuándo el audio realmente empezó a capturar datos.
        self.timestamp_inicio_real: float | None = None

    def iniciar(self, ruta_salida: str):
        self.ruta_salida = ruta_salida
        self.frames = []
        self.grabando = True
        # daemon=True: si la app principal se cierra de golpe, este hilo
        # no la deja "colgada" esperando a que termine
        self.hilo = threading.Thread(target=self._grabar, daemon=True)
        self.hilo.start()

    def _grabar(self):
        self.pyaudio_instance = pyaudio.PyAudio()

        # Encuentra el dispositivo de salida por defecto (tus bocinas/audífonos)
        # y busca su versión "loopback" — WASAPI loopback significa
        # "captura lo que este dispositivo está reproduciendo", no
        # lo que entra por un micrófono
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

        # Bucle de captura: mientras self.grabando sea True, sigue
        # leyendo bloques de audio y acumulándolos en memoria
        primer_frame = True
        while self.grabando:
            datos = self.stream.read(1024, exception_on_overflow=False)
            if primer_frame:
                # Timestamp real del primer dato de audio capturado.
                # Se usa en el muxing para calcular el desfase con el video.
                self.timestamp_inicio_real = time.time()
                primer_frame = False
            self.frames.append(datos)

        self._guardar_wav()

    def _guardar_wav(self):
        self.stream.stop_stream()
        self.stream.close()

        archivo_wav = wave.open(self.ruta_salida, "wb")
        archivo_wav.setnchannels(self.dispositivo["maxInputChannels"])
        archivo_wav.setsampwidth(self.pyaudio_instance.get_sample_size(pyaudio.paInt16))
        archivo_wav.setframerate(int(self.dispositivo["defaultSampleRate"]))
        archivo_wav.writeframes(b"".join(self.frames))
        archivo_wav.close()

        self.pyaudio_instance.terminate()

    def detener(self):
        """Le avisa al hilo que pare y espera a que termine de escribir el .wav."""
        self.grabando = False
        if self.hilo:
            self.hilo.join(timeout=5)