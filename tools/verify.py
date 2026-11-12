#!/usr/bin/env python3
"""Verify a DataSwitch deb without extraction or payload execution."""
import argparse
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import sys
sys.dont_write_bytecode = True
from dataswitch import (ROOT, DEB, BUNDLE, EXECUTABLE, PROVENANCE, PROVENANCE_INPUT,
                        RESOURCE_PATHS, RESOURCE_SIZES, regular, require, sha256,
                        control_fields, module_plist, provenance)
from macho import macho
from mkdeb import MEMBERS
from resources import manifest, validate_resource


def ar_members(data):
    require(data[:8] == b'!<arch>\n', 'bad ar magic')
    pos, members = 8, {}
    while pos < len(data):
        header = data[pos:pos + 60]
        require(len(header) == 60 and header[58:] == b'`\n', 'bad ar header')
        name = header[:16].decode('ascii').strip()
        require(name in MEMBERS and name not in members, 'unexpected/duplicate deb member')
        require(header[16:28].strip() == b'0' and header[28:34].strip() == b'0' and header[34:40].strip() == b'0', 'ar ownership/mtime must be zero')
        require(header[40:48].strip() == b'100644', 'wrong ar member mode')
        size_text = header[48:58].strip()
        require(size_text.isdigit(), 'invalid ar member size')
        size = int(size_text)
        pos += 60
        require(pos + size <= len(data), 'truncated ar member')
        members[name] = data[pos:pos + size]
        pos += size
        if size % 2:
            require(data[pos:pos + 1] == b'\n', 'invalid ar alignment padding')
            pos += 1
    require(pos == len(data) and tuple(members) == MEMBERS, 'deb must contain exactly three ordered members')
    require(members['debian-binary'] == b'2.0\n', 'invalid deb version')
    return members


def octal(field):
    text = field.rstrip(b'\0 ').lstrip(b' ')
    require(not text or all(c in b'01234567' for c in text), 'USTAR field must be octal, not base-256')
    return int(text or b'0', 8)


def tar_files(compressed):
    require(compressed[:4] == b'\x1f\x8b\x08\x00' and compressed[4:8] == bytes(4), 'gzip must omit timestamp/name/comment metadata')
    raw = gzip.decompress(compressed)
    require(len(raw) % 512 == 0, 'tar must be 512-byte aligned')
    pos = 0
    while True:
        header = raw[pos:pos + 512]
        require(len(header) == 512, 'tar missing end blocks')
        if header == bytes(512):
            require(len(raw) - pos >= 1024 and not any(raw[pos:]), 'tar requires two zero end blocks and zero tail')
            break
        require(header[257:265] == b'ustar\x0000', 'archive must use raw POSIX USTAR')
        require(header[156:157] in (b'0', b'5'), 'PAX/GNU/link/device archive entry forbidden')
        require(not any(header[157:257]) and not any(header[500:512]), 'unexpected tar link/extension data')
        checksum = octal(header[148:156])
        require(sum(header[:148]) + 8*32 + sum(header[156:]) == checksum, 'tar header checksum mismatch')
        require(octal(header[108:116]) == octal(header[116:124]) == 0, 'tar uid/gid must be root')
        require(octal(header[136:148]) == 0, 'tar mtime must be zero')
        size = octal(header[124:136])
        end = pos + 512 + size
        next_pos = pos + 512 + ((size + 511)//512)*512
        require(next_pos <= len(raw) and not any(raw[end:next_pos]), 'invalid tar size/padding')
        if header[156:157] == b'5':
            require(size == 0, 'directory must be empty')
        pos = next_pos
    files, seen = {}, set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
        for entry in tar:
            require(entry.name == '.' or entry.name.startswith('./'), 'tar paths must be relative ./ paths')
            rel = entry.name.removeprefix('./')
            path = PurePosixPath(rel)
            require(not path.is_absolute() and '..' not in path.parts, 'unsafe tar path')
            require(rel not in seen, 'duplicate tar entry')
            seen.add(rel)
            require(entry.uid == entry.gid == 0 and entry.uname == entry.gname == 'root' and not entry.pax_headers, 'unexpected ownership/PAX headers')
            if entry.isdir():
                require(entry.mode == 0o755, 'wrong directory mode')
                continue
            require(entry.isfile() and rel != '.', 'unexpected tar entry type')
            stream = tar.extractfile(entry)
            require(stream is not None, 'unreadable tar file')
            files[rel] = (stream.read(), entry.mode)
    return files


def verify(path):
    data = regular(path)
    members = ar_members(data)
    control = tar_files(members['control.tar.gz'])
    require(set(control) == {'control'} and control['control'][1] == 0o644, 'control archive must have only control; no maintainer scripts')
    fields = control_fields(control['control'][0])
    require(control['control'][0] == regular(ROOT / 'control'), 'packaged control differs from source')
    files = tar_files(members['data.tar.gz'])
    expected = {BUNDLE + '/' + EXECUTABLE, BUNDLE + '/Info.plist'} | set(RESOURCE_PATHS.values())
    require(set(files) in (expected, expected | {PROVENANCE}), 'unexpected/missing payload file (no helper/injection payload allowed)')
    for name, (body, mode) in files.items():
        require(mode == (0o755 if name == BUNDLE + '/' + EXECUTABLE else 0o644), 'wrong payload mode: ' + name)
    info_data = files[BUNDLE + '/Info.plist'][0]
    module_plist(info_data)
    require(info_data == regular(ROOT / 'Resources/Info.plist'), 'packaged Info.plist differs from source')
    hashes = manifest()
    resource_report = {name: validate_resource(name, files[RESOURCE_PATHS[name]][0], hashes) for name in RESOURCE_SIZES}
    provenance_report = provenance(files[PROVENANCE][0]) if PROVENANCE in files else None
    if PROVENANCE_INPUT.exists():
        require(PROVENANCE in files and files[PROVENANCE][0] == regular(PROVENANCE_INPUT), 'present source provenance must be packaged unchanged')
    module_report = macho(files[BUNDLE + '/' + EXECUTABLE][0])
    return {'package': path.name, 'size': len(data), 'sha256': sha256(data),
            'control': fields, 'module': module_report, 'resources': resource_report,
            'provenance': provenance_report, 'payload_files': sorted(files),
            'archive': 'ar / deterministic gzip / raw USTAR', 'runtime_tested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deb', nargs='?', type=Path, default=DEB)
    parser.add_argument('--report', type=Path, default=ROOT / 'dist/package-validation.json')
    args = parser.parse_args()
    report = verify(args.deb)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('VERIFY_OK', args.deb.name, report['size'], report['sha256'])


if __name__ == '__main__':
    main()
