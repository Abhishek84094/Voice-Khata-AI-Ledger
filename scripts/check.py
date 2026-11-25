#!/usr/bin/env python3
"""Cross-platform gate check runner for Voice Khata.

Runs:
1. ruff check . && ruff format --check .
2. mypy --strict backend/app
3. pytest -q --cov=app --cov-fail-under=85
4. bandit -q -r backend/app
5. pip-audit
6. gitleaks detect --no-banner (if installed)
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_step(name: str, cmd: list[str], cwd: str | None = None) -> bool:
    print(f"\n--- [GATE] Running: {name} ---")
    print(f"Command: {' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(ROOT, "backend")
    res = subprocess.run(cmd, cwd=cwd or ROOT, env=env)
    if res.returncode != 0:
        print(f"[GATE FAILED] {name} exited with code {res.returncode}")
        return False
    print(f"[GATE PASSED] {name}")
    return True


def main() -> int:
    py = sys.executable

    steps = [
        ("ruff format check", [py, "-m", "ruff", "format", "--check", "."]),
        ("ruff lint check", [py, "-m", "ruff", "check", "."]),
        ("mypy strict", [py, "-m", "mypy", "--strict", "backend/app"]),
        (
            "pytest coverage",
            [
                py,
                "-m",
                "pytest",
                "-q",
                "--cov=app",
                "--cov-report=term-missing",
                "--cov-fail-under=85",
                "backend/tests",
            ],
        ),
        (
            "bandit security scan",
            [py, "-m", "bandit", "-q", "-r", "backend/app", "-c", "pyproject.toml"],
        ),
        ("pip-audit dependency vulnerability check", [py, "-m", "pip_audit"]),
    ]

    for name, cmd in steps:
        if not run_step(name, cmd):
            return 1

    # Check gitleaks if available
    gitleaks_bin = shutil.which("gitleaks")
    if gitleaks_bin:
        if not run_step("gitleaks secret scan", [gitleaks_bin, "detect", "--no-banner"]):
            return 1
    else:
        print(
            "\n--- [GATE] gitleaks not installed locally; "
            "skipping local gitleaks check (enforced in CI) ---"
        )

    print("\n==========================================")
    print("ALL GATE CHECKS PASSED SUCCESSFULLY (GREEN)")
    print("==========================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
