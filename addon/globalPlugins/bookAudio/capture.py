"""PCM output adapter, used only in the isolated synthesis process."""

if __package__:
    from .i18n import _
else:
    from i18n import _
import ctypes
from array import array
from numbers import Real
import sys
import threading
from typing import Optional
import wave


class WaveSink:
    def __init__(self, path, volume=100):
        self.path = str(path)
        if type(volume) is not int or not 0 <= volume <= 100:
            raise ValueError(_('Громкость должна быть целым числом от 0 до 100.'))
        self.volume = volume
        self._wav = None
        self._format = None
        self._lock = threading.RLock()
        self.frames = 0
        self.error = None

    def write(self, fmt, data):
        with self._lock:
            if self._wav is None:
                self._format = fmt
                self._wav = wave.open(self.path, 'wb')
                self._wav.setnchannels(fmt[0])
                self._wav.setframerate(fmt[1])
                self._wav.setsampwidth(fmt[2] // 8)
            if fmt != self._format:
                self.error = _('Драйвер изменил формат звука внутри главы. Выберите другой голос.')
                return
            if self.volume != 100:
                if fmt[2] != 16:
                    self.error = _('Синтезатор выдал не 16-битный PCM; этот формат пока не поддерживается.')
                    return
                if len(data) % (fmt[0] * 2):
                    self.error = _('Драйвер передал неполный аудиокадр.')
                    return
                samples = array('h')
                samples.frombytes(data)
                if sys.byteorder != 'little':
                    samples.byteswap()
                samples = array('h', (int(value * self.volume / 100) for value in samples))
                if sys.byteorder != 'little':
                    samples.byteswap()
                data = samples.tobytes()
            self._wav.writeframesraw(data)
            self.frames += len(data) // (fmt[0] * (fmt[2] // 8))

    def close(self):
        with self._lock:
            if self._wav:
                self._wav.close()
                self._wav = None


def make_player(sink):
    class FilePlayer:
        DEFAULT_DEVICE_KEY = 'default'
        audioDeviceError_static = False

        def __init__(self, channels, samplesPerSec, bitsPerSample, *args, **kwargs):
            self.channels = channels
            self.samplesPerSec = samplesPerSec
            self.bitsPerSample = bitsPerSample
            self._format = (channels, samplesPerSec, bitsPerSample)
            self._gains = (1.0, 1.0)

        def feed(self, data, size=None, onDone=None):
            if not isinstance(data, bytes):
                data = ctypes.string_at(data, size)
            elif size is not None:
                data = data[:size]
            try:
                if not data:
                    return
                if self.bitsPerSample != 16:
                    sink.error = _('Синтезатор выдал не 16-битный PCM; этот формат пока не поддерживается.')
                    return
                if self.channels not in (1, 2):
                    sink.error = _('Поддерживается только моно или стерео.')
                    return
                if len(data) % (self.channels * 2):
                    sink.error = _('Драйвер передал неполный аудиокадр.')
                    return
                # The engine may already have applied driver.volume. Only apply
                # explicit stream gains; untouched players preserve its PCM exactly.
                gains = self._gains
                if gains != (1.0, 1.0):
                    samples = array('h')
                    samples.frombytes(data)
                    if sys.byteorder != 'little':
                        samples.byteswap()
                    samples = array('h', (
                        int(value * gains[index % self.channels])
                        for index, value in enumerate(samples)
                    ))
                    if sys.byteorder != 'little':
                        samples.byteswap()
                    data = samples.tobytes()
                sink.write(self._format, data)
            finally:
                if onDone:
                    onDone()

        def open(self):
            pass

        def close(self):
            pass

        def sync(self):
            pass

        def idle(self):
            pass

        def stop(self):
            pass

        def pause(self, switch):
            pass

        def setVolume(
            self, *, all: Optional[float] = None,
            left: Optional[float] = None, right: Optional[float] = None,
        ):
            if all is None and left is None and right is None:
                raise ValueError('At least one of all, left or right must be specified')
            if all is not None:
                if left is not None or right is not None:
                    raise ValueError('all specified, so left and right must not be specified')
                left = right = all
            for value in (left, right):
                if value is not None and (not isinstance(value, Real) or not 0 <= value <= 1):
                    raise ValueError('Volume must be a finite number between 0 and 1')
            oldLeft, oldRight = self._gains
            self._gains = (
                oldLeft if left is None else left,
                oldRight if right is None else right,
            )

        def enableTrimmingLeadingSilence(self, *args, **kwargs):
            pass

        def startTrimmingLeadingSilence(self, *args, **kwargs):
            pass

    return FilePlayer
