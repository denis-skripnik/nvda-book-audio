"""Structural book planning regressions, using real files outside NVDA."""
import pathlib
import tempfile
import unittest
import zipfile

from test_documents import load_documents


class BookStructureTests(unittest.TestCase):
    def setUp(self):
        self.d = load_documents()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = pathlib.Path(self.temp.name)

    def fb2(self, body, description=''):
        xml = ('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
               + description + body + '</FictionBook>').encode()
        path = self.directory / 'book.fb2'
        path.write_bytes(xml)
        return path

    def test_read_book_partitions_nested_structure_without_losing_text(self):
        path = self.fb2('''<body><p>Preface.</p><section><title><p>Parent</p></title>
<section><title><p>Child A</p></title><p>Глава поселения пришёл.</p></section>
<p>Between.</p><section><section><title><p>Child B</p></title>
<poem><stanza><v>Verse.</v></stanza><text-author>Poet.</text-author></poem>
<table><tr><th>Header.</th><td>Cell.</td></tr></table></section></section>
<p>Trailing.</p></section></body><body name="notes"><p>Notes.</p></body>''',
            '<description><title-info><book-title>Глава misleading</book-title></title-info></description>')
        book = self.d.read_book(path)
        self.assertEqual(book.kind, 'fb2')
        self.assertEqual(book.text, self.d.read_document(path))
        self.assertEqual(book.annotation, '')
        self.assertEqual(book.sections, [
            ('Предисловие', 'Preface.'),
            ('Child A', 'Parent\nChild A\nГлава поселения пришёл.\nBetween.'),
            ('Child B', 'Child B\nVerse.\nPoet.\nHeader.\nCell.\nTrailing.\nNotes.')])
        self.assertEqual('\n'.join(text for _, text in book.sections), book.text)

    def test_annotation_primary_only_mixed_markup_and_zip_equivalence(self):
        path = self.fb2('<body><section><title><p>Open</p></title><p>Body.</p></section></body>',
            '<description><title-info><annotation><p>A <emphasis>mixed</emphasis> summary.</p><p>Next.</p></annotation></title-info>'
            '<src-title-info><annotation><p>Do not duplicate.</p></annotation></src-title-info></description>')
        book = self.d.read_book(path)
        self.assertEqual(book.annotation, 'A mixed summary.\nNext.')
        self.assertEqual(book.text, 'Open\nBody.')
        zipped = self.directory / 'book.fb2.zip'
        with zipfile.ZipFile(zipped, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('nested/book.FB2', path.read_bytes())
        self.assertEqual(self.d.read_book(zipped), book)

    def test_modes_annotation_and_validation(self):
        book = self.d.Document('Open\nГлава поселения arrived.\nMeeting\nEnd.',
            [('Open', 'Open\nГлава поселения arrived.'), ('Meeting', 'Meeting\nEnd.')], 'Summary.', 'fb2')
        for mode in ('auto', 'structure'):
            self.assertEqual(self.d.plan_chapters(book, 'Глава', mode),
                             [('Аннотация', 'Summary.')] + book.sections)
            self.assertEqual(self.d.plan_chapters(book, 'Глава', mode, False), book.sections)
        self.assertEqual(self.d.plan_chapters(book, 'Глава', 'phrase'),
                         [('Аннотация', 'Summary.')] + self.d.split_chapters(book.text, 'Глава'))
        self.assertEqual(self.d.plan_chapters(book, 'Глава', 'none'),
                         [('Книга', 'Summary.\n\n' + book.text)])
        self.assertEqual(self.d.plan_chapters(book, 'Глава', 'none', False), [('Книга', book.text)])
        for mode in ('invalid', '', None):
            with self.assertRaisesRegex(ValueError, 'Неизвестный режим разбиения книги'):
                self.d.plan_chapters(book, '', mode)
        for include in (1, 0, 'true', None):
            with self.assertRaisesRegex(ValueError, 'Параметр озвучивания аннотации'):
                self.d.plan_chapters(book, '', include_annotation=include)

    def test_auto_plain_numbered_headings_are_conservative(self):
        headings = ['Глава 1', 'чАсТь II.', 'CHAPTER IV', 'part 12.',
                    'Глава первая', 'Часть двадцать первая', 'Chapter One', 'Part Twenty-One']
        text = 'Preface.\nГлава поселения пришёл.\nЧасть людей\n' + '\n'.join(
            h + '\nBody ' + str(i) for i, h in enumerate(headings))
        for kind in ('txt', 'pdf', 'fb2'):
            for separator in ('Глава', 'bananas', ''):
                with self.subTest(kind=kind, separator=separator):
                    book = self.d.Document(text, [], kind=kind)
                    plan = self.d.plan_chapters(book, separator)
                    self.assertEqual([title for title, _ in plan], ['Предисловие'] + headings)
                    self.assertEqual('\n'.join(body for _, body in plan), text)
                    self.assertEqual(self.d.plan_chapters(book, separator, 'structure'), [('Книга', text)])
        for line in ('Глава поселения', 'Глава первая встретила нас.', 'Глава 1 человек пришёл.',
                     'Chapter One person arrived.', 'Chapter CIVIL matters', 'Главарь 1', 'Глава IIX',
                     'Часть людей', 'Глава 1..', 'Part VX', 'bananas 1', 'Chapter 1: A title'):
            text = 'Start\n' + line + '\nEnd'
            prefix = 'Chapter' if line.startswith('Chapter') else 'Глава'
            self.assertEqual(self.d.plan_chapters(self.d.Document(text, []), prefix), [('Книга', text)])

    def test_auto_preserves_indentation_blank_lines_and_heading_limit(self):
        long_line = 'Chapter ' + '1' * 113  # 121 characters: not a heading.
        text = 'Preface.  \n\n' + long_line + '\n\n  Chapter I.\n  Body.  \n\n\tЧасть 2\nLast.'
        plan = self.d.plan_chapters(self.d.Document(text, []), 'bananas')
        self.assertEqual([title for title, _ in plan], ['Предисловие', 'Chapter I.', 'Часть 2'])
        self.assertEqual('\n'.join(body for _, body in plan), text)

    def test_auto_prefers_structural_sections_for_every_format(self):
        text = 'Chapter 1\nBody.\nPart II\nEnd.'
        sections = [('Actual heading', text)]
        for kind in ('txt', 'pdf', 'fb2'):
            book = self.d.Document(text, sections, 'Summary.', kind)
            self.assertEqual(self.d.plan_chapters(book, 'bananas'), [('Аннотация', 'Summary.')] + sections)
            self.assertEqual(self.d.plan_chapters(book, '', include_annotation=False), sections)

    def test_fb2_without_titles_uses_numbered_fallback(self):
        for annotation in ('', '<annotation/>'):
            path = self.fb2('<body><title><p>Глава title of book</p></title><section><p>Глава 1</p>'
                            '<p>Глава поселения arrived.</p><p>Глава 2</p></section></body>',
                '<description><title-info>' + annotation + '</title-info>'
                '<src-title-info><annotation><p>Excluded source annotation.</p></annotation></src-title-info></description>')
            book = self.d.read_book(path)
            self.assertEqual(book.annotation, '')
            self.assertEqual(book.sections, [])
            self.assertEqual(self.d.plan_chapters(book, 'Глава', 'structure'), [('Книга', book.text)])
            self.assertEqual(self.d.plan_chapters(book, ''), [
                ('Предисловие', 'Глава title of book'),
                ('Глава 1', 'Глава 1\nГлава поселения arrived.'), ('Глава 2', 'Глава 2')])

    def test_titled_parent_with_content_and_untitled_wrappers(self):
        path = self.fb2('<body><section><section><title><p>Parent</p></title><p>Intro.</p>'
                        '<section><title><p>Child</p></title><p>Middle.</p></section>'
                        '<p>After.</p></section><p>Final.</p></section></body>')
        book = self.d.read_book(path)
        self.assertEqual(book.sections, [('Parent', 'Parent\nIntro.'), ('Child', 'Child\nMiddle.\nAfter.\nFinal.')])
        self.assertEqual('\n'.join(text for _, text in book.sections), book.text)
        self.assertEqual(self.d.plan_chapters(book, ''), book.sections)

    def test_empty_body_and_annotation_only(self):
        book = self.d.read_book(self.fb2('<body/>',
            '<description><title-info><annotation><p>Summary.</p></annotation></title-info></description>'))
        self.assertEqual(self.d.plan_chapters(book, 'Глава'), [('Аннотация', 'Summary.')])
        self.assertEqual(self.d.plan_chapters(book, 'Глава', 'none'), [('Книга', 'Summary.')])
        self.assertEqual(self.d.plan_chapters(book, 'Глава', include_annotation=False), [])
        self.assertEqual(self.d.plan_chapters(self.d.Document('', []), 'Глава'), [])

    def test_read_book_uses_the_same_safe_xml_and_zip_loader(self):
        import struct
        for xml in (b'<!DOCTYPE FictionBook><FictionBook/>',
                    b'<!DOCTYPE FictionBook [<!ENTITY x SYSTEM "file:///never-read">]><FictionBook><body><p>&x;</p></body></FictionBook>'):
            path = self.directory / 'unsafe.fb2'
            path.write_bytes(xml)
            with self.assertRaisesRegex(ValueError, 'небезопасный XML'):
                self.d.read_book(path)
        xml = b'<FictionBook><body><p>Safe.</p></body></FictionBook>'
        for member in ('../book.fb2', 'nested/book.fb2'):
            path = self.directory / 'unsafe.fb2.zip'
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(member, xml)
            if member.startswith('..'):
                with self.assertRaisesRegex(ValueError, 'небезопасное имя'):
                    self.d.read_book(path)
            else:
                data = bytearray(path.read_bytes())
                central = data.index(b'PK\x01\x02')
                struct.pack_into('<I', data, central + 16, 0)
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'поврежд'):
                    self.d.read_book(path)


if __name__ == '__main__':
    unittest.main()
