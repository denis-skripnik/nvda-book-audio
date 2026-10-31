"""Native book options, isolated preferences and controlled worker requests."""
from pathlib import Path
import json
import os
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gui_preferences_check as prefs
from gui_preferences_check import host, wx, dialog_module
from bookAudio.preferences import save_preferences, load_preferences
from bookAudio.i18n import set_language, _


class BookOptionChecks(unittest.TestCase):
    setUpClass = classmethod(host.FocusChecks.setUpClass.__func__)
    tearDownClass = classmethod(host.FocusChecks.tearDownClass.__func__)
    pump = host.FocusChecks.pump
    loaded = prefs.PreferenceChecks.loaded
    create = prefs.PreferenceChecks.create
    close = prefs.PreferenceChecks.close
    tearDown = prefs.PreferenceChecks.tearDown

    def setUp(self):
        set_language('ru')
        prefs.PreferenceChecks.setUp(self)

    def change(self, index):
        d = self.dialog
        d.splitMode.SetSelection(index)
        event = wx.CommandEvent(wx.EVT_CHOICE.typeId, d.splitMode.GetId())
        event.SetEventObject(d.splitMode)
        d.splitMode.GetEventHandler().ProcessEvent(event)

    def test_native_defaults_labels_tab_and_mode_enabling(self):
        d = self.create()
        self.assertTrue(hasattr(d, 'splitMode'), 'Missing native book splitting choice')
        self.assertIsInstance(d.splitMode, wx.Choice)
        self.assertIsInstance(d.includeAnnotation, wx.CheckBox)
        self.assertFalse(hasattr(d, 'separator'), 'Prefix input must be removed')
        self.assertFalse(any(isinstance(c, wx.TextCtrl) and c.GetValue() == 'Глава' for c in d.GetChildren()))
        self.assertEqual(d.splitModeItems, ['auto', 'structure', 'none'])
        self.assertEqual(d.splitMode.GetSelection(), 0)
        self.assertTrue(d.includeAnnotation.GetValue())
        self.assertEqual(d.includeAnnotation.GetLabel(), 'Озвучивать аннотацию FB2, если она есть')
        self.assertIn('Разбиение на части:', [c.GetLabel() for c in d.GetChildren() if isinstance(c, wx.StaticText)])
        self.assertEqual(d.splitMode.GetStrings(), ['Авто', 'По структуре книги', 'Один файл на книгу'])
        self.assertIn('Авто: структура книги / доступные закладки, затем Глава/Часть/Chapter/Part + номер.', [c.GetLabel() for c in d.GetChildren() if isinstance(c, wx.StaticText)])
        self.loaded()
        d.browseButton.SetFocus()
        self.pump(lambda: wx.Window.FindFocus() == d.browseButton)
        d.browseButton.Navigate(wx.NavigationKeyEvent.IsForward)
        self.pump(lambda: wx.Window.FindFocus() == d.splitMode)
        d.splitMode.Navigate(wx.NavigationKeyEvent.IsForward)
        self.pump(lambda: wx.Window.FindFocus() == d.includeAnnotation)
        for index in (1, 2, 0):
            self.change(index)
            d.splitMode.SetFocus()
            d.splitMode.Navigate(wx.NavigationKeyEvent.IsForward)
            self.pump(lambda: wx.Window.FindFocus() == d.includeAnnotation)

    def test_saved_restart_restore_and_older_invalid_fallback(self):
        for saved, expected in [({'separator': 'Part'}, ('auto', True)),
                                ({'splitMode': 'phrase', 'separator': 'Custom'}, ('auto', True)),
                                ({'splitMode': 'bad', 'includeAnnotation': 'false'}, ('auto', True)),
                                ({'splitMode': True, 'includeAnnotation': 0}, ('auto', True)),
                                ({'splitMode': 'none', 'includeAnnotation': False}, ('none', False))]:
            (self.directory / 'bookAudio.json').write_text(json.dumps({'schemaVersion': 1, 'settings': saved}), encoding='utf-8')
            d = self.create()
            self.loaded()
            self.assertEqual((d.splitModeItems[d.splitMode.GetSelection()], d.includeAnnotation.GetValue()), expected)
            self.close()
            self.assertNotIn('separator', json.loads((self.directory / 'bookAudio.json').read_text(encoding='utf-8'))['settings'])
        d = self.create()
        self.loaded()
        self.change(2)
        d.includeAnnotation.SetValue(False)

        self.close()
        d = self.create()
        self.loaded()
        self.assertEqual(d.splitMode.GetSelection(), 2)
        self.assertFalse(d.includeAnnotation.GetValue())
        self.assertNotIn('separator', load_preferences(self.directory))

    def test_book_options_requests_busy_and_probe_not_invalidated(self):
        d = self.create()
        self.loaded()
        d.on_probe(None)
        self.pump(lambda: self.runners[-1].started.is_set())
        request = self.runners[-1].request
        self.assertNotIn('splitMode', request)
        self.assertNotIn('includeAnnotation', request)
        self.assertFalse(d.splitMode.IsEnabled())
        self.assertFalse(d.includeAnnotation.IsEnabled())
        self.runners[-1].release.set()
        self.pump(lambda: not d.running)
        status = d.probeStatus.GetValue()
        self.change(2)
        d.includeAnnotation.SetValue(False)
        event = wx.CommandEvent(wx.EVT_CHECKBOX.typeId, d.includeAnnotation.GetId())
        event.SetEventObject(d.includeAnnotation)
        d.includeAnnotation.GetEventHandler().ProcessEvent(event)
        self.assertEqual(d.probeStatus.GetValue(), status)
        d.output.SetValue(str(self.directory))
        d.add_paths([__file__])
        d.on_start(None)
        self.pump(lambda: self.runners[-1].started.is_set())
        self.assertEqual(self.runners[-1].request['splitMode'], 'none')
        self.assertEqual(self.runners[-1].request.get('separator', ''), '')
        self.assertIs(self.runners[-1].request['includeAnnotation'], False)
        self.assertFalse(d.splitMode.IsEnabled())
        self.assertFalse(d.includeAnnotation.IsEnabled())
        self.runners[-1].result = {'count': 1}
        self.runners[-1].release.set()
        self.pump(lambda: not d.running)
        self.assertTrue(d.splitMode.IsEnabled())
        self.assertTrue(d.includeAnnotation.IsEnabled())


    def test_loading_keeps_book_options_enabled_without_focus_steal(self):
        d = self.create()
        self.assertTrue(d.splitMode.IsEnabled())
        self.assertTrue(d.includeAnnotation.IsEnabled())
        d.includeAnnotation.SetFocus()
        self.pump(lambda: wx.Window.FindFocus() == d.includeAnnotation)
        self.loaded()
        self.assertEqual(wx.Window.FindFocus(), d.includeAnnotation)

    def test_english_options_and_annotation_catalog(self):
        set_language('en')
        d = self.create()
        self.loaded()
        self.assertEqual(d.splitMode.GetStrings(), ['Auto', 'By book structure', 'One file per book'])
        self.assertEqual(d.splitModeItems, ['auto', 'structure', 'none'])
        self.assertIn('Auto: book structure / available bookmarks, then Глава/Часть/Chapter/Part + number.', [c.GetLabel() for c in d.GetChildren() if isinstance(c, wx.StaticText)])
        self.assertEqual(d.includeAnnotation.GetLabel(), 'Read the FB2 annotation, if present')
        self.assertIn('Split into parts:', [c.GetLabel() for c in d.GetChildren() if isinstance(c, wx.StaticText)])
        self.assertEqual(_('Аннотация'), 'Annotation')


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        host._host.cleanup()
