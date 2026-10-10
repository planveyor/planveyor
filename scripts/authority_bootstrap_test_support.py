"""Supported bootstrap launchers shared by authority integration tests.

The bootstrap is caller-owned data: this helper reads the fixture copy once
and passes those retained bytes to an isolated child interpreter.  It never
executes or imports the bootstrap by pathname.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Mapping
from pathlib import Path
import subprocess
import sys
import types
from typing import Any, Iterator, Protocol


class AuthorityFixtureLike(Protocol):
    runtime_root: Path
    target_root: Path

    def environment(self) -> dict[str, str]: ...


_AUTHORITY_MODULE_NAMES = (
    "fs_object_identity",
    "contract_authority_snapshot",
    "contract_authority_runtime",
    "contract_authority_context",
)
_MISSING = object()


def _bootstrap_literal(fixture: AuthorityFixtureLike) -> str:
    path = fixture.runtime_root / "scripts" / "contract_authority_bootstrap.py"
    return path.read_bytes().decode("utf-8")


def run_bootstrapped_bridge(
    fixture: AuthorityFixtureLike,
    *arguments: str,
    cwd: Path | None = None,
    environment: Mapping[str, str] | None = None,
    stdin_text: str | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run an active bridge command through the retained literal bootstrap."""

    bridge = fixture.runtime_root / "scripts" / "contract_authority_bridge.py"
    command = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        _bootstrap_literal(fixture),
        str(bridge),
        *arguments,
    ]
    kwargs: dict[str, Any] = {
        "cwd": cwd or fixture.target_root,
        "env": dict(environment) if environment is not None else fixture.environment(),
        "text": True,
        "capture_output": True,
        "check": False,
        "timeout": timeout,
    }
    if stdin_text is None:
        return subprocess.run(command, stdin=subprocess.DEVNULL, **kwargs)
    return subprocess.run(command, input=stdin_text, **kwargs)


def run_python_stdin(
    fixture: AuthorityFixtureLike,
    source: str,
    *arguments: str,
    cwd: Path | None = None,
    environment: Mapping[str, str] | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run caller-owned stdin after the bridge validates retained core bytes."""

    return run_bootstrapped_bridge(
        fixture,
        "python-stdin",
        "--",
        *arguments,
        cwd=cwd,
        environment=environment,
        stdin_text=source,
        timeout=timeout,
    )


def run_python_entry(
    fixture: AuthorityFixtureLike,
    path: Path,
    *arguments: str,
    cwd: Path | None = None,
    environment: Mapping[str, str] | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run one frozen runtime Python entry after bridge admission."""

    return run_bootstrapped_bridge(
        fixture,
        "python-entry",
        "--path",
        str(path),
        "--",
        *arguments,
        cwd=cwd,
        environment=environment,
        timeout=timeout,
    )


@contextmanager
def supported_bridge_module(fixture: AuthorityFixtureLike) -> Iterator[types.ModuleType]:
    """Load the real bridge bytes with the literal bootstrap's real reader.

    This test-only in-process route permits a regression to call the same
    bridge module twice while retaining the actual source capsules that the
    bootstrap read.  It does not import or execute the bootstrap by pathname.
    """

    bootstrap_path = fixture.runtime_root / "scripts" / "contract_authority_bootstrap.py"
    bootstrap_namespace: dict[str, Any] = {
        "__name__": "authority_bootstrap_test_literal",
        "__file__": str(bootstrap_path),
    }
    literal = _bootstrap_literal(fixture)
    exec(compile(literal, str(bootstrap_path), "exec", dont_inherit=True), bootstrap_namespace)

    bridge_path = fixture.runtime_root / "scripts" / "contract_authority_bridge.py"
    bridge_capsule = bootstrap_namespace["_read_regular_source"](str(bridge_path))
    source_reader = bootstrap_namespace["_reader_with_cache"](bridge_capsule)
    module_name = "authority_bootstrap_test_bridge"
    bridge_module = types.ModuleType(module_name)
    bridge_module.__dict__.update(
        {
            "__file__": bridge_capsule[0],
            "__package__": None,
            "__loader__": None,
            "__spec__": None,
            "__cached__": None,
            "__authority_source_capsule__": bridge_capsule,
            "__authority_read_source__": source_reader,
        }
    )
    names = tuple(
        alias
        for name in _AUTHORITY_MODULE_NAMES
        for alias in (name, f"scripts.{name}")
    )
    previous_modules = {name: sys.modules.get(name, _MISSING) for name in (*names, module_name)}
    for name in names:
        sys.modules.pop(name, None)
    sys.modules[module_name] = bridge_module
    try:
        exec(
            compile(bridge_capsule[3], bridge_capsule[0], "exec", dont_inherit=True),
            bridge_module.__dict__,
            bridge_module.__dict__,
        )
        yield bridge_module
    finally:
        for name, previous in previous_modules.items():
            if previous is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
