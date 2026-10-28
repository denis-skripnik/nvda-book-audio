# Development

## Layout

- `addon/`: NVDA add-on source, vendored runtime/dependencies and licenses.
- `tests/`: pure unit tests, isolated NVDA integration tests and native wx checks.
- `tools/`: translation compiler and publication privacy audit.
- `third_party_sources/`: corresponding sources/build material for bundled encoder components.
- `dist/`: generated installable add-on; binaries are distributed as GitHub release assets, not committed to source history.

## Build

On Windows, with Python installed:

```console
python build.py
```

This compiles the English gettext catalog and produces `dist/bookAudio-0.1.5.nvda-addon`. Russian help is generated from `README.ru.md`, English help from `README.md`. No separate FFmpeg is needed at runtime.

## Test

```console
python -m unittest discover -s tests -v
```

Real-driver tests require the targeted NVDA installation and voices. `test_newfon_runtime.py` is opt-in via a validated `BOOK_AUDIO_NEWFON_FIXTURE` and a `BOOK_AUDIO_NEWFON_JOBS` directory. Use a disposable test directory through `TEMP`/`TMP` when desired. FFmpeg is a development-only independent decoder.

Native checks such as `tests/gui_probe_check.py`, `tests/gui_focus_check.py`, `tests/gesture_check.py` and `tests/packed_check.py` use `addon/globalPlugins/bookAudio/runtime/python.exe`. They do not install the add-on or restart the active NVDA.

## Publication privacy

Run `python tools/audit_privacy.py` before a commit or release. It scans source and generated archives recursively for the current account/machine identifiers and common credential formats. It does not upload any scan data. Review staged files and commit author metadata too. Do not commit raw research logs, local profiles, fixture paths or authentication helpers. Automated scanning reduces risk; it cannot prove the absence of every conceivable secret.

## References

Development guidance: [denis-skripnik/nvda-skill](https://github.com/denis-skripnik/nvda-skill) and [web3blind/coding-skill](https://github.com/web3blind/coding-skill). Installed-runtime APIs are checked against [NV Access source](https://github.com/nvaccess/nvda/tree/release-2026.2), not assumed stable across versions.
