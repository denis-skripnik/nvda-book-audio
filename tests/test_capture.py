import ctypes
import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'addon/globalPlugins/bookAudio'))

def load_capture():
    file = ROOT / 'addon/globalPlugins/bookAudio/capture.py'
    if not file.exists():
        raise AssertionError('PCM capture module is not implemented')
    spec = importlib.util.spec_from_file_location('capture', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class CaptureTests(unittest.TestCase):
    def test_pcm_bytes_pointer_and_callback_are_written(self):
        m = load_capture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'speech.wav'
            sink = m.WaveSink(path)
            player = m.make_player(sink)(1, 24000, 16)
            calls = []
            player.feed(b'\x01\x00' * 20, onDone=lambda: calls.append(True))
            data = ctypes.create_string_buffer(b'\x02\x00' * 10)
            player.feed(ctypes.cast(data, ctypes.c_void_p), 20)
            sink.close()
            with wave.open(str(path)) as wav:
                self.assertEqual(wav.getnframes(), 30)
                self.assertEqual(wav.getframerate(), 24000)
                self.assertEqual(wav.readframes(30), b'\x01\x00' * 20 + b'\x02\x00' * 10)
            self.assertEqual(calls, [True])
