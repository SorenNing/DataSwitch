"""DataSwitch package contract; Python standard library only."""
from pathlib import Path
import hashlib
import json
import plistlib

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'com.ning.dataswitch'
NAME = '数据切换'
VERSION = '1.0.1'
BUNDLE_ID = PACKAGE + '.module'
EXECUTABLE = 'DataSwitch'
BUNDLE = 'var/jb/Library/ControlCenter/Bundles/DataSwitch.bundle'
PROVENANCE = 'var/jb/usr/share/doc/' + PACKAGE + '/provenance.json'
PROVENANCE_INPUT = ROOT / 'share/doc' / PACKAGE / 'provenance.json'
DEB = ROOT / 'dist' / f'{PACKAGE}_{VERSION}_iphoneos-arm64.deb'
SOURCES = tuple('src/DataSwitch' + part + '.m' for part in ('Module', 'Controller', 'Service', 'Row'))
RESOURCE_SIZES = {
    'DataSwitch.png': 50, 'DataSwitch@2x.png': 100, 'DataSwitch@3x.png': 150,
    'SettingsIcon.png': 29, 'SettingsIcon@2x.png': 58, 'SettingsIcon@3x.png': 87,
    'PackageIcon.png': 512, 'PackageIcon@256.png': 256, 'PackageIcon@128.png': 128,
}
RESOURCE_PATHS = {
    name: ('var/jb/usr/share/icons/' + PACKAGE + name.removeprefix('PackageIcon')
           if name.startswith('PackageIcon') else BUNDLE + '/' + name)
    for name in RESOURCE_SIZES
}
RESOURCE_MANIFEST = ROOT / 'tools/resource-hashes.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'missing/non-regular input: ' + str(path))
    return path.read_bytes()


def control_fields(data):
    fields = {}
    for line in data.decode('utf-8').splitlines():
        require(line and not line[0].isspace() and ':' in line, 'invalid control field')
        key, value = line.split(':', 1)
        require(key not in fields and value.strip(), 'duplicate/empty control field')
        fields[key] = value.strip()
    expected = {
        'Package': PACKAGE, 'Name': NAME, 'Version': VERSION,
        'Architecture': 'iphoneos-arm64',
        'Depends': 'firmware (>= 16.0), firmware (<< 18.0), com.opa334.ccsupport',
        'Section': 'Tweaks', 'Priority': 'optional',
        'Icon': 'file:///' + RESOURCE_PATHS['PackageIcon.png'],
    }
    for key, value in expected.items():
        require(fields.get(key) == value, 'incorrect control field: ' + key)
    for key in ('Author', 'Maintainer', 'Description'):
        require(fields.get(key), 'missing control field: ' + key)
    require(not ({'Pre-Depends', 'Recommends'} & fields.keys()), 'unexpected additional dependency')
    return fields


def module_plist(data):
    info = plistlib.loads(data)
    require(isinstance(info, dict), 'Info.plist must be a dictionary')
    unit = {'Width': 1, 'Height': 1}
    expected = {
        'CFBundleIdentifier': BUNDLE_ID, 'CFBundleExecutable': EXECUTABLE,
        'NSPrincipalClass': 'DataSwitchModule', 'CFBundlePackageType': 'BNDL',
        'CFBundleName': NAME, 'CFBundleDisplayName': NAME,
        'CFBundleShortVersionString': VERSION, 'CFBundleVersion': VERSION,
        'MinimumOSVersion': '16.0', 'CFBundleSupportedPlatforms': ['iPhoneOS'],
        'UIDeviceFamily': [1, 2], 'ModuleSize': {'columns': 1, 'rows': 1},
        'CCSModuleDefaultSize': unit,
        'CCSModuleSize': {'Portrait': unit, 'Landscape': unit},
        'CFBundleIcons': {'CFBundlePrimaryIcon': {'CFBundleIconFiles': ['SettingsIcon']}},
    }
    for key, value in expected.items():
        require(info.get(key) == value, 'incorrect Info.plist key: ' + key)
    return info


def provenance(data):
    """Opaque documentation, not backend/helper integrity gating."""
    value = json.loads(data)
    require(isinstance(value, dict), 'provenance.json must contain a JSON object')
    return {'sha256': sha256(data), 'size': len(data)}
