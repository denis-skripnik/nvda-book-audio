"""Add-on-only preferences, independent of NVDA's main configuration."""
import json
import os
import tempfile
from pathlib import Path


def _normalize(values):
    if not isinstance(values, dict):
        return {}
    result = {}
    for key in ('output', 'separator', 'driver', 'voice'):
        if isinstance(values.get(key), str):
            result[key] = values[key]
    for key, maximum in (('rate', 100), ('volume', 100), ('commaPauseMs', 2000), ('sentencePauseMs', 2000)):
        value = values.get(key)
        if type(value) is int and 0 <= value <= maximum:
            result[key] = value
    value = values.get('bitrate')
    if type(value) is int and value in (64, 96, 128, 160, 192):
        result['bitrate'] = value
    return result


def load_preferences(config_dir) -> dict:
    """Load valid fields from schema 1; unavailable/invalid stores return {}.

    No defaults are imposed: callers retain their own defaults for absent fields.
    """
    try:
        with (Path(config_dir) / 'bookAudio.json').open('rb') as stream:
            payload = stream.read(64 * 1024 + 1)
        if len(payload) > 64 * 1024:
            return {}
        document = json.loads(payload.decode('utf-8'))
        if not isinstance(document, dict):
            return {}
        version = document.get('schemaVersion')
        if type(version) is not int or version != 1:
            return {}
        return _normalize(document.get('settings'))
    except (OSError, ValueError, TypeError, RecursionError):
        return {}


def save_preferences(config_dir, values) -> bool:
    """Atomically replace the entire settings snapshot in an existing config_dir.

    Only whitelisted valid fields are written, within 64 KiB including the wrapper.
    Return False on storage/encoding failure; never save NVDA's configuration.
    """
    partial = None
    try:
        target = Path(config_dir) / 'bookAudio.json'
        payload = json.dumps({'schemaVersion': 1, 'settings': _normalize(values)}, ensure_ascii=False).encode('utf-8')
        if len(payload) > 64 * 1024:
            return False
        with tempfile.NamedTemporaryFile(mode='wb', prefix='bookAudio.', suffix='.tmp',
                                         dir=target.parent, delete=False) as stream:
            partial = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(partial, target)
        partial = None
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if partial is not None:
            try:
                os.unlink(partial)
            except OSError:
                pass
