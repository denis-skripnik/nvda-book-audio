"""Pure, lossless additional punctuation pauses; no NVDA runtime required."""
from pathlib import Path
import sys
import unittest

PLUGIN = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
from pauses import pause_segments, validate_pauses


class PauseTests(unittest.TestCase):
    def test_spaced_russian_abbreviations(self):
        for text in ('и т. д. далее, и т. п. дальше, т. е. пояснение',
                     'и т.е. пояснение', 'и Т. Д. далее', 'и т. п.'):
            with self.subTest(text=text):
                self.assertEqual(pause_segments(text, sentence_ms=100), [('text', text)])

    def test_comma_and_numeric_comma(self):
        self.assertEqual(pause_segments('Да, 1,5, нет', 120),
                         [('text', 'Да,'), ('pause', 120), ('text', ' 1,5,'),
                          ('pause', 120), ('text', ' нет')])
        self.assertEqual(pause_segments(',word', 120),
                         [('text', ','), ('pause', 120), ('text', 'word')])

    def test_sentence_clusters_and_closing_quotes(self):
        self.assertEqual(pause_segments('«Да?!» Next...\n(Нет.) Done!x', 0, 250),
            [('text', '«Да?!»'), ('pause', 250), ('text', ' Next...'),
             ('pause', 250), ('text', '\n(Нет.)'), ('pause', 250), ('text', ' Done!x')])

    def test_abbreviations_initials_and_nonterminal_numbers(self):
        samples = [
            'г. Москва, ул. Мира, д. 5, стр. 3, рис. 2, им. Пушкина',
            'и т.д. далее и т.п. дальше',
            'Mr. Smith, Mrs. Brown, Dr. Иванов, e.g. sample, i.e. example, etc. далее',
            'A. B. Иванов и А. Б. Smith',
            '1. пункт 2. пункт, 3.14 и v1.2.3 https://example.com/a user@example.com',
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assertEqual(pause_segments(text, sentence_ms=100), [('text', text)])
        for text in ('Это т.д.!', 'Ask Dr.?!', 'Это т.п....', 'A. B. Иванов.'):
            with self.subTest(text=text):
                self.assertEqual(pause_segments(text, sentence_ms=100),
                                 [('text', text), ('pause', 100)])

    def test_invalid_parameters_and_bounds(self):
        message = 'Пауза должна быть целым числом от 0 до 2000 мс.'
        for invalid in (True, False, -1, 2001, 1.0, '100', None, [], {}):
            for kwargs in ({'comma_ms': invalid}, {'sentence_ms': invalid}):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaisesRegex(ValueError, '^' + message.replace('.', r'\.') + '$'):
                        validate_pauses(**kwargs)
                    with self.assertRaises(ValueError):
                        pause_segments('', **kwargs)
        self.assertIsNone(validate_pauses(0, 2000))
        self.assertIsNone(validate_pauses(2000, 0))
        self.assertEqual(pause_segments('x, y.', 2000, 2000),
            [('text', 'x,'), ('pause', 2000), ('text', ' y.'), ('pause', 2000)])

    def test_quoted_abbreviation_stays_protected(self):
        self.assertEqual(pause_segments('«стр.» далее', sentence_ms=100),
                         [('text', '«стр.» далее')])

    def test_zero_identity_and_independent_categories(self):
        for text in ('', 'Да, нет.\n', '&lt;tag&gt; &amp; &#46;', 'A. B. Иванов…'):
            self.assertEqual(pause_segments(text), [('text', text)])
        self.assertEqual(pause_segments('a, b.', 10, 0),
                         [('text', 'a,'), ('pause', 10), ('text', ' b.')])
        self.assertEqual(pause_segments('a, b.', 0, 20),
                         [('text', 'a, b.'), ('pause', 20)])

    def test_exact_text_preservation_property_cases(self):
        import itertools
        atoms = ('', ',', '1,5', '…?!»', ' т.д.', '\n\t ', '&lt;x&gt;', 'Hello.', 'Привет!')
        for pieces in itertools.product(atoms, repeat=2):
            text = ''.join(pieces)
            for comma, sentence in ((0, 0), (17, 0), (0, 29), (17, 29)):
                result = pause_segments(text, comma, sentence)
                self.assertEqual(''.join(value for kind, value in result if kind == 'text'), text)
                self.assertEqual(result[0][0], 'text')
                self.assertTrue(all(kind in ('text', 'pause') for kind, value in result))
                self.assertTrue(all(value for kind, value in result if kind == 'text') or text == '')
                self.assertTrue(all(type(value) is int and value in (17, 29)
                                    for kind, value in result if kind == 'pause'))

    def test_unicode_ellipsis(self):
        self.assertEqual(pause_segments('Wait…» Ещё…?!', sentence_ms=300),
            [('text', 'Wait…»'), ('pause', 300), ('text', ' Ещё…?!'), ('pause', 300)])


if __name__ == '__main__':
    unittest.main()
