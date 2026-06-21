from pathlib import Path

ROOT = Path(__file__).resolve().parent / "upstream"


def replace(path: str, old: str, new: str, *, count: int = -1) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:140]!r}")
    text = text.replace(old, new, count)
    p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Reproducible OpenClaw install. Do not silently pull a newer incompatible CLI.
# ---------------------------------------------------------------------------
replace(
    "flutter_app/lib/services/bootstrap_service.dart",
    "'$nodeRun $npmCli install -g openclaw',",
    "'$nodeRun $npmCli install -g openclaw@2026.6.9',",
)
replace(
    "flutter_app/lib/services/bootstrap_service.dart",
    "message: 'Installing OpenClaw (this may take a few minutes)...',",
    "message: 'Installing tested OpenClaw 2026.6.9 (this may take a few minutes)...',",
)


# ---------------------------------------------------------------------------
# The setup is not considered successful until a real local gateway answers
# /healthz on the actual phone. Authentication is remembered across retries.
# ---------------------------------------------------------------------------
replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    '''echo "CLAWEASY:STEP:2"
openclaw models auth login --provider openrouter --method oauth || fail 21 "OpenRouter sign-in did not finish"

''',
    '''echo "CLAWEASY:STEP:2"
AUTH_MARKER=/root/.openclaw/claweasy-openrouter-authenticated
if [ -f "$AUTH_MARKER" ]; then
  echo "CLAWEASY:INFO:Using saved OpenRouter sign-in"
else
  openclaw models auth login --provider openrouter --method oauth || fail 21 "OpenRouter sign-in did not finish"
  touch "$AUTH_MARKER"
fi

''',
)
replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    '''echo "CLAWEASY:STEP:4"
openclaw config validate || fail 41 "OpenClaw configuration is invalid"
openclaw infer model run --local \\
  --model openrouter/openrouter/free \\
  --prompt "Reply with exactly: CLAWEASY_OK" \\
  --json || fail 42 "The free model test failed"

echo "CLAWEASY:SUCCESS"
''',
    '''echo "CLAWEASY:STEP:4"
openclaw config validate || fail 41 "OpenClaw configuration is invalid"
if ! openclaw infer model run --local \\
  --model openrouter/openrouter/free \\
  --prompt "Reply with exactly: CLAWEASY_OK" \\
  --json; then
  rm -f "$AUTH_MARKER"
  fail 42 "The free model test failed. Tap Fix and Retry to sign in again."
fi

echo "CLAWEASY:STEP:5"
GW_LOG=/tmp/claweasy-gateway-smoke.log
GW_PID=""
cleanup_gateway() {
  if [ -n "$GW_PID" ] && kill -0 "$GW_PID" 2>/dev/null; then
    kill "$GW_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$GW_PID" 2>/dev/null || true
  fi
  if [ -n "$GW_PID" ]; then
    wait "$GW_PID" 2>/dev/null || true
  fi
}
trap cleanup_gateway EXIT INT TERM
rm -f "$GW_LOG"
OPENCLAW_GATEWAY_STARTUP_TRACE=1 NO_COLOR=1 \\
  openclaw gateway --verbose --cli-backend-logs --allow-unconfigured \\
  --bind loopback --port 18789 >"$GW_LOG" 2>&1 &
GW_PID=$!
healthy=0
i=0
while [ "$i" -lt 120 ]; do
  if curl -fsS --max-time 2 http://127.0.0.1:18789/healthz >/dev/null 2>&1; then
    healthy=1
    break
  fi
  if ! kill -0 "$GW_PID" 2>/dev/null; then
    break
  fi
  i=$((i + 1))
  sleep 1
done
if [ "$healthy" -ne 1 ]; then
  echo "CLAWEASY:GATEWAY_LOG_BEGIN"
  tail -n 100 "$GW_LOG" 2>/dev/null || true
  echo "CLAWEASY:GATEWAY_LOG_END"
  cleanup_gateway
  GW_PID=""
  fail 51 "The gateway failed its on-device health test. Technical details are shown below."
fi
curl -fsS --max-time 3 http://127.0.0.1:18789/readyz >/dev/null 2>&1 || true
cleanup_gateway
GW_PID=""
trap - EXIT INT TERM
touch /root/.openclaw/claweasy-gateway-smoke-v1

echo "CLAWEASY:SUCCESS"
''',
)
replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    '''      if (clean.contains('CLAWEASY:STEP:4')) {
        _step = 4;
        _status = 'Testing the model…';
      }
      if (clean.contains('CLAWEASY:SUCCESS')) {
        _step = 5;
        _status = 'Your free AI is ready';
''',
    '''      if (clean.contains('CLAWEASY:STEP:4')) {
        _step = 4;
        _status = 'Testing the free model…';
      }
      if (clean.contains('CLAWEASY:STEP:5')) {
        _step = 5;
        _status = 'Starting and testing the gateway on this phone…';
      }
      if (clean.contains('CLAWEASY:SUCCESS')) {
        _step = 6;
        _status = 'Your free AI is ready';
''',
)
replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    '''            _StepRow(number: 3, label: 'Select OpenRouter Free', current: _step),
            _StepRow(number: 4, label: 'Run a real model test', current: _step),
            const SizedBox(height: 20),
''',
    '''            _StepRow(number: 3, label: 'Select OpenRouter Free', current: _step),
            _StepRow(number: 4, label: 'Run a real model test', current: _step),
            _StepRow(number: 5, label: 'Start and health-check the gateway', current: _step),
            const SizedBox(height: 20),
''',
)
replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    "if (active && current < 5)",
    "if (active && current < 6)",
)
replace(
    "flutter_app/lib/screens/free_model_setup_screen.dart",
    "OpenClaw is configured for the OpenRouter free-model router and the gateway is locked to this phone.",
    "The free model answered successfully, and the gateway passed a real on-device health check. It is locked to this phone.",
)


