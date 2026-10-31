# Book Audio 0.1.8 — Preview

## Structural FB2 chapters

The default Auto mode now splits FB2 and FB2.ZIP using actual `section/title` elements, not a line beginning with the word “Chapter”. An ordinary paragraph such as “Глава поселения встретил гостей” remains within its section. Primary book-title metadata is not mistaken for a chapter. Nested titled sections, prefaces, untitled wrappers, body text between sections, poems and tables retain their reading order without duplicated body paragraphs. Adjacent heading-only blocks are carried into the next substantive track instead of producing heading-only audio files.

Three explicit modes are available; the editable chapter-prefix field is removed:

- **Auto:** structural FB2 headings or available local PDF bookmarks first; if structure is absent, fixed Russian/English numbered heading patterns for any supported format.
- **Book structure:** structural headings/bookmarks when available, otherwise the complete body.
- **One file per book:** a combined output track, including the annotation when enabled.

Auto fallback recognizes number-only heading lines beginning with Глава, Часть, Chapter or Part, with Arabic/Roman numbering and supported Russian/English number words. Matching is case-insensitive, allows indentation and a final period, and requires the complete heading line to fit within 120 characters. It does not treat “Глава поселения” or “Часть людей” as a numbered heading. Saved custom prefixes are ignored, and the old phrase mode is no longer offered in the interface. Plain-text inference remains conservative: arbitrary trailing titles are not guessed. If no reliable boundaries are found, the body remains one track (plus a separate annotation when enabled).

PDF bookmarks split at known page boundaries, not arbitrary positions within a page. Multiple bookmarks on the same page are collapsed predictably; unavailable or unusable bookmarks fall back to text-based detection rather than discarding valid page text. Only PDFs with an existing text layer are supported; OCR is not added.

## FB2 annotation

The primary `description/title-info/annotation` is read by default in FB2 and FB2.ZIP. It becomes the first separate track, except in one-file mode, where it is prepended to the combined book. A checkbox can disable annotation reading. Missing or empty annotations do not create empty files, and `src-title-info` annotations are not duplicated.

The split mode and annotation choice are saved alongside the existing output and speech preferences. An old saved phrase-mode choice falls back to Auto. Voice verification remains independent of book-splitting choices. Existing native volume, bitrate, pause, background-conversion and restart-persistent settings features remain included.

## Safety and verification

The existing XML DTD/entity/external-resource prohibition and ZIP single-FB2, path, encryption, CRC and actual expanded-size checks remain in place. Existing body-text and explicit phrase-splitting utility APIs remain compatible.

Tests reproduce the original false boundary and missing annotation, cover hierarchy/text preservation and preference/UI behavior, and perform real FB2/FB2.ZIP-to-MP3 conversion. Produced MP3 files are independently decoded; disabling annotations, whole-book mode and legacy mode are exercised separately. The final archive is checked with NVDA's parser and its extracted runtime. Any optional external-driver fixture not present in the test environment is reported as skipped rather than treated as passed.
