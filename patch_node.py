from pathlib import Path

ROOT = Path(__file__).resolve().parent / "upstream"


def replace(path: str, old: str, new: str, *, count: int = -1) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:140]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# OpenClaw 2026.6.9 refuses to run on Node versions below 22.19.0.
# Use a newer official Node 22 LTS release for fresh installations.
replace(
    "flutter_app/lib/constants.dart",
    "static const String nodeVersion = '22.14.0';",
    "static const String nodeVersion = '22.22.1';",
)

# Verify the exact runtime after extraction rather than merely checking that
# `node --version` returns something.
replace(
    "flutter_app/lib/services/bootstrap_service.dart",
    """      await NativeBridge.runInProot(
        'node --version && $nodeRun $npmCli --version',
      );
""",
    """      await NativeBridge.runInProot(
        'node -e \\\'const v=process.versions.node.split(\".\").map(Number); '
        'if(v[0] < 22 || (v[0] === 22 && v[1] < 19)) process.exit(19);\\\' && '
        'node --version && $nodeRun $npmCli --version',
      );
""",
)

# Existing installations may already contain Node 22.14. Repair that runtime
# automatically before invoking any OpenClaw command, so Fix and Retry really
# fixes the problem instead of repeating it.
replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    '''echo "CLAWEASY:STEP:1"
openclaw config set gateway.mode local || fail 11 "Could not set local gateway mode"
''',
    '''echo "CLAWEASY:STEP:1"
NODE_REQUIRED=22.22.1
if node -e 'const v=process.versions.node.split(".").map(Number); process.exit(v[0] > 22 || (v[0] === 22 && (v[1] > 22 || (v[1] === 22 && v[2] >= 1))) ? 0 : 1)' 2>/dev/null; then
  echo "CLAWEASY:INFO:Node $(node --version) is compatible"
else
  echo "CLAWEASY:INFO:Updating Node.js to v${NODE_REQUIRED}"
  case "$(uname -m)" in
    aarch64|arm64) NODE_ARCH=arm64 ;;
    armv7l|armhf|arm) NODE_ARCH=armv7l ;;
    x86_64|amd64) NODE_ARCH=x64 ;;
    *) fail 9 "Unsupported CPU architecture for Node.js repair: $(uname -m)" ;;
  esac
  NODE_TAR=/tmp/node-v${NODE_REQUIRED}.tar.xz
  curl -fL --retry 3 --connect-timeout 20 \
    -o "$NODE_TAR" \
    "https://nodejs.org/dist/v${NODE_REQUIRED}/node-v${NODE_REQUIRED}-linux-${NODE_ARCH}.tar.xz" \
    || fail 10 "Could not download the compatible Node.js runtime"
  tar -xJf "$NODE_TAR" -C /usr/local --strip-components=1 \
    || fail 10 "Could not install the compatible Node.js runtime"
  rm -f "$NODE_TAR"
  hash -r
  node -e 'const v=process.versions.node.split(".").map(Number); process.exit(v[0] > 22 || (v[0] === 22 && (v[1] > 22 || (v[1] === 22 && v[2] >= 1))) ? 0 : 1)' \
    || fail 10 "Node.js upgrade verification failed"
  echo "CLAWEASY:INFO:Node upgraded to $(node --version)"
fi
openclaw config set gateway.mode local || fail 11 "Could not set local gateway mode"
''',
)

# Version bump.
replace("flutter_app/lib/constants.dart", "static const String version = '0.1.2';", "static const String version = '0.1.3';")
replace("flutter_app/pubspec.yaml", "version: 0.1.2+3", "version: 0.1.3+4")

print("ClawEasy Node.js compatibility patch applied successfully")
