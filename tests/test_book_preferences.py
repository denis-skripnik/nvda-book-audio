"""Strict storage validation for book-only options, without live profiles."""
import json
import subprocess
import sys
import unittest
import test_preferences as legacy
from test_preferences import fresh_store, PLUGIN


class BookPreferencesTests(unittest.TestCase):
    setUp = legacy.PreferencesTests.setUp
    def test_book_options_roundtrip_fresh_process(self):
        for mode in ('auto', 'structure', 'none'):
            for annotation in (True, False):
                settings = dict(splitMode=mode, includeAnnotation=annotation)
                self.assertTrue(fresh_store().save_preferences(self.root, settings))
                code = ('import json,sys;sys.path.insert(0,sys.argv[1]);'
                        'from preferences import load_preferences;'
                        'print(json.dumps(load_preferences(sys.argv[2])))')
                result = subprocess.run([sys.executable, '-I', '-c', code, str(PLUGIN), str(self.root)],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), settings)

    def test_invalid_book_options_filtered_on_save_and_load(self):
        for key, values in {'splitMode': ('phrase', 'AUTO', '', True, False, 1, None, [], {}),
                            'includeAnnotation': ('true', 'false', 1, 0, None, [], {})}.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    settings = {key: value, 'rate': 37}
                    self.assertTrue(fresh_store().save_preferences(self.root, settings))
                    self.assertEqual(fresh_store().load_preferences(self.root), {'rate': 37})
                    (self.root / 'bookAudio.json').write_text(json.dumps({'schemaVersion': 1, 'settings': settings}), encoding='utf-8')
                    self.assertEqual(fresh_store().load_preferences(self.root), {'rate': 37})

    def test_older_preferences_do_not_invent_new_fields(self):
        self.assertTrue(fresh_store().save_preferences(self.root, {'separator': 'Part'}))
        self.assertEqual(fresh_store().load_preferences(self.root), {})


if __name__ == '__main__':
    unittest.main()
