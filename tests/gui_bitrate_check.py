"""Native wx bitrate controls, request integrity and isolated worker checks."""
from pathlib import Path
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gui_probe_check as probe
from gui_probe_check import host, wx


class BitrateChecks(unittest.TestCase):
    setUpClass = classmethod(host.FocusChecks.setUpClass.__func__)
    tearDownClass = classmethod(host.FocusChecks.tearDownClass.__func__)
    setUp = probe.ProbeChecks.setUp
    tearDown = host.FocusChecks.tearDown
    pump = host.FocusChecks.pump

    def test_native_choices_default_label_and_tab_after_volume(self):
        d = self.dialog
        self.assertTrue(hasattr(d, 'bitrate'), 'Missing accessible MP3 bitrate choice')
        self.assertIsInstance(d.bitrate, wx.Choice)
        self.assertEqual(d.bitrate.GetStrings(), ['64', '96', '128', '160', '192'])
        self.assertEqual(d.bitrate.GetStringSelection(), '128')
        labels = [c.GetLabel().replace('&', '') for c in d.GetChildren() if isinstance(c, wx.StaticText)]
        self.assertIn('Битрейт MP3, кбит/с:', labels)
        self.assertGreater(d.bitrate.GetPosition().y, d.volume.GetPosition().y)
        d.volume.SetFocus()
        self.pump(lambda: wx.Window.FindFocus() == d.volume)
        d.volume.Navigate(wx.NavigationKeyEvent.IsForward)
        self.pump(lambda: wx.Window.FindFocus() == d.bitrate)
        d.bitrate.Navigate(wx.NavigationKeyEvent.IsBackward)
        self.pump(lambda: wx.Window.FindFocus() == d.volume)
    def test_probe_carries_integer_bitrate_and_disables_editing(self):
        d = self.dialog
        d.bitrate.SetStringSelection('96')
        d.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        self.assertEqual(runner.request.get('bitrate'), 96)
        self.assertIs(type(runner.request['bitrate']), int)
        self.assertFalse(d.bitrate.IsEnabled())
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertTrue(d.bitrate.IsEnabled())

    def test_conversion_carries_selected_bitrate_and_disables_editing(self):
        d = self.dialog
        d.add_paths([__file__])
        d.output.SetValue(os.environ['TMPDIR'])
        d.bitrate.SetStringSelection('192')
        d.on_start(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        self.assertEqual(runner.request.get('bitrate'), 192)
        self.assertFalse(d.bitrate.IsEnabled())
        runner.result = {'count': 1}
        runner.release.set()
        self.pump(lambda: not d.running)
        self.assertTrue(d.bitrate.IsEnabled())
    def finish_bitrate_probe(self, replacement=None):
        d = self.dialog
        d.on_probe(None)
        runner = self.runners[-1]
        self.pump(lambda: runner.started.is_set())
        runner.result = dict(type='compatibility', status='verified', driver='a', voice='one',
                             rate=37, volume=100, bitrate=128, frames=100, sampleRate=22050, mp3Bytes=800,
                             commaPauseMs=0, sentencePauseMs=0)
        if replacement:
            runner.result.update(replacement)
        runner.release.set()
        self.pump(lambda: not d.running)

    def test_choice_change_invalidates_successful_probe(self):
        d = self.dialog
        self.finish_bitrate_probe()
        self.assertNotIn('не проверена', d.probeStatus.GetValue())
        d.bitrate.SetStringSelection('96')
        event = wx.CommandEvent(wx.EVT_CHOICE.typeId, d.bitrate.GetId())
        event.SetEventObject(d.bitrate)
        d.bitrate.GetEventHandler().ProcessEvent(event)
        self.assertIn('не проверена', d.probeStatus.GetValue())

    def test_probe_rejects_mismatched_or_missing_bitrate(self):
        for value in (96, None, '128'):
            with self.subTest(value=value):
                self.finish_bitrate_probe({'bitrate': value})
                self.assertIn('Ошибка проверки записи', self.dialog.probeStatus.GetValue())

    def test_matching_probe_is_accepted(self):
        self.finish_bitrate_probe()
        self.assertNotIn('не проверена', self.dialog.probeStatus.GetValue())
        self.assertNotIn('Ошибка', self.dialog.probeStatus.GetValue())

    def test_bitrate_stays_enabled_during_voice_discovery_without_focus_steal(self):
        d = self.dialog
        d.drivers.SetSelection(1)
        d.on_driver(None)
        self.assertTrue(d.bitrate.IsEnabled())
        d.bitrate.SetFocus()
        self.pump(lambda: wx.Window.FindFocus() == d.bitrate)
        self.runners[-1].release.set()
        self.pump(lambda: not d.loadingVoices)
        self.assertEqual(wx.Window.FindFocus(), d.bitrate)
    def test_english_bitrate_label_and_validation_message(self):
        from bookAudio.i18n import _, set_language
        self.dialog.destroy_dialog()
        self.pump(lambda: not bool(self.dialog))
        set_language('en')
        d = self.dialog = probe.dialog_module.BookDialog(None, [('a', 'Driver A')], {'language': 'en'}, preferences_dir=False)
        d.Show()
        self.runners[-1].release.set()
        self.pump(lambda: not d.loadingVoices)
        labels = [c.GetLabel() for c in d.GetChildren() if isinstance(c, wx.StaticText)]
        self.assertIn('MP3 &bitrate, kbps:', labels)
        self.assertEqual(_('Битрейт MP3 должен быть целым числом: 64, 96, 128, 160 или 192 кбит/с.'),
                         'MP3 bitrate must be an integer: 64, 96, 128, 160 or 192 kbps.')

    def test_real_worker_probe_accepts_selected_96_bitrate(self):
        self.dialog.destroy_dialog()
        self.pump(lambda: not bool(self.dialog))
        self.patcher.stop()
        d = self.dialog = probe.dialog_module.BookDialog(None, [('espeak', 'eSpeak NG')],
            {'nvda': os.environ.get('BOOK_AUDIO_TEST_NVDA', 'C:/Program Files/NVDA'),
             'addons': [], 'language': 'ru', 'rate': 50}, preferences_dir=False)
        d.Show()
        self.pump(lambda: not d.loadingVoices)
        self.assertTrue(d.voiceItems, d.status.GetValue())
        d.bitrate.SetStringSelection('96')
        d.on_probe(None)
        self.pump(lambda: not d.running)
        self.assertNotIn('не проверена', d.probeStatus.GetValue())
        self.assertNotIn('Ошибка', d.probeStatus.GetValue())
        self.assertEqual(d.probeRequest['bitrate'], 96)


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        host._host.cleanup()
