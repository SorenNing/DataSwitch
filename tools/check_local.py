#!/usr/bin/env python3
"""Read-only source/metadata/PNG/hash/manual-workflow checks. Never builds."""
import argparse
import ast
import json
import re
import zlib
import sys
sys.dont_write_bytecode = True
from dataswitch import (ROOT, PACKAGE, NAME, VERSION, SOURCES, RESOURCE_SIZES,
                        RESOURCE_MANIFEST, PROVENANCE_INPUT, control_fields,
                        module_plist, provenance, regular, require, sha256)
from resources import manifest, check_resource


def workflow_check(data):
    """Validate this deliberately small YAML contract without external parsers."""
    text = data.decode('utf-8')
    require('\t' not in text, 'workflow indentation must use spaces')
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    tops = []
    blocks = {}
    current = None
    for line in lines:
        if not line.startswith(' '):
            match = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9-]*|'on'|\"on\"):.*", line)
            require(match, 'unsupported workflow top-level syntax')
            current = match[1].strip("'\"")
            require(current not in blocks, 'duplicate workflow top-level key')
            tops.append(current)
            blocks[current] = [line]
        else:
            require(current is not None, 'orphan workflow line')
            blocks[current].append(line)
    require(set(tops) == {'name', 'on', 'permissions', 'jobs'}, 'unexpected workflow top-level keys')
    require(blocks['on'][0] in ('on:', "'on':", '"on":'), 'workflow triggers must use explicit block mapping')
    require(blocks['on'][1:] == ['  workflow_dispatch:'], 'workflow must have workflow_dispatch only')
    require(blocks['permissions'] == ['permissions:', '  contents: read'], 'workflow token must be read-only')
    require('    runs-on: macos-latest' in lines, 'workflow must use macos-latest')
    runners = [line.strip() for line in lines if line.strip().startswith('runs-on:')]
    require(runners == ['runs-on: macos-latest'], 'unexpected runner/job')
    require('        run: bash tools/build-macos.sh' in lines, 'missing explicit Apple build step')
    require(any(line.strip() == 'name: DataSwitch-' + VERSION for line in lines), 'artifact name/version mismatch')
    require('            dist/' + PACKAGE + '_' + VERSION + '_iphoneos-arm64.deb' in lines, 'deb artifact path mismatch')
    require('            dist/package-validation.json' in lines, 'validation artifact missing')
    forbidden = ('push:', 'pull_request:', 'schedule:', 'workflow_run:', 'repository_dispatch:',
                 'contents: write', 'git push', 'gh repo create', 'softprops/action-gh-release')
    require(not any(token in text for token in forbidden), 'unexpected trigger/publish action')
    return {'trigger': 'workflow_dispatch', 'runner': 'macos-latest', 'permissions': 'contents: read'}


def source_check(name, data):
    text = data.decode('utf-8')
    require(text.strip() and '\x00' not in text, 'empty/binary source: ' + name)
    require('@implementation ' + name.split('/')[-1].removesuffix('.m') in text, 'expected Objective-C implementation missing: ' + name)
    forbidden = ('%hook', 'MSHookFunction', 'MSHookMessageEx', 'DobbyHook', 'fishhook',
                 'CCSIMTool', '/usr/libexec/', '/var/jb/usr/libexec/', 'posix_spawn(', 'system(')
    require(not any(token in text for token in forbidden), 'hook/helper execution token found: ' + name)
    return {'sha256': sha256(data), 'size': len(data), 'objc_compiled': False}


def build_script_check(data):
    text = data.decode('utf-8')
    for token in ('xcrun --sdk iphoneos clang', 'for ARCH in arm64 arm64e',
                  '${ARCH}-apple-ios16.0', '-framework Foundation', '-framework UIKit',
                  '-framework CoreGraphics', '-framework QuartzCore', '-framework CoreTelephony',
                  '-Wl,-needed_framework,ControlCenterUIKit', '-Wl,-fixup_chains',
                  'xcrun lipo', 'xcrun codesign', '--sign -', '--timestamp=none',
                  'python3 tools/package.py', 'python3 tools/verify.py'):
        require(token in text, 'missing build script contract: ' + token)
    for source in SOURCES:
        require(source in text, 'build source missing: ' + source)
    require(not re.search(r'(^|[\s;/])(ar|llvm-ar|dpkg-deb|ldid|clang-19)([\s;]|$)', text), 'non-Apple compiler/signing or host deb builder')
    return {'apple_toolchain': True, 'architectures': ['arm64', 'arm64e'], 'executed': False}


