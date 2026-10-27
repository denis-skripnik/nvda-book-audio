"""Actual private voice checks, including the process protocol."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys
import test_runtime as runtime

sys.path.insert(0, str(runtime.PLUGIN))
SCRATCH = Path(tempfile.gettempdir())


@unittest.skipUnless(runtime.NVDA.exists() and runtime.PYTHON.exists(), 'Installed NVDA integration')
class ProbeRuntimeTests(unittest.TestCase):
    def test_probe_returns_real_audio_evidence_without_output_folder(self):
        events = runtime.RuntimeTests.run_worker(self, 'sapi5', 'probe')
        result = events[-1]
        self.assertEqual(result['type'], 'compatibility')
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['driver'], 'sapi5')
        self.assertTrue(result['voice'])
        self.assertEqual(result['rate'], 50)
        self.assertGreater(result['frames'], 1000)
        self.assertGreater(result['sampleRate'], 0)
        self.assertGreater(result['mp3Bytes'], 1000)

    def test_probe_preserves_requested_rate_when_driver_quantizes_it(self):
        from client import WorkerClient
        result = WorkerClient().run({
            'nvda': str(runtime.NVDA), 'addons': [], 'driver': 'sapi5',
            'action': 'probe', 'voice': '', 'rate': 43,
        }, lambda event: None)
        self.assertEqual(result['rate'], 43)
        self.assertGreater(result['effectiveRate'], -1)

    def test_client_accepts_completed_voice_probe(self):
        from client import WorkerClient
        events = []
        result = WorkerClient().run({
            'nvda': str(runtime.NVDA), 'addons': [], 'driver': 'sapi5_32',
            'action': 'probe', 'voice': '', 'rate': 45,
        }, events.append)
        self.assertEqual(result['type'], 'compatibility')
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['rate'], 45)
        self.assertGreater(result['frames'], 1000)
        self.assertEqual(events[-1], result)


if __name__ == '__main__':
    tempfile.tempdir = str(SCRATCH)
    unittest.main()
