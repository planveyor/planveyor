#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def _default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def _uuid7(ms: int | None = None) -> str:
    """
    Generate a UUIDv7 (RFC 9562) string without external deps.
    """
    if ms is None:
        ms = int(time.time() * 1000)
    ts48 = ms & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (ts48 << 80) | (0x7 << 76) | (rand_a << 64) | (0x2 << 62) | rand_b
    return str(uuid.UUID(int=value))


def _iter_rollout_files(codex_home: Path, sid: str) -> list[Path]:
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.exists():
        return []
    files = list(sessions_dir.rglob(f"rollout-*-{sid}.jsonl"))
    if files:
        return sorted(files)
    # Fallback for older/variant names.
    files = list(sessions_dir.rglob(f"*{sid}*.jsonl"))
    return sorted([p for p in files if p.is_file()])


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _clone_one_rollout(
    *,
    src_path: Path,
    dst_path: Path,
    old_sid: str,
    new_sid: str,
    originator: str,
    source: str,
    write: bool,
) -> None:
    if dst_path.exists():
        raise FileExistsError(f"Destination already exists: {dst_path}")

    if not write:
        return

    _safe_mkdir(dst_path.parent)
    tmp_path = dst_path.with_name(dst_path.name + f".tmp.{os.getpid()}")
    try:
        with src_path.open("r", encoding="utf-8", errors="replace") as src, tmp_path.open(
            "w", encoding="utf-8"
        ) as dst:
            for idx, raw in enumerate(src, start=1):
                if idx == 1:
                    line = raw.rstrip("\n")
                    try:
                        obj = json.loads(line)
                    except Exception:
                        # Keep original line if it isn't JSON (unexpected).
                        dst.write(raw)
                        continue

                    if isinstance(obj, dict) and obj.get("type") == "session_meta":
                        payload = obj.get("payload")
                        if isinstance(payload, dict):
                            if str(payload.get("id") or "") == old_sid:
                                payload["id"] = new_sid
                            payload["originator"] = originator
                            payload["source"] = source
                            obj["payload"] = payload
                    dst.write(_json_dumps(obj) + "\n")
                    continue

                dst.write(raw)
        tmp_path.replace(dst_path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def _patch_one_rollout_in_place(
    *,
    path: Path,
    sid: str,
    originator: str,
    source: str,
    write: bool,
) -> None:
    if not write:
        return

    tmp_path = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        with path.open("rb") as src, tmp_path.open("wb") as dst:
            first_raw = src.readline()
            if not first_raw:
                raise ValueError(f"Empty rollout file: {path}")
            try:
                obj = json.loads(first_raw.decode("utf-8", errors="replace"))
            except Exception as e:
                raise ValueError(f"Invalid JSON in first line: {path}") from e

            if isinstance(obj, dict) and obj.get("type") == "session_meta":
                payload = obj.get("payload")
                if isinstance(payload, dict):
                    if str(payload.get("id") or "") != sid:
                        raise ValueError(
                            f"session_meta.payload.id mismatch: expected={sid} got={payload.get('id')!r} ({path})"
                        )
                    payload["originator"] = originator
                    payload["source"] = source
                    obj["payload"] = payload

            dst.write(_json_dumps(obj).encode("utf-8") + b"\n")
            # Copy the rest as-is.
            import shutil

            shutil.copyfileobj(src, dst)
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


@dataclass(frozen=True)
class CloneResult:
    dst_codex_home: str
    dst_paths: list[str]


def clone_session(
    *,
    src_codex_home: Path,
    dst_codex_homes: list[Path],
    sid: str,
    new_sid: str,
    originator: str,
    source: str,
    write: bool,
) -> list[CloneResult]:
    src_codex_home = src_codex_home.expanduser()
    rollout_files = _iter_rollout_files(src_codex_home, sid)
    if not rollout_files:
        raise FileNotFoundError(f"No rollout files found for sid={sid} in {src_codex_home}/sessions/**")

    results: list[CloneResult] = []
    for dst_home in dst_codex_homes:
        dst_home = dst_home.expanduser()
        dst_paths: list[str] = []

        for src_path in rollout_files:
            rel = src_path.relative_to(src_codex_home)
            new_name = rel.name.replace(sid, new_sid)
            rel_dst = rel.with_name(new_name)
            dst_path = dst_home / rel_dst
            _clone_one_rollout(
                src_path=src_path,
                dst_path=dst_path,
                old_sid=sid,
                new_sid=new_sid,
                originator=originator,
                source=source,
                write=write,
            )
            dst_paths.append(str(dst_path))

        results.append(CloneResult(dst_codex_home=str(dst_home), dst_paths=dst_paths))
    return results


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sid", required=True, help="Source session id to clone")
    ap.add_argument(
        "--src-codex-home",
        default="",
        help="Source CODEX_HOME (default: env CODEX_HOME or ~/.codex)",
    )
    ap.add_argument(
        "--dst-codex-home",
        action="append",
        default=[],
        help="Destination CODEX_HOME (repeatable). Default: same as --src-codex-home",
    )
    ap.add_argument("--new-sid", default="", help="New session id. Default: auto-generate UUIDv7")
    ap.add_argument("--originator", default="codex_cli_rs", help='session_meta.payload.originator (default: "codex_cli_rs")')
    ap.add_argument("--source", default="cli", help='session_meta.payload.source (default: "cli")')
    ap.add_argument(
        "--patch-in-place",
        action="store_true",
        help="Patch originator/source inside existing rollout files (no cloning, keeps SID)",
    )
    ap.add_argument("--write", action="store_true", help="Actually write files (default: dry-run)")
    args = ap.parse_args(argv)

    src_home = Path(args.src_codex_home).expanduser() if args.src_codex_home else _default_codex_home()
    dst_homes = [Path(p).expanduser() for p in args.dst_codex_home] if args.dst_codex_home else [src_home]

    sid = args.sid.strip()
    if not sid:
        raise SystemExit(2)

    if args.patch_in_place:
        patched: list[dict[str, Any]] = []
        for dst_home in dst_homes:
            files = _iter_rollout_files(dst_home, sid)
            if not files:
                raise FileNotFoundError(f"No rollout files found for sid={sid} in {dst_home}/sessions/**")
            for path in files:
                _patch_one_rollout_in_place(
                    path=path,
                    sid=sid,
                    originator=args.originator,
                    source=args.source,
                    write=bool(args.write),
                )
                patched.append({"codex_home": str(dst_home), "path": str(path)})
        print(
            _json_dumps(
                {
                    "sid": sid,
                    "originator": args.originator,
                    "source": args.source,
                    "write": bool(args.write),
                    "patched": patched,
                }
            )
        )
        return 0

    new_sid = (args.new_sid or "").strip() or _uuid7()

    results = clone_session(
        src_codex_home=src_home,
        dst_codex_homes=dst_homes,
        sid=sid,
        new_sid=new_sid,
        originator=args.originator,
        source=args.source,
        write=bool(args.write),
    )

    out = {
        "sid_src": sid,
        "sid_new": new_sid,
        "originator": args.originator,
        "source": args.source,
        "write": bool(args.write),
        "results": [r.__dict__ for r in results],
    }
    print(_json_dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
