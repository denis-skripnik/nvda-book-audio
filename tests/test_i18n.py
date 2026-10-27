"""Localization contract; safe tests never start NVDA's GUI."""
import gettext
import importlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
sys.path.insert(0, str(ROOT / 'tools'))


class LocalizationTests(unittest.TestCase):
    def test_compiler_produces_standard_deterministic_gnu_catalog(self):
        self.assertTrue((ROOT / 'tools/compile_translations.py').is_file(), 'Compiler is missing')
        compiler = importlib.import_module('compile_translations')
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'en.json', Path(tmp) / 'en.mo'
            source.write_text(json.dumps({'Книга': 'Book', 'Ошибка {name}': 'Error {name}'}), encoding='utf-8')
            compiler.compile_catalog(source, target)
            data = target.read_bytes()
            self.assertEqual(struct.unpack_from('<7I', data)[:3], (0x950412de, 0, 3))
            catalog = gettext.GNUTranslations(io.BytesIO(data))
            self.assertEqual(catalog.gettext('Ошибка {name}').format(name='X'), 'Error X')
            compiler.compile_catalog(source, target)
            self.assertEqual(target.read_bytes(), data)

    def test_core_messages_and_named_status_placeholders(self):
        import i18n
        import documents
        import jobs
        i18n.set_language('en')
        self.addCleanup(i18n.set_language, 'ru')
        self.assertEqual(documents.split_chapters('text', '')[0][0], 'Book')
        with self.assertRaisesRegex(ValueError, 'Unsupported format'):
            documents.read_document('book.doc')
        events = []
        with self.assertRaisesRegex(ValueError, 'empty.txt.*no text'):
            jobs.convert({'files': ['empty.txt'], 'separator': ''}, lambda p: '', lambda *a: [], str,
                         None, None, lambda kind, **kw: events.append((kind, kw)))
        self.assertEqual(events[0][1]['message'], 'Reading file 1 of 1: empty.txt')

    def test_real_worker_bootstrap_error_uses_requested_english(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = Path(tmp) / 'request.json'
            request.write_text(json.dumps({'nvda': tmp, 'language': 'en_US'}), encoding='utf-8')
            result = subprocess.run([sys.executable, str(PLUGIN / 'worker.py'), str(request)],
                                    capture_output=True, timeout=15)
            event = json.loads(result.stdout.decode().splitlines()[-1])
            self.assertEqual(event['message'], 'Installed NVDA not found: library.zip is missing.')

    def test_all_core_russian_literals_are_catalogued_and_wrapped(self):
        import ast
        import re
        messages = json.loads((ROOT / 'addon/locale/en/LC_MESSAGES/nvda.json').read_text(encoding='utf-8'))
        for name in ('worker', 'documents', 'jobs', 'client', 'capture', 'encoder', 'dialog', '__init__'):
            tree = ast.parse((PLUGIN / (name + '.py')).read_text(encoding='utf-8'))
            parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or not re.search('[А-Яа-яЁё]', node.value):
                    continue
                # Source-language descriptive docstrings are not user messages.
                if isinstance(parents.get(node), ast.Expr):
                    continue
                parent = parents.get(node)
                self.assertTrue(isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == '_',
                                (name, node.lineno, node.value))
                self.assertIn(node.value, messages, (name, node.value))
                self.assertNotEqual(messages[node.value], node.value)

    def test_pdf_password_error_is_localized_without_text_based_control_flow(self):
        import documents
        import i18n
        from pypdf import PdfWriter
        i18n.set_language('en')
        self.addCleanup(i18n.set_language, 'ru')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'protected.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.encrypt('secret')
            writer.write(path)
            with self.assertRaisesRegex(ValueError, 'password-protected'):
                documents.read_document(path)
        import inspect
        self.assertNotIn('str(error)', inspect.getsource(documents._read_pdf),
                         'Exception routing must not depend on translated message text')

    def test_missing_catalog_is_visible_and_keeps_previous_language(self):
        import i18n
        i18n.set_language('ru')
        with tempfile.TemporaryDirectory() as tmp, patch.object(i18n, 'LOCALE_DIR', Path(tmp)):
            with self.assertRaises(FileNotFoundError):
                i18n.set_language('en')
        self.assertEqual(i18n._('Книга'), 'Книга')

    def test_autodetect_uses_nvda_language_without_changing_it(self):
        code = ('import sys, types; sys.path.insert(0, sys.argv[1]); '
                'sys.modules["languageHandler"] = types.SimpleNamespace(getLanguage=lambda: "en_US"); '
                'import i18n; print(i18n._("Книга"))')
        result = subprocess.run([sys.executable, '-c', code, str(PLUGIN)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), b'Book')

    def test_compiler_rejects_missing_or_invalid_translations(self):
        import compile_translations as compiler
        for messages in ({'Ошибка {name}': 'Error {wrong}'}, {'Книга': ''},
                         {'Книга': 42}, {'Книга': 'Book\u0000bad'}):
            with self.subTest(messages=messages), tempfile.TemporaryDirectory() as tmp:
                source, target = Path(tmp) / 'en.json', Path(tmp) / 'en.mo'
                source.write_text(json.dumps(messages), encoding='utf-8')
                with self.assertRaises(ValueError):
                    compiler.compile_catalog(source, target)
                self.assertFalse(target.exists())

    @unittest.skipUnless((PLUGIN / 'runtime/python.exe').exists() and Path('C:/Program Files/NVDA').exists(),
                         'Installed NVDA integration test')
    def test_real_worker_english_status_and_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'empty.txt'
            source.write_text('', encoding='utf-8')
            request = Path(tmp) / 'request.json'
            request.write_text(json.dumps({'language': 'en', 'nvda': 'C:/Program Files/NVDA',
                'config': tmp, 'driver': 'sapi5', 'action': 'convert', 'files': [str(source)],
                'separator': '', 'output': tmp, 'voice': '', 'rate': 50}), encoding='utf-8')
            result = subprocess.run([str(PLUGIN / 'runtime/python.exe'), str(PLUGIN / 'worker.py'), str(request)],
                                    capture_output=True, timeout=30)
            events = [json.loads(line) for line in result.stdout.decode().splitlines() if line.startswith('{')]
            self.assertEqual(events[0]['type'], 'status', result.stderr)
            self.assertEqual(events[0]['message'], 'Reading file 1 of 1: empty.txt')
            self.assertEqual(events[-1]['message'], 'The file "empty.txt" contains no text to convert to speech.')
            self.assertNotEqual(result.returncode, 0)

    def test_language_selection_and_live_imported_wrapper(self):
        self.assertTrue((PLUGIN / 'i18n.py').is_file(), 'Localization helper is missing')
        i18n = importlib.import_module('i18n')
        self.addCleanup(i18n.set_language, 'ru')
        translate = i18n._
        for language, expected in [('ru', 'Книга'), ('ru_RU', 'Книга'), ('en', 'Book'),
                                   ('en_US', 'Book'), ('de', 'Book')]:
            i18n.set_language(language)
            self.assertEqual(translate('Книга'), expected)


if __name__ == '__main__':
    unittest.main()
