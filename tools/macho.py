"""Read-only universal Mach-O, ad-hoc signature and chained-fixup validation.

Adapted from the SIMControl standard-library verifier; no helper handling.
"""
import argparse
import hashlib
import json
import plistlib
import struct
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from dataswitch import require, sha256

PRIVATE_DYLIB = '/System/Library/PrivateFrameworks/ControlCenterUIKit.framework/ControlCenterUIKit'
FRAMEWORKS = ('Foundation', 'UIKit', 'CoreGraphics', 'QuartzCore', 'CoreTelephony', 'CoreFoundation')
ALLOWED_DYLIBS = {PRIVATE_DYLIB, '/usr/lib/libobjc.A.dylib', '/usr/lib/libSystem.B.dylib'} | {
    '/System/Library/Frameworks/' + name + '.framework/' + name for name in FRAMEWORKS
}


def signature(thin, offset, length, require_adhoc=True):
    """Validate SuperBlob, all CodeDirectories and every signed code page."""
    blob = thin[offset:offset + length]
    require(len(blob) == length and length >= 12, 'truncated code signature')
    magic, total, count = struct.unpack_from('>III', blob)
    require(magic == 0xfade0cc0 and 12 + 8*count <= total <= length, 'bad signature SuperBlob')
    slots, occupied = {}, []
    for index in range(count):
        slot, pos = struct.unpack_from('>II', blob, 12 + 8*index)
        require(slot not in slots and 12 + 8*count <= pos <= total - 8, 'bad signature index')
        kind, size = struct.unpack_from('>II', blob, pos)
        require(size >= 8 and pos + size <= total, 'signature blob out of range')
        require(all(pos + size <= a or pos >= b for a, b in occupied), 'overlapping signature blobs')
        occupied.append((pos, pos + size))
        slots[slot] = (kind, blob[pos:pos + size])
    directories = []
    for slot, (kind, cd) in slots.items():
        if slot != 0 and not 0x1000 <= slot <= 0x1005:
            continue
        require(kind == 0xfade0c02 and len(cd) >= 44, 'bad CodeDirectory')
        _, _, version, flags, hashes, ident, special, pages, limit = struct.unpack_from('>9I', cd)
        size, algorithm, _, shift = struct.unpack_from('4B', cd, 36)
        algorithms = {1: ('sha1', 20), 2: ('sha256', 32), 3: ('sha256', 20), 4: ('sha384', 48)}
        require(algorithm in algorithms and size == algorithms[algorithm][1], 'unsupported code hash')
        require(0 < shift <= 16 and limit == offset and limit > 0, 'signature must cover all bytes before LC_CODE_SIGNATURE')
        header_size = 44
        for minimum, needed in ((0x20100, 48), (0x20200, 52), (0x20300, 64),
                                (0x20400, 88), (0x20500, 96), (0x20600, 108)):
            if version >= minimum:
                header_size = needed
        require(len(cd) >= header_size, 'truncated CodeDirectory version')
        if version >= 0x20100:
            require(struct.unpack_from('>I', cd, 44)[0] == 0, 'scatter signatures unsupported')
        if version >= 0x20300:
            require(struct.unpack_from('>Q', cd, 56)[0] in (0, limit), 'unexpected 64-bit code limit')
        page_size = 1 << shift
        require(pages == (limit + page_size - 1)//page_size, 'CodeDirectory page count mismatch')
        require(hashes - special*size >= header_size and hashes + pages*size <= len(cd), 'code hash table out of range')
        require(header_size <= ident < hashes - special*size and b'\0' in cd[ident:hashes - special*size], 'missing signing identifier')
        if require_adhoc:
            require(flags & 2, 'DataSwitch requires an ad-hoc signature')
            if 0x10000 in slots:
                require(slots[0x10000] == (0xfade0b01, struct.pack('>II', 0xfade0b01, 8)), 'ad-hoc signature may contain only an empty CMS placeholder')
        for page in range(pages):
            content = thin[page*page_size:min((page + 1)*page_size, limit)]
            digest = hashlib.new(algorithms[algorithm][0], content).digest()[:size]
            require(digest == cd[hashes + page*size:hashes + (page + 1)*size], 'code page hash mismatch')
        for special_slot in (2, 5, 7):
            if special_slot in slots:
                require(special_slot <= special, 'signature special slot is not hashed')
                digest = hashlib.new(algorithms[algorithm][0], slots[special_slot][1]).digest()[:size]
                require(digest == cd[hashes - special_slot*size:hashes - (special_slot - 1)*size], 'signature special-slot hash mismatch')
        directories.append({'slot': slot, 'identifier': cd[ident:].split(b'\0')[0].decode(),
                            'flags': hex(flags), 'hash_type': algorithm, 'code_pages': pages})
    require(any(item['slot'] == 0 for item in directories), 'missing primary CodeDirectory')
    entitlements = None
    if 5 in slots:
        require(slots[5][0] == 0xfade7171, 'bad XML entitlement blob')
        entitlements = plistlib.loads(slots[5][1][8:])
        require(isinstance(entitlements, dict), 'invalid entitlement dictionary')
    require(not entitlements and 7 not in slots, 'DataSwitch must not request injected/helper entitlements')
    return {'sha256': sha256(blob), 'slots': sorted(slots), 'directories': directories,
            'entitlement_keys': sorted(entitlements or {})}


def chained_formats(thin, offset, length, subtype):
    blob = thin[offset:offset + length]
    require(len(blob) == length and length >= 28, 'truncated chained fixups')
    version, starts, imports, symbols, count, import_format, symbol_format = struct.unpack_from('<7I', blob)
    require(version == 0 and 28 <= starts <= length - 4, 'bad chained fixups header')
    require(0 <= imports <= length and 0 <= symbols <= length and symbol_format == 0, 'bad chained data offsets')
    widths = {1: 4, 2: 8, 3: 16}
    require(import_format in widths and imports + count*widths[import_format] <= length, 'bad chained imports table')
    segments = struct.unpack_from('<I', blob, starts)[0]
    require(starts + 4 + 4*segments <= length, 'bad chained segment table')
    formats = set()
    for index in range(segments):
        relative = struct.unpack_from('<I', blob, starts + 4 + 4*index)[0]
        if not relative:
            continue
        pos = starts + relative
        require(starts + 4 + 4*segments <= pos <= length - 22, 'bad chained segment offset')
        size, page_size, pointer_format, _, _, pages = struct.unpack_from('<IHHQIH', blob, pos)
        require(22 + 2*pages <= size and pos + size <= length, 'bad chained page table')
        require(page_size in (4096, 16384), 'unsupported chained page size')
        allowed = {1, 9, 12} if subtype == 0x80000002 else {2, 6}
        require(pointer_format in allowed, f'unsupported iOS 16/17 chained pointer format {pointer_format}')
        formats.add(pointer_format)
    require(formats, 'empty chained fixups')
    return {'formats': sorted(formats), 'import_format': import_format, 'imports': count}


def macho(data, module=True):
    """Validate the universal DataSwitch executable without executing it."""
    require(module, 'only the independent DataSwitch module is supported')
    require(data[:4] == b'\xca\xfe\xba\xbe' and len(data) >= 8, 'DataSwitch must be a universal Mach-O')
    count = struct.unpack_from('>I', data, 4)[0]
    require(count == 2 and 8 + 20*count <= len(data), 'module needs exactly two fat slices')
    slices = [struct.unpack_from('>IIIII', data, 8 + 20*i) for i in range(count)]
    require({item[1] for item in slices} == {0, 0x80000002}, 'module needs arm64 and arm64e ABI-v2 (0x80000002)')
    result, occupied = [], []
    for cpu, subtype, offset, size, alignment in slices:
        require(cpu == 0x100000c and subtype in (0, 0x80000002), 'unsupported CPU subtype')
        require(0 <= alignment <= 20 and offset % (1 << alignment) == 0, 'bad fat alignment')
        require(size >= 32 and 8 + 20*count <= offset <= len(data) - size, 'slice outside file/header overlap')
        require(all(offset + size <= a or offset >= b for a, b in occupied), 'overlapping fat slices')
        occupied.append((offset, offset + size))
        thin = data[offset:offset + size]
        require(thin[:4] == b'\xcf\xfa\xed\xfe', 'expected little-endian 64-bit Mach-O')
        _, tcpu, tsub, kind, ncmds, cmdsize, _, _ = struct.unpack_from('<8I', thin)
        require((tcpu, tsub) == (cpu, subtype), 'fat/thin CPU subtype mismatch')
        require(kind == 6, 'DataSwitch must be MH_DYLIB')
        require(0 < ncmds <= cmdsize//8 and 32 + cmdsize <= size, 'invalid load command table')
        pos, loads, commands, builds, install_names = 32, [], {}, [], []
        for _ in range(ncmds):
            require(pos + 8 <= 32 + cmdsize, 'truncated load command')
            cmd, length = struct.unpack_from('<II', thin, pos)
            require(length >= 8 and length % 8 == 0 and pos + length <= 32 + cmdsize, 'invalid load command length')
            require(cmd not in (0x1c, 0x8000001c), 'DataSwitch must not carry an LC_RPATH (including RootHide paths)')
            if cmd in (0xc, 0xd, 0x80000018, 0x8000001f, 0x20, 0x80000023):
                require(length >= 24, 'truncated dylib load command')
                string_pos = struct.unpack_from('<I', thin, pos + 8)[0]
                require(24 <= string_pos < length, 'invalid dylib path offset')
                raw = thin[pos + string_pos:pos + length]
                require(b'\0' in raw, 'unterminated dylib name')
                path = raw.split(b'\0')[0].decode()
                if cmd == 0xd:
                    install_names.append(path)
                else:
                    loads.append({'command': hex(cmd), 'path': path})
            if cmd in (0x1d, 0x80000034):
                require(cmd not in commands and length == 16, 'duplicate/invalid linkedit command')
                a, b = struct.unpack_from('<II', thin, pos + 8)
                require(a >= 32 + cmdsize and b > 0 and a + b <= size, 'linkedit data outside slice')
                commands[cmd] = (a, b)
            if cmd == 0x32:
                require(length >= 24, 'bad build version')
                platform, minimum, sdk, tools = struct.unpack_from('<4I', thin, pos + 8)
                require(length == 24 + tools*8, 'invalid build tools table')
                require(platform == 2 and minimum == 16 << 16, 'module must target iPhoneOS 16.0')
                builds.append({'platform': platform, 'minimum': '16.0', 'sdk': hex(sdk)})
            pos += length
        require(pos == 32 + cmdsize and len(builds) == 1, 'invalid/missing LC_BUILD_VERSION')
        require(install_names == ['@loader_path/DataSwitch'], 'wrong DataSwitch install name')
        require(any(item['path'] == PRIVATE_DYLIB and item['command'] == '0xc' for item in loads), 'ControlCenterUIKit must be a strong LC_LOAD_DYLIB')
        require(all(item['path'] in ALLOWED_DYLIBS for item in loads), 'unexpected external/hook/backend dylib dependency')
        require(0x1d in commands and 0x80000034 in commands, 'missing code signature/chained fixups')
        signed = signature(thin, *commands[0x1d], require_adhoc=True)
        chained = chained_formats(thin, *commands[0x80000034], subtype)
        result.append({'cpu': hex(cpu), 'subtype': hex(subtype), 'size': size,
                       'build_version': builds[0], 'loads': loads, 'signature': signed,
                       'chained_fixups': chained})
    return {'sha256': sha256(data), 'size': len(data), 'slices': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    args = parser.parse_args()
    print(json.dumps(macho(args.executable.read_bytes()), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
