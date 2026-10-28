# Book Audio 0.1.5 — Preview

## Recording volume

- Add a recording-volume control from 0 to 100 immediately after rate in the dialog and keyboard navigation. The default is 100, preserving the previous output level.
- Apply the selected gain to captured PCM before encoding MP3. Main NVDA speech volume is unchanged, and export does not depend on whether a synthesizer implements its volume through a playback-device API.
- Use the selected volume for voice verification as well as full conversion, and invalidate verification when volume changes.
- Zero intentionally produces muted book files. A voice verification at zero asks for a value above zero rather than incorrectly declaring the voice unsupported.

The NVDA 2026.3 frozen-resource fix and background conversion remain included. This build targets NVDA 2026.2 and 2026.3, Windows x64, Python 3.13. Jobs do not survive exiting/restarting NVDA. Voice packages are not bundled.

Development verification includes signed mono/stereo PCM scaling, unchanged default output, zero-volume conversion, invalid values/formats, and real eSpeak, OneCore and 32-bit SAPI5 output at different volumes. Created MP3 files are independently decoded to confirm the changed level. These checks do not replace listening to every voice or installation in the active NVDA profile.
