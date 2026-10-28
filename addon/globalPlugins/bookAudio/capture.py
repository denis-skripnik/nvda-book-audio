"""PCM output adapter, used only in the isolated synthesis process."""

if __package__:
    from .i18n import _
else:
    from i18n import _
import ctypes
from array import array
import sys
import threading
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

        def feed(self, data, size=None, onDone=None):
            if not isinstance(data, bytes):
                data = ctypes.string_at(data, size)
            elif size is not None:
                data = data[:size]
            if data:
                sink.write(self._format, data)
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

        def setVolume(self, *args, **kwargs):
            pass

        def enableTrimmingLeadingSilence(self, *args, **kwargs):
            pass

        def startTrimmingLeadingSilence(self, *args, **kwargs):
            pass

    return FilePlayer
