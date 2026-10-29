# Book Audio 0.1.6 — Preview

## Fix synthesis volume before capture

- Apply the selected volume to the synthesizer in the private recording worker, rather than forcing its volume to 100 and attenuating an already synthesized waveform.
- Initialize the control from the chosen driver's default in the isolated worker. Neural Voices and the tested RHVoice default to 50; tested eSpeak, OneCore and SAPI5 default to 100. Do not overwrite a volume the user edits while voices are loading.
- Honor explicit per-player volume commands, including independent stereo channels. Do not apply the requested volume twice. Drivers without native volume retain a PCM fallback; zero intentionally mutes conversion.
- Main NVDA speech settings remain unchanged. Synthesizer percentage scales need not be linear; setting a driver above its normal level can still distort its output.

The overload was reproduced with the locally installed RyanNeural model before MP3 encoding. For the same text, native volume 100 produced 5,520 near-full-scale PCM samples. Native volume 50 produced none. Attenuating the volume-100 waveform afterward preserved 5,520 near-peak plateau samples, demonstrating why the old control could not repair the distortion. The regression test checks for those flattened peaks rather than only a quieter output file. This is evidence for the tested model and phrase, not a guarantee about every Microsoft voice.

## Select MP3 bitrate

Choose 64, 96, 128, 160 or 192 kbit/s after volume. The default remains 128. The selected bitrate is used for book conversion and recording verification; changing it invalidates verification. Lower bitrate reduces size, not existing synthesis distortion.

## Punctuation pauses

This version does not expose punctuation-pause durations. Capability inspection found BreakCommand advertised by the tested eSpeak, OneCore, SAPI5/x64, SAPI5/x86 and Neural Voices drivers, but not the installed RHVoice. Advertising a command is not proof of exact pause timing. A future setting needs explicit semantics (additional versus absolute pause) and tests for abbreviations, numbers, punctuation and unsupported drivers; no add-on file edit currently enables it.

## Verification

Automated tests run in the bundled Python 3.13 with isolated NVDA 2026.2 and 2026.3 configurations. Coverage includes real RyanNeural clipping regression, volume defaults/validation and unsupported-driver fallback, mono/stereo stream gain, pointer-fed PCM and callbacks, actual MP3 bitrate measured independently with ffprobe, native GUI settings/requests and existing background conversion. The final archive is checked with NVDA's parser and its extracted runtime. These checks are not installation into the active NVDA profile or a human listening test.
