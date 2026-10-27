"""Local pre-publication identifier/credential scan, including nested archives."""
import argparse
import io
import json
import os
from pathlib import Path
import re
import tarfile
import zipfile

LIMIT = 200 * 1024 * 1024
CREDENTIAL = re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
STATS = {'files': 0, 'blobs': 0, 'archives': 0}


def scan_blob(label, data, identifiers, depth=0):
    """Return locations/categories, never matching secret values or snippets."""
    STATS['blobs'] += 1
    findings = []
    texts = [data.decode('utf-8', 'ignore'), data.decode('utf-16-le', 'ignore')]
    for value in identifiers:
        if value and any(re.search(r'(?<![\w])' + re.escape(value) + r'(?![\w])', text, re.I) for text in [label, *texts]):
            findings.append({'file': label, 'category': 'local-identifier'})
            break
    if any(CREDENTIAL.search(text) for text in texts):
        findings.append({'file': label, 'category': 'credential-format'})
    suffix = label.lower().split('!')[-1]
    is_zip = suffix.endswith(('.zip', '.whl', '.nvda-addon'))
    is_tar = suffix.endswith(('.tar', '.tar.gz', '.tgz', '.tar.xz'))
    if not (is_zip or is_tar):
        return findings
    STATS['archives'] += 1
    if depth >= 6:
        return findings + [{'file': label, 'category': 'archive-depth-limit'}]
    try:
        if is_zip:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(item.file_size for item in archive.infolist()) > LIMIT:
                    raise ValueError('archive limit')
                for item in archive.infolist():
                    if not item.is_dir():
                        findings.extend(scan_blob(label + '!' + item.filename, archive.read(item), identifiers, depth + 1))
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
                members = archive.getmembers()
                if sum(item.size for item in members if item.isfile()) > LIMIT:
                    raise ValueError('archive limit')
                for item in members:
                    if item.isfile():
                        stream = archive.extractfile(item)
                        if stream is not None:
                            findings.extend(scan_blob(label + '!' + item.name, stream.read(LIMIT + 1), identifiers, depth + 1))
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, tarfile.TarError):
        findings.append({'file': label, 'category': 'archive-scan-error'})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--forbid', action='append', default=[], help='Additional local identifier; not included in output')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    identifiers = [os.environ.get('USERNAME', ''), os.environ.get('COMPUTERNAME', ''), *args.forbid]
    findings = []
    for file in sorted(root.rglob('*')):
        relative = file.relative_to(root)
        if not file.is_file() or any(part in ('.git', '__pycache__') for part in relative.parts):
            continue
        STATS['files'] += 1
        findings.extend(scan_blob(relative.as_posix(), file.read_bytes(), identifiers))
    print(json.dumps(dict(passed=not findings, identifiers_checked=sum(bool(x) for x in identifiers),
                          statistics=STATS, findings=findings), indent=2))
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
