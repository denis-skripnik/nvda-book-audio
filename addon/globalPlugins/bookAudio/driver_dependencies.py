"""Worker-only, opt-in import plumbing; not a synthesizer support guarantee."""


def prepare_driver_dependencies(driver, addons):
    """Prepare only the reviewed Tiflotecnia utils dependency in a private worker.

    Pass enabled Addon objects (or their filesystem roots) after synth search
    paths and capture are installed, immediately before getSynthInstance().
    Never call this in the user's running NVDA process. See the adapter notes
    for the reviewed source revision and the deliberately absent plugin UI.
    """
    if driver != 'tiflotecniaVoices':
        return

    import importlib
    from importlib.machinery import ModuleSpec
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path
    import sys

    from importlib.machinery import PathFinder
    synths = importlib.import_module('synthDrivers')
    selected = PathFinder.find_spec('synthDrivers.' + driver, synths.__path__)
    roots = {Path(getattr(addon, 'path', addon)).resolve() for addon in addons}
    root = next((root for root in roots
                 if selected and selected.origin
                 and Path(selected.origin).resolve() == root / 'synthDrivers' / driver / '__init__.py'), None)
    error = ('Tiflotecnia Voices dependency is unavailable in the selected enabled add-on; '
             'enable or reinstall the complete Tiflotecnia Voices add-on in NVDA, '
             'then retry Book Audio. No license activation is performed by this adapter.')
    if root is None:
        raise RuntimeError(error)
    loaded = sys.modules.get('synthDrivers.' + driver)
    if loaded is not None and (
        not getattr(loaded, '__file__', None)
        or Path(loaded.__file__).resolve() != Path(selected.origin).resolve()
    ):
        raise RuntimeError('Tiflotecnia Voices driver is already loaded from another source; restart the Book Audio worker.')
    dependency = root / 'globalPlugins' / driver
    if not all((dependency / file).is_file() for file in ('__init__.py', 'utils.py')):
        raise RuntimeError(error)
    core = importlib.import_module('globalPlugins')
    name = 'globalPlugins.' + driver
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, '_book_audio_dependency_root', None) == root:
        return
    if existing is not None or hasattr(core, driver) or any(
        key.startswith(name + '.') for key in sys.modules
    ):
        raise RuntimeError('Tiflotecnia Voices dependency is already loaded from another source; restart the Book Audio worker.')
    package = module_from_spec(ModuleSpec(name, loader=None, is_package=True))
    package._book_audio_dependency_root = root
    package.instance = None
    package.__file__ = str(dependency / '__init__.py')
    sys.modules[name] = package
    setattr(core, driver, package)
    spec = spec_from_file_location(name + '.utils', dependency / 'utils.py')
    utils = module_from_spec(spec)
    sys.modules[spec.name] = utils
    try:
        # Execute with the real filename for addonHandler.getCodeAddon(), but
        # never let SourceFileLoader write __pycache__ into the enabled add-on.
        exec(compile((dependency / 'utils.py').read_bytes(), spec.origin, 'exec'), utils.__dict__)
    except Exception as cause:
        sys.modules.pop(spec.name, None)
        sys.modules.pop(name, None)
        delattr(core, driver)
        raise RuntimeError(error + ' Import failed: ' + str(cause)) from cause
    package.utils = utils
