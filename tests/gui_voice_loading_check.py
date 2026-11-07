"""Real voice-choice population for each installed test driver, isolated from NVDA."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
import worker

with tempfile.TemporaryDirectory(prefix='bookAudio-voices-', dir=os.environ.get('TMPDIR')) as temp:
    folder = Path(temp)
    addon_root = Path.home() / 'AppData/Roaming/nvda/addons'
    addons = [str(p) for pattern in ('RHVoice*', 'NeuralVoices*') for p in addon_root.glob(pattern)
              if (p / 'manifest.ini').is_file()]
    context = dict(nvda=os.environ.get('BOOK_AUDIO_TEST_NVDA', 'C:/Program Files/NVDA'),
                   config=str(folder / 'host-config'), addons=addons, language='ru')
    worker.bootstrap(context)
    import buildVersion
    import wx
    app = wx.App(False)
    package = types.ModuleType('bookAudio')
    package.__path__ = [str(PLUGIN)]
    sys.modules['bookAudio'] = package
    from bookAudio.dialog import BookDialog
    from bookAudio.client import WorkerClient
    observations = []
    real_run = WorkerClient.run
    def observe_run(client, request, on_event):
        actual = dict(request)
        # Negative control for this harness, never used by production code.
        if os.environ.get('BOOK_AUDIO_TEST_WRONG_DRIVER') == '1':
            actual['driver'] = 'sapi5'
        result = real_run(client, actual, on_event)
        observations.append((actual, result))
        return result
    WorkerClient.run = observe_run
    drivers = [('espeak', 'eSpeak NG'), ('sapi5', 'SAPI5 x64'), ('sapi5_32', 'SAPI5 x86'),
               ('oneCore', 'OneCore'), ('RHVoice', 'RHVoice'), ('NeuralVoices', 'NeuralVoices')]
    dialog = BookDialog(None, drivers, context, preferences_dir=False)
    source = folder / 'sample.txt'
    source.write_text('Chapter 1\nVoice loading check.', encoding='utf-8')
    dialog.add_paths([str(source)])
    dialog.output.SetValue(str(folder / 'output'))
    dialog.Show()
    loop = wx.GUIEventLoop()
    activator = wx.EventLoopActivator(loop)
    results = []
    try:
        for index, (driver, label) in enumerate(drivers):
            if index:
                dialog.drivers.SetSelection(index)
                dialog.on_driver(None)
            deadline = time.monotonic() + float(os.environ.get('BOOK_AUDIO_TEST_VOICE_DEADLINE', '60'))
            while dialog.loadingVoices and time.monotonic() < deadline:
                while loop.Pending():
                    loop.Dispatch()
                app.ProcessPendingEvents()
                time.sleep(0.01)
            assert not dialog.loadingVoices, driver + ': voice loading timed out'
            assert len(observations) == index + 1, driver + ': missing worker completion'
            request, response = observations[-1]
            assert request['driver'] == driver, driver + ': wrong dispatched driver'
            assert response['type'] == 'voices', driver + ': wrong worker result'
            assert response['voices'] == dialog.voiceItems, driver + ': displayed voices differ from worker'
            labels = list(dialog.voice.GetStrings())
            assert labels and all(label.strip() for label in labels), driver + ': ' + dialog.status.GetValue()
            assert dialog.voice.IsEnabled(), driver
            assert dialog.startButton.IsEnabled(), driver + ': Start unavailable'
            record = dict(driver=driver, voiceCount=len(labels), voiceChoiceEnabled=True, startEnabled=True)
            results.append(record)
            print(json.dumps(record), flush=True)
    finally:
        dialog.on_close(None)
        threads = list(dialog.workerThreads.items())
        for thread, client in threads:
            client.cancel()
        deadline = time.monotonic() + 30
        while any(thread.is_alive() for thread, client in threads) and time.monotonic() < deadline:
            while loop.Pending():
                loop.Dispatch()
            app.ProcessPendingEvents()
            for thread, client in threads:
                thread.join(0.01)
        assert not any(thread.is_alive() for thread, client in threads), 'Voice worker cleanup timed out'
        while loop.Pending():
            loop.Dispatch()
        app.ProcessPendingEvents()
        if dialog.alive:
            dialog.destroy_dialog()
        WorkerClient.run = real_run
        del activator
    print(json.dumps(dict(passed=True, nvda=buildVersion.version, drivers=results)), flush=True)
