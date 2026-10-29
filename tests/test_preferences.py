"""Pure preference storage tests; temporary profiles never use live NVDA data."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/bookAudio'


def fresh_store():
    spec = importlib.util.spec_from_file_location('book_audio_preferences_test', PLUGIN / 'preferences.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='book-audio-preferences-', dir=os.environ['TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_missing_store_returns_empty_without_creating_files(self):
        store = fresh_store()
        self.assertEqual(store.load_preferences(self.root), {})
        self.assertEqual(list(self.root.iterdir()), [])

    def test_all_settings_survive_fresh_module_and_preserve_literal_strings(self):
        settings = dict(output='\\\\offline-server\\Книги\\не существует ', separator=' Глава\n',
                        driver='драйвер', voice='голос', rate=0, volume=100, bitrate=192,
                        commaPauseMs=0, sentencePauseMs=2000)
        self.assertTrue(fresh_store().save_preferences(self.root, settings))
        self.assertEqual(fresh_store().load_preferences(self.root), settings)
        document = json.loads((self.root / 'bookAudio.json').read_text(encoding='utf-8'))
        self.assertEqual(document, {'schemaVersion': 1, 'settings': settings})
        self.assertEqual([p.name for p in self.root.iterdir()], ['bookAudio.json'])

    def test_only_valid_whitelisted_values_are_saved_and_loaded(self):
        store = fresh_store()
        cases = {
            'output': ('', '  путь  ', None, 1, [], True),
            'separator': ('', '\nГлава\n', False, 3),
            'driver': ('', 'espeak', {}, 4),
            'voice': ('', 'ru', [], False),
            'rate': (0, 100, 50, -1, 101, True, False, 50.0, '50', None),
            'volume': (0, 100, 50, -1, 101, True, False, 50.0, '50', None),
            'bitrate': (64, 96, 128, 160, 192, 63, 256, True, 96.0, '96'),
            'commaPauseMs': (0, 2000, 250, -1, 2001, True, 1.0, '1'),
            'sentencePauseMs': (0, 2000, 250, -1, 2001, False, 1.0, '1'),
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    if key in ('output', 'separator', 'driver', 'voice'):
                        valid = type(value) is str
                    elif key == 'bitrate':
                        valid = type(value) is int and value in (64, 96, 128, 160, 192)
                    else:
                        valid = type(value) is int and 0 <= value <= (2000 if key.endswith('Ms') else 100)
                    expected = {key: value} if valid else {}
                    supplied = {key: value, 'queue': ['secret'], 'progress': 3, 'job': 'old', 'unknown': 1}
                    self.assertTrue(store.save_preferences(self.root, supplied))
                    self.assertEqual(json.loads((self.root / 'bookAudio.json').read_text(encoding='utf-8'))['settings'], expected)
                    (self.root / 'bookAudio.json').write_text(json.dumps({'schemaVersion': 1, 'settings': supplied}), encoding='utf-8')
                    self.assertEqual(store.load_preferences(self.root), expected)

    def test_corrupt_wrong_schema_and_oversized_documents_are_empty(self):
        store = fresh_store()
        payloads = [b'{', b'\xff', b'null', b'[]', b'1', b'"text"', b'{}',
                    b'{"settings":{"rate":25}}',
                    b'{"schemaVersion":2,"settings":{"rate":25}}',
                    b'{"schemaVersion":true,"settings":{"rate":25}}',
                    b'{"schemaVersion":1.0,"settings":{"rate":25}}',
                    b'{"schemaVersion":1,"settings":[]}',
                    b'{"schemaVersion":1,"settings":null}',
                    b'[' * 1500 + b']' * 1500,
                    json.dumps({'schemaVersion': 1, 'settings': {'output': 'x' * 65536}}).encode()]
        for payload in payloads:
            with self.subTest(payload=payload[:90]):
                (self.root / 'bookAudio.json').write_bytes(payload)
                self.assertEqual(store.load_preferences(self.root), {})
        with patch.object(Path, 'open', side_effect=PermissionError('private')):
            self.assertEqual(store.load_preferences(self.root), {})
        self.assertEqual(store.load_preferences(None), {})

    def test_atomic_replace_failure_preserves_previous_and_cleans_only_owned_partial(self):
        store = fresh_store()
        self.assertTrue(store.save_preferences(self.root, {'rate': 20}))
        before = (self.root / 'bookAudio.json').read_bytes()
        unrelated = self.root / 'bookAudio.someone-else.tmp'
        unrelated.write_bytes(b'leave alone')
        def fail_replace(source, target):
            self.assertEqual(Path(source).parent, self.root)
            self.assertNotEqual(Path(source), Path(target))
            self.assertEqual(Path(target), self.root / 'bookAudio.json')
            self.assertEqual(json.loads(Path(source).read_bytes())['settings'], {'rate': 30})
            raise PermissionError('private location')
        with patch('os.replace', side_effect=fail_replace) as replace:
            self.assertFalse(store.save_preferences(self.root, {'rate': 30}))
            replace.assert_called_once()
        self.assertEqual((self.root / 'bookAudio.json').read_bytes(), before)
        self.assertEqual(store.load_preferences(self.root), {'rate': 20})
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['bookAudio.json', unrelated.name])

    def test_oversized_encoded_save_fails_before_tempfile_and_preserves_previous(self):
        store = fresh_store()
        self.assertTrue(store.save_preferences(self.root, {'rate': 20}))
        before = (self.root / 'bookAudio.json').read_bytes()
        with patch.object(store.tempfile, 'NamedTemporaryFile', side_effect=AssertionError('must not open')):
            self.assertFalse(store.save_preferences(self.root, {'output': 'я' * 32768}))
        self.assertEqual((self.root / 'bookAudio.json').read_bytes(), before)
        self.assertEqual([p.name for p in self.root.iterdir()], ['bookAudio.json'])

    def test_failed_create_sync_and_invalid_path_return_false_without_changes(self):
        store = fresh_store()
        self.assertTrue(store.save_preferences(self.root, {'rate': 20}))
        before = (self.root / 'bookAudio.json').read_bytes()
        for target in ('tempfile.NamedTemporaryFile', 'os.fsync'):
            with self.subTest(target=target), patch(target, side_effect=OSError('private details')):
                self.assertFalse(store.save_preferences(self.root, {'rate': 30}))
            self.assertEqual((self.root / 'bookAudio.json').read_bytes(), before)
            self.assertEqual([p.name for p in self.root.iterdir()], ['bookAudio.json'])
        self.assertFalse(store.save_preferences(None, {}))
        self.assertFalse(store.save_preferences(self.root / 'missing', {}))
        self.assertFalse(store.save_preferences(self.root, {'output': '\ud800'}))
        self.assertEqual(store.load_preferences(self.root), {'rate': 20})

    def test_exact_size_boundary_and_mixed_validity(self):
        store = fresh_store()
        payload = json.dumps({'schemaVersion': 1, 'settings': {'rate': 0, 'volume': True, 'driver': 'x'}}).encode()
        (self.root / 'bookAudio.json').write_bytes(payload + b' ' * (65536 - len(payload)))
        self.assertEqual(store.load_preferences(self.root), {'rate': 0, 'driver': 'x'})
        (self.root / 'bookAudio.json').write_bytes(payload + b' ' * (65537 - len(payload)))
        self.assertEqual(store.load_preferences(self.root), {})
        empty_size = len(json.dumps({'schemaVersion': 1, 'settings': {'output': ''}}, ensure_ascii=False).encode())
        output = 'x' * (65536 - empty_size)
        self.assertTrue(store.save_preferences(self.root, {'output': output}))
        self.assertEqual((self.root / 'bookAudio.json').stat().st_size, 65536)
        self.assertEqual(store.load_preferences(self.root), {'output': output})
        self.assertFalse(store.save_preferences(self.root, {'output': output + 'x'}))
        self.assertEqual(store.load_preferences(self.root), {'output': output})

    def test_import_has_no_nvda_or_config_root_dependencies_or_io(self):
        import builtins
        original_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if name.split('.')[0] in ('config', 'NVDAState', 'globalVars'):
                raise AssertionError('NVDA dependency')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=guarded_import), \
                patch.object(Path, 'open', side_effect=AssertionError('import IO')), \
                patch.dict(os.environ, {}, clear=True):
            store = fresh_store()
        self.assertTrue(callable(store.load_preferences))
        self.assertTrue(callable(store.save_preferences))

    def test_saved_settings_survive_a_separate_python_process(self):
        import subprocess
        import sys
        settings = {'output': 'несуществующая папка', 'volume': 0, 'bitrate': 64}
        self.assertTrue(fresh_store().save_preferences(self.root, settings))
        code = ('import json,sys; sys.path.insert(0, sys.argv[1]); '
                'from preferences import load_preferences; '
                'print(json.dumps(load_preferences(sys.argv[2]), ensure_ascii=True))')
        result = subprocess.run([sys.executable, '-I', '-c', code, str(PLUGIN), str(self.root)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), settings)


if __name__ == '__main__':
    unittest.main()
