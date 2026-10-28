# Book Audio 0.1.4 — Preview

## NVDA 2026.3 voice-loading fix

Book Audio 0.1.2 and 0.1.3 could fail before loading any synthesizer on NVDA 2026.3, reporting that `runtime/pyphenDictionaries` could not be found. The frozen NVDA Pyphen module resolved its dictionary directory relative to Book Audio's private Python executable instead of NVDA.

The worker now preloads that optional resource-dependent module against the NVDA executable directory and immediately restores the actual worker executable, including on import failure. It uses NVDA's existing dictionaries; it does not create empty replacement dictionaries or require users to copy files into the add-on.

## Verification and compatibility

- Reproduced the exact error with the published 0.1.2 archive and an isolated extraction of the official NVDA 2026.3 installer.
- Confirmed the affected worker code was identical in 0.1.2 and 0.1.3.
- Passed 83 unit/integration tests on NVDA 2026.2 and again on NVDA 2026.3, including real voice discovery, PCM/MP3 output and independent decoding for the available test drivers.
- Passed native background conversion, voice-check, focus, close, language, menu, gesture and extracted-distribution checks on both NVDA versions.
- Kept the minimum supported NVDA version at 2026.2 and updated the last-tested version to 2026.3. Earlier NVDA/Python architectures remain unsupported by this build.

The shorter report "could not load" without a complete error message is not sufficient to establish that every user's failure has this same cause. Other third-party driver problems may need separate diagnostics.

Background conversion introduced in 0.1.3 remains included: closing the window during book creation hides it without cancelling the job; reopen with NVDA+Windows+A or through Tools. Exiting/restarting NVDA still stops jobs.

The active NVDA installation/profile was not modified or restarted during verification. Third-party voice packages are not bundled.
