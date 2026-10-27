"""Native modeless-window background conversion checks, isolated from live NVDA."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gui_focus_check as host
from gui_focus_check import dialog_module, wx


class ConversionRunner(host.ControlledRunner):
    def run(self, request, progress):
        if request['action'] == 'voices':
            return super().run(request, progress)
        self.progress = progress
        self.started.set()
        if not self.release.wait(8):
            raise RuntimeError('Test did not release conversion')
        if self.cancelled.is_set():
            raise dialog_module.Cancelled()
        if getattr(self, 'error', None):
            raise RuntimeError(self.error)
        return {'type': 'done', 'count': 2}

    def cancel(self):
        super().cancel()
        self.release.set()


class BackgroundChecks(unittest.TestCase):
    setUpClass = classmethod(host.FocusChecks.setUpClass.__func__)
    tearDownClass = classmethod(host.FocusChecks.tearDownClass.__func__)
    pump = host.FocusChecks.pump
    tearDown = host.FocusChecks.tearDown

    def setUp(self):
        from bookAudio.i18n import set_language
        set_language('ru')
        self.runners = []
        def factory(**kwargs):
            runner = ConversionRunner()
            self.runners.append(runner)
            return runner
        self.patcher = patch.object(dialog_module, 'WorkerClient', side_effect=factory)
        self.patcher.start()
        self.dialog = dialog_module.BookDialog(None, [('a', 'Driver A')], {})
        self.dialog.Show()
        self.pump(lambda: self.runners[0].started.is_set())
        self.runners[0].release.set()
        self.pump(lambda: not self.dialog.loadingVoices)
        self.dialog.add_paths([str(Path(host._host.name) / 'fixture.txt')])
        self.dialog.output.SetValue(host._host.name)

    def start_conversion(self):
        self.dialog.on_start(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        self.assertTrue(self.dialog.running)
        return runner

    def escape(self):
        event = wx.KeyEvent(wx.EVT_CHAR_HOOK.typeId)
        event.SetKeyCode(wx.WXK_ESCAPE)
        self.dialog.GetEventHandler().ProcessEvent(event)

    def test_hidden_completion_keeps_window_hidden_and_reopens_on_result(self):
        d = self.dialog
        runner = self.start_conversion()
        self.escape()
        with patch.object(d.status, 'SetFocus', wraps=d.status.SetFocus) as focus:
            runner.release.set()
            self.pump(lambda: not d.running)
            self.assertFalse(d.IsShown())
            focus.assert_not_called()
        self.assertIn('Создано MP3: 2', d.status.GetValue())
        d.Show()
        d.activate()
        self.pump()
        self.assertEqual(wx.Window.FindFocus(), d.status)

    def test_button_and_titlebar_hide_without_cancelling(self):
        d = self.dialog
        runner = self.start_conversion()
        button = wx.CommandEvent(wx.EVT_BUTTON.typeId, d.closeButton.GetId())
        button.SetEventObject(d.closeButton)
        d.closeButton.GetEventHandler().ProcessEvent(button)
        self.assertFalse(d.IsShown())
        self.assertFalse(runner.cancelled.is_set())
        d.Show()
        close = wx.CloseEvent(wx.EVT_CLOSE.typeId, d.GetId())
        close.SetCanVeto(True)
        d.GetEventHandler().ProcessEvent(close)
        self.assertTrue(close.GetVeto())
        self.assertFalse(d.IsShown())
        self.assertFalse(runner.cancelled.is_set())
        self.assertTrue(d.alive)

    def test_reopen_through_plugin_reuses_job_and_unload_cancels(self):
        import bookAudio
        import gui
        d = self.dialog
        runner = self.start_conversion()
        self.escape()
        class Tray(wx.EvtHandler):
            def __init__(self):
                super().__init__()
                self.toolsMenu = wx.Menu()
        frame = wx.Frame(None)
        frame.sysTrayIcon = Tray()
        previous = gui.mainFrame
        gui.mainFrame = frame
        plugin = bookAudio.GlobalPlugin()
        plugin.dialog = d
        try:
            count = len(self.runners)
            plugin.on_open(None)
            self.assertIs(plugin.dialog, d)
            self.assertTrue(d.IsShown())
            self.assertIs(d.runner, runner)
            self.assertEqual(len(self.runners), count)
            self.assertFalse(runner.cancelled.is_set())
            self.escape()
            plugin.terminate()
            self.assertTrue(runner.cancelled.is_set())
            self.assertFalse(d.alive)
            self.assertFalse(any(thread.is_alive() for thread in d.workerThreads))
        finally:
            if d.alive:
                plugin.terminate()
            gui.mainFrame = previous
            frame.Destroy()

    def test_explicit_stop_still_cancels_after_reopen(self):
        d = self.dialog
        runner = self.start_conversion()
        self.escape()
        d.Show()
        d.activate()
        d.on_cancel(None)
        self.pump(lambda: not d.running)
        self.assertTrue(runner.cancelled.is_set())
        self.assertIn('Остановлено', d.status.GetValue())

    def test_hidden_failure_stays_hidden_and_preserves_error(self):
        d = self.dialog
        runner = self.start_conversion()
        runner.error = 'fixture conversion failure'
        self.escape()
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertFalse(d.IsShown())
        self.assertEqual(d.status.GetValue(), 'fixture conversion failure')
        d.Show()
        d.activate()
        self.pump()
        self.assertEqual(wx.Window.FindFocus(), d.status)

    def test_real_conversion_finishes_hidden_with_three_mp3(self):
        from bookAudio.client import WorkerClient
        self.dialog.destroy_dialog()
        with patch.object(dialog_module, 'WorkerClient', WorkerClient):
            self.dialog = dialog_module.BookDialog(None, [('espeak', 'eSpeak NG')],
                {'nvda': 'C:/Program Files/NVDA', 'addons': [], 'driver': 'espeak', 'rate': 50})
            d = self.dialog
            d.Show()
            self.pump(lambda: not d.loadingVoices)
            source = Path(host._host.name) / 'background-real.txt'
            source.write_text('Вступление.\nГлава 1\nПервая часть.\nГлава 2\nВторая часть.', encoding='utf-8')
            d.add_paths([str(source)])
            d.output.SetValue(host._host.name)
            d.on_start(None)
            self.escape()
            self.assertFalse(d.IsShown())
            self.assertTrue(d.alive)
            self.pump(lambda: not d.running)
            self.assertFalse(d.IsShown())
            self.assertIn('Создано MP3: 3', d.status.GetValue())
            files = list(Path(host._host.name).glob('background-real*/*.mp3'))
            self.assertEqual(len(files), 3)
            self.assertTrue(all(file.stat().st_size > 1000 for file in files))
            d.Show()
            d.activate()
            self.pump()
            self.assertEqual(wx.Window.FindFocus(), d.status)

    def test_escape_hides_without_cancelling_and_keeps_progress(self):
        d = self.dialog
        runner = self.start_conversion()
        self.escape()
        self.assertFalse(runner.cancelled.is_set(), 'Escape must not interrupt book creation')
        self.assertTrue(d.alive)
        self.assertFalse(d.IsShown())
        self.assertFalse(d.closePending)
        runner.progress({'type': 'chapter', 'message': 'Chapter two', 'chapter': 2, 'chapters': 3})
        self.pump(lambda: d.status.GetValue() == 'Chapter two')
        self.assertGreater(d.progress.GetValue(), 0)
        self.assertTrue(d.running)
        d.Show()
        d.activate()
        self.pump(lambda: wx.Window.FindFocus() == d.status)
        self.assertEqual(d.status.GetValue(), 'Chapter two')
        self.assertIs(d.runner, runner)
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertIn('Создано MP3: 2', d.status.GetValue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
