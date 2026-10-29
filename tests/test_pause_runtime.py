"""Real driver capability gates for additional punctuation pauses."""
from pathlib import Path
import sys
import tempfile
import unittest
import test_runtime as runtime
sys.path.insert(0, str(runtime.PLUGIN))
from client import WorkerClient


@unittest.skipUnless(runtime.NVDA.exists() and runtime.PYTHON.exists(), 'Installed NVDA integration')
class PauseRuntimeTests(unittest.TestCase):
    def request(self, driver, **extra):
        addons = [str(x) for x in (Path.home() / 'AppData/Roaming/nvda/addons').glob(driver + '*')
                  if (x / 'manifest.ini').is_file()] if driver in ('RHVoice', 'NeuralVoices') else []
        request = dict(nvda=str(runtime.NVDA), addons=addons, driver=driver, rate=50, voice='', language='ru')
        request.update(extra)
        return request

    def test_unsupported_driver_rejects_nonzero_pauses_before_creating_audio(self):
        for action in ('render', 'probe', 'convert'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'book.txt'
                source.write_text('Первая фраза, вторая фраза.', encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'не поддерживает дополнительные паузы'):
                    WorkerClient().run(self.request('RHVoice', action=action, commaPauseMs=400, sentencePauseMs=600,
                        text=source.read_text(encoding='utf-8'), wav=str(root / 'audio.wav'),
                        files=[str(source)], output=tmp, separator=''), lambda event: None)
                self.assertFalse((root / 'audio.wav').exists())
                self.assertEqual(list(root.rglob('*.mp3')), [])

    def test_supported_drivers_insert_pauses_in_real_pcm(self):
        import wave
        for driver in ('espeak', 'oneCore', 'sapi5', 'sapi5_32', 'NeuralVoices'):
            with self.subTest(driver=driver), tempfile.TemporaryDirectory() as tmp:
                durations = []
                for comma, sentence in [(0, 0), (300, 600)]:
                    wav = Path(tmp) / (str(comma) + '.wav')
                    WorkerClient().run(self.request(driver, action='render', commaPauseMs=comma,
                        sentencePauseMs=sentence, text='Первая фраза, вторая фраза. Третья фраза',
                        wav=str(wav)), lambda event: None)
                    with wave.open(str(wav)) as audio:
                        durations.append(audio.getnframes() / audio.getframerate())
                delta = durations[1] - durations[0]
                if driver in ('NeuralVoices', 'espeak'):
                    # Native timing can depend on rate and punctuation prosody.
                    # Both requested categories together must exceed either alone.
                    self.assertGreater(delta, 0.50 if driver == 'NeuralVoices' else 0.60)
                    self.assertLess(delta, 1.1)
                else:
                    self.assertAlmostEqual(delta, 0.9, delta=0.12)

    def test_supported_conversion_forwards_pauses_to_every_mp3_and_probe(self):
        import shutil
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'book.txt'
            source.write_text('Глава 1\nПервая фраза, вторая фраза. Третья фраза\n'
                              'Глава 2\nПервая фраза, вторая фраза. Третья фраза', encoding='utf-8')
            ffmpeg = shutil.which('ffmpeg')
            self.assertIsNotNone(ffmpeg)
            verifier = root / 'ffmpeg.exe'
            shutil.copy2(ffmpeg, verifier)
            measured = []
            for comma, sentence in [(0, 0), (300, 600)]:
                output = root / str(comma)
                output.mkdir()
                result = WorkerClient().run(self.request('espeak', action='convert', files=[str(source)],
                    output=str(output), separator='Глава', bitrate=96, commaPauseMs=comma,
                    sentencePauseMs=sentence), lambda event: None)
                self.assertEqual(result, {'type': 'done', 'count': 2})
                files = sorted(output.rglob('*.mp3'))
                self.assertEqual(len(files), 2)
                durations = []
                for mp3 in files:
                    decoded = subprocess.run([str(verifier), '-v', 'error', '-i', str(mp3), '-ac', '1',
                        '-ar', '24000', '-f', 's16le', '-'], capture_output=True, timeout=20)
                    self.assertEqual(decoded.returncode, 0, decoded.stderr)
                    self.assertTrue(any(decoded.stdout))
                    durations.append(len(decoded.stdout) / (24000 * 2))
                measured.append(durations)
            for baseline, paused in zip(*measured):
                self.assertGreater(paused - baseline, 0.50)
                self.assertLess(paused - baseline, 1.1)
            result = WorkerClient().run(self.request('espeak', action='probe', commaPauseMs=300,
                sentencePauseMs=600), lambda event: None)
            self.assertEqual((result['commaPauseMs'], result['sentencePauseMs']), (300, 600))
            self.assertEqual(result['status'], 'verified')

    def test_unsupported_driver_accepts_zero_pauses_and_records_normally(self):
        import wave
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / 'normal.wav'
            result = WorkerClient().run(self.request('RHVoice', action='render', commaPauseMs=0,
                sentencePauseMs=0, text='Первая фраза, вторая фраза. Третья фраза', wav=str(wav)), lambda event: None)
            self.assertEqual(result['type'], 'rendered')
            with wave.open(str(wav)) as audio:
                self.assertGreater(audio.getnframes(), 1000)
                self.assertTrue(any(audio.readframes(audio.getnframes())))
            result = WorkerClient().run(self.request('RHVoice', action='probe', commaPauseMs=0,
                sentencePauseMs=0), lambda event: None)
            self.assertEqual(result['status'], 'verified')
            self.assertEqual((result['commaPauseMs'], result['sentencePauseMs']), (0, 0))

    def test_invalid_pause_values_are_rejected_before_synthesis(self):
        for driver in ('espeak', 'RHVoice'):
            with self.subTest(driver=driver), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(RuntimeError, 'целым числом'):
                    WorkerClient().run(self.request(driver, action='render', commaPauseMs=True,
                        text='Проверка.', wav=str(Path(tmp) / 'invalid.wav')), lambda event: None)
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_capabilities_are_reported_for_supporting_and_unsupported_drivers(self):
        for driver, supported in [('espeak', True), ('RHVoice', False)]:
            with self.subTest(driver=driver):
                result = WorkerClient().run(self.request(driver, action='voices'), lambda event: None)
                self.assertIs(result.get('supportsPauses'), supported)


if __name__ == '__main__':
    unittest.main()
