"""
Cross-platform Docker container health-check poller.
Used by Makefile `make up` to wait for Qdrant before starting the rest of the stack.

Usage:
  python scripts/wait_healthy.py <container-name> [max-wait-seconds]

Exit codes:
  0 — container reached 'healthy' state
  1 — timed out
"""

import subprocess
import sys
import time


def wait_healthy(container: str, timeout: int = 120) -> bool:
    interval = 3
    elapsed = 0
    while elapsed < timeout:
        result = subprocess.run(
            ["docker", "inspect", container, "--format", "{{.State.Health.Status}}"],
            capture_output=True,
            text=True,
        )
        status = result.stdout.strip()
        if status == "healthy":
            print(f"  {container} is healthy.")
            return True
        print(f"  Waiting for {container}... (status={status or 'not found'}, {elapsed}s elapsed)")
        time.sleep(interval)
        elapsed += interval

    print(f"  ERROR: {container} did not become healthy within {timeout}s")
    return False


if __name__ == "__main__":
    container = sys.argv[1] if len(sys.argv) > 1 else "zih-qdrant"
    max_wait = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    sys.exit(0 if wait_healthy(container, max_wait) else 1)