def linker_check(data):
    text = data.decode('utf-8')
    for token in ("install-name:    '/System/Library/PrivateFrameworks/ControlCenterUIKit.framework/ControlCenterUIKit'",
                  '[ arm64-ios, arm64e-ios ]', 'tbd-version:     4'):
        require(token in text, 'linker stub missing: ' + token)
    return {'format': 'tapi-tbd-v4', 'architectures': ['arm64', 'arm64e']}


def check_inputs(allow_pending=False):
    report = {'package': PACKAGE, 'name': NAME, 'version': VERSION, 'checks': [],
              'ios_built': False, 'device_tested': False, 'ci_triggered': False}
    def check(label, function, pending=False):
        try:
            result = function()
            report['checks'].append({'check': label, 'status': 'ok', 'result': result})
        except (ValueError, OSError, SyntaxError, UnicodeError, zlib.error) as error:
            report['checks'].append({'check': label, 'status': 'pending' if pending else 'error', 'message': str(error)})
    check('control', lambda: control_fields(regular(ROOT / 'control')))
    check('Info.plist', lambda: module_plist(regular(ROOT / 'Resources/Info.plist')))
    for source in SOURCES:
        path = ROOT / source
        check(source, lambda s=source, p=path: source_check(s, regular(p)), not path.exists())
    for path in sorted((ROOT / 'src').glob('*.h')):
        def header_check(p=path):
            data = regular(p)
            text = data.decode('utf-8')
            require(text.strip() and '\x00' not in text, 'empty/binary header: ' + p.name)
            require(not any(token in text for token in ('%hook', 'MSHook', 'CCSIMTool', '/usr/libexec/', 'posix_spawn(')), 'hook/helper token in header: ' + p.name)
            return {'sha256': sha256(data), 'size': len(data)}
        check(str(path.relative_to(ROOT)), header_check)
    for path in sorted((ROOT / 'tools').glob('*.py')):
        check('python AST: ' + path.name, lambda p=path: bool(ast.parse(regular(p).decode('utf-8'), filename=str(p))))
    check('workflow', lambda: workflow_check(regular(ROOT / '.github/workflows/build.yml')))
    check('build script (read-only)', lambda: build_script_check(regular(ROOT / 'tools/build-macos.sh')))
    check('framework link stub', lambda: linker_check(regular(ROOT / 'tools/linker/ControlCenterUIKit.framework/ControlCenterUIKit.tbd')))
    hashes = None
    try:
        hashes = manifest()
        report['checks'].append({'check': 'resource manifest', 'status': 'ok', 'result': {'sha256': sha256(regular(RESOURCE_MANIFEST))}})
    except (ValueError, OSError, UnicodeError) as error:
        report['checks'].append({'check': 'resource manifest', 'status': 'error', 'message': str(error)})
    if hashes is not None:
        for name in RESOURCE_SIZES:
            path = ROOT / 'Resources' / name
            check('PNG: ' + name, lambda n=name, p=path: check_resource(n, regular(p)), not path.exists())
            check('SHA-256: ' + name,
                  lambda n=name, p=path: require(hashes[n] is not None and sha256(regular(p)) == hashes[n], 'resource hash missing/mismatched: ' + n),
                  not path.exists() or hashes[name] is None)
    if PROVENANCE_INPUT.exists():
        check('optional provenance', lambda: provenance(regular(PROVENANCE_INPUT)))
    else:
        report['checks'].append({'check': 'optional provenance', 'status': 'optional-missing', 'message': str(PROVENANCE_INPUT.relative_to(ROOT))})
    errors = [item for item in report['checks'] if item['status'] == 'error']
    pending = [item for item in report['checks'] if item['status'] == 'pending']
    report['ready_to_build'] = not errors and not pending
    report['passed'] = not errors and (allow_pending or not pending)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-pending', action='store_true', help='inventory in-progress source/icons; never marks ready_to_build')
    args = parser.parse_args()
    report = check_inputs(args.allow_pending)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
