# Book Audio 0.1.7 — Preview

## Conditional additional punctuation pauses

Two controls appear after bitrate only when the loaded driver advertises `BreakCommand`: an additional comma pause and an additional sentence pause, each 0–2000 ms, default zero. Unsupported, unavailable and loading drivers hide the controls; changing to an unsupported driver clears stale values. The recording worker independently validates ranges and support, so unsupported nonzero settings cannot be silently ignored.

Literal punctuation/text is retained. Numeric commas, decimal/version/URL periods, common Russian/English abbreviations and initials receive conservative protection, including spaced Russian abbreviations. Sentence-ending punctuation clusters and closing quotes are handled together. These are heuristics, not complete language understanding; unknown abbreviations, ambiguous sentence endings and chunk boundaries can still need attention. Zero leaves the existing speech sequence unchanged.

Requested milliseconds are native driver commands, not an absolute replacement of built-in punctuation timing. Actual spacing can depend on rate and engine prosody. Real PCM comparisons confirmed added pauses in eSpeak, OneCore, SAPI5 x64/x86 and Neural Voices; the installed RHVoice did not advertise support. On one phrase requesting a 300 ms comma pause and 600 ms sentence pause, total audio increased by approximately 900 ms for OneCore/SAPI5, 700 ms for eSpeak and 600 ms for Neural Voices at rate 50. These measurements are examples, not a timing guarantee for every voice. Long requested pauses extend the bounded synthesis deadline and retain worker heartbeats.

Recording verification exercises punctuation and echoes both settings; mismatched results cannot verify recording. Settings are forwarded to every book chapter. Tests also independently decode multi-chapter MP3 output to confirm longer audio, and check normal recording with unsupported-driver defaults and explicit rejection of nonzero values.

## Durable settings

The output folder, literal chapter separator, chosen available driver/voice, rate, volume, bitrate and supported pauses are saved in add-on-only `bookAudio.json` under NVDA's configuration directory. Restoration respects asynchronous voice loading, native volume defaults and edits made while loading. Missing folders are retained; unavailable saved voices/drivers use available fallbacks. Main NVDA synthesis/settings are not changed or force-saved.

Writes are atomic, bounded and restricted to validated settings. Corrupt/unknown-schema files fall back safely; failed writes do not destroy the previous settings or stop conversion. Settings are flushed on close/start/unload and debounced during edits. The input-file queue and conversion state are not persisted, and jobs do not resume after restarting NVDA.

## Other changes and verification

This build retains native-volume clipping prevention, selectable MP3 bitrate, background conversion and NVDA 2026.3 resource compatibility. It also handles a worker voice-load failure with an empty exception message without leaving the GUI stuck or raising a callback error.

Automated coverage includes both supporting and unsupported real drivers, literal-text preservation, strict pause validation, fresh-process preference reload, native GUI keyboard/focus/lifecycle tests and extracted-package execution under NVDA 2026.2 and 2026.3. These are isolated tests, not installation/restart of the user's main NVDA or a human listening test of every voice.
