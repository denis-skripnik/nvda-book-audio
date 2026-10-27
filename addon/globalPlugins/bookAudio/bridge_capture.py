"""Worker-only NVDA 2026.2 bridge audio routing.

Launcher sequence adapted from NV Access's synthDriverHost32/launcher.py,
Copyright (C) 2025 NV Access Limited, GPL-2.0-or-later with NVDA permissions:
https://github.com/nvaccess/nvda/blob/release-2026.2/copying.txt
Unlike the normal launcher, always broker audio back into our file-only player.
Never imported or installed in the user's NVDA process.
"""
import subprocess


class BridgeCapture:
    def __init__(self):
        from _bridge.clients.synthDriverHost32 import launcher, synthDriver
        from _bridge import base
        self.base = base
        self.original_pipe = base.PipeStream
        base.PipeStream = self.make_pipe_stream
        self.launcher = launcher
        self.proxy_module = synthDriver
        self.original_launcher = launcher.createSynthDriver
        self.original_proxy = synthDriver.createSynthDriver
        self.hosts = []
        launcher.createSynthDriver = self.create_driver
        synthDriver.createSynthDriver = self.create_driver

    def create_driver(self, name, synthDriversPath):
        launcher = self.launcher
        job = launcher.jobObject.Job()
        job.setBasicLimits(launcher.JOB_OBJECT_LIMIT.KILL_ON_JOB_CLOSE)
        process = subprocess.Popen(
            [launcher._hostExe], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        connection = None
        try:
            job.assignProcess(process._handle)
            process._job = job  # Killing the export worker also kills its hosts.
            stream = self.make_pipe_stream(process.stdout, process.stdin)
            service = launcher.NVDAService(process)
            connection = launcher.Connection(stream, service, name='Book Audio synthDriverHost32')
            connection.bgEventLoop(daemon=True)
            # Must happen before constructing the remote driver / its player.
            connection.remoteService.installProxies(service, brokerAudio=True)
            connection.remoteService.registerSynthDriversPath(synthDriversPath)
            driver = connection.remoteService.SynthDriver(name)
            self.hosts.append((process, connection))
            return connection, driver
        except BaseException:
            self._close_host(process, connection)
            raise

    def make_pipe_stream(self, incoming, outgoing):
        # RPyC closes Win32 handles, not the Python descriptors owning them.
        # Both launcher and dependent PCM-feeder pipes need distinct ownership.
        if not hasattr(incoming, 'fileno'):
            return self.original_pipe(incoming, outgoing)
        import _winapi
        import msvcrt
        current = _winapi.GetCurrentProcess()
        read_handle = _winapi.DuplicateHandle(
            current, msvcrt.get_osfhandle(incoming.fileno()), current,
            0, False, _winapi.DUPLICATE_SAME_ACCESS,
        )
        write_handle = None
        try:
            write_handle = _winapi.DuplicateHandle(
                current, msvcrt.get_osfhandle(outgoing.fileno()), current,
                0, False, _winapi.DUPLICATE_SAME_ACCESS,
            )
            stream = self.original_pipe(read_handle, write_handle)
            stream._fileno = incoming.fileno()
            stream._keepalive = (incoming, outgoing)
            return stream
        except BaseException:
            _winapi.CloseHandle(read_handle)
            if write_handle is not None:
                _winapi.CloseHandle(write_handle)
            raise

    @staticmethod
    def _close_host(process, connection):
        # A native driver may be wedged. Never wait indefinitely during cleanup.
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        if connection is not None:
            connection.close()
        for pipe in (process.stdin, process.stdout):
            if pipe is not None and not pipe.closed:
                pipe.close()

    def close(self):
        self.launcher.createSynthDriver = self.original_launcher
        self.proxy_module.createSynthDriver = self.original_proxy
        try:
            for process, connection in reversed(self.hosts):
                self._close_host(process, connection)
        finally:
            self.hosts.clear()
            self.base.PipeStream = self.original_pipe
