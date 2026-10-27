"""Native, keyboard-accessible Russian conversion dialog."""
from pathlib import Path
import threading

import wx
from gui.guiHelper import BoxSizerHelper

from .client import Cancelled, WorkerClient
from .i18n import _


class BookDialog(wx.Dialog):
    def __init__(self, parent, drivers, context, python=None):
        super().__init__(parent, title=_('Book Audio — текст в MP3'), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.context = dict(context)
        self.driverItems = list(drivers)
        self.python = python
        self.paths = []
        self.voiceItems = []
        self.loadingVoices = False
        self.running = False
        self.probing = False
        self.runner = None
        self.closePending = False
        self.workerThread = None
        self.workerThreads = {}
        self.voiceGeneration = 0
        self.alive = True
        outer = wx.BoxSizer(wx.VERTICAL)
        helper = BoxSizerHelper(self, sizer=outer)
        self.files = helper.addLabeledControl(_('Файлы в порядке обработки:'), wx.ListBox, size=(620, 115))
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.addButton = wx.Button(self, label=_('&Добавить файлы…'))
        self.removeButton = wx.Button(self, label=_('&Удалить выбранный'))
        row.Add(self.addButton, 0, wx.RIGHT, 8)
        row.Add(self.removeButton)
        outer.Add(row, 0, wx.TOP | wx.BOTTOM, 8)
        self.output = helper.addLabeledControl(_('Папка сохранения:'), wx.TextCtrl)
        self.browseButton = wx.Button(self, label=_('Выбрать &папку…'))
        outer.Add(self.browseButton, 0, wx.TOP | wx.BOTTOM, 8)
        self.separator = helper.addLabeledControl(_('Фраза разделения в начале строки (пусто — весь файл):'), wx.TextCtrl, value=_('Глава'))
        self.drivers = helper.addLabeledControl(_('Драйвер &синтезатора:'), wx.Choice, choices=[label for name, label in drivers])
        self.voice = helper.addLabeledControl(_('&Голос:'), wx.Choice)
        self.rate = helper.addLabeledControl(_('С&корость NVDA, от 0 до 100:'), wx.SpinCtrl, min=0, max=100, initial=int(context.get('rate', 50)))
        self.probeButton = wx.Button(self, label=_('Проверить запись'))
        outer.Add(self.probeButton, 0, wx.TOP, 8)
        self.probeStatus = helper.addLabeledControl(_('Проверка записи:'), wx.TextCtrl,
                                                   value=_('Запись не проверена для выбранного драйвера, голоса и скорости.'),
                                                   style=wx.TE_READONLY)
        self.progress = wx.Gauge(self, range=100)
        self.progress.SetName(_('Выполнено в текущем файле'))
        outer.Add(self.progress, 0, wx.EXPAND | wx.TOP, 8)
        self.status = helper.addLabeledControl(_('Состояние:'), wx.TextCtrl, value=_('Выберите файлы и папку.'), style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 85))
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.startButton = wx.Button(self, label=_('&Запуск'))
        self.cancelButton = wx.Button(self, label=_('&Остановить'))
        self.closeButton = wx.Button(self, wx.ID_CLOSE, label=_('&Закрыть'))
        for button in (self.startButton, self.cancelButton, self.closeButton):
            row.Add(button, 0, wx.RIGHT, 8)
        outer.Add(row, 0, wx.TOP, 10)
        border = wx.BoxSizer(wx.VERTICAL)
        border.Add(outer, 1, wx.ALL | wx.EXPAND, 12)
        self.SetSizerAndFit(border)
        self.SetMinSize(self.GetSize())
        self.addButton.Bind(wx.EVT_BUTTON, self.on_add)
        self.removeButton.Bind(wx.EVT_BUTTON, self.on_remove)
        self.browseButton.Bind(wx.EVT_BUTTON, self.on_browse)
        self.drivers.Bind(wx.EVT_CHOICE, self.on_driver)
        self.voice.Bind(wx.EVT_CHOICE, self.invalidate_probe)
        self.rate.Bind(wx.EVT_SPINCTRL, self.invalidate_probe)
        self.rate.Bind(wx.EVT_TEXT, self.invalidate_probe)
        self.startButton.Bind(wx.EVT_BUTTON, self.on_start)
        self.probeButton.Bind(wx.EVT_BUTTON, self.on_probe)
        self.cancelButton.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.closeButton.Bind(wx.EVT_BUTTON, self.on_close)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.cancelButton.Disable()
        selected = next((i for i, (name, _) in enumerate(drivers) if name == context.get('driver')), 0)
        self.probeButton.Disable()
        if drivers:
            self.drivers.SetSelection(selected)
            self.on_driver(None)
        else:
            self.status.SetValue(_('Доступные драйверы синтеза не найдены.'))
            self.startButton.Disable()
        wx.CallAfter(self.activate)

    def activate(self):
        if self.alive:
            self.Raise()
            (self.addButton if self.addButton.IsEnabled() else self.status).SetFocus()

    def on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def add_paths(self, paths):
        seen = {str(Path(p).resolve()).casefold() for p in self.paths}
        for path in paths:
            normalized = str(Path(path).resolve())
            if normalized.casefold() not in seen:
                self.paths.append(normalized)
                self.files.Append(normalized)
                seen.add(normalized.casefold())
        if self.paths:
            self.files.SetSelection(len(self.paths) - 1)

    def on_add(self, event):
        with wx.FileDialog(self, _('Добавить текстовые файлы'), wildcard=_('Книги FB2, FB2.ZIP, TXT, PDF (*.fb2;*.fb2.zip;*.txt;*.pdf)|*.fb2;*.fb2.zip;*.txt;*.pdf'), style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.add_paths(dialog.GetPaths())
        self.files.SetFocus()

    def on_remove(self, event):
        index = self.files.GetSelection()
        if index != wx.NOT_FOUND:
            del self.paths[index]
            self.files.Delete(index)
            if self.paths:
                self.files.SetSelection(min(index, len(self.paths) - 1))
        self.files.SetFocus()

    def on_browse(self, event):
        with wx.DirDialog(self, _('Куда сохранять аудиокниги?'), defaultPath=self.output.GetValue(), style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.output.SetValue(dialog.GetPath())
        self.output.SetFocus()

    def update_controls(self):
        busy = self.running or self.loadingVoices
        for control in (self.addButton, self.removeButton, self.files, self.output, self.browseButton, self.separator, self.drivers, self.rate):
            control.Enable(not self.running)
        self.voice.Enable(not busy and bool(self.voiceItems))
        self.startButton.Enable(not busy and bool(self.voiceItems))
        self.probeButton.Enable(not busy and bool(self.voiceItems))
        self.cancelButton.Enable(self.running)

    def run_background(self, request, finish, voiceGeneration=None):
        runner = self.runner = WorkerClient(python=self.python)
        def deliver(callback, args):
            if self.alive and self.runner is runner and (voiceGeneration is None or voiceGeneration == self.voiceGeneration):
                callback(*args)

        def post(callback, *args):
            if not self.alive:
                return
            try:
                wx.CallAfter(deliver, callback, args)
            except (RuntimeError, AttributeError):
                # NVDA may be shutting down and have already destroyed wx.App.
                return

        def task():
            result = None
            error = None
            try:
                result = runner.run(request, lambda event: post(self.handle_event, event))
            except Cancelled:
                error = (_('Проверка записи остановлена. Запись не проверена.') if request.get('action') == 'probe'
                         else _('Остановлено. Уже сохранённые MP3 оставлены в выбранной папке.'))
            except Exception as exception:
                error = str(exception)
            post(finish, result, error)
        self.workerThread = threading.Thread(target=task, daemon=True, name='bookAudio-client')
        self.workerThreads = {thread: client for thread, client in self.workerThreads.items() if thread.is_alive()}
        self.workerThreads[self.workerThread] = runner
        self.workerThread.start()

    def on_driver(self, event):
        index = self.drivers.GetSelection()
        if index == wx.NOT_FOUND or self.running or self.closePending:
            return
        self.invalidate_probe()
        self.voiceGeneration += 1
        if self.runner:
            self.runner.cancel()
        self.voiceItems = []
        self.voice.Clear()
        self.loadingVoices = True
        self.status.SetValue(_('Загрузка голосов выбранного синтезатора…'))
        self.update_controls()
        request = dict(self.context, action='voices', driver=self.driverItems[index][0])
        self.run_background(request, self.voices_finished, self.voiceGeneration)

    def voices_finished(self, result, error):
        if not self.alive:
            return
        self.loadingVoices = False
        self.runner = None
        if self.closePending:
            self.destroy_dialog()
            return
        if error:
            self.status.SetValue(_('Ошибка загрузки голосов: ') + error)
        else:
            self.voiceItems = result['voices']
            self.voice.Set([voice['name'] for voice in self.voiceItems])
            if self.voiceItems:
                index = next((i for i, voice in enumerate(self.voiceItems) if voice['id'] == self.context.get('voice')), 0)
                self.voice.SetSelection(index)
            self.status.SetValue(_('Голоса загружены. Выберите файлы, папку и нажмите «Запуск».') if self.voiceItems else _('У этого драйвера нет доступных голосов.'))
        self.update_controls()

    def handle_event(self, event):
        if not self.alive or self.closePending:
            return
        if event['type'] in ('status', 'chapter'):
            self.status.SetValue(event['message'])
        if event['type'] == 'chapter':
            self.progress.SetValue(int(100 * (event['chapter'] - 1) / max(1, event['chapters'])))

    def on_start(self, event):
        if self.running or self.loadingVoices:
            return
        if not self.paths:
            self.status.SetValue(_('Добавьте хотя бы один файл.'))
            self.addButton.SetFocus()
            return
        if not Path(self.output.GetValue()).is_dir() or not self.output.GetValue().strip():
            self.status.SetValue(_('Выберите существующую папку сохранения.'))
            self.output.SetFocus()
            return
        if self.voice.GetSelection() == wx.NOT_FOUND:
            self.status.SetValue(_('Выберите голос.'))
            self.voice.SetFocus()
            return
        request = dict(self.context, action='convert', files=list(self.paths), output=self.output.GetValue(),
                       separator=self.separator.GetValue(), driver=self.driverItems[self.drivers.GetSelection()][0],
                       voice=self.voiceItems[self.voice.GetSelection()]['id'], rate=self.rate.GetValue())
        self.running = True
        self.progress.SetValue(0)
        self.status.SetValue(_('Начинается создание аудиокниг…'))
        self.update_controls()
        self.cancelButton.SetFocus()
        self.run_background(request, self.conversion_finished)

    def conversion_finished(self, result, error):
        if not self.alive:
            return
        self.running = False
        self.runner = None
        if self.closePending:
            self.destroy_dialog()
            return
        self.status.SetValue(error if error else _('Готово. Создано MP3: {count}. Папка: {folder}').format(count=result['count'], folder=self.output.GetValue()))
        if not error:
            self.progress.SetValue(100)
        self.update_controls()
        self.status.SetFocus()
        # The focused read-only edit exposes completion/errors to NVDA without pop-ups.

    def on_probe(self, event):
        if self.running or self.loadingVoices or self.closePending:
            return
        index = self.voice.GetSelection()
        driver = self.drivers.GetSelection()
        if index == wx.NOT_FOUND or driver == wx.NOT_FOUND:
            return
        request = dict(self.context, action='probe', driver=self.driverItems[driver][0],
                       voice=self.voiceItems[index]['id'], rate=self.rate.GetValue())
        self.probeRequest = request
        self.probeCancelled = False
        self.running = self.probing = True
        self.probeStatus.SetValue(_('Проверка записи…'))
        self.update_controls()
        self.run_background(request, self.probe_finished)

    def invalidate_probe(self, event=None):
        if self.alive and not self.closePending:
            self.probeStatus.SetValue(_('Запись не проверена для выбранного драйвера, голоса и скорости.'))
        if event is not None:
            event.Skip()

    def probe_finished(self, result, error):
        if not self.alive:
            return
        self.running = self.probing = False
        self.runner = None
        if self.closePending:
            self.destroy_dialog()
            return
        if self.probeCancelled:
            error = _('Проверка записи остановлена. Запись не проверена.')
        if not error and not (
            isinstance(result, dict) and result.get('type') == 'compatibility'
            and result.get('status') == 'verified'
            and all(result.get(key) == self.probeRequest[key] for key in ('driver', 'voice', 'rate'))
            and all(type(result.get(key)) is int and result[key] > 0
                    for key in ('frames', 'sampleRate', 'mp3Bytes'))
        ):
            error = _('Процесс проверки не подтвердил запись выбранного голоса.')
        self.probeStatus.SetValue(_('Ошибка проверки записи: ') + error if error else
                                  _('Запись проверена для выбранного драйвера, голоса и скорости.'))
        self.update_controls()

    def on_cancel(self, event):
        if self.runner:
            if self.probing:
                self.probeCancelled = True
            self.cancelButton.Disable()
            self.status.SetValue(_('Остановка процесса синтеза…'))
            self.runner.cancel()

    def on_close(self, event):
        if self.runner:
            self.closePending = True
            self.status.SetValue(_('Остановка и закрытие…'))
            self.runner.cancel()
            if isinstance(event, wx.CloseEvent) and event.CanVeto():
                event.Veto()
            return
        self.destroy_dialog()

    def destroy_dialog(self):
        if self.alive:
            self.alive = False
            self.Destroy()
