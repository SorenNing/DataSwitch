#!/usr/bin/env python3
"""Pure-memory parser checks; no compilation, dylib, deb, disk writes or CI."""
import io
import struct
import tarfile
import zlib
import sys
sys.dont_write_bytecode = True
from dataswitch import ROOT, regular, sha256
from check_local import check_inputs, workflow_check
from macho import signature, chained_formats, macho
from package import archive
from resources import png, manifest
from verify import tar_files, ar_members


def rejected(function, label):
    try:
        function()
    except (ValueError, OSError, struct.error, zlib.error):
        return label
    raise AssertionError('malformed input unexpectedly accepted: ' + label)


def main():
    results = []
    text = regular(ROOT / '.github/workflows/build.yml')
    workflow_check(text)
    results.append(rejected(lambda: workflow_check(text.replace(b'  workflow_dispatch:', b'  push:')), 'reject automatic push workflow'))
    results.append(rejected(lambda: workflow_check(text.replace(b'  workflow_dispatch:', b'  workflow_dispatch:\n  schedule:')), 'reject additional workflow trigger'))
    for name, edge in (('DataSwitch.png', 50), ('DataSwitch@2x.png', 100), ('DataSwitch@3x.png', 150)):
        path = ROOT / 'Resources' / name
        if path.exists():
            data = regular(path)
            png(data, edge, True)
            changed = bytearray(data)
            changed[29] ^= 1
            results.append(rejected(lambda: png(bytes(changed), edge, True), 'reject PNG CRC: ' + name))
            results.append(rejected(lambda: png(data, edge + 1, True), 'reject PNG dimensions: ' + name))
    results.append(rejected(lambda: manifest(b'{"schema_version":1}'), 'reject incomplete hash manifest'))
    # A standalone CodeDirectory test blob is not a Mach-O executable.
    code = b'page hash verification test'.ljust(64, b'\0')
    ident = b'com.ning.dataswitch.module\0'
    hashes = 44 + len(ident)
    cd = struct.pack('>9I4BI', 0xfade0c02, hashes + 32, 0x20001, 2,
                     hashes, 44, 0, 1, len(code), 32, 2, 0, 12, 0)
    cd += ident + bytes.fromhex(sha256(code))
    blob = struct.pack('>5I', 0xfade0cc0, 20 + len(cd), 1, 0, 20) + cd
    signed = code + blob
    signature(signed, len(code), len(blob))
    results.append('accept valid isolated CodeDirectory/code-page hashes')
    def with_cms(body):
        cms = struct.pack('>II', 0xfade0b01, 8 + len(body)) + body
        superblob = struct.pack('>7I', 0xfade0cc0, 28 + len(cd) + len(cms), 2, 0, 28, 0x10000, 28 + len(cd)) + cd + cms
        return code + superblob, len(superblob)
    empty, size = with_cms(b'')
    signature(empty, len(code), size)
    results.append('accept Apple ad-hoc empty CMS placeholder')
    nonempty, size = with_cms(b'x')
    results.append(rejected(lambda: signature(nonempty, len(code), size), 'reject nonempty CMS signer for ad-hoc module'))
    changed = bytearray(signed)
    changed[0] ^= 1
    results.append(rejected(lambda: signature(bytes(changed), len(code), len(blob)), 'reject changed signed code page'))
    changed = bytearray(signed)
    struct.pack_into('>I', changed, len(code) + 20 + 12, 0)
    results.append(rejected(lambda: signature(bytes(changed), len(code), len(blob)), 'reject missing ad-hoc flag'))
    for subtype, pointer_format in ((0, 2), (0x80000002, 12)):
        fixup = struct.pack('<7I', 0, 28, 60, 60, 0, 1, 0)
        fixup += struct.pack('<2I', 1, 8)
        fixup += struct.pack('<IHHQIHH', 24, 16384, pointer_format, 0, 0, 1, 0xffff)
        chained_formats(fixup, 0, len(fixup), subtype)
        results.append(rejected(lambda f=fixup, s=subtype: chained_formats(f, 0, len(f), 0 if s else 0x80000002), 'reject chained pointer format for wrong CPU ABI'))
    results.append(rejected(lambda: macho(b'not a Mach-O'), 'reject non-universal module'))
    entries = {'example/note.txt': (b'non-executable archive parser fixture\n', 0o644)}
    first = archive(entries)
    second = archive(entries)
    assert first == second, 'raw USTAR/gzip is not deterministic'
    assert tar_files(first) == entries
    results.append('accept deterministic in-memory raw USTAR/gzip round-trip')
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.PAX_FORMAT) as tar:
        entry = tarfile.TarInfo('a'*110)
        entry.size = 1
        tar.addfile(entry, io.BytesIO(b'x'))
    results.append(rejected(lambda: tar_files(__import__('gzip').compress(buffer.getvalue(), mtime=0)), 'reject PAX extension archive'))
    results.append(rejected(lambda: ar_members(b'!<arch>\n'), 'reject empty Debian container'))
    results.append(rejected(lambda: ar_members(b'!<arch>\nshort'), 'reject truncated ar member header'))
    print('SELFTEST_OK', len(results))
    for result in results:
        print('-', result)
    print('No compiler/toolchain/CI invocation; no dylib/deb/output files written.')


if __name__ == '__main__':
    main()
