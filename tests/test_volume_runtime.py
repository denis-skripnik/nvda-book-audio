"""Real worker output gain and MP3 evidence; no playback or live NVDA changes."""
from array import array
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave
import sys
import test_runtime as runtime

sys.path.insert(0, str(runtime.PLUGIN))
from client import WorkerClient


def rms(data):
    values = array('h')
    values.frombytes(data)
    return math.sqrt(sum(value * value for value in values) / max(1, len(values)))


@unittest.skipUnless(runtime.NVDA.exists() and runtime.PYTHON.exists(), 'Installed NVDA integration')
class VolumeRuntimeTests(unittest.TestCase):
    def request(self, **extra):
        request = dict(nvda=str(runtime.NVDA), addons=[], driver='espeak', action='render',
                       text='Проверка громкости записи аудиокниги.', voice='', rate=50, language='ru')
        request.update(extra)
        return request

    def test_probe_echoes_volume_and_zero_has_a_clear_validation_error(self):
        result = WorkerClient().run(self.request(action='probe', volume=25), lambda event: None)
        self.assertEqual(result['type'], 'compatibility')
        self.assertEqual(result['volume'], 25)
        with self.assertRaisesRegex(RuntimeError, 'громкость выше 0'):
            WorkerClient().run(self.request(action='probe', volume=0), lambda event: None)

    def test_zero_volume_converts_two_chapters_to_muted_mp3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'muted.txt'
            source.write_text('Глава 1\nПервая часть.\nГлава 2\nВторая часть.', encoding='utf-8')
            result = WorkerClient().run(self.request(action='convert', volume=0, files=[str(source)],
                output=tmp, separator='Глава'), lambda event: None)
            self.assertEqual(result, {'type': 'done', 'count': 2})
            files = list(root.glob('muted*/*.mp3'))
            self.assertEqual(len(files), 2)
            ffmpeg = shutil.which('ffmpeg')
            self.assertIsNotNone(ffmpeg)
            verifier = root / 'ffmpeg.exe'
            shutil.copy2(ffmpeg, verifier)
            for mp3 in files:
                decoded = subprocess.run([str(verifier), '-v', 'error', '-i', str(mp3), '-f', 's16le', '-'],
                                         capture_output=True, timeout=20)
                self.assertEqual(decoded.returncode, 0, decoded.stderr)
                self.assertGreater(len(decoded.stdout), 1000)
                self.assertEqual(rms(decoded.stdout), 0)

    def test_selected_volume_changes_real_pcm_and_decoded_mp3(self):
        for driver in ('espeak', 'oneCore', 'sapi5_32'):
            with self.subTest(driver=driver):
                self.check_driver_volume(driver)

    def check_driver_volume(self, driver):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg = shutil.which('ffmpeg')
            self.assertIsNotNone(ffmpeg, 'Independent MP3 decoder is required')
            verifier = root / 'ffmpeg.exe'
            shutil.copy2(ffmpeg, verifier)
            measured = {}
            for volume in (100, 25):
                wav = root / (str(volume) + '.wav')
                mp3 = wav.with_suffix('.mp3')
                result = WorkerClient().run(self.request(driver=driver, volume=volume, wav=str(wav), mp3=str(mp3)), lambda event: None)
                self.assertEqual(result['type'], 'rendered')
                with wave.open(str(wav)) as audio:
                    pcm = audio.readframes(audio.getnframes())
                    measured[volume] = [rms(pcm)]
                decoded = subprocess.run([str(verifier), '-v', 'error', '-i', str(mp3), '-f', 's16le', '-'], capture_output=True, timeout=20)
                self.assertEqual(decoded.returncode, 0, decoded.stderr)
                self.assertTrue(decoded.stdout)
                measured[volume].append(rms(decoded.stdout))
            for index in (0, 1):
                ratio = measured[25][index] / measured[100][index]
                self.assertGreater(ratio, 0.15)
                self.assertLess(ratio, 0.35, measured)


if __name__ == '__main__':
    unittest.main()
