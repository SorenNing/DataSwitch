# DataSwitch 1.0.1 rootless packaging contract

Package `com.ning.dataswitch`, title `数据切换`, version `1.0.1`, architecture `iphoneos-arm64` (universal arm64 + arm64e ABI-v2). Bundle ID `com.ning.dataswitch.module`; executable `DataSwitch`; principal class `DataSwitchModule`. Both CFBundleShortVersionString and CFBundleVersion are `1.0.1`.

The package depends exactly on `firmware (>= 16.0), firmware (<< 18.0), com.opa334.ccsupport`. Author and Maintainer currently say `Ning`; the main agent may add confirmed upstream attribution. The validators require nonempty attribution fields rather than pinning an unconfirmed identity.

This is a directly loaded CCSupport module. Packaging is independent of the selected in-process cellular backend. The tools do not vendor a backend, helper, hook engine, CC18 module, injected library, launch daemon or maintainer script. The linker allows the five requested public frameworks, system libobjc/libSystem, and a strong LC_LOAD_DYLIB for ControlCenterUIKit. The text-based ControlCenterUIKit.tbd is a link interface only and is never shipped.

Input and installed-file mapping:

| Input | Installed path | Mode |
| --- | --- | --- |
| build/DataSwitch | var/jb/Library/ControlCenter/Bundles/DataSwitch.bundle/DataSwitch | 0755 |
| Resources/Info.plist | var/jb/Library/ControlCenter/Bundles/DataSwitch.bundle/Info.plist | 0644 |
| Resources/DataSwitch.png, @2x, @3x | var/jb/Library/ControlCenter/Bundles/DataSwitch.bundle, same names | 0644 |
| Resources/SettingsIcon.png, @2x, @3x | var/jb/Library/ControlCenter/Bundles/DataSwitch.bundle, same names | 0644 |
| Resources/PackageIcon.png | var/jb/usr/share/icons/com.ning.dataswitch.png | 0644 |
| Resources/PackageIcon@256.png | var/jb/usr/share/icons/com.ning.dataswitch@256.png | 0644 |
| Resources/PackageIcon@128.png | var/jb/usr/share/icons/com.ning.dataswitch@128.png | 0644 |
| share/doc/com.ning.dataswitch/provenance.json (optional) | var/jb/usr/share/doc/com.ning.dataswitch/provenance.json | 0644 |

Provenance remains main-agent-authored documentation. If present, it must be a JSON object and is copied byte-for-byte. There are no inherited SIM/helper hashes, provenance-field assertions or helper execution paths. Missing optional provenance does not block a package; the report records its absence.

PNG inputs are 8-bit non-interlaced PNGs. Sizes are DataSwitch 50/100/150px, SettingsIcon 29/58/87px, PackageIcon 512/256/128px. Compact glyphs must have transparent pixels and white visible pixels. CRC, IDAT decompression, scanline filters, dimensions and SHA-256 are checked using only Python's standard library. Resources are not generated or resized by these tools. Runtime compact 46pt / expanded 32pt sizing belongs to src and does not affect the pixel-size contract.

The main agent must finalize all nine PNGs and then explicitly freeze their reviewed bytes:

```sh
python3 tools/resources.py --freeze
python3 tools/check_local.py
python3 tools/package.py --dry-run
```

`resource-hashes.json` initially contains nulls so unreviewed images cannot pass strict validation. Use `--freeze --force` only after deliberately reviewing changed resources. CI never regenerates the approved hashes.

Allowed local read-only checks:

```sh
python3 tools/check_local.py --allow-pending
python3 tools/package.py --dry-run --allow-pending
python3 tools/selftest.py
bash -n tools/build-macos.sh
python3 tools/mkdeb.py --dry-run /tmp/not-written.deb /tmp/not-read-members
```

The check script reads source files and headers, control/plist, PNG/hash inputs, Python AST, linker stub and the small manual-workflow contract. It does not invoke clang, xcrun, the build script, GitHub APIs or subprocesses. Source token checks are a coarse static guard, not Objective-C compilation or proof of runtime behavior. `--allow-pending` permits inventory completion but keeps `ready_to_build: false`; strict mode exits nonzero until source, images and hashes are complete. Entry-point scripts disable Python bytecode writes.

Only a later explicit manual workflow run uses `macos-latest` and the selected Apple toolchain. `build-macos.sh` first validates inputs, then builds exactly the four DataSwitch .m files for `arm64-apple-ios16.0` and `arm64e-apple-ios16.0`, links Foundation/UIKit/CoreGraphics/QuartzCore/CoreTelephony and strong ControlCenterUIKit, uses chained fixups, combines slices with Apple lipo and signs ad-hoc with Apple codesign. No macOS ar, dpkg-deb, third-party compiler, helper signing or entitlement transfer is used.

`macho.py` checks universal slice bounds/alignment/non-overlap, arm64 subtype 0 and arm64e ABI-v2 subtype 0x80000002 in both fat and thin headers, iPhoneOS 16 deployment metadata, the install name, dependency allowlist, strong ControlCenterUIKit, chained-fixup pointer formats, ad-hoc CodeDirectories, complete code-page hashes and any signed internal special blobs. It performs structural/hash validation; Apple codesign additionally verifies the built artifact on the runner.

`package.py` assembles only whitelisted files. It generates raw USTAR bytes with uid/gid 0, root names, mtime 0, fixed modes and sorted paths, then gzip with mtime 0 and no original filename. `mkdeb.py` writes Debian's three ar members directly in Python. `verify.py` rejects PAX/GNU extensions, links/devices, path traversal, duplicates, extra payload files, maintainer scripts, incorrect ownership/modes, mismatched metadata, bad signatures and changed resource hashes. The native compiler and codesign output may vary with Xcode; deterministic archive headers do not imply cross-Xcode binary reproducibility.

Expected outputs on a later user-triggered build are `dist/com.ning.dataswitch_1.0.1_iphoneos-arm64.deb` and `dist/package-validation.json`, uploaded as `DataSwitch-1.0.1`. Workflow has only `workflow_dispatch`, `contents: read`, no push/PR/schedule triggers, no release/publish/push actions. Package payload paths are relative `var/jb/...` inside the deb (absolute `/var/jb/...` after installation). The icon control URI is `file:///var/jb/usr/share/icons/com.ning.dataswitch.png`.

The archived 1.0 RootHide executable's arm64 and arm64e slices had no LC_RPATH and only system dynamic-library loads; this does not prove the separately repackaged 1.0.1 binary works on a normal rootless device. The current workflow builds fresh from source, and `macho.py` explicitly rejects any LC_RPATH, including RootHide search paths. No fresh 1.0.1 compile, deb generation, CI run or device runtime check has been performed as part of this source-only update.
