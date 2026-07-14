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
    args = parser.parse_args()
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"

    run("backend tests", [sys.executable, "-m", "pytest"])
    run("frontend build", [npm, "run", "build"], ROOT / "frontend")
    if args.mode == "full":
        run("dependency audit", [npm, "audit", "--audit-level=moderate"], ROOT / "frontend")

    print(f"\nAll {args.mode} checks passed.")


if __name__ == "__main__":
    main()

