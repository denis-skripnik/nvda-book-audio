# Book Audio 0.1.9 — Preview

## NVDA 2026.3.1rc1 voice-loading compatibility

The published 0.1.8 package fails before enumerating voices on NVDA 2026.3.1rc1. The candidate's frozen PyWinRT modules require `_table.pywinrt` projection data beside the selected NVDA executable. Book Audio's isolated Python host otherwise makes them look beside its own runtime instead. This affects initialization before a particular synthesizer is selected, not just one voice package.

Preload the actual projection namespaces shipped with the selected NVDA while its resource directory is temporarily in scope, alongside the existing optional Pyphen preload. Restore the real worker executable in `finally`, including error paths. No data files are copied, no placeholder resources are created, and neither the main NVDA process nor its settings are modified.

Regression coverage includes loading without Pyphen, executable restoration, actual frozen resources and native voice-choice population across the available eSpeak NG, SAPI5 x64/x86, OneCore, RHVoice and NeuralVoices test drivers. Runtime and final-package checks exercise real audio, not only mocked voice lists. Each driver's available voices and licensing remain dependent on the user's installation.

This preview was tested in isolated configurations with NVDA 2026.2, 2026.3 and 2026.3.1rc1. Each version passed 155 unit/integration tests; five optional tests were skipped because their Newfon fixture or RyanNeural model was unavailable. Native GUI and extracted-package audio checks also passed. The minimum NVDA API remains 2026.2.0 and last-tested API remains 2026.3.0. Existing chapter splitting, annotations and saved settings are unchanged.
