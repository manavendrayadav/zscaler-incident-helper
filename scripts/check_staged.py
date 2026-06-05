"""
Cross-platform staged-file safety check for `make preflight`.

Replaces the Unix-only shell pipe:
    git diff --staged --name-only | grep -iE '\.env|\.key|secret|^data/'

Works identically on Windows, Linux, and macOS.
"""

import re
import subprocess
import sys

SENSITIVE_PATTERN = re.compile(r"(\.env$|\.key$|secret|^data/)", re.IGNORECASE)

result = subprocess.run(
    ["git", "diff", "--staged", "--name-only"],
    capture_output=True,
    text=True,
)

staged_files = [f for f in result.stdout.splitlines() if f.strip()]
flagged = [f for f in staged_files if SENSITIVE_PATTERN.search(f)]

if flagged:
    print("WARNING: Potentially sensitive file(s) staged — review before pushing!")
    for f in flagged:
        print(f"  {f}")
    sys.exit(1)
else:
    print("OK — no sensitive files detected.")
