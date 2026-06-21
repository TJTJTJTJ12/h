# ClawEasy

ClawEasy is an Android build of the MIT-licensed `mithun50/openclaw-termux` project with a simplified first-run flow.

## What this build changes

- Installs the full OpenClaw gateway on the phone; it is not merely a companion node.
- Keeps the gateway bound to loopback by default.
- Generates gateway token security automatically.
- Runs OpenRouter's OAuth sign-in instead of asking the user to manually configure providers.
- Selects `openrouter/openrouter/free` automatically.
- Validates the OpenClaw configuration.
- Sends a real test prompt before reporting success.
- Hides the terminal unless technical details are needed.
- Uses a separate Android application ID (`com.taylor.claweasy`) so it can coexist with the upstream app.

## Build

Push this kit to a GitHub branch named `claweasy-build`. GitHub Actions produces an ARM64 APK in the `ClawEasy-Android-APK` artifact.

## First run

1. Tap **Begin Setup**. The app downloads roughly 500 MB for Ubuntu, Node.js, and OpenClaw.
2. Tap **Set Up Free AI**.
3. Complete the OpenRouter browser sign-in.
4. The app selects the free router, validates it, and sends a test prompt.
5. Tap **Open ClawEasy**.

## Important limits

OpenRouter's free models have daily and per-minute rate limits, and availability can vary. The app is designed for a hosted free model, not a fully offline model. Running a useful OpenClaw model entirely on a low-memory phone would be much slower and less capable.

## Security defaults

ClawEasy binds the gateway to loopback and creates a random gateway token. Do not expose port 18789 directly to the public internet. Review third-party skills before installing them.

## Licensing

ClawEasy is a modification layer for `mithun50/openclaw-termux`, which is MIT licensed, and installs OpenClaw, which is also MIT licensed. Original copyright notices and repository history remain in the checked-out upstream source during the build.
