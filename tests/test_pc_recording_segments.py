"""FFmpeg real + pantalla y dispositivo de audio sintéticos, sin capturar al usuario."""
import ast
from pathlib import Path
import math
import os
import re
import struct
import subprocess
import tempfile
import threading
import time
import types
import unittest
import wave

import test_pc_recording_recovery as recovery
from test_pc_recording_recovery import REPO

FFMPEG = str(REPO / "pc-app/ffmpeg.exe")


def audio_class(folder):
    pcm = b"".join(struct.pack('<hh', int(math.sin(i * 2 * math.pi * 1000 / 48000) * 10000),
                             int(math.sin(i * 2 * math.pi * 1000 / 48000) * 10000)) for i in range(1024))
    class Stream:
        def read(self, count, **kwargs):
            time.sleep(count / 48000)
            return pcm
        def stop_stream(self): pass
        def close(self): pass
    class Device:
        def get_host_api_info_by_type(self, kind): return {"defaultOutputDevice": 0}
        def get_device_info_by_index(self, index):
            return {"isLoopbackDevice": True, "maxInputChannels": 2, "defaultSampleRate": 48000, "index": 0}
        def open(self, **kwargs): return Stream()
        def terminate(self): pass
    tree = ast.parse((REPO / 'pc-app/core/audio_recorder.py').read_text(encoding='utf-8'))
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    scope = {"threading": threading, "time": time, "os": os, "wave": wave,
             "CARPETA_TEMPORAL": folder,
             "pyaudio": types.SimpleNamespace(PyAudio=Device, paWASAPI=13, paInt16=8)}
    exec(compile(ast.Module(body=[klass], type_ignores=[]), 'audio_recorder.py', 'exec'), scope)
    return scope[klass.name]


class AudioSlotTests(unittest.TestCase):
    def test_empty_first_segment_does_not_shift_second_audio_or_timestamps(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = audio_class(folder)()
            audio.identificador_base = 'fixture'
            audio.dispositivo = {"maxInputChannels": 2, "defaultSampleRate": 48000}
            audio.grabando = True
            audio.pausar()  # Sin recibir una muestra del primer tramo.
            audio.reanudar()
            audio._asegurar_slot(1)
            audio.timestamps_inicio_fragmentos[1] = 123
            audio.frames = [b'\0' * 4096]
            audio.pausar()
            self.assertEqual(audio.rutas_audio_temp[0], None)
            self.assertEqual(audio.timestamps_inicio_fragmentos, [None, 123])
            self.assertTrue(audio.rutas_audio_temp[1].endswith('part1.wav'))


@unittest.skipUnless(os.name == 'nt' and Path(FFMPEG).exists(), 'Requiere FFmpeg Windows')
class RealSegmentTests(unittest.TestCase):
    def run_ffmpeg(self, *args):
        return subprocess.run([FFMPEG, '-hide_banner', '-v', 'error', *args],
                              capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)

    def duration(self, path):
        result = subprocess.run([FFMPEG, '-hide_banner', '-i', path], capture_output=True,
                                timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        match = re.search(rb'Duration: (\d+):(\d+):([\d.]+)', result.stderr)
        self.assertIsNotNone(match, result.stderr[-1500:])
        return float(match[1])*3600 + float(match[2])*60 + float(match[3])

    def test_three_segments_survive_two_pauses_with_and_without_audio(self):
        for with_audio in (False, True):
            with self.subTest(audio=with_audio), tempfile.TemporaryDirectory() as folder:
                recorder = recovery.RecordingRecoveryTests().recorder(folder)
                recorder._detener_ffmpeg_actual = types.MethodType(type(recorder)._detener_ffmpeg_actual, recorder)
                scope = recorder._finalizar_grabacion.__func__.__globals__
                scope['obtener_ruta_ffmpeg'] = lambda: FFMPEG
                scope['GrabadorAudio'] = audio_class(folder)
                recorder.estado = 'detenido'
                durations = []
                for index, color in enumerate(('red', 'blue', 'lime')):
                    recorder._entrada_video = lambda color=color: [
                        '-re', '-f', 'lavfi', '-i', f'color=c={color}:s=320x180:r=30']
                    if index == 0: recorder.iniciar(with_audio)
                    else: recorder.reanudar()
                    time.sleep(.22)
                    recorder.pausar()
                    durations.append(self.duration(recorder.rutas_video_temp[-1]))
                    if with_audio and index == 0:
                        # Reproducir un primer tramo sin muestras: los siguientes
                        # conservan su índice y deben seguir oyéndose.
                        recorder.grabador_audio.rutas_audio_temp[0] = None
                        recorder.grabador_audio.timestamps_inicio_fragmentos[0] = None
                    self.assertEqual(recorder.estado, 'pausado')
                    time.sleep(.08)
                output = recorder.detener()
                self.assertEqual(recorder.estado, 'detenido')
                self.assertAlmostEqual(self.duration(output), sum(durations), delta=.18)
                cursor = 0
                for index, duration in enumerate(durations):
                    result = self.run_ffmpeg('-ss', str(cursor + duration / 2), '-i', output,
                                             '-frames:v', '1', '-vf', 'scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(len(result.stdout), 3)
                    rgb = result.stdout
                    expected_channel = (0, 2, 1)[index]
                    self.assertGreater(rgb[expected_channel], 180, rgb)
                    cursor += duration
                decoded = self.run_ffmpeg('-xerror', '-i', output, '-f', 'null', '-')
                self.assertEqual(decoded.returncode, 0, decoded.stderr)
                audio = self.run_ffmpeg('-i', output, '-map', '0:a:0', '-f', 's16le', 'pipe:1')
                if with_audio:
                    self.assertEqual(audio.returncode, 0, audio.stderr)
                    self.assertTrue(any(audio.stdout))
                else:
                    self.assertNotEqual(audio.returncode, 0)
                self.assertIsNone(recorder.proceso_video)

    def test_quality_profile_keeps_full_hd_resolution_and_30_fps(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = recovery.RecordingRecoveryTests().recorder(folder)
            recorder._detener_ffmpeg_actual = types.MethodType(type(recorder)._detener_ffmpeg_actual, recorder)
            recorder._finalizar_grabacion.__func__.__globals__['obtener_ruta_ffmpeg'] = lambda: FFMPEG
            recorder._entrada_video = lambda: ['-re', '-f', 'lavfi', '-i', 'testsrc2=s=1920x1080:r=30']
            recorder.estado = 'detenido'
            recorder.iniciar(False)
            time.sleep(.2)
            result = recorder.detener()
            meta = subprocess.run([FFMPEG, '-hide_banner', '-i', result], capture_output=True,
                                  timeout=10, creationflags=subprocess.CREATE_NO_WINDOW).stderr
            self.assertIn(b'1920x1080', meta)
            self.assertIn(b'30 fps', meta)
            self.assertEqual(recorder._calidad_video()[recorder._calidad_video().index('-crf') + 1], '20')

