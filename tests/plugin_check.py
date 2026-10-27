import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
if not (PLUGIN / '__init__.py').exists():
    raise AssertionError('NVDA Tools menu plug-in is not implemented')
import worker
worker.bootstrap({'nvda': 'C:/Program Files/NVDA', 'config': str(ROOT / 'plugin-test-config'), 'addons': []})
import wx
import gui
app = wx.App(False)
class Tray(wx.EvtHandler):
    def __init__(self):
        super().__init__()
        self.toolsMenu = wx.Menu()
class Frame(wx.Frame):
    def __init__(self):
        super().__init__(None)
        self.sysTrayIcon = Tray()
        self.balance = 0
    def prePopup(self):
        self.balance += 1
    def postPopup(self):
        self.balance -= 1
frame = Frame()
gui.mainFrame = frame
sys.path.insert(0, str(PLUGIN.parent))
import bookAudio
plugin = bookAudio.GlobalPlugin()
assert frame.sysTrayIcon.toolsMenu.GetMenuItemCount() == 1
plugin.on_open(None)
assert plugin.dialog is not None
assert plugin.dialog.IsShown()
assert frame.balance == 0
first = plugin.dialog
plugin.on_open(None)
assert plugin.dialog is first
plugin.terminate()
import threading
assert not any(thread.name == 'bookAudio-client' and thread.is_alive() for thread in threading.enumerate()), 'Plug-in shutdown returned before worker cleanup completed'
assert frame.sysTrayIcon.toolsMenu.GetMenuItemCount() == 0
print('NVDA menu add/open/reopen/remove: PASS', flush=True)
app.Destroy()
