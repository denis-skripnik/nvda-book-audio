import importlib.util
import io
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class PrivacyAuditTests(unittest.TestCase):
    def scanner(self):
        file = ROOT / 'tools/audit_privacy.py'
        self.assertTrue(file.is_file(), 'Publication privacy scanner is not implemented')
        spec = importlib.util.spec_from_file_location('privacy_audit', file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_finds_identifiers_in_nested_archive_without_disclosing_value(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('trace.txt', 'C:/Users/private-test-account/work')
        findings = self.scanner().scan_blob('fixture.zip', stream.getvalue(), ['private-test-account'])
        self.assertTrue(findings)
        self.assertTrue(any('trace.txt' in item['file'] for item in findings))
        self.assertNotIn('private-test-account', str(findings))

    def test_scans_utf16_identifiers(self):
        findings = self.scanner().scan_blob('fixture.bin', 'PRIVATE-TEST-HOST'.encode('utf-16-le'), ['private-test-host'])
        self.assertTrue(findings)

    def test_word_boundaries_avoid_substring_false_positives(self):
        findings = self.scanner().scan_blob('fixture.txt', b'public scannercascade example', ['cascade'])
        self.assertEqual(findings, [])

    def test_detects_credential_format(self):
        sample = ('ghp_' + 'a' * 36).encode()
        findings = self.scanner().scan_blob('fixture.txt', sample, [])
        self.assertTrue(any(item['category'] == 'credential-format' for item in findings))


if __name__ == '__main__':
    unittest.main()
