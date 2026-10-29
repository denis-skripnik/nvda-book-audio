"""Native conditional extra-pause controls; isolated NVDA configuration only."""
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gui_probe_check as probe
from gui_probe_check import host, wx, dialog_module


class PauseRunner(probe.ProbeRunner):
    def run(self, request, progress):
        self.request = dict(request)
        self.progress = progress
        self.started.set()
        if not self.release.wait(8):
            raise RuntimeError('Test did not release pause worker')
        if getattr(self, 'error', None):
            raise self.error
        if hasattr(self, 'result'):
            return self.result
        if request['action'] == 'voices':
            return {'voices': [{'id': 'one', 'name': 'Voice one'}], 'supportsPauses': True}
        return dict(request, type='compatibility', status='verified', frames=1000,
                    sampleRate=22050, mp3Bytes=800)


class PauseChecks(unittest.TestCase):
    setUpClass = classmethod(host.FocusChecks.setUpClass.__func__)
    tearDownClass = classmethod(host.FocusChecks.tearDownClass.__func__)
    tearDown = host.FocusChecks.tearDown
    pump = host.FocusChecks.pump

    def setUp(self):
        from bookAudio.i18n import set_language
        set_language('ru')
        self.runners = []
        def factory(**kwargs):
            runner = PauseRunner()
            self.runners.append(runner)
            return runner
        self.patcher = patch.object(dialog_module, 'WorkerClient', side_effect=factory)
        self.patcher.start()
        self.dialog = dialog_module.BookDialog(None, [('a', 'Driver A'), ('b', 'Driver B')],
                                              {'language': 'ru', 'rate': 37}, preferences_dir=False)
        self.dialog.Show()
        self.pump(lambda: self.runners[-1].started.is_set())

    def loaded(self, result=None, error=None):
        runner = self.runners[-1]
        if result is not None:
            runner.result = result
        runner.error = error
        runner.release.set()
        self.pump(lambda: not self.dialog.loadingVoices)
        return runner

    def test_empty_worker_exception_hides_pauses_and_reports_voice_error(self):
        self.loaded(error=RuntimeError(''))
        d = self.dialog
        self.assertIn('Ошибка загрузки голосов:', d.status.GetValue())
        self.assertFalse(d.commaPause.IsShown())
        self.assertFalse(d.sentencePause.IsShown())
        self.assertFalse(d.startButton.IsEnabled())
        self.assertTrue(d.drivers.IsEnabled())

    def test_native_controls_initially_hidden_then_supported_range_labels_tab(self):
        d = self.dialog
        self.assertTrue(hasattr(d, 'commaPause'), 'Missing conditional comma-pause spin control')
        for control in (d.commaPause, d.sentencePause):
            self.assertIsInstance(control, wx.SpinCtrl)
            self.assertFalse(control.IsShown())
            self.assertEqual((control.GetMin(), control.GetMax(), control.GetValue()), (0, 2000, 0))
        self.loaded()
        labels = [c.GetLabel().replace('&', '') for c in d.GetChildren() if isinstance(c, wx.StaticText)]
        self.assertIn('Дополнительная пауза после запятой, мс:', labels)
        self.assertIn('Дополнительная пауза в конце предложения, мс:', labels)
        for before, after in ((d.bitrate, d.commaPause), (d.commaPause, d.sentencePause), (d.sentencePause, d.probeButton)):
            self.assertTrue(after.IsShown())
            before.SetFocus()
            self.pump(lambda: wx.Window.FindFocus() == before)
            before.Navigate(wx.NavigationKeyEvent.IsForward)
            self.pump(lambda: wx.Window.FindFocus() == after)

    def select_driver(self, index):
        self.dialog.drivers.SetSelection(index)
        self.dialog.on_driver(None)
        self.pump(lambda: self.runners[-1].started.is_set())
        return self.runners[-1]

    def test_capability_exact_true_hide_reset_error_tab_and_focus(self):
        self.loaded()
        d = self.dialog
        for capability in (False, None, 1, 'true', 'missing', 'error'):
            with self.subTest(capability=capability):
                if not d.commaPause.IsShown():
                    self.select_driver(0)
                    self.loaded()
                d.commaPause.SetValue(180)
                d.sentencePause.SetValue(360)
                d.commaPause.SetFocus()
                self.pump(lambda: wx.Window.FindFocus() == d.commaPause)
                self.select_driver(1)
                self.assertFalse(d.commaPause.IsShown())
                self.assertFalse(d.sentencePause.IsShown())
                self.assertEqual(wx.Window.FindFocus(), d.drivers)
                d.output.SetFocus()
                self.pump(lambda: wx.Window.FindFocus() == d.output)
                result = {'voices': [{'id': 'one', 'name': 'One'}]}
                if capability != 'missing':
                    result['supportsPauses'] = capability
                self.loaded(result, RuntimeError('no voices') if capability == 'error' else None)
                self.assertEqual(wx.Window.FindFocus(), d.output)
                self.assertFalse(d.commaPause.IsShown())
                self.assertEqual((d.commaPause.GetValue(), d.sentencePause.GetValue()), (0, 0))
                labels = [c for c in d.GetChildren() if isinstance(c, wx.StaticText) and 'Дополнительная' in c.GetLabel()]
                self.assertTrue(labels)
                self.assertTrue(all(not label.IsShown() for label in labels))
                d.bitrate.SetFocus()
                self.pump(lambda: wx.Window.FindFocus() == d.bitrate)
                d.bitrate.Navigate(wx.NavigationKeyEvent.IsForward)
                self.pump(lambda: wx.Window.FindFocus() == d.probeButton or capability == 'error')
                if capability != 'error':
                    d.probeButton.Navigate(wx.NavigationKeyEvent.IsBackward)
                    self.pump(lambda: wx.Window.FindFocus() == d.bitrate)

    def test_rapid_switch_generation_guards_capability_and_progress(self):
        self.loaded()
        obsolete = self.select_driver(1)
        current = self.select_driver(0)
        self.assertTrue(obsolete.cancelled.is_set())
        obsolete.result = {'voices': [{'id': 'old', 'name': 'Old'}], 'supportsPauses': True}
        obsolete.release.set()
        self.pump(lambda: not any(t.is_alive() for t in self.dialog.workerThreads if t is not self.dialog.workerThread))
        obsolete.progress({'type': 'status', 'message': 'obsolete'})
        self.pump()
        self.assertTrue(self.dialog.loadingVoices)
        self.assertFalse(self.dialog.commaPause.IsShown())
        self.assertNotEqual(self.dialog.status.GetValue(), 'obsolete')
        self.loaded({'voices': [{'id': 'new', 'name': 'New'}], 'supportsPauses': False})
        self.assertFalse(self.dialog.commaPause.IsShown())
        self.assertEqual(self.dialog.voiceItems[0]['id'], 'new')

    def finish_probe(self, replacement=None):
        d = self.dialog
        d.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        if replacement is not None:
            runner.result = dict(runner.request, type='compatibility', status='verified',
                                 frames=1000, sampleRate=22050, mp3Bytes=800)
            runner.result.update(replacement)
            for key, value in replacement.items():
                if value == 'missing':
                    runner.result.pop(key)
        runner.release.set()
        self.pump(lambda: not d.running)
        return runner

    def test_probe_request_busy_zero_and_selected_integer_values(self):
        self.loaded()
        d = self.dialog
        for comma, sentence in ((0, 0), (123, 2000)):
            d.commaPause.SetValue(comma)
            d.sentencePause.SetValue(sentence)
            d.on_probe(None)
            runner = self.runners[-1]
            self.pump(lambda: runner.started.is_set())
            for key, expected in (('commaPauseMs', comma), ('sentencePauseMs', sentence)):
                self.assertIs(type(runner.request.get(key)), int)
                self.assertEqual(runner.request[key], expected)
            self.assertFalse(d.commaPause.IsEnabled())
            self.assertFalse(d.sentencePause.IsEnabled())
            runner.release.set()
            self.pump(lambda: not d.running)
            self.assertTrue(d.commaPause.IsEnabled())
            self.assertNotIn('Ошибка', d.probeStatus.GetValue())

    def test_convert_request_and_unsupported_forced_zero(self):
        self.loaded()
        d = self.dialog
        d.add_paths([__file__])
        d.output.SetValue(os.environ['TMPDIR'])
        for supported in (True, False):
            if not supported:
                self.select_driver(1)
                self.loaded({'voices': [{'id': 'one', 'name': 'One'}], 'supportsPauses': False})
            d.commaPause.SetValue(99)
            d.sentencePause.SetValue(222)
            d.on_start(None)
            runner = self.runners[-1]
            self.pump(lambda: runner.started.is_set())
            self.assertEqual((runner.request.get('commaPauseMs'), runner.request.get('sentencePauseMs')),
                             (99, 222) if supported else (0, 0))
            self.assertFalse(d.commaPause.IsEnabled())
            runner.result = {'count': 1}
            runner.release.set()
            self.pump(lambda: not d.running)
        runner = self.finish_probe()
        self.assertEqual((runner.request['commaPauseMs'], runner.request['sentencePauseMs']), (0, 0))

    def test_probe_strict_pause_echo_rejects_missing_mismatch_and_wrong_type(self):
        self.loaded()
        for key in ('commaPauseMs', 'sentencePauseMs'):
            for value in (None, 1, '0', False, 'missing'):
                with self.subTest(key=key, value=value):
                    self.finish_probe({key: value})
                    self.assertIn('Ошибка проверки записи', self.dialog.probeStatus.GetValue())
        self.finish_probe()
        self.assertNotIn('Ошибка', self.dialog.probeStatus.GetValue())

    def test_spin_and_actual_typed_changes_invalidate_verification(self):
        import ctypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetFocus.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
        user32.SendMessageW.restype = ctypes.c_ssize_t
        self.loaded()
        d = self.dialog
        for control in (d.commaPause, d.sentencePause):
            self.finish_probe()
            self.assertNotIn('Ошибка', d.probeStatus.GetValue())
            event = wx.SpinEvent(wx.EVT_SPINCTRL.typeId, control.GetId())
            event.SetEventObject(control)
            control.GetEventHandler().ProcessEvent(event)
            self.assertIn('не проверена', d.probeStatus.GetValue())
            self.finish_probe()
            control.SetFocus()
            self.pump(lambda: wx.Window.FindFocus() == control)
            control.SetSelection(-1, -1)
            user32.SendMessageW(user32.GetFocus(), 0x0102, ord('7'), 0)
            self.pump(lambda: control.GetValue() == 7)
            self.assertIn('не проверена', d.probeStatus.GetValue())

    def test_english_labels_validation_and_unique_accelerators(self):
        from bookAudio.i18n import _, set_language
        self.loaded()
        self.dialog.destroy_dialog()
        self.pump(lambda: not bool(self.dialog))
        set_language('en')
        d = self.dialog = dialog_module.BookDialog(None, [('a', 'Driver A')], {'language': 'en'}, preferences_dir=False)
        d.Show()
        self.loaded()
        labels = [c.GetLabel() for c in d.GetChildren() if isinstance(c, wx.StaticText)]
        self.assertIn('Additional pause after co&mma, ms:', labels)
        self.assertIn('Additional pause at sentence &end, ms:', labels)
        self.assertEqual(_('Выбранный драйвер не поддерживает дополнительные паузы.'),
                         'The selected driver does not support additional pauses.')
        self.assertEqual(_('Пауза должна быть целым числом от 0 до 2000 мс.'),
                         'Pause must be an integer from 0 to 2000 ms.')
        accelerators = [label.split('&')[1][0].lower() for label in labels if '&' in label]
        accelerators += [c.GetLabel().split('&')[1][0].lower() for c in d.GetChildren()
                         if isinstance(c, wx.Button) and '&' in c.GetLabel()]
        self.assertEqual(len(accelerators), len(set(accelerators)))


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        host._host.cleanup()
