from pathlib import Path

path = Path(__file__).resolve().parent / "upstream/flutter_app/lib/services/gateway_service.dart"
text = path.read_text(encoding="utf-8")

# patch_runtime.py uses Python triple-quoted replacement strings. Convert the
# two intended Dart escape sequences back from literal line breaks.
text = text.replace("join('\n');", "join('\\n');")
text = text.replace(
    "errorMessage: 'Gateway failed to become healthy within 150 seconds.\n$recent',",
    "errorMessage: 'Gateway failed to become healthy within 150 seconds.\\n$recent',",
)

path.write_text(text, encoding="utf-8")
print("ClawEasy Dart newline escapes repaired")
