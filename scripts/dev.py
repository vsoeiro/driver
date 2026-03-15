from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "src" / "backend"
FRONTEND_DIR = REPO_ROOT / "src" / "frontend"
ALEMBIC_INI = REPO_ROOT / "src" / "alembic.ini"
DEFAULT_WORKERS = (
    ("worker-light", "driver:jobs:light", "3"),
    ("worker-default", "driver:jobs", "2"),
    ("worker-heavy", "driver:jobs:heavy", "1"),
)


@dataclass
class ManagedProcess:
    name: str
    command: list[str]
    cwd: Path
    env: dict[str, str] | None = None
    process: subprocess.Popen[str] | None = None


def resolve_command(name: str) -> str:
    candidates = [name]
    if os.name == "nt":
        candidates.insert(0, f"{name}.cmd")

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    raise SystemExit(f"Required command not found in PATH: {name}")


def format_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def relay_output(name: str, stream: subprocess.Popen[str]) -> None:
    assert stream.stdout is not None
    for line in stream.stdout:
        print(f"[{name}] {line.rstrip()}", flush=True)


def run_checked(
    command: list[str],
    cwd: Path,
    label: str,
    dry_run: bool,
    env: dict[str, str] | None = None,
) -> None:
    print(f"[{label}] {format_command(command)}", flush=True)
    if dry_run:
        return

    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def spawn_process(managed: ManagedProcess, dry_run: bool) -> threading.Thread | None:
    print(f"[{managed.name}] {format_command(managed.command)}", flush=True)
    if dry_run:
        return None

    popen_kwargs: dict[str, object] = {
        "cwd": managed.cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "text": True,
        "bufsize": 1,
        "env": managed.env or os.environ.copy(),
    }

    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["preexec_fn"] = os.setsid

    managed.process = subprocess.Popen(managed.command, **popen_kwargs)
    thread = threading.Thread(target=relay_output, args=(managed.name, managed.process), daemon=True)
    thread.start()
    return thread


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return

    os.killpg(process.pid, signal.SIGTERM)
    deadline = time.time() + 5
    while process.poll() is None and time.time() < deadline:
        time.sleep(0.1)
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)


def warn_missing_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        print("[dev] Warning: .env not found in repository root.", flush=True)


def resolve_backend_proxy_host(host: str) -> str:
    if host in {"0.0.0.0", ""}:
        return "127.0.0.1"
    if host == "::":
        return "[::1]"
    return host


def build_backend_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_entries = [str(REPO_ROOT / "src")]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    return env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run backend and frontend together for local development.",
    )
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Skip `alembic upgrade head` before starting the backend.",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=8000,
        help="Port for the FastAPI backend.",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=5173,
        help="Port for the Vite frontend.",
    )
    parser.add_argument(
        "--backend-host",
        default="0.0.0.0",
        help="Host for the FastAPI backend.",
    )
    parser.add_argument(
        "--frontend-host",
        default="0.0.0.0",
        help="Host for the Vite frontend.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without starting processes.",
    )
    parser.add_argument(
        "--skip-workers",
        action="store_true",
        help="Start only backend and frontend, without ARQ workers.",
    )
    parser.add_argument(
        "--with-scheduler",
        action="store_true",
        help="Also start the dedicated scheduler process.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    uv = resolve_command("uv")
    npm = resolve_command("npm")
    backend_env = build_backend_env()

    warn_missing_env()

    if not args.skip_migrate:
        run_checked(
            [
                uv,
                "run",
                "--project",
                str(BACKEND_DIR),
                "alembic",
                "-c",
                str(ALEMBIC_INI),
                "upgrade",
                "head",
            ],
            REPO_ROOT,
            "migrate",
            args.dry_run,
            backend_env,
        )

    managed_processes = [
        ManagedProcess(
            name="backend",
            cwd=REPO_ROOT,
            command=[
                uv,
                "run",
                "--project",
                str(BACKEND_DIR),
                "uvicorn",
                "backend.main:app",
                "--reload",
                "--host",
                args.backend_host,
                "--port",
                str(args.backend_port),
            ],
            env=backend_env,
        ),
        ManagedProcess(
            name="frontend",
            cwd=FRONTEND_DIR,
            command=[
                npm,
                "run",
                "dev",
                "--workspaces=false",
                "--",
                "--host",
                args.frontend_host,
                "--port",
                str(args.frontend_port),
            ],
            env={
                **os.environ.copy(),
                "FRONTEND_API_PROXY_TARGET": (
                    f"http://{resolve_backend_proxy_host(args.backend_host)}:{args.backend_port}"
                ),
            },
        ),
    ]

    if not args.skip_workers:
        for worker_name, queue_name, concurrency in DEFAULT_WORKERS:
            managed_processes.append(
                ManagedProcess(
                    name=worker_name,
                    cwd=REPO_ROOT,
                    command=[
                        uv,
                        "run",
                        "--project",
                        str(BACKEND_DIR),
                        "arq",
                        "backend.workers.arq_worker.WorkerSettings",
                    ],
                    env={
                        **backend_env,
                        "WORKER_QUEUE_NAME": queue_name,
                        "WORKER_CONCURRENCY": concurrency,
                        "DB_POOL_MODE": "null",
                    },
                )
            )

    if args.with_scheduler:
        managed_processes.append(
            ManagedProcess(
                name="scheduler",
                cwd=REPO_ROOT,
                command=[
                    uv,
                    "run",
                    "--project",
                    str(BACKEND_DIR),
                    "python",
                    "-m",
                    "backend.workers.scheduler_worker",
                ],
                env=backend_env,
            )
        )

    threads: list[threading.Thread | None] = []
    try:
        for managed in managed_processes:
            threads.append(spawn_process(managed, args.dry_run))

        if args.dry_run:
            return 0

        while True:
            for managed in managed_processes:
                assert managed.process is not None
                return_code = managed.process.poll()
                if return_code is None:
                    continue

                print(
                    f"[dev] Process `{managed.name}` exited with code {return_code}. Stopping remaining processes.",
                    flush=True,
                )
                for other in managed_processes:
                    if other.process is not None and other.process is not managed.process:
                        terminate_process_tree(other.process)
                return return_code

            time.sleep(0.2)
    except KeyboardInterrupt:
        print("[dev] Stopping backend and frontend...", flush=True)
        for managed in managed_processes:
            if managed.process is not None:
                terminate_process_tree(managed.process)
        return 0
    finally:
        for thread in threads:
            if thread is not None:
                thread.join(timeout=1)


if __name__ == "__main__":
    sys.exit(main())
