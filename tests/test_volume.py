"""Export gain is applied to captured PCM, never the main NVDA synth."""
from array import array
from pathlib import Path
import sys
import tempfile
import unittest
import wave

PLUGIN = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
from capture import WaveSink


class VolumeCaptureTests(unittest.TestCase):
    def test_invalid_volume_is_rejected_before_audio_is_opened(self):
        for value in (-1, 101, 1.5, True, '50'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                WaveSink('unused.wav', volume=value)

    def test_malformed_gain_input_reports_error_without_raising_in_callback(self):
        for fmt, data in [((1, 16000, 8), b'\x80\x80'), ((1, 16000, 16), b'\x01')]:
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as tmp:
                sink = WaveSink(Path(tmp) / 'bad.wav', volume=50)
                try:
                    sink.write(fmt, data)
                    self.assertIsNotNone(sink.error)
                    self.assertEqual(sink.frames, 0)
                finally:
                    sink.close()

    def test_default_volume_preserves_bytes_and_zero_mutes_stereo(self):
        data = array('h', [-32768, 32767, -1, 1]).tobytes()
        for volume, expected in [(100, data), (0, b'\x00' * len(data))]:
            with self.subTest(volume=volume), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'stereo.wav'
                sink = WaveSink(path, volume=volume)
                sink.write((2, 16000, 16), data)
                sink.close()
                with wave.open(str(path)) as audio:
                    self.assertEqual(audio.getnframes(), 2)
                    self.assertEqual(audio.readframes(2), expected)

    def test_quarter_volume_scales_signed_mono_pcm(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'volume.wav'
            sink = WaveSink(path, volume=25)
            sink.write((1, 16000, 16), array('h', [-32000, -1000, 0, 1000, 32000]).tobytes())
            sink.close()
            with wave.open(str(path)) as audio:
                result = array('h')
                result.frombytes(audio.readframes(audio.getnframes()))
            self.assertEqual(result.tolist(), [-8000, -250, 0, 250, 8000])
            self.assertEqual(sink.frames, 5)


if __name__ == '__main__':
    unittest.main()
