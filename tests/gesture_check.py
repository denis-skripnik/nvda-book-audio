"""Native NVDA gesture registration smoke test in an isolated wx host."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
import worker
with tempfile.TemporaryDirectory(prefix='bookAudio-gesture-', dir=ROOT) as temp:
    worker.bootstrap({'nvda': 'C:/Program Files/NVDA', 'config': temp, 'addons': []})
    import wx
    import gui
    import keyboardHandler
    app = wx.App(False)
    class Tray(wx.EvtHandler):
        def __init__(self):
            super().__init__()
            self.toolsMenu = wx.Menu()
    class Frame(wx.Frame):
        def __init__(self):
            super().__init__(None)
            self.sysTrayIcon = Tray()
        def prePopup(self):
            pass
        def postPopup(self):
            pass
    frame = Frame()
    gui.mainFrame = frame
    sys.path.insert(0, str(PLUGIN.parent))
    import bookAudio
    plugin = bookAudio.GlobalPlugin()
    try:
        modifiers = {keyboardHandler.getNVDAModifierKeys()[0], (0x5B, False)}
        gesture = keyboardHandler.KeyboardInputGesture(modifiers, 0x41, 0, False)
        bound = plugin.getScript(gesture)
        assert bound is not None and bound.__name__ == 'script_openBookAudio', 'Default NVDA+Windows+A is not registered'
        assert bound.__doc__, 'Input Gestures requires a script description'
        assert bound.category == 'Book Audio', 'Script must be discoverable under Book Audio'
        assert 'Book Audio' in plugin.menuItem.GetItemLabelText()
        bound(gesture)
        app.Yield()
        assert plugin.dialog is not None and plugin.dialog.IsShown(), 'Gesture did not open the window'
        first = plugin.dialog
        bound(gesture)
        app.Yield()
        assert plugin.dialog is first, 'Repeated gesture opened a duplicate window'
        # The exposed, documented script is bindable by NVDA's normal gesture APIs.
        plugin.bindGesture('kb:NVDA+windows+b', 'openBookAudio')
        reassigned = plugin.getScript(keyboardHandler.KeyboardInputGesture(modifiers, 0x42, 0, False))
        assert reassigned is not None and reassigned.__name__ == 'script_openBookAudio'
        print('NVDA+Windows+A binding, script metadata, open/reopen and rebinding: PASS', flush=True)
    finally:
        plugin.terminate()
        app.Destroy()
