#!/usr/bin/env python3
"""Package the independent module with Python raw USTAR/gzip and mkdeb.

--dry-run validates inputs and prints the plan without creating any files.
"""
import argparse
import gzip
import io
import json
from pathlib import PurePosixPath
import tarfile
import tempfile
import sys
sys.dont_write_bytecode = True
from check_local import check_inputs
from dataswitch import (ROOT, DEB, BUNDLE, EXECUTABLE, PROVENANCE, PROVENANCE_INPUT,
                        RESOURCE_PATHS, RESOURCE_SIZES, regular, require,
                        control_fields, module_plist, provenance, sha256)
from macho import macho
from mkdeb import pack
from resources import manifest, validate_resource


def archive(entries):
    """Return deterministic gzip of root-owned raw USTAR (no PAX/AppleDouble)."""
    directories = {'.'}
    for name in entries:
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and '.' not in path.parts, 'unsafe payload path')
        directories.update(str(parent) for parent in path.parents)
    require(not (directories & entries.keys()), 'file/directory collision')
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name in sorted(directories | entries.keys(), key=lambda value: (value != '.', value)):
            info = tarfile.TarInfo('.' if name == '.' else './' + name)
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            info.mtime = 0
            if name in directories:
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            else:
                data, mode = entries[name]
                info.size, info.mode = len(data), mode
                tar.addfile(info, io.BytesIO(data))
    output = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=output, mode='wb', compresslevel=9, mtime=0) as stream:
        stream.write(buffer.getvalue())
    return output.getvalue()


def plan():
    files = {BUNDLE + '/' + EXECUTABLE: {'input': 'build/' + EXECUTABLE, 'mode': '0755'},
             BUNDLE + '/Info.plist': {'input': 'Resources/Info.plist', 'mode': '0644'}}
    for name, destination in RESOURCE_PATHS.items():
        files[destination] = {'input': 'Resources/' + name, 'mode': '0644'}
    if PROVENANCE_INPUT.exists():
        files[PROVENANCE] = {'input': str(PROVENANCE_INPUT.relative_to(ROOT)), 'mode': '0644'}
    return {'output': str(DEB.relative_to(ROOT)), 'control': 'control', 'files': files,
            'archive': 'Python ar / deterministic gzip / raw USTAR',
            'optional_provenance': str(PROVENANCE_INPUT.relative_to(ROOT)),
            'executable_built': False, 'deb_written': False}


def collect():
    report = check_inputs()
    require(report['ready_to_build'], 'input preflight failed; run tools/check_local.py')
    executable = regular(ROOT / 'build' / EXECUTABLE)
    module_report = macho(executable)
    info = regular(ROOT / 'Resources/Info.plist')
    module_plist(info)
    control = regular(ROOT / 'control')
    control_fields(control)
    entries = {BUNDLE + '/' + EXECUTABLE: (executable, 0o755), BUNDLE + '/Info.plist': (info, 0o644)}
    hashes = manifest()
    for name in RESOURCE_SIZES:
        data = regular(ROOT / 'Resources' / name)
        validate_resource(name, data, hashes)
        entries[RESOURCE_PATHS[name]] = (data, 0o644)
    if PROVENANCE_INPUT.exists():
        data = regular(PROVENANCE_INPUT)
        provenance(data)
        entries[PROVENANCE] = (data, 0o644)
    return control, entries, module_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--allow-pending', action='store_true', help='dry-run inventory while source/icons are in progress')
    args = parser.parse_args()
    require(not args.allow_pending or args.dry_run, '--allow-pending requires --dry-run')
    if args.dry_run:
        report = check_inputs(args.allow_pending)
        output = plan()
        output.update({'dry_run': True, 'inputs_passed': report['passed'],
                       'ready_to_build': report['ready_to_build'],
                       'issues': [item for item in report['checks'] if item['status'] != 'ok']})
        print(json.dumps(output, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report['passed'] else 1)
    control, entries, module_report = collect()
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='deb-members-', dir=ROOT / 'build') as temporary:
        from pathlib import Path
        members = Path(temporary)
        (members / 'debian-binary').write_bytes(b'2.0\n')
        (members / 'control.tar.gz').write_bytes(archive({'control': (control, 0o644)}))
        (members / 'data.tar.gz').write_bytes(archive(entries))
        pack(DEB, members, epoch=0)
    print(json.dumps({'package': str(DEB), 'size': DEB.stat().st_size,
                      'sha256': sha256(DEB.read_bytes()), 'module': module_report}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
