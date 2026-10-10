#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import contract_authority_children
from contract_authority_context import context_for_reader, context_to_json

if TYPE_CHECKING:
    from contract_authority_context import ContractContext


PLAN_ROOT_PREFIX = "docs/plans/"
EXCLUDED_PLAN_PATHS = {"docs/plans/README.md"}
ALL_ZERO_SHA_RE = re.compile(r"^0+$")


def run_git(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def filter_plan_paths(paths: list[str]) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = raw_path.strip()
        if not path.startswith(PLAN_ROOT_PREFIX) or not path.endswith(".md"):
            continue
        relative_path = path.removeprefix(PLAN_ROOT_PREFIX)
        if any(part.startswith("_") for part in relative_path.split("/")):
            continue
        if path in EXCLUDED_PLAN_PATHS:
            continue
        if path in seen:
            continue
        seen.add(path)
        filtered.append(path)
    return filtered


def default_base_ref(root: Path) -> str:
    env_base = os.environ.get("PLAN_LINT_BASE", "").strip()
    if env_base and not ALL_ZERO_SHA_RE.fullmatch(env_base):
        return env_base
    try:
        return run_git(root, ["rev-parse", "--verify", "HEAD~1"])
    except subprocess.CalledProcessError:
        return run_git(root, ["rev-list", "--max-parents=0", "HEAD"])


def changed_plan_paths(root: Path, base: str, head: str) -> list[str]:
    raw = run_git(root, ["diff", "--name-only", "--diff-filter=ACMR", base, head, "--", "docs/plans"])
    paths = [line for line in raw.splitlines() if line.strip()]
    return filter_plan_paths(paths)


def resolve_plan_lint_path(root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return root / path


def run_plan_lint(
    root: Path,
    plan_lint_path: Path,
    plan_paths: list[str],
    *,
    context: ContractContext | None = None,
) -> int:
    authority_context = context_for_reader(root, context)
    if authority_context.state == "engaged":
        command = contract_authority_children.python_entry_argv(
            authority_context,
            plan_lint_path,
            plan_paths,
            python_executable=sys.executable,
        )
    else:
        # Preserve the long-standing raw legacy launch exactly until the
        # target opts into an engaged authority context.
        command = [sys.executable, "-B", str(plan_lint_path), *plan_paths]
    run_kwargs: dict[str, object] = {"cwd": root}
    if authority_context.state == "engaged":
        child_env = os.environ.copy()
        child_env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = context_to_json(authority_context)
        run_kwargs["env"] = child_env
    result = subprocess.run(command, **run_kwargs)
    return result.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run plan_lint.py only for changed docs/plans/*.md files.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--base", default="", help="Base ref/SHA. Defaults to PLAN_LINT_BASE or previous commit.")
    parser.add_argument("--head", default=os.environ.get("PLAN_LINT_HEAD", "HEAD"), help="Head ref/SHA.")
    parser.add_argument("--plan-lint", default="scripts/plan_lint.py", help="Path to plan_lint.py.")
    parser.add_argument("--print-only", action="store_true", help="Print selected plan paths and do not run lint.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    base = args.base.strip() or default_base_ref(root)
    if ALL_ZERO_SHA_RE.fullmatch(base):
        base = default_base_ref(root)
    head = args.head.strip() or "HEAD"
    plan_paths = changed_plan_paths(root, base, head)

    if args.print_only:
        for path in plan_paths:
            print(path)
        return 0

    if not plan_paths:
        print("plan-lint-changed: no changed docs/plans/*.md files")
        return 0

    print("plan-lint-changed: linting " + ", ".join(plan_paths))
    return run_plan_lint(root, resolve_plan_lint_path(root, args.plan_lint), plan_paths)


if __name__ == "__main__":
    raise SystemExit(main())
