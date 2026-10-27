"""Real 32-bit host tests; never load the current user's NVDA profile."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import wave
import test_runtime as runtime
import sys
sys.path.insert(0, str(runtime.PLUGIN))

SCRATCH = Path(tempfile.gettempdir())


@unittest.skipUnless(runtime.NVDA.exists() and runtime.PYTHON.exists(), 'NVDA x64 integration')
class BridgeRuntimeTests(unittest.TestCase):
    def test_cancel_terminates_worker_and_its_32bit_host(self):
        import ctypes
        from ctypes import wintypes
        from client import WorkerClient, Cancelled

        class Entry(ctypes.Structure):
            _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                        ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                        ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                        ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                        ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handles = []
        runner = __import__('client').WorkerClient()
        with tempfile.TemporaryDirectory(prefix='bookAudio-cancel32-', dir=SCRATCH) as tmp:
            source = Path(tmp) / 'long.txt'
            source.write_text('A long book for cancellation testing. ' * 10000, encoding='utf-8')
            def on_event(event):
                if event['type'] != 'chapter':
                    return
                snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
                self.assertNotEqual(snapshot, ctypes.c_void_p(-1).value)
                try:
                    entry = Entry()
                    entry.dwSize = ctypes.sizeof(entry)
                    more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
                    while more:
                        if entry.th32ParentProcessID == runner._process.pid:
                            handle = kernel.OpenProcess(0x00100000, False, entry.th32ProcessID)
                            if handle:
                                handles.append(handle)
                        more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
                finally:
                    kernel.CloseHandle(snapshot)
                runner.cancel()
            try:
                with self.assertRaises(Cancelled):
                    runner.run({'nvda': str(runtime.NVDA), 'addons': [], 'driver': 'sapi5_32',
                                'action': 'convert', 'files': [str(source)], 'output': tmp,
                                'separator': '', 'voice': '', 'rate': 50}, on_event)
                self.assertTrue(handles, 'Expected a real 32-bit child host before cancellation')
                for handle in handles:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 3000), 0, '32-bit host survived cancellation')
                self.assertIsNone(runner._process)
                self.assertFalse(list(Path(tmp).rglob('*.part')))
            finally:
                for handle in handles:
                    kernel.CloseHandle(handle)

    def test_brokered_worker_has_clean_shutdown(self):
        with tempfile.TemporaryDirectory(prefix='bookAudio-shutdown32-', dir=SCRATCH) as tmp:
            request = {'nvda': str(runtime.NVDA), 'config': tmp, 'addons': [],
                       'driver': 'sapi5_32', 'action': 'probe', 'voice': '', 'rate': 50}
            path = Path(tmp) / 'request.json'
            path.write_text(json.dumps(request), encoding='utf-8')
            result = subprocess.run([str(runtime.PYTHON), str(runtime.PLUGIN / 'worker.py'), str(path)],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout.decode('utf-8', 'replace'))
            self.assertFalse(result.stderr, result.stderr.decode('utf-8', 'replace'))

    def test_sapi32_mp3_decodes_from_brokered_pcm(self):
        with tempfile.TemporaryDirectory(prefix='bookAudio-bridge-', dir=SCRATCH) as tmp:
            wav = Path(tmp) / 'sapi32.wav'
            events = runtime.RuntimeTests.run_worker(self, 'sapi5_32', 'render', wav)
            self.assertEqual(events[-1]['type'], 'rendered')
            with wave.open(str(wav)) as audio:
                self.assertGreater(audio.getnframes(), 1000)
                self.assertTrue(any(audio.readframes(audio.getnframes())))
            mp3 = wav.with_suffix('.mp3')
            self.assertGreater(mp3.stat().st_size, 1000)
            ffmpeg = shutil.which('ffmpeg')
            self.assertIsNotNone(ffmpeg, 'Independent MP3 decoder required for this integration check')
            verifier = Path(tmp) / 'ffmpeg.exe'
            shutil.copy2(ffmpeg, verifier)
            decoded = subprocess.run([str(verifier), '-v', 'error', '-i', str(mp3), '-f', 's16le', '-'], capture_output=True, timeout=20)
            self.assertEqual(decoded.returncode, 0, decoded.stderr)
            self.assertGreater(len(decoded.stdout), 10000)
            self.assertTrue(any(decoded.stdout))


if __name__ == '__main__':
    tempfile.tempdir = str(SCRATCH)
    unittest.main()