# ---------------------------------------------------------------------------
# Gateway launch: preflight Node/OpenClaw/config, use explicit safe flags, and
# turn on startup tracing so failures are visible rather than swallowed.
# ---------------------------------------------------------------------------
replace(
    "flutter_app/android/app/src/main/kotlin/com/nxg/openclawproot/GatewayService.kt",
    '''                emitLog("[INFO] Spawning proot process...")
                synchronized(lock) {
                    if (stopping) return@Thread
                    processStartTime = System.currentTimeMillis()
                    gatewayProcess = pm.startProotProcess("openclaw gateway --verbose")
                }
''',
    '''                emitLog("[INFO] Running gateway preflight...")
                try {
                    val preflight = pm.runInProotSync(
                        "node --version && openclaw --version && openclaw config validate",
                        60
                    )
                    preflight.lineSequence()
                        .filter { it.isNotBlank() }
                        .forEach { emitLog("[CHECK] $it") }
                } catch (e: Exception) {
                    emitLog("[ERROR] Gateway preflight failed: ${e.message}")
                    throw e
                }

                emitLog("[INFO] Spawning proot process...")
                synchronized(lock) {
                    if (stopping) return@Thread
                    processStartTime = System.currentTimeMillis()
                    gatewayProcess = pm.startProotProcess(
                        "OPENCLAW_GATEWAY_STARTUP_TRACE=1 NO_COLOR=1 " +
                        "openclaw gateway --verbose --cli-backend-logs " +
                        "--allow-unconfigured --bind loopback --port 18789"
                    )
                }
''',
)


