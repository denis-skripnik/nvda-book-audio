"""PDF bookmarks are page boundaries; malformed outlines must not lose text."""
from pathlib import Path
from io import BytesIO
import sys
import tempfile
import unittest
from unittest.mock import patch, PropertyMock

PLUGIN = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
sys.path.insert(0, str(PLUGIN / 'vendor'))
from pypdf import PdfWriter, PdfReader
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from documents import read_book, read_document, plan_chapters


def make_pdf(texts, outlines=()):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(('BT /F1 12 Tf 30 250 Td (' + text + ') Tj ET').encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    for title, page in outlines:
        item = writer.add_outline_item(title, page)
        if title == 'Second':
            writer.add_outline_item('Nested same page', page, parent=item)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PdfStructureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / 'book.pdf'

    def test_preface_physical_order_and_first_bookmark_per_page(self):
        self.file.write_bytes(make_pdf(['Preface', 'Middle text', 'Final text'], [('Third', 2), ('Second', 1)]))
        book = read_book(self.file)
        self.assertEqual(book.kind, 'pdf')
        self.assertEqual([title for title, text in book.sections][1:], ['Second', 'Third'])
        self.assertEqual('\n\n'.join(text for title, text in book.sections), book.text)
        self.assertEqual(read_document(self.file), book.text)
        self.assertEqual(book.annotation, '')

    def test_no_outline_uses_fixed_numbered_fallback(self):
        self.file.write_bytes(make_pdf(['Chapter 1', 'Part II']))
        book = read_book(self.file)
        self.assertEqual(book.sections, [])
        self.assertEqual([title for title, text in plan_chapters(book, 'obsolete')], ['Chapter 1', 'Part II'])

    def test_broken_optional_outline_preserves_text_and_fallback(self):
        self.file.write_bytes(make_pdf(['Chapter 1', 'Part II'], [('Broken', 0)]))
        with patch.object(PdfReader, 'outline', new_callable=PropertyMock, side_effect=ValueError('broken outline')):
            book = read_book(self.file)
        self.assertEqual(book.sections, [])
        self.assertEqual([title for title, text in plan_chapters(book, '')], ['Chapter 1', 'Part II'])

    def test_unresolvable_out_of_range_destination_is_not_a_text_failure(self):
        self.file.write_bytes(make_pdf(['Body text'], [('Outside', 0)]))
        with patch.object(PdfReader, 'get_destination_page_number', return_value=999):
            book = read_book(self.file)
        self.assertEqual(book.sections, [])
        self.assertEqual(book.text, 'Body text')

    def test_blank_image_only_pages_do_not_create_empty_tracks(self):
        self.file.write_bytes(make_pdf(['', 'Readable text'], [('Empty', 0), ('Readable', 1)]))
        book = read_book(self.file)
        self.assertEqual(book.sections, [('Readable', 'Readable text')])
        self.assertEqual(book.text, 'Readable text')

    def test_no_text_still_requires_ocr(self):
        self.file.write_bytes(make_pdf([''], [('Title', 0)]))
        with self.assertRaisesRegex(ValueError, 'OCR'):
            read_book(self.file)


if __name__ == '__main__':
    unittest.main()
