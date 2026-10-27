"""Real wx close/cancel regressions in an isolated host, never live NVDA."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
import worker

# Use Hermes scratch, not NVDA's user profile or a system temporary directory.
_host = tempfile.TemporaryDirectory(prefix='gui-close-', dir=ROOT.parent)
worker.bootstrap({'nvda': 'C:/Program Files/NVDA', 'config': str(Path(_host.name) / 'config'), 'addons': []})
import wx

pkg = types.ModuleType('bookAudio')
pkg.__path__ = [str(PLUGIN)]
sys.modules['bookAudio'] = pkg
from bookAudio import dialog as dialog_module


class ControlledRunner:
    """Keep completion blocked until the test has checked deferred closing."""
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()
        self.cancel_count = 0

    def run(self, request, progress):
        self.started.set()
        if not self.release.wait(5):
            raise RuntimeError('Test failed to release the worker')
        raise dialog_module.Cancelled()

    def cancel(self):
        self.cancel_count += 1
        self.cancelled.set()


class CloseChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App(False)
        cls.app.SetExitOnFrameDelete(False)
        cls.loop = wx.GUIEventLoop()
        cls.activator = wx.EventLoopActivator(cls.loop)

    @classmethod
    def tearDownClass(cls):
        cls.app.Destroy()

    def pump_until(self, condition):
        deadline = time.monotonic() + 5
        while not condition():
            self.app.Yield()
            self.loop.ProcessIdle()
            if time.monotonic() > deadline:
                self.fail('Timed out waiting for asynchronous wx cleanup')
            time.sleep(0.005)

    def close(self, dialog, kind):
        if kind == 'button':
            event = wx.CommandEvent(wx.EVT_BUTTON.typeId, dialog.closeButton.GetId())
            event.SetEventObject(dialog.closeButton)
            # Invoke the bound handler directly so unittest reports wx callback errors.
            dialog.on_close(event)
        elif kind == 'titlebar':
            event = wx.CloseEvent(wx.EVT_CLOSE.typeId, dialog.GetId())
            event.SetCanVeto(True)
            dialog.GetEventHandler().ProcessEvent(event)
            return event
        else:
            event = wx.KeyEvent(wx.EVT_CHAR_HOOK.typeId)
            event.SetKeyCode(wx.WXK_ESCAPE)
            self.assertEqual(event.GetKeyCode(), wx.WXK_ESCAPE)
            dialog.GetEventHandler().ProcessEvent(event)
        return event

    def test_busy_close_defers_destruction_until_worker_finish(self):
        # Voice discovery is disposable; a running book now hides instead.
        for state in ('voices',):
            for kind in ('button', 'titlebar', 'escape'):
                with self.subTest(state=state, event=kind):
                    dialog = dialog_module.BookDialog(None, [], {})
                    runner = ControlledRunner()
                    completed = []
                    destroyed = []
                    dialog_id = dialog.GetId()
                    dialog.Bind(wx.EVT_WINDOW_DESTROY, lambda event: destroyed.append(event.GetId()) if event.GetId() == dialog_id else None)
                    dialog.loadingVoices = state == 'voices'
                    dialog.running = state == 'conversion'
                    finish = dialog.voices_finished if state == 'voices' else dialog.conversion_finished

                    def finished(result, error):
                        completed.append((dialog.alive, dialog.closePending))
                        finish(result, error)

                    try:
                        with patch.object(dialog_module, 'WorkerClient', return_value=runner):
                            dialog.run_background({'action': state}, finished)
                        self.assertTrue(runner.started.wait(2))
                        event = self.close(dialog, kind)
                        self.assertTrue(runner.cancelled.is_set())
                        self.assertEqual(runner.cancel_count, 1)
                        self.assertTrue(dialog.closePending)
                        self.assertTrue(dialog.alive)
                        self.assertTrue(bool(dialog))
                        self.assertEqual(completed, [])
                        self.assertEqual(destroyed, [])
                        if kind == 'titlebar':
                            self.assertTrue(event.GetVeto())
                        runner.release.set()
                        self.pump_until(lambda: not bool(dialog))
                        self.assertEqual(completed, [(True, True)])
                        self.assertFalse(dialog.alive)
                        self.assertIsNone(dialog.runner)
                        self.assertFalse(dialog.loadingVoices if state == 'voices' else dialog.running)
                        self.assertEqual(len(destroyed), 1)
                    finally:
                        runner.release.set()
                        self.pump_until(lambda: bool(completed))
                        if dialog.alive:
                            dialog.destroy_dialog()
                        self.pump_until(lambda: not bool(dialog))

    def test_idle_close_destroys_immediately(self):
        for kind in ('button', 'titlebar', 'escape'):
            with self.subTest(event=kind):
                dialog = dialog_module.BookDialog(None, [], {})
                self.close(dialog, kind)
                self.assertFalse(dialog.alive)
                self.assertFalse(dialog.closePending)
                self.pump_until(lambda: not bool(dialog))


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        _host.cleanup()
