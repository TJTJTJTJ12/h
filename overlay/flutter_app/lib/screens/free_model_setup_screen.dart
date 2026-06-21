import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_pty/flutter_pty.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/native_bridge.dart';
import '../services/terminal_service.dart';
import 'dashboard_screen.dart';

/// Guided, mostly automatic OpenRouter-free setup for OpenClaw Android.
///
/// The only user action is completing OpenRouter's browser login. Everything
/// else—safe loopback binding, gateway token generation, model selection,
/// config validation, and a live inference test—is performed automatically.
class FreeModelSetupScreen extends StatefulWidget {
  final bool isFirstRun;

  const FreeModelSetupScreen({super.key, this.isFirstRun = false});

  @override
  State<FreeModelSetupScreen> createState() => _FreeModelSetupScreenState();
}

class _FreeModelSetupScreenState extends State<FreeModelSetupScreen> {
  Pty? _pty;
  StreamSubscription<List<int>>? _outputSub;
  final _redirectController = TextEditingController();

  int _step = 0;
  String _status = 'Preparing…';
  String _logs = '';
  String? _signInUrl;
  String? _error;
  bool _success = false;
  bool _browserOpened = false;
  bool _running = false;

  static final _ansi = RegExp(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])');
  static final _openRouterUrl = RegExp(
    r'''https://openrouter\.ai/[^\s\x1b<>"']+''',
    caseSensitive: false,
  );

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _runSetup());
  }

  Future<void> _runSetup() async {
    if (_running) return;
    await _stopProcess();

    setState(() {
      _running = true;
      _step = 0;
      _status = 'Preparing OpenClaw…';
      _logs = '';
      _signInUrl = null;
      _error = null;
      _success = false;
      _browserOpened = false;
    });

    try {
      await NativeBridge.setupDirs();
      await NativeBridge.writeResolv();

      final config = await TerminalService.getProotShellConfig();
      final args = TerminalService.buildProotArgs(config, columns: 100, rows: 32);
      args.removeLast(); // -l
      args.removeLast(); // /bin/bash

      const script = r'''
set -uo pipefail
fail() {
  code="$1"
  shift
  echo "CLAWEASY:ERROR:${code}:$*"
  exit "$code"
}

echo "CLAWEASY:STEP:1"
openclaw config set gateway.mode local || fail 11 "Could not set local gateway mode"
openclaw config set gateway.bind loopback || fail 12 "Could not bind gateway to loopback"
TOKEN="$(node -e "console.log(require('crypto').randomBytes(24).toString('hex'))")" || fail 13 "Could not generate gateway token"
openclaw config set gateway.auth.mode token || fail 14 "Could not enable gateway token security"
openclaw config set gateway.auth.token "$TOKEN" || fail 15 "Could not save gateway token"

echo "CLAWEASY:STEP:2"
openclaw models auth login --provider openrouter --method oauth || fail 21 "OpenRouter sign-in did not finish"

echo "CLAWEASY:STEP:3"
openclaw models set openrouter/openrouter/free || fail 31 "Could not select the free model router"

echo "CLAWEASY:STEP:4"
openclaw config validate || fail 41 "OpenClaw configuration is invalid"
openclaw infer model run --local \
  --model openrouter/openrouter/free \
  --prompt "Reply with exactly: CLAWEASY_OK" \
  --json || fail 42 "The free model test failed"

echo "CLAWEASY:SUCCESS"
''';

      args.addAll(['/bin/bash', '-lc', script]);

      _pty = Pty.start(
        config['executable']!,
        arguments: args,
        environment: TerminalService.buildHostEnv(config),
        columns: 100,
        rows: 32,
      );

      _outputSub = _pty!.output.cast<List<int>>().listen(
        (data) {
          final text = utf8.decode(data, allowMalformed: true);
          _handleOutput(text);
        },
        onError: (Object e) {
          if (mounted) {
            setState(() {
              _error = 'Setup process error: $e';
              _status = 'Setup stopped';
              _running = false;
            });
          }
        },
      );

      _pty!.exitCode.then((code) {
        if (!mounted || _success) return;
        setState(() {
          _running = false;
          _error ??= 'Setup exited before finishing (code $code).';
          _status = 'Setup needs attention';
        });
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _running = false;
        _error = 'Could not start setup: $e';
        _status = 'Setup could not start';
      });
    }
  }

  void _handleOutput(String text) {
    final clean = text.replaceAll(_ansi, '');
    final combined = '$_logs$clean';
    final urlMatch = _openRouterUrl.firstMatch(combined);

    if (!mounted) return;
    setState(() {
      _logs = combined.length > 12000
          ? combined.substring(combined.length - 12000)
          : combined;

      if (clean.contains('CLAWEASY:STEP:1')) {
        _step = 1;
        _status = 'Securing the local gateway…';
      }
      if (clean.contains('CLAWEASY:STEP:2')) {
        _step = 2;
        _status = 'Sign in to OpenRouter in your browser';
      }
      if (clean.contains('CLAWEASY:STEP:3')) {
        _step = 3;
        _status = 'Selecting the free model…';
      }
      if (clean.contains('CLAWEASY:STEP:4')) {
        _step = 4;
        _status = 'Testing the model…';
      }
      if (clean.contains('CLAWEASY:SUCCESS')) {
        _step = 5;
        _status = 'Your free AI is ready';
        _success = true;
        _running = false;
      }

      final errorLine = RegExp(r'CLAWEASY:ERROR:(\d+):([^\r\n]+)').firstMatch(clean);
      if (errorLine != null) {
        _error = errorLine.group(2)?.trim() ?? 'Setup failed';
        _status = 'Setup needs attention';
        _running = false;
      }

      if (urlMatch != null && _signInUrl == null) {
        _signInUrl = urlMatch.group(0)?.replaceAll(RegExp(r'[),.;]+$'), '');
      }
    });

    if (_signInUrl != null && !_browserOpened) {
      _browserOpened = true;
      unawaited(_openSignIn());
    }
  }

  Future<void> _openSignIn() async {
    final url = _signInUrl;
    if (url == null) return;
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  void _sendRedirect() {
    final value = _redirectController.text.trim();
    if (value.isEmpty) return;
    _pty?.write(Uint8List.fromList(utf8.encode('$value\n')));
    _redirectController.clear();
    FocusScope.of(context).unfocus();
    setState(() => _status = 'Finishing sign-in…');
  }

  Future<void> _stopProcess() async {
    await _outputSub?.cancel();
    _outputSub = null;
    _pty?.kill();
    _pty = null;
  }

  void _goToDashboard() {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const DashboardScreen()),
      (_) => false,
    );
  }

  @override
  void dispose() {
    _redirectController.dispose();
    unawaited(_stopProcess());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Set Up Free AI'),
        automaticallyImplyLeading: !widget.isFirstRun,
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              _status,
              style: theme.textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'ClawEasy handles the technical setup. You only need to approve the free OpenRouter sign-in.',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 24),
            _StepRow(number: 1, label: 'Secure local gateway', current: _step),
            _StepRow(number: 2, label: 'Sign in for free model access', current: _step),
            _StepRow(number: 3, label: 'Select OpenRouter Free', current: _step),
            _StepRow(number: 4, label: 'Run a real model test', current: _step),
            const SizedBox(height: 20),
            if (_signInUrl != null && !_success) ...[
              FilledButton.icon(
                onPressed: _openSignIn,
                icon: const Icon(Icons.open_in_browser),
                label: const Text('Open Free Sign-In'),
              ),
              const SizedBox(height: 12),
              Text(
                'The browser normally returns automatically. Only use the box below if OpenRouter shows you a final redirect URL.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _redirectController,
                keyboardType: TextInputType.url,
                autocorrect: false,
                decoration: const InputDecoration(
                  labelText: 'Paste redirect URL (only if asked)',
                ),
                onSubmitted: (_) => _sendRedirect(),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: _sendRedirect,
                child: const Text('Finish Sign-In'),
              ),
            ],
            if (_running && _signInUrl == null) ...[
              const SizedBox(height: 12),
              const LinearProgressIndicator(),
            ],
            if (_error != null) ...[
              const SizedBox(height: 20),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.error_outline, color: theme.colorScheme.error),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _error!,
                              style: const TextStyle(fontWeight: FontWeight.w700),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      FilledButton.icon(
                        onPressed: _running ? null : _runSetup,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Fix and Retry'),
                      ),
                      ExpansionTile(
                        tilePadding: EdgeInsets.zero,
                        title: const Text('Technical details'),
                        children: [
                          Container(
                            width: double.infinity,
                            constraints: const BoxConstraints(maxHeight: 220),
                            padding: const EdgeInsets.all(12),
                            color: theme.colorScheme.surfaceContainerHighest,
                            child: SingleChildScrollView(
                              child: SelectableText(
                                _logs,
                                style: theme.textTheme.bodySmall?.copyWith(
                                  fontFamily: 'monospace',
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ],
            if (_success) ...[
              const SizedBox(height: 20),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    children: [
                      Icon(Icons.check_circle, size: 54, color: Colors.green.shade500),
                      const SizedBox(height: 10),
                      Text(
                        'Everything worked.',
                        style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 6),
                      const Text(
                        'OpenClaw is configured for the OpenRouter free-model router and the gateway is locked to this phone.',
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 16),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: _goToDashboard,
                          icon: const Icon(Icons.rocket_launch),
                          label: const Text('Open ClawEasy'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: 20),
            Text(
              'Free models have provider rate limits and can occasionally be busy. ClawEasy never exposes the gateway to the public internet by default.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  final int number;
  final String label;
  final int current;

  const _StepRow({required this.number, required this.label, required this.current});

  @override
  Widget build(BuildContext context) {
    final complete = current > number;
    final active = current == number;
    final colors = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        children: [
          CircleAvatar(
            radius: 16,
            backgroundColor: complete || active ? colors.primary : colors.surfaceContainerHighest,
            foregroundColor: complete || active ? colors.onPrimary : colors.onSurfaceVariant,
            child: complete
                ? const Icon(Icons.check, size: 18)
                : Text('$number', style: const TextStyle(fontWeight: FontWeight.w700)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontWeight: active ? FontWeight.w800 : FontWeight.w500,
              ),
            ),
          ),
          if (active && current < 5)
            const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
        ],
      ),
    );
  }
}
