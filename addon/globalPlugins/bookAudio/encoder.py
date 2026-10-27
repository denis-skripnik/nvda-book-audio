"""Streaming PCM16 to MP3 using the bundled LAME encoder."""

if __package__:
    from .i18n import _
else:
    from i18n import _
from pathlib import Path
import sys
import wave


def encode_wav(source, destination):
    sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
    import lameenc
    destination = Path(destination)
    partial = destination.with_suffix('.mp3.part')
    try:
        with wave.open(str(source), 'rb') as wav:
            if wav.getsampwidth() != 2:
                raise ValueError(_('Синтезатор выдал не 16-битный PCM; этот формат пока не поддерживается.'))
            if wav.getnchannels() not in (1, 2):
                raise ValueError(_('Поддерживается только моно или стерео.'))
            encoder = lameenc.Encoder()
            encoder.set_bit_rate(128)
            encoder.set_in_sample_rate(wav.getframerate())
            encoder.set_channels(wav.getnchannels())
            encoder.set_quality(2)
            encoder.silence()
            with partial.open('xb') as output:
                while data := wav.readframes(32768):
                    output.write(encoder.encode(data))
                output.write(encoder.flush())
        if destination.exists():
            raise FileExistsError(_('Выходной файл уже существует: {destination}').format(destination=destination))
        # Windows rename is no-clobber, unlike replace.
        partial.rename(destination)
    finally:
        partial.unlink(missing_ok=True)
