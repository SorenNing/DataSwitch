#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then
  printf '%s\n' 'This script requires macOS and the Apple iPhoneOS SDK.' >&2
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
# Preflight never invokes a compiler; approved resource hashes must already exist.
python3 tools/check_local.py
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
mkdir -p build dist
SOURCES=(src/DataSwitchModule.m src/DataSwitchController.m src/DataSwitchService.m src/DataSwitchRow.m)
for ARCH in arm64 arm64e; do
  xcrun --sdk iphoneos clang -fobjc-arc -fblocks -O2 -fvisibility=hidden \
    -Werror=implicit-function-declaration -Werror=objc-method-access \
    -isysroot "$SDK" -target "${ARCH}-apple-ios16.0" -dynamiclib -Isrc \
    -Ftools/linker -framework Foundation -framework UIKit -framework CoreGraphics -framework QuartzCore \
    -framework CoreTelephony -Wl,-needed_framework,ControlCenterUIKit \
    -Wl,-fixup_chains -Wl,-install_name,@loader_path/DataSwitch \
    "${SOURCES[@]}" -o "build/DataSwitch-${ARCH}"
done
xcrun lipo -create -output build/DataSwitch build/DataSwitch-arm64 build/DataSwitch-arm64e
xcrun codesign --force --sign - --identifier com.ning.dataswitch.module --timestamp=none build/DataSwitch
xcrun codesign --verify --strict --verbose=2 build/DataSwitch
python3 tools/macho.py build/DataSwitch
python3 tools/package.py
python3 tools/verify.py
