# Book Audio 0.1.3 — Preview

## Background book conversion

- Escape, Close and the title-bar close button now hide the window while book conversion continues.
- Reopen through Tools or NVDA+Windows+A to return to the same job and its current progress.
- Completion or failure while hidden does not show the window or steal keyboard focus. Reopening focuses the saved result.
- Use Stop to interrupt conversion. Exiting/restarting NVDA or unloading the add-on still stops the job; jobs do not survive a restart.
- Closing during voice discovery or a short recording check still cancels that disposable operation.

## Verification

79 unit/integration tests and seven new native background-conversion tests passed. The new tests include real hidden-window synthesis producing three MP3 files, all close routes, progress retention, reopening the same job, explicit Stop, hidden errors and add-on unload. Existing recording-check, focus, language, gesture and extracted-package checks passed. Independent review found no blocking issues. A recursive publication privacy scan found no matches for the checked local identifiers or common credential formats.

## Requirements

This preview targets NVDA 2026.2 on Windows x64. See the README and compatibility notes for supported documents and tested synthesizers. Licensed Vocalizer runtime synthesis is not verified.

Download `bookAudio-0.1.3.nvda-addon`, open it in NVDA to update, and restart NVDA. Python and the MP3 encoder are included. `SHA256SUMS` contains the package checksum.

Author: **Denis Skripnik** — [X](https://x.com/denis_skripnik), [Telegram](https://t.me/blind_dev), [Website](https://blinddev.xyz).

Development guidance: [nvda-skill](https://github.com/denis-skripnik/nvda-skill) and [coding-skill](https://github.com/web3blind/coding-skill).
