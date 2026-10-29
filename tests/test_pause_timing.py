"""Long requested pauses must not exhaust the ordinary speech deadline."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addon/globalPlugins/bookAudio'))
import worker


class PauseTimingTests(unittest.TestCase):
    def test_pause_budget_extends_deadline_and_keeps_default_bounded(self):
        budget = getattr(worker, 'speech_timeout_seconds', None)
        self.assertTrue(callable(budget), 'Missing bounded pause-aware synthesis deadline')
        self.assertEqual(budget([('text', 'Plain speech')]), 180)
        seconds = budget([('text', 'Words,'), ('pause', 2000)] * 100)
        self.assertGreater(seconds, 180 + 200)
        self.assertLess(seconds, 3600)


if __name__ == '__main__':
    unittest.main()
