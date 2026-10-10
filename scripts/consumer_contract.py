#!/usr/bin/env python3
"""Create, inspect and cautiously upgrade a sibling's Copier contract."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import stat
import subprocess
import sys
import tempfile

try:
    import yaml
except ImportError:  # Keep the CLI diagnostic actionable when bootstrap is incomplete.
    yaml = None

from contract_authority_snapshot import ContractAuthorityError, parse_local_marker_bytes

SOURCE_URL = "https://github.com/planveyor/planveyor.git"
MARKER = Path("docs/_meta/planveyor_contract_authority.v1.json")
ANSWERS = Path(".copier-answers.yml")
BOOTSTRAP_LOCK = "requirements-dev.lock"
COPIER_VERSION = "9.18.2"
LOCAL_HEADINGS = ("## Локальные правила стека", "## Разрешённое локальное переопределение процесса")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
CONFLICT = re.compile(rb"^(?:<{7}|={7}|>{7})(?:\s|$)", re.MULTILINE)
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
NOTICE_FIELDS = ("summary", "contract_changes", "engine_changes", "sibling_actions", "checks")
NOTICE_ROOT = "docs/contract_notices"
INIT_AUTHOR_NAME = "Planveyor Initializer"
INIT_AUTHOR_EMAIL = "planveyor-init@example.invalid"
INIT_IDENTITY_EDGE_CHARACTERS = frozenset('"\'\\,;:')


class ContractError(RuntimeError):
    pass


def die(message: str) -> None:
    raise ContractError(message)


def bootstrap_hint(runtime: Path) -> str:
    return (
        "Activate the Planveyor environment that already provides Python 3.12, Copier "
        f"{COPIER_VERSION} and PyYAML as pinned in {shlex.quote(os.fspath(runtime / BOOTSTRAP_LOCK))}, "
        f"then rerun the command; the current interpreter is {shlex.quote(sys.executable)}. "
        "Planveyor never installs dependencies itself or from a sibling project."
    )


def require_pyyaml(runtime: Path) -> None:
    if yaml is None:
        die("Missing PyYAML required for the consumer contract. " + bootstrap_hint(runtime))


def copier_executable(runtime: Path) -> str:
    executable = shutil.which("copier")
    if executable is None:
        die(
            f"Missing Copier {COPIER_VERSION} required for the consumer contract. "
            + bootstrap_hint(runtime)
        )
    version = command([executable, "--version"], env=process_env(runtime), check=False)
    expected = f"copier {COPIER_VERSION}"
    observed = version.stdout.strip() or version.stderr.strip() or f"exit status {version.returncode}"
    if version.returncode or version.stdout.strip() != expected:
        die(
            f"Copier {COPIER_VERSION} is required for the consumer contract; found {observed!r}. "
            + bootstrap_hint(runtime)
        )
    return executable


def require_consumer_dependencies(runtime: Path) -> None:
    require_pyyaml(runtime)
    copier_executable(runtime)


def copier_cache_home(runtime: Path) -> Path:
    """Return the Copier cache directory of one runtime root.

    Copier keys its template mirror by the public source URL alone, so runtimes
    that shared one cache would mix their refs and collide on mirror updates.
    """
    digest = hashlib.sha256(os.fsencode(runtime)).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"planveyor-copier-cache-{digest}"


def process_env(runtime: Path, *, copier: bool = False) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_") and key not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
    )
    if copier:
        env.update(
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0=f"url.{runtime.as_uri()}/.insteadOf",
            GIT_CONFIG_VALUE_0=SOURCE_URL,
            XDG_CACHE_HOME=os.fspath(copier_cache_home(runtime)),
        )
    return env


def command(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
            check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True,
                          stdin=subprocess.DEVNULL, check=False, timeout=300)
    if check and done.returncode:
        die(f"command failed ({done.returncode}): {' '.join(argv[:4])}: {done.stderr.strip() or done.stdout.strip()}")
    return done


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return command(["git", "-C", os.fspath(root), *args], env=process_env(root), check=check)


def git_inventory_bytes(root: Path, *args: str) -> bytes:
    done = subprocess.run(
        ["git", "-C", os.fspath(root), *args],
        env=process_env(root),
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=300,
    )
    if done.returncode:
        die(f"cannot read Git inventory ({done.returncode})")
    return done.stdout


def git_inventory_records(output: bytes) -> list[str]:
    if not output:
        return []
    if not output.endswith(b"\0"):
        die("cannot parse Git inventory")
    records = output[:-1].split(b"\0")
    if any(not record for record in records):
        die("cannot parse Git inventory")
    try:
        return [record.decode("utf-8", "strict") for record in records]
    except UnicodeDecodeError:
        die("cannot parse Git inventory")


def git_owned_paths(root: Path) -> set[str]:
    selected: set[str] = set()
    for arguments in (("ls-files", "-z"), ("ls-files", "--others", "--exclude-standard", "-z")):
        selected.update(git_inventory_records(git_inventory_bytes(root, *arguments)))
    return selected


def selected_path(root: Path, relative: str) -> tuple[Path | None, os.stat_result | None, str | None]:
    parts = relative.split("/")
    if (not relative or "\0" in relative or relative.startswith("/")
            or any(part in {"", ".", "..", ".git"} for part in parts)):
        return None, None, "invalid selected path"
    path = root
    for index, part in enumerate(parts):
        path = path / part
        try:
            metadata = path.lstat()
        except OSError:
            return None, None, "cannot inspect selected path"
        if stat.S_ISLNK(metadata.st_mode) or (index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode)):
            return None, None, "unsafe selected path"
    if not stat.S_ISREG(metadata.st_mode):
        return None, None, "unsafe selected path"
    return path, metadata, None


def same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino, left.st_mode) == (right.st_dev, right.st_ino, right.st_mode)


def read_selected_file(path: Path, expected: os.stat_result) -> tuple[bytes | None, str | None]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None, "cannot read selected path"
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not same_file_identity(expected, opened):
            return None, "selected path changed during inspection"
        remaining = expected.st_size + 1
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b"".join(chunks)
    except OSError:
        return None, "cannot read selected path"
    finally:
        os.close(descriptor)
    try:
        current = path.lstat()
    except OSError:
        return None, "cannot inspect selected path"
    if len(body) != expected.st_size or not stat.S_ISREG(current.st_mode) or not same_file_identity(expected, current):
        return None, "selected path changed during inspection"
    return body, None


def full_commit(runtime: Path, value: str) -> str:
    if not HEX40.fullmatch(value):
        die("source commit must be a full 40-character lowercase Git object ID")
    done = git(runtime, "rev-parse", "--verify", f"{value}^{{commit}}", check=False)
    if done.returncode or done.stdout.strip() != value:
        die(f"source commit is unavailable in this runtime: {value}")
    return value


def require_branch_or_tag(runtime: Path, value: str) -> None:
    """Refuse a source commit that no local branch or tag of the runtime contains.

    Copier reads the public source URL through a mirror cache keyed by that URL
    and refreshes an existing mirror with ``git remote update``, which fetches
    refs but not a detached HEAD; such a commit then fails inside Copier.
    """
    contained = git(runtime, "for-each-ref", "--count=1", "--format=%(refname)", "--contains", value,
                    "refs/heads", "refs/tags").stdout.strip()
    if not contained:
        die(
            f"source commit {value} is not on any branch or tag of the Planveyor runtime {runtime}: "
            "Copier fetches the template into its cache by refs, so a commit reachable only from a "
            "detached HEAD may be missing there. Check out a branch or tag that contains this commit "
            "(for example, git pull on main) and rerun the command."
        )


def resolve_answer_ref(runtime: Path, value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith("-") or "\n" in value:
        die("Copier answers contain an invalid _commit")
    done = git(runtime, "rev-parse", "--verify", f"{value}^{{commit}}", check=False)
    if done.returncode or not HEX40.fullmatch(done.stdout.strip()):
        die("Copier answers _commit cannot be resolved in the selected source")
    return done.stdout.strip()


def canonical_external(path: str, runtime: Path, *, must_exist: bool) -> Path:
    raw = Path(path)
    if not raw.is_absolute() or ".." in raw.parts:
        die("target must be an absolute canonical path")
    target = raw.resolve(strict=False)
    if target != raw:
        die(
            f"target must be a canonical physical path without symlinks: {raw} resolves to {target}; "
            "pass the resolved path instead (on macOS, for example, /private/tmp/... rather than /tmp/...)"
        )
    if target == runtime or runtime in target.parents:
        die(f"target must be a separate sibling path outside the Planveyor runtime {runtime}")
    if target.is_symlink() or not target.parent.is_dir():
        die("target parent must exist and target must not be a symlink")
    if must_exist and (not target.is_dir() or target.is_symlink()):
        die("target must be an existing physical directory")
    return target


def ensure_git_root(target: Path) -> None:
    done = git(target, "rev-parse", "--show-toplevel", check=False)
    if done.returncode or done.stdout.strip() != os.fspath(target):
        die("target is not an independent Git repository root")


def git_metadata_path(target: Path, *arguments: str, label: str) -> Path:
    done = git(target, "rev-parse", "--path-format=absolute", *arguments, check=False)
    raw = done.stdout.strip()
    if done.returncode or not raw:
        die(f"cannot resolve target Git {label}")
    path = Path(raw)
    if not path.is_absolute():
        die(f"target Git {label} is not an absolute path")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        die(f"cannot resolve target Git {label}: {exc}")


def ensure_private_git_metadata(target: Path) -> None:
    """Reject metadata that copytree would preserve as a shared Git control plane."""
    git_entry = target / ".git"
    if git_entry.is_symlink() or not git_entry.is_dir():
        die(
            "target uses linked-worktree or external Git metadata; consumer upgrade requires a private .git directory "
            "before a candidate is copied"
        )
    try:
        expected_git_dir = git_entry.resolve(strict=True)
    except OSError as exc:
        die(f"cannot resolve target .git directory: {exc}")
    git_dir = git_metadata_path(target, "--git-dir", label="directory")
    common_dir = git_metadata_path(target, "--git-common-dir", label="common directory")
    index = git_metadata_path(target, "--git-path", "index", label="index")
    if git_dir != expected_git_dir:
        die(
            "target uses external Git metadata; consumer upgrade requires a private .git directory "
            "before a candidate is copied"
        )
    if common_dir != git_dir:
        die(
            "target uses linked or shared Git metadata; consumer upgrade refuses it before copying "
            "a candidate because a candidate could change the original index"
        )
    expected_index = (git_dir / "index").resolve(strict=False)
    if index != expected_index or (git_dir / "index").is_symlink():
        die(
            "target uses external Git index metadata; consumer upgrade requires a private index "
            "before a candidate is copied"
        )
    def walk_error(error: OSError) -> None:
        die(f"cannot inspect target Git metadata: {error}")

    for parent, directories, files in os.walk(git_dir, followlinks=False, onerror=walk_error):
        for name in (*directories, *files):
            metadata = Path(parent) / name
            if metadata.is_symlink():
                die(
                    "target uses external Git metadata symlink; consumer upgrade requires private Git metadata "
                    "before a candidate is copied: " + os.fspath(metadata.relative_to(git_dir))
                )
    alternates = git_dir / "objects" / "info" / "alternates"
    if alternates.exists() or alternates.is_symlink():
        if not alternates.is_file():
            die(
                "target Git object alternates is not a regular empty file; consumer upgrade requires private Git "
                "metadata before a candidate is copied"
            )
        try:
            if alternates.read_bytes():
                die(
                    "target uses external Git object alternates; consumer upgrade requires private Git metadata "
                    "before a candidate is copied"
                )
        except OSError as exc:
            die(f"cannot inspect target Git object alternates: {exc}")


def path_occupied(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def file_map(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        if ".git" in path.relative_to(root).parts or not path.is_file():
            continue
        if path.is_symlink():
            die(f"managed contract symlink is not allowed: {path.relative_to(root)}")
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def bad_merge_state(root: Path, *, managed_paths: set[str] | None = None) -> list[str]:
    problems: list[str] = []
    if git(root, "ls-files", "-u").stdout.strip():
        problems.append("unmerged Git index")
    managed_paths = managed_paths or set()
    for relative in sorted(git_owned_paths(root) | managed_paths):
        path, metadata, error = selected_path(root, relative)
        if error is not None:
            problems.append(f"{error}: {relative}")
            continue
        if path.name.endswith(".rej"):
            problems.append(f"reject file: {relative}")
            continue
        if metadata.st_size > 2_000_000:
            if relative in managed_paths:
                problems.append(f"managed path is too large to scan: {relative}")
            continue
        body, error = read_selected_file(path, metadata)
        if error is not None:
            problems.append(f"{error}: {relative}")
            continue
        if CONFLICT.search(body):
            problems.append(f"conflict markers: {relative}")
    return problems


def marker_answers(target: Path, runtime: Path) -> tuple[object, dict[str, object]]:
    require_pyyaml(runtime)
    try:
        marker = parse_local_marker_bytes((target / MARKER).read_bytes())
    except (OSError, ContractAuthorityError) as exc:
        die(f"invalid or missing contract marker: {exc}")
    if not IDENTITY.fullmatch(marker.repository_id):
        die("marker repository_id is invalid")
    if marker.contract_root != "." or (marker.required_runtime_api.minimum, marker.required_runtime_api.maximum) != (5, 5):
        die("marker contract root or runtime API is incompatible")
    try:
        answers = yaml.safe_load((target / ANSWERS).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        die(f"invalid or missing Copier answers: {exc}")
    if not isinstance(answers, dict) or answers.get("_src_path") != SOURCE_URL:
        die("Copier answers source URL does not match the public Planveyor source")
    if answers.get("repository_id") != marker.repository_id:
        die("Copier answers repository_id differs from marker")
    full_commit(runtime, marker.source_commit)
    if resolve_answer_ref(runtime, answers.get("_commit")) != marker.source_commit:
        die("Copier answers _commit differs from marker source_commit")
    return marker, answers


def copier_env(runtime: Path) -> dict[str, str]:
    return process_env(runtime, copier=True)


def copier_copy(runtime: Path, target: Path, source_commit: str, repository_id: str) -> None:
    command([copier_executable(runtime), "copy", "--trust", "--defaults", "--data", f"repository_id={repository_id}",
             "--vcs-ref", source_commit, SOURCE_URL, os.fspath(target)], env=copier_env(runtime))


def rendered(runtime: Path, source_commit: str, repository_id: str) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, str]]:
    tmp = tempfile.TemporaryDirectory(prefix="planveyor-contract-render-")
    root = Path(tmp.name) / "contract"
    try:
        copier_copy(runtime, root, source_commit, repository_id)
        files = file_map(root)
    except Exception:
        tmp.cleanup()
        raise
    return tmp, root, files


def doctor(target: Path, runtime: Path, *, exact_runtime: bool = True,
           expected: str | None = None) -> dict[str, object]:
    require_consumer_dependencies(runtime)
    ensure_git_root(target)
    marker, _answers = marker_answers(target, runtime)
    require_branch_or_tag(runtime, marker.source_commit)
    runtime_commit = git(runtime, "rev-parse", "HEAD").stdout.strip()
    tmp, _root, expected_files = rendered(runtime, marker.source_commit, marker.repository_id)
    try:
        missing = sorted(path for path in expected_files if not (target / path).is_file())
        problems = bad_merge_state(target, managed_paths=set(expected_files) - set(missing))
        if expected is not None and marker.source_commit != expected:
            problems.append("marker source_commit differs from requested version")
        if exact_runtime and marker.source_commit != runtime_commit:
            problems.append(f"runtime commit {runtime_commit} differs from contract {marker.source_commit}")
        problems.extend(f"missing managed path: {path}" for path in missing)
    finally:
        tmp.cleanup()
    return {"state": "ok" if not problems else "blocked", "target": os.fspath(target),
            "source_commit": marker.source_commit, "runtime_commit": runtime_commit,
            "managed_paths": len(expected_files), "problems": problems}


def local_sections(root: Path, paths: set[str], *, required_paths: set[str] | None = None) -> dict[str, dict[str, bytes]]:
    required_paths = required_paths or set()
    selected: dict[str, dict[str, bytes]] = {}
    for rel in sorted(paths):
        path = root / rel
        try:
            body = path.read_bytes()
        except OSError as exc:
            if rel in required_paths:
                die(f"cannot read protected local section: {rel}: {exc}")
            continue
        lines = body.splitlines(keepends=True)
        sections: dict[str, bytes] = {}
        for heading in LOCAL_HEADINGS:
            heading_bytes = heading.encode("utf-8")
            indexes = [i for i, line in enumerate(lines) if line.rstrip(b"\r\n") == heading_bytes]
            if len(indexes) > 1:
                die(f"duplicate local section {heading}: {rel}")
            if not indexes:
                continue
            start = indexes[0]
            end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(b"## ")), len(lines))
            sections[heading] = b"".join(lines[start:end])
        if rel in required_paths or sections:
            try:
                body.decode("utf-8")
            except UnicodeDecodeError as exc:
                die(f"managed local section is not valid UTF-8: {rel}: {exc}")
        if sections:
            selected[rel] = sections
    return selected


def notice_text(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return not any(
        ordinal <= 0x1F
        or 0x7F <= ordinal <= 0x9F
        or ordinal in (0x2028, 0x2029)
        or 0xD800 <= ordinal <= 0xDFFF
        for ordinal in map(ord, value)
    )


def validate_notice(parsed: object, source: str) -> dict[str, object]:
    if not isinstance(parsed, dict) or not notice_text(parsed.get("summary")):
        die(f"invalid notice schema: {source}")
    for field in NOTICE_FIELDS[1:]:
        value = parsed.get(field)
        if not isinstance(value, list) or not all(notice_text(item) for item in value):
            die(f"invalid notice schema: {source}")
    return parsed


def notice_path(path: str) -> bool:
    return path.startswith(NOTICE_ROOT + "/") and path.endswith(".json")


def notice_changes(runtime: Path, *options: str) -> list[tuple[str, str, str]]:
    """Return (commit, status, path) for each notice directory change that git log reports."""
    output = git(
        runtime,
        "log",
        "--format=%H",
        "--name-status",
        "-z",
        "--no-renames",
        *options,
        "--",
        NOTICE_ROOT,
    ).stdout
    changes: list[tuple[str, str, str]] = []
    commit: str | None = None
    fields = output.split("\0")
    index = 0
    while index < len(fields):
        field = fields[index]
        if not field:
            index += 1
            continue
        if HEX40.fullmatch(field):
            commit = field
            index += 1
            continue
        if not commit:
            die("cannot parse notice history entry")
        status = field[1:] if field.startswith("\n") else field
        index += 1
        if len(status) != 1 or status not in "ACDMRTUXB" or index >= len(fields):
            die("cannot parse notice history entry")
        changes.append((commit, status, fields[index]))
        index += 1
    return changes


def notice_blobs(runtime: Path, commit: str) -> dict[str, str]:
    """Return the notice paths in the tree of commit with their object IDs."""
    output = git(runtime, "ls-tree", "-r", "-z", "--full-tree", commit, "--", NOTICE_ROOT).stdout
    blobs: dict[str, str] = {}
    for entry in filter(None, output.split("\0")):
        metadata, separator, path = entry.partition("\t")
        fields = metadata.split(" ")
        if not separator or len(fields) != 3:
            die("cannot parse notice tree entry")
        if notice_path(path):
            blobs[path] = fields[2]
    return blobs


def read_notice(runtime: Path, commit: str, path: str) -> dict[str, object]:
    blob = git(runtime, "show", f"{commit}:{path}", check=False)
    if blob.returncode:
        die(f"cannot read notice in source history: {path}@{commit}")
    try:
        parsed = json.loads(blob.stdout)
    except json.JSONDecodeError:
        die(f"invalid notice in source history: {path}@{commit}")
    return validate_notice(parsed, f"{path}@{commit}")


def notices(runtime: Path, old: str, new: str) -> list[dict[str, object]]:
    """Return each notice that the range old..new delivers, once.

    Every notice version that a commit of the range adds or changes against any
    of its parents is validated first, so a broken notice anywhere in the range
    history still refuses the upgrade.  The range delivers the notices whose
    text in the new tree differs from the old tree, new files included, and the
    notices that its first-parent line adds and removes again.  A notice that
    the old tree already has with the same text is not repeated, even when a
    merged branch forked before it.  Each notice comes with its text at the
    latest first-parent commit that added or changed it, where a merge counts
    only what it brings to that line.
    """
    revisions = f"{old}..{new}"
    validated: dict[tuple[str, str], dict[str, object]] = {}
    for commit, status, path in notice_changes(runtime, "--full-history", "--diff-merges=separate", revisions):
        if status != "D" and notice_path(path) and (commit, path) not in validated:
            validated[(commit, path)] = read_notice(runtime, commit, path)
    before = notice_blobs(runtime, old)
    after = notice_blobs(runtime, new)
    changed = {path for path, blob in after.items() if before.get(path) != blob}
    present = before.keys() | after.keys()
    arrivals: dict[str, str] = {}
    for commit, status, path in notice_changes(runtime, "--first-parent", "--diff-merges=first-parent", revisions):
        if status != "D" and notice_path(path) and (path in changed or path not in present):
            arrivals.setdefault(path, commit)
    # When old is off the first-parent line, a notice can differ from the old
    # tree without a first-parent change, for example after a merge that kept a
    # notice the old side deleted; such a notice arrives with new.
    for path in sorted(changed - arrivals.keys()):
        arrivals[path] = new
    result: list[dict[str, object]] = []
    for path, commit in arrivals.items():
        notice = validated[(commit, path)] if (commit, path) in validated else read_notice(runtime, commit, path)
        result.append({**notice, "commit": commit, "path": path})
    return result


def adaptation_plan(candidate: Path, runtime: Path, old: str, new: str,
                    changed_contract: list[str], changed_engine: list[str], selected_notices: list[dict[str, object]]) -> Path:
    now = datetime.now().astimezone()
    name = f"{now:%y%m%d_%H%M}_contract_upgrade_{old[:7]}_{new[:7]}.md"
    path = candidate / "docs/plans" / name
    if path.exists():
        die(f"adaptation plan already exists: {path}")
    template = candidate / "docs/plans/_template.md"
    body = template.read_text(encoding="utf-8")
    body = body.replace("# Plan: <TOPIC>", "# Plan: Адаптация контракта Planveyor", 1)
    body = body.replace("**Date:** YYYY-MM-DD HH:MM", f"**Date:** {now:%Y-%m-%d %H:%M %z}", 1)
    body = body.replace("**Stage:** UNCONFIRMED (Stage 1/2/3)", "**Stage:** Stage 1", 1)
    body = body.replace("**Priority:** UNCONFIRMED (P0/P1/P2)", "**Priority:** P1", 1)
    body = re.sub(r"\*\*Status:\*\* Architect initial draft \|[^\n]*", "**Status:** Architect initial draft", body, count=1)
    body = body.replace('"cluster": "UNCONFIRMED"', '"cluster": "process"', 1)
    body = body.replace("## Как я понял задачу\n", "## Как я понял задачу\nНужно принять новый контракт Planveyor, проверить локальные правила стека и выполнить нужную адаптацию в этом sibling. Автоматическое слияние не закрывает этот план.\n", 1)
    body = body.replace("## Problem\n", f"## Problem\n- Контракт источника меняется с `{old}` на `{new}`; точный результат и локальные overrides требуют проверки.\n", 1)
    body = body.replace("## Solution (high level)\n", "## Solution (high level)\n- Проверить управляемые файлы, локальные секции, извещения и engine changes; провести обычный review и acceptance.\n", 1)
    items = [f"- `{p}`" for p in changed_contract] or ["- N/A (why=template files unchanged; engine-only update)"]
    engine = [f"- `{p}`" for p in changed_engine] or ["- N/A (why=no engine file changes)"]
    notice_rows = [f"- `{item['path']}` at `{item['commit']}`: {item['summary']}" for item in selected_notices] or ["- N/A (why=no notices in range)"]
    body = body.replace("## Scope\n", "## Scope\n- From source commit: `" + old + "`\n- To source commit: `" + new + "`\n- Изменённые файлы контракта:\n" + "\n".join(items) + "\n- Изменения движка:\n" + "\n".join(engine) + "\n- Извещения диапазона:\n" + "\n".join(notice_rows) + "\n", 1)
    actions = [str(x) for n in selected_notices for x in n["sibling_actions"]]
    checks = [str(x) for n in selected_notices for x in n["checks"]]
    body = body.replace("## Tests\n", "## Tests\n- Проверить локальные stack/Reviewer overrides и точный diff.\n" + "\n".join(f"- {x}" for x in checks) + "\n", 1)
    body = body.replace("## Commands\n", "## Commands\n- `\"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor\" --project \"$PWD\" planveyor_consumer_doctor`\n", 1)
    body = body.replace("## Evidence (chronological, append-only)\n", "## Evidence (chronological, append-only)\n- План создан механическим обновлением; проверки sibling и решения Architect/Reviewer ещё открыты.\n" + "\n".join(f"- Действие: {x}" for x in actions) + "\n", 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    lint = command([os.fspath(runtime / "bin/planveyor"), "--project", os.fspath(candidate),
                    "planveyor_plan_lint", os.fspath(path.relative_to(candidate))],
                   env=process_env(runtime), check=False)
    if lint.returncode:
        die(f"generated adaptation plan failed lint: {lint.stdout.strip()} {lint.stderr.strip()}")
    return path


def valid_init_identity(value: object, *, email: bool) -> bool:
    if not notice_text(value):
        return False
    assert isinstance(value, str)
    if value != value.strip() or "<" in value or ">" in value:
        return False
    if email and any(character.isspace() for character in value):
        return False
    return value[0] not in INIT_IDENTITY_EDGE_CHARACTERS and value[-1] not in INIT_IDENTITY_EDGE_CHARACTERS


def init_identity(author_name: object | None, author_email: object | None) -> tuple[str, str]:
    if author_name is None and author_email is None:
        return INIT_AUTHOR_NAME, INIT_AUTHOR_EMAIL
    if author_name is None or author_email is None:
        die("init author name and email must be supplied together")
    if not valid_init_identity(author_name, email=False) or not valid_init_identity(author_email, email=True):
        die("invalid init identity")
    assert isinstance(author_name, str) and isinstance(author_email, str)
    return author_name, author_email


def plain_directory_mode() -> int:
    """Return the mode that a plain mkdir gives a new directory under the current umask."""
    mask = os.umask(0o077)
    os.umask(mask)
    return 0o777 & ~mask


def init(runtime: Path, target: Path, selected: str, *, author_name: str | None = None,
         author_email: str | None = None, save_identity: bool = False) -> dict[str, object]:
    if save_identity and (author_name is None or author_email is None):
        die("saving init identity requires an explicit author name and email")
    author_name, author_email = init_identity(author_name, author_email)
    require_consumer_dependencies(runtime)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        die("existing nonempty target is preserved")
    repository_id = target.name
    if not IDENTITY.fullmatch(repository_id) or repository_id == "default":
        die("target directory name is not a supported repository_id")
    selected = full_commit(runtime, selected)
    require_branch_or_tag(runtime, selected)
    candidate = Path(tempfile.mkdtemp(prefix=f".{target.name}-init-", dir=target.parent))
    try:
        # mkdtemp creates a private 0700 directory; the sibling root gets the mode of a plain mkdir.
        candidate.chmod(plain_directory_mode())
        copier_copy(runtime, candidate, selected, repository_id)
        marker, _ = marker_answers(candidate, runtime)
        if marker.source_commit != selected:
            die("Copier marker source_commit differs from selected commit")
        git(candidate, "init", "-b", "main")
        if save_identity:
            # Configure only the private candidate, before the atomic target swap.
            git(candidate, "config", "--local", "user.name", author_name)
            git(candidate, "config", "--local", "user.email", author_email)
        git(candidate, "add", "--all")
        command(["git", "-C", os.fspath(candidate), "-c", f"user.name={author_name}",
                 "-c", f"user.email={author_email}", "commit", "-m", "Initialize Planveyor sibling contract"],
                env=process_env(runtime))
        result = doctor(candidate, runtime, exact_runtime=False, expected=selected)
        if result["state"] != "ok":
            die("generated sibling failed doctor: " + "; ".join(result["problems"]))
        if target.exists():
            target.rmdir()
        candidate.rename(target)
        result["target"] = os.fspath(target)
        return result
    except Exception:
        # Retain a failed candidate for inspection; never replace the target.
        print(f"candidate retained: {candidate}", file=sys.stderr)
        raise


def upgrade_warnings(target: Path, backup: Path) -> list[str]:
    return [
        "Finish active sibling role and shell sessions before an upgrade; directory replacement leaves "
        "open sessions in the backup.",
        f"Directory swap complete: reopen the sibling at {target}; the previous directory is retained at {backup}.",
    ]


def upgrade(runtime: Path, target: Path, selected: str, *, accept_candidate: bool = False) -> dict[str, object]:
    require_consumer_dependencies(runtime)
    ensure_git_root(target)
    ensure_private_git_metadata(target)
    marker, _ = marker_answers(target, runtime)
    old = marker.source_commit
    new = full_commit(runtime, selected)
    if old == new:
        die("contract already uses the selected source commit")
    if git(runtime, "merge-base", "--is-ancestor", old, new, check=False).returncode:
        die("selected source commit is not a descendant of the saved source commit")
    # The saved commit is an ancestor of the selected one, so this covers both renders.
    require_branch_or_tag(runtime, new)
    candidate = target.parent / f".{target.name}-upgrade-{new[:12]}"
    backup = target.parent / f".{target.name}-before-{new[:12]}"
    if path_occupied(backup):
        die(f"backup path already exists: {backup}")
    if accept_candidate:
        if not candidate.is_dir() or candidate.is_symlink():
            die(f"candidate to accept does not exist: {candidate}")
        ensure_git_root(candidate)
        ensure_private_git_metadata(candidate)
        original_head = git(target, "rev-parse", "HEAD").stdout.strip()
        if git(candidate, "merge-base", "--is-ancestor", original_head, "HEAD", check=False).returncode:
            die("candidate Git history does not descend from the original sibling")
        if git(candidate, "status", "--porcelain=v1", "--untracked-files=all").stdout:
            die("candidate must be reviewed and committed before acceptance")
    elif path_occupied(candidate):
        die(f"candidate path already exists: {candidate}; resolve it and use --accept-candidate")
    before_status = git(target, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if before_status:
        die("sibling has uncommitted changes or conflict indicators; commit or resolve them first")
    old_tmp, old_root, old_files = rendered(runtime, old, marker.repository_id)
    new_tmp, _new_root, new_files = rendered(runtime, new, marker.repository_id)
    try:
        removed = sorted(set(old_files) - set(new_files))
        if removed and set(new_files) - set(old_files):
            die("managed paths disappear or rename before Copier: " + ", ".join(removed))
        for rel in removed:
            contents: list[tuple[bytes, int]] = []
            for root in (old_root, target):
                path, metadata, error = selected_path(root, rel)
                if error is not None:
                    die(f"managed path cannot be removed before Copier: {rel}: {error}")
                assert path is not None and metadata is not None
                body, error = read_selected_file(path, metadata)
                if error is not None:
                    die(f"managed path cannot be removed before Copier: {rel}: {error}")
                assert body is not None
                contents.append((body, stat.S_IMODE(metadata.st_mode)))
            if contents[0] != contents[1]:
                die(f"managed path cannot be removed before Copier: {rel}: bytes or permissions differ from old render")
        missing = sorted(path for path in old_files if not (target / path).is_file())
        if missing:
            die("missing managed paths before Copier: " + ", ".join(missing))
        required_local_paths = set(local_sections(old_root, set(old_files)))
        preserved = local_sections(target, set(old_files), required_paths=required_local_paths)
        for rel in removed:
            if rel in required_local_paths or rel in preserved:
                die(f"managed path cannot be removed before Copier: {rel}: protected local section")
        if bad_merge_state(target, managed_paths=set(old_files)):
            die("sibling has uncommitted changes or conflict indicators; commit or resolve them first")
        changed_contract = sorted(path for path in set(old_files) | set(new_files)
                                  if old_files.get(path) != new_files.get(path))
    finally:
        old_tmp.cleanup()
        new_tmp.cleanup()
    changed_engine = git(runtime, "diff", "--name-only", old, new, "--", "scripts", "bin", "Makefile").stdout.splitlines()
    selected_notices = notices(runtime, old, new)
    if not accept_candidate:
        shutil.copytree(target, candidate, symlinks=True)
    try:
        done = None
        if not accept_candidate:
            done = command([copier_executable(runtime), "update", "--trust", "--defaults", "--conflict", "inline", "--vcs-ref", new,
                            os.fspath(candidate)], env=copier_env(runtime), check=False)
        if done is not None and done.returncode:
            problems = [f"Copier exited {done.returncode}: {done.stderr.strip()}"]
        else:
            problems = []
        problems.extend(f"removed managed path still exists: {rel}" for rel in removed
                        if path_occupied(candidate / rel))
        candidate_sections = local_sections(
            candidate,
            required_local_paths | set(preserved),
            required_paths=required_local_paths,
        )
        for rel, sections in preserved.items():
            after = candidate_sections.get(rel, {})
            for heading, body in sections.items():
                if after.get(heading) != body:
                    problems.append(f"local text changed or disappeared: {rel} / {heading}")
        problems.extend(bad_merge_state(candidate, managed_paths=set(new_files)))
        if problems:
            return {"state": "blocked", "candidate": os.fspath(candidate), "target": os.fspath(target),
                    "from_commit": old, "to_commit": new, "problems": problems,
                    "resolution": "Resolve and review the candidate, commit it, then rerun upgrade with --accept-candidate."}
        checked = doctor(candidate, runtime, exact_runtime=False, expected=new)
        if checked["state"] != "ok":
            return {"state": "blocked", "candidate": os.fspath(candidate), "target": os.fspath(target),
                    "from_commit": old, "to_commit": new, "problems": checked["problems"],
                    "resolution": "Resolve and review the candidate, commit it, then rerun upgrade with --accept-candidate."}
        plan = adaptation_plan(candidate, runtime, old, new, changed_contract, changed_engine, selected_notices)
        target.rename(backup)
        try:
            candidate.rename(target)
        except OSError as exc:
            try:
                backup.rename(target)
            except OSError as rollback:
                die(
                    "candidate replacement failed and the original sibling could not be restored: "
                    f"replacement={exc}; rollback={rollback}"
                )
            die(f"candidate replacement failed; original sibling restored from backup: {exc}")
        return {"state": "updated_pending_adaptation", "target": os.fspath(target),
                "backup": os.fspath(backup), "plan": os.fspath(target / plan.relative_to(candidate)),
                "from_commit": old, "to_commit": new, "contract_changes": changed_contract,
                "engine_changes": changed_engine, "notices": selected_notices,
                "warnings": upgrade_warnings(target, backup)}
    except Exception:
        print(f"candidate retained: {candidate}", file=sys.stderr)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True)
    sub = parser.add_subparsers(dest="operation", required=True)
    create = sub.add_parser("init")
    create.add_argument("target")
    create.add_argument("--source-commit", required=True)
    create.add_argument("--author-name", help="author name of the init commit; pass with --author-email")
    create.add_argument("--author-email", help="author email of the init commit; pass with --author-name; without both flags the author is " + f"{INIT_AUTHOR_NAME} <{INIT_AUTHOR_EMAIL}>")
    create.add_argument("--save-identity", action="store_true", help="save the explicitly supplied identity in the new sibling's local Git config")
    inspect = sub.add_parser("doctor")
    inspect.add_argument("target")
    change = sub.add_parser("upgrade")
    change.add_argument("target")
    change.add_argument("--source-commit", required=True)
    change.add_argument("--accept-candidate", action="store_true")
    args = parser.parse_args(argv)
    runtime = Path(args.runtime_root).resolve(strict=True)
    try:
        ensure_git_root(runtime)
        target = canonical_external(args.target, runtime, must_exist=args.operation != "init")
        if args.operation == "init":
            payload = init(runtime, target, args.source_commit, author_name=args.author_name,
                           author_email=args.author_email, save_identity=args.save_identity)
            if args.author_name is None and args.author_email is None:
                print(
                    f"note: init commit author is {INIT_AUTHOR_NAME} <{INIT_AUTHOR_EMAIL}>; pass --author-name "
                    "and --author-email together to sign it with your own identity.",
                    file=sys.stderr,
                )
        elif args.operation == "doctor":
            payload = doctor(target, runtime)
        else:
            print(
                "warning: upgrade swaps the sibling directory through a retained backup. Finish active sibling "
                "role and shell sessions before continuing, then reopen the sibling after success.",
                file=sys.stderr,
            )
            payload = upgrade(runtime, target, args.source_commit, accept_candidate=args.accept_candidate)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if payload["state"] in {"ok", "updated_pending_adaptation"} else 3
    except ContractError as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
