from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    npm_command = "npm.cmd" if sys.platform.startswith("win") else "npm"
    run(
        ["uv", "run", "--project", "src/backend", "pytest", "--cov=src/backend", "--cov-report=xml"],
        cwd=ROOT,
    )
    run([npm_command, "run", "coverage", "--workspaces=false"], cwd=ROOT / "src" / "frontend")


if __name__ == "__main__":
    main()
