"""Private synthesis host. Never starts NVDA core or changes the user's profile."""
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

if __package__:
    from .i18n import _
else:
    from i18n import _


def emit(kind, **values):
    print(json.dumps(dict(type=kind, **values), ensure_ascii=True), flush=True)


def preload_nvda_resources(nvda):
    """Resolve frozen NVDA data relative to NVDA, not the private interpreter."""
    import importlib
    import importlib.util
    if importlib.util.find_spec('pyphen') is None:
        return
    # NVDA 2026.3's frozen Pyphen computes its dictionaries directory from
    # sys.executable at import time. Preload it before NVDAHelper imports
    # braille/textUtils, then restore our real executable for subprocesses.
    executable = sys.executable
    try:
        sys.executable = str(Path(nvda) / 'nvda.exe')
        importlib.import_module('pyphen')
    finally:
        sys.executable = executable


def bootstrap(request):
    # Select our catalog before validation; NVDA imports follow path bootstrap.
    import i18n
    i18n.set_language(request.get('language', 'ru'))
    nvda = Path(request['nvda']).resolve()
    if not (nvda / 'library.zip').is_file():
        raise RuntimeError(_('Не найдена установленная NVDA: library.zip отсутствует.'))
    # Prefer the full embedded stdlib: NVDA's trimmed xml package lacks xml.dom.
    # Put NVDA libraries after the worker stdlib, not before it.
    sys.path.insert(0, str(HERE / 'vendor'))
    sys.path.extend([str(nvda), str(nvda / 'library.zip')])
    # NVDA distributes its native extensions beside library.zip.
    dllHandle = os.add_dll_directory(str(nvda))
    os.chdir(nvda)
    sys.frozen = True
    import monkeyPatches
    monkeyPatches.applyMonkeyPatches()
    import globalVars
    from argsParsing import getParser
    globalVars.appArgs, globalVars.unknownAppArgs = getParser().parse_known_args([])
    globalVars.appDir = str(nvda)
    globalVars.appArgs.configPath = request['config']
    globalVars.appArgs.secure = False
    globalVars.appArgs.disableAddons = True
    globalVars.appArgs.minimal = True
    globalVars.appArgs.launcher = False
    from NVDAState import WritePaths
    WritePaths.configDir = request['config']
    import config
    config.initConfigPath()
    config.initialize()
    import languageHandler
    languageHandler.setLanguage(request.get('language', 'ru'))
    # Installed NVDA relocates this resource outside library.zip.
    import certifi
    certifi.where = lambda: str(nvda / 'cacert.pem')
    preload_nvda_resources(nvda)
    import NVDAHelper
    # OneCore's native helper logs during initialization. Its callback is
    # normally installed by NVDAHelper.initialize(), which also starts remote
    # injection and must not run in this private host. Install logging only.
    NVDAHelper._setDllFuncPointer(
        NVDAHelper.localLib.dll, '_nvdaControllerInternal_logMessage',
        NVDAHelper.nvdaControllerInternal_logMessage,
    )
    import speech
    import synthDriverHandler
    import addonHandler
    import synthDrivers
    addons = []
    for path in request.get('addons', []):
        addon = addonHandler.Addon(path)
        addons.append(addon)
        addonHandler._availableAddons[addon.path] = addon
        extension = Path(path) / 'synthDrivers'
        if extension.is_dir():
            synthDrivers.__path__.insert(0, str(extension))
    # Only the enabled add-ons explicitly passed by the parent are exposed.
    # No global plug-in, install task, keyboard hook, or user config is executed.
    addonHandler.getRunningAddons = lambda: iter(addons)
    # Translation uses getCodeAddon(), which checks source roots before the
    # registry. Drivers remain in their original enabled add-on directories,
    # while the writable configuration deliberately lives elsewhere.
    addon_roots = list(dict.fromkeys(str(Path(addon.path).parent) for addon in addons))
    addonHandler._getDefaultAddonPaths = lambda: list(addon_roots)
    return synthDriverHandler, dllHandle


def render(driver, handler, text, voice, rate):
    import threading
    import time
    import comtypes.client
    import queueHandler
    done = threading.Event()

    def on_done(synth=None, **kwargs):
        if synth is driver:
            done.set()

    if handler.synthDoneSpeaking not in driver.supportedNotifications:
        raise RuntimeError(_('Драйвер не сообщает о завершении речи и не поддерживается.'))
    if voice:
        driver.voice = voice
    driver.rate = int(rate)
    if hasattr(driver, 'volume'):
        # Keep synthesis at its original level; drivers may implement volume
        # only through playback-device APIs. Export gain belongs in WaveSink.
        driver.volume = 100
    handler.synthDoneSpeaking.register(on_done)
    try:
        # Bounded requests prevent synthesizer XML/engine limits on whole books.
        import textwrap
        for chunk in textwrap.wrap(text, width=2000, replace_whitespace=False):
            emit('heartbeat')
            done.clear()
            driver.speak([chunk])
            deadline = time.monotonic() + 180
            while not done.wait(0.01):
                comtypes.client.PumpEvents(0.01)
                import wx
                wx.YieldIfNeeded()
                queueHandler.pumpAll()
                if time.monotonic() > deadline:
                    raise TimeoutError(_('Синтезатор не завершил фрагмент за 3 минуты.'))
    finally:
        handler.synthDoneSpeaking.unregister(on_done)


