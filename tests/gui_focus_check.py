"""Native wx focus/racing-worker regressions; no primary NVDA profile changes."""
from pathlib import Path
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
import worker
_host = tempfile.TemporaryDirectory(prefix='gui-focus-', dir=os.environ['TMPDIR'])
worker.bootstrap({'nvda': 'C:/Program Files/NVDA', 'config': str(Path(_host.name) / 'config'), 'addons': []})
import wx
import gui
sys.path.insert(0, str(PLUGIN.parent))
import bookAudio
from bookAudio import dialog as dialog_module


class ControlledRunner:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()
        self.driver = None
        self.progress = None

    def run(self, request, progress):
        self.driver = request['driver']
        self.progress = progress
        self.started.set()
        if not self.release.wait(8):
            raise RuntimeError('Test did not release controlled worker')
        return {'voices': [{'id': self.driver, 'name': self.driver}]}

    def cancel(self):
        self.cancelled.set()


class FocusChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App(False)
        cls.app.SetExitOnFrameDelete(False)
        cls.loop = wx.GUIEventLoop()
        cls.activator = wx.EventLoopActivator(cls.loop)

    @classmethod
    def tearDownClass(cls):
        cls.app.Destroy()

    def pump(self, condition=lambda: True):
        deadline = time.monotonic() + 5
        while True:
            self.app.Yield()
            self.loop.ProcessIdle()
            if condition():
                return
            if time.monotonic() > deadline:
                self.fail('Timed out waiting for native wx/thread condition')
            time.sleep(.005)

    def setUp(self):
        self.runners = []
        def factory(**kwargs):
            runner = ControlledRunner()
            self.runners.append(runner)
            return runner
        self.patcher = patch.object(dialog_module, 'WorkerClient', side_effect=factory)
        self.patcher.start()
        self.dialog = dialog_module.BookDialog(None, [('a', 'Driver A'), ('b', 'Driver B'), ('c', 'Driver C')], {})
        self.dialog.Show()
        self.pump(lambda: self.runners[0].started.is_set())
        self.runners[0].release.set()
        self.pump(lambda: not self.dialog.loadingVoices)

    def tearDown(self):
        for runner in self.runners:
            runner.release.set()
        self.pump(lambda: not any(t.name == 'bookAudio-client' for t in threading.enumerate()))
        if self.dialog.alive:
            self.dialog.destroy_dialog()
        self.pump(lambda: not bool(self.dialog))
        self.patcher.stop()

    def select(self, index):
        self.dialog.drivers.SetFocus()
        self.pump(lambda: wx.Window.FindFocus() == self.dialog.drivers)
        self.dialog.drivers.SetSelection(index)
        event = wx.CommandEvent(wx.EVT_CHOICE.typeId, self.dialog.drivers.GetId())
        event.SetEventObject(self.dialog.drivers)
        self.dialog.drivers.GetEventHandler().ProcessEvent(event)
        self.pump(lambda: self.runners[-1].started.is_set())
        return self.runners[-1]

    def test_file_picker_offers_fb2_zip(self):
        from unittest.mock import MagicMock
        picker = MagicMock()
        picker.__enter__.return_value.ShowModal.return_value = wx.ID_CANCEL
        with patch.object(wx, 'FileDialog', return_value=picker) as factory:
            self.dialog.on_add(None)
        wildcard = factory.call_args.kwargs['wildcard']
        self.assertIn('*.fb2.zip', wildcard.split('|')[1])
        self.assertIn('FB2.ZIP', wildcard.split('|')[0])

    def test_driver_focus_retained_during_and_after_loading(self):
        runner = self.select(1)
        self.assertTrue(self.dialog.drivers.IsEnabled(), 'Driver selection disabled during voice loading')
        self.assertEqual(wx.Window.FindFocus(), self.dialog.drivers)
        self.assertFalse(self.dialog.voice.IsEnabled())
        self.assertFalse(self.dialog.startButton.IsEnabled())
        runner.release.set()
        self.pump(lambda: not self.dialog.loadingVoices)
        self.assertEqual(wx.Window.FindFocus(), self.dialog.drivers)

    def test_keyboard_navigation_not_stolen_on_completion(self):
        runner = self.select(1)
        self.assertTrue(self.dialog.rate.IsEnabled(), 'Rate must remain keyboard reachable while loading')
        self.dialog.drivers.Navigate(wx.NavigationKeyEvent.IsForward)
        self.pump(lambda: wx.Window.FindFocus() != self.dialog.drivers)
        focused = wx.Window.FindFocus()
        self.assertEqual(focused, self.dialog.rate)
        runner.release.set()
        self.pump(lambda: not self.dialog.loadingVoices)
        self.assertEqual(wx.Window.FindFocus(), focused)

    def test_rapid_selection_cancels_superseded_worker_and_ignores_late_callbacks(self):
        obsolete = self.select(1)
        current = self.select(2)
        self.assertTrue(obsolete.cancelled.is_set(), 'Superseded voice worker was not cancelled')
        current_runner = self.dialog.runner
        status = self.dialog.status.GetValue()
        obsolete.progress({'type': 'status', 'message': 'obsolete progress'})
        obsolete.release.set()
        self.pump(lambda: not any(t.name == 'bookAudio-client' and t is not self.dialog.workerThread for t in threading.enumerate()))
        self.pump()
        self.assertTrue(self.dialog.loadingVoices)
        self.assertIs(self.dialog.runner, current_runner)
        self.assertEqual(self.dialog.voiceItems, [])
        self.assertEqual(self.dialog.status.GetValue(), status)
        current.release.set()
        self.pump(lambda: not self.dialog.loadingVoices)
        self.assertEqual(self.dialog.voiceItems[0]['id'], 'c')
        # A later obsolete completion must not replace already loaded voices either.
        obsolete = self.select(0)
        current = self.select(1)
        current.release.set()
        self.pump(lambda: not self.dialog.loadingVoices)
        obsolete.release.set()
        self.pump(lambda: not any(t.name == 'bookAudio-client' for t in threading.enumerate()))
        self.pump()
        self.assertEqual(self.dialog.voiceItems[0]['id'], 'b')

    def test_unload_joins_superseded_workers_even_after_dialog_close(self):
        self.check_unload(False)

    def test_unload_joins_closed_dialog_workers_after_reopening(self):
        self.check_unload(True)

    def check_unload(self, reopen):
        obsolete = self.select(1)
        current = self.select(2)
        old_thread = next(t for t in threading.enumerate() if t.name == 'bookAudio-client' and t is not self.dialog.workerThread)
        self.dialog.Close()
        self.assertTrue(current.cancelled.is_set())
        current.release.set()
        self.pump(lambda: not self.dialog.alive)
        self.assertTrue(old_thread.is_alive(), 'Test needs overlapping obsolete cleanup at unload')
        class Tray(wx.EvtHandler):
            def __init__(self):
                super().__init__()
                self.toolsMenu = wx.Menu()
        frame = wx.Frame(None)
        frame.sysTrayIcon = Tray()
        frame.prePopup = lambda: None
        frame.postPopup = lambda: None
        previous = gui.mainFrame
        gui.mainFrame = frame
        plugin = bookAudio.GlobalPlugin()
        plugin.dialog = self.dialog
        if reopen:
            with patch.object(bookAudio.synthDriverHandler, 'getSynth', return_value=None), patch.object(bookAudio.synthDriverHandler, 'getSynthList', return_value=[]):
                plugin.on_open(None)
            self.assertIsNot(plugin.dialog, self.dialog)
        timer = threading.Timer(.1, obsolete.release.set)
        timer.start()
        try:
            plugin.terminate()
            self.assertFalse(old_thread.is_alive(), 'Unload returned with obsolete client thread alive')
            self.assertTrue(obsolete.cancelled.is_set())
            self.assertFalse(any(t.name == 'bookAudio-client' for t in threading.enumerate()))
        finally:
            timer.join()
            gui.mainFrame = previous
            frame.Destroy()


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        _host.cleanup()
