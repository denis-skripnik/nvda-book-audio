# Changelog

## 0.1.7 — Preview

- Add conditional additional comma/sentence pause controls (0–2000 ms, default zero) based on the loaded driver's advertised BreakCommand support. Hide/reset unsupported settings and reject nonzero unsupported requests in the worker.
- Preserve literal text with conservative numeric, abbreviation, initial and punctuation-cluster handling; verify real PCM and multi-chapter MP3 behavior. Requested pause timing remains engine-dependent.
- Persist output folder and synthesis/chapter settings across NVDA restarts in validated, atomic add-on-only preferences, without saving the input queue or resuming jobs.
- Keep long-pause synthesis bounded with an adjusted deadline and heartbeats; handle empty-message voice-loading failures gracefully.

## 0.1.6 — Preview

- Fix clipping-prone recording volume: set native synthesis volume before capture, adopt the driver's initial level, and avoid duplicate gain. Honor per-player volume controls; retain PCM fallback for drivers without native volume.
- Add MP3 bitrate choices 64/96/128/160/192 kbit/s (default 128), including recording verification and invalidation on changes.
- Add a real RyanNeural regression that distinguishes prevented clipping from attenuated clipped peaks, and independently verify actual encoded bitrate.
- Keep punctuation-pause settings unavailable pending driver-specific timing and text-boundary handling; document capability findings and limitations.

## 0.1.5 — Preview

- Add recording volume 0–100 immediately after rate in the dialog and keyboard navigation.
- Apply gain to captured PCM before MP3 encoding, without changing main NVDA speech volume or relying on device-only driver volume controls.
- Include volume in recording verification and invalidate results when it changes. Zero is an intentional mute for conversion; voice checks require a value above zero.
- Retain the NVDA 2026.3 resource fix and background-conversion behavior.

## 0.1.4 — Preview

- Fix voice discovery failing on NVDA 2026.3 with a missing runtime/pyphenDictionaries path. Frozen Pyphen now resolves dictionaries from NVDA during its early import; the worker executable is restored immediately afterward.
- Reproduce the original issue using the published 0.1.2 package and an isolated official NVDA 2026.3 extraction.
- Keep the NVDA 2026.2 minimum; add targeted NVDA 2026.3 voice, PCM and MP3 verification without changing the active NVDA profile.
- Add explicit runtime-resource and selectable NVDA-version test coverage.

## 0.1.3 — Preview

- Keep book conversion running when Escape, Close or the title-bar close button hides the window.
- Reopen the existing job and its live progress through Tools or NVDA+Windows+A.
- Keep hidden completion/failure unobtrusive and focus its saved result when reopened.
- Preserve explicit Stop and cancellation on NVDA exit/add-on unload; no restart persistence is claimed.

## 0.1.2 — Preview

- Add a private recording check for the selected driver, voice and rate.
- Capture brokered audio from the standard NVDA 32-bit synthesizer host; exercise SAPI5 x86 export and cancellation.
- Verify Newfon x64 release V2026.10.26 with two voices, chapter conversion and independent MP3 decoding.
- Add narrowly scoped dependency plumbing for Tiflotecnia Voices without running its global plugin interface. Commercial runtime synthesis is not verified.
- Preserve Russian/English UI, focus behavior, cancellation and the reassignable NVDA+Windows+A command.
- Publish with Denis Skripnik author metadata, English project documentation and a privacy-audited source tree.

This is an initial public preview, not a guarantee for every synthesizer, voice or NVDA version.
