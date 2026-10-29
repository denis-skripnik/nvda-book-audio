# Book Audio

An accessible NVDA add-on for turning books into MP3 audiobooks.

**Author:** Denis Skripnik — [X](https://x.com/denis_skripnik) · [Telegram](https://t.me/blind_dev) · [Website](https://blinddev.xyz).

[Download the latest release](https://github.com/denis-skripnik/nvda-book-audio/releases) · [Russian documentation](README.ru.md) · [Compatibility notes](docs/COMPATIBILITY.md)

Current version: **0.1.7 (preview)**.

Turn TXT, FB2, FB2.ZIP and text-based PDF documents into chapter MP3 files using synthesizers and voices installed in NVDA. This build targets **NVDA 2026.2 or 2026.3, Windows x64, Python 3.13**. Python and MP3 encoding are included; no separate Python or FFmpeg installation is required.

## Open and configure

Install `bookAudio-0.1.7.nvda-addon` and restart NVDA. Open **NVDA → Tools → Book Audio — Text to MP3**, or press **NVDA+Windows+A**. Reassign this command in **Preferences → Input gestures**, under **Book Audio**, command **Open the Book Audio window**. User gesture mappings are handled by NVDA, not stored by this add-on.

The interface follows NVDA's language: Russian for Russian NVDA, English for English and other NVDA languages. Restart NVDA after changing its interface language. The add-on's internal identifier remains `bookAudio`, so this version updates the previous installation rather than creating a duplicate add-on.

1. Choose **Add files**. You can select multiple files at once or press this button repeatedly to append files in order. Duplicate paths are ignored; remove unwanted files from the queue.
2. Choose an existing output folder.
3. Enter a chapter separator such as `Chapter`. The phrase is literal, case-insensitive and matched at the beginning of a line. Headings remain in the spoken text. Text before the first heading becomes a separate preface. An empty separator or no matches produces one MP3 for the entire document.
4. Select a synthesizer driver, wait for its voices and select a voice. Focus stays on the driver selector while voices load; if you move to another field, loading does not steal focus back. Changing drivers again cancels the obsolete request and discards late results.
5. Set the **NVDA rate**, from 0 to 100. This is the driver's NVDA percentage scale, not words per minute. Rate boost is not enabled.
6. Set **Volume** from 0 to 100, immediately after rate. The initial value comes from the selected driver in the private worker (for example, 50 for Neural Voices and RHVoice); it is not forced to 100. Volume is applied through the synthesizer before capture, without a second copy of the same gain. Player-based volume controls are honored; drivers without native volume use a PCM fallback. Main NVDA speech settings remain unchanged. Different drivers can have different, nonlinear volume scales. Zero produces muted files; voice verification requires a positive value. Settings cannot be changed during an active job.
7. Select the **MP3 bitrate**: 64, 96, 128, 160 or 192 kbit/s. The default remains 128. A lower bitrate reduces file size, but does not repair distortion already present in synthesis.
8. If the selected driver advertises native pause commands, two additional controls appear after bitrate: **additional comma pause** and **additional sentence pause**, each 0–2000 ms, default 0. Zero leaves that category unchanged. These are requested extra pauses, not an exact replacement of engine punctuation timing; speech rate and engine prosody can affect the measured gap. Numbers, common abbreviations and initials are conservatively protected, but text-boundary handling is heuristic, not complete language understanding. Unsupported drivers hide these fields and discard stale values.
9. Optionally choose **Verify recording**. The selected voice synthesizes a short phrase privately; the check requires nonempty, non-silent PCM and successful MP3 encoding. Nothing is played through the speakers and no test output is saved with your books. No input document or output folder is required. Changing driver, voice, rate, volume, bitrate or pause settings invalidates the result. The check can be stopped. Success applies to those settings and a short phrase, not every voice or book.
10. Choose **Start**. **Status** reports the current book and chapter. When conversion finishes with the window visible, focus moves to this read-only field so NVDA can read the result.

Use Tab, arrow keys, Enter/Space and the labelled Alt shortcuts. **Stop** cancels the job and preserves finished MP3s. **Escape**, **Close** and the window close button hide the window while book conversion continues in the background. Reopen it through Tools or NVDA+Windows+A to see the same job and its current status. Completion or failure while hidden does not pop up the window or steal focus; reopening focuses the saved result. Use **Stop** to interrupt a book. Exiting/restarting NVDA or unloading the add-on stops the job; jobs do not survive a restart. Voice discovery and short recording checks are still cancelled when their window closes. A repeated open gesture raises the existing window instead of opening a duplicate.

## Saved settings

Book Audio remembers the output folder, chapter separator, selected available driver and voice, rate, volume, bitrate and supported pause settings across dialog reopening and NVDA restarts. Preferences are stored separately in `bookAudio.json` inside NVDA's configuration directory; saving them does not change the main synthesizer or force-save unrelated NVDA settings. Missing output folders are retained so an offline drive does not erase your choice; normal output-folder validation still applies before conversion.

This does not save the input-file queue or resume an interrupted conversion after NVDA exits. An unavailable saved driver or voice falls back to an available choice; unsupported pause settings are not applied.

## Output

Each input book gets a new subfolder. Files are numbered, for example `001 - Preface.mp3` and `002 - Chapter 1.mp3`. Existing folders cause a new name such as `Book (2)` to be chosen; completed files are never overwritten. Both extensions are removed from the folder name for `.fb2.zip` input. MP3 is encoded with LAME at the selected target bitrate (default 128 kbit/s); the voice determines sample rate and channel count.

Cancellation or an error stops the queue. Finished chapters remain; incomplete `.mp3.part` files are removed. Empty output folders may remain. Restarting a job starts from the beginning in fresh folders; there is no resume function.

## Supported input and limits

- **TXT:** UTF-8 with or without BOM, UTF-16 with BOM, or Windows-1251. Convert other encodings to UTF-8 first.
- **FB2:** body text, headings, paragraphs, subtitles, poetry and table-cell text. Images and metadata are skipped. XML DTDs and entities are rejected.
- **FB2.ZIP:** exactly one FB2 payload, optionally in a nested folder; image assets may also be present. The document is read in memory without extracting archive members to disk. Multiple/no FB2 files, unsafe paths, encryption, corrupt ZIP/CRC, and invalid XML produce an error. Compressed input and expanded FB2 are each limited to 128 MiB.
- **PDF:** an existing text layer is required. **OCR is not included.** Reading order in complex layouts depends on the PDF. Remove nonempty passwords first; some encryption may need external decryption.
- Each input file is limited to 128 MiB. Temporary WAV data needs additional free space. Split extremely long chapters into smaller parts.

Newfon x64 official release V2026.10.26 was exercised in an isolated staging directory: four voices enumerated, two voices rendered at rate 50, two-chapter conversion and cancellation tested, and MP3 independently decoded. Newfon is not bundled; install its compatible driver separately to use it. Legacy 32-bit Newfon builds were not tested.

Version 0.1.2 captures audio brokered from NVDA's standard 32-bit host. SAPI5 x86 MP3 export and independent decoding have been exercised; cancellation terminates both the worker and its 32-bit child. This does not establish compatibility with all legacy add-ons. Tiflotecnia/Vocalizer still requires a suitable driver, voice data and a valid license; no commercial build has been verified here.

SAPI5 x64, RHVoice, eSpeak NG, Windows OneCore and Microsoft Neural Voices have been exercised with real synthesis. Other drivers must provide PCM through `nvwave` and report speech completion; listing a driver does not guarantee export support. Hardware, network or unusual drivers may be incompatible. Respect each voice provider's recording and redistribution license.

Document reading and MP3 encoding run locally. The add-on has no cloud API, but a selected third-party network driver may transmit text according to its own behavior. A separate worker uses a private temporary configuration; the main NVDA voice, configuration and dictionaries are not changed or captured. No Tools item is registered on the secure desktop.

## Credits

Author: **Denis Skripnik**. Development used [nvda-skill](https://github.com/denis-skripnik/nvda-skill) and [coding-skill](https://github.com/web3blind/coding-skill). See [AUTHORS.md](AUTHORS.md), [development notes](docs/DEVELOPMENT.md) and [third-party notices](addon/THIRD_PARTY.md).

## Validation and development

Tests cover document/archive safety, chapter boundaries, output naming/no overwrite, cancellation, worker shutdown, real drivers and MP3 decoding. Isolated native-wx checks cover focus, rapid driver selection, close during work, menu lifecycle and the default/reassigned gesture. The final archive is validated by NVDA's manifest parser and its extracted runtime is exercised. These checks are distinct from installing/restarting the user's main NVDA and manually reading every control with NVDA.

Sources are in `addon/globalPlugins/bookAudio/`; run `python -m unittest discover -s tests -v`, then the native GUI/gesture checks with `addon/globalPlugins/bookAudio/runtime/python.exe`. `python build.py` compiles the English gettext catalog and builds the add-on. Integration tests require the installed target NVDA and voice packages. The source messages are Russian; English translations are maintained in `addon/locale/en/LC_MESSAGES/nvda.json` and compiled to standard GNU gettext `.mo`.

Add-on code is GPL-2.0-or-later. Bundled component licenses and corresponding encoder sources/build recipes are included; see `THIRD_PARTY.md`. NVDA binaries and voice models are not redistributed in this package.
