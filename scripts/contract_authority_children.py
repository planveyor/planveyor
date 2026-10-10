"""Build retained-buffer authority child commands.

This module deliberately does not dispatch a child itself.  Callers retain
ownership of environment, stdio, cwd, timeouts, and subprocess semantics.  In
an engaged context it creates only the bridge-backed forms that preserve the
already validated runtime pin:

* ``python-entry`` for one absolute runtime-owned Python entry; and
* an anchored zsh command that installs a caller-owned loader literal before
  sourcing the pinned facade.

Legacy callers must retain their existing raw launch path and must not call
these builders.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import shlex
import sys
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # pragma: no cover - imports are resolved from the active runtime at execution.
    from contract_authority_context import ContractContext


class AuthorityChildLaunchError(RuntimeError):
    """A requested child shape cannot preserve the engaged authority pin."""


def _authority_modules() -> tuple[object, object]:
    """Return the already-selected context module and its sibling runtime.

    The context module owns the alias and source-origin checks for the core
    authority modules.  Reading its private sibling reference avoids a second
    package-resolution policy in this small command builder.
    """

    try:
        context_module = importlib.import_module("contract_authority_context")
    except ImportError as exc:  # pragma: no cover - surfaced only by malformed callers.
        raise AuthorityChildLaunchError("contract authority context is unavailable") from exc
    runtime_module = getattr(context_module, "_runtime", None)
    if runtime_module is None:
        raise AuthorityChildLaunchError("contract authority runtime is unavailable")
    return context_module, runtime_module


def _canonical_absolute_path(value: str | os.PathLike[str], *, field: str) -> Path:
    raw = os.fspath(value)
    if not raw or "\x00" in raw or not os.path.isabs(raw):
        raise AuthorityChildLaunchError(f"{field} must be a canonical absolute path")
    normalized = os.path.normpath(raw)
    if normalized != raw or normalized == os.path.sep or normalized.startswith("//"):
        raise AuthorityChildLaunchError(f"{field} must be a canonical absolute path")
    return Path(normalized)


def _engaged_runtime(context: ContractContext) -> tuple[object, object, Path]:
    context_module, runtime_module = _authority_modules()
    state = getattr(context, "state", None)
    if state != "engaged":
        raise AuthorityChildLaunchError("buffered authority children require an engaged context")
    validate = getattr(context_module, "validate_before_effect", None)
    if not callable(validate):
        raise AuthorityChildLaunchError("contract authority context cannot validate an effect")
    validate(context)
    pin = getattr(context, "runtime_pin", None)
    runtime_root = getattr(pin, "runtime_root", None)
    if pin is None or runtime_root is None:
        raise AuthorityChildLaunchError("engaged context has no verified runtime pin")
    return runtime_module, pin, _canonical_absolute_path(os.fspath(runtime_root), field="runtime root")


def _runtime_entry_path(runtime_root: Path, entry_path: str | os.PathLike[str]) -> Path:
    entry = _canonical_absolute_path(entry_path, field="runtime entry path")
    try:
        relative = entry.relative_to(runtime_root)
    except ValueError as exc:
        raise AuthorityChildLaunchError("runtime entry path is outside the pinned runtime root") from exc
    if not relative.parts or relative.parts[0] != "scripts" or entry.suffix != ".py":
        raise AuthorityChildLaunchError("runtime entry path is not a runtime-owned Python script")
    return entry


def _argv_text(values: Sequence[str], *, field: str) -> list[str]:
    result: list[str] = []
    for value in values:
        if type(value) is not str or "\x00" in value:
            raise AuthorityChildLaunchError(f"{field} contains an invalid argument")
        result.append(value)
    return result


def _python_executable(value: str | os.PathLike[str] | None) -> str:
    selected = sys.executable if value is None else os.fspath(value)
    if not selected or "\x00" in selected:
        raise AuthorityChildLaunchError("Python executable is invalid")
    return selected


def _bootstrap_literal(runtime_module: object, pin: object) -> str:
    literal = getattr(runtime_module, "authority_bootstrap_literal", None)
    if not callable(literal):
        raise AuthorityChildLaunchError("runtime does not provide a retained bootstrap literal")
    value = literal(pin)
    if type(value) is not str or not value or "\x00" in value:
        raise AuthorityChildLaunchError("runtime returned an invalid bootstrap literal")
    return value


def _runtime_pin_summary(runtime_module: object, pin: object) -> str:
    factory = getattr(runtime_module, "loaded_runtime_pin_summary", None)
    if not callable(factory):
        raise AuthorityChildLaunchError("runtime does not provide a compact pin summary")
    value = factory(pin)
    if type(value) is not dict:
        raise AuthorityChildLaunchError("runtime returned an invalid compact pin summary")
    try:
        encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise AuthorityChildLaunchError("runtime returned an invalid compact pin summary") from exc
    if not encoded or "\x00" in encoded:
        raise AuthorityChildLaunchError("runtime returned an invalid compact pin summary")
    return encoded


def python_entry_argv(
    context: ContractContext,
    entry_path: str | os.PathLike[str],
    entry_args: Sequence[str] = (),
    *,
    python_executable: str | os.PathLike[str] | None = None,
) -> list[str]:
    """Build the one supported buffered command for a runtime Python entry."""

    runtime_module, pin, runtime_root = _engaged_runtime(context)
    entry = _runtime_entry_path(runtime_root, entry_path)
    bridge = runtime_root / "scripts" / "contract_authority_bridge.py"
    runtime_summary = _runtime_pin_summary(runtime_module, pin)
    return [
        _python_executable(python_executable),
        "-I",
        "-B",
        "-c",
        _bootstrap_literal(runtime_module, pin),
        os.fspath(bridge),
        "python-entry",
        "--runtime-pin-summary",
        runtime_summary,
        "--path",
        os.fspath(entry),
        "--",
        *_argv_text(entry_args, field="runtime entry arguments"),
    ]


def python_stdin_argv(
    context: ContractContext,
    entry_args: Sequence[str] = (),
    *,
    python_executable: str | os.PathLike[str] | None = None,
) -> list[str]:
    """Build the buffered bridge command for caller-owned stdin Python bytes."""

    runtime_module, pin, runtime_root = _engaged_runtime(context)
    bridge = runtime_root / "scripts" / "contract_authority_bridge.py"
    runtime_summary = _runtime_pin_summary(runtime_module, pin)
    return [
        _python_executable(python_executable),
        "-I",
        "-B",
        "-c",
        _bootstrap_literal(runtime_module, pin),
        os.fspath(bridge),
        "python-stdin",
        "--runtime-pin-summary",
        runtime_summary,
        "--",
        *_argv_text(entry_args, field="stdin entry arguments"),
    ]


def shell_command(
    context: ContractContext,
    post_anchor_body: str,
    *,
    shell_executable: str | os.PathLike[str] = "/bin/zsh",
) -> list[str]:
    """Build an anchored zsh command for a runtime-owned child shell.

    ``post_anchor_body`` executes only after the rendered caller-owned loader
    has installed ``planveyor_source_runtime`` and that function has streamed the
    pinned ``scripts/planveyor.zsh`` facade.  It is a command body, not an
    authority transport; callers retain responsibility for quoting their own
    dynamic values before passing it here.
    """

    if type(post_anchor_body) is not str or "\x00" in post_anchor_body:
        raise AuthorityChildLaunchError("post-anchor shell body is invalid")
    selected_shell = os.fspath(shell_executable)
    if not selected_shell or "\x00" in selected_shell:
        raise AuthorityChildLaunchError("shell executable is invalid")
    runtime_module, pin, runtime_root = _engaged_runtime(context)
    render = getattr(runtime_module, "authority_shell_loader_literal", None)
    if not callable(render):
        raise AuthorityChildLaunchError("runtime does not provide a rendered shell loader")
    loader = render(pin)
    if type(loader) is not str or not loader or "\x00" in loader:
        raise AuthorityChildLaunchError("runtime returned an invalid shell loader")
    facade = runtime_root / "scripts" / "planveyor.zsh"
    runtime_summary = _runtime_pin_summary(runtime_module, pin)
    command = (
        "export PLANVEYOR_CHILD_SHELL_V1=planveyor-child-shell.v1\n"
        "export PLANVEYOR_RUNTIME_SOURCE_KIND=git\n"
        f"export PLANVEYOR_ROOT={shlex.quote(os.fspath(runtime_root))}\n"
        f"export PLANVEYOR_PROJECT_ROOT={shlex.quote(os.fspath(context.project_root))}\n"
    ) + loader
    if not command.endswith("\n"):
        command += "\n"
    command += (
        f"planveyor_source_runtime {shlex.quote(os.fspath(facade))} "
        f"{shlex.quote(runtime_summary)} || exit $?\n"
    )
    command += post_anchor_body
    return [selected_shell, "-dfc", command]


__all__ = [
    "AuthorityChildLaunchError",
    "python_entry_argv",
    "python_stdin_argv",
    "shell_command",
]