# ---------------------------------------------------------------------------
# Flutter gateway state: subscribe before launch, probe the documented health
# endpoint, detect fatal logs, and never display Starting forever.
# ---------------------------------------------------------------------------
replace(
    "flutter_app/lib/services/gateway_service.dart",
    "  Timer? _initialDelayTimer;\n",
    "  Timer? _initialDelayTimer;\n  Timer? _startupDeadlineTimer;\n",
)
replace(
    "flutter_app/lib/services/gateway_service.dart",
    '''      _updateState(_state.copyWith(logs: logs, dashboardUrl: dashboardUrl));
''',
    '''      final lower = log.toLowerCase();
      final fatal = lower.contains('cannot link executable') ||
          lower.contains('gateway preflight failed') ||
          lower.contains('openclaw: command not found') ||
          lower.contains('cannot find module') ||
          lower.contains('max restarts reached') ||
          lower.contains('[error] gateway error:');
      if (fatal && _state.status == GatewayStatus.starting) {
        _cancelAllTimers();
        _updateState(_state.copyWith(
          status: GatewayStatus.error,
          logs: logs,
          dashboardUrl: dashboardUrl,
          errorMessage: log.replaceAll(AppConstants.ansiEscape, '').trim(),
        ));
      } else {
        _updateState(_state.copyWith(logs: logs, dashboardUrl: dashboardUrl));
      }
''',
)
replace(
    "flutter_app/lib/services/gateway_service.dart",
    '''      _startingAt = DateTime.now();
      await NativeBridge.startGateway();
      _subscribeLogs();
      _startHealthCheck();
''',
    '''      _startingAt = DateTime.now();
      // Subscribe first so an immediate native/PRoot failure cannot disappear.
      _subscribeLogs();
      await NativeBridge.startGateway();
      _startHealthCheck();
''',
)
replace(
    "flutter_app/lib/services/gateway_service.dart",
    '''    _initialDelayTimer?.cancel();
    _initialDelayTimer = null;
    _healthTimer?.cancel();
''',
    '''    _initialDelayTimer?.cancel();
    _initialDelayTimer = null;
    _startupDeadlineTimer?.cancel();
    _startupDeadlineTimer = null;
    _healthTimer?.cancel();
''',
)
replace(
    "flutter_app/lib/services/gateway_service.dart",
    '''  void _startHealthCheck() {
    _cancelAllTimers();
    // Delay the first health check by 30s — Node.js inside proot needs time to start.
''',
    '''  void _startHealthCheck() {
    _cancelAllTimers();
    _startupDeadlineTimer = Timer(const Duration(seconds: 150), () async {
      if (_state.status != GatewayStatus.starting) return;
      final startIndex = _state.logs.length > 8 ? _state.logs.length - 8 : 0;
      final recent = _state.logs.sublist(startIndex).join('\n');
      try { await NativeBridge.stopGateway(); } catch (_) {}
      _updateState(_state.copyWith(
        status: GatewayStatus.error,
        errorMessage: 'Gateway failed to become healthy within 150 seconds.\n$recent',
        logs: [
          ..._state.logs,
          _ts('[ERROR] Gateway startup timed out after 150 seconds'),
        ],
      ));
      _cancelAllTimers();
    });
    // Delay the first health check while Node.js starts inside PRoot.
''',
)
replace(
    "flutter_app/lib/services/gateway_service.dart",
    ".head(Uri.parse(AppConstants.gatewayUrl))",
    ".get(Uri.parse('${AppConstants.gatewayUrl}/healthz'))",
)
replace(
    "flutter_app/lib/services/gateway_service.dart",
    '''        _updateState(_state.copyWith(
          status: GatewayStatus.running,
''',
    '''        _startupDeadlineTimer?.cancel();
        _startupDeadlineTimer = null;
        _updateState(_state.copyWith(
          status: GatewayStatus.running,
''',
    count=1,
)
replace(
    "flutter_app/lib/services/gateway_service.dart",
    '''    } catch (_) {
      // Still starting or temporarily unreachable
      final isRunning = await NativeBridge.isGatewayRunning();
      if (!isRunning && _state.status != GatewayStatus.stopped) {
        // Grace period: if we're still within 120s of startup, don't declare dead.
        // proot + Node.js can take a long time on first boot.
        if (_startingAt != null &&
            _state.status == GatewayStatus.starting &&
            DateTime.now().difference(_startingAt!).inSeconds < 120) {
          _updateState(_state.copyWith(
            logs: [..._state.logs, _ts('[INFO] Starting, waiting for gateway...')],
          ));
          return;
        }
        _updateState(_state.copyWith(
          status: GatewayStatus.stopped,
          logs: [..._state.logs, _ts('[WARN] Gateway process not running')],
        ));
        _cancelAllTimers();
      }
    }
''',
    '''    } catch (_) {
      // Still starting or temporarily unreachable.
      final isRunning = await NativeBridge.isGatewayRunning();
      final elapsed = _startingAt == null
          ? 0
          : DateTime.now().difference(_startingAt!).inSeconds;
      if (!isRunning && _state.status != GatewayStatus.stopped) {
        if (_state.status == GatewayStatus.starting && elapsed < 150) {
          _updateState(_state.copyWith(
            logs: [..._state.logs, _ts('[INFO] Starting, waiting for gateway...')],
          ));
          return;
        }
        _updateState(_state.copyWith(
          status: GatewayStatus.error,
          errorMessage: 'The gateway process stopped before it became healthy.',
          logs: [..._state.logs, _ts('[ERROR] Gateway process stopped during startup')],
        ));
        _cancelAllTimers();
      }
    }
''',
)


# Branding/version metadata after the base ClawEasy patch.
replace("flutter_app/lib/constants.dart", "static const String version = '1.8.7';", "static const String version = '0.1.2';")
replace("flutter_app/lib/constants.dart", "static const String packageName = 'com.nxg.openclawproot';", "static const String packageName = 'com.taylor.claweasy';")
replace("flutter_app/pubspec.yaml", "version: 0.1.1+2", "version: 0.1.2+3")

print("ClawEasy runtime reliability patch applied successfully")
