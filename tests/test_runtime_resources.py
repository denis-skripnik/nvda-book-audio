"""Frozen-resource import scope; real version-matrix synthesis is in test_runtime."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/bookAudio'
sys.path.insert(0, str(PLUGIN))
import worker


class FrozenResourceTests(unittest.TestCase):
    def test_optional_package_absent_keeps_runtime_executable(self):
        original = sys.executable
        with patch('importlib.util.find_spec', return_value=None), patch('importlib.import_module') as load:
            worker.preload_nvda_resources(Path('fixture-nvda'))
        self.assertEqual(sys.executable, original)
        load.assert_not_called()

    def test_import_resolves_against_nvda_then_restores_runtime(self):
        original = sys.executable
        seen = []
        def load(name):
            seen.append((name, sys.executable))
        with patch('importlib.util.find_spec', return_value=object()), patch('importlib.import_module', load):
            worker.preload_nvda_resources(Path('fixture-nvda'))
        self.assertEqual(seen, [('pyphen', str(Path('fixture-nvda') / 'nvda.exe'))])
        self.assertEqual(sys.executable, original)

    def test_winrt_tables_load_from_nvda_even_without_pyphen(self):
        import tempfile
        original = sys.executable
        with tempfile.TemporaryDirectory() as temp:
            nvda = Path(temp)
            table = nvda / 'winrt/windows/devices/bluetooth/_table.pywinrt'
            table.parent.mkdir(parents=True)
            table.write_bytes(b'projection fixture')
            seen = []
            def load(name):
                resource = Path(sys.executable).parent.joinpath(*name.split('.'), '_table.pywinrt')
                self.assertEqual(resource.read_bytes(), b'projection fixture')
                seen.append(name)
            with patch('importlib.util.find_spec', return_value=None), patch('importlib.import_module', load):
                worker.preload_nvda_resources(nvda)
            self.assertEqual(seen, ['winrt.windows.devices.bluetooth'])
        self.assertEqual(sys.executable, original)

    def test_import_error_also_restores_runtime_executable(self):
        original = sys.executable
        with patch('importlib.util.find_spec', return_value=object()), patch('importlib.import_module', side_effect=OSError('fixture missing data')):
            with self.assertRaisesRegex(OSError, 'fixture missing data'):
                worker.preload_nvda_resources(Path('fixture-nvda'))
        self.assertEqual(sys.executable, original)


if __name__ == '__main__':
    unittest.main()