def verify_voice_recording(driver, handler, request, sink):
    """Check the selected settings with actual, private PCM and MP3 output."""
    if request.get('volume', 100) == 0:
        raise ValueError(_('Для проверки голоса установите громкость выше 0.'))
    import wave
    from encoder import encode_wav
    wav = Path(request['config']) / 'voice-check.wav'
    mp3 = wav.with_suffix('.mp3')
    sink.path = str(wav)
    render(driver, handler, _('Проверка записи голоса.'), request.get('voice'), request['rate'])
    sink.close()
    if sink.error:
        raise RuntimeError(sink.error)
    if sink.frames == 0:
        raise RuntimeError(_('Драйвер не передал PCM-аудио. Выберите другой синтезатор.'))
    with wave.open(str(wav)) as audio:
        sample_rate = audio.getframerate()
        non_silent = False
        while block := audio.readframes(8192):
            if audio.getsampwidth() == 1:
                non_silent |= any(value != 128 for value in block)
            else:
                non_silent |= any(block)
            if non_silent:
                break
    if not non_silent:
        raise RuntimeError(_('Синтезатор передал только тишину. Выберите другой голос.'))
    encode_wav(wav, mp3)
    mp3_bytes = mp3.stat().st_size
    if mp3_bytes == 0:
        raise RuntimeError(_('Не удалось создать MP3 при проверке записи.'))
    return dict(
        status='verified', driver=request['driver'], voice=driver.voice,
        rate=int(request['rate']), effectiveRate=int(driver.rate), volume=request.get('volume', 100),
        frames=sink.frames, sampleRate=sample_rate,
        mp3Bytes=mp3_bytes,
    )


def main(request):
    handler, dllHandle = bootstrap(request)
    import wx
    app = wx.App(False)
    import nvwave
    from capture import WaveSink, make_player
    sink = WaveSink(Path(request['config']) / 'unused.wav', volume=request.get('volume', 100))
    nvwave.WavePlayer = make_player(sink)
    import speechDictHandler
    speechDictHandler.initialize()
    from bridge_capture import BridgeCapture
    bridge = BridgeCapture()
    driver = None
    try:
        from driver_dependencies import prepare_driver_dependencies
        import addonHandler
        prepare_driver_dependencies(request['driver'], list(addonHandler.getRunningAddons()))
        driver = handler.getSynthInstance(request['driver'])
        if request['action'] == 'voices':
            voices = [{'id': key, 'name': value.displayName} for key, value in driver.availableVoices.items()]
            emit('voices', voices=voices, rate=int(driver.rate))
        elif request['action'] == 'probe':
            emit('compatibility', **verify_voice_recording(driver, handler, request, sink))
        elif request['action'] == 'render':
            sink.path = request['wav']
            render(driver, handler, request['text'], request.get('voice'), request['rate'])
            sink.close()
            if sink.error:
                raise RuntimeError(sink.error)
            if sink.frames == 0:
                raise RuntimeError(_('Драйвер не передал PCM-аудио. Запись этого синтезатора не поддерживается.'))
            if request.get('mp3'):
                from encoder import encode_wav
                encode_wav(request['wav'], request['mp3'])
            emit('rendered', frames=sink.frames, wav=request['wav'])
        elif request['action'] == 'convert':
            from documents import read_document, split_chapters, safe_name
            from jobs import convert
            from encoder import encode_wav

            def render_chapter(text, wav):
                sink.close()
                sink.path = str(wav)
                sink.frames = 0
                sink.error = None
                render(driver, handler, text, request['voice'], request['rate'])
                sink.close()
                if sink.error:
                    raise RuntimeError(sink.error)
                if sink.frames == 0:
                    raise RuntimeError(_('Драйвер не передал PCM-аудио. Выберите другой синтезатор.'))
            count = convert(request, read_document, split_chapters, safe_name, render_chapter, encode_wav, emit)
            emit('done', count=count)
        else:
            raise ValueError(_('Неизвестное действие.'))
    finally:
        try:
            if driver is not None:
                try:
                    driver.cancel()
                finally:
                    driver.terminate()
        finally:
            try:
                # Kill/close hosts before dropping proxies: their finalizers
                # otherwise race with native stop callbacks over closing RPC.
                bridge.close()
                # initSettings() installs a private settings ring retaining
                # the driver. Release it while NVDA's config is still alive.
                import globalVars
                globalVars.settingsRing = None
                driver = None
                import gc
                gc.collect()
            finally:
                sink.close()


if __name__ == '__main__':
    try:
        request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        main(request)
    except Exception as error:
        emit('error', message=str(error), details=traceback.format_exc())
        sys.exit(1)
