"""Selectable MP3 bitrate: validation and independently measured real output."""
from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
from encoder import encode_wav


class BitrateTests(unittest.TestCase):
    def test_invalid_bitrates_rejected_before_input_or_output_is_opened(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'invalid.mp3'
            for bitrate in (0, 63, 65, 97, 256, -96, True, False, '96', 96.0, None):
                with self.subTest(bitrate=bitrate):
                    with self.assertRaises(ValueError):
                        encode_wav('missing.wav', output, bitrate=bitrate)
                    self.assertEqual(list(Path(tmp).iterdir()), [])

    @unittest.skipUnless(sys.version_info[:2] == (3, 13), 'Bundled LAME uses Python 3.13')
    def test_real_encoder_selected_and_default_bitrates_with_ffprobe(self):
        import json
        import math
        import shutil
        import subprocess
        import wave
        from array import array
        ffprobe = shutil.which('ffprobe')
        self.assertIsNotNone(ffprobe, 'Independent MP3 metadata verifier is required')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Avoid WindowsApps execution aliases in the isolated runtime.
            verifier = root / 'ffprobe.exe'
            shutil.copy2(ffprobe, verifier)
            wav = root / 'tone.wav'
            pcm = array('h', (int(6000 * math.sin(2 * math.pi * 440 * n / 44100)) for n in range(88200)))
            with wave.open(str(wav), 'wb') as audio:
                audio.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
                audio.writeframes(pcm.tobytes())
            sizes = {}
            for bitrate in (64, 96, 128, 160, 192, None):
                with self.subTest(bitrate=bitrate):
                    mp3 = root / (str(bitrate) + '.mp3')
                    if bitrate is None:
                        encode_wav(wav, mp3)
                    else:
                        encode_wav(wav, mp3, bitrate=bitrate)
                    result = subprocess.run([str(verifier), '-v', 'error', '-show_entries',
                        'stream=codec_name,bit_rate', '-of', 'json', str(mp3)], capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    stream = json.loads(result.stdout)['streams'][0]
                    self.assertEqual(stream['codec_name'], 'mp3')
                    self.assertEqual(int(stream['bit_rate']), (128 if bitrate is None else bitrate) * 1000)
                    sizes[bitrate] = mp3.stat().st_size
                    self.assertFalse(mp3.with_suffix('.mp3.part').exists())
            self.assertLess(sizes[96], sizes[128])
            self.assertEqual(sizes[None], sizes[128])


class WorkerBitrateTests(unittest.TestCase):
    def test_worker_forwards_bitrate_for_render_convert_and_probe(self):
        import json
        import os
        import shutil
        import subprocess
        from client import WorkerClient
        nvda = Path(os.environ.get('BOOK_AUDIO_TEST_NVDA', 'C:/Program Files/NVDA'))
        if not (nvda / 'library.zip').is_file():
            self.skipTest('NVDA runtime is required')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            verifier = root / 'ffprobe.exe'
            shutil.copy2(shutil.which('ffprobe'), verifier)
            source = root / 'book.txt'
            source.write_text('A short book for bitrate testing.', encoding='utf-8')
            request = dict(nvda=str(nvda), addons=[], driver='espeak', rate=50,
                           voice='', language='en', bitrate=96, volume=100)
            wav = root / 'render.wav'
            WorkerClient().run(dict(request, action='render', text='A test of selected bitrate.',
                wav=str(wav), mp3=str(wav.with_suffix('.mp3'))), lambda event: None)
            WorkerClient().run(dict(request, action='convert', files=[str(source)], output=tmp,
                                   separator=''), lambda event: None)
            outputs = list(root.rglob('*.mp3'))
            self.assertEqual(len(outputs), 2)
            for output in outputs:
                result = subprocess.run([str(verifier), '-v', 'error', '-show_entries',
                    'stream=bit_rate', '-of', 'json', str(output)], capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(int(json.loads(result.stdout)['streams'][0]['bit_rate']), 96000)
            result = WorkerClient().run(dict(request, action='probe'), lambda event: None)
            self.assertEqual(result['type'], 'compatibility')
            self.assertEqual(result.get('bitrate'), 96)
            request.pop('bitrate')
            result = WorkerClient().run(dict(request, action='probe'), lambda event: None)
            self.assertEqual(result.get('bitrate'), 128)


if __name__ == '__main__':
    unittest.main(verbosity=2)
