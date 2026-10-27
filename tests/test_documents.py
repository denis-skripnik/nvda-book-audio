"""Real-file document parser tests, independent of NVDA."""
import importlib.util
import pathlib
import tempfile
import unittest
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'addon/globalPlugins/bookAudio'))
SPEC = importlib.util.spec_from_file_location("book_audio_documents", ROOT / "addon/globalPlugins/bookAudio/documents.py")


def load_documents():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.documents = load_documents()
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.cleanup_temp)
        self.directory = pathlib.Path(self.temp.name)

    def cleanup_temp(self):
        # Windows antivirus/indexers can briefly hold just-created fixtures.
        for attempt in range(5):
            try:
                self.temp.cleanup()
                return
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(0.1)

    def fixture(self, name, data):
        path = self.directory / name
        path.write_bytes(data)
        return path

    def zip_fixture(self, entries, name="book.fb2.zip"):
        import zipfile
        path = self.directory / name
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member, data in entries:
                archive.writestr(member, data)
        return path

    def test_fb2_zip_reads_nested_payload_in_memory_case_insensitively(self):
        xml = '<FictionBook><body><p>Привет мир!</p></body></FictionBook>'
        path = self.zip_fixture([('folder/', b''), ('folder/book.FB2', xml.encode()),
                                 ('cover.jpg', b'image')], 'BOOK.Fb2.ZiP')
        before = set(self.directory.rglob('*'))
        self.assertEqual(self.documents.read_document(path), 'Привет мир!')
        self.assertEqual(set(self.directory.rglob('*')), before)
        with self.assertRaisesRegex(ValueError, 'формат'):
            self.documents.read_document(self.zip_fixture([('book.fb2', xml)], 'book.zip'))

    def test_fb2_zip_requires_exactly_one_payload(self):
        import warnings
        xml = b'<FictionBook><body><p>text</p></body></FictionBook>'
        for entries in ([('cover.jpg', b'image'), ('empty.fb2/', b'')],
                        [('a.fb2', xml), ('b.FB2', xml)],
                        [('book.fb2', xml), ('book.fb2', xml)]):
            with self.subTest(entries=[name for name, _ in entries]):
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    path = self.zip_fixture(entries)
                with self.assertRaisesRegex(ValueError, 'ровно один файл FB2'):
                    self.documents.read_document(path)

    def test_fb2_zip_rejects_unsafe_member_paths_including_assets(self):
        xml = b'<FictionBook><body><p>text</p></body></FictionBook>'
        for name in ('../book.fb2', 'folder/../book.fb2', '/book.fb2',
                     '\\book.fb2', 'folder\\..\\book.fb2', 'C:/book.fb2',
                     'C:book.fb2', '//server/share/book.fb2'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'небезопасное имя'):
                    self.documents.read_document(self.zip_fixture([(name, xml)]))
        with self.assertRaisesRegex(ValueError, 'небезопасное имя'):
            self.documents.read_document(self.zip_fixture([('book.fb2', xml), ('../cover.jpg', b'x')]))

    def test_fb2_zip_rejects_broken_crc_and_encrypted_archives(self):
        import struct
        xml = b'<FictionBook><body><p>text</p></body></FictionBook>'
        valid = self.zip_fixture([('book.fb2', xml)]).read_bytes()
        central = valid.index(b'PK\x01\x02')
        encrypted = bytearray(valid)
        for offset in (6, central + 8):
            flags = struct.unpack_from('<H', encrypted, offset)[0]
            struct.pack_into('<H', encrypted, offset, flags | 1)
        bad_crc = bytearray(valid)
        struct.pack_into('<I', bad_crc, central + 16, 0)
        for data, message in ((b'not a zip', 'поврежд'), (valid[:-22], 'поврежд'),
                              (bad_crc, 'поврежд'), (encrypted, 'зашифрован')):
            with self.subTest(message=message, length=len(data)):
                with self.assertRaisesRegex(ValueError, message):
                    self.documents.read_document(self.fixture('bad.fb2.zip', data))

    def test_fb2_zip_rejects_unsafe_and_malformed_xml(self):
        for xml in (b'<FictionBook><body>',
                    b'<!DOCTYPE FictionBook [<!ENTITY x "bad">]><FictionBook><body><p>&x;</p></body></FictionBook>'):
            with self.subTest(xml=xml):
                with self.assertRaisesRegex(ValueError, 'небезопасный XML'):
                    self.documents.read_document(self.zip_fixture([('book.fb2', xml)]))

    def test_fb2_zip_limits_compressed_and_expanded_sizes(self):
        from unittest.mock import patch
        xml = b'<FictionBook><body><p>' + b'x' * 4096 + b'</p></body></FictionBook>'
        compressed = self.zip_fixture([('book.fb2', xml)])
        self.assertLess(compressed.stat().st_size, 1024)
        with patch.object(self.documents, 'MAX_DOCUMENT_BYTES', 1024, create=True):
            with self.assertRaisesRegex(ValueError, '128 МиБ'):
                self.documents.read_document(compressed)
        archive = self.zip_fixture([('book.fb2', b'<FictionBook/>'), ('cover.jpg', bytes(range(256)) * 8)])
        with patch.object(self.documents, 'MAX_DOCUMENT_BYTES', 128, create=True):
            with self.assertRaisesRegex(ValueError, '128 МиБ'):
                self.documents.read_document(archive)
            # Size can change after stat; the input read itself must be bounded.
            with patch.object(pathlib.Path, 'stat') as stat:
                stat.return_value.st_size = 0
                with self.assertRaisesRegex(ValueError, '128 МиБ'):
                    self.documents.read_document(archive)

    def test_fb2_zip_rejects_forged_expanded_size_even_with_prefix_crc(self):
        import struct
        import zlib
        from unittest.mock import patch
        prefix = b'<FictionBook><body><p>prefix</p></body></FictionBook>'
        xml = prefix + b' ' * 4096
        path = self.zip_fixture([('book.fb2', xml)])
        valid = path.read_bytes()
        central = valid.index(b'PK\x01\x02')
        for declared in (len(prefix), len(xml) + 1):
            with self.subTest(declared=declared):
                forged = bytearray(valid)
                for offset in (22, central + 24):
                    struct.pack_into('<I', forged, offset, declared)
                if declared == len(prefix):
                    # A plain ZipExtFile read silently truncates to declared size.
                    for offset in (14, central + 16):
                        struct.pack_into('<I', forged, offset, zlib.crc32(prefix))
                path.write_bytes(forged)
                with patch.object(self.documents, 'MAX_DOCUMENT_BYTES', 1024, create=True):
                    with self.assertRaisesRegex(ValueError, '128 МиБ|размер|поврежд'):
                        self.documents.read_document(path)

    def test_fb2_zip_accepts_exact_expanded_limit_and_rejects_size_mismatch(self):
        import struct
        from unittest.mock import patch
        xml = b'<FictionBook><body><p>' + b'x' * 1024 + b'</p></body></FictionBook>'
        path = self.zip_fixture([('book.fb2', xml)])
        with patch.object(self.documents, 'MAX_DOCUMENT_BYTES', len(xml)):
            self.assertEqual(self.documents.read_document(path), 'x' * 1024)
        valid = path.read_bytes()
        central = valid.index(b'PK\x01\x02')
        for declared in (len(xml) - 1, len(xml) + 1):
            with self.subTest(declared=declared):
                forged = bytearray(valid)
                for offset in (22, central + 24):
                    struct.pack_into('<I', forged, offset, declared)
                with patch.object(self.documents, 'MAX_DOCUMENT_BYTES', 2048):
                    with self.assertRaisesRegex(ValueError, 'неверный размер'):
                        self.documents.read_document(self.fixture('size.fb2.zip', forged))

    def test_fb2_zip_uses_bounded_read_for_underdeclared_bomb(self):
        import struct
        import zipfile
        from unittest.mock import patch
        xml = b'<FictionBook><body><p>' + b'x' * 8192 + b'</p></body></FictionBook>'
        path = self.zip_fixture([('book.fb2', xml)])
        forged = bytearray(path.read_bytes())
        central = forged.index(b'PK\x01\x02')
        for offset in (22, central + 24):
            struct.pack_into('<I', forged, offset, 10)
        path.write_bytes(forged)
        read = zipfile.ZipExtFile.read
        sizes = []
        def track_read(stream, size=-1):
            sizes.append(size)
            return read(stream, size)
        with patch.object(self.documents, 'MAX_DOCUMENT_BYTES', 1024):
            with patch.object(zipfile.ZipExtFile, 'read', track_read):
                with self.assertRaisesRegex(ValueError, '128 МиБ|поврежд'):
                    self.documents.read_document(path)
        self.assertEqual(sizes, [1025])

    def test_txt_encodings(self):
        text = "Глава 1\nПривет, мир!"
        for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-16-be", "cp1251"):
            with self.subTest(encoding=encoding):
                data = text.encode(encoding)
                if encoding == "utf-16-be":
                    data = b"\xfe\xff" + data
                self.assertEqual(self.documents.read_document(self.fixture("book.TXT", data)), text)

    def test_fb2_body_structure_only(self):
        xml = '''<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
<description><title-info><annotation><p>СЕКРЕТ МЕТАДАННЫХ</p></annotation></title-info></description>
<body><section><title><p>Глава 1</p></title><subtitle>Подзаголовок</subtitle>
<p>Привет <emphasis>мир</emphasis>!</p><empty-line/><p>Продолжение.</p>
<image>НЕ ТЕКСТ</image></section></body><binary>БИНАРНЫЕ ДАННЫЕ</binary>
</FictionBook>'''
        self.assertEqual(self.documents.read_document(self.fixture("book.fb2", xml.encode())),
                         "Глава 1\nПодзаголовок\nПривет мир!\n\nПродолжение.")

    def test_fb2_preserves_poems_authors_and_table_cells(self):
        xml = '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><body><section><poem><stanza><v>Первая строка</v><v>Вторая <emphasis>строка</emphasis></v></stanza><text-author>Автор стихов</text-author></poem><table><tr><th>Заголовок</th><td>Ячейка</td></tr></table></section></body></FictionBook>'
        text = self.documents.read_document(self.fixture('poem.fb2', xml.encode()))
        self.assertEqual(text, 'Первая строка\nВторая строка\nАвтор стихов\nЗаголовок\nЯчейка')
        self.assertTrue(self.documents.split_chapters(text, 'Глава'))
        mixed = xml.replace('<poem>', '<p>Проза до стихов.</p><poem>')
        mixed_text = self.documents.read_document(self.fixture('mixed.fb2', mixed.encode()))
        self.assertTrue(mixed_text.startswith('Проза до стихов.\nПервая строка\nВторая строка'))

    def test_fb2_rejects_entities_and_malformed_xml(self):
        for xml in ('<!DOCTYPE FictionBook [<!ENTITY x "опасно">]><FictionBook><body><p>&x;</p></body></FictionBook>',
                    '<FictionBook><body>'):
            with self.subTest(xml=xml):
                with self.assertRaisesRegex(ValueError, "FB2|ФБ2"):
                    self.documents.read_document(self.fixture("unsafe.fb2", xml.encode()))

    def pdf_fixture(self, password=None, text=True):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        if text:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 10 200 Td (Chapter one) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
        if password is not None:
            writer.encrypt(user_password=password, owner_password="owner-secret")
        path = self.directory / "book.pdf"
        writer.write(path)
        return path

    def test_pdf_text_and_blank_password(self):
        for password in (None, ""):
            with self.subTest(password=password):
                self.assertEqual(self.documents.read_document(self.pdf_fixture(password)).strip(), "Chapter one")

    def test_pdf_password_and_ocr_errors_are_russian(self):
        with self.assertRaisesRegex(ValueError, "парол"):
            self.documents.read_document(self.pdf_fixture("secret"))
        with self.assertRaisesRegex(ValueError, "OCR"):
            self.documents.read_document(self.pdf_fixture(text=False))

    def test_split_literal_line_headings_preserves_preface(self):
        text = "Предисловие\nЭто Глава внутри строки\nГлаварь остаётся\nгЛаВа 1\nТекст\nГлава: 2\nКонец"
        self.assertEqual(self.documents.split_chapters(text, "Глава"), [
            ("Предисловие", "Предисловие\nЭто Глава внутри строки\nГлаварь остаётся"),
            ("гЛаВа 1", "гЛаВа 1\nТекст"), ("Глава: 2", "Глава: 2\nКонец")])

    def test_split_empty_separator_no_match_literal_and_empty_book(self):
        self.assertEqual(self.documents.split_chapters("Глава 1\nТекст", ""), [("Книга", "Глава 1\nТекст")])
        self.assertEqual(self.documents.split_chapters("Текст", "Глава"), [("Книга", "Текст")])
        self.assertEqual(self.documents.split_chapters("", "Глава"), [])
        self.assertEqual(self.documents.split_chapters("Часть [1]\nА\nЧасть 1\nБ", "Часть [1]"),
                         [("Часть [1]", "Часть [1]\nА\nЧасть 1\nБ")])
        self.assertEqual(self.documents.split_chapters("Глава 1\r\nА\r\nГлава 2\r\nБ", "Глава"),
                         [("Глава 1", "Глава 1\nА"), ("Глава 2", "Глава 2\nБ")])

    def test_safe_windows_names(self):
        for name in ("CON", "con.txt", "PRN", "AUX", "NUL", "COM1", "LPT9", "COM¹", "LPT²", "CONIN$", "CONOUT$"):
            with self.subTest(name=name):
                safe = self.documents.safe_name(name)
                self.assertNotEqual(safe.split(".")[0].upper(), name.split(".")[0].upper())
        for name in ("../../escape", "..\\..\\escape", "<>:\"/\\|?*\x00\x1f", "...", "", "тест. ", "а" * 200):
            with self.subTest(name=name):
                safe = self.documents.safe_name(name)
                self.assertTrue(safe)
                self.assertLessEqual(len(safe), 100)
                self.assertNotIn(safe, (".", ".."))
                self.assertEqual(safe, safe.rstrip(" ."))
                self.assertFalse(any(c in '<>:"/\\|?*' or ord(c) < 32 for c in safe))
        self.assertEqual(self.documents.safe_name("Глава 1"), "Глава 1")

    def test_read_errors_are_russian(self):
        with self.assertRaisesRegex(ValueError, "прочитать"):
            self.documents.read_document(self.directory / "missing.txt")
        with self.assertRaisesRegex(ValueError, "формат"):
            self.documents.read_document(self.fixture("book.doc", b"text"))
        with self.assertRaisesRegex(ValueError, "кодиров"):
            self.documents.read_document(self.fixture("bad.txt", b"\xff\xfe\x00"))
        with self.assertRaisesRegex(ValueError, "кодиров"):
            self.documents.read_document(self.fixture("bad.txt", b"\x98"))
        with self.assertRaisesRegex(ValueError, "PDF"):
            self.documents.read_document(self.fixture("bad.pdf", b"not a pdf"))

    def test_reject_document_over_128_mib(self):
        path = self.directory / "large.txt"
        with path.open("wb") as stream:
            stream.truncate(128 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "128"):
            self.documents.read_document(path)


if __name__ == "__main__":
    unittest.main()
