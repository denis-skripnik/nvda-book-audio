"""Exercise Russian and English native controls and status messages."""
from pathlib import Path
import os
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
import worker
with tempfile.TemporaryDirectory(prefix='bookAudio-language-', dir=os.environ['TMPDIR']) as temp:
    worker.bootstrap({'nvda': os.environ.get('BOOK_AUDIO_TEST_NVDA', 'C:/Program Files/NVDA'), 'config': temp, 'addons': [], 'language': 'en'})
    import languageHandler
    languageHandler.setLanguage('en')
    import wx
    app = wx.App(False)
    pkg = types.ModuleType('bookAudio')
    pkg.__path__ = [str(PLUGIN)]
    sys.modules['bookAudio'] = pkg
    from bookAudio.dialog import BookDialog
    dialog = BookDialog(None, [], {'language': 'en'})
    try:
        assert dialog.GetTitle() == 'Book Audio — Text to MP3', 'English NVDA must select an English window title'
        assert dialog.startButton.GetLabel().replace('&', '') == 'Start'
        assert dialog.closeButton.GetLabel().replace('&', '') == 'Close'
        assert dialog.separator.GetValue() == 'Chapter'
        dialog.on_start(None)
        assert dialog.status.GetValue() == 'Add at least one file.'
        dialog.output.SetValue(temp)
        dialog.conversion_finished({'count': 2}, None)
        assert 'Done.' in dialog.status.GetValue() and '2' in dialog.status.GetValue()
        assert not any('\u0400' <= char <= '\u04ff' for control in dialog.GetChildren() for char in control.GetLabel()), 'Untranslated native GUI label'
    finally:
        dialog.destroy_dialog()
    from bookAudio.i18n import set_language
    set_language('ru')
    russian = BookDialog(None, [], {'language': 'ru'})
    try:
        assert russian.GetTitle() == 'Book Audio — текст в MP3'
        assert russian.startButton.GetLabel().replace('&', '') == 'Запуск'
        assert russian.separator.GetValue() == 'Глава'
        russian.on_start(None)
        assert russian.status.GetValue() == 'Добавьте хотя бы один файл.'
        russian.output.SetValue(temp)
        russian.conversion_finished({'count': 2}, None)
        assert 'Готово.' in russian.status.GetValue() and '2' in russian.status.GetValue()
        print('English/Russian native GUI, default separator, validation and completion: PASS', flush=True)
    finally:
        russian.destroy_dialog()
        app.Destroy()
