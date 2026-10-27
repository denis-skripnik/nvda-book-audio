# Synthesizer compatibility

Target: NVDA 2026.2, Windows x64, Python 3.13. Other targets are not claimed supported.

| Driver | Verification |
|---|---|
| SAPI5 x64 | Real synthesis, PCM capture and MP3 export |
| SAPI5 x86 | Real brokered PCM, independently decoded MP3 and child-process cancellation |
| RHVoice | Real synthesis and independently decoded MP3 |
| eSpeak NG | Real synthesis and private recording check |
| Windows OneCore | Real synthesis and independently decoded MP3 |
| Microsoft Neural Voices (tested installed implementation) | Real synthesis and independently decoded MP3 |
| Newfon x64 V2026.10.26 | Four voices enumerated; voices 0 and 1 rendered at rate 50; two chapters, cancellation and independent MP3 decoding |
| Tiflotecnia Voices | Import dependency adapter covered by fixture tests; licensed engine, voice enumeration and audio export NOT verified |
| Other Vocalizer variants, SAPI4, Eloquence, IBMTTS, Acapela | No runtime compatibility claim |

The driver appearing in NVDA does not establish recording support. Use **Verify recording** for the selected settings. A short probe checks non-silent PCM, completion and MP3 encoding; it cannot establish intelligibility, every book/setting, or legal redistribution rights.

Newfon and commercial engines/voices are not bundled. Recording and distribution rights depend on each engine/voice license.

## Technical references

- [NVDA skill](https://github.com/denis-skripnik/nvda-skill)
- [NVDA 2026.2 host launcher](https://github.com/nvaccess/nvda/blob/release-2026.2/source/_bridge/clients/synthDriverHost32/launcher.py)
- [Newfon release used for verification](https://github.com/nikkov199525/newfon/releases/tag/V2026.10.26)
- [Tiflotecnia Voices source](https://github.com/ruifontes/tiflotecniaVoices)

## Verification boundaries

Automated checks exercise isolated processes and native wx windows, not installation into the active NVDA profile or a complete manual screen-reader walkthrough. Raw machine-specific research logs are deliberately excluded from the repository.
