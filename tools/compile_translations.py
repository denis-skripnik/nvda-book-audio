"""Compile UTF-8 Russian-msgid -> English JSON to standard GNU MO (stdlib only).

Run: python tools/compile_translations.py [source.json] [destination.mo]
With no arguments, compile addon/locale/en/LC_MESSAGES/nvda.json in place.
"""
import argparse
import json
from pathlib import Path
import struct

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / 'addon/locale/en/LC_MESSAGES/nvda.json'


def compile_catalog(source, destination=None):
    source = Path(source)
    destination = Path(destination) if destination else source.with_suffix('.mo')
    messages = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(messages, dict) or not messages:
        raise ValueError('Translation source must be a nonempty JSON object')
    from string import Formatter
    formatter = Formatter()
    def fields(text):
        return sorted((field, spec, conversion) for _, field, spec, conversion in formatter.parse(text)
                      if field is not None)
    for key, value in messages.items():
        if not isinstance(key, str) or not key or not isinstance(value, str) or not value.strip():
            raise ValueError('Every msgid and English translation must be a nonempty string')
        if '\x00' in key or '\x00' in value:
            raise ValueError('NUL characters are not allowed in translation entries')
        if fields(key) != fields(value):
            raise ValueError(f'Translation placeholders differ: {key!r}')
    messages[''] = 'Content-Type: text/plain; charset=UTF-8\nLanguage: en\n'
    entries = sorted((key.encode('utf-8'), value.encode('utf-8')) for key, value in messages.items())
    count = len(entries)
    original_offset = 28 + 16 * count
    originals = b''.join(key + b'\0' for key, _ in entries)
    translated_offset = original_offset + len(originals)
    original_index, translated_index = [], []
    translations = bytearray()
    for key, value in entries:
        original_index.append((len(key), original_offset))
        original_offset += len(key) + 1
        translated_index.append((len(value), translated_offset + len(translations)))
        translations.extend(value + b'\0')
    header = struct.pack('<7I', 0x950412de, 0, count, 28, 28 + count * 8, 0, 0)
    indexes = b''.join(struct.pack('<2I', *entry) for entry in original_index + translated_index)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(header + indexes + originals + translations)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('destination', nargs='?', type=Path)
    args = parser.parse_args()
    print(compile_catalog(args.source, args.destination))


if __name__ == '__main__':
    main()
