"""Real worker structural FB2 splitting, annotation and safe mode selection."""
from pathlib import Path
from io import BytesIO
import shutil
import subprocess
import tempfile
import unittest
import zipfile
import sys
import test_runtime as runtime
sys.path.insert(0, str(runtime.PLUGIN))
from client import WorkerClient

FB2 = '''<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
<description><title-info><book-title>Глава поселения</book-title>
<annotation><p>Это аннотация книги, она должна озвучиваться.</p></annotation></title-info></description>
<body><section><title><p>Открытие</p></title><p>Первая настоящая часть.</p>
<p>Глава поселения встретил гостей.</p></section>
<section><title><p>Встреча</p></title><p>Вторая настоящая часть.</p>
<p>Глава поселения проводил гостей.</p></section></body></FictionBook>'''


@unittest.skipUnless(runtime.NVDA.exists() and runtime.PYTHON.exists(), 'Installed NVDA integration')
class BookRuntimeTests(unittest.TestCase):
    def convert(self, root, zipped=False, **options):
        source = root / ('book.fb2.zip' if zipped else 'book.fb2')
        if zipped:
            with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('nested/book.fb2', FB2.encode('utf-8'))
        else:
            source.write_text(FB2, encoding='utf-8')
        events = []
        request = dict(nvda=str(runtime.NVDA), addons=[], driver='espeak', action='convert', voice='',
                       rate=50, language='ru', files=[str(source)], output=str(root), separator='Глава')
        request.update(options)
        result = WorkerClient().run(request, events.append)
        return result, events, sorted(root.rglob('*.mp3'))

    def test_pdf_bookmarks_take_priority_over_numbered_body_lines(self):
        sys.path.insert(0, str(runtime.PLUGIN / 'vendor'))
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writer = PdfWriter()
            for text in ('Chapter 99', 'Part 78'):
                page = writer.add_blank_page(width=300, height=300)
                font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                    NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
                page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
                    DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
                stream = DecodedStreamObject()
                stream.set_data(('BT /F1 12 Tf 30 250 Td (' + text + ') Tj ET').encode('ascii'))
                page[NameObject('/Contents')] = writer._add_object(stream)
            writer.add_outline_item('Opening', 0)
            writer.add_outline_item('Meeting', 1)
            source = root / 'bookmarks.pdf'
            with source.open('wb') as output:
                writer.write(output)
            result = WorkerClient().run(dict(nvda=str(runtime.NVDA), addons=[], driver='espeak', action='convert',
                voice='', rate=50, language='en', files=[str(source)], output=tmp), lambda event: None)
            self.assertEqual(result, {'type': 'done', 'count': 2})
            self.assertEqual([p.name.split(' - ', 1)[1] for p in sorted(root.rglob('*.mp3'))],
                             ['Opening.mp3', 'Meeting.mp3'])

    def test_automatic_request_needs_no_separator_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'book.fb2'
            source.write_text(FB2, encoding='utf-8')
            result = WorkerClient().run(dict(nvda=str(runtime.NVDA), addons=[], driver='espeak', action='convert',
                voice='', rate=50, language='ru', files=[str(source)], output=tmp), lambda event: None)
            self.assertEqual(result, {'type': 'done', 'count': 3})

    def test_annotation_can_be_disabled_and_whole_book_mode_is_one_file(self):
        for mode, annotation, count in [('auto', False, 2), ('none', True, 1), ('none', False, 1), ('phrase', False, 3)]:
            with self.subTest(mode=mode, annotation=annotation), tempfile.TemporaryDirectory() as tmp:
                result, events, files = self.convert(Path(tmp), splitMode=mode, includeAnnotation=annotation)
                self.assertEqual(result, {'type': 'done', 'count': count})
                self.assertEqual(len(files), count)
                if mode == 'auto':
                    self.assertEqual([p.name.split(' - ', 1)[1] for p in files], ['Открытие.mp3', 'Встреча.mp3'])

    def test_txt_auto_does_not_split_narrative_chapter_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'story.txt'
            source.write_text('Глава 1\nНачало истории.\nГлава поселения встретил гостей.\nГлава 2\nПродолжение.', encoding='utf-8')
            result = WorkerClient().run(dict(nvda=str(runtime.NVDA), addons=[], driver='espeak', action='convert',
                voice='', rate=50, language='ru', files=[str(source)], output=tmp, separator='Глава'), lambda event: None)
            self.assertEqual(result, {'type': 'done', 'count': 2})
            self.assertEqual([p.name.split(' - ', 1)[1] for p in sorted(root.rglob('*.mp3'))],
                             ['Глава 1.mp3', 'Глава 2.mp3'])

    def test_fb2_and_zip_use_real_titles_and_include_annotation_by_default(self):
        for zipped in (False, True):
            with self.subTest(zipped=zipped), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result, events, files = self.convert(root, zipped)
                self.assertEqual(result, {'type': 'done', 'count': 3})
                self.assertEqual([p.name.split(' - ', 1)[1] for p in files],
                                 ['Аннотация.mp3', 'Открытие.mp3', 'Встреча.mp3'])
                self.assertEqual(len([e for e in events if e['type'] == 'chapter']), 3)
                ffmpeg = shutil.which('ffmpeg')
                self.assertIsNotNone(ffmpeg)
                verifier = root / 'ffmpeg.exe'
                shutil.copy2(ffmpeg, verifier)
                for mp3 in files:
                    decoded = subprocess.run([str(verifier), '-v', 'error', '-i', str(mp3), '-f', 's16le', '-'],
                                             capture_output=True, timeout=20)
                    self.assertEqual(decoded.returncode, 0, decoded.stderr)
                    self.assertGreater(len(decoded.stdout), 1000)
                    self.assertTrue(any(decoded.stdout))


if __name__ == '__main__':
    unittest.main()
