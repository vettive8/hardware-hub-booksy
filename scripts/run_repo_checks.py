from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str], cwd: Path = ROOT) -> None:
    print(f"\n[{label}] {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Hardware Hub repository checks")
    parser.add_argument("--mode", choices=("quick", "full"), default="quick")
    parser.add_argument(
        "--include-integration",
        action="store_true",
        help="Include credential-gated provider tests that may spend OpenRouter credits",
    )
    args = parser.parse_args()
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"

    pytest_command = [sys.executable, "-m", "pytest"]
    if not args.include_integration:
        pytest_command.extend(["-m", "not integration"])
    run("backend tests", pytest_command)
    run("frontend build", [npm, "run", "build"], ROOT / "frontend")
    if args.mode == "full":
        run("dependency audit", [npm, "audit", "--audit-level=moderate"], ROOT / "frontend")

    print(f"\nAll {args.mode} checks passed.")


if __name__ == "__main__":
    main()
