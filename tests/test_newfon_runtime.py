"""Opt-in real upstream Newfon test; never discovers or installs live add-ons.

Set BOOK_AUDIO_NEWFON_FIXTURE to the staging.json from a validated official
release extraction, and BOOK_AUDIO_NEWFON_JOBS to an isolated scratch directory.
Artifacts and exact protocol/diagnostics survive failures there. FFmpeg is only
an independent decoder and is copied locally before child execution.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/bookAudio'
PYTHON = PLUGIN / 'runtime/python.exe'
NVDA = Path(os.environ.get('BOOK_AUDIO_TEST_NVDA', 'C:/Program Files/NVDA'))
FIXTURE = os.environ.get('BOOK_AUDIO_NEWFON_FIXTURE')
JOBS = os.environ.get('BOOK_AUDIO_NEWFON_JOBS')


@unittest.skipUnless(FIXTURE and JOBS and Path(FIXTURE).is_file(),
                     'Opt-in: validated Newfon staging fixture and scratch jobs required')
class NewfonRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(Path(FIXTURE).read_text(encoding='utf-8'))
        self.stage = Path(self.fixture['stage']).resolve()
        self.assertTrue((self.stage / 'manifest.ini').is_file())
        self.assertEqual(hashlib.sha256(Path(self.fixture['package']).read_bytes()).hexdigest(),
                         self.fixture['sha256'])
        self.assertTrue(PYTHON.is_file())
        self.job = Path(JOBS) / (self._testMethodName + '-' + uuid.uuid4().hex[:8])
        self.job.mkdir(parents=True)
        self.old_temp = tempfile.tempdir
        self.old_env = {key: os.environ.get(key) for key in ('TMPDIR', 'TMP', 'TEMP')}
        tempfile.tempdir = str(self.job)
        for key in self.old_env:
            os.environ[key] = str(self.job)
        self.addCleanup(self.restore_temp)

    def restore_temp(self):
        tempfile.tempdir = self.old_temp
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def request(self, action, **kwargs):
        request = dict(nvda=str(NVDA), addons=[str(self.stage)], driver='newfon',
                       action=action, voice='0', rate=50, language='ru')
        request.update(kwargs)
        return request

    def run_worker(self, action, **kwargs):
        directory = self.job / (action + '-' + uuid.uuid4().hex[:6])
        directory.mkdir()
        request = self.request(action, config=str(directory), **kwargs)
        path = directory / 'request.json'
        path.write_text(json.dumps(request), encoding='utf-8')
        worker = PLUGIN / 'worker.py'
        record = dict(request=request, worker_sha256_before=hashlib.sha256(worker.read_bytes()).hexdigest(),
                      python=str(PYTHON), command=[str(PYTHON), '-u', str(worker), str(path)])
        started = time.monotonic()
        try:
            result = subprocess.run(record['command'], capture_output=True, timeout=45,
                                    env=dict(os.environ, PYTHONIOENCODING='utf-8'))
            record.update(returncode=result.returncode, stdout=result.stdout.decode('utf-8', 'replace'),
                          stderr=result.stderr.decode('utf-8', 'replace'))
        except subprocess.TimeoutExpired as error:
            record.update(timeout=True, stdout=(error.stdout or b'').decode('utf-8', 'replace'),
                          stderr=(error.stderr or b'').decode('utf-8', 'replace'))
        record.update(elapsed_seconds=time.monotonic()-started,
                      worker_sha256_after=hashlib.sha256(worker.read_bytes()).hexdigest())
        (directory / 'result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        self.assertEqual(record.get('returncode'), 0, json.dumps(record, ensure_ascii=True))
        events = [json.loads(line) for line in record['stdout'].splitlines() if line.startswith('{')]
        self.assertTrue(events)
        self.assertNotEqual(events[-1]['type'], 'error', events[-1])
        return events

    def decode(self, mp3):
        ffmpeg = shutil.which('ffmpeg')
        self.assertIsNotNone(ffmpeg, 'Independent FFmpeg verification is required')
        local = self.job / 'ffmpeg.exe'
        if not local.exists():
            shutil.copy2(ffmpeg, local)
        result = subprocess.run([str(local), '-v', 'error', '-i', str(mp3), '-f', 's16le', '-'],
                                capture_output=True, timeout=20)
        record = dict(mp3=str(mp3), mp3_bytes=mp3.stat().st_size,
                      mp3_sha256=hashlib.sha256(mp3.read_bytes()).hexdigest(),
                      decoder_source=ffmpeg, decoder=str(local), returncode=result.returncode,
                      stderr=result.stderr.decode('utf-8', 'replace'), decoded_bytes=len(result.stdout),
                      decoded_nonzero=any(result.stdout), decoded_sha256=hashlib.sha256(result.stdout).hexdigest())
        mp3.with_suffix('.decode.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        self.assertEqual(result.returncode, 0, record)
        self.assertGreater(len(result.stdout), 10000)
        self.assertTrue(any(result.stdout))

    def test_voices(self):
        event = self.run_worker('voices')[-1]
        self.assertEqual(event['type'], 'voices')
        self.assertEqual([v['id'] for v in event['voices']], ['0', '1', '2', '3'])

    def test_render_two_voices_and_decode(self):
        for voice in ('0', '1'):
            with self.subTest(voice=voice):
                wav = self.job / ('voice-' + voice + '.wav')
                events = self.run_worker('render', voice=voice,
                                         text='Проверка создания аудиокниги. Это настоящий синтез речи.',
                                         wav=str(wav), mp3=str(wav.with_suffix('.mp3')))
                self.assertEqual(events[-1]['type'], 'rendered')
                with wave.open(str(wav)) as audio:
                    record = dict(frames=audio.getnframes(), rate=audio.getframerate(),
                                  channels=audio.getnchannels(), width=audio.getsampwidth())
                    pcm = audio.readframes(audio.getnframes())
                wav.with_suffix('.pcm.json').write_text(json.dumps(record), encoding='utf-8')
                self.assertGreater(record['frames'], 1000)
                self.assertTrue(any(pcm))
                self.assertEqual(record['frames'], events[-1]['frames'])
                self.decode(wav.with_suffix('.mp3'))

    def test_multichapter_conversion(self):
        source = self.job / 'two-chapters.txt'
        source.write_text('Глава 1\nПервая часть книги.\nГлава 2\nВторая часть книги.', encoding='utf-8')
        events = self.run_worker('convert', files=[str(source)], output=str(self.job), separator='Глава')
        self.assertEqual(events[-1], {'type': 'done', 'count': 2})
        saved = [Path(e['output']) for e in events if e['type'] == 'saved']
        self.assertEqual(len(saved), 2)
        self.assertEqual([p.name[:3] for p in saved], ['001', '002'])
        self.assertEqual(len(list(self.job.rglob('*.mp3'))), 2)
        for mp3 in saved:
            self.decode(mp3)

    def test_worker_client_cancellation(self):
        sys.path.insert(0, str(PLUGIN))
        self.addCleanup(lambda: sys.path.remove(str(PLUGIN)))
        spec = importlib.util.spec_from_file_location('newfon_test_client', PLUGIN / 'client.py')
        client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client)
        source = self.job / 'long.txt'
        source.write_text('Длинная книга для проверки остановки. ' * 10000, encoding='utf-8')
        runner = client.WorkerClient(python=PYTHON)
        events = []
        def on_event(event):
            events.append(event)
            # A heartbeat means render has started; chapter only means queued.
            if event['type'] == 'heartbeat':
                runner.cancel()
        started = time.monotonic()
        error = None
        request = self.request('convert', files=[str(source)], output=str(self.job), separator='')
        worker_hash = hashlib.sha256((PLUGIN / 'worker.py').read_bytes()).hexdigest()
        try:
            runner.run(request, on_event)
        except Exception as caught:
            error = caught
        (self.job / 'cancel.json').write_text(json.dumps(dict(events=events, request=request,
            worker_sha256_before=worker_hash,
            worker_sha256_after=hashlib.sha256((PLUGIN / 'worker.py').read_bytes()).hexdigest(),
            exception=type(error).__name__,
            message=str(error), elapsed_seconds=time.monotonic()-started,
            process_cleared=runner._process is None), indent=2), encoding='utf-8')
        self.assertIsInstance(error, client.Cancelled)
        self.assertTrue(any(e['type'] == 'heartbeat' for e in events))
        self.assertIsNone(runner._process)
        self.assertFalse(list(self.job.rglob('*.part')))
        self.assertFalse(list(self.job.rglob('*.mp3')))


if __name__ == '__main__':
    unittest.main()
