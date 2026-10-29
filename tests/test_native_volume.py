"""Native synthesis gain must precede PCM capture, not attenuate clipping."""
from array import array
from pathlib import Path
import sys
import tempfile
import unittest
import wave
from types import SimpleNamespace
import test_runtime as runtime
sys.path.insert(0, str(runtime.PLUGIN))
from client import WorkerClient
import worker


class VolumeConfigurationTests(unittest.TestCase):
    def test_native_default_and_requested_volume_without_double_gain(self):
        configure = getattr(worker, 'configure_recording_volume', None)
        self.assertTrue(callable(configure), 'Missing native/fallback volume configuration')
        for requested, expected in ((None, 50), (25, 25), (0, 0)):
            driver = SimpleNamespace(volume=50, isSupported=lambda key: True)
            sink = SimpleNamespace(volume=100)
            self.assertEqual(configure(driver, sink, requested), expected)
            self.assertEqual(driver.volume, expected)
            self.assertEqual(sink.volume, 0 if expected == 0 else 100)

    def test_driver_without_volume_uses_capture_fallback(self):
        configure = getattr(worker, 'configure_recording_volume', None)
        self.assertTrue(callable(configure), 'Missing native/fallback volume configuration')
        driver = SimpleNamespace(volume=100, isSupported=lambda key: False)
        sink = SimpleNamespace(volume=100)
        self.assertEqual(configure(driver, sink, 25), 25)
        self.assertEqual(driver.volume, 100)
        self.assertEqual(sink.volume, 25)


@unittest.skipUnless(runtime.NVDA.exists() and runtime.PYTHON.exists(), 'Installed NVDA integration')
class NativeVolumeRuntimeTests(unittest.TestCase):
    def test_invalid_native_volume_is_rejected(self):
        for volume in (101, -1, True, 50.5, '50'):
            with self.subTest(volume=volume), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(RuntimeError, 'целым числом'):
                    WorkerClient().run(dict(nvda=str(runtime.NVDA), addons=[], driver='espeak', action='render',
                        volume=volume, rate=50, voice='', language='ru', text='Проверка.',
                        wav=str(Path(tmp) / 'invalid.wav')), lambda event: None)

    def test_neural_voice_discovery_reports_the_native_default(self):
        root = Path.home() / 'AppData/Roaming/nvda/addons'
        addons = [str(x) for x in root.glob('NeuralVoices*') if (x / 'manifest.ini').is_file()]
        if not addons:
            self.skipTest('Optional installed NeuralVoices driver and models')
        result = WorkerClient().run(dict(nvda=str(runtime.NVDA), addons=addons, driver='NeuralVoices',
            action='voices', language='ru'), lambda event: None)
        self.assertEqual(result.get('volume'), 50)

    def test_neural_volume_50_does_not_preserve_max_gain_clipped_plateaus(self):
        root = Path.home() / 'AppData/Roaming/nvda/addons'
        addons = [str(x) for x in root.glob('NeuralVoices*') if (x / 'manifest.ini').is_file()]
        request = dict(nvda=str(runtime.NVDA), addons=addons, driver='NeuralVoices', rate=50, language='ru')
        if not addons:
            self.skipTest('Optional installed NeuralVoices driver and models')
        voices = WorkerClient().run(dict(request, action='voices'), lambda event: None)['voices']
        voice = next((v['id'] for v in voices if 'RyanNeural' in v['id']), None)
        if not voice:
            self.skipTest('Optional installed RyanNeural model')
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / 'native.wav'
            result = WorkerClient().run(dict(request, action='render', volume=50, voice=voice,
                text='Проверка записи аудиокниги. Это настоящий синтез речи. Слушайте внимательно: голос должен звучать чисто, без искажений.',
                wav=str(wav)), lambda event: None)
            self.assertEqual(result['type'], 'rendered')
            with wave.open(str(wav)) as audio:
                samples = array('h')
                samples.frombytes(audio.readframes(audio.getnframes()))
            peak = max(abs(value) for value in samples)
            self.assertGreater(peak, 1000)
            self.assertLess(peak, 32760)
            plateau_fraction = sum(abs(value) >= peak - 1 for value in samples) / len(samples)
            self.assertLess(plateau_fraction, 0.001, 'Lower gain must prevent, not merely attenuate, clipped plateaus')


if __name__ == '__main__':
    unittest.main()
