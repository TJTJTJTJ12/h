from pathlib import Path

ROOT = Path(__file__).resolve().parent / "upstream"


def replace(path: str, old: str, new: str, *, count: int = -1) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:160]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# The native writeResolv call can race with directory setup on some Samsung /
# Android 16 devices. Build the bind-mount source directly from Dart, verify it,
# and also write a rootfs copy so DNS still works if the bind mount is skipped.
replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    "import 'dart:convert';\nimport 'dart:typed_data';",
    "import 'dart:convert';\nimport 'dart:io';\nimport 'dart:typed_data';",
)

replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    """  Future<void> _runSetup() async {
    if (_running) return;
""",
    """  Future<void> _ensureRuntimeFiles() async {
    final filesDir = await NativeBridge.getFilesDir();
    final requiredDirs = <String>[
      '$filesDir/config',
      '$filesDir/tmp',
      '$filesDir/home',
      '$filesDir/home/.openclaw',
      '$filesDir/rootfs/ubuntu/etc',
      '$filesDir/rootfs/ubuntu/root/.openclaw',
      '$filesDir/rootfs/ubuntu/tmp',
    ];
    for (final path in requiredDirs) {
      await Directory(path).create(recursive: true);
      if (!await Directory(path).exists()) {
        throw FileSystemException('Could not create required directory', path);
      }
    }

    const resolv = 'nameserver 1.1.1.1\\nnameserver 8.8.8.8\\noptions timeout:2 attempts:3\\n';
    final hostResolv = File('$filesDir/config/resolv.conf');
    await hostResolv.writeAsString(resolv, flush: true);
    if (!await hostResolv.exists() || await hostResolv.length() < 10) {
      throw FileSystemException('Could not create DNS configuration', hostResolv.path);
    }

    // Keep a second copy inside Ubuntu. This is deliberately independent of
    // the PRoot bind mount so DNS survives if Android removes the host file.
    final rootfsResolv = File('$filesDir/rootfs/ubuntu/etc/resolv.conf');
    await rootfsResolv.parent.create(recursive: true);
    try {
      if (await rootfsResolv.exists()) await rootfsResolv.delete();
      await rootfsResolv.writeAsString(resolv, flush: true);
    } catch (_) {
      // The host-side bind file above is the required source of truth.
    }
  }

  Future<void> _runSetup() async {
    if (_running) return;
""",
)

replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    """      await NativeBridge.setupDirs();
      await NativeBridge.writeResolv();

      final config = await TerminalService.getProotShellConfig();
""",
    """      // Do not trust a background native setup race. Create and verify
      // every bind-mount source synchronously before PRoot is launched.
      await NativeBridge.setupDirs();
      await _ensureRuntimeFiles();
      try {
        await NativeBridge.writeResolv();
      } catch (_) {
        // _ensureRuntimeFiles already created a verified fallback.
      }
      await _ensureRuntimeFiles();

      final config = await TerminalService.getProotShellConfig();
""",
)

# Run a real network/DNS preflight before provider authentication. This gives a
# useful error instead of sending the user into a browser flow that cannot work.
replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    '''echo "CLAWEASY:STEP:1"
NODE_REQUIRED=22.22.1
''',
    '''echo "CLAWEASY:STEP:1"
getent hosts nodejs.org >/dev/null 2>&1 \
  || curl -fsI --max-time 12 https://nodejs.org/ >/dev/null 2>&1 \
  || fail 8 "Internet or DNS is unavailable inside OpenClaw. Turn off VPN/private DNS temporarily and retry."
NODE_REQUIRED=22.22.1
''',
)

# Fresh installs and upgrades both need the directories. Make setupDirectories
# create resolv.conf itself, so every native service gets the same guarantee.
replace(
    "flutter_app/android/app/src/main/kotlin/com/nxg/openclawproot/BootstrapManager.kt",
    """        // Create fake /proc and /sys files for proot bind mounts
        setupFakeSysdata()
    }
""",
    """        // Create fake /proc and /sys files for proot bind mounts
        setupFakeSysdata()
        // Every PRoot launch binds this exact host file. Create it here rather
        // than relying on a later asynchronous call.
        writeResolvConf()
    }
""",
)

# Version bump after prior patches have produced 0.1.3.
replace("flutter_app/lib/constants.dart", "static const String version = '0.1.3';", "static const String version = '0.1.4';")
replace("flutter_app/pubspec.yaml", "version: 0.1.3+4", "version: 0.1.4+5")

print("ClawEasy runtime filesystem patch applied successfully")
