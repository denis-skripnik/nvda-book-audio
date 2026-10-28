from pathlib import Path
import subprocess
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

class BuildTests(unittest.TestCase):
    def test_gitignore_does_not_exclude_required_native_extensions(self):
        import fnmatch
        patterns = (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
        self.assertFalse(any(fnmatch.fnmatch('lameenc.cp313-win_amd64.pyd', pattern)
                             for pattern in patterns if pattern.startswith('*.')),
                         'Native .pyd extensions are required to build/run the add-on')

    def test_release_version(self):
        import runpy
        self.assertEqual(runpy.run_path(str(ROOT / 'build.py'))['VERSION'], '0.1.5')

    def test_addon_archive_layout_runtime_and_licenses(self):
        script = ROOT / 'build.py'
        self.assertTrue(script.exists(), 'Reproducible addon builder is not implemented')
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        addon = ROOT / 'dist/bookAudio-0.1.5.nvda-addon'
        with zipfile.ZipFile(addon) as archive:
            names = set(archive.namelist())
            required = {'manifest.ini', 'globalPlugins/bookAudio/__init__.py',
                        'globalPlugins/bookAudio/bridge_capture.py',
                        'globalPlugins/bookAudio/driver_dependencies.py',
                        'licenses/NVDA-copying.txt',
                        'globalPlugins/bookAudio/runtime/python.exe',
                        'globalPlugins/bookAudio/runtime/LICENSE.txt',
                        'doc/ru/readme.html', 'LICENSE.txt', 'THIRD_PARTY.md'}
            self.assertTrue(required <= names, required - names)
            self.assertFalse(any(n.startswith('addon/') or '__pycache__' in n or n.endswith(('.pyc', '.pyo')) for n in names))
            self.assertIsNone(archive.testzip())
            english_help = archive.read('doc/en/readme.html').decode('utf-8')
            russian_help = archive.read('doc/ru/readme.html').decode('utf-8')
            self.assertIn('<html lang="en">', english_help)
            self.assertIn('NVDA+Windows+A', english_help)
            self.assertIn('<html lang="ru">', russian_help)
            self.assertIn('locale/en/LC_MESSAGES/nvda.mo', names)
            self.assertIn('locale/ru/manifest.ini', names)
