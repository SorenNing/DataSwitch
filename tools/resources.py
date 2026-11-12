#!/usr/bin/env python3
"""Check PNG inputs and explicitly freeze approved resource SHA-256 values."""
import argparse
import json
import struct
import zlib
import sys
sys.dont_write_bytecode = True
from dataswitch import (PACKAGE, VERSION, ROOT, RESOURCE_SIZES, RESOURCE_MANIFEST,
                        regular, require, sha256)


def png(data, expected_size, glyph=False):
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG')
    pos, chunks, image, palette, transparency = 8, [], bytearray(), None, None
    ihdr = None
    while pos < len(data):
        require(pos + 12 <= len(data), 'truncated PNG chunk')
        length = struct.unpack_from('>I', data, pos)[0]
        tag = data[pos + 4:pos + 8]
        require(pos + 12 + length <= len(data), 'PNG chunk outside file')
        body = data[pos + 8:pos + 8 + length]
        crc = struct.unpack_from('>I', data, pos + 8 + length)[0]
        require(zlib.crc32(tag + body) & 0xffffffff == crc, 'PNG chunk CRC mismatch')
        require(chunks or tag == b'IHDR', 'IHDR must be first')
        require(tag not in (b'IHDR', b'PLTE', b'tRNS', b'IEND') or tag not in chunks, 'duplicate PNG singleton chunk')
        require(tag in (b'IHDR', b'PLTE', b'IDAT', b'IEND') or tag[0] & 32, 'unknown critical PNG chunk')
        if tag == b'IHDR':
            require(length == 13, 'invalid IHDR')
            ihdr = struct.unpack('>IIBBBBB', body)
        elif tag == b'PLTE':
            require(b'IDAT' not in chunks and length and length % 3 == 0 and length <= 768, 'invalid PNG palette')
            palette = body
        elif tag == b'tRNS':
            require(b'IDAT' not in chunks, 'late PNG transparency')
            transparency = body
        elif tag == b'IDAT':
            require(b'IDAT' not in chunks or chunks[-1] == b'IDAT', 'non-contiguous IDAT')
            image.extend(body)
        elif tag == b'IEND':
            require(length == 0 and pos + 12 == len(data), 'invalid IEND/trailing PNG bytes')
        chunks.append(tag)
        pos += 12 + length
    require(chunks[-1:] == [b'IEND'] and image and ihdr, 'incomplete PNG')
    width, height, bits, color, compression, filtering, interlace = ihdr
    require(width == height == expected_size, f'PNG must be {expected_size}x{expected_size}, got {width}x{height}')
    require(bits == 8 and color in (0, 2, 3, 4, 6), 'icons must be 8-bit PNG')
    require(compression == filtering == interlace == 0, 'icons must be non-interlaced standard PNG')
    if color == 3:
        require(palette is not None, 'indexed PNG requires palette')
    if transparency is not None:
        require(color in (0, 2, 3), 'invalid tRNS color type')
        expected = {0: 2, 2: 6}.get(color)
        require(len(transparency) == expected if expected else 0 < len(transparency) <= len(palette)//3, 'invalid tRNS length')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    stride = width * channels
    decoder = zlib.decompressobj()
    expected_bytes = (stride + 1) * height
    raw = decoder.decompress(bytes(image), expected_bytes + 1)
    require(len(raw) == expected_bytes and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail, 'invalid PNG compressed scanlines')
    require(all(raw[row*(stride + 1)] <= 4 for row in range(height)), 'unknown PNG scanline filter')
    report = {'width': width, 'height': height, 'bit_depth': bits, 'color_type': color,
              'sha256': sha256(data), 'size': len(data)}
    if not glyph:
        return report
    previous = bytearray(stride)
    alphas, visible = set(), 0
    for y in range(height):
        start = y*(stride + 1)
        kind, row = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            a = row[x - channels] if x >= channels else 0
            b = previous[x]
            c = previous[x - channels] if x >= channels else 0
            if kind == 1:
                prediction = a
            elif kind == 2:
                prediction = b
            elif kind == 3:
                prediction = (a + b)//2
            elif kind == 4:
                p = a + b - c
                distances = (abs(p - a), abs(p - b), abs(p - c))
                prediction = (a, b, c)[distances.index(min(distances))]
            else:
                prediction = 0
            row[x] = (row[x] + prediction) & 255
        for x in range(0, stride, channels):
            pixel = tuple(row[x:x + channels])
            if color == 6:
                rgb, alpha = pixel[:3], pixel[3]
            elif color == 4:
                rgb, alpha = (pixel[0],)*3, pixel[1]
            elif color == 3:
                index = pixel[0]
                require(index*3 + 3 <= len(palette), 'PNG palette index out of range')
                rgb = tuple(palette[index*3:index*3 + 3])
                alpha = transparency[index] if transparency is not None and index < len(transparency) else 255
            else:
                rgb = pixel if color == 2 else (pixel[0],)*3
                transparent_pixel = struct.unpack('>3H' if color == 2 else '>H', transparency) if transparency else None
                alpha = 0 if pixel == transparent_pixel else 255
            alphas.add(alpha)
            if alpha:
                visible += 1
                require(rgb == (255, 255, 255), 'compact glyph must contain white foreground pixels only')
        previous = row
    require(0 in alphas and visible, 'compact glyph must have both transparent and visible pixels')
    report.update({'white_glyph': True, 'transparent': True, 'visible_pixels': visible})
    return report


def check_resource(name, data):
    require(name in RESOURCE_SIZES, 'unknown icon: ' + name)
    return png(data, RESOURCE_SIZES[name], name.startswith('DataSwitch'))


def manifest(data=None):
    result = json.loads(regular(RESOURCE_MANIFEST) if data is None else data)
    require(isinstance(result, dict), 'resource manifest must be a JSON object')
    require(result.get('schema_version') == 1 and result.get('package') == PACKAGE and result.get('version') == VERSION, 'resource manifest metadata mismatch')
    hashes = result.get('resources')
    require(isinstance(hashes, dict) and set(hashes) == set(RESOURCE_SIZES), 'resource manifest key mismatch')
    require(all(value is None or isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value) for value in hashes.values()), 'invalid resource SHA-256')
    return hashes


def validate_resource(name, data, hashes):
    report = check_resource(name, data)
    require(hashes[name] is not None, 'resource hash not frozen: ' + name)
    require(report['sha256'] == hashes[name], 'resource SHA-256 mismatch: ' + name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true', help='explicitly approve all current PNG bytes')
    parser.add_argument('--force', action='store_true', help='replace previously frozen hashes')
    args = parser.parse_args()
    old = manifest()
    reports = {name: check_resource(name, regular(ROOT / 'Resources' / name)) for name in RESOURCE_SIZES}
    if args.freeze:
        require(args.force or not any(old.values()), 'hashes already frozen; review changes before --freeze --force')
        value = {'schema_version': 1, 'package': PACKAGE, 'version': VERSION,
                 'resources': {name: report['sha256'] for name, report in reports.items()}}
        RESOURCE_MANIFEST.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    else:
        for name, report in reports.items():
            require(old[name] is not None and old[name] == report['sha256'], 'resource hash missing/mismatched: ' + name)
    print(json.dumps({'resources': reports, 'hashes_frozen': args.freeze}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
