import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
PYTHON = PLUGIN / 'runtime/python.exe'
NVDA = Path(os.environ.get('BOOK_AUDIO_TEST_NVDA', 'C:/Program Files/NVDA'))

@unittest.skipUnless(NVDA.exists() and PYTHON.exists(), 'Installed NVDA x64 integration test')
class RuntimeTests(unittest.TestCase):
    def run_worker(self, driver, action, output=None):
        worker = PLUGIN / 'worker.py'
        self.assertTrue(worker.exists(), 'Isolated NVDA worker is not implemented')
        with tempfile.TemporaryDirectory() as tmp:
            addon_root = Path.home() / 'AppData/Roaming/nvda/addons'
            prefix = driver + '*' if driver in ('RHVoice', 'NeuralVoices') else None
            addons = [str(p) for p in addon_root.glob(prefix) if (p / 'manifest.ini').is_file()] if prefix else []
            request = {'nvda': str(NVDA), 'config': tmp, 'addons': addons,
                       'driver': driver, 'action': action, 'text': 'Проверка создания аудиокниги.',
                       'voice': '', 'rate': 50, 'wav': str(output or ''),
                       'mp3': str(output.with_suffix('.mp3')) if output else None}
            file = Path(tmp) / 'request.json'
            file.write_text(json.dumps(request), encoding='utf-8')
            try:
                result = subprocess.run([str(PYTHON), str(worker), str(file)], capture_output=True, timeout=25)
            except subprocess.TimeoutExpired as error:
                self.fail((error.stdout or b'').decode('utf-8', 'replace') + (error.stderr or b'').decode('utf-8', 'replace'))
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace') + result.stdout.decode('utf-8', 'replace'))
            events = [json.loads(line) for line in result.stdout.decode('utf-8').splitlines() if line.startswith('{')]
            self.assertTrue(events, result.stdout)
            self.assertNotEqual(events[-1].get('type'), 'error', events[-1])
            return events

    def test_mp3_is_real_and_decodes(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / 'audio.wav'
            self.run_worker('RHVoice', 'render', wav)
            mp3 = wav.with_suffix('.mp3')
            self.assertTrue(mp3.is_file(), 'MP3 encoding is not implemented')
            self.assertGreater(mp3.stat().st_size, 1000)
            ffmpeg = shutil.which('ffmpeg')
            if ffmpeg:
                # Some MSIX-packaged tools cannot be executed by a child Python
                # at their original path; a job-local copy is executable.
                verifier = Path(tmp) / 'ffmpeg.exe'
                shutil.copy2(ffmpeg, verifier)
                result = subprocess.run([str(verifier), '-v', 'error', '-i', str(mp3), '-f', 's16le', '-'], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertGreater(len(result.stdout), 10000)
                self.assertTrue(any(result.stdout))

    def test_rhvoice_renders_nonempty_pcm(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / 'rhvoice.wav'
            events = self.run_worker('RHVoice', 'render', wav)
            self.assertEqual(events[-1]['type'], 'rendered')
            with wave.open(str(wav)) as audio:
                self.assertGreater(audio.getnframes(), 1000)
                self.assertTrue(any(audio.readframes(audio.getnframes())))

    def test_espeak_renders_nonempty_pcm(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / 'espeak.wav'
            events = self.run_worker('espeak', 'render', wav)
            self.assertEqual(events[-1]['type'], 'rendered')
            with wave.open(str(wav)) as audio:
                self.assertGreater(audio.getnframes(), 1000)

    def test_sapi_renders_nonempty_pcm(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / 'test.wav'
            events = self.run_worker('sapi5', 'render', wav)
            self.assertEqual(events[-1]['type'], 'rendered')
            with wave.open(str(wav)) as audio:
                self.assertGreater(audio.getnframes(), 1000)
                self.assertTrue(any(audio.readframes(audio.getnframes())))

    def test_frozen_resources_use_nvda_directory_and_restore_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = Path(tmp) / 'resources.json'
            request.write_text(json.dumps({'nvda': str(NVDA), 'config': tmp, 'addons': []}), encoding='utf-8')
            script = (
                'import sys,json,importlib.util; from pathlib import Path\n'
                f'sys.path.insert(0, {str(PLUGIN)!r})\n'
                'import worker\noriginal = sys.executable\n'
                f'worker.bootstrap(json.loads(Path({str(request)!r}).read_text(encoding="utf-8")))\n'
                'assert sys.executable == original\n'
                'if importlib.util.find_spec("pyphen") is not None:\n'
                ' import pyphen\n'
                f' assert pyphen.dictionaries.resolve() == (Path({str(NVDA)!r}) / "pyphenDictionaries").resolve()\n'
                ' assert pyphen.LANGUAGES and all(p.is_file() for p in pyphen.LANGUAGES.values())\n'
                'print("FROZEN_RESOURCE_CHECK_OK")\n'
            )
            result = subprocess.run([str(PYTHON), '-c', script], capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
            self.assertIn(b'FROZEN_RESOURCE_CHECK_OK', result.stdout)

    def test_enumerate_sapi_voices_in_separate_process(self):
        events = self.run_worker('sapi5', 'voices')
        self.assertEqual(events[-1]['type'], 'voices')
        self.assertTrue(events[-1]['voices'])

    def test_onecore_and_neural_render_real_mp3(self):
        import shutil
        for name in ('oneCore', 'NeuralVoices'):
            with self.subTest(driver=name), tempfile.TemporaryDirectory() as tmp:
                wav = Path(tmp) / (name + '.wav')
                events = self.run_worker(name, 'render', wav)
                self.assertEqual(events[-1]['type'], 'rendered')
                with wave.open(str(wav)) as audio:
                    self.assertGreater(audio.getnframes(), 1000)
                    self.assertTrue(any(audio.readframes(audio.getnframes())))
                mp3 = wav.with_suffix('.mp3')
                self.assertGreater(mp3.stat().st_size, 1000)
                ffmpeg = shutil.which('ffmpeg')
                if ffmpeg:
                    verifier = Path(tmp) / 'ffmpeg.exe'
                    shutil.copy2(ffmpeg, verifier)
                    decoded = subprocess.run([str(verifier), '-v', 'error', '-i', str(mp3), '-f', 's16le', '-'], capture_output=True, timeout=20)
                    self.assertEqual(decoded.returncode, 0, decoded.stderr)
                    self.assertGreater(len(decoded.stdout), 10000)
                    self.assertTrue(any(decoded.stdout))

    def test_enumerate_onecore_voices_in_separate_process(self):
        events = self.run_worker('oneCore', 'voices')
        self.assertEqual(events[-1]['type'], 'voices')
        self.assertTrue(events[-1]['voices'])

    def test_enumerate_neural_voices_in_separate_process(self):
        events = self.run_worker('NeuralVoices', 'voices')
        self.assertEqual(events[-1]['type'], 'voices')
        self.assertTrue(events[-1]['voices'])

if __name__ == '__main__':
    unittest.main()
