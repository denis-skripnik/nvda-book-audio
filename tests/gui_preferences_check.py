"""Durable add-on preferences through real wx controls and isolated NVDA hosts."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gui_pauses_check as pauses
from gui_pauses_check import host, wx, dialog_module
from bookAudio.preferences import load_preferences, save_preferences


class PreferenceChecks(unittest.TestCase):
    setUpClass = classmethod(host.FocusChecks.setUpClass.__func__)
    tearDownClass = classmethod(host.FocusChecks.tearDownClass.__func__)
    pump = host.FocusChecks.pump
    loaded = pauses.PauseChecks.loaded
    select_driver = pauses.PauseChecks.select_driver

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.directory = Path(self.temp.name)
        self.runners = []
        def factory(**kwargs):
            runner = pauses.PauseRunner()
            self.runners.append(runner)
            return runner
        self.patcher = patch.object(dialog_module, 'WorkerClient', side_effect=factory)
        self.patcher.start()
        self.dialog = None

    def create(self, **kwargs):
        self.dialog = dialog_module.BookDialog(None, [('a', 'A'), ('b', 'B')],
            {'driver': 'a', 'voice': 'one', 'rate': 37}, preferences_dir=kwargs.get('preferences_dir', self.directory))
        self.dialog.Show()
        self.pump(lambda: self.runners[-1].started.is_set())
        return self.dialog

    def close(self):
        self.dialog.on_close(None)
        self.pump(lambda: not bool(self.dialog))

    def tearDown(self):
        for runner in self.runners:
            runner.release.set()
        self.pump(lambda: not any(t.is_alive() for t in getattr(self.dialog, 'workerThreads', {})))
        if self.dialog and self.dialog.alive:
            self.dialog.destroy_dialog()
            self.pump(lambda: not bool(self.dialog))
        self.patcher.stop()
        self.temp.cleanup()

    def test_all_settings_roundtrip_without_job_or_queue(self):
        d = self.create()
        self.loaded()
        self.select_driver(1)
        self.loaded({'voices': [{'id': 'two', 'name': 'Two'}], 'volume': 50, 'supportsPauses': True})
        d.output.SetValue(str(self.directory / 'Несуществующая папка 音'))
        d.separator.SetValue('')
        d.rate.SetValue(72)
        d.volume.SetValue(83)
        d.bitrate.SetStringSelection('192')
        d.commaPause.SetValue(123)
        d.sentencePause.SetValue(456)
        d.add_paths([__file__])
        self.close()
        saved = load_preferences(self.directory)
        self.assertEqual(saved, dict(output=str(self.directory / 'Несуществующая папка 音'), separator='',
            driver='b', voice='two', rate=72, volume=83, bitrate=192, commaPauseMs=123, sentencePauseMs=456))
        d = self.create()
        self.assertEqual(d.drivers.GetSelection(), 1)
        self.loaded({'voices': [{'id': 'one', 'name': 'One'}, {'id': 'two', 'name': 'Two'}], 'volume': 50, 'supportsPauses': True})
        self.assertEqual(d.voice.GetSelection(), 1)
        self.assertEqual((d.output.GetValue(), d.separator.GetValue(), d.rate.GetValue(), d.volume.GetValue(),
            d.bitrate.GetStringSelection(), d.commaPause.GetValue(), d.sentencePause.GetValue(), d.paths),
            (saved['output'], '', 72, 83, '192', 123, 456, []))

    def test_actual_nvda_config_directory_not_worker_context(self):
        from NVDAState import WritePaths
        d = self.create(preferences_dir=None)
        self.loaded()
        self.assertEqual(d.preferencesDir, WritePaths.configDir)
        self.assertNotEqual(str(d.preferencesDir), str(self.directory))
        d.output.SetValue('Native configuration directory')
        self.close()
        self.assertEqual(load_preferences(WritePaths.configDir)['output'], 'Native configuration directory')

    def test_raw_destruction_flushes_pending_fields(self):
        d = self.create()
        self.loaded()
        d.output.SetValue('Отложенная папка')
        d.separator.SetValue('')
        d.Destroy()
        self.pump(lambda: not bool(d))
        self.assertEqual(load_preferences(self.directory)['output'], 'Отложенная папка')
        self.assertEqual(load_preferences(self.directory)['separator'], '')

    def test_rapid_switch_does_not_save_loading_or_restore_wrong_driver(self):
        save_preferences(self.directory, dict(driver='a', voice='one', volume=81, commaPauseMs=123))
        d = self.create()
        self.loaded()
        obsolete = self.select_driver(1)
        current = self.select_driver(0)
        d.flush_preferences()
        self.assertEqual(load_preferences(self.directory)['driver'], 'a')
        self.assertEqual(load_preferences(self.directory)['voice'], 'one')
        obsolete.result = {'voices': [{'id': 'old', 'name': 'Old'}], 'volume': 2, 'supportsPauses': False}
        obsolete.release.set()
        self.pump(lambda: not any(t.is_alive() for t in d.workerThreads if t is not d.workerThread))
        self.assertTrue(d.loadingVoices)
        self.loaded({'voices': [{'id': 'one', 'name': 'One'}], 'volume': 50, 'supportsPauses': True})
        self.assertEqual(d.volume.GetValue(), 81)
        self.assertEqual(d.commaPause.GetValue(), 123)
        self.select_driver(1)
        self.loaded({'voices': [{'id': 'two', 'name': 'Two'}], 'volume': 50, 'supportsPauses': False})
        self.assertEqual(d.volume.GetValue(), 50)
        self.close()
        self.assertEqual((load_preferences(self.directory)['driver'], load_preferences(self.directory)['voice']), ('b', 'two'))

    def test_missing_voice_uses_current_context_before_first_voice(self):
        save_preferences(self.directory, dict(driver='a', voice='missing', volume=81))
        d = self.create()
        self.loaded({'voices': [{'id': 'other', 'name': 'Other'}, {'id': 'one', 'name': 'One'}], 'volume': 50})
        self.assertEqual(d.voice.GetSelection(), 1)
        self.assertEqual(d.volume.GetValue(), 81)

    def test_user_edit_loading_not_clobbered_and_unsupported_pauses_zero(self):
        save_preferences(self.directory, dict(driver='a', voice='one', volume=81, commaPauseMs=234, sentencePauseMs=567))
        d = self.create()
        d.volume.SetValue(63)
        event = wx.CommandEvent(wx.EVT_TEXT.typeId, d.volume.GetId())
        event.SetEventObject(d.volume)
        d.volume.GetEventHandler().ProcessEvent(event)
        self.loaded({'voices': [{'id': 'one', 'name': 'One'}], 'volume': 50, 'supportsPauses': False})
        self.assertEqual(d.volume.GetValue(), 63)
        self.assertEqual((d.commaPause.GetValue(), d.sentencePause.GetValue()), (0, 0))
        self.close()
        self.assertEqual(load_preferences(self.directory)['commaPauseMs'], 0)

    def test_unavailable_driver_native_volume_not_wrong_saved_volume(self):
        save_preferences(self.directory, dict(driver='absent', voice='missing', volume=81))
        d = self.create()
        self.loaded({'voices': [{'id': 'one', 'name': 'One'}], 'volume': 50})
        self.assertEqual(d.drivers.GetSelection(), 0)
        self.assertEqual(d.volume.GetValue(), 50)

    def test_explicit_false_never_reads_or_writes(self):
        with patch.object(dialog_module, 'load_preferences', side_effect=AssertionError('read')), patch.object(dialog_module, 'save_preferences', side_effect=AssertionError('write')):
            d = self.create(preferences_dir=False)
            self.loaded()
            d.output.SetValue('ignored')
            self.close()
        self.assertFalse((self.directory / 'bookAudio.json').exists())

    def test_native_completion_debounced_without_user_change(self):
        d = self.create()
        self.loaded({'voices': [{'id': 'one', 'name': 'One'}], 'volume': 50})
        self.pump(lambda: load_preferences(self.directory).get('voice') == 'one')
        self.assertEqual(load_preferences(self.directory)['volume'], 50)

    def test_save_failure_nonfatal_start_hide_shutdown_notifies_once(self):
        d = self.create()
        self.loaded()
        d.add_paths([__file__])
        d.output.SetValue(str(self.directory))
        with patch.object(dialog_module, 'save_preferences', return_value=False), self.assertLogs('bookAudio.dialog', level='WARNING') as logs:
            d.on_start(None)
            self.pump(lambda: self.runners[-1].started.is_set())
            self.assertTrue(d.running)
            d.on_close(None)
            self.assertTrue(d.alive)
            self.assertFalse(d.IsShown())
            self.runners[-1].result = {'count': 1}
            self.runners[-1].release.set()
            self.pump(lambda: not d.running)
            d.destroy_dialog()
            self.pump(lambda: not bool(d))
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn(str(self.directory), logs.output[0])


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        host._host.cleanup()
