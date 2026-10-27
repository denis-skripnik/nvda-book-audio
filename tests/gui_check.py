"""Real wx acceptance test in a separate process; does not install into NVDA."""
import json
from pathlib import Path
import sys
import types
import time
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
if not (PLUGIN / 'dialog.py').exists():
    raise AssertionError('Accessible book dialog is not implemented')
import worker
test_temp = tempfile.TemporaryDirectory(prefix='gui-check-', dir=ROOT)
folder = Path(test_temp.name)
context = {'nvda': 'C:/Program Files/NVDA', 'config': str(folder / 'host-config'), 'addons': [], 'driver': 'sapi5', 'action': 'voices'}
worker.bootstrap(context)
import wx
app = wx.App(False)
pkg = types.ModuleType('bookAudio')
pkg.__path__ = [str(PLUGIN)]
sys.modules['bookAudio'] = pkg
from bookAudio.dialog import BookDialog
source = folder / 'sample.txt'
source.write_text('Вступление.\nГлава 1\nЭто первая глава.\nГлава 2\nЭто вторая глава.', encoding='utf-8')
dialog = BookDialog(None, [('sapi5', 'Microsoft SAPI 5'), ('espeak', 'eSpeak NG')], context)
dialog.Show()
dialog.add_paths([str(source), str(source)])
assert dialog.files.GetCount() == 1, 'Queue must deduplicate files'
dialog.output.SetValue(str(folder))
dialog.separator.SetValue('Глава')
started = [False]
start = time.monotonic()
result = {'passed': False}

def tick():
    if time.monotonic() - start > 90:
        result['error'] = 'GUI conversion timed out: ' + dialog.status.GetValue()
        dialog.on_close(None)
        app.ExitMainLoop()
        return
    if not dialog.loadingVoices and not started[0]:
        assert dialog.voice.GetCount() > 0, dialog.status.GetValue()
        assert dialog.startButton.IsEnabled()
        started[0] = True
        dialog.on_start(None)
    elif started[0] and not dialog.running:
        status = dialog.status.GetValue()
        result.update(passed='Готово' in status, status=status)
        result['mp3_count'] = len(list(folder.glob('sample*/*.mp3')))
        dialog.on_close(None)
        app.ExitMainLoop()
        return
    wx.CallLater(100, tick)
wx.CallLater(100, tick)
app.MainLoop()
print(json.dumps(result, ensure_ascii=True), flush=True)
assert result['passed'], result
assert result['mp3_count'] == 3, result
test_temp.cleanup()
