"""Filesystem import fixtures only: no vendor engine, license, or running NVDA."""
import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'addon/globalPlugins/bookAudio/driver_dependencies.py'
SCRATCH = Path(tempfile.gettempdir())


def load_adapter():
    if not MODULE.is_file():
        raise AssertionError('Driver dependency adapter is not implemented')
    spec = importlib.util.spec_from_file_location('driver_dependencies', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DependencyTests(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.saved = {key: value for key, value in sys.modules.items()
                      if key == 'globalPlugins' or key.startswith('globalPlugins.')
                      or key == 'synthDrivers' or key.startswith('synthDrivers.')}
        for key in self.saved:
            del sys.modules[key]
        self.addCleanup(self.restore_modules)
        self.core = types.ModuleType('globalPlugins')
        self.core.__path__ = [str(self.root / 'core')]
        self.core.sentinel = object()
        self.synths = types.ModuleType('synthDrivers')
        self.synths.__path__ = []
        sys.modules['globalPlugins'] = self.core
        sys.modules['synthDrivers'] = self.synths

    def restore_modules(self):
        for key in list(sys.modules):
            if key == 'globalPlugins' or key.startswith('globalPlugins.') or key == 'synthDrivers' or key.startswith('synthDrivers.'):
                del sys.modules[key]
        sys.modules.update(self.saved)
        importlib.invalidate_caches()

    def addon(self, name='enabled', utils='value = 42\n'):
        root = self.root / name
        driver = root / 'synthDrivers/tiflotecniaVoices'
        dependency = root / 'globalPlugins/tiflotecniaVoices'
        driver.mkdir(parents=True)
        dependency.mkdir(parents=True)
        (driver / '__init__.py').write_text('raise AssertionError("driver executed too soon")\n', encoding='utf-8')
        (dependency / '__init__.py').write_text('raise AssertionError("global plugin initializer executed")\n', encoding='utf-8')
        (dependency / 'utils.py').write_text(utils, encoding='utf-8')
        (dependency / 'interface.py').write_text('raise AssertionError("UI exposed")\n', encoding='utf-8')
        (root / 'globalPlugins/unrelated.py').write_text('raise AssertionError("unrelated plugin executed")\n', encoding='utf-8')
        self.synths.__path__.append(str(root / 'synthDrivers'))
        return root

    def test_only_utils_is_exposed_without_executing_plugin_initializer(self):
        adapter = load_adapter()
        root = self.addon()
        original_path = list(self.core.__path__)
        original_sys_path = list(sys.path)
        adapter.prepare_driver_dependencies('tiflotecniaVoices', [types.SimpleNamespace(path=str(root))])
        package = importlib.import_module('globalPlugins.tiflotecniaVoices')
        utils = importlib.import_module('globalPlugins.tiflotecniaVoices.utils')
        self.assertEqual(utils.value, 42)
        self.assertIsNone(package.instance)
        self.assertEqual(package.__path__, [])
        self.assertIs(self.core, sys.modules['globalPlugins'])
        self.assertEqual(self.core.__path__, original_path)
        self.assertEqual(sys.path, original_sys_path)
        self.assertNotIn('synthDrivers.tiflotecniaVoices', sys.modules)
        for name in ('globalPlugins.unrelated', 'globalPlugins.tiflotecniaVoices.interface'):
            with self.assertRaises(ModuleNotFoundError):
                importlib.import_module(name)

    def test_dependency_follows_actual_synth_search_order_not_addon_order(self):
        adapter = load_adapter()
        first = self.addon('first', 'value = "first"\n')
        selected = self.addon('selected', 'value = "selected"\n')
        self.synths.__path__.reverse()
        unrelated = self.root / 'unrelated'
        unrelated.mkdir()
        adapter.prepare_driver_dependencies('tiflotecniaVoices', [unrelated, first, selected])
        self.assertEqual(importlib.import_module('globalPlugins.tiflotecniaVoices.utils').value, 'selected')

    def test_missing_or_mismatched_dependency_is_actionable_and_atomic(self):
        adapter = load_adapter()
        root = self.addon()
        utils = root / 'globalPlugins/tiflotecniaVoices/utils.py'
        utils.unlink()
        for addons in ([], [root]):
            with self.subTest(addons=addons):
                with self.assertRaisesRegex(RuntimeError, 'Tiflotecnia Voices.*enable.*reinstall'):
                    adapter.prepare_driver_dependencies('tiflotecniaVoices', addons)
                self.assertNotIn('globalPlugins.tiflotecniaVoices', sys.modules)
                self.assertFalse(hasattr(self.core, 'tiflotecniaVoices'))

    def test_repeated_prepare_deduplicates_case_aliases_without_reexecuting_utils(self):
        adapter = load_adapter()
        root = self.addon(utils='calls = globals().get("calls", 0) + 1\n')
        # Windows path identity is case insensitive; driver identifier is not.
        adapter.prepare_driver_dependencies('tiflotecniaVoices', [root, str(root).upper(), root / '.'])
        utils = importlib.import_module('globalPlugins.tiflotecniaVoices.utils')
        adapter.prepare_driver_dependencies('tiflotecniaVoices', [root])
        self.assertIs(utils, importlib.import_module('globalPlugins.tiflotecniaVoices.utils'))
        self.assertEqual(utils.calls, 1)

    def test_existing_foreign_package_is_not_replaced(self):
        adapter = load_adapter()
        root = self.addon()
        foreign = types.ModuleType('globalPlugins.tiflotecniaVoices')
        sys.modules[foreign.__name__] = foreign
        self.core.tiflotecniaVoices = foreign
        with self.assertRaisesRegex(RuntimeError, 'already loaded.*restart'):
            adapter.prepare_driver_dependencies('tiflotecniaVoices', [root])
        self.assertIs(sys.modules[foreign.__name__], foreign)
        self.assertIs(self.core.tiflotecniaVoices, foreign)

    def test_failed_utils_import_rolls_back_and_reports_cause(self):
        adapter = load_adapter()
        root = self.addon(utils='raise ValueError("fixture failure")\n')
        with self.assertRaisesRegex(RuntimeError, 'Tiflotecnia Voices.*fixture failure') as caught:
            adapter.prepare_driver_dependencies('tiflotecniaVoices', [root])
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertNotIn('globalPlugins.tiflotecniaVoices', sys.modules)
        self.assertNotIn('globalPlugins.tiflotecniaVoices.utils', sys.modules)
        self.assertFalse(hasattr(self.core, 'tiflotecniaVoices'))

    def test_loaded_driver_from_different_source_is_rejected(self):
        adapter = load_adapter()
        first = self.addon('first')
        second = self.addon('second')
        loaded = types.ModuleType('synthDrivers.tiflotecniaVoices')
        loaded.__file__ = str(second / 'synthDrivers/tiflotecniaVoices/__init__.py')
        sys.modules[loaded.__name__] = loaded
        with self.assertRaisesRegex(RuntimeError, 'already loaded.*restart'):
            adapter.prepare_driver_dependencies('tiflotecniaVoices', [first, second])
        self.assertNotIn('globalPlugins.tiflotecniaVoices', sys.modules)

    def test_import_does_not_write_bytecode_into_enabled_addon(self):
        adapter = load_adapter()
        root = self.addon()
        with patch.object(sys, 'dont_write_bytecode', False):
            adapter.prepare_driver_dependencies('tiflotecniaVoices', [root])
        self.assertEqual(list(root.rglob('__pycache__')), [])

    def test_incomplete_selected_addon_never_borrows_other_addon_dependency(self):
        adapter = load_adapter()
        selected = self.addon('selected')
        complete = self.addon('complete')
        (selected / 'globalPlugins/tiflotecniaVoices/__init__.py').unlink()
        with self.assertRaisesRegex(RuntimeError, 'enable or reinstall'):
            adapter.prepare_driver_dependencies('tiflotecniaVoices', [complete, selected])
        self.assertNotIn('globalPlugins.tiflotecniaVoices', sys.modules)

    def test_no_resolvable_driver_is_actionable_without_importing_plugins(self):
        adapter = load_adapter()
        root = self.addon()
        self.synths.__path__.clear()
        with self.assertRaisesRegex(RuntimeError, 'enable or reinstall'):
            adapter.prepare_driver_dependencies('tiflotecniaVoices', [root])
        self.assertNotIn('globalPlugins.tiflotecniaVoices', sys.modules)

    def test_source_shaped_utils_keeps_filename_translation_and_plugin_instance_none(self):
        import inspect
        adapter = load_adapter()
        source = ('import addonHandler\n'
                  'addonHandler.initTranslation()\n'
                  'addonInst = addonHandler.getCodeAddon()\n'
                  'addonName = addonInst.name\n'
                  'addonVersion = addonInst.version\n'
                  'addonSummary = _(addonInst.manifest["summary"])\n'
                  'menuEntryName = "&{name}".format(name=addonSummary)\n')
        root = self.addon(utils=source)
        handler = types.ModuleType('addonHandler')
        addon = types.SimpleNamespace(path=root, name='tiflotecniaVoices', version='fixture', manifest={'summary': 'Fixture voices'})
        def init_translation():
            inspect.currentframe().f_back.f_globals['_'] = lambda text: text
        def code_addon():
            self.assertEqual(Path(inspect.currentframe().f_back.f_code.co_filename), root / 'globalPlugins/tiflotecniaVoices/utils.py')
            return addon
        handler.initTranslation = init_translation
        handler.getCodeAddon = code_addon
        with patch.dict(sys.modules, {'addonHandler': handler}):
            adapter.prepare_driver_dependencies('tiflotecniaVoices', [addon])
            # Mirrors both imports at the head of the public driver/lowLevel.
            namespace = {}
            exec('import globalPlugins.tiflotecniaVoices as pluginInstance\nfrom globalPlugins.tiflotecniaVoices.utils import *', namespace)
        self.assertIsNone(namespace['pluginInstance'].instance)
        self.assertEqual(namespace['addonName'], 'tiflotecniaVoices')
        self.assertEqual(namespace['menuEntryName'], '&Fixture voices')

    def test_other_drivers_are_exact_noop(self):
        adapter = load_adapter()
        def forbidden():
            raise AssertionError('Nonmatching driver inspected addons')
            yield
        before = dict(sys.modules)
        for name in ('espeak', 'vocalizer', 'TiflotecniaVoices', 'tiflotecniavoices', ''):
            self.assertIsNone(adapter.prepare_driver_dependencies(name, forbidden()))
        self.assertEqual(sys.modules, before)


if __name__ == '__main__':
    unittest.main()
