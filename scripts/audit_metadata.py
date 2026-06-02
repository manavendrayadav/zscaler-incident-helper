"""
Audit version consistency across README badges, requirements.txt,
Dockerfile, pyproject.toml, .python-version, and CI config.
Exits 0 if everything matches, 1 with a report if anything drifts.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
errors = []


def check(label, expected, actual, source_expected, source_actual):
    if expected != actual:
        errors.append(
            f"  {label}: {source_expected} says {expected!r}, {source_actual} says {actual!r}"
        )


# ── Python version ────────────────────────────────────────────────────────────
py_ver = (ROOT / ".python-version").read_text(encoding="utf-8").strip()  # e.g. "3.12"

dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
docker_py = re.search(r"FROM python:(\d+\.\d+)", dockerfile).group(1)
check("Python", py_ver, docker_py, ".python-version", "Dockerfile")

pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
pyproject_py = re.search(r'requires-python\s*=\s*">=(\d+\.\d+)"', pyproject).group(1)
check("Python", py_ver, pyproject_py, ".python-version", "pyproject.toml requires-python")

ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
ci_versions = re.findall(r'python-version:\s*"(\d+\.\d+)"', ci)
for ci_py in ci_versions:
    check("Python", py_ver, ci_py, ".python-version", ".github/workflows/ci.yml")

readme = (ROOT / "README.md").read_text(encoding="utf-8")
readme_py_m = re.search(r"badge/python-(\d+\.\d+)-", readme)
if readme_py_m:
    check("Python", py_ver, readme_py_m.group(1), ".python-version", "README badge")
else:
    errors.append("  Python: README badge not found")

# ── FastAPI version ───────────────────────────────────────────────────────────
reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8")
fastapi_req_m = re.search(r"fastapi>=(\d+\.\d+)", reqs)
if fastapi_req_m:
    fastapi_req = fastapi_req_m.group(1)  # e.g. "0.135"
    readme_fastapi_m = re.search(r"badge/FastAPI-(\d+\.\d+)", readme)
    if readme_fastapi_m:
        check("FastAPI", fastapi_req, readme_fastapi_m.group(1), "requirements.txt", "README badge")
    else:
        errors.append("  FastAPI: README badge not found")
else:
    errors.append("  FastAPI: not found in requirements.txt")

# ── Project version ───────────────────────────────────────────────────────────
ver_py_m = re.search(
    r'__version__\s*=\s*"([^"]+)"', (ROOT / "version.py").read_text(encoding="utf-8")
)
pyproject_ver_m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
if ver_py_m and pyproject_ver_m:
    check(
        "Project version",
        ver_py_m.group(1),
        pyproject_ver_m.group(1),
        "version.py",
        "pyproject.toml",
    )
else:
    errors.append("  Project version: could not parse from version.py or pyproject.toml")

# ── Docker image versions (informational) ─────────────────────────────────────
compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
docker_images = re.findall(r"image:\s*(\S+)", compose)

# ── Report ────────────────────────────────────────────────────────────────────
if errors:
    print("AUDIT FAILED — version drift detected:")
    for e in errors:
        print(e)
    print("\nDocker images in compose (verify manually):")
    for img in docker_images:
        print(f"  {img}")
    sys.exit(1)

print("AUDIT PASSED — all versions consistent.")
print("\nDocker images in compose (verify manually):")
for img in docker_images:
    print(f"  {img}")
