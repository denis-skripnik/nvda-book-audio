# Book Audio 0.1.2 — Preview

Create chapter-based MP3 audiobooks from TXT, FB2, FB2.ZIP and text-based PDF using voices installed in NVDA.

## Highlights

- Accessible native dialog under Tools and a reassignable NVDA+Windows+A command.
- Russian/English interface following NVDA's language.
- Per-voice recording verification without selecting an input book or output folder.
- Private synthesis process that does not switch or record the main NVDA voice.
- Brokered 32-bit host capture verified with SAPI5 x86.
- Newfon x64 V2026.10.26 tested with two voices, chapters, cancellation and independently decoded MP3 output.
- Safe ordered file queue, no-overwrite output folders and cancellation preserving completed chapters.

## Requirements and limits

NVDA 2026.2, Windows x64 and Python 3.13 ABI. The package includes its private Python runtime and MP3 encoder; no separate Python or FFmpeg installation is required for use. Voice packages and engines are not included. PDF requires an existing text layer; OCR is not provided. Licensed Vocalizer runtime synthesis remains unverified. Respect each voice's recording and redistribution license.

## Verification

79 unit/integration tests and 13 native recording-check tests passed. The extracted distribution was exercised with SAPI5 x64/x86, OneCore, Microsoft Neural Voices and Newfon. The source tree and nested distribution archives were scanned for publishing-machine/account identifiers and common credential formats. Exported Git source rebuilds the same add-on bytes. This preview has not been automatically installed into the active NVDA profile or subjected to a complete manual screen-reader walkthrough.

## Install

Download `bookAudio-0.1.2.nvda-addon`, open it in NVDA, confirm installation and restart NVDA. `SHA256SUMS` provides the package checksum.

## Author and credits

**Denis Skripnik** — [X](https://x.com/denis_skripnik), [Telegram](https://t.me/blind_dev), [Website](https://blinddev.xyz).

Development guidance: [nvda-skill](https://github.com/denis-skripnik/nvda-skill) and [coding-skill](https://github.com/web3blind/coding-skill). GPL-2.0-or-later; bundled components retain their own licenses and notices.
