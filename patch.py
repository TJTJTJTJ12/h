from pathlib import Path

ROOT = Path(__file__).resolve().parent / "upstream"


def replace(path: str, old: str, new: str, *, count: int = -1) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:100]!r}")
    text = text.replace(old, new, count)
    p.write_text(text, encoding="utf-8")


# Route first-time setup into the automatic free-model flow.
replace(
    "flutter_app/lib/screens/setup_wizard_screen.dart",
    "import 'onboarding_screen.dart';",
    "import 'free_model_setup_screen.dart';",
)
replace(
    "flutter_app/lib/screens/setup_wizard_screen.dart",
    "label: const Text('Configure API Keys'),",
    "label: const Text('Set Up Free AI'),",
)
replace(
    "flutter_app/lib/screens/setup_wizard_screen.dart",
    "builder: (_) => const OnboardingScreen(isFirstRun: true),",
    "builder: (_) => const FreeModelSetupScreen(isFirstRun: true),",
)

# On later launches, finish model setup before showing the dashboard.
replace(
    "flutter_app/lib/screens/splash_screen.dart",
    "import 'setup_wizard_screen.dart';\nimport 'dashboard_screen.dart';",
    "import 'setup_wizard_screen.dart';\nimport 'free_model_setup_screen.dart';\nimport 'dashboard_screen.dart';",
)
replace(
    "flutter_app/lib/screens/splash_screen.dart",
    """      if (setupComplete) {
        prefs.setupComplete = true;
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const DashboardScreen()),
        );
      } else {
""",
    """      if (setupComplete) {
        prefs.setupComplete = true;
        String configText = '';
        try {
          configText = await NativeBridge.readRootfsFile('root/.openclaw/openclaw.json') ?? '';
        } catch (_) {}
        final freeModelReady = configText.contains('openrouter/openrouter/free');
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => freeModelReady
                ? const DashboardScreen()
                : const FreeModelSetupScreen(isFirstRun: true),
          ),
        );
      } else {
""",
)

# Replace the confusing generic onboarding shortcut with a one-tap repair path.
replace(
    "flutter_app/lib/screens/dashboard_screen.dart",
    "import 'onboarding_screen.dart';",
    "import 'free_model_setup_screen.dart';",
)
replace(
    "flutter_app/lib/screens/dashboard_screen.dart",
    """            StatusCard(
              title: 'Onboarding',
              subtitle: 'Configure API keys and binding',
              icon: Icons.vpn_key,
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const OnboardingScreen()),
              ),
            ),
""",
    """            StatusCard(
              title: 'Free AI Setup',
              subtitle: 'Sign in, select, test, or repair the free model',
              icon: Icons.auto_awesome,
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const FreeModelSetupScreen()),
              ),
            ),
""",
)

# Brand it as a separate install so it can coexist with the upstream app.
replace("flutter_app/lib/app.dart", "title: 'OpenClaw',", "title: 'ClawEasy',")
replace("flutter_app/lib/screens/dashboard_screen.dart", "title: const Text('OpenClaw'),", "title: const Text('ClawEasy'),")
replace("flutter_app/lib/screens/splash_screen.dart", "'OpenClaw',", "'ClawEasy',", count=1)
replace("flutter_app/android/app/src/main/AndroidManifest.xml", 'android:label="OpenClaw"', 'android:label="ClawEasy"')
replace("flutter_app/android/app/build.gradle", 'applicationId = "com.nxg.openclawproot"', 'applicationId = "com.taylor.claweasy"')
replace("flutter_app/pubspec.yaml", "name: openclaw", "name: claweasy")
replace(
    "flutter_app/pubspec.yaml",
    "description: OpenClaw AI Gateway for Android - standalone, no Termux required.",
    "description: One-tap OpenClaw Android setup with automatic free-model configuration.",
)
replace("flutter_app/pubspec.yaml", "version: 1.8.7+18", "version: 0.1.0+1")

print("ClawEasy patch applied successfully")
