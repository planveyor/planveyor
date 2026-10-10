"""Disposable repositories shared by contract-authority integration tests.

Fixtures copy the candidate source bytes into a new Git repository. They never
activate the source checkout or an Owner repository.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterable

SOURCE_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_RUNTIME_INPUTS = (
    "docs/_meta/runner_selection_resolution.v1.json",
)

PLANVEYOR_MERGE_GATE_POLICY_PATH = "docs/_meta/planveyor_merge_gate_policy.v1.json"
PLANVEYOR_MERGE_GATE_POLICY_SCHEMA = "planveyor_merge_gate_policy.v1"
def planveyor_merge_gate_policy(
    *,
    modes: tuple[str, ...] | None = None,
    ledger_required: bool = True,
    doc_lint_argv: tuple[str, ...] = ("planveyor_doc_lint",),
) -> bytes:
    """Build a finite v1 policy with an optional declared consumer schema gate."""

    commands: list[dict[str, object]] = [
        {"id": "document_lint", "argv": list(doc_lint_argv)},
    ]
    steps: list[dict[str, object]] = []
    if modes is not None:
        mode_rows: list[dict[str, str]] = []
        commands.append({"id": "consumer_schema_check", "argv": ["consumer_schema_check"]})
        for index, mode in enumerate(modes):
            precheck = f"consumer_schema_{index}_precheck"
            apply = f"consumer_schema_{index}_apply"
            commands.extend(
                [
                    {"id": precheck, "argv": ["consumer_schema_precheck", mode]},
                    {"id": apply, "argv": ["consumer_schema_apply", mode]},
                ]
            )
            mode_rows.append({"mode": mode, "precheck_command_id": precheck, "apply_command_id": apply})
        commands.append({"id": "consumer_schema_resolve", "argv": ["consumer_schema_resolve"]})
        steps.append(
            {
                "id": "step:migrations_gate",
                "migration": {
                    "change_probe": "consumer_schema_paths.v1",
                    "check_command_id": "consumer_schema_check",
                    "modes": mode_rows,
                    "merge_command_id": "consumer_schema_resolve",
                },
            }
        )
    steps.extend(
        [
        {"id": "step:review_range"},
        {"id": "step:merge_notes"},
        {"id": "step:plan_harvest"},
        {"id": "step:canon_sweep"},
        {"id": "step:packetization_gate"},
        {"id": "step:docs_finalize"},
        {"id": "step:doc_lint", "command_id": "document_lint"},
        ]
    )
    if ledger_required:
        commands.append({"id": "ledger_lint", "argv": ["consumer_ledger_lint"]})
        steps.append({"id": "step:ledger_lint", "command_id": "ledger_lint"})
    steps.extend(
        [
            {"id": "step:post_merge_audit"},
            {"id": "step:docs_hygiene_archive"},
            {"id": "step:docs_hygiene_suggest"},
            {"id": "step:ready_to_push"},
        ]
    )
    payload = {
        "schema": PLANVEYOR_MERGE_GATE_POLICY_SCHEMA,
        "repository_id": "planveyor",
        "steps": steps,
        "commands": commands,
        "ledger_required": ledger_required,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def git_environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_AUTHOR_NAME="Authority fixture",
        GIT_AUTHOR_EMAIL='authority-fixture' + '@' + 'example' + '.' + 'invalid',
        GIT_COMMITTER_NAME="Authority fixture",
        GIT_COMMITTER_EMAIL='authority-fixture' + '@' + 'example' + '.' + 'invalid',
        LC_ALL="C",
    )
    return env


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false",
         "-C", str(root), *arguments],
        env=git_environment(), capture_output=True, text=True, check=True, timeout=20,
    )
    return result.stdout.strip()


def commit_all(root: Path, message: str = "fixture") -> str:
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--allow-empty", "-m", message)
    return git(root, "rev-parse", "HEAD")


def write(root: Path, relative_path: str, data: bytes | str, *, executable: bool = False) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    path.chmod(0o755 if executable else 0o644)
    return path


def tree_snapshot(root: Path) -> dict[str, tuple[int, str]]:
    """Fixture objects, including empty directories, Git, and runtime state."""
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            snapshot[path.relative_to(root).as_posix()] = (
                path.lstat().st_mode, os.readlink(path),
            )
        elif path.is_file():
            snapshot[path.relative_to(root).as_posix()] = (
                path.stat().st_mode, hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        elif path.is_dir():
            snapshot[path.relative_to(root).as_posix()] = (path.stat().st_mode, "directory")
    return snapshot


def shell_loader_literal(runtime_root: Path) -> str:
    """Render the fixture caller's chosen loader, outside its runtime pin."""
    template = (runtime_root / "scripts/contract_authority_shell_loader.zsh").read_text()
    bootstrap = (runtime_root / "scripts/contract_authority_bootstrap.py").read_text()
    placeholder = "@PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL@"
    if template.count(placeholder) != 1:
        raise ValueError("shell loader template must contain one bootstrap placeholder")
    return template.replace(placeholder, bootstrap) + "\n"


