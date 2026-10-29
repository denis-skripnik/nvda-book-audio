"""Captured WavePlayer stream volume, independent of native engine volume."""
import ctypes
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

PLUGIN = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
from capture import WaveSink, make_player


def pcm(*samples):
    return struct.pack('<' + 'h' * len(samples), *samples)


class PlayerVolumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'capture.wav'
        self.sink = WaveSink(self.path)
        self.addCleanup(self.sink.close)
        self.Player = make_player(self.sink)

    def audio(self):
        self.sink.close()
        with wave.open(str(self.path), 'rb') as audio:
            return audio.getnframes(), audio.readframes(audio.getnframes())

    def test_all_scales_signed_mono_without_changing_input(self):
        player = self.Player(1, 16000, 16)
        original = pcm(-32768, -1001, 0, 1001, 32767)
        player.setVolume(all=0.5)
        player.feed(original)
        self.assertEqual(self.audio(), (5, pcm(-16384, -500, 0, 500, 16383)))
        self.assertEqual(original, pcm(-32768, -1001, 0, 1001, 32767))

    def test_channel_updates_preserve_other_channel_and_all_resets_both(self):
        player = self.Player(2, 16000, 16)
        player.setVolume(all=0.5)
        player.setVolume(left=0.25)
        player.feed(pcm(8000, -8000))
        player.setVolume(right=0)
        player.feed(pcm(8000, -8000))
        player.setVolume(all=1)
        player.feed(pcm(8000, -8000))
        self.assertEqual(self.audio(), (3, pcm(2000, -4000, 2000, 0, 8000, -8000)))

    def test_mono_uses_left_channel(self):
        player = self.Player(1, 16000, 16)
        player.setVolume(left=0.25, right=0.75)
        player.feed(pcm(8000, -8000))
        self.assertEqual(self.audio(), (2, pcm(2000, -2000)))

    def test_invalid_volume_calls_leave_previous_gains_unchanged(self):
        player = self.Player(2, 16000, 16)
        player.setVolume(all=0.5)
        invalid = [{}, {'all': None}, {'all': 0, 'left': 0.5},
                   {'all': 1, 'right': 0}]
        for key in ('all', 'left', 'right'):
            invalid.extend({key: value} for value in
                           (-0.1, 1.1, float('nan'), float('inf'), -float('inf'), '0.5', object()))
        invalid.append({'left': 0.25, 'right': float('nan')})
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                player.setVolume(**kwargs)
        with self.assertRaises(TypeError):
            player.setVolume(0.5)
        player.feed(pcm(8000, -8000))
        self.assertEqual(self.audio(), (1, pcm(4000, -4000)))

    def test_malformed_pcm_sets_sink_error_and_still_calls_done(self):
        cases = [(1, 8, b'\x80\x80'), (1, 24, b'\x00' * 3),
                 (1, 16, b'\x01'), (2, 16, pcm(10)), (3, 16, pcm(1, 2, 3))]
        for gain in (1, 0.5, 0):
            for channels, bits, data in cases:
                with self.subTest(gain=gain, channels=channels, bits=bits):
                    sink = WaveSink(Path(self.tmp.name) / 'bad.wav')
                    player = make_player(sink)(channels, 16000, bits)
                    player.setVolume(all=gain)
                    done = []
                    try:
                        player.feed(data, onDone=lambda: done.append(True))
                        self.assertIsNotNone(sink.error)
                        self.assertEqual(sink.frames, 0)
                        self.assertEqual(done, [True])
                    finally:
                        sink.close()

    def test_pointer_size_and_callback_preserve_original_buffer(self):
        player = self.Player(2, 16000, 16)
        player.setVolume(left=0.5, right=0.25)
        original = pcm(8000, -8000, 32000, -32000)
        buffer = ctypes.create_string_buffer(original)
        done = []
        player.feed(ctypes.cast(buffer, ctypes.c_void_p), 4,
                    onDone=lambda: done.append(self.sink.frames))
        self.assertEqual(buffer.raw[:len(original)], original)
        self.assertEqual(done, [1])
        self.assertEqual(self.audio(), (1, pcm(4000, -2000)))

    def test_players_sharing_sink_have_independent_stream_gains(self):
        first = self.Player(1, 16000, 16)
        second = self.Player(1, 16000, 16)
        first.setVolume(all=0.25)
        first.feed(pcm(8000))
        second.feed(pcm(8000))
        second.setVolume(all=0.5)
        first.feed(pcm(8000))
        second.feed(pcm(8000))
        self.assertEqual(self.audio(), (4, pcm(2000, 8000, 2000, 4000)))

    def test_default_and_explicit_unity_do_not_rescale_native_pcm(self):
        player = self.Player(2, 16000, 16)
        # Already attenuated by a native engine: do not apply driver volume again.
        native_pcm = pcm(-8192, 8191, -1, 1, 0, 1001)
        player.feed(native_pcm)
        player.setVolume(all=1)
        player.feed(native_pcm + pcm(123), size=len(native_pcm))
        self.assertEqual(self.audio(), (6, native_pcm * 2))

    def test_zero_gain_mutes_without_losing_frames(self):
        player = self.Player(2, 16000, 16)
        player.setVolume(all=0)
        player.feed(pcm(-32768, 32767, -1, 1))
        self.assertEqual(self.audio(), (2, b'\x00' * 8))
        self.assertEqual(self.sink.frames, 2)

    def test_global_hard_mute_still_overrides_stream_gain(self):
        self.sink.volume = 0
        player = self.Player(1, 16000, 16)
        player.setVolume(all=0.5)
        player.feed(pcm(-32768, 32767))
        self.assertEqual(self.audio(), (2, pcm(0, 0)))

    def test_lifecycle_and_empty_feed_preserve_stream_gain_and_callback(self):
        player = self.Player(1, 16000, 16)
        player.setVolume(all=0.5)
        done = []
        player.open()
        player.feed(b'', onDone=lambda: done.append(True))
        player.pause(True)
        player.pause(False)
        player.sync()
        player.idle()
        player.stop()
        player.close()
        player.open()
        player.feed(pcm(8000))
        self.assertEqual(done, [True])
        self.assertEqual(self.audio(), (1, pcm(4000)))


if __name__ == '__main__':
    unittest.main()
