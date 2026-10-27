"""Negative probe checks with explicit PCM/encoder fixtures, not runtime claims."""
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
import worker
import capture
import i18n

SCRATCH = Path(tempfile.gettempdir())


class ProbeValidationTests(unittest.TestCase):
    def run_fixture(self, pcm, encode=None):
        i18n.set_language('ru')
        with tempfile.TemporaryDirectory(prefix='bookAudio-probe-unit-', dir=SCRATCH) as tmp:
            sink = capture.WaveSink(Path(tmp) / 'unused.wav')
            def synth(*args, **kwargs):
                if pcm:
                    capture.make_player(sink)(1, 16000, 16).feed(pcm)
            try:
                with patch.object(worker, 'render', synth):
                    if encode is not None:
                        with patch('encoder.encode_wav', encode):
                            return worker.verify_voice_recording(SimpleNamespace(voice='fixture', rate=50), None,
                                {'config': tmp, 'driver': 'fixture', 'voice': 'fixture', 'rate': 50}, sink)
                    return worker.verify_voice_recording(SimpleNamespace(voice='fixture', rate=50), None,
                        {'config': tmp, 'driver': 'fixture', 'voice': 'fixture', 'rate': 50}, sink)
            finally:
                sink.close()

    def test_empty_pcm_is_never_reported_verified(self):
        with self.assertRaisesRegex(RuntimeError, 'PCM'):
            self.run_fixture(b'')

    def test_silent_pcm_is_never_reported_verified(self):
        with self.assertRaisesRegex(RuntimeError, 'тишину'):
            self.run_fixture(b'\x00\x00' * 4000)

    def test_encoder_error_is_not_hidden(self):
        def fail(source, destination):
            raise OSError('fixture encoder failure')
        with self.assertRaisesRegex(OSError, 'fixture encoder failure'):
            self.run_fixture(b'\x01\x00' * 4000, fail)

    def test_empty_mp3_is_never_reported_verified(self):
        def empty(source, destination):
            Path(destination).write_bytes(b'')
        with self.assertRaisesRegex(RuntimeError, 'MP3'):
            self.run_fixture(b'\x01\x00' * 4000, empty)


if __name__ == '__main__':
    unittest.main()