class AuthorityFixture:
    def __init__(self, *, identity: str = "planveyor") -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="planveyor-authority-")
        self.root = Path(self.temporary.name).resolve()
        self.runtime_root = self.root / "planveyor"
        self.target_root = self.root / "consumers" / identity
        self.home = self.root / "home"
        self.home.mkdir()
        self.child_tmp = self.root / "child_tmp"
        self.child_tmp.mkdir()
        self.identity = identity.replace("-", "_")
        for repo in (self.runtime_root, self.target_root):
            repo.mkdir(parents=True)
            git(repo, "init", "--quiet", "--object-format=sha1")
        self._copy_runtime()
        self.runtime_commit = commit_all(self.runtime_root, "candidate runtime")
        write(self.target_root, "README.md", "Disposable target.\n")
        commit_all(self.target_root, "legacy target")

    def _copy_runtime(self) -> None:
        repo_root_result = subprocess.run(
            ["git", "-C", str(SOURCE_ROOT), "rev-parse", "--show-toplevel"],
            env=git_environment(), capture_output=True, text=True, check=False, timeout=20,
        )
        repo_root = (
            Path(repo_root_result.stdout.strip()).resolve()
            if repo_root_result.returncode == 0 and repo_root_result.stdout.strip()
            else None
        )
        if repo_root == SOURCE_ROOT.resolve():
            result = subprocess.run(
                ["git", "-C", str(SOURCE_ROOT), "ls-files", "--cached", "--others",
                 "--exclude-standard", "-z", "--", "scripts", "private_shell", *EXTERNAL_RUNTIME_INPUTS],
                env=git_environment(), capture_output=True, check=True, timeout=20,
            )
            relative_paths = {os.fsdecode(raw) for raw in result.stdout.split(b"\0") if raw}
        else:
            # Candidate snapshots live below an enclosing source worktree and
            # are deliberately ignored by its Git index.  Copy their current
            # source bytes directly, rather than silently producing an empty
            # runtime fixture from the enclosing repository's pathspec.
            relative_paths = {
                source.relative_to(SOURCE_ROOT).as_posix()
                for source_root in ("scripts", "private_shell")
                for source in (SOURCE_ROOT / source_root).rglob("*")
                if source.is_file()
                and "__pycache__" not in source.parts
                and source.suffix != ".pyc"
            }
            relative_paths.update(
                relative
                for relative in EXTERNAL_RUNTIME_INPUTS
                if (SOURCE_ROOT / relative).is_file()
            )
        for relative in sorted(relative_paths):
            source = SOURCE_ROOT / relative
            if not source.is_file():
                continue
            target = self.runtime_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)

    @staticmethod
    def _local_fixture_path(contract_root: str, logical: str) -> str:
        if contract_root == ".":
            return logical
        if (
            not contract_root
            or contract_root.startswith("/")
            or contract_root.endswith("/")
            or "\\" in contract_root
            or any(part in {"", ".", ".."} for part in contract_root.split("/"))
        ):
            raise ValueError("fixture contract_root must be normalized relative POSIX text")
        return f"{contract_root}/{logical}"

    def populate(self, paths: Iterable[str], *, write_root: str = ".") -> None:
        """Create logical fixture carriers at the requested physical root."""
        for relative in paths:
            target_relative = self._local_fixture_path(write_root, relative)
            if relative.startswith("docs/tools/prompts/"):
                role = Path(relative).name.split("_", 1)[0]
                body = f"# Fixture prompt\nRead docs/roles/{role}.md.\nTARGET_ONLY:{relative}\n"
            elif relative.startswith("docs/roles/"):
                body = f"# Fixture role\n\n## Rules\n- TARGET_ONLY:{relative}\n"
            elif relative == "AGENTS.md":
                body = "# Fixture instructions\nAll contract sources belong to this target.\n"
            elif (SOURCE_ROOT / relative).is_file():
                write(self.target_root, target_relative, (SOURCE_ROOT / relative).read_bytes())
                continue
            else:
                body = f"# Fixture contract\nTARGET_ONLY:{relative}\n"
            write(self.target_root, target_relative, body)

    def activate(
        self,
        paths: Iterable[str],
        *,
        overrides: dict[str, str | bytes] | None = None,
        required_runtime_api: tuple[int, int] = (3, 3),
    ) -> None:
        """Commit a manifest and marker only in this disposable target."""
        ordered = sorted(set(paths))
        self.populate(ordered)
        for relative, data in (overrides or {}).items():
            if relative not in ordered:
                raise ValueError("fixture override is not a declared carrier")
            write(self.target_root, relative, data)
        commit_all(self.target_root, "inert mechanical carriers")
        rows = []
        for relative in ordered:
            path = self.target_root / relative
            data = path.read_bytes()
            rows.append({
                "path": relative,
                "mode": "100755" if path.stat().st_mode & 0o111 else "100644",
                "blob_oid": git(self.target_root, "rev-parse", f"HEAD:{relative}"),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        write(self.target_root, "docs/_meta/contract_sources.v1.json",
              json.dumps({"schema_version": 1, "required_content": rows}, sort_keys=True) + "\n")
        marker = {
            "schema_version": 1,
            "repository_id": self.identity,
            "authority_mode": "target-local",
            "contract_root": ".",
            "required_runtime_api": {
                "minimum": required_runtime_api[0],
                "maximum": required_runtime_api[1],
            },
            "closure_manifest": "docs/_meta/contract_sources.v1.json",
            "source_baseline": {"repository_id": "planveyor", "commit": self.runtime_commit},
        }
        write(self.target_root, "docs/_meta/planveyor_contract_authority.v1.json",
              json.dumps(marker, sort_keys=True) + "\n")
        commit_all(self.target_root, "activate disposable target")

    def activate_local(
        self,
        paths: Iterable[str],
        *,
        overrides: dict[str, str | bytes] | None = None,
        contract_root: str = ".",
        required_runtime_api: tuple[int, int] = (5, 5),
    ) -> None:
        ordered = tuple(dict.fromkeys(paths))
        self.populate(ordered, write_root=contract_root)
        for relative, data in (overrides or {}).items():
            if relative not in ordered:
                raise ValueError("fixture override is not a local content carrier")
            write(self.target_root, self._local_fixture_path(contract_root, relative), data)
        commit_all(self.target_root, "local fixture content")
        marker = {
            "schema_version": 3,
            "source_commit": self.runtime_commit,
            "repository_id": self.identity,
            "authority_mode": "target-local",
            "contract_root": contract_root,
            "required_runtime_api": {"minimum": required_runtime_api[0], "maximum": required_runtime_api[1]},
        }
        write(self.target_root, "docs/_meta/planveyor_contract_authority.v1.json", json.dumps(marker, sort_keys=True) + "\n")

    def activate_planveyor(
        self,
        paths: Iterable[str],
        *,
        overrides: dict[str, str | bytes] | None = None,
        required_runtime_api: tuple[int, int] = (5, 5),
        merge_policy: str | bytes | None = None,
        include_merge_policy: bool | None = None,
        contract_root: str = ".",
    ) -> None:
        """Activate a Planveyor fixture with its source-owned required carriers."""

        if self.identity != "planveyor":
            raise ValueError("activate_planveyor requires a planveyor fixture identity")
        ordered = tuple(paths)
        selected_overrides = dict(overrides or {})
        needs_merge_policy = required_runtime_api[0] >= 4 if include_merge_policy is None else include_merge_policy
        if needs_merge_policy:
            if PLANVEYOR_MERGE_GATE_POLICY_PATH in selected_overrides and merge_policy is not None:
                raise ValueError("merge_policy must be passed once")
            selected_overrides.setdefault(
                PLANVEYOR_MERGE_GATE_POLICY_PATH,
                planveyor_merge_gate_policy() if merge_policy is None else merge_policy,
            )
        self.activate_local(
            (*ordered, *((PLANVEYOR_MERGE_GATE_POLICY_PATH,) if needs_merge_policy else ())),
            overrides=selected_overrides,
            contract_root=contract_root,
            required_runtime_api=required_runtime_api,
        )

    def environment(self) -> dict[str, str]:
        env = git_environment()
        for key in tuple(env):
            if key.startswith(("PLANVEYOR_", "_PLANVEYOR_", "ZCODE_", "CODEX_")) or key in {
                "PYTHONPATH", "PYTHONHOME", "TMPDIR", "TMPPREFIX", "ZDOTDIR",
            }:
                env.pop(key)
        env.update(
            HOME=str(self.home),
            TMPDIR=str(self.child_tmp),
            TMPPREFIX=str(self.child_tmp / "zsh"),
            PLANVEYOR_ROOT=str(self.runtime_root),
            PYTHONDONTWRITEBYTECODE="1",
        )
        return env

    def shell_loader(self) -> str:
        """Caller-selected literal; fixture/runtime attestation starts inside it.

        Tests pass this text to zsh's command argument instead of claiming that
        an already selected raw repository source can attest itself.
        """
        return shell_loader_literal(self.runtime_root)

    def close(self) -> None:
        self.temporary.cleanup()

    def __enter__(self) -> "AuthorityFixture":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
