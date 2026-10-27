import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'addon/globalPlugins/bookAudio'))

class JobTests(unittest.TestCase):
    def test_fb2_zip_output_name_strips_both_extensions(self):
        import zipfile
        documents_spec = importlib.util.spec_from_file_location(
            'documents', ROOT / 'addon/globalPlugins/bookAudio/documents.py')
        documents = importlib.util.module_from_spec(documents_spec)
        documents_spec.loader.exec_module(documents)
        jobs_spec = importlib.util.spec_from_file_location(
            'jobs', ROOT / 'addon/globalPlugins/bookAudio/jobs.py')
        jobs = importlib.util.module_from_spec(jobs_spec)
        jobs_spec.loader.exec_module(jobs)
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            source = Path(tmp) / 'my.book.FB2.ZIP'
            with zipfile.ZipFile(source, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('folder/book.fb2', '<FictionBook><body><p>Текст</p></body></FictionBook>')
            def render(text, wav):
                wav.write_text(text, encoding='utf-8')
            def encode(wav, target):
                target.write_bytes(wav.read_bytes())
            request = {'files': [str(source)], 'output': tmp, 'separator': '', 'config': tmp}
            for directory in ('my.book', 'my.book (2)'):
                self.assertEqual(jobs.convert(request, documents.read_document,
                    documents.split_chapters, documents.safe_name, render, encode,
                    lambda *args, **kwargs: None), 1)
                target = Path(tmp) / directory / '001 - Книга.mp3'
                self.assertEqual(target.read_text(encoding='utf-8'), 'Текст')

    def test_empty_book_is_error_not_success(self):
        file = ROOT / 'addon/globalPlugins/bookAudio/jobs.py'
        spec = importlib.util.spec_from_file_location('jobs', file)
        jobs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(jobs)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'текст'):
                jobs.convert({'files': ['empty.txt'], 'output': tmp, 'separator': '', 'config': tmp},
                             lambda path: '', lambda text, marker: [], str,
                             lambda *args: None, lambda *args: None, lambda *args, **kw: None)

    def test_queue_writes_one_mp3_per_chapter_without_overwrite(self):
        file = ROOT / 'addon/globalPlugins/bookAudio/jobs.py'
        self.assertTrue(file.is_file(), 'Conversion jobs are not implemented')
        spec = importlib.util.spec_from_file_location('jobs', file)
        jobs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(jobs)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'book.txt'
            source.write_text('preface\nГлава 1\none\nГлава 2\ntwo', encoding='utf-8')
            def render(text, wav):
                wav.write_text(text, encoding='utf-8')
            def encode(wav, mp3):
                mp3.write_text(wav.read_text(encoding='utf-8'), encoding='utf-8')
            events = []
            request = {'files': [str(source)], 'output': tmp, 'separator': 'Глава', 'config': tmp}
            def read(path):
                return Path(path).read_text(encoding='utf-8')
            def split(text, marker):
                return [('Вступление', 'preface'), ('Глава 1', 'one'), ('Глава 2', 'two')]
            def safe(text):
                return text
            count = jobs.convert(request, read, split, safe, render, encode, lambda kind, **kw: events.append((kind, kw)))
            self.assertEqual(count, 3)
            self.assertEqual(len(list((Path(tmp) / 'book').glob('*.mp3'))), 3)
            jobs.convert(request, read, split, safe, render, encode, lambda *a, **kw: None)
            self.assertEqual(len(list((Path(tmp) / 'book (2)').glob('*.mp3'))), 3)
