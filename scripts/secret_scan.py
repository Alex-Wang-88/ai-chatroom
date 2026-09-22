"""Small dependency-free guard for accidental credential commits."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", "target", "data", "probe-output"}
SKIP_FILES = {".env"}
PATTERNS = (
    re.compile(r"shareId=(?!\{|replace-with|\$\{)[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"Authorization[ \t]*[:=][ \t]*(?!replace-with|\$\{|\[REDACTED\])[A-Za-z0-9+/=_-]{20,}", re.IGNORECASE),
)


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name in SKIP_FILES or any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                findings.append(f"{path.relative_to(ROOT)}: matched {pattern.pattern}")
    if findings:
        print("Potential secrets found:")
        print("\n".join(findings))
        return 1
    print("Secret scan passed (local .env and generated files excluded).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
