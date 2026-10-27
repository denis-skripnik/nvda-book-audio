"""Book Audio NVDA global plug-in. GPL-2.0-or-later."""
import struct
import sys
import time

import addonHandler
import globalPluginHandler
import globalVars
import gui
import languageHandler
from scriptHandler import script
import synthDriverHandler
import wx

from .dialog import BookDialog
from .i18n import _


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dialog = None
        self.menuItem = None
        if globalVars.appArgs.secure:
            return
        self.tray = gui.mainFrame.sysTrayIcon
        self.menuItem = self.tray.toolsMenu.Append(wx.ID_ANY, _('Book Audio — текст в MP3…'))
        self.tray.Bind(wx.EVT_MENU, self.on_open, self.menuItem)

    @script(description=_('Открыть окно Book Audio'), category='Book Audio', gesture='kb:NVDA+windows+a')
    def script_openBookAudio(self, gesture):
        wx.CallAfter(self.on_open, None)

    def on_open(self, event):
        if globalVars.appArgs.secure:
            return
        if self.dialog and self.dialog.alive:
            self.dialog.Show()
            self.dialog.activate()
            return
        if sys.version_info[:2] != (3, 13) or struct.calcsize('P') != 8:
            gui.messageBox(_('Эта сборка рассчитана на NVDA с Python 3.13 x64 (проверена NVDA 2026.2). Нужна подходящая сборка дополнения.'), 'Book Audio', wx.OK | wx.ICON_ERROR)
            return
        current = synthDriverHandler.getSynth()
        context = {
            'nvda': globalVars.appDir,
            'addons': [addon.path for addon in addonHandler.getRunningAddons()],
            'driver': current.name if current else 'sapi5',
            'voice': getattr(current, 'voice', ''),
            'rate': int(getattr(current, 'rate', 50)),
            'language': languageHandler.getLanguage(),
        }
        drivers = [(name, label) for name, label in synthDriverHandler.getSynthList() if name != 'silence']
        gui.mainFrame.prePopup()
        try:
            previousWorkers = self.dialog.workerThreads if self.dialog is not None else {}
            self.dialog = BookDialog(gui.mainFrame, drivers, context)
            # A closed window may still have cancelled subprocess cleanup running.
            self.dialog.workerThreads.update({thread: runner for thread, runner in previousWorkers.items() if thread.is_alive()})
            self.dialog.Show()
            self.dialog.activate()
        finally:
            gui.mainFrame.postPopup()

    def terminate(self):
        if self.dialog is not None:
            workers = list(self.dialog.workerThreads.items())
            for thread, runner in workers:
                if thread.is_alive():
                    runner.cancel()
            if self.dialog.alive:
                self.dialog.destroy_dialog()
            # The worker does not wait for UI callbacks. Let its cancelled
            # subprocess and temporary log close before NVDA unloads/exits.
            deadline = time.monotonic() + 5
            for thread, runner in workers:
                thread.join(timeout=max(0, deadline - time.monotonic()))
        if self.menuItem:
            self.tray.Unbind(wx.EVT_MENU, handler=self.on_open, source=self.menuItem)
            self.tray.toolsMenu.Remove(self.menuItem)
            self.menuItem.Destroy()
            self.menuItem = None
        super().terminate()
