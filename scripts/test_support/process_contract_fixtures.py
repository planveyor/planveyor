"""Small helpers for process-contract test fixtures.

The helpers write caller-provided fixture bodies unchanged. Keep the markdown
contract itself at the call site so reviewers can inspect the exact input.
"""

from __future__ import annotations

import contextlib
import math
import os
import subprocess
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any


_MAX_ZSH_FIXTURE_TIMEOUT_SECONDS = 240.0


def run_zsh_fixture(
    command: str,
    *,
    cwd: Path | str,
    path: str,
    pybin: str,
    fixture_env: Mapping[str, str] | None = None,
    home: Path | str | None = None,
    argv0: str = "zsh",
    argv_tail: Sequence[str] = (),
    capture_output: bool = True,
    stdout: Any | None = None,
    stderr: Any | None = None,
    check: bool = False,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    """Run a finite zsh fixture with only the environment its test supplies."""
    if fixture_env is not None and {"HOME", "PATH", "PYBIN"}.intersection(fixture_env):
        raise ValueError("fixture_env must not override HOME, PATH, or PYBIN")
    if not Path(pybin).is_absolute():
        raise ValueError("pybin must be an absolute path")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
        or timeout > _MAX_ZSH_FIXTURE_TIMEOUT_SECONDS
    ):
        raise ValueError(
            f"timeout must be positive and no greater than {_MAX_ZSH_FIXTURE_TIMEOUT_SECONDS:g} seconds"
        )
    if capture_output and (stdout is not None or stderr is not None):
        raise ValueError("capture_output cannot be combined with stdout or stderr")

    def run(home_path: Path) -> subprocess.CompletedProcess[str]:
        environment = {
            "PATH": str(path),
            "PYBIN": str(pybin),
            "HOME": str(home_path),
        }
        if fixture_env is not None:
            environment.update(fixture_env)

        def invoke() -> subprocess.CompletedProcess[str]:
            options: dict[str, Any] = {
                "cwd": cwd,
                "env": environment,
                "stdin": subprocess.DEVNULL,
                "text": True,
                "capture_output": capture_output,
                "check": check,
                "timeout": timeout,
            }
            if stdout is not None:
                options["stdout"] = stdout
            if stderr is not None:
                options["stderr"] = stderr
            return subprocess.run(
                ["/bin/zsh", "-fc", command, argv0, *argv_tail],
                **options,
            )

        if "TMPDIR" in environment or "TMPPREFIX" in environment:
            return invoke()
        with tempfile.TemporaryDirectory(
            prefix="planveyor-zsh-fixture-child-",
        ) as temporary_child:
            child_tmp = Path(temporary_child).resolve()
            environment.update(
                TMPDIR=str(child_tmp),
                TMPPREFIX=str(child_tmp / "zsh"),
            )
            return invoke()

    if home is not None:
        return run(Path(home))
    with tempfile.TemporaryDirectory(prefix="planveyor-zsh-fixture-home-") as temporary_home:
        return run(Path(temporary_home))


def write_text_fixture(root: Path, rel_path: str, body: str) -> Path:
    """Write a text fixture under root and return its path."""
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def write_bytes_fixture(root: Path, rel_path: str, body: bytes = b"") -> Path:
    """Write a binary fixture under root and return its path."""
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return target


def standalone_git_root(root: Path | str) -> Path:
    """Make an existing fixture directory its own Git top-level and return it.

    The engine resolves an explicit project root through Git and refuses a
    directory that Git resolves to an enclosing work tree (git_root_mismatch).
    A fixture project with its own repository and one empty commit stays a
    valid project root wherever the temporary directory lies, for example when
    TMPDIR is inside a worktree's ignored .tmp/.
    """
    root = Path(root)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    for arguments in (
        ("init", "--quiet"),
        (
            "-c", "user.name=Fixture project",
            "-c", "user.email=fixture-project@example.invalid",
            "-c", "commit.gpgSign=false",
            "commit", "--quiet", "--allow-empty", "--no-verify", "-m", "Fixture project root",
        ),
    ):
        subprocess.run(
            ["git", "-C", str(root), *arguments],
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
            timeout=60,
        )
    return root


@contextlib.contextmanager
def temporary_git_root(**kwargs: Any) -> Iterator[str]:
    """Yield a temporary directory that is its own Git top-level (see standalone_git_root)."""
    with tempfile.TemporaryDirectory(**kwargs) as temporary:
        standalone_git_root(temporary)
        yield temporary


NON_GIT_ROOT_SKIP_REASON = (
    "needs a non-Git project root, which a TMPDIR inside a Git work tree cannot provide: "
    "the engine refuses such a root (git_root_mismatch)"
)


def inside_git_work_tree(path: Path | str) -> bool:
    """Tell whether Git discovery from path reaches a work tree, ignoring GIT_* variables as the engine does."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=60,
    )
    return completed.returncode == 0 and completed.stdout.strip() == b"true"
