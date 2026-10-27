# Publication validation

The initial 0.1.2 preview was rebuilt after author and documentation changes.

- 79 unit/integration tests passed, with the opt-in staged Newfon fixture enabled.
- 13 native wx recording-verification tests passed.
- Native English/Russian GUI checks passed.
- NVDA AddonBundle accepted the generated manifest, including the author metadata.
- Extracted distribution runtime successfully converted documents and ran voice probes using SAPI5 x64, SAPI5 x86, OneCore, Microsoft Neural Voices and Newfon.
- MP3 output was independently decoded in the real-driver integration suite.
- A recursive local privacy audit of source, distribution and nested archives found no matches for the publishing machine/account identifiers, the separately excluded personal email, or common credential formats. Raw local research logs and profiles were not included.

The scanner is a risk-reduction check, not proof that arbitrary secrets can never exist. Third-party components retain upstream metadata and licenses. No installation into the active NVDA profile, restart, or complete manual screen-reader walkthrough was performed as part of publication. Commercial Vocalizer runtime compatibility remains unverified.
