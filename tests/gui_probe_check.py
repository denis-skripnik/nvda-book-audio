"""Native wx recording-verification checks; isolated config, never live NVDA."""
from pathlib import Path
import os
import sys
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from unittest.mock import patch

import gui_focus_check as host
from gui_focus_check import dialog_module, wx


class ProbeRunner(host.ControlledRunner):
    def run(self, request, progress):
        self.request = dict(request)
        self.progress = progress
        self.started.set()
        if not self.release.wait(8):
            raise RuntimeError('Test did not release probe')
        if request['action'] == 'voices':
            return {'voices': [{'id': 'one', 'name': 'Voice one'}, {'id': 'two', 'name': 'Voice two'}]}
        if getattr(self, 'error', None):
            raise self.error
        if hasattr(self, 'result'):
            return self.result
        return {'type': 'compatibility', 'status': 'verified', 'driver': request['driver'],
                'voice': request['voice'], 'rate': request['rate'], 'volume': request['volume'], 'frames': 1000,
                'sampleRate': 22050, 'mp3Bytes': 800, 'bitrate': request['bitrate'],
                'commaPauseMs': request.get('commaPauseMs', 0), 'sentencePauseMs': request.get('sentencePauseMs', 0)}


class ProbeChecks(unittest.TestCase):
    setUpClass = classmethod(host.FocusChecks.setUpClass.__func__)
    tearDownClass = classmethod(host.FocusChecks.tearDownClass.__func__)
    pump = host.FocusChecks.pump
    tearDown = host.FocusChecks.tearDown

    def setUp(self):
        from bookAudio.i18n import set_language
        set_language('ru')
        self.runners = []
        def factory(**kwargs):
            runner = ProbeRunner()
            self.runners.append(runner)
            return runner
        self.patcher = patch.object(dialog_module, 'WorkerClient', side_effect=factory)
        self.patcher.start()
        self.dialog = dialog_module.BookDialog(None, [('a', 'Driver A'), ('b', 'Driver B')],
                                              {'language': 'ru', 'rate': 37, 'nvda': 'isolated-nvda', 'addons': []}, preferences_dir=False)
        self.dialog.Show()
        self.pump(lambda: self.runners[0].started.is_set())
        self.runners[0].release.set()
        self.pump(lambda: not self.dialog.loadingVoices)

    def test_probe_without_files_or_output_uses_selected_configuration(self):
        d = self.dialog
        self.assertTrue(hasattr(d, 'probeButton'), 'Missing recording verification button')
        self.assertEqual(d.probeButton.GetLabel().replace('&', ''), 'Проверить запись')
        self.assertIn('не проверена', d.probeStatus.GetValue())
        self.assertTrue(d.probeStatus.HasFlag(wx.TE_READONLY))
        self.assertTrue(d.probeButton.IsEnabled())
        d.voice.SetSelection(1)
        d.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        self.assertEqual(runner.request, dict(d.context, action='probe', driver='a', voice='two', rate=37, volume=100, bitrate=128,
                                              commaPauseMs=0, sentencePauseMs=0))
        self.assertEqual(d.paths, [])
        self.assertEqual(d.output.GetValue(), '')
        self.assertIn('Проверка', d.probeStatus.GetValue())
        self.assertTrue(d.cancelButton.IsEnabled())
        self.assertFalse(d.probeButton.IsEnabled())
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertIn('проверена', d.probeStatus.GetValue())
        self.assertNotIn('не проверена', d.probeStatus.GetValue())
        self.assertTrue(d.probeButton.IsEnabled())

    def finish_probe(self):
        self.dialog.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        runner.release.set()
        self.pump(lambda: not self.dialog.running)

    def test_driver_voice_and_rate_changes_invalidate_verification(self):
        d = self.dialog
        for control, kind in ((d.voice, wx.EVT_CHOICE), (d.rate, wx.EVT_SPINCTRL),
                              (d.rate, wx.EVT_TEXT), (d.drivers, wx.EVT_CHOICE)):
            with self.subTest(control=control.GetId(), event=kind.typeId):
                self.finish_probe()
                self.assertNotIn('не проверена', d.probeStatus.GetValue())
                if control == d.voice:
                    control.SetSelection(1)
                elif control == d.drivers:
                    control.SetSelection(1)
                else:
                    control.SetValue(control.GetValue() + 1)
                event = wx.CommandEvent(kind.typeId, control.GetId())
                event.SetEventObject(control)
                control.GetEventHandler().ProcessEvent(event)
                self.assertIn('не проверена', d.probeStatus.GetValue())
                if d.loadingVoices:
                    self.assertFalse(d.probeButton.IsEnabled())
                    self.assertTrue(d.drivers.IsEnabled())
                    self.runners[-1].release.set()
                    self.pump(lambda: not d.loadingVoices)
                    self.assertIn('не проверена', d.probeStatus.GetValue())


    def test_only_matching_positive_compatibility_result_verifies_recording(self):
        for replacement in ({'type': 'done'}, {'status': 'failed'}, {'driver': 'b'},
                            {'voice': 'two'}, {'rate': 90}, {'frames': 0},
                            {'sampleRate': 0}, {'mp3Bytes': 0}):
            with self.subTest(replacement=replacement):
                self.dialog.on_probe(None)
                runner = self.runners[-1]
                self.pump(lambda: runner.started.is_set())
                runner.result = dict(type='compatibility', status='verified', driver='a',
                                     voice='one', rate=37, volume=100, frames=100, sampleRate=22050, mp3Bytes=800,
                                     bitrate=128, commaPauseMs=0, sentencePauseMs=0)
                runner.result.update(replacement)
                runner.release.set()
                self.pump(lambda: not self.dialog.running)
                self.assertIn('Ошибка проверки записи', self.dialog.probeStatus.GetValue())

    def test_cancelled_probe_never_verifies_even_if_success_was_already_queued(self):
        d = self.dialog
        d.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        d.on_cancel(None)
        self.assertTrue(runner.cancelled.is_set())
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertIn('остановлена', d.probeStatus.GetValue())
        self.assertIn('не проверена', d.probeStatus.GetValue())
        self.assertTrue(d.probeButton.IsEnabled())

    def test_late_probe_progress_cannot_overwrite_new_voice_loading(self):
        self.finish_probe()
        obsolete = self.runners[-1]
        d = self.dialog
        d.drivers.SetSelection(1)
        d.on_driver(None)
        self.pump(lambda: self.runners[-1].started.is_set())
        status = d.status.GetValue()
        obsolete.progress({'type': 'status', 'message': 'obsolete probe'})
        self.pump()
        self.assertEqual(d.status.GetValue(), status)
        self.assertIn('не проверена', d.probeStatus.GetValue())

    def test_probe_failure_exposes_exception_and_allows_retry(self):
        d = self.dialog
        d.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        runner.error = RuntimeError('No PCM from this voice')
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertIn('Ошибка проверки записи: No PCM', d.probeStatus.GetValue())
        self.assertTrue(d.probeButton.IsEnabled())
        self.finish_probe()
        self.assertNotIn('Ошибка', d.probeStatus.GetValue())

    def test_probe_completion_does_not_steal_keyboard_focus(self):
        d = self.dialog
        d.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        d.probeStatus.SetFocus()
        self.pump(lambda: wx.Window.FindFocus() == d.probeStatus)
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertEqual(wx.Window.FindFocus(), d.probeStatus)

    def test_probe_close_cancels_and_ignores_callbacks_after_destruction(self):
        d = self.dialog
        d.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        event = wx.CommandEvent(wx.EVT_BUTTON.typeId, d.closeButton.GetId())
        d.on_close(event)
        self.assertTrue(d.alive)
        self.assertTrue(d.closePending)
        self.assertTrue(runner.cancelled.is_set())
        runner.release.set()
        self.pump(lambda: not bool(d))
        self.assertFalse(d.alive)
        runner.progress({'type': 'status', 'message': 'after destroy'})
        self.pump()
        self.assertFalse(d.running)
        self.assertIsNone(d.runner)

    def test_english_probe_labels_and_states(self):
        from bookAudio.i18n import set_language
        self.dialog.destroy_dialog()
        self.pump(lambda: not bool(self.dialog))
        set_language('en')
        d = self.dialog = dialog_module.BookDialog(None, [('a', 'Driver A')], {'language': 'en'}, preferences_dir=False)
        d.Show()
        self.runners[-1].release.set()
        self.pump(lambda: not d.loadingVoices)
        self.assertEqual(d.probeButton.GetLabel(), 'Verify recording')
        self.assertIn('not yet verified', d.probeStatus.GetValue())
        d.on_probe(None)
        self.pump(lambda: self.runners[-1].started.is_set())
        self.assertEqual(d.probeStatus.GetValue(), 'Checking recording…')
        self.runners[-1].release.set()
        self.pump(lambda: not d.running)
        self.assertIn('Recording verified', d.probeStatus.GetValue())
        d.invalidate_probe()
        self.assertIn('not yet verified', d.probeStatus.GetValue())
        d.on_probe(None)
        self.pump(lambda: self.runners[-1].started.is_set())
        self.runners[-1].error = RuntimeError('No PCM')
        self.runners[-1].release.set()
        self.pump(lambda: not d.running)
        self.assertEqual(d.probeStatus.GetValue(), 'Recording verification failed: No PCM')

    def test_probe_titlebar_close_defers_destruction(self):
        self.dialog.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        event = wx.CloseEvent(wx.EVT_CLOSE.typeId, self.dialog.GetId())
        event.SetCanVeto(True)
        self.dialog.GetEventHandler().ProcessEvent(event)
        self.assertTrue(event.GetVeto())
        self.assertTrue(runner.cancelled.is_set())
        self.assertTrue(self.dialog.alive)
        runner.release.set()
        self.pump(lambda: not bool(self.dialog))

    def test_probe_escape_close_defers_destruction(self):
        self.dialog.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        event = wx.KeyEvent(wx.EVT_CHAR_HOOK.typeId)
        event.SetKeyCode(wx.WXK_ESCAPE)
        self.dialog.GetEventHandler().ProcessEvent(event)
        self.assertTrue(runner.cancelled.is_set())
        self.assertTrue(self.dialog.alive)
        runner.release.set()
        self.pump(lambda: not bool(self.dialog))

    def test_unload_cancels_and_joins_probe_thread(self):
        self.dialog.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        class Tray(wx.EvtHandler):
            def __init__(self):
                super().__init__()
                self.toolsMenu = wx.Menu()
        frame = wx.Frame(None)
        frame.sysTrayIcon = Tray()
        previous = host.gui.mainFrame
        host.gui.mainFrame = frame
        plugin = host.bookAudio.GlobalPlugin()
        plugin.dialog = self.dialog
        timer = threading.Timer(.1, runner.release.set)
        timer.start()
        try:
            plugin.terminate()
            self.assertTrue(runner.cancelled.is_set())
            self.assertFalse(self.dialog.alive)
            self.assertFalse(self.dialog.workerThread.is_alive())
            runner.progress({'type': 'status', 'message': 'after unload'})
            self.pump()
        finally:
            timer.join()
            host.gui.mainFrame = previous
            frame.Destroy()

    def test_real_worker_probe_verifies_espeak_without_user_files(self):
        self.dialog.destroy_dialog()
        self.pump(lambda: not bool(self.dialog))
        self.patcher.stop()
        d = self.dialog = dialog_module.BookDialog(None, [('espeak', 'eSpeak NG')],
            {'nvda': os.environ.get('BOOK_AUDIO_TEST_NVDA', 'C:/Program Files/NVDA'), 'addons': [], 'language': 'ru', 'rate': 50}, preferences_dir=False)
        d.Show()
        self.pump(lambda: not d.loadingVoices)
        self.assertTrue(d.voiceItems, d.status.GetValue())
        self.assertTrue(d.probeButton.IsEnabled())
        d.on_probe(None)
        self.pump(lambda: not d.running)
        self.assertIn('Запись проверена', d.probeStatus.GetValue())
        self.assertEqual(d.paths, [])
        self.assertEqual(d.output.GetValue(), '')


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        host._host.cleanup()
