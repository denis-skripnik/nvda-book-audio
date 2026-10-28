"""Native wx output-volume checks; never install or restart live NVDA."""
from pathlib import Path
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gui_probe_check as probe
from gui_probe_check import host, wx


class VolumeChecks(unittest.TestCase):
    setUpClass = classmethod(host.FocusChecks.setUpClass.__func__)
    tearDownClass = classmethod(host.FocusChecks.tearDownClass.__func__)
    setUp = probe.ProbeChecks.setUp
    tearDown = host.FocusChecks.tearDown
    pump = host.FocusChecks.pump

    def test_native_volume_range_default_label_and_tab_after_rate(self):
        d = self.dialog
        self.assertTrue(hasattr(d, 'volume'), 'Missing accessible output-volume control')
        self.assertIsInstance(d.volume, wx.SpinCtrl)
        self.assertEqual((d.volume.GetMin(), d.volume.GetMax(), d.volume.GetValue()), (0, 100, 100))
        labels = [c for c in d.GetChildren() if isinstance(c, wx.StaticText)]
        self.assertTrue(any(c.GetLabel().replace('&', '') == 'Громкость, от 0 до 100:' for c in labels))
        self.assertGreater(d.volume.GetPosition().y, d.rate.GetPosition().y)
        d.rate.SetFocus()
        self.pump(lambda: wx.Window.FindFocus() == d.rate)
        d.rate.Navigate(wx.NavigationKeyEvent.IsForward)
        self.pump(lambda: wx.Window.FindFocus() == d.volume)
        d.volume.Navigate(wx.NavigationKeyEvent.IsBackward)
        self.pump(lambda: wx.Window.FindFocus() == d.rate)

    def test_probe_carries_volume_and_disables_editing_until_completion(self):
        d = self.dialog
        d.volume.SetValue(42)
        d.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        self.assertEqual(runner.request.get('volume'), 42)
        self.assertFalse(d.volume.IsEnabled())
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertTrue(d.volume.IsEnabled())

    def test_conversion_carries_zero_volume_and_disables_editing(self):
        d = self.dialog
        d.add_paths([__file__])
        d.output.SetValue(os.environ['TMPDIR'])
        d.volume.SetValue(0)
        d.on_start(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        self.assertEqual(runner.request['action'], 'convert')
        self.assertEqual(runner.request.get('volume'), 0)
        self.assertFalse(d.volume.IsEnabled())
        runner.result = {'count': 1}
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertTrue(d.volume.IsEnabled())

    def test_volume_stays_enabled_during_voice_discovery_without_focus_steal(self):
        d = self.dialog
        d.drivers.SetSelection(1)
        d.on_driver(None)
        self.assertTrue(d.loadingVoices)
        self.assertTrue(d.volume.IsEnabled())
        d.volume.SetFocus()
        self.pump(lambda: wx.Window.FindFocus() == d.volume)
        self.runners[-1].release.set()
        self.pump(lambda: not d.loadingVoices)
        self.assertEqual(wx.Window.FindFocus(), d.volume)

    def finish_probe(self):
        probe.ProbeChecks.finish_probe(self)

    def test_spin_and_typed_volume_changes_invalidate_verification(self):
        d = self.dialog
        for kind in (wx.EVT_SPINCTRL, wx.EVT_TEXT):
            with self.subTest(event=kind.typeId):
                self.finish_probe()
                self.assertNotIn('не проверена', d.probeStatus.GetValue())
                if kind == wx.EVT_TEXT:
                    d.volume.SetFocus()
                    d.volume.SetSelection(-1, -1)
                    # Send real character messages to the focused native edit.
                    import ctypes
                    user32 = ctypes.windll.user32
                    user32.GetFocus.restype = ctypes.c_void_p
                    user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
                    edit = user32.GetFocus()
                    for character in '63':
                        user32.SendMessageW(edit, 0x0102, ord(character), 0)  # WM_CHAR
                    self.pump()
                    self.assertEqual(d.volume.GetValue(), 63)
                else:
                    d.volume.SetValue(64)
                    event = wx.CommandEvent(kind.typeId, d.volume.GetId())
                    event.SetEventObject(d.volume)
                    d.volume.GetEventHandler().ProcessEvent(event)
                self.assertIn('не проверена', d.probeStatus.GetValue())

    def test_probe_result_must_match_requested_volume(self):
        d = self.dialog
        for selected, returned in ((42, 100), (42, None), (100, None)):
            with self.subTest(selected=selected, returned=returned):
                d.volume.SetValue(selected)
                d.on_probe(None)
                runner = self.runners[-1]
                self.pump(lambda: runner.started.is_set())
                runner.result = dict(type='compatibility', status='verified', driver='a',
                                     voice='one', rate=37, frames=100, sampleRate=22050, mp3Bytes=800)
                if returned is not None:
                    runner.result['volume'] = returned
                runner.release.set()
                self.pump(lambda: not d.running)
                self.assertIn('Ошибка проверки записи', d.probeStatus.GetValue())

    def test_zero_volume_probe_rejected_with_accessible_localized_message(self):
        d = self.dialog
        count = len(self.runners)
        d.volume.SetValue(0)
        d.on_probe(None)
        self.assertEqual(d.probeStatus.GetValue(), 'Для проверки голоса установите громкость выше 0.')
        self.assertEqual(len(self.runners), count)
        self.assertFalse(d.running)
        self.assertEqual(wx.Window.FindFocus(), d.volume)

    def test_russian_and_english_volume_labels_verification_and_errors(self):
        from bookAudio.i18n import _, set_language
        for language, label, unverified, verified, error in (
            ('ru', 'Громкость, от 0 до 100:',
             'Запись не проверена для выбранного драйвера, голоса, скорости и громкости.',
             'Запись проверена для выбранного драйвера, голоса, скорости и громкости.',
             'Для проверки голоса установите громкость выше 0.'),
            ('en', 'Volume, from 0 to 100:',
             'Recording not yet verified for the selected driver, voice, rate and volume.',
             'Recording verified for the selected driver, voice, rate and volume.',
             'Set the volume above 0 to verify the voice.'),
        ):
            with self.subTest(language=language):
                self.dialog.destroy_dialog()
                self.pump(lambda: not bool(self.dialog))
                set_language(language)
                d = self.dialog = probe.dialog_module.BookDialog(None, [('a', 'Driver A')], {'language': language})
                d.Show()
                self.runners[-1].release.set()
                self.pump(lambda: not d.loadingVoices)
                labels = [c.GetLabel() for c in d.GetChildren() if isinstance(c, wx.StaticText)]
                self.assertTrue(any(text.replace('&', '') == label and '&' in text for text in labels))
                self.assertEqual(d.probeStatus.GetValue(), unverified)
                self.finish_probe()
                self.assertEqual(d.probeStatus.GetValue(), verified)
                d.volume.SetValue(0)
                d.on_probe(None)
                self.assertEqual(d.probeStatus.GetValue(), error)
                if language == 'en':
                    self.assertEqual(_('Громкость должна быть целым числом от 0 до 100.'), 'Volume must be an integer from 0 to 100.')
                    self.assertEqual(_('Драйвер передал неполный аудиокадр.'), 'The driver provided an incomplete audio frame.')


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        host._host.cleanup()
