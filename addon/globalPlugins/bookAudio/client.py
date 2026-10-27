"""Cancellable process protocol. This module never imports a synthesis driver."""

if __package__:
    from .i18n import _
else:
    from i18n import _
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent


class Cancelled(Exception):
    pass


class WorkerClient:
    def __init__(self, python=None):
        self.python = Path(python) if python else HERE / 'runtime/python.exe'
        self.cancelled = threading.Event()
        self._process = None
        self._lock = threading.Lock()

    def cancel(self):
        self.cancelled.set()
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()

    def run(self, request, on_event):
        if not self.python.is_file():
            raise RuntimeError(_('В пакете отсутствует среда синтеза Python.'))
        request = dict(request)
        current_output = None
        last_event = None
        timed_out = threading.Event()
        finished = threading.Event()
        heartbeat = [time.monotonic()]
        with tempfile.TemporaryDirectory(prefix='bookAudio-') as temp:
            request['config'] = temp
            path = Path(temp) / 'request.json'
            path.write_text(json.dumps(request, ensure_ascii=True), encoding='utf-8')
            log_path = Path(temp) / 'worker.log'
            with log_path.open('wb') as log:
                if self.cancelled.is_set():
                    raise Cancelled()
                with self._lock:
                    if self.cancelled.is_set():
                        raise Cancelled()
                    self._process = subprocess.Popen(
                        [str(self.python), '-u', str(HERE / 'worker.py'), str(path)],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                        env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                    )
                    process = self._process

                def watchdog():
                    while not finished.wait(1):
                        if time.monotonic() - heartbeat[0] > 240:
                            timed_out.set()
                            if process.poll() is None:
                                process.terminate()
                            return
                threading.Thread(target=watchdog, daemon=True).start()
                try:
                    for line in process.stdout:
                        try:
                            event = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        if not isinstance(event, dict) or 'type' not in event:
                            continue
                        heartbeat[0] = time.monotonic()
                        last_event = event
                        if event['type'] == 'chapter':
                            current_output = event['output']
                        on_event(event)
                        if event['type'] == 'error' and process.poll() is None:
                            # A partially initialized driver can leave non-daemon
                            # threads alive even after the worker reports failure.
                            process.terminate()
                    code = process.wait(timeout=10)
                finally:
                    finished.set()
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=10)
                    process.stdout.close()
                    with self._lock:
                        self._process = None
                    if current_output:
                        Path(current_output).with_suffix('.mp3.part').unlink(missing_ok=True)
            if self.cancelled.is_set():
                raise Cancelled()
            if timed_out.is_set():
                raise RuntimeError(_('Процесс синтеза не отвечает более 4 минут.'))
            if last_event and last_event['type'] == 'error':
                raise RuntimeError(last_event.get('message', _('Ошибка синтеза.')))
            if code != 0 or not last_event or last_event['type'] not in ('voices', 'done', 'rendered', 'compatibility'):
                diagnostics = log_path.read_text(encoding='utf-8', errors='replace')[-2000:]
                raise RuntimeError(_('Процесс синтеза завершился с кодом {code}. {diagnostics}').format(code=code, diagnostics=diagnostics))
            return last_event
