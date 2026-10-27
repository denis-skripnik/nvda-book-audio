"""Build a deterministic NVDA add-on from the local, vendored tree."""
import hashlib
import html
from pathlib import Path
import re
import zipfile
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
ADDON = ROOT / 'addon'
VERSION = '0.1.2'


def html_document(markdown, language='ru'):
    def inline(text):
        text = html.escape(text)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    lines = [f'<!doctype html><html lang="{html.escape(language)}"><meta charset="utf-8"><title>Book Audio</title><body>']
    for line in markdown.splitlines():
        if line.startswith('# '):
            lines.append('<h1>' + inline(line[2:]) + '</h1>')
        elif line.startswith('## '):
            lines.append('<h2>' + inline(line[3:]) + '</h2>')
        elif line.strip():
            lines.append('<p>' + inline(line) + '</p>')
    return '\n'.join(lines + ['</body></html>']).encode('utf-8')


def add(archive, name, data):
    info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data, compresslevel=9)


def build():
    subprocess.run([sys.executable, str(ROOT / 'tools/compile_translations.py')], check=True)
    destination = ROOT / f'dist/bookAudio-{VERSION}.nvda-addon'
    destination.parent.mkdir(exist_ok=True)
    required = ['manifest.ini', 'globalPlugins/bookAudio/__init__.py',
                'globalPlugins/bookAudio/runtime/python.exe', 'globalPlugins/bookAudio/runtime/python313.zip',
                'globalPlugins/bookAudio/vendor/lameenc.cp313-win_amd64.pyd', 'LICENSE.txt', 'THIRD_PARTY.md']
    for file in required:
        if not (ADDON / file).is_file():
            raise FileNotFoundError('Missing build input: ' + file)
    with zipfile.ZipFile(destination, 'w') as archive:
        for file in sorted(ADDON.rglob('*')):
            if not file.is_file() or '__pycache__' in file.parts or file.suffix in ('.pyc', '.pyo'):
                continue
            name = file.relative_to(ADDON).as_posix()
            data = file.read_bytes()
            if file.suffix == '.py':
                compile(data, name, 'exec')
            add(archive, name, data)
        add(archive, 'doc/ru/readme.html', html_document((ROOT / 'README.ru.md').read_text(encoding='utf-8')))
        add(archive, 'doc/en/readme.html', html_document((ROOT / 'README.md').read_text(encoding='utf-8'), 'en'))
        for file in sorted((ROOT / 'third_party_sources').glob('*')):
            if file.is_file():
                add(archive, 'licenses/sources/' + file.name, file.read_bytes())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip():
            raise RuntimeError('ZIP verification failed')
    print(str(destination))
    print(f'{destination.stat().st_size} bytes; SHA256 {hashlib.sha256(destination.read_bytes()).hexdigest()}')
    return destination


if __name__ == '__main__':
    build()
