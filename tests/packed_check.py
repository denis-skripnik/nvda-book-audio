"""Verify the final archive with NVDA's parser and execute its bundled worker."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
import worker
archive = ROOT / 'dist/bookAudio-0.1.2.nvda-addon'
with tempfile.TemporaryDirectory(prefix='bookAudio-packed-', dir=ROOT) as temp:
    temp = Path(temp)
    worker.bootstrap({'nvda': 'C:/Program Files/NVDA', 'config': str(temp / 'parser'), 'addons': []})
    import addonHandler
    bundle = addonHandler.AddonBundle(str(archive))
    assert bundle.manifest['name'] == 'bookAudio'
    assert bundle.manifest['version'] == '0.1.2'
    assert bundle.manifest.errors is None, bundle.manifest.errors
    unpacked = temp / 'unpacked'
    with zipfile.ZipFile(archive) as package:
        package.extractall(unpacked)
    target = unpacked / 'globalPlugins/bookAudio'
    txt = temp / 'packed.txt'
    txt.write_text('Глава 1\nПроверка пакета без изменения основной NVDA.', encoding='utf-8')
    fb2zip = temp / 'packed.fb2.zip'
    with zipfile.ZipFile(fb2zip, 'w', zipfile.ZIP_DEFLATED) as book:
        book.writestr('nested/book.fb2', '<FictionBook><body><section><title><p>Глава 1</p></title><p>Проверка архивной книги.</p></section></body></FictionBook>'.encode('utf-8'))
    addon_root = Path.home() / 'AppData/Roaming/nvda/addons'
    neural_addons = [str(path) for path in addon_root.glob('NeuralVoices*') if (path / 'manifest.ini').is_file()]
    cases = [('sapi5', txt, []), ('sapi5_32', txt, []), ('oneCore', txt, []), ('NeuralVoices', fb2zip, neural_addons)]
    import os
    fixture = os.environ.get('BOOK_AUDIO_NEWFON_FIXTURE')
    if fixture:
        staging = json.loads(Path(fixture).read_text(encoding='utf-8'))
        cases.append(('newfon', txt, [staging['stage']]))
    for driver, source, addons in cases:
        output = temp / ('output-' + driver)
        output.mkdir()
        payload = {'nvda': 'C:/Program Files/NVDA', 'config': str(temp / ('config-' + driver)), 'addons': addons,
                   'action': 'convert', 'driver': driver, 'voice': '', 'rate': 50,
                   'language': 'en' if driver == 'oneCore' else 'ru',
                   'files': [str(source)], 'output': str(output), 'separator': 'Глава'}
        request = temp / (driver + '.json')
        request.write_text(json.dumps(payload), encoding='utf-8')
        process = subprocess.run([str(target / 'runtime/python.exe'), str(target / 'worker.py'), str(request)], capture_output=True, timeout=90)
        assert process.returncode == 0, process.stdout.decode() + process.stderr.decode(errors='replace')
        events = [json.loads(line) for line in process.stdout.decode().splitlines() if line.startswith('{')]
        assert events[-1] == {'type': 'done', 'count': 1}, events
        if driver == 'oneCore':
            assert events[0]['message'].startswith('Reading file '), events
        mp3s = list(output.rglob('*.mp3'))
        assert len(mp3s) == 1 and mp3s[0].stat().st_size > 1000
        print(driver + ' + ' + source.suffix + ': extracted runtime MP3 PASS', flush=True)
        payload.update(action='probe', config=str(temp / ('probe-' + driver)))
        request.write_text(json.dumps(payload), encoding='utf-8')
        process = subprocess.run([str(target / 'runtime/python.exe'), str(target / 'worker.py'), str(request)], capture_output=True, timeout=90)
        assert process.returncode == 0, process.stdout.decode() + process.stderr.decode(errors='replace')
        events = [json.loads(line) for line in process.stdout.decode().splitlines() if line.startswith('{')]
        result = events[-1]
        assert result['type'] == 'compatibility' and result['status'] == 'verified', result
        assert all(result[key] > 0 for key in ('frames', 'sampleRate', 'mp3Bytes')), result
        print(driver + ': extracted runtime voice probe PASS', flush=True)
    print('NVDA AddonBundle manifest + all extracted-runtime checks: PASS', flush=True)
