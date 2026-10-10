# --- Role runners (status-driven) ---
_planveyor_role_run_model_for_runner() {
  local runner_id="${1:-}"
  local role="${2:-}"
  local base_role=""
  base_role="$(_planveyor_role_execution_base_role "$role")"
  case "$runner_id" in
    codex)
      local profile=""
      profile="$(_planveyor_model_identity_profile_for_runner "$runner_id" "$role")" || return $?
      [[ -n "${profile//[[:space:]]/}" ]] || {
        echo "N/A (why=no explicit Codex profile)"
        return 0
      }
      _planveyor_codex_expected_model_for_profile "$profile" || return $?
      ;;
    claude)
      local claude_model=""
      claude_model="$(_planveyor_claude_configured_model 2>/dev/null || true)"
      if [[ -n "${claude_model//[[:space:]]/}" ]]; then
        echo "$claude_model"
      else
        echo "N/A (why=consumer default)"
      fi
      ;;
    *)
      echo "N/A (why=runner not supported by role-run receipt)"
      ;;
  esac
}

_planveyor_role_run_state_for_rc() {
  local rc="${1:-1}"
  local timed_out="${2:-false}"
  if [[ "$timed_out" == "true" ]]; then
    echo "timeout"
  elif [[ "$rc" == "0" ]]; then
    echo "success"
  elif [[ "$rc" == "130" || "$rc" == "143" ]]; then
    echo "interrupted"
  else
    echo "failed"
  fi
}

_planveyor_role_run_non_green_reason() {
  local state="${1:-failed}"
  local rc="${2:-1}"
  case "$state" in
    success) echo "" ;;
    timeout) echo "timeout" ;;
    interrupted) echo "interrupted" ;;
    precondition_failed) echo "precondition_failed" ;;
    *) echo "exit_code_${rc}" ;;
  esac
}

_planveyor_role_runtime_status_norm() {
  local status_value="${1:-}"
  local s="${status_value:l}"
  s="${s//$'\r'/}"
  s="${s//$'\t'/ }"
  while [[ "$s" == *"  "* ]]; do s="${s//  / }"; done
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  print -r -- "$s"
}

_planveyor_censor_handoff_status_for_role() {
  local role="${1:-}"
  local status_value="${2:-}"
  local status_norm="$(_planveyor_role_runtime_status_norm "$status_value")"
  case "${role}|${status_norm}" in
    "architect|architect draft") echo "Architect draft" ;;
    "architect|ready for planner") echo "Ready for Planner" ;;
    "planner|ready for coder") echo "Ready for Coder" ;;
    "coder|ready for review") echo "Ready for Review" ;;
    *) return 1 ;;
  esac
}

_planveyor_censor_receipt_gate_check() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_censor_receipt_gate_check)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local censor_role="${1:-}"
  local plan_path="${2:-}"
  local handoff_status="${3:-}"
  [[ -n "${censor_role//[[:space:]]/}" && -n "${plan_path//[[:space:]]/}" && -n "${handoff_status//[[:space:]]/}" ]] || return 0

  local helper="" lint_json="" lint_rc=0 lint_kv=""
  helper="$(_planveyor_script censor_receipts_harvest.py)" || return 1
  lint_json="$(_planveyor_py_any "$helper" --plan "$plan_path" --censor-role "$censor_role" --handoff-status "$handoff_status" --format json 2>&1)"
  lint_rc=$?
  lint_kv="$(_planveyor_py_any - "$lint_json" <<'PY'
from __future__ import annotations
import json
import sys

try:
    payload = json.loads(sys.argv[1])
    lint = payload.get("censor_evidence_lint") or {}
except Exception as exc:
    print("state=invalid_json")
    print(f"reason_code={type(exc).__name__}")
    print("missing_fields=[]")
    print("invalid_reasons=[]")
    print("receipt_line=")
    raise SystemExit(0)

def emit(key: str, value: object) -> None:
    if isinstance(value, list):
        text = ",".join(str(item) for item in value)
    elif value is None:
        text = ""
    else:
        text = str(value)
    print(f"{key}={text}")

emit("state", lint.get("state", ""))
emit("reason_code", lint.get("reason_code", ""))
emit("missing_fields", lint.get("missing_fields", []))
emit("invalid_reasons", lint.get("invalid_reasons", []))
emit("receipt_line", lint.get("receipt_line", ""))
PY
)"
  local state="" reason_code="" missing_fields="" invalid_reasons="" receipt_line=""
  local row=""
  for row in ${(f)lint_kv}; do
    case "$row" in
      state=*) state="${row#state=}" ;;
      reason_code=*) reason_code="${row#reason_code=}" ;;
      missing_fields=*) missing_fields="${row#missing_fields=}" ;;
      invalid_reasons=*) invalid_reasons="${row#invalid_reasons=}" ;;
      receipt_line=*) receipt_line="${row#receipt_line=}" ;;
    esac
  done
  if (( lint_rc != 0 )) || [[ "$state" != "complete" && "$state" != "skipped_by_valid_hint" ]]; then
    echo "❗ CENSOR receipt blocked: role=${censor_role} handoff_status=${handoff_status} helper_state=${state:-unknown} reason_code=${reason_code:-unknown} missing_fields=${missing_fields:-[]} invalid_reasons=${invalid_reasons:-[]} receipt_line=${receipt_line:-N/A}" >&2
    return 5
  fi
  return 0
}

_planveyor_role_run_supervise() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_supervise)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root="${1:-}"
  local wrapper="${2:-}"
  local wrapper_source="${3:-}"
  local stdout_path="${4:-}"
  local stderr_path="${5:-}"
  local timeout_seconds="${6:-0}"
  shift 6
  local dispatch_role="" dispatch_runner=""
  while (( $# > 0 )); do
    case "${1:-}" in
      --dispatch-role)
        shift
        (( $# > 0 )) || return 2
        dispatch_role="${1:-}"
        ;;
      --dispatch-runner)
        shift
        (( $# > 0 )) || return 2
        dispatch_runner="${1:-}"
        ;;
      --)
        shift
        break
        ;;
      *)
        break
        ;;
    esac
    shift
  done
  [[ -z "${dispatch_role//[[:space:]]/}" && -z "${dispatch_runner//[[:space:]]/}" ]] || \
    [[ -n "${dispatch_role//[[:space:]]/}" && -n "${dispatch_runner//[[:space:]]/}" ]] || return 2
  # Trailing KEY=VALUE args are the current role-run carrier injected into the
  # role process env (identity only: run_id/paths/session_key/target_plan). The
  # accepted proof's dispatch role/runner travel as private supervisor arguments
  # and are installed only as a child-local `planveyor_runner` override, never as an
  # exported proof environment variable or a durable carrier.
  local -a role_run_env_pairs
  role_run_env_pairs=("$@")
  local project_root=""
  project_root="$(_planveyor_project_root)" || return $?
  [[ "$root" == "$project_root" ]] || return 1
  local runtime_root=""
  local runtime_pin_sha256=""
  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    runtime_root="$(_planveyor_authority_runtime_root)" || return $?
    runtime_pin_sha256="$(_planveyor_authority_context_field "$PLANVEYOR_CTX_JSON" runtime_pin_sha256)" || return $?
    [[ -n "${runtime_root//[[:space:]]/}" && -n "${runtime_pin_sha256//[[:space:]]/}" ]] || return 1
    local _PLANVEYOR_AUTHORITY_CONTEXT_V1
    typeset -x _PLANVEYOR_AUTHORITY_CONTEXT_V1="$PLANVEYOR_CTX_JSON"
  fi
  local -a supervisor_python=(_planveyor_py_any -)
  if [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" == pinned ]]; then
    supervisor_python=(_planveyor_py_authority_stdin)
  fi
  "${supervisor_python[@]}" "$root" "$wrapper" "$wrapper_source" "$stdout_path" "$stderr_path" "$timeout_seconds" "$dispatch_role" "$dispatch_runner" "$PLANVEYOR_CTX_STATE" "$runtime_root" "$runtime_pin_sha256" "${role_run_env_pairs[@]}" <<'PY'
from __future__ import annotations

import json
import os
import pathlib
import shlex
import signal
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
wrapper = sys.argv[2]
wrapper_source = pathlib.Path(sys.argv[3])
stdout_path = pathlib.Path(sys.argv[4])
stderr_path = pathlib.Path(sys.argv[5])
try:
    timeout_seconds = int(sys.argv[6])
except ValueError:
    timeout_seconds = 0
dispatch_role = sys.argv[7]
dispatch_runner = sys.argv[8]
authority_state = sys.argv[9]
runtime_root = sys.argv[10]
runtime_pin_sha256 = sys.argv[11]

# Current role-run carrier: identity only (run_id + paths + session_key +
# target_plan). The final receipt state is still written by this supervisor
# after the role process exits, so the carrier MUST NOT carry final state.
child_env = os.environ.copy()
child_env.pop("PLANVEYOR_ROLE_OUTCOME_RECOVERY_OF_RUN_ID", None)
child_env.pop("PLANVEYOR_ROLE_OUTCOME_REJECTION_RECEIPT_SHA256", None)
# Caller-local context variables are never a child transport.  Clear any
# ambient exported spoof before selectively carrying the compact assertion for
# an engaged child below.
authority_transport_keys = (
    "PLANVEYOR_CTX_SEAL",
    "PLANVEYOR_CTX_ROOT",
    "PLANVEYOR_CTX_GENERATION",
    "PLANVEYOR_CTX_JSON",
    "PLANVEYOR_CTX_STATE",
    "_PLANVEYOR_AUTHORITY_CONTEXT_V1",
)
for context_key in authority_transport_keys:
    child_env.pop(context_key, None)
expected_authority_context = ""
if authority_state == "engaged":
    expected_authority_context = os.environ.get("_PLANVEYOR_AUTHORITY_CONTEXT_V1", "")
    if not expected_authority_context:
        raise SystemExit("engaged child is missing compact authority assertion")
    child_env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = expected_authority_context
for pair in sys.argv[12:]:
    if "=" in pair:
        key, value = pair.split("=", 1)
        if key in authority_transport_keys:
            continue
        child_env[key] = value

if authority_state == "engaged":
    if not runtime_root or not runtime_pin_sha256:
        raise SystemExit("engaged child is missing pinned runtime identity")
    script_lines = [
        f"_planveyor_runtime_api_guard 5 5 {shlex.quote(runtime_pin_sha256)} || exit $?",
        '_planveyor_authority_before_effect_json "${_PLANVEYOR_AUTHORITY_CONTEXT_V1:?missing}" >/dev/null || exit $?',
        f"source {shlex.quote(str(wrapper_source))} || exit $?",
    ]
else:
    # Retain the legacy target-relative source behavior until explicit engaged
    # admission.  The engaged branch above cannot execute a target shim.
    script_lines = [
        "source scripts/planveyor.zsh",
        f"source {shlex.quote(str(wrapper_source))}",
    ]
if dispatch_role and dispatch_runner:
    script_lines.extend(
        [
            "functions -c planveyor_runner _planveyor_role_run_dispatch_original_runner",
            "planveyor_runner() {",
            f"  if [[ \"${{1:-}}\" == {shlex.quote(dispatch_role)} ]]; then",
            f"    print -r -- {shlex.quote(dispatch_runner)}",
            "    return 0",
            "  fi",
            "  _planveyor_role_run_dispatch_original_runner \"$@\"",
            "}",
        ]
    )
script_lines.append(shlex.quote(wrapper))
script = "\n".join(script_lines)
child_command = ["/bin/zsh", "-fc", script]
if authority_state == "engaged":
    import contract_authority_context as authority_context
    from contract_authority_children import shell_command

    inherited_context = authority_context.resolve_top_level_context(
        root, runtime_root=pathlib.Path(runtime_root), expected=expected_authority_context,
    )
    child_command = shell_command(inherited_context, script)

payload = {"exit_code": 125, "timed_out": False, "process_started": False, "supervisor_error": ""}
old_umask = os.umask(0o077)
try:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.parent.chmod(0o700)
    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        os.fchmod(stdout_handle.fileno(), 0o600)
        os.fchmod(stderr_handle.fileno(), 0o600)
        proc = subprocess.Popen(
            child_command,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            env=child_env,
            start_new_session=True,
        )
        payload["process_started"] = True
        try:
            exit_code = proc.wait(timeout=timeout_seconds if timeout_seconds > 0 else None)
        except subprocess.TimeoutExpired:
            payload["timed_out"] = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
            exit_code = 124
        payload["exit_code"] = exit_code
except Exception as exc:
    payload["supervisor_error"] = f"{exc.__class__.__name__}: {exc}"
    try:
        with stderr_path.open("ab") as stderr_handle:
            stderr_handle.write((payload["supervisor_error"] + "\n").encode("utf-8"))
    except Exception:
        pass
finally:
    os.umask(old_umask)

print(json.dumps(payload, sort_keys=True))
PY
}

_planveyor_role_outcome_contract_active() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_outcome_contract_active)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local plan_path="${1:-}" role="${2:-}"
  case "$role" in
    planner|coder|reviewer_code_risk|reviewer_code_contracts) ;;
    *) return 1 ;;
  esac
  _planveyor_py_any - "$plan_path" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
try:
    start = lines.index("## Verification rerun / exec handoff") + 1
except ValueError:
    raise SystemExit(1)
for line in lines[start:]:
    if line.startswith("## "):
        break
    if line == "- Mode: manager-custom-pipeline":
        raise SystemExit(0)
raise SystemExit(1)
PY
}

_planveyor_role_outcome_helper_json() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_outcome_helper_json)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local operation="${1:-}" root="${2:-}" plan_path="${3:-}" role="${4:-}"
  local run_id="${5:-}" output_dir="${6:-}" receipt_path="${7:-}" preflight_path="${8:-}"
  local recovery_of_run_id="${9:-}" rejection_receipt_sha256="${10:-}"
  local project_root=""
  project_root="$(_planveyor_project_root)" || return $?
  [[ "$root" == "$project_root" ]] || return 1
  local helper=""
  helper="$(_planveyor_script role_outcome_receipt.py)" || return 127
  [[ -f "$helper" ]] || return 127
  local -a args
  args=(
    "$operation"
    --project-root "$root"
    --plan "$plan_path"
    --role "$role"
    --run-id "$run_id"
    --output-dir "$output_dir"
  )
  if [[ "$operation" != "preflight" && "$operation" != "reserve-rerun" ]]; then
    args+=(--execution-receipt "$receipt_path")
  fi
  if [[ "$operation" == "finalize" ]]; then
    args+=(--preflight-result "$preflight_path")
  fi
  if [[ "$operation" == "reserve-rerun" ]]; then
    args+=(
      --recovery-of-run-id "$recovery_of_run_id"
      --rejection-receipt-sha256 "$rejection_receipt_sha256"
    )
  fi
  args+=(--format json)
  _planveyor_py_any -B "$helper" "${args[@]}"
}

_planveyor_role_outcome_result_kv() {
  local payload_json="${1:-}" kind="${2:-}" expected_role="${3:-}"
  local expected_run_id="${4:-}" expected_plan="${5:-}"
  _planveyor_py_any - "$payload_json" "$kind" "$expected_role" "$expected_run_id" "$expected_plan" <<'PY'
from __future__ import annotations

import json
import sys

try:
    payload = json.loads(sys.argv[1])
except (TypeError, json.JSONDecodeError):
    raise SystemExit(1)
if not isinstance(payload, dict):
    raise SystemExit(1)
state = payload.get("state")
reason = payload.get("reason_code")
if not isinstance(state, str) or not isinstance(reason, str) or not state or not reason:
    raise SystemExit(1)
kind = sys.argv[2]
role, run_id, target_plan = sys.argv[3:6]
common = {
    "schema_version", "state", "reason_code", "run_id", "role", "lane",
    "target_plan", "carrier_path", "artifact_ref", "semantic_draft_count",
    "finalized_receipt_count", "forbidden_carrier_hits",
}
if (
    payload.get("role") != role
    or payload.get("lane") != role
    or payload.get("run_id") != run_id
    or payload.get("target_plan") != target_plan
):
    raise SystemExit(1)
if kind == "preflight":
    fields = common | {"forbidden_carrier_path"}
    if (
        set(payload) != fields
        or payload.get("schema_version") != "role_outcome_preflight.v1"
        or state not in {"ready", "blocked"}
    ):
        raise SystemExit(1)
    persisted = ""
elif kind == "reservation":
    fields = {
        "schema_version", "state", "reason_code", "run_id",
        "recovery_of_run_id", "rejection_receipt_sha256", "role", "lane",
        "target_plan", "carrier_path", "safe_action", "written_at",
        "mutation_performed",
    }
    if (
        set(payload) != fields
        or payload.get("schema_version") != "role_outcome_rerun_reservation.v1"
        or state not in {"started", "blocked"}
        or not isinstance(payload.get("mutation_performed"), bool)
        or (
            state == "started"
            and (
                payload.get("reason_code") != "ok"
                or payload.get("safe_action") != "continue_same_role_dispatch"
                or payload.get("mutation_performed") is not True
            )
        )
        or (
            state == "blocked"
            and (
                payload.get("safe_action") != "return_owner_architect"
                or payload.get("mutation_performed") is not False
            )
        )
    ):
        raise SystemExit(1)
    persisted = ""
else:
    fields = common | {"execution_receipt_path", "written_at", "role_outcome_readback_persisted"}
    if (
        set(payload) != fields
        or payload.get("schema_version") != "role_outcome_readback.v1"
        or payload.get("execution_receipt_path") != f".planveyor.role_runs/{run_id}.json"
        or state not in {"finalized", "blocked"}
    ):
        raise SystemExit(1)
    raw_persisted = payload.get("role_outcome_readback_persisted")
    if not isinstance(raw_persisted, bool):
        raise SystemExit(1)
    persisted = "true" if raw_persisted else "false"
print(f"state={state}")
print(f"reason_code={reason}")
print(f"persisted={persisted}")
PY
}

# Passive frozen-evidence parser: this runs after role-outcome persistence and
# cannot admit another live action, so it deliberately does not recapture the
# mutable target context.
_planveyor_role_outcome_diagnostic_kv() {
  local diagnostic_path="${1:-}" expected_role="${2:-}" expected_run_id="${3:-}"
  local expected_plan="${4:-}" root="${5:-}"
  _planveyor_py_any - "$diagnostic_path" "$expected_role" "$expected_run_id" "$expected_plan" "$root" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
role, run_id, target_plan = sys.argv[2:5]
root = Path(sys.argv[5]).resolve()
expected = (root / ".tmp" / "planveyor_role_runs" / run_id / "role_outcome_semantic_diagnostic.json").resolve()
if path.resolve() != expected:
    raise SystemExit(1)
payload = json.loads(path.read_text(encoding="utf-8"))
fields = {
    "schema_version", "state", "reason_code", "run_id", "role", "lane",
    "target_plan", "carrier_path", "semantic_draft_sha256", "diagnostics",
    "recovery_state", "safe_action", "written_at",
}
if (
    not isinstance(payload, dict)
    or set(payload) != fields
    or payload.get("schema_version") != "role_outcome_semantic_diagnostic.v1"
    or payload.get("state") not in {"invalid", "blocked"}
    or payload.get("run_id") != run_id
    or payload.get("role") != role
    or payload.get("lane") != role
    or payload.get("target_plan") != target_plan
    or not isinstance(payload.get("diagnostics"), list)
    or payload.get("recovery_state") not in {"reject_required", "unavailable"}
    or payload.get("safe_action") not in {
        "reject_then_explicit_same_role_rerun", "return_owner_architect"
    }
    or not isinstance(payload.get("carrier_path"), (str, type(None)))
    or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
        str(payload.get("written_at", "")),
    )
):
    raise SystemExit(1)
if payload["state"] == "invalid":
    if (
        payload["reason_code"] != "semantic_draft_invalid"
        or not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("semantic_draft_sha256", "")))
        or not payload["diagnostics"]
    ):
        raise SystemExit(1)
if (payload["recovery_state"], payload["safe_action"]) not in {
    ("reject_required", "reject_then_explicit_same_role_rerun"),
    ("unavailable", "return_owner_architect"),
}:
    raise SystemExit(1)
print(f"state={payload['state']}")
print(f"reason_code={payload['reason_code']}")
print(f"recovery_state={payload['recovery_state']}")
print(f"safe_action={payload['safe_action']}")
PY
}

# Passive frozen-output parser: provider completion may legitimately change target
# project data.  This helper only classifies captured output and cannot start or
# admit a later live action, so it deliberately does not recapture context.
_planveyor_role_run_provider_error_json() {
  local stdout_path="${1:-}"
  local stderr_path="${2:-}"
  _planveyor_py_any - "$stdout_path" "$stderr_path" <<'PY'
from __future__ import annotations

import json
import pathlib
import re
import sys

TAIL_BYTES = 64 * 1024


def tail_lines(raw_path: str) -> list[str]:
    path = pathlib.Path(raw_path)
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES))
            data = handle.read(TAIL_BYTES)
    except OSError:
        return []
    return data.decode("utf-8", errors="replace").splitlines()


def has_number(text: str, number: str) -> bool:
    return re.search(rf"(?<!\d){re.escape(number)}(?!\d)", text) is not None


matches: set[tuple[str, str, str, str]] = set()
error_shape = re.compile(
    r"\b(?:api[ _-]?error|error|failed|failure|invalid|status|code|unauthorized|forbidden|too many requests|rate[ _-]?limit|overload)\b",
    re.IGNORECASE,
)
auth_marker = re.compile(
    r"\b(?:auth(?:entication|orization)?|unauthorized|forbidden|credential|api[ _-]?key)\b",
    re.IGNORECASE,
)
rate_limit_marker = re.compile(
    r"\b(?:rate[ _-]?limit(?:ed|ing)?|too many requests)\b",
    re.IGNORECASE,
)

for line in tail_lines(sys.argv[1]) + tail_lines(sys.argv[2]):
    if error_shape.search(line) and has_number(line, "400") and has_number(line, "1211"):
        matches.add(("400", "1211", "model_invalid", "not_retryable"))
    if error_shape.search(line) and has_number(line, "529") and has_number(line, "1305"):
        matches.add(("529", "1305", "overload", "retryable"))
    if error_shape.search(line) and auth_marker.search(line):
        if has_number(line, "401"):
            matches.add(("401", "unknown", "authentication", "not_retryable"))
        if has_number(line, "403"):
            matches.add(("403", "unknown", "authentication", "not_retryable"))
    if error_shape.search(line) and rate_limit_marker.search(line) and has_number(line, "429"):
        matches.add(("429", "unknown", "rate_limit", "retryable"))

if len(matches) == 1:
    status, code, error_class, retryability = next(iter(matches))
else:
    status = code = error_class = retryability = "unknown"

print(
    json.dumps(
        {
            "provider_error_class": error_class,
            "provider_error_code": code,
            "provider_http_status": status,
            "provider_retryability": retryability,
        },
        sort_keys=True,
    )
)
PY
}

_planveyor_role_run_payload_json() {
  _planveyor_py_any - "$@" <<'PY'
from __future__ import annotations

import json
import sys

payload = {}
bool_fields = {
    "child_session",
    "success",
    "timed_out",
    "terminated_by_timeout",
    "interrupted",
    "session_reset_performed",
    "process_persistent",
}
int_fields = {"exit_code", "duration_seconds", "elapsed_seconds", "timeout_seconds"}
for item in sys.argv[1:]:
    key, value = item.split("=", 1)
    if key in bool_fields:
        payload[key] = value == "true"
    elif key in int_fields:
        try:
            payload[key] = int(value)
        except ValueError:
            payload[key] = value
    elif key == "authority_context":
        try:
            authority_context = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise SystemExit(1)
        if not isinstance(authority_context, dict):
            raise SystemExit(1)
        payload[key] = authority_context
    else:
        payload[key] = value

print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
}

_planveyor_role_run_preflight_proof_kv() {
  local proof_json="${1:-}" expected_role="${2:-}" expected_runner_role="${3:-}"
  local expected_session_key="${4:-}" expected_sid="${5:-}"
  _planveyor_py_any - "$proof_json" "$expected_role" "$expected_runner_role" "$expected_session_key" "$expected_sid" <<'PY'
from __future__ import annotations

import json
import re
import sys

raw, expected_role, expected_runner_role, expected_session_key, expected_sid = sys.argv[1:]
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


def blocked(reason: str) -> None:
    print("state=blocked")
    print(f"reason={reason}")
    raise SystemExit(0)


try:
    payload = json.loads(raw, object_pairs_hook=unique_object)
except (TypeError, ValueError, json.JSONDecodeError):
    blocked("precondition_failed")

if not isinstance(payload, dict):
    blocked("precondition_failed")

if payload.get("execution_ready") is not True or payload.get("reason") != "ok":
    reason = payload.get("reason")
    blocked(reason if reason in {"runner_not_readable", "runner_invalid_for_role"} else "precondition_failed")

required = {
    "role": expected_role,
    "runner_role": expected_runner_role,
    "session_key": expected_session_key,
    "sid": expected_sid,
    "selection_schema_version": "runner_selection_resolution.v1",
}
for key, expected in required.items():
    if payload.get(key) != expected:
        blocked("precondition_failed")

runner = payload.get("runner")
if not isinstance(runner, str) or not runner or payload.get("runner_id") != runner:
    blocked("precondition_failed")
attempt = payload.get("init_attempt_id")
digest = payload.get("selection_digest")
if not isinstance(attempt, str) or not UUID_RE.fullmatch(attempt):
    blocked("precondition_failed")
if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
    blocked("precondition_failed")
if payload.get("carrier_state") not in {"absent_default", "present_valid"}:
    blocked("precondition_failed")
if not UUID_RE.fullmatch(expected_sid):
    blocked("precondition_failed")

print("state=valid")
print("reason=ok")
print(f"runner={runner}")
print(f"init_attempt_id={attempt}")
print(f"selection_digest={digest}")
print(f"carrier_state={payload['carrier_state']}")
PY
}

_planveyor_role_run_current_selection_match_kv() {
  local current_json="${1:-}" expected_runner_role="${2:-}" expected_runner="${3:-}"
  local expected_attempt="${4:-}" expected_digest="${5:-}"
  _planveyor_py_any - "$current_json" "$expected_runner_role" "$expected_runner" "$expected_attempt" "$expected_digest" <<'PY'
from __future__ import annotations

import json
import re
import sys

raw, expected_role, expected_runner, expected_attempt, expected_digest = sys.argv[1:]
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
expected_keys = {
    "carrier_state",
    "init_attempt_id",
    "role",
    "runner",
    "schema_version",
    "selection_digest",
}


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


try:
    payload = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("selection_shape")
    if payload.get("schema_version") != "runner_selection_resolution.v1":
        raise ValueError("selection_schema")
    if payload.get("carrier_state") not in {"absent_default", "present_valid"}:
        raise ValueError("carrier_state")
    if not isinstance(payload.get("init_attempt_id"), str) or not UUID_RE.fullmatch(payload["init_attempt_id"]):
        raise ValueError("attempt")
    if not isinstance(payload.get("selection_digest"), str) or not DIGEST_RE.fullmatch(payload["selection_digest"]):
        raise ValueError("digest")
except (TypeError, ValueError, json.JSONDecodeError):
    print("state=invalid")
    raise SystemExit(0)

if (
    payload.get("role") != expected_role
    or payload.get("runner") != expected_runner
    or payload.get("init_attempt_id") != expected_attempt
    or payload.get("selection_digest") != expected_digest
):
    print("state=mismatch")
else:
    print("state=match")
PY
}

_planveyor_role_run_managed_preflight() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_managed_preflight)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root="${1:-}" receipt_root="${2:-}" output_root="${3:-}" lock_root="${4:-}"
  local run_dir="${5:-}" receipt_path="${6:-}" latest_path="${7:-}" lock_path="${8:-}"
  local lock_ready_path="${9:-}" lock_release_path="${10:-}" transaction_done_path="${11:-}"
  local project_root=""
  project_root="$(_planveyor_project_root)" || return $?
  [[ "$root" == "$project_root" ]] || return 1
  shift 11
  _planveyor_py_any - "$root" "$receipt_root" "$output_root" "$lock_root" "$run_dir" \
    "$receipt_path" "$latest_path" "$lock_path" "$lock_ready_path" "$lock_release_path" \
    "$transaction_done_path" "$@" <<'PY'
from __future__ import annotations

import json
import os
import pathlib
import stat
import sys

root = pathlib.Path(sys.argv[1]).resolve()
receipt_root, output_root, lock_root, run_dir = map(pathlib.Path, sys.argv[2:6])
receipt_path, latest_path, lock_path = map(pathlib.Path, sys.argv[6:9])
control_files = [pathlib.Path(value) for value in sys.argv[9:12]]
managed_files = [pathlib.Path(value) for value in sys.argv[12:]]
directories = [receipt_root, output_root, lock_root, run_dir]
optional_files = [latest_path, lock_path]
mutation_performed = False


class UnsafePath(Exception):
    def __init__(self, path: pathlib.Path, reason: str) -> None:
        super().__init__(reason)
        self.path = path
        self.reason = reason


def lexical(path: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.path.abspath(os.fspath(path)))


def require_inside(path: pathlib.Path) -> pathlib.Path:
    candidate = lexical(path)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePath(candidate, "path_escape") from exc
    return candidate


def require_under(path: pathlib.Path, boundary: pathlib.Path) -> None:
    candidate = require_inside(path)
    expected_root = require_inside(boundary)
    try:
        candidate.relative_to(expected_root)
    except ValueError as exc:
        raise UnsafePath(candidate, "managed_root_escape") from exc


def validate_components(path: pathlib.Path, *, final_kind: str, allow_missing: bool) -> None:
    candidate = require_inside(path)
    relative = candidate.relative_to(root)
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        is_final = index == len(relative.parts) - 1
        try:
            info = current.lstat()
        except FileNotFoundError:
            if is_final and not allow_missing:
                raise UnsafePath(current, "missing_managed_path")
            continue
        if stat.S_ISLNK(info.st_mode):
            raise UnsafePath(current, "symlink_managed_path")
        expected = final_kind if is_final else "dir"
        if expected == "dir" and not stat.S_ISDIR(info.st_mode):
            raise UnsafePath(current, "managed_path_not_directory")
        if expected == "file" and not stat.S_ISREG(info.st_mode):
            raise UnsafePath(current, "managed_path_not_regular_file")


try:
    require_under(lock_root, output_root)
    require_under(run_dir, output_root)
    require_under(receipt_path, receipt_root)
    require_under(lock_path, lock_root)
    if latest_path.parent != root:
        raise UnsafePath(latest_path, "managed_root_escape")
    for path in control_files + managed_files:
        require_under(path, run_dir)
    for directory in directories:
        validate_components(directory, final_kind="dir", allow_missing=True)
    validate_components(receipt_path, final_kind="file", allow_missing=True)
    if lexical(receipt_path).exists():
        raise UnsafePath(receipt_path, "receipt_path_already_exists")
    for path in optional_files + control_files + managed_files:
        validate_components(path, final_kind="file", allow_missing=True)
    for path in control_files:
        if lexical(path).exists():
            raise UnsafePath(path, "control_marker_already_exists")

    old_umask = os.umask(0o077)
    try:
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
            mutation_performed = True
        for path in optional_files:
            if path.exists():
                path.chmod(0o600)
                mutation_performed = True
        flags = os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        for path in managed_files:
            fd = os.open(path, flags, 0o600)
            try:
                os.fchmod(fd, 0o600)
            finally:
                os.close(fd)
            mutation_performed = True
    finally:
        os.umask(old_umask)
except (OSError, UnsafePath) as exc:
    path = exc.path if isinstance(exc, UnsafePath) else pathlib.Path(getattr(exc, "filename", "") or root)
    reason = exc.reason if isinstance(exc, UnsafePath) else f"{exc.__class__.__name__}:{exc}"
    print(json.dumps({"ok": False, "error": "unsafe_managed_path", "path": str(path), "reason": reason, "mutation_performed": mutation_performed}, sort_keys=True))
    raise SystemExit(1)

print(json.dumps({"ok": True, "mutation_performed": mutation_performed}, sort_keys=True))
PY
}

_planveyor_role_run_lock_holder() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_lock_holder)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local lock_path="${1:-}" ready_path="${2:-}" release_path="${3:-}" parent_pid="${4:-}"
  _planveyor_py_any - "$lock_path" "$ready_path" "$release_path" "$parent_pid" <<'PY'
from __future__ import annotations

import fcntl
import json
import os
import pathlib
import stat
import tempfile
import time
import sys

lock_path = pathlib.Path(sys.argv[1])
ready_path = pathlib.Path(sys.argv[2])
release_path = pathlib.Path(sys.argv[3])
parent_pid = int(sys.argv[4])


def publish_ready(payload: dict[str, object]) -> None:
    payload = dict(payload)
    payload["holder_pid"] = os.getpid()
    payload["parent_pid"] = parent_pid
    old_umask = os.umask(0o077)
    temp_name = ""
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{ready_path.name}.tmp-", dir=ready_path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, ready_path)
        dir_fd = os.open(ready_path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        os.umask(old_umask)
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


flags = os.O_CREAT | os.O_RDWR
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
try:
    fd = os.open(lock_path, flags, 0o600)
    os.fchmod(fd, 0o600)
except OSError as exc:
    publish_ready({"state": "error", "reason": f"{exc.__class__.__name__}:{exc}"})
    raise SystemExit(0)

with os.fdopen(fd, "a+") as handle:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        publish_ready({"state": "contended", "reason": "role_run_lock_contended"})
        raise SystemExit(0)
    except OSError as exc:
        publish_ready({"state": "error", "reason": f"{exc.__class__.__name__}:{exc}"})
        raise SystemExit(0)
    publish_ready({"state": "acquired", "reason": "ok"})
    while True:
        try:
            release_info = release_path.lstat()
        except FileNotFoundError:
            release_info = None
        if (
            release_info is not None
            and stat.S_ISREG(release_info.st_mode)
            and stat.S_IMODE(release_info.st_mode) == 0o600
            and release_info.st_uid == os.getuid()
        ):
            break
        try:
            os.kill(parent_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
PY
}

_planveyor_role_run_lock_release() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_lock_release)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local release_path="${1:-}" lock_pid="${2:-}" holder_pid="${3:-}"
  local marker_json="" marker_rc=0 holder_timed_out="false" holder_cleanup_failed="false"
  local wait_index=0 watchdog_pid=""
  marker_json="$(_planveyor_role_run_publish_control_marker lock_release "$release_path")" || marker_rc=$?

  if [[ "$holder_pid" == <-> && "$holder_pid" -gt 0 ]]; then
    if (( marker_rc != 0 )); then
      kill -TERM "$holder_pid" 2>/dev/null || true
    else
      while (( wait_index < 200 )) && kill -0 "$holder_pid" 2>/dev/null; do
        sleep 0.01
        (( wait_index += 1 ))
      done
    fi
    if kill -0 "$holder_pid" 2>/dev/null; then
      holder_timed_out="true"
      kill -TERM "$holder_pid" 2>/dev/null || true
      wait_index=0
      while (( wait_index < 100 )) && kill -0 "$holder_pid" 2>/dev/null; do
        sleep 0.01
        (( wait_index += 1 ))
      done
    fi
    if kill -0 "$holder_pid" 2>/dev/null; then
      kill -KILL "$holder_pid" 2>/dev/null || true
      wait_index=0
      while (( wait_index < 100 )) && kill -0 "$holder_pid" 2>/dev/null; do
        sleep 0.01
        (( wait_index += 1 ))
      done
    fi
    kill -0 "$holder_pid" 2>/dev/null && holder_cleanup_failed="true"
  else
    holder_cleanup_failed="true"
  fi

  if [[ "$lock_pid" == <-> && "$lock_pid" -gt 0 ]]; then
    (
      sleep 1
      kill -TERM "$lock_pid" 2>/dev/null || exit 0
      sleep 1
      kill -KILL "$lock_pid" 2>/dev/null || true
    ) &
    watchdog_pid=$!
    wait "$lock_pid" 2>/dev/null || true
    if kill "$watchdog_pid" 2>/dev/null; then
      wait "$watchdog_pid" 2>/dev/null || true
    else
      wait "$watchdog_pid" 2>/dev/null || true
    fi
  fi

  if (( marker_rc != 0 )) || [[ "$holder_timed_out" == "true" || "$holder_cleanup_failed" == "true" ]]; then
    typeset -g _PLANVEYOR_ROLE_RUN_LOCK_RELEASE_JSON
    _PLANVEYOR_ROLE_RUN_LOCK_RELEASE_JSON="$(_planveyor_py_any - "$marker_json" "$marker_rc" "$holder_timed_out" "$holder_cleanup_failed" <<'PY'
import json
import sys

try:
    marker = json.loads(sys.argv[1])
except (TypeError, ValueError):
    marker = {"ok": False, "reason": "invalid_marker_result"}
reason = "lock_release_failed" if int(sys.argv[2]) else "lock_holder_release_timeout"
print(json.dumps({
    "ok": False,
    "reason": reason,
    "marker": marker,
    "holder_timed_out": sys.argv[3] == "true",
    "holder_cleanup_failed": sys.argv[4] == "true",
}, sort_keys=True))
PY
    )"
    return 1
  fi
  typeset -g _PLANVEYOR_ROLE_RUN_LOCK_RELEASE_JSON='{"holder_cleanup_failed":false,"holder_timed_out":false,"ok":true,"reason":"ok"}'
}

_planveyor_role_run_mark_transaction_done() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_mark_transaction_done)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local done_path="${1:-}"
  _planveyor_role_run_publish_control_marker transaction_done "$done_path"
}

_planveyor_role_run_publish_control_marker() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_publish_control_marker)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local marker_kind="${1:-}" marker_path="${2:-}"
  _planveyor_py_any - "$marker_kind" "$marker_path" <<'PY'
from __future__ import annotations

import json
import os
import pathlib
import secrets
import stat
import sys

kind = sys.argv[1]
path = pathlib.Path(sys.argv[2])
dir_fd = -1
fd = -1
temp_name = ""
mutation_performed = False

try:
    if not path.name or path.name in {".", ".."}:
        raise OSError("invalid_control_marker_name")
    dir_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        dir_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        dir_flags |= os.O_NOFOLLOW
    dir_fd = os.open(path.parent, dir_flags)
    if not stat.S_ISDIR(os.fstat(dir_fd).st_mode):
        raise OSError("control_marker_parent_not_directory")

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _ in range(16):
        temp_name = f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(6)}"
        try:
            fd = os.open(temp_name, flags, 0o600, dir_fd=dir_fd)
            break
        except FileExistsError:
            temp_name = ""
    if fd < 0:
        raise OSError("control_marker_temp_exhausted")
    os.fchmod(fd, 0o600)
    os.fsync(fd)
    os.close(fd)
    fd = -1
    os.link(
        temp_name,
        path.name,
        src_dir_fd=dir_fd,
        dst_dir_fd=dir_fd,
        follow_symlinks=False,
    )
    mutation_performed = True
    os.unlink(temp_name, dir_fd=dir_fd)
    temp_name = ""
    os.fsync(dir_fd)
except OSError as exc:
    print(json.dumps({
        "ok": False,
        "kind": kind,
        "path": str(path),
        "reason": f"{exc.__class__.__name__}:{exc}",
        "mutation_performed": mutation_performed,
    }, sort_keys=True))
    raise SystemExit(1)
finally:
    if fd >= 0:
        os.close(fd)
    if temp_name and dir_fd >= 0:
        try:
            os.unlink(temp_name, dir_fd=dir_fd)
        except FileNotFoundError:
            pass
    if dir_fd >= 0:
        os.close(dir_fd)

print(json.dumps({"ok": True, "kind": kind, "path": str(path), "mutation_performed": mutation_performed}, sort_keys=True))
PY
}

_planveyor_role_run_close_transaction() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_close_transaction)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local done_path="${1:-}" release_path="${2:-}" lock_pid="${3:-}" holder_pid="${4:-}" lock_state="${5:-}"
  local done_json="" release_json="" done_rc=0 release_rc=0 compose_rc=0
  done_json="$(_planveyor_role_run_mark_transaction_done "$done_path")" || done_rc=$?
  if [[ "$lock_state" == "acquired" ]]; then
    _planveyor_role_run_lock_release "$release_path" "$lock_pid" "$holder_pid" || release_rc=$?
    release_json="${_PLANVEYOR_ROLE_RUN_LOCK_RELEASE_JSON:-}"
  else
    release_json='{"ok":true,"reason":"not_lock_owner"}'
  fi
  typeset -g _PLANVEYOR_ROLE_RUN_CLOSE_JSON
  _PLANVEYOR_ROLE_RUN_CLOSE_JSON="$(_planveyor_py_any - "$done_json" "$done_rc" "$release_json" "$release_rc" <<'PY'
import json
import sys

def load(raw: str, fallback: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {"ok": False, "reason": fallback}
    return value if isinstance(value, dict) else {"ok": False, "reason": fallback}

done = load(sys.argv[1], "invalid_transaction_done_result")
release = load(sys.argv[3], "invalid_lock_release_result")
done_rc = int(sys.argv[2])
release_rc = int(sys.argv[4])
if release_rc:
    reason = "lock_release_failed"
elif done_rc:
    reason = "transaction_done_publication_failed"
else:
    reason = "ok"
print(json.dumps({"ok": not (done_rc or release_rc), "reason": reason, "transaction_done": done, "lock_release": release}, sort_keys=True))
raise SystemExit(1 if done_rc or release_rc else 0)
PY
  )" || compose_rc=$?
  (( compose_rc == 0 && done_rc == 0 && release_rc == 0 ))
}

_planveyor_role_run_atomic_publish() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_atomic_publish)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local kind="${1:-}" destination="${2:-}" payload_json="${3:-}" fail_stage=""
  if (( $+functions[_planveyor_role_run_test_fail_stage] )); then
    fail_stage="$(_planveyor_role_run_test_fail_stage "$kind" 2>/dev/null || true)"
  fi
  _planveyor_py_any - "$kind" "$destination" "$payload_json" "$fail_stage" <<'PY'
from __future__ import annotations

import json
import os
import pathlib
import stat
import sys
import tempfile

kind = sys.argv[1]
path = pathlib.Path(sys.argv[2])
payload = json.loads(sys.argv[3])
fail_stage = sys.argv[4]

if kind in {"primary", "outcome_preflight"}:
    data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
elif kind == "latest":
    rows = [f"# {payload.get('receipt_written_at', '')}"]
    for key in sorted(payload):
        value = payload[key]
        if isinstance(value, bool):
            value = "true" if value else "false"
        rows.append(f"{key}={value}")
    data = ("\n".join(rows) + "\n").encode("utf-8")
else:
    print(json.dumps({"ok": False, "reason": "unknown_publish_kind", "mutation_performed": False}, sort_keys=True))
    raise SystemExit(1)

old_exists = path.exists()
old_bytes = path.read_bytes() if old_exists else b""
old_mode = stat.S_IMODE(path.stat().st_mode) if old_exists else 0o600
temp_name = ""
replaced = False


def maybe(stage: str) -> None:
    if fail_stage == stage:
        raise OSError(f"synthetic_{kind}_{stage}_failure")


def fsync_dir(directory: pathlib.Path) -> None:
    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def restore_previous() -> None:
    if old_exists:
        fd, rollback_name = tempfile.mkstemp(prefix=f".{path.name}.rollback-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                os.fchmod(handle.fileno(), old_mode)
                handle.write(old_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(rollback_name, path)
            fsync_dir(path.parent)
        finally:
            try:
                os.unlink(rollback_name)
            except FileNotFoundError:
                pass
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        fsync_dir(path.parent)


old_umask = os.umask(0o077)
try:
    maybe("temp_create")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    with os.fdopen(fd, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        maybe("write")
        handle.write(data)
        maybe("flush")
        handle.flush()
        maybe("fsync")
        os.fsync(handle.fileno())
    maybe("replace")
    os.replace(temp_name, path)
    temp_name = ""
    replaced = True
    maybe("dir_fsync")
    fsync_dir(path.parent)
except OSError as exc:
    if replaced:
        try:
            restore_previous()
        except OSError:
            pass
    if temp_name:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    current_exists = path.exists()
    current_bytes = path.read_bytes() if current_exists and path.is_file() else b""
    mutation_performed = current_exists != old_exists or (current_exists and current_bytes != old_bytes)
    print(json.dumps({"ok": False, "reason": f"{exc.__class__.__name__}:{exc}", "stage": fail_stage or "runtime", "mutation_performed": mutation_performed}, sort_keys=True))
    raise SystemExit(1)
finally:
    os.umask(old_umask)

print(json.dumps({"ok": True, "mutation_performed": True}, sort_keys=True))
PY
}

# Passive frozen-receipt parser: this verifies an already-published artifact after
# execution and cannot admit a later live action, so it deliberately does not
# recapture the current target context.
_planveyor_role_run_check_latest_json() {
  local latest_path="${1:-}" expected_run_id="${2:-}" expected_session_key="${3:-}" expected_target_plan="${4:-}"
  _planveyor_py_any - "$latest_path" "$expected_run_id" "$expected_session_key" "$expected_target_plan" <<'PY'
from __future__ import annotations

import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
expected = {"run_id": sys.argv[2], "session_key": sys.argv[3], "target_plan": sys.argv[4]}
try:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key in rows:
            raise ValueError(f"duplicate key: {key}")
        rows[key] = value
except Exception as exc:
    print(json.dumps({"readback_state": "blocked", "reason": f"unreadable_latest:{exc.__class__.__name__}"}, sort_keys=True))
    raise SystemExit(1)
if rows.get("schema_version") != "role_execution_receipt.v1":
    print(json.dumps({"readback_state": "blocked", "reason": "latest_schema_mismatch"}, sort_keys=True))
    raise SystemExit(1)
for key, value in expected.items():
    if rows.get(key) != value:
        print(json.dumps({"readback_state": "blocked", "reason": f"latest_{key}_mismatch", "expected": value, "actual": rows.get(key, "")}, sort_keys=True))
        raise SystemExit(1)
print(json.dumps({"readback_state": "ok", "reason": "ok"}, sort_keys=True))
PY
}

_planveyor_role_run_probe_impl() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_probe_impl)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root="${1:-}" operation="${2:-}" probe_kind="${3:-}" scenario="${4:-}"
  local target_plan="${5:-}" probe_id="${6:-}"
  local project_root=""
  project_root="$(_planveyor_project_root)" || return $?
  [[ "$root" == "$project_root" ]] || return 1
  _planveyor_py_any - "$root" "$operation" "$probe_kind" "$scenario" "$target_plan" "$probe_id" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import json
import os
import pathlib
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

root = pathlib.Path(sys.argv[1]).resolve()
operation = sys.argv[2]
probe_kind = sys.argv[3]
scenario = sys.argv[4]
target_plan_arg = sys.argv[5]
probe_id_arg = sys.argv[6]
probe_root = root / ".tmp" / "planveyor_role_run_probes"

MANIFEST_SCHEMA = "role_run_probe.v1"
READBACK_SCHEMA = "role_run_probe_readback.v1"
PRODUCER = "planveyor_role_run_probe"
PROBE_ID_RE = re.compile(r"^probe_[0-9a-f]{32}$")
MANIFEST_FIELDS = {
    "schema_version",
    "probe_id",
    "probe_kind",
    "scenario",
    "producer",
    "target_plan",
    "created_at",
    "state",
    "finished_at",
    "fixture_root",
    "worker_pgid",
    "retain_reason",
}
SCENARIOS = {
    ("retention", "orphan_output"),
    ("retention", "malformed_receipt"),
    ("retention", "active_lease"),
    ("retention", "terminal_recovery"),
}
NONTERMINAL_STATES = {"prepared", "running"}
TERMINAL_STATES = {"passed", "failed", "interrupted"}
ALL_STATES = NONTERMINAL_STATES | TERMINAL_STATES


class Result(Exception):
    def __init__(self, payload: dict[str, object], rc: int) -> None:
        super().__init__(str(payload.get("reason_code", "")))
        self.payload = payload
        self.rc = rc


class Interrupted(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc(value: object) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be RFC3339 UTC")
    datetime.fromisoformat(value[:-1] + "+00:00")


def relative(path: pathlib.Path | None) -> str | None:
    if path is None:
        return None
    return path.relative_to(root).as_posix()


def readback(
    *,
    ok: bool,
    reason_code: str,
    probe_id: str | None,
    probe_state: str,
    mutation_performed: bool,
    manifest_path: pathlib.Path | None,
    fixture_root: pathlib.Path | None,
    lease_state: str,
    target_plan: str | None,
) -> dict[str, object]:
    return {
        "schema_version": READBACK_SCHEMA,
        "ok": ok,
        "operation": operation,
        "probe_id": probe_id,
        "probe_state": probe_state,
        "reason_code": reason_code,
        "mutation_performed": mutation_performed,
        "manifest_path": relative(manifest_path),
        "fixture_root": relative(fixture_root),
        "lease_state": lease_state,
        "target_plan": target_plan,
    }


def stop(
    reason_code: str,
    *,
    rc: int = 126,
    probe_id: str | None = None,
    probe_state: str = "invalid",
    mutation_performed: bool = False,
    manifest_path: pathlib.Path | None = None,
    fixture_root: pathlib.Path | None = None,
    lease_state: str = "invalid",
    target_plan: str | None = None,
) -> None:
    raise Result(
        readback(
            ok=False,
            reason_code=reason_code,
            probe_id=probe_id,
            probe_state=probe_state,
            mutation_performed=mutation_performed,
            manifest_path=manifest_path,
            fixture_root=fixture_root,
            lease_state=lease_state,
            target_plan=target_plan,
        ),
        rc,
    )


def lstat_regular(path: pathlib.Path, mode: int | None = None) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("regular file required")
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise ValueError("file mode mismatch")
    return info


def lstat_directory(path: pathlib.Path, mode: int | None = None) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ValueError("directory required")
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise ValueError("directory mode mismatch")
    return info


def fsync_directory(path: pathlib.Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_probe_root(create: bool) -> None:
    tmp_root = root / ".tmp"
    if create:
        tmp_root.mkdir(mode=0o700, exist_ok=True)
        lstat_directory(tmp_root)
        try:
            probe_root.mkdir(mode=0o700)
        except FileExistsError:
            pass
    if probe_root.exists() or probe_root.is_symlink():
        lstat_directory(probe_root, 0o700)


def normalize_target_plan(value: str) -> str:
    pure = pathlib.PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or ".." in pure.parts
        or len(pure.parts) != 3
        or pure.parts[:2] != ("docs", "plans")
        or pure.suffix != ".md"
    ):
        raise ValueError("unsafe target plan")
    path = root.joinpath(*pure.parts)
    lstat_regular(path)
    resolved = path.resolve(strict=True)
    if resolved != path.absolute() or root not in resolved.parents:
        raise ValueError("unsafe target plan")
    return pure.as_posix()


def atomic_manifest_write(path: pathlib.Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=".probe.json.", dir=path.parent)
    temp_path = pathlib.Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(fd)
        fd = -1
        os.replace(temp_path, path)
        path.chmod(0o600)
        fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def open_lease(path: pathlib.Path) -> int:
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise ValueError("regular lease required")
    os.fchmod(fd, 0o600)
    os.set_inheritable(fd, True)
    return fd


def try_acquire_lease(path: pathlib.Path) -> tuple[int | None, str]:
    flags = os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        os.close(fd)
        raise ValueError("lease mismatch")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None, "held_external"
    return fd, "held_by_helper"


def identity(info: os.stat_result) -> tuple[int, int, int]:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def safe_tree(path: pathlib.Path) -> None:
    lstat_directory(path, 0o700)
    for current, directories, files in os.walk(path, topdown=True, followlinks=False):
        current_path = pathlib.Path(current)
        lstat_directory(current_path)
        for name in directories:
            child = current_path / name
            info = child.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise ValueError("unsafe probe directory entry")
        for name in files:
            child = current_path / name
            info = child.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise ValueError("unsafe probe file entry")


def validate_manifest(probe_id: str) -> tuple[dict[str, object], pathlib.Path, pathlib.Path, pathlib.Path]:
    if not PROBE_ID_RE.fullmatch(probe_id):
        raise ValueError("unsafe probe id")
    ensure_probe_root(False)
    probe_path = probe_root / probe_id
    lstat_directory(probe_path, 0o700)
    if probe_path.parent != probe_root:
        raise ValueError("unsafe containment")
    manifest_path = probe_path / "probe.json"
    lease_path = probe_path / "lease.lock"
    fixture_path = probe_path / "fixture"
    lstat_regular(manifest_path, 0o600)
    lstat_regular(lease_path, 0o600)
    lstat_directory(fixture_path, 0o700)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != MANIFEST_FIELDS:
        raise ValueError("manifest field mismatch")
    if (
        payload["schema_version"] != MANIFEST_SCHEMA
        or payload["probe_id"] != probe_id
        or payload["producer"] != PRODUCER
        or (payload["probe_kind"], payload["scenario"]) not in SCENARIOS
        or payload["fixture_root"] != "fixture"
        or payload["state"] not in ALL_STATES
    ):
        raise ValueError("manifest identity mismatch")
    if not all(
        isinstance(payload[field], str)
        for field in ("probe_id", "probe_kind", "scenario", "producer", "target_plan", "created_at", "state", "fixture_root")
    ):
        raise ValueError("manifest type mismatch")
    parse_utc(payload["created_at"])
    normalize_target_plan(str(payload["target_plan"]))
    state = str(payload["state"])
    finished_at = payload["finished_at"]
    worker_pgid = payload["worker_pgid"]
    retain_reason = payload["retain_reason"]
    if state in NONTERMINAL_STATES:
        if finished_at is not None or retain_reason is not None:
            raise ValueError("nonterminal nullability mismatch")
    else:
        parse_utc(finished_at)
    if worker_pgid is not None and (
        isinstance(worker_pgid, bool)
        or not isinstance(worker_pgid, int)
        or worker_pgid <= 0
    ):
        raise ValueError("worker pgid mismatch")
    if state == "prepared" and worker_pgid is not None:
        raise ValueError("prepared worker mismatch")
    if state in {"running", "passed", "interrupted"} and worker_pgid is None:
        raise ValueError("post-spawn worker missing")
    if state == "passed" and retain_reason is not None:
        raise ValueError("passed retain reason mismatch")
    if state in {"failed", "interrupted"} and retain_reason != state:
        raise ValueError("terminal retain reason mismatch")
    return payload, probe_path, manifest_path, fixture_path


def mutation_delay() -> None:
    raw = os.environ.get("PLANVEYOR_ROLE_RUN_PROBE_TEST_PRE_MUTATION_DELAY", "")
    if not raw:
        return
    delay = float(raw)
    if delay < 0 or delay > 10:
        raise ValueError("invalid test delay")
    time.sleep(delay)


def run_probe() -> tuple[dict[str, object], int]:
    if (probe_kind, scenario) not in SCENARIOS:
        stop("allowlist_rejected", rc=2, lease_state="absent")
    try:
        target_plan = normalize_target_plan(target_plan_arg)
        ensure_probe_root(True)
    except Exception:
        stop("unsafe_probe_path", lease_state="absent")
    probe_id = f"probe_{uuid.uuid4().hex}"
    probe_path = probe_root / probe_id
    manifest_path = probe_path / "probe.json"
    lease_path = probe_path / "lease.lock"
    fixture_path = probe_path / "fixture"
    mutation_performed = False
    lease_fd = -1
    worker: subprocess.Popen[bytes] | None = None
    managed_signals = {signal.SIGTERM, signal.SIGINT}
    previous_signal_mask = signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)

    def interrupt(_signum: int, _frame: object) -> None:
        raise Interrupted()

    old_term: object | None = signal.signal(signal.SIGTERM, interrupt)
    old_int: object | None = signal.signal(signal.SIGINT, interrupt)
    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA,
        "probe_id": probe_id,
        "probe_kind": probe_kind,
        "scenario": scenario,
        "producer": PRODUCER,
        "target_plan": target_plan,
        "created_at": utc_now(),
        "state": "prepared",
        "finished_at": None,
        "fixture_root": "fixture",
        "worker_pgid": None,
        "retain_reason": None,
    }

    def terminate_worker_group() -> None:
        if worker is None or worker.poll() is not None:
            return
        try:
            os.killpg(worker.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            worker.wait()

    def terminalize_failure() -> None:
        nonlocal manifest
        try:
            current, _probe_path, current_manifest_path, _fixture_path = validate_manifest(probe_id)
            if current["state"] in NONTERMINAL_STATES:
                current["state"] = "failed"
                current["finished_at"] = utc_now()
                current["retain_reason"] = "failed"
                atomic_manifest_write(current_manifest_path, current)
            manifest = current
        except Exception:
            return

    try:
        probe_path.mkdir(mode=0o700)
        mutation_performed = True
        probe_path.chmod(0o700)
        lease_fd = open_lease(lease_path)
        fcntl.flock(lease_fd, fcntl.LOCK_EX)
        fixture_path.mkdir(mode=0o700)
        fixture_path.chmod(0o700)
        fsync_directory(probe_path)
        atomic_manifest_write(manifest_path, manifest)
        if os.environ.get("PLANVEYOR_ROLE_RUN_PROBE_TEST_KILL_AFTER_PREPARED", "") == "1":
            os.kill(os.getpid(), signal.SIGKILL)
        worker_code = r'''
import os, pathlib, signal, sys, time
fixture = pathlib.Path(sys.argv[1])
scenario = sys.argv[2]
hold = float(sys.argv[3])
signal_supervisor = sys.argv[4] == "true"
signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM, signal.SIGINT})
def sync_file(path: pathlib.Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    with path.open("rb") as handle:
        os.fsync(handle.fileno())
if scenario == "orphan_output":
    path = fixture / ".tmp" / "planveyor_role_runs" / "probe-orphan"
    path.mkdir(parents=True, mode=0o700)
elif scenario == "malformed_receipt":
    path = fixture / ".planveyor.role_runs"
    path.mkdir(parents=True, mode=0o700)
    sync_file(path / "malformed.json", "{not-json\n")
elif scenario == "active_lease":
    sync_file(fixture / "active.marker", "active\n")
elif scenario == "terminal_recovery":
    sync_file(fixture / "terminal.marker", "terminal\n")
if signal_supervisor:
    os.kill(os.getppid(), signal.SIGTERM)
if hold:
    time.sleep(hold)
'''
        raw_hold = os.environ.get("PLANVEYOR_ROLE_RUN_PROBE_TEST_HOLD_SECONDS", "")
        hold = 2.0 if scenario == "active_lease" else 0.0
        if raw_hold:
            hold = float(raw_hold)
            if hold < 0 or hold > 120:
                raise ValueError("invalid test hold")
        signal_supervisor = (
            os.environ.get("PLANVEYOR_ROLE_RUN_PROBE_TEST_SIGNAL_SUPERVISOR", "") == "1"
        )

        worker = subprocess.Popen(
            [
                sys.executable,
                "-c",
                worker_code,
                str(fixture_path),
                scenario,
                str(hold),
                "true" if signal_supervisor else "false",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            pass_fds=(lease_fd,),
            close_fds=True,
        )
        manifest["state"] = "running"
        manifest["worker_pgid"] = worker.pid
        atomic_manifest_write(manifest_path, manifest)
        if signal_supervisor:
            signal_deadline = time.monotonic() + 10.0
            while signal.SIGTERM not in signal.sigpending():
                if worker.poll() is not None:
                    raise RuntimeError("signal fixture exited before supervisor signal")
                if time.monotonic() >= signal_deadline:
                    raise RuntimeError("signal fixture timed out before supervisor signal")
                time.sleep(0.01)
            received_signal = signal.sigwait({signal.SIGTERM})
            if received_signal != signal.SIGTERM:
                raise RuntimeError("signal fixture delivered an unexpected signal")
            terminate_worker_group()
            manifest["state"] = "interrupted"
            manifest["finished_at"] = utc_now()
            manifest["retain_reason"] = "interrupted"
            atomic_manifest_write(manifest_path, manifest)
        else:
            try:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_signal_mask)
                worker_rc = worker.wait()
            except Interrupted:
                signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
                terminate_worker_group()
                manifest["state"] = "interrupted"
                manifest["finished_at"] = utc_now()
                manifest["retain_reason"] = "interrupted"
                atomic_manifest_write(manifest_path, manifest)
            else:
                signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
                manifest["state"] = "passed" if worker_rc == 0 else "failed"
                manifest["finished_at"] = utc_now()
                manifest["retain_reason"] = None if worker_rc == 0 else "failed"
                atomic_manifest_write(manifest_path, manifest)

        final, final_probe_path, final_manifest_path, final_fixture_path = validate_manifest(probe_id)
        state = str(final["state"])
        reason = "ok" if state in {"passed", "interrupted"} else "scenario_failed"
        payload = readback(
            ok=state in {"passed", "interrupted"},
            reason_code=reason,
            probe_id=probe_id,
            probe_state=state,
            mutation_performed=True,
            manifest_path=final_manifest_path,
            fixture_root=final_fixture_path,
            lease_state="held_by_helper",
            target_plan=target_plan,
        )
        return payload, 0 if payload["ok"] else 126
    except Result:
        raise
    except Interrupted:
        signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
        terminate_worker_group()
        try:
            current, _probe_path, current_manifest_path, _fixture_path = validate_manifest(probe_id)
            if current["state"] == "running":
                current["state"] = "interrupted"
                current["finished_at"] = utc_now()
                current["retain_reason"] = "interrupted"
                atomic_manifest_write(current_manifest_path, current)
                final, _final_probe, final_manifest, final_fixture = validate_manifest(probe_id)
                return readback(
                    ok=True,
                    reason_code="ok",
                    probe_id=probe_id,
                    probe_state=str(final["state"]),
                    mutation_performed=True,
                    manifest_path=final_manifest,
                    fixture_root=final_fixture,
                    lease_state="held_by_helper",
                    target_plan=target_plan,
                ), 0
        except Exception:
            pass
        terminalize_failure()
        stop(
            "internal_error",
            probe_id=probe_id,
            probe_state=str(manifest.get("state", "invalid")),
            mutation_performed=mutation_performed,
            manifest_path=manifest_path if manifest_path.exists() else None,
            fixture_root=fixture_path if fixture_path.exists() else None,
            lease_state="held_by_helper" if lease_fd >= 0 else "absent",
            target_plan=target_plan,
        )
    except Exception:
        signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
        terminate_worker_group()
        terminalize_failure()
        stop(
            "internal_error",
            probe_id=probe_id,
            probe_state=str(manifest.get("state", "invalid")),
            mutation_performed=mutation_performed,
            manifest_path=manifest_path if manifest_path.exists() else None,
            fixture_root=fixture_path if fixture_path.exists() else None,
            lease_state="held_by_helper" if lease_fd >= 0 else "absent",
            target_plan=target_plan,
        )
    finally:
        if old_term is not None:
            signal.signal(signal.SIGTERM, old_term)
        if old_int is not None:
            signal.signal(signal.SIGINT, old_int)
        if lease_fd >= 0:
            try:
                fcntl.flock(lease_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lease_fd)
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_signal_mask)


def existing_probe() -> tuple[dict[str, object], pathlib.Path, pathlib.Path, pathlib.Path]:
    try:
        return validate_manifest(probe_id_arg)
    except FileNotFoundError:
        if operation in {"inspect", "recover"} and PROBE_ID_RE.fullmatch(probe_id_arg):
            reason = "already_absent"
            raise Result(
                readback(
                    ok=True,
                    reason_code=reason,
                    probe_id=probe_id_arg,
                    probe_state="absent",
                    mutation_performed=False,
                    manifest_path=None,
                    fixture_root=None,
                    lease_state="absent",
                    target_plan=None,
                ),
                0,
            )
        stop("transition_invalid", probe_id=probe_id_arg or None, lease_state="absent")
    except Result:
        raise
    except Exception:
        reason = "unsafe_probe_path" if not PROBE_ID_RE.fullmatch(probe_id_arg) else "manifest_invalid"
        stop(reason, probe_id=probe_id_arg or None)


def inspect_probe() -> tuple[dict[str, object], int]:
    manifest, _probe_path, manifest_path, fixture_path = existing_probe()
    lease_path = manifest_path.parent / "lease.lock"
    try:
        lease_fd, lease_state = try_acquire_lease(lease_path)
    except Exception:
        stop(
            "manifest_invalid",
            probe_id=probe_id_arg,
            probe_state="invalid",
            manifest_path=manifest_path,
            fixture_root=fixture_path,
            target_plan=str(manifest["target_plan"]),
        )
    if lease_fd is not None:
        fcntl.flock(lease_fd, fcntl.LOCK_UN)
        os.close(lease_fd)
        lease_state = "free"
    return readback(
        ok=True,
        reason_code="ok",
        probe_id=probe_id_arg,
        probe_state=str(manifest["state"]),
        mutation_performed=False,
        manifest_path=manifest_path,
        fixture_root=fixture_path,
        lease_state=lease_state,
        target_plan=str(manifest["target_plan"]),
    ), 0


def mutate_probe(mark_interrupted: bool) -> tuple[dict[str, object], int]:
    manifest, probe_path, manifest_path, fixture_path = existing_probe()
    lease_path = probe_path / "lease.lock"
    try:
        lease_fd, lease_state = try_acquire_lease(lease_path)
    except Exception:
        stop(
            "manifest_invalid",
            probe_id=probe_id_arg,
            manifest_path=manifest_path,
            fixture_root=fixture_path,
            target_plan=str(manifest["target_plan"]),
        )
    if lease_fd is None:
        stop(
            "lease_held",
            probe_id=probe_id_arg,
            probe_state=str(manifest["state"]),
            manifest_path=manifest_path,
            fixture_root=fixture_path,
            lease_state=lease_state,
            target_plan=str(manifest["target_plan"]),
        )
    try:
        original = (
            identity(lstat_directory(probe_path, 0o700)),
            identity(lstat_regular(manifest_path, 0o600)),
            identity(lstat_regular(lease_path, 0o600)),
        )
        if mark_interrupted:
            if manifest["state"] not in {"prepared", "running"}:
                stop(
                    "transition_invalid",
                    probe_id=probe_id_arg,
                    probe_state=str(manifest["state"]),
                    manifest_path=manifest_path,
                    fixture_root=fixture_path,
                    lease_state="held_by_helper",
                    target_plan=str(manifest["target_plan"]),
                )
        elif manifest["state"] not in TERMINAL_STATES:
            stop(
                "transition_invalid",
                probe_id=probe_id_arg,
                probe_state=str(manifest["state"]),
                manifest_path=manifest_path,
                fixture_root=fixture_path,
                lease_state="held_by_helper",
                target_plan=str(manifest["target_plan"]),
            )
        mutation_delay()
        try:
            current, current_probe_path, current_manifest_path, current_fixture_path = validate_manifest(probe_id_arg)
        except Exception:
            stop(
                "unsafe_probe_path",
                probe_id=probe_id_arg,
                probe_state="invalid",
                manifest_path=None,
                fixture_root=None,
                lease_state="held_by_helper",
                target_plan=str(manifest["target_plan"]),
            )
        repeated = (
            identity(lstat_directory(current_probe_path, 0o700)),
            identity(lstat_regular(current_manifest_path, 0o600)),
            identity(lstat_regular(lease_path, 0o600)),
        )
        if original != repeated or current != manifest:
            stop(
                "unsafe_probe_path",
                probe_id=probe_id_arg,
                probe_state="invalid",
                manifest_path=current_manifest_path,
                fixture_root=current_fixture_path,
                lease_state="held_by_helper",
                target_plan=str(manifest["target_plan"]),
            )
        safe_tree(probe_path)
        final_identity = (
            identity(lstat_directory(probe_path, 0o700)),
            identity(lstat_regular(manifest_path, 0o600)),
            identity(lstat_regular(lease_path, 0o600)),
        )
        if final_identity != original:
            stop(
                "unsafe_probe_path",
                probe_id=probe_id_arg,
                probe_state="invalid",
                manifest_path=manifest_path,
                fixture_root=fixture_path,
                lease_state="held_by_helper",
                target_plan=str(manifest["target_plan"]),
            )
        if mark_interrupted:
            updated = dict(manifest)
            updated["state"] = "failed" if manifest["state"] == "prepared" else "interrupted"
            updated["finished_at"] = utc_now()
            updated["retain_reason"] = updated["state"]
            atomic_manifest_write(manifest_path, updated)
            final, _final_probe, final_manifest, final_fixture = validate_manifest(probe_id_arg)
            return readback(
                ok=True,
                reason_code="ok",
                probe_id=probe_id_arg,
                probe_state=str(final["state"]),
                mutation_performed=True,
                manifest_path=final_manifest,
                fixture_root=final_fixture,
                lease_state="held_by_helper",
                target_plan=str(final["target_plan"]),
            ), 0

        shutil.rmtree(probe_path)
        fsync_directory(probe_root)
        if probe_path.exists() or probe_path.is_symlink():
            stop(
                "post_readback_failed",
                probe_id=probe_id_arg,
                probe_state="invalid",
                mutation_performed=True,
                lease_state="held_by_helper",
            )
        return readback(
            ok=True,
            reason_code="ok",
            probe_id=probe_id_arg,
            probe_state="absent",
            mutation_performed=True,
            manifest_path=None,
            fixture_root=None,
            lease_state="absent",
            target_plan=None,
        ), 0
    finally:
        fcntl.flock(lease_fd, fcntl.LOCK_UN)
        os.close(lease_fd)


try:
    if operation == "run":
        output, exit_code = run_probe()
    elif operation == "inspect":
        output, exit_code = inspect_probe()
    elif operation == "mark-interrupted":
        output, exit_code = mutate_probe(True)
    elif operation == "recover":
        output, exit_code = mutate_probe(False)
    else:
        stop("usage_error", rc=2, lease_state="absent")
except Result as result:
    output, exit_code = result.payload, result.rc
except Exception:
    output = readback(
        ok=False,
        reason_code="internal_error",
        probe_id=probe_id_arg or None,
        probe_state="invalid",
        mutation_performed=False,
        manifest_path=None,
        fixture_root=None,
        lease_state="invalid",
        target_plan=None,
    )
    exit_code = 126

print(json.dumps(output, ensure_ascii=False, sort_keys=True))
raise SystemExit(exit_code)
PY
}

_planveyor_role_run_prune() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_prune)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local receipt_root="${1:-}" output_root="${2:-}" session_key="${3:-}" current_run_id="${4:-}" latest_path="${5:-}"
  local fail_stage="" kill_stage=""
  if (( $+functions[_planveyor_role_run_test_prune_failure] )); then
    print -r -- '{"affected_paths":[],"mutation_performed":false,"ok":false,"reason":"synthetic_prune_failure"}'
    return 1
  fi
  if (( $+functions[_planveyor_role_run_test_prune_fail_stage] )); then
    fail_stage="$(_planveyor_role_run_test_prune_fail_stage 2>/dev/null || true)"
  fi
  if (( $+functions[_planveyor_role_run_test_prune_kill_stage] )); then
    kill_stage="$(_planveyor_role_run_test_prune_kill_stage 2>/dev/null || true)"
  fi
  _planveyor_py_any - "$receipt_root" "$output_root" "$session_key" "$current_run_id" "$latest_path" "$fail_stage" "$kill_stage" <<'PY'
from __future__ import annotations

from datetime import datetime
import fcntl
import json
import os
import pathlib
import re
import secrets
import shutil
import stat
import sys

receipt_root = pathlib.Path(sys.argv[1])
output_root = pathlib.Path(sys.argv[2])
session_key = sys.argv[3]
current_run_id = sys.argv[4]
latest_path = pathlib.Path(sys.argv[5])
fail_stage = sys.argv[6]
kill_stage = sys.argv[7]
unclassified: list[str] = []
unclassified_orphan_output_dirs: list[str] = []
valid_run_ids: set[str] = set()
candidates: list[tuple[datetime, str, pathlib.Path]] = []
recovered: list[dict[str, str]] = []
affected_paths: set[str] = set()
any_mutation = False

JOURNAL_SCHEMA = "role_run_prune_journal.v1"
JOURNAL_RE = re.compile(
    r"^\.prune-txn-([0-9a-f]{32})\.(building|prepared|committed|retired)$"
)
PRUNE_LEASE_NAME = "retention-prune.lock"


def affect(*paths: pathlib.Path | str) -> None:
    affected_paths.update(str(path) for path in paths if str(path))


def affected(*paths: pathlib.Path | str) -> list[str]:
    values = set(affected_paths)
    values.update(str(path) for path in paths if str(path))
    return sorted(values)


def parsed_timestamp(value: object) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed


def maybe_fail(stage: str) -> None:
    if fail_stage == stage:
        raise OSError(f"synthetic_prune_{stage}_failure")


def maybe_kill(stage: str) -> None:
    if kill_stage == stage:
        os._exit(97)


def lexists(path: pathlib.Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def fsync_directory(directory: pathlib.Path) -> None:
    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def fsync_directories() -> None:
    for directory in (receipt_root, output_root):
        fsync_directory(directory)


def require_regular(path: pathlib.Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"not a regular file: {path}")


def require_directory(path: pathlib.Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"not a directory: {path}")


class JournalLifecycleError(OSError):
    def __init__(self, stage: str, cause: OSError) -> None:
        super().__init__(f"{stage}:{cause.__class__.__name__}:{cause}")
        self.stage = stage


def journal_step(stage: str, action):
    try:
        result = action()
        maybe_fail(stage)
    except OSError as exc:
        raise JournalLifecycleError(stage, exc) from exc
    maybe_kill(stage)
    return result


def acquire_prune_lease() -> int:
    lock_root = output_root / ".locks"
    try:
        lock_root.mkdir(mode=0o700, exist_ok=True)
        require_directory(lock_root)
        lock_root.chmod(0o700)
        lease_path = lock_root / PRUNE_LEASE_NAME
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        lease_fd = os.open(lease_path, flags, 0o600)
        lease_info = os.fstat(lease_fd)
        if not stat.S_ISREG(lease_info.st_mode):
            raise ValueError(f"not a regular lease file: {lease_path}")
        os.fchmod(lease_fd, 0o600)
        try:
            fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(lease_fd)
            print(json.dumps({
                "ok": False,
                "reason": "retention_prune_lock_contended",
                "lease_path": str(lease_path),
                "affected_paths": [str(lease_path)],
                "mutation_performed": False,
            }, sort_keys=True))
            raise SystemExit(1)
        return lease_fd
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "reason": f"retention_prune_lease_failed:{exc.__class__.__name__}:{exc}",
            "affected_paths": [],
            "mutation_performed": False,
        }, sort_keys=True))
        raise SystemExit(1)


def journal_paths(token: str) -> dict[str, pathlib.Path]:
    return {
        "building": receipt_root / f".prune-txn-{token}.building",
        "prepared": receipt_root / f".prune-txn-{token}.prepared",
        "committed": receipt_root / f".prune-txn-{token}.committed",
        "retired": receipt_root / f".prune-txn-{token}.retired",
        "staged_receipt": receipt_root / f".prune-txn-{token}.receipt",
        "staged_output": output_root / f".prune-txn-{token}.output",
    }


def load_journal(journal_path: pathlib.Path, token: str) -> dict[str, object]:
    require_directory(journal_path)
    entries = list(journal_path.iterdir())
    if [entry.name for entry in entries] != ["journal.json"]:
        raise ValueError("journal directory contents mismatch")
    journal_file = entries[0]
    require_regular(journal_file)
    journal_path.chmod(0o700)
    journal_file.chmod(0o600)
    payload = json.loads(journal_file.read_text(encoding="utf-8"))
    run_id = str(payload.get("run_id", ""))
    payload_session_key = str(payload.get("session_key", ""))
    owner_pid = int(payload.get("owner_pid", 0))
    output_present = payload.get("output_present")
    expected_paths = journal_paths(token)
    if (
        payload.get("schema_version") != JOURNAL_SCHEMA
        or payload.get("token") != token
        or payload.get("lease_name") not in {None, PRUNE_LEASE_NAME}
        or not run_id
        or pathlib.PurePath(run_id).name != run_id
        or run_id in {".", ".."}
        or not payload_session_key
        or owner_pid <= 0
        or not isinstance(output_present, bool)
        or payload.get("receipt_name") != f"{run_id}.json"
        or payload.get("output_name") != run_id
        or payload.get("staged_receipt_name") != expected_paths["staged_receipt"].name
        or payload.get("staged_output_name") != expected_paths["staged_output"].name
    ):
        raise ValueError("journal payload mismatch")
    return payload


def cleanup_phase_directory(phase_path: pathlib.Path) -> None:
    require_directory(phase_path)
    entries = list(phase_path.iterdir())
    if any(entry.name != "journal.json" for entry in entries):
        raise ValueError("journal directory contents mismatch")
    for entry in entries:
        require_regular(entry)
        entry.unlink()
    phase_path.rmdir()
    fsync_directory(receipt_root)


def incomplete_legacy_phase_is_discardable(
    phase_path: pathlib.Path,
    token: str,
) -> bool:
    paths = journal_paths(token)
    if lexists(paths["staged_receipt"]) or lexists(paths["staged_output"]):
        return False
    try:
        require_directory(phase_path)
        entries = list(phase_path.iterdir())
        if not entries:
            return True
        if len(entries) != 1 or entries[0].name != "journal.json":
            return False
        require_regular(entries[0])
        json.loads(entries[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return True
    except Exception:
        return False
    return False


def write_journal(token: str, payload: dict[str, object]) -> pathlib.Path:
    paths = journal_paths(token)
    building_path = paths["building"]
    prepared_path = paths["prepared"]
    journal_step("journal_mkdir", lambda: building_path.mkdir(mode=0o700))
    journal_file = building_path / "journal.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(journal_file, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as handle:
            def write_payload() -> None:
                json.dump(payload, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()

            journal_step("journal_write", write_payload)
            journal_step("journal_file_fsync", lambda: os.fsync(handle.fileno()))
    finally:
        os.close(fd)
    journal_step("journal_phase_fsync", lambda: fsync_directory(building_path))
    journal_step("journal_publish", lambda: building_path.rename(prepared_path))
    journal_step("journal_root_fsync", lambda: fsync_directory(receipt_root))
    return prepared_path


def retire_journal(journal_path: pathlib.Path, token: str) -> None:
    retired_path = journal_paths(token)["retired"]
    if journal_path != retired_path:
        journal_step("journal_retire", lambda: journal_path.rename(retired_path))
        journal_step("journal_retire_root_fsync", lambda: fsync_directory(receipt_root))
    require_directory(retired_path)
    entries = list(retired_path.iterdir())
    if any(entry.name != "journal.json" for entry in entries):
        raise ValueError("journal directory contents mismatch")
    journal_file = retired_path / "journal.json"
    if lexists(journal_file):
        require_regular(journal_file)
        journal_step("journal_payload_unlink", journal_file.unlink)
    journal_step("journal_rmdir", retired_path.rmdir)
    journal_step("journal_cleanup_root_fsync", lambda: fsync_directory(receipt_root))


def recover_journal(
    journal_path: pathlib.Path,
    phase: str,
    token: str,
    payload: dict[str, object],
    mutation: list[bool],
) -> str:
    run_id = str(payload["run_id"])
    receipt_path = receipt_root / str(payload["receipt_name"])
    output_path = output_root / str(payload["output_name"])
    paths = journal_paths(token)
    staged_receipt = paths["staged_receipt"]
    staged_output = paths["staged_output"]
    output_present = bool(payload["output_present"])

    receipt_exists = lexists(receipt_path)
    staged_receipt_exists = lexists(staged_receipt)
    output_exists = lexists(output_path)
    staged_output_exists = lexists(staged_output)
    if phase == "prepared":
        if receipt_exists == staged_receipt_exists:
            raise ValueError("prepared receipt state is ambiguous")
        if receipt_exists:
            require_regular(receipt_path)
        else:
            require_regular(staged_receipt)
        if output_present:
            if output_exists == staged_output_exists:
                raise ValueError("prepared output state is ambiguous")
            if output_exists:
                require_directory(output_path)
            else:
                require_directory(staged_output)
        elif output_exists or staged_output_exists:
            raise ValueError("unexpected output for receipt-only transaction")

        if staged_receipt_exists:
            staged_receipt.rename(receipt_path)
            mutation[0] = True
        if staged_output_exists:
            staged_output.rename(output_path)
            mutation[0] = True
        fsync_directories()
        retire_journal(journal_path, token)
        mutation[0] = True
        return "rolled_back"

    if receipt_exists or output_exists:
        raise ValueError("committed transaction restored canonical path")
    if staged_receipt_exists:
        require_regular(staged_receipt)
    if staged_output_exists:
        require_directory(staged_output)
    if staged_output_exists:
        shutil.rmtree(staged_output)
        mutation[0] = True
    if staged_receipt_exists:
        staged_receipt.unlink()
        mutation[0] = True
    fsync_directories()
    retire_journal(journal_path, token)
    mutation[0] = True
    return "cleanup_completed"


prune_lease_fd = acquire_prune_lease()
journals_by_token: dict[str, list[tuple[pathlib.Path, str]]] = {}
for path in sorted(receipt_root.iterdir(), key=lambda item: item.name):
    match = JOURNAL_RE.fullmatch(path.name)
    if not match:
        continue
    token, phase = match.groups()
    journals_by_token.setdefault(token, []).append((path, phase))

for token, records in sorted(journals_by_token.items()):
    for record_path, _ in records:
        affect(record_path)
    if len(records) != 1:
        unclassified.extend(str(path) for path, _ in records)
        continue
    journal_path, phase = records[0]
    if phase in {"building", "retired"}:
        try:
            phase_paths = journal_paths(token)
            if lexists(phase_paths["staged_receipt"]) or lexists(phase_paths["staged_output"]):
                raise ValueError("terminal journal phase has staging debt")
            cleanup_phase_directory(journal_path)
            any_mutation = True
        except Exception:
            unclassified.append(str(journal_path))
        continue
    try:
        payload = load_journal(journal_path, token)
    except Exception:
        if incomplete_legacy_phase_is_discardable(journal_path, token):
            try:
                cleanup_phase_directory(journal_path)
                any_mutation = True
                continue
            except Exception:
                pass
        unclassified.append(str(journal_path))
        continue
    recovery_mutation = [False]
    recovery_paths = journal_paths(token)
    affect(
        journal_path,
        receipt_root / str(payload["receipt_name"]),
        output_root / str(payload["output_name"]),
        recovery_paths["staged_receipt"],
        recovery_paths["staged_output"],
    )
    try:
        action = recover_journal(journal_path, phase, token, payload, recovery_mutation)
        any_mutation = any_mutation or recovery_mutation[0]
        recovered.append({"run_id": str(payload["run_id"]), "action": action})
    except Exception as exc:
        any_mutation = any_mutation or recovery_mutation[0]
        print(json.dumps({
            "ok": False,
            "reason": f"staging_recovery_failed:{exc.__class__.__name__}:{exc}",
            "affected_run_id": str(payload.get("run_id", "")),
            "recovery_journal_path": str(next(
                (
                    recovery_paths[phase_name]
                    for phase_name in ("building", "prepared", "committed", "retired")
                    if lexists(recovery_paths[phase_name])
                ),
                "",
            )),
            "affected_paths": affected(),
            "mutation_performed": any_mutation,
            "recovered_before_failure": recovered,
            "failure_stage": getattr(exc, "stage", "journal_recovery"),
        }, sort_keys=True))
        raise SystemExit(1)


for path in sorted(receipt_root.iterdir(), key=lambda item: item.name):
    if JOURNAL_RE.fullmatch(path.name):
        continue
    affect(path)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or path.suffix != ".json":
            raise ValueError("not a regular json receipt")
        path.chmod(0o600)
        payload = json.loads(path.read_text(encoding="utf-8"))
        run_id = str(payload.get("run_id", ""))
        if payload.get("schema_version") != "role_execution_receipt.v1" or path.stem != run_id:
            raise ValueError("schema or run_id mismatch")
        timestamp = parsed_timestamp(payload.get("receipt_written_at"))
        payload_session_key = str(payload.get("session_key", ""))
        if not payload_session_key:
            raise ValueError("missing session_key")
        valid_run_ids.add(run_id)
        if payload_session_key == session_key:
            candidates.append((timestamp, run_id, path))
    except Exception:
        unclassified.append(str(path))

for path in sorted(output_root.iterdir(), key=lambda item: item.name):
    if path.name == ".locks":
        continue
    affect(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        continue
    active_transaction = False
    ready_path = path / "lock.ready.json"
    if (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and path.name not in valid_run_ids
        and not (path / "transaction.done").exists()
        and ready_path.is_file()
        and not ready_path.is_symlink()
    ):
        try:
            ready_payload = json.loads(ready_path.read_text(encoding="utf-8"))
            parent_pid = int(ready_payload.get("parent_pid", 0))
            if ready_payload.get("state") in {"acquired", "contended"} and parent_pid > 0:
                os.kill(parent_pid, 0)
                active_transaction = True
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            active_transaction = False
    if active_transaction:
        continue
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or path.name not in valid_run_ids:
        unclassified.append(str(path))
        if (
            stat.S_ISDIR(info.st_mode)
            and not stat.S_ISLNK(info.st_mode)
            and path.name not in valid_run_ids
        ):
            unclassified_orphan_output_dirs.append(str(path))
        continue
    path.chmod(0o700)
    for managed_path in path.rglob("*"):
        affect(managed_path)
        try:
            managed_info = managed_path.lstat()
            if stat.S_ISLNK(managed_info.st_mode):
                raise ValueError("symlink in managed run dir")
            if stat.S_ISDIR(managed_info.st_mode):
                managed_path.chmod(0o700)
            elif stat.S_ISREG(managed_info.st_mode):
                managed_path.chmod(0o600)
            else:
                raise ValueError("unsupported managed run path")
        except Exception:
            unclassified.append(str(managed_path))

if unclassified:
    reason = (
        "unclassified_orphan_output_dir"
        if sorted(unclassified) == sorted(unclassified_orphan_output_dirs)
        else "unclassified_carriers"
    )
    print(json.dumps({
        "ok": False,
        "reason": reason,
        "paths": sorted(unclassified),
        "affected_paths": affected(),
        "mutation_performed": any_mutation,
    }, sort_keys=True))
    raise SystemExit(1)

latest_run_id = ""
for line in latest_path.read_text(encoding="utf-8").splitlines():
    if line.startswith("run_id="):
        latest_run_id = line.split("=", 1)[1]
        break

candidates.sort(key=lambda item: (item[0], item[1]))
protected = {current_run_id, latest_run_id}
keep_ids = {run_id for _, run_id, _ in candidates[-20:]} | protected
to_prune = [(run_id, path) for _, run_id, path in candidates if run_id not in keep_ids]
pruned: list[str] = []
for run_id, receipt_path in to_prune:
    output_path = output_root / run_id
    token = secrets.token_hex(16)
    paths = journal_paths(token)
    building_journal = paths["building"]
    prepared_journal = paths["prepared"]
    committed_journal = paths["committed"]
    retired_journal = paths["retired"]
    staged_receipt = paths["staged_receipt"]
    staged_output = paths["staged_output"]
    affect(
        receipt_path,
        output_path,
        building_journal,
        prepared_journal,
        committed_journal,
        retired_journal,
        staged_receipt,
        staged_output,
    )
    output_present = lexists(output_path)
    journal_payload: dict[str, object] = {
        "schema_version": JOURNAL_SCHEMA,
        "token": token,
        "lease_name": PRUNE_LEASE_NAME,
        "run_id": run_id,
        "session_key": session_key,
        "owner_pid": os.getpid(),
        "receipt_name": receipt_path.name,
        "output_name": output_path.name,
        "staged_receipt_name": staged_receipt.name,
        "staged_output_name": staged_output.name,
        "output_present": output_present,
    }
    try:
        prepared_journal = write_journal(token, journal_payload)
    except OSError as exc:
        cleanup_errors: list[str] = []
        try:
            for phase_path in (building_journal, prepared_journal, retired_journal):
                if lexists(phase_path):
                    cleanup_phase_directory(phase_path)
        except Exception as cleanup_exc:
            cleanup_errors.append(f"{cleanup_exc.__class__.__name__}:{cleanup_exc}")
        remaining_journal = next(
            (path for path in (building_journal, prepared_journal, retired_journal) if lexists(path)),
            None,
        )
        print(json.dumps({
            "ok": False,
            "reason": f"{exc.__class__.__name__}:{exc}",
            "failure_stage": getattr(exc, "stage", "journal_prepare"),
            "affected_run_id": run_id,
            "affected_paths": affected(),
            "mutation_performed": any_mutation or remaining_journal is not None,
            "cleanup_errors": cleanup_errors,
            "recovery_journal_path": str(remaining_journal or ""),
            "pruned_before_failure": pruned,
        }, sort_keys=True))
        raise SystemExit(1)

    stage = "output_remove"
    try:
        if output_present:
            maybe_fail(stage)
            output_path.rename(staged_output)
            maybe_kill(stage)
        stage = "receipt_unlink"
        maybe_fail(stage)
        receipt_path.rename(staged_receipt)
        maybe_kill(stage)
        stage = "dir_fsync"
        maybe_fail(stage)
        fsync_directories()
        maybe_kill(stage)
    except OSError as exc:
        rollback_mutation = [False]
        rollback_errors: list[str] = []
        try:
            recover_journal(prepared_journal, "prepared", token, journal_payload, rollback_mutation)
        except Exception as rollback_exc:
            rollback_errors.append(f"{rollback_exc.__class__.__name__}:{rollback_exc}")
        rollback_state = "complete" if not rollback_errors else "incomplete"
        print(json.dumps({
            "ok": False,
            "reason": f"{exc.__class__.__name__}:{exc}",
            "failure_stage": getattr(
                rollback_exc if rollback_errors else exc,
                "stage",
                stage,
            ),
            "affected_run_id": run_id,
            "affected_paths": affected(),
            "mutation_performed": any_mutation or rollback_state != "complete",
            "rollback_state": rollback_state,
            "rollback_errors": rollback_errors,
            "recovery_journal_path": str(next(
                (path for path in (prepared_journal, retired_journal) if lexists(path)),
                "",
            )) if rollback_errors else "",
            "pruned_before_failure": pruned,
        }, sort_keys=True))
        raise SystemExit(1)

    try:
        prepared_journal.rename(committed_journal)
        fsync_directory(receipt_root)
        maybe_kill("journal_commit")
    except OSError as exc:
        if lexists(committed_journal):
            pruned.append(run_id)
            any_mutation = True
            print(json.dumps({
                "ok": False,
                "reason": f"{exc.__class__.__name__}:{exc}",
                "failure_stage": "journal_commit",
                "affected_run_id": run_id,
                "affected_paths": affected(),
                "mutation_performed": True,
                "rollback_state": "committed_cleanup_pending",
                "cleanup_pending_paths": [str(path) for path in (staged_receipt, staged_output) if lexists(path)],
                "recovery_journal_path": str(committed_journal),
                "pruned_before_failure": pruned,
            }, sort_keys=True))
            raise SystemExit(1)
        rollback_mutation = [False]
        rollback_errors: list[str] = []
        try:
            recover_journal(prepared_journal, "prepared", token, journal_payload, rollback_mutation)
        except Exception as rollback_exc:
            rollback_errors.append(f"{rollback_exc.__class__.__name__}:{rollback_exc}")
        print(json.dumps({
            "ok": False,
            "reason": f"{exc.__class__.__name__}:{exc}",
            "failure_stage": "journal_commit",
            "affected_run_id": run_id,
            "affected_paths": affected(),
            "mutation_performed": any_mutation or bool(rollback_errors),
            "rollback_state": "complete" if not rollback_errors else "incomplete",
            "rollback_errors": rollback_errors,
            "recovery_journal_path": str(next(
                (path for path in (prepared_journal, retired_journal) if lexists(path)),
                "",
            )) if rollback_errors else "",
            "pruned_before_failure": pruned,
        }, sort_keys=True))
        raise SystemExit(1)

    pruned.append(run_id)
    any_mutation = True
    cleanup_stage = "output_cleanup"
    try:
        if output_present:
            maybe_fail(cleanup_stage)
            shutil.rmtree(staged_output)
            maybe_kill(cleanup_stage)
        cleanup_stage = "receipt_cleanup"
        maybe_fail(cleanup_stage)
        staged_receipt.unlink()
        maybe_kill(cleanup_stage)
        cleanup_stage = "dir_fsync_cleanup"
        maybe_fail(cleanup_stage)
        fsync_directories()
        maybe_kill(cleanup_stage)
        cleanup_stage = "journal_cleanup"
        retire_journal(committed_journal, token)
    except OSError as exc:
        cleanup_stage = getattr(exc, "stage", cleanup_stage)
        pending_paths = [
            str(path)
            for path in (staged_receipt, staged_output)
            if lexists(path)
        ]
        print(json.dumps({
            "ok": False,
            "reason": f"{exc.__class__.__name__}:{exc}",
            "failure_stage": cleanup_stage,
            "affected_run_id": run_id,
            "affected_paths": affected(),
            "mutation_performed": True,
            "rollback_state": "committed_cleanup_pending",
            "cleanup_pending_paths": pending_paths,
            "recovery_journal_path": str(next(
                (path for path in (committed_journal, retired_journal) if lexists(path)),
                "",
            )),
            "pruned_before_failure": pruned,
        }, sort_keys=True))
        raise SystemExit(1)

print(json.dumps({
    "affected_paths": affected(),
    "mutation_performed": any_mutation,
    "ok": True,
    "reason": "ok",
    "pruned": pruned,
    "retained": len(candidates) - len(pruned),
    "recovered": recovered,
}, sort_keys=True))
PY
}

_planveyor_role_run_prune_result_kv() {
  local payload_json="${1:-}" helper_rc="${2:-}"
  _planveyor_py_any - "$payload_json" "$helper_rc" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1])
    helper_rc = int(sys.argv[2])
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    ok = payload.get("ok")
    reason = payload.get("reason")
    paths = payload.get("affected_paths")
    mutation = payload.get("mutation_performed")
    if not isinstance(ok, bool):
        raise ValueError("ok must be bool")
    if not isinstance(reason, str) or not reason:
        raise ValueError("reason must be non-empty string")
    if (
        not isinstance(paths, list)
        or any(not isinstance(path, str) for path in paths)
        or paths != sorted(set(paths))
    ):
        raise ValueError("affected_paths must be sorted unique strings")
    if not isinstance(mutation, bool):
        raise ValueError("mutation_performed must be bool")
    if helper_rc == 0 and ok is True and reason == "ok":
        state = "completed"
    elif helper_rc != 0 and ok is False:
        state = "blocked"
    else:
        raise ValueError("helper status mismatch")
except (TypeError, ValueError, json.JSONDecodeError):
    raise SystemExit(1)

print(f"state={state}")
print(f"reason={reason}")
print("paths_json=" + json.dumps(paths, ensure_ascii=False, separators=(",", ":")))
print(f"mutation_performed={'true' if mutation else 'false'}")
PY
}

# Passive frozen-receipt parser: this verifies an already-published artifact after
# execution and cannot admit a later live action, so it deliberately does not
# recapture the current target context.
_planveyor_role_run_check_json() {
  local receipt_path="${1:-}"
  local expected_run_id="${2:-}"
  local expected_session_key="${3:-}"
  local expected_target_plan="${4:-}"
  local expected_pre_status="${5:-}"
  [[ -n "${receipt_path//[[:space:]]/}" ]] || return 1

  _planveyor_py_any - "$receipt_path" "$expected_run_id" "$expected_session_key" "$expected_target_plan" "$expected_pre_status" <<'PY'
from __future__ import annotations

import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
expected = {
    "run_id": sys.argv[2],
    "session_key": sys.argv[3],
    "target_plan": sys.argv[4],
    "pre_status": sys.argv[5],
}
required = [
    "schema_version",
    "run_id",
    "role",
    "session_key",
    "wrapper",
    "runner_id",
    "runner_alias",
    "profile",
    "model",
    "configured_model_id",
    "observable_model_id",
    "model_id_state",
    "sid",
    "child_session",
    "target_plan",
    "pre_status",
    "post_status",
    "exit_code",
    "timeout_seconds",
    "duration_seconds",
    "elapsed_seconds",
    "timed_out",
    "terminated_by_timeout",
    "state",
    "started_at",
    "finished_at",
    "receipt_written_at",
]
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(json.dumps({"readback_state": "blocked", "reason": f"unreadable_receipt:{exc.__class__.__name__}"}, sort_keys=True))
    sys.exit(1)

if payload.get("schema_version") != "role_execution_receipt.v1":
    print(json.dumps({"readback_state": "blocked", "reason": "wrong_schema_version", "schema_version": payload.get("schema_version", "")}, sort_keys=True))
    sys.exit(1)

missing = [key for key in required if key not in payload or payload.get(key) in (None, "")]
if missing:
    print(json.dumps({"readback_state": "blocked", "reason": "missing_required_fields", "missing_fields": missing}, sort_keys=True))
    sys.exit(1)

for key, value in expected.items():
    if value and str(payload.get(key, "")) != value:
        print(json.dumps({"readback_state": "blocked", "reason": f"{key}_mismatch", "expected": value, "actual": payload.get(key, "")}, sort_keys=True))
        sys.exit(1)

if not payload.get("finished_at") or not payload.get("started_at"):
    print(json.dumps({"readback_state": "blocked", "reason": "missing_timestamp_window"}, sort_keys=True))
    sys.exit(1)

def block(reason: str, **extra: object) -> None:
    out = {"readback_state": "blocked", "reason": reason}
    out.update(extra)
    print(json.dumps(out, sort_keys=True))
    sys.exit(1)

def as_int(key: str) -> int:
    try:
        return int(payload[key])
    except (TypeError, ValueError):
        block("invalid_timing_field", field=key, actual=payload.get(key))

def as_bool(key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    block("invalid_timing_field", field=key, actual=value)

duration_seconds = as_int("duration_seconds")
elapsed_seconds = as_int("elapsed_seconds")
if elapsed_seconds != duration_seconds:
    block(
        "timing_alias_mismatch",
        elapsed_seconds=elapsed_seconds,
        duration_seconds=duration_seconds,
    )

timed_out = as_bool("timed_out")
terminated_by_timeout = as_bool("terminated_by_timeout")
if terminated_by_timeout != timed_out:
    block(
        "timeout_alias_mismatch",
        terminated_by_timeout=terminated_by_timeout,
        timed_out=timed_out,
    )

state = str(payload.get("state", ""))
if (state == "timeout") != terminated_by_timeout:
    block(
        "timeout_state_mismatch",
        state=state,
        terminated_by_timeout=terminated_by_timeout,
    )

lifecycle_provider_fields = [
    "session_action_requested",
    "session_pointer_relation",
    "process_start_outcome",
    "session_reset_performed",
    "cli_process_mode",
    "process_persistent",
    "provider_error_class",
    "provider_http_status",
    "provider_error_code",
    "provider_retryability",
]
present_contract_fields = [key for key in lifecycle_provider_fields if key in payload]
if not present_contract_fields:
    lifecycle_provider_contract_state = "legacy_absent"
elif len(present_contract_fields) != len(lifecycle_provider_fields):
    block(
        "partial_lifecycle_provider_contract",
        present_fields=present_contract_fields,
        missing_fields=[key for key in lifecycle_provider_fields if key not in payload],
    )
else:
    lifecycle_provider_contract_state = "current"
    source_fields = ["sid_before", "sid_after", "success", "interrupted", "non_green_reason"]
    missing_source_fields = [key for key in source_fields if key not in payload]
    if missing_source_fields:
        block("lifecycle_provider_contract_contradiction", missing_source_fields=missing_source_fields)

    def contract_bool(key: str) -> bool:
        value = payload.get(key)
        if not isinstance(value, bool):
            block("lifecycle_provider_contract_contradiction", field=key, actual=value)
        return value

    session_action_requested = str(payload.get("session_action_requested", ""))
    session_pointer_relation = str(payload.get("session_pointer_relation", ""))
    process_start_outcome = str(payload.get("process_start_outcome", ""))
    cli_process_mode = str(payload.get("cli_process_mode", ""))
    provider_error_class = str(payload.get("provider_error_class", ""))
    provider_http_status = payload.get("provider_http_status")
    provider_error_code = payload.get("provider_error_code")
    provider_retryability = str(payload.get("provider_retryability", ""))
    session_reset_performed = contract_bool("session_reset_performed")
    process_persistent = contract_bool("process_persistent")
    success = contract_bool("success")
    interrupted = contract_bool("interrupted")
    exit_code = as_int("exit_code")
    non_green_reason = str(payload.get("non_green_reason", ""))

    enums = {
        "session_action_requested": ({"resume"}, session_action_requested),
        "session_pointer_relation": ({"same", "replaced", "missing"}, session_pointer_relation),
        "process_start_outcome": ({"started", "not_started"}, process_start_outcome),
        "cli_process_mode": ({"one_shot"}, cli_process_mode),
        "provider_error_class": (
            {"model_invalid", "overload", "authentication", "rate_limit", "unknown", "not_applicable"},
            provider_error_class,
        ),
        "provider_retryability": (
            {"retryable", "not_retryable", "unknown", "not_applicable"},
            provider_retryability,
        ),
    }
    for field, (allowed, actual) in enums.items():
        if actual not in allowed:
            block("lifecycle_provider_contract_contradiction", field=field, actual=actual)
    if session_reset_performed or process_persistent:
        block(
            "lifecycle_provider_contract_contradiction",
            session_reset_performed=session_reset_performed,
            process_persistent=process_persistent,
        )
    for field, value in (
        ("provider_http_status", provider_http_status),
        ("provider_error_code", provider_error_code),
    ):
        if not isinstance(value, str) or not (value.isdecimal() or value in {"unknown", "not_applicable"}):
            block("lifecycle_provider_contract_contradiction", field=field, actual=value)

    sid_before = str(payload.get("sid_before", ""))
    sid_after = str(payload.get("sid_after", ""))

    def missing_sid(value: str) -> bool:
        return not value.strip() or value.startswith("N/A (why=")

    if missing_sid(sid_before):
        expected_pointer_relation = "missing"
    elif missing_sid(sid_after):
        block("lifecycle_provider_contract_contradiction", field="sid_after", actual=sid_after)
    elif sid_before == sid_after:
        expected_pointer_relation = "same"
    else:
        expected_pointer_relation = "replaced"
    if session_pointer_relation != expected_pointer_relation:
        block(
            "lifecycle_provider_contract_contradiction",
            field="session_pointer_relation",
            expected=expected_pointer_relation,
            actual=session_pointer_relation,
        )

    process_lifecycle_rows = (
        {
            "source": "started_success",
            "start": "started",
            "state": "success",
            "exit_policy": "exact",
            "exit_codes": {0},
            "reason": "",
            "flags": (True, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "started_timeout",
            "start": "started",
            "state": "timeout",
            "exit_policy": "exact",
            "exit_codes": {124},
            "reason": "timeout",
            "flags": (False, True, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "started_interrupted",
            "start": "started",
            "state": "interrupted",
            "exit_policy": "exact",
            "exit_codes": {130, 143},
            "reason": "interrupted",
            "flags": (False, False, True),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "started_failure",
            "start": "started",
            "state": "failed",
            "exit_policy": "failed_exit",
            "exit_codes": set(),
            "reason": "",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "missing_session_precondition",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "missing_session_sid",
            "flags": (False, False, False),
            "pointer_relations": {"missing"},
        },
        {
            "source": "role_run_lock_contention",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "role_run_lock_contended",
            "flags": (False, False, False),
            "pointer_relations": {"missing"},
        },
        {
            "source": "runner_preflight_precondition",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "preflight_failed",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "runner_preflight_proof_invalid",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "precondition_failed",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "runner_preflight_runner_unreadable",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "runner_not_readable",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "runner_preflight_runner_invalid",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "runner_invalid_for_role",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "runner_preflight_selection_changed",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "runner_changed_since_preflight",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "role_outcome_preflight_precondition",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "role_outcome_preflight_failed",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "role_outcome_recovery_preflight_precondition",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "role_outcome_recovery_preflight_failed",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "missing_wrapper_precondition",
            "start": "not_started",
            "state": "precondition_failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "missing_wrapper_function",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
        {
            "source": "supervisor_spawn_failure",
            "start": "not_started",
            "state": "failed",
            "exit_policy": "exact",
            "exit_codes": {125},
            "reason": "exit_code_125",
            "flags": (False, False, False),
            "pointer_relations": {"same", "replaced"},
        },
    )

    def process_lifecycle_row_matches(row: dict[str, object]) -> bool:
        if (
            process_start_outcome != row["start"]
            or state != row["state"]
            or (success, timed_out, interrupted) != row["flags"]
            or session_pointer_relation not in row["pointer_relations"]
        ):
            return False
        if row["exit_policy"] == "failed_exit":
            return exit_code not in {0, 130, 143} and non_green_reason == f"exit_code_{exit_code}"
        return exit_code in row["exit_codes"] and non_green_reason == row["reason"]

    matched_process_sources = [
        str(row["source"])
        for row in process_lifecycle_rows
        if process_lifecycle_row_matches(row)
    ]
    if len(matched_process_sources) != 1:
        block(
            "lifecycle_provider_contract_contradiction",
            session_pointer_relation=session_pointer_relation,
            process_start_outcome=process_start_outcome,
            state=state,
            exit_code=exit_code,
            success=success,
            timed_out=timed_out,
            interrupted=interrupted,
            non_green_reason=non_green_reason,
            matched_process_sources=matched_process_sources,
        )

    eligible_provider_failure = (
        process_start_outcome == "started"
        and state == "failed"
        and exit_code != 0
        and not timed_out
        and not interrupted
    )
    provider_tuple = (
        provider_http_status,
        provider_error_code,
        provider_error_class,
        provider_retryability,
    )
    if not eligible_provider_failure:
        expected_provider_tuple = ("not_applicable",) * 4
        if provider_tuple != expected_provider_tuple:
            block(
                "lifecycle_provider_contract_contradiction",
                expected_provider_tuple=expected_provider_tuple,
                actual_provider_tuple=provider_tuple,
            )
    else:
        allowed_provider_tuples = {
            ("400", "1211", "model_invalid", "not_retryable"),
            ("529", "1305", "overload", "retryable"),
            ("401", "unknown", "authentication", "not_retryable"),
            ("403", "unknown", "authentication", "not_retryable"),
            ("429", "unknown", "rate_limit", "retryable"),
            ("unknown", "unknown", "unknown", "unknown"),
        }
        if provider_tuple not in allowed_provider_tuples:
            block("lifecycle_provider_contract_contradiction", actual_provider_tuple=provider_tuple)

print(
    json.dumps(
        {
            "readback_state": "ok",
            "reason": "ok",
            "run_id": payload["run_id"],
            "session_key": payload["session_key"],
            "target_plan": payload["target_plan"],
            "lifecycle_provider_contract_state": lifecycle_provider_contract_state,
        },
        sort_keys=True,
    )
)
PY
}

planveyor_role_run_receipt_check() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_role_run_receipt_check)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local receipt_path="${1:-}"
  if [[ "$receipt_path" == "--help" || "$receipt_path" == "-h" ]]; then
    echo "Usage: planveyor_role_run_receipt_check <receipt.json> [--run-id ID] [--session-key KEY] [--target-plan PLAN] [--pre-status STATUS] [--json]" >&2
    return 0
  fi
  [[ -n "${receipt_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_role_run_receipt_check <receipt.json> [--run-id ID] [--session-key KEY] [--target-plan PLAN] [--pre-status STATUS] [--json]" >&2
    return 2
  }
  shift
  local expected_run_id="" expected_session_key="" expected_target_plan="" expected_pre_status="" json=0
  while (( $# > 0 )); do
    case "${1:-}" in
      --run-id) shift; expected_run_id="${1:-}" ;;
      --session-key) shift; expected_session_key="${1:-}" ;;
      --target-plan) shift; expected_target_plan="${1:-}" ;;
      --pre-status) shift; expected_pre_status="${1:-}" ;;
      --json) json=1 ;;
      *)
        echo "Usage: planveyor_role_run_receipt_check <receipt.json> [--run-id ID] [--session-key KEY] [--target-plan PLAN] [--pre-status STATUS] [--json]" >&2
        return 2
        ;;
    esac
    shift
  done

  local out=""
  out="$(_planveyor_role_run_check_json "$receipt_path" "$expected_run_id" "$expected_session_key" "$expected_target_plan" "$expected_pre_status")"
  local rc=$?
  if (( json )); then
    print -r -- "$out"
  else
    _planveyor_py_any - "$out" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
for key in sorted(payload):
    print(f"{key}={payload[key]}")
PY
  fi
  return $rc
}

_planveyor_explicit_plan_normalize() {
  local root="${1:-}"
  local raw_plan="${2:-}"
  [[ -n "${root//[[:space:]]/}" && -n "${raw_plan//[[:space:]]/}" ]] || return 1
  _planveyor_py_any - "$root" "$raw_plan" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
raw = sys.argv[2].strip()
candidate = Path(raw)
if not candidate.is_absolute():
    candidate = root / candidate
try:
    candidate = candidate.resolve(strict=True)
    relative = candidate.relative_to(root)
except (OSError, ValueError):
    raise SystemExit(1)
if not candidate.is_file() or relative.parts[:2] != ("docs", "plans") or candidate.suffix != ".md":
    raise SystemExit(1)
print(relative.as_posix())
PY
}

planveyor_role_run() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_role_run)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local role_arg="" json=0 timeout_arg_seen=0
  local usage="Usage: planveyor_role_run <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> [--timeout SECONDS] [--json]"
  local default_timeout_seconds="${PLANVEYOR_ROLE_RUN_DEFAULT_TIMEOUT_SECONDS:-3600}"
  [[ "$default_timeout_seconds" == <-> && "$default_timeout_seconds" -gt 0 ]] || default_timeout_seconds=3600
  local timeout_seconds="${PLANVEYOR_ROLE_RUN_TIMEOUT_SECONDS:-$default_timeout_seconds}"
  while (( $# > 0 )); do
    case "${1:-}" in
      --json) json=1 ;;
      --timeout)
        shift
        timeout_seconds="${1:-}"
        timeout_arg_seen=1
        ;;
      --help|-h)
        echo "$usage" >&2
        return 0
        ;;
      *)
        if [[ -z "${role_arg//[[:space:]]/}" ]]; then
          role_arg="${1:-}"
        else
          echo "$usage" >&2
          return 2
        fi
        ;;
    esac
    shift
  done
  [[ -n "${role_arg//[[:space:]]/}" ]] || {
    echo "$usage" >&2
    return 2
  }
  [[ "$timeout_seconds" == <-> ]] || {
    echo "Invalid --timeout: ${timeout_seconds}" >&2
    return 2
  }
  if (( ! timeout_arg_seen && timeout_seconds <= 0 )); then
    timeout_seconds="$default_timeout_seconds"
  fi

  local plan_path=""
  plan_path="$(planveyor_planpath)" || return 1
  local -a execute_args
  execute_args=("$role_arg" "$plan_path" --timeout "$timeout_seconds")
  (( json )) && execute_args+=(--json)
  _planveyor_role_run_execute_for_plan "${execute_args[@]}"
}

_planveyor_role_run_execute_for_plan() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_run_execute_for_plan)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local role_arg="${1:-}"
  local plan_path="${2:-}"
  local requested_plan="$plan_path"
  local usage="Usage: _planveyor_role_run_execute_for_plan <role-key> <normalized-plan> [--timeout SECONDS] [--preflight-proof JSON] [--json]"
  [[ -n "${role_arg//[[:space:]]/}" && -n "${plan_path//[[:space:]]/}" ]] || {
    echo "$usage" >&2
    return 2
  }
  shift 2
  local json=0 preflight_proof_seen=0 preflight_proof_json=""
  local default_timeout_seconds="${PLANVEYOR_ROLE_RUN_DEFAULT_TIMEOUT_SECONDS:-3600}"
  [[ "$default_timeout_seconds" == <-> && "$default_timeout_seconds" -gt 0 ]] || default_timeout_seconds=3600
  local timeout_seconds="${PLANVEYOR_ROLE_RUN_TIMEOUT_SECONDS:-$default_timeout_seconds}"
  while (( $# > 0 )); do
    case "${1:-}" in
      --json) json=1 ;;
      --timeout)
        shift
        timeout_seconds="${1:-}"
        ;;
      --preflight-proof)
        shift
        (( preflight_proof_seen == 0 )) || {
          echo "$usage" >&2
          return 2
        }
        preflight_proof_json="${1:-}"
        preflight_proof_seen=1
        ;;
      *)
        echo "$usage" >&2
        return 2
        ;;
    esac
    shift
  done
  [[ "$timeout_seconds" == <-> ]] || {
    echo "Invalid --timeout: ${timeout_seconds}" >&2
    return 2
  }

  local normalized=""
  normalized="$(_planveyor_role_runner_preflight_normalize "$role_arg" 2>/dev/null || true)"
  [[ -n "${normalized//[[:space:]]/}" ]] || {
    echo "Unsupported role for planveyor_role_run: ${role_arg}" >&2
    return 2
  }

  local role="" session_key="" wrapper="" runner_role="" unsupported=""
  local part=""
  for part in ${(s:;:)normalized}; do
    case "$part" in
      role=*) role="${part#role=}" ;;
      session_key=*) session_key="${part#session_key=}" ;;
      wrapper=*) wrapper="${part#wrapper=}" ;;
      runner_role=*) runner_role="${part#runner_role=}" ;;
      unsupported=*) unsupported="${part#unsupported=}" ;;
    esac
  done
  [[ -z "${unsupported//[[:space:]]/}" ]] || {
    echo "Unsupported role for planveyor_role_run: ${role_arg}" >&2
    return 2
  }

  local root=""
  root="$(_planveyor_project_root)" || return $?
  plan_path="$(_planveyor_explicit_plan_normalize "$root" "$plan_path" 2>/dev/null || true)"
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Invalid explicit plan for role run: ${requested_plan}" >&2
    return 2
  }
  local resume_sid_preflight=""
  resume_sid_preflight="$(planveyor_session "$session_key" 2>/dev/null || true)"
  [[ "$resume_sid_preflight" == "<SESSION_ID>" ]] && resume_sid_preflight=""
  if [[ -n "${resume_sid_preflight//[[:space:]]/}" ]]; then
    _planveyor_session_authority_resume_validate "$session_key" "$resume_sid_preflight" || return $?
  elif [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    _planveyor_session_missing_recovery "$session_key"
    return $?
  fi
  local status_pre="" status_post=""
  local started_at="" finished_at="" receipt_written_at=""
  local run_stamp="" run_id="" receipt_path="" latest_path="" output_dir="" stdout_path="" stderr_path=""
  local receipt_root="${root}/.planveyor.role_runs" output_root="${root}/.tmp/planveyor_role_runs"
  local lock_root="${output_root}/.locks" lock_path="" lock_ready_path="" lock_release_path="" transaction_done_path="" lock_pid="" lock_holder_pid="" lock_state=""
  local runner_id="N/A (why=preflight proof unavailable)" model="N/A (why=preflight proof unavailable)" sid_before="" sid_after="" sid="" child_session="false" result_artifact=""
  local -a model_identity_args
  model_identity_args=(
    "runner_alias=N/A (why=preflight proof unavailable)"
    "profile=N/A (why=preflight proof unavailable)"
    "configured_model_id=N/A (why=preflight proof unavailable)"
    "observable_model_id=N/A (why=preflight proof unavailable)"
    "model_id_state=unknown"
  )
  local child_rc=0 final_rc=0 state="" timed_out="false" interrupted="false" success="false" non_green_reason=""
  local readback_state="ok" readback_reason="ok" process_started="false" process_start_outcome="not_started"
  local retention_prune_state="not_run" retention_prune_reason="upstream_not_reached"
  local retention_prune_paths_json="[]" retention_prune_mutation_performed="false"
  local session_pointer_relation="missing" provider_http_status="not_applicable" provider_error_code="not_applicable"
  local provider_error_class="not_applicable" provider_retryability="not_applicable" precondition_failed="false"
  local role_outcome_attempted="false" role_outcome_preflight_blocked="false" role_outcome_transport_failed="false"
  local role_outcome_recovery_preflight_blocked="false"
  local role_outcome_state="" role_outcome_reason_code="" role_outcome_readback_persisted=""
  local role_outcome_diagnostic_state="" role_outcome_diagnostic_reason_code=""
  local role_outcome_recovery_state="" role_outcome_safe_action=""
  local recovery_of_run_id="${PLANVEYOR_ROLE_OUTCOME_RECOVERY_OF_RUN_ID:-}"
  local rejection_receipt_sha256="${PLANVEYOR_ROLE_OUTCOME_REJECTION_RECEIPT_SHA256:-}"
  local started_seconds=$SECONDS

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  case "$role" in
    architect_initial|architect_censor|planner_censor|coder_censor) child_session="false" ;;
    *) [[ "$session_key" != "$role" ]] && child_session="true" ;;
  esac
  result_artifact="$(_planveyor_result_artifact_for_plan "$plan_path" "stdout receipt")"
  started_at="$(_planveyor_now_utc_iso)"
  run_stamp="$(TZ=UTC date "+%Y%m%dT%H%M%SZ")"
  run_id="${run_stamp}_${session_key}_${$}_${RANDOM}"
  receipt_path="${receipt_root}/${run_id}.json"
  latest_path="${root}/.planveyor.run_receipt.role.${session_key}"
  output_dir="${output_root}/${run_id}"
  stdout_path="${output_dir}/stdout.log"
  stderr_path="${output_dir}/stderr.log"
  local wrapper_source="${output_dir}/wrapper.zsh"
  local preflight_path="${output_dir}/preflight.json" preflight_stderr_path="${output_dir}/preflight.stderr"
  local role_outcome_preflight_path="${output_dir}/role_outcome_preflight.json"
  local role_outcome_readback_path="${output_dir}/role_outcome_readback.json"
  local role_outcome_diagnostic_path="${output_dir}/role_outcome_semantic_diagnostic.json"
  lock_path="${lock_root}/${session_key}.lock"
  lock_ready_path="${output_dir}/lock.ready.json"
  lock_release_path="${output_dir}/lock.release"
  transaction_done_path="${output_dir}/transaction.done"

  local managed_json=""
  managed_json="$(_planveyor_role_run_managed_preflight "$root" "$receipt_root" "$output_root" "$lock_root" "$output_dir" \
    "$receipt_path" "$latest_path" "$lock_path" "$lock_ready_path" "$lock_release_path" "$transaction_done_path" \
    "$stdout_path" "$stderr_path" "$wrapper_source" "$preflight_path" "$preflight_stderr_path" \
    "$role_outcome_preflight_path")"
  if (( $? != 0 )); then
    if (( json )); then
      _planveyor_py_any - "$managed_json" "$session_key" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
payload["session_key"] = sys.argv[2]
print(json.dumps(payload, sort_keys=True))
PY
    else
      print -r -- "error=unsafe_managed_path"
      print -r -- "session_key=${session_key}"
    fi
    popd >/dev/null || true
    return 125
  fi

  _planveyor_role_run_lock_holder "$lock_path" "$lock_ready_path" "$lock_release_path" "${$}" >/dev/null 2>&1 &
  lock_pid=$!
  local wait_index=0
  while (( wait_index < 500 )) && [[ ! -f "$lock_ready_path" ]]; do
    sleep 0.01
    (( wait_index += 1 ))
  done
  if [[ ! -f "$lock_ready_path" ]]; then
    [[ -n "${lock_pid//[[:space:]]/}" ]] && kill "$lock_pid" 2>/dev/null || true
    wait "$lock_pid" 2>/dev/null || true
    if (( json )); then
      print -r -- "{\"error\":\"unsafe_managed_path\",\"mutation_performed\":false,\"ok\":false,\"path\":\"${lock_path}\",\"session_key\":\"${session_key}\"}"
    else
      print -r -- "error=unsafe_managed_path"
    fi
    popd >/dev/null || true
    return 125
  fi
  lock_state="$(_planveyor_py_any - "$lock_ready_path" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("state", "error"))
PY
)"
  lock_holder_pid="$(_planveyor_py_any - "$lock_ready_path" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("holder_pid", ""))
PY
)"
  if [[ "$lock_state" == "error" ]]; then
    wait "$lock_pid" 2>/dev/null || true
    if (( json )); then
      print -r -- "{\"error\":\"unsafe_managed_path\",\"mutation_performed\":false,\"ok\":false,\"path\":\"${lock_path}\",\"session_key\":\"${session_key}\"}"
    else
      print -r -- "error=unsafe_managed_path"
    fi
    popd >/dev/null || true
    return 125
  fi
  if [[ "$lock_state" == "acquired" && ( "$lock_holder_pid" != <-> || "$lock_holder_pid" -le 0 ) ]]; then
    kill -TERM "$lock_pid" 2>/dev/null || true
    wait "$lock_pid" 2>/dev/null || true
    if (( json )); then
      print -r -- "{\"error\":\"unsafe_managed_path\",\"mutation_performed\":false,\"ok\":false,\"path\":\"${lock_ready_path}\",\"session_key\":\"${session_key}\"}"
    else
      print -r -- "error=unsafe_managed_path"
    fi
    popd >/dev/null || true
    return 125
  fi

  if [[ "$lock_state" == "contended" ]]; then
    child_rc=125
    state="precondition_failed"
    non_green_reason="role_run_lock_contended"
    precondition_failed="true"
    : > "$stdout_path"
    printf 'role run lock contended for %s\n' "$session_key" > "$stderr_path"
    wait "$lock_pid" 2>/dev/null || true
  else
    sid_before="$(planveyor_session "$session_key" 2>/dev/null || true)"
    [[ "$sid_before" == "<SESSION_ID>" ]] && sid_before=""
    sid="$sid_before"
    if [[ -z "${sid_before//[[:space:]]/}" ]]; then
      child_rc=125
      state="precondition_failed"
      precondition_failed="true"
      non_green_reason="missing_session_sid"
      printf 'missing session id for %s\n' "$session_key" > "$stderr_path"
      : > "$stdout_path"
    else
      local preflight_rc=0 proof_kv="" proof_state="" proof_reason=""
      local proof_runner="" proof_init_attempt_id="" proof_selection_digest="" proof_carrier_state="" proof_row=""
      if (( preflight_proof_seen )); then
        : > "$preflight_stderr_path"
      else
        preflight_proof_json="$(planveyor_role_runner_preflight "$role" --json 2> "$preflight_stderr_path")"
        preflight_rc=$?
      fi
      print -r -- "$preflight_proof_json" > "$preflight_path" || {
        child_rc=125
        state="precondition_failed"
        precondition_failed="true"
        non_green_reason="precondition_failed"
        : > "$stdout_path"
        printf 'could not capture role runner preflight proof\n' > "$stderr_path"
      }
      if [[ "$precondition_failed" != "true" ]] && (( ! preflight_proof_seen && preflight_rc != 0 )); then
        child_rc=125
        state="precondition_failed"
        precondition_failed="true"
        non_green_reason="precondition_failed"
        : > "$stdout_path"
        cat "$preflight_stderr_path" > "$stderr_path" 2>/dev/null || printf 'role runner preflight failed\n' > "$stderr_path"
      fi
      if [[ "$precondition_failed" != "true" ]]; then
        proof_kv="$(_planveyor_role_run_preflight_proof_kv "$preflight_proof_json" "$role" "$runner_role" "$session_key" "$sid_before" 2>/dev/null || true)"
        for proof_row in ${(f)proof_kv}; do
          case "$proof_row" in
            state=*) proof_state="${proof_row#state=}" ;;
            reason=*) proof_reason="${proof_row#reason=}" ;;
            runner=*) proof_runner="${proof_row#runner=}" ;;
            init_attempt_id=*) proof_init_attempt_id="${proof_row#init_attempt_id=}" ;;
            selection_digest=*) proof_selection_digest="${proof_row#selection_digest=}" ;;
            carrier_state=*) proof_carrier_state="${proof_row#carrier_state=}" ;;
          esac
        done
        if [[ "$proof_state" != "valid" || "$proof_reason" != "ok" || -z "${proof_runner//[[:space:]]/}" || -z "${proof_init_attempt_id//[[:space:]]/}" || -z "${proof_selection_digest//[[:space:]]/}" || -z "${proof_carrier_state//[[:space:]]/}" ]]; then
          child_rc=125
          state="precondition_failed"
          precondition_failed="true"
          non_green_reason="${proof_reason:-precondition_failed}"
          : > "$stdout_path"
          if (( preflight_rc != 0 )) && [[ ! -s "$preflight_stderr_path" ]]; then
            printf 'role runner preflight failed\n' > "$stderr_path"
          else
            cat "$preflight_stderr_path" > "$stderr_path" 2>/dev/null || printf 'role runner preflight proof invalid\n' > "$stderr_path"
          fi
        else
          runner_id="$proof_runner"
          model_identity_args=("${(@f)$(_planveyor_model_identity_payload_args "$runner_id" "$role")}")
          model="$(_planveyor_role_run_model_for_runner "$runner_id" "$role")"
          functions "$wrapper" > "$wrapper_source" || {
            child_rc=125
            state="precondition_failed"
            precondition_failed="true"
            non_green_reason="missing_wrapper_function"
            : > "$stdout_path"
            printf 'missing wrapper function: %s\n' "$wrapper" > "$stderr_path"
          }
        fi
      fi
      if [[ "$precondition_failed" != "true" ]] && _planveyor_role_outcome_contract_active "$plan_path" "$role"; then
        role_outcome_attempted="true"
        if [[ -n "$recovery_of_run_id" || -n "$rejection_receipt_sha256" ]]; then
          if [[ -z "$recovery_of_run_id" || -z "$rejection_receipt_sha256" ]]; then
            child_rc=125
            state="precondition_failed"
            precondition_failed="true"
            non_green_reason="role_outcome_recovery_preflight_failed"
            role_outcome_state="blocked"
            role_outcome_reason_code="recovery_not_available"
            role_outcome_readback_persisted="false"
            role_outcome_recovery_state="unavailable"
            role_outcome_safe_action="return_owner_architect"
            role_outcome_recovery_preflight_blocked="true"
            : > "$stdout_path"
            printf 'role outcome recovery tuple is incomplete\n' > "$stderr_path"
          else
            local reservation_json="" reservation_rc=0 reservation_kv=""
            reservation_json="$(_planveyor_role_outcome_helper_json reserve-rerun "$root" "$plan_path" "$role" "$run_id" "$output_dir" "" "" "$recovery_of_run_id" "$rejection_receipt_sha256")"
            reservation_rc=$?
            reservation_kv="$(_planveyor_role_outcome_result_kv "$reservation_json" reservation "$role" "$run_id" "$plan_path" 2>/dev/null || true)"
            local reservation_state="" reservation_reason="" reservation_row=""
            for reservation_row in ${(f)reservation_kv}; do
              case "$reservation_row" in
                state=*) reservation_state="${reservation_row#state=}" ;;
                reason_code=*) reservation_reason="${reservation_row#reason_code=}" ;;
              esac
            done
            if [[ "$reservation_state" != "started" || "$reservation_rc" != "0" ]]; then
              child_rc=125
              state="precondition_failed"
              precondition_failed="true"
              non_green_reason="role_outcome_recovery_preflight_failed"
              role_outcome_state="blocked"
              if [[ -z "$reservation_state" ]]; then
                role_outcome_reason_code="helper_output_invalid"
              else
                role_outcome_reason_code="${reservation_reason:-recovery_not_available}"
              fi
              role_outcome_readback_persisted="false"
              role_outcome_recovery_state="unavailable"
              role_outcome_safe_action="return_owner_architect"
              role_outcome_recovery_preflight_blocked="true"
              : > "$stdout_path"
              printf 'role outcome recovery reservation blocked: %s\n' "$role_outcome_reason_code" > "$stderr_path"
            else
              role_outcome_recovery_state="rerun_available"
              role_outcome_safe_action="continue_same_role_dispatch"
            fi
          fi
        fi
      fi
      if [[ "$precondition_failed" != "true" ]] && _planveyor_role_outcome_contract_active "$plan_path" "$role"; then
        role_outcome_attempted="true"
        local outcome_preflight_json="" outcome_preflight_rc=0 outcome_preflight_kv=""
        outcome_preflight_json="$(_planveyor_role_outcome_helper_json preflight "$root" "$plan_path" "$role" "$run_id" "$output_dir")"
        outcome_preflight_rc=$?
        outcome_preflight_kv="$(_planveyor_role_outcome_result_kv "$outcome_preflight_json" preflight "$role" "$run_id" "$plan_path" 2>/dev/null || true)"
        local outcome_preflight_state="" outcome_preflight_reason="" outcome_row=""
        for outcome_row in ${(f)outcome_preflight_kv}; do
          case "$outcome_row" in
            state=*) outcome_preflight_state="${outcome_row#state=}" ;;
            reason_code=*) outcome_preflight_reason="${outcome_row#reason_code=}" ;;
          esac
        done
        if [[ -z "$outcome_preflight_state" || -z "$outcome_preflight_reason" ]]; then
          child_rc=125
          state="precondition_failed"
          precondition_failed="true"
          non_green_reason="role_outcome_preflight_failed"
          role_outcome_transport_failed="true"
          role_outcome_state="blocked"
          if (( outcome_preflight_rc == 127 )); then
            role_outcome_reason_code="helper_invocation_failed"
          else
            role_outcome_reason_code="helper_output_invalid"
          fi
          role_outcome_readback_persisted="false"
          : > "$stdout_path"
          printf 'role outcome preflight transport failed: %s\n' "$role_outcome_reason_code" > "$stderr_path"
        elif ! _planveyor_role_run_atomic_publish outcome_preflight "$role_outcome_preflight_path" "$outcome_preflight_json" >/dev/null; then
          child_rc=125
          state="precondition_failed"
          precondition_failed="true"
          non_green_reason="role_outcome_preflight_failed"
          role_outcome_transport_failed="true"
          role_outcome_state="blocked"
          role_outcome_reason_code="helper_output_invalid"
          role_outcome_readback_persisted="false"
          : > "$stdout_path"
          printf 'role outcome preflight capture failed\n' > "$stderr_path"
        elif [[ "$outcome_preflight_state" == "blocked" && "$outcome_preflight_rc" == "125" ]]; then
          child_rc=125
          state="precondition_failed"
          precondition_failed="true"
          non_green_reason="role_outcome_preflight_failed"
          role_outcome_preflight_blocked="true"
          : > "$stdout_path"
          printf 'role outcome preflight blocked: %s\n' "$outcome_preflight_reason" > "$stderr_path"
        elif [[ "$outcome_preflight_state" != "ready" || "$outcome_preflight_rc" != "0" ]]; then
          child_rc=125
          state="precondition_failed"
          precondition_failed="true"
          non_green_reason="role_outcome_preflight_failed"
          role_outcome_transport_failed="true"
          role_outcome_state="blocked"
          role_outcome_reason_code="helper_output_invalid"
          role_outcome_readback_persisted="false"
          : > "$stdout_path"
          printf 'role outcome preflight result invalid\n' > "$stderr_path"
        fi
      fi
      if [[ "$precondition_failed" != "true" ]]; then
        local current_sid="" current_selection_json="" current_selection_rc=0 current_selection_kv="" current_selection_state=""
        current_sid="$(planveyor_session "$session_key" 2>/dev/null || true)"
        [[ "$current_sid" == "<SESSION_ID>" ]] && current_sid=""
        if [[ "$current_sid" != "$sid_before" ]]; then
          child_rc=125
          state="precondition_failed"
          precondition_failed="true"
          non_green_reason="runner_changed_since_preflight"
          : > "$stdout_path"
          printf 'session identity changed since role runner preflight\n' > "$stderr_path"
        else
          current_selection_json="$(planveyor_runner_resolve_strict "$runner_role" "$proof_init_attempt_id" 2>> "$preflight_stderr_path")"
          current_selection_rc=$?
          if (( current_selection_rc != 0 )); then
            child_rc=125
            state="precondition_failed"
            precondition_failed="true"
            non_green_reason="runner_not_readable"
            : > "$stdout_path"
            cat "$preflight_stderr_path" > "$stderr_path" 2>/dev/null || printf 'current runner selection unreadable\n' > "$stderr_path"
          else
            current_selection_kv="$(_planveyor_role_run_current_selection_match_kv "$current_selection_json" "$runner_role" "$proof_runner" "$proof_init_attempt_id" "$proof_selection_digest" 2>/dev/null || true)"
            for proof_row in ${(f)current_selection_kv}; do
              case "$proof_row" in
                state=*) current_selection_state="${proof_row#state=}" ;;
              esac
            done
            if [[ "$current_selection_state" != "match" ]]; then
              child_rc=125
              state="precondition_failed"
              precondition_failed="true"
              non_green_reason="runner_changed_since_preflight"
              : > "$stdout_path"
              printf 'runner selection changed since role runner preflight\n' > "$stderr_path"
            fi
          fi
        fi
      fi
      if [[ "$precondition_failed" != "true" ]]; then
        local supervise_json=""
        supervise_json="$(_planveyor_role_run_supervise "$root" "$wrapper" "$wrapper_source" "$stdout_path" "$stderr_path" "$timeout_seconds" \
          --dispatch-role "$runner_role" \
          --dispatch-runner "$proof_runner" \
          -- \
          "PLANVEYOR_ROLE_RUN_ID=${run_id}" \
          "PLANVEYOR_ROLE_RUN_OUTPUT_DIR=${output_dir}" \
          "PLANVEYOR_ROLE_RUN_RECEIPT_PATH=${receipt_path}" \
          "PLANVEYOR_ROLE_RUN_LATEST_RECEIPT_PATH=${latest_path}" \
          "PLANVEYOR_ROLE_RUN_SESSION_KEY=${session_key}" \
          "PLANVEYOR_ROLE_RUN_TARGET_PLAN=${plan_path}")"
        child_rc="$(_planveyor_py_any - "$supervise_json" <<'PY'
import json, sys
print(json.loads(sys.argv[1]).get("exit_code", 125))
PY
)"
        timed_out="$(_planveyor_py_any - "$supervise_json" <<'PY'
import json, sys
print("true" if json.loads(sys.argv[1]).get("timed_out") else "false")
PY
)"
        process_started="$(_planveyor_py_any - "$supervise_json" <<'PY'
import json, sys
print("true" if json.loads(sys.argv[1]).get("process_started") else "false")
PY
)"
        state="$(_planveyor_role_run_state_for_rc "$child_rc" "$timed_out")"
        [[ "$state" == "interrupted" ]] && interrupted="true"
        non_green_reason="$(_planveyor_role_run_non_green_reason "$state" "$child_rc")"
      fi
    fi
  fi

  finished_at="$(_planveyor_now_utc_iso)"
  receipt_written_at="$finished_at"
  if [[ "$lock_state" == "acquired" ]]; then
    sid_after="$(planveyor_session "$session_key" 2>/dev/null || true)"
    [[ "$sid_after" == "<SESSION_ID>" ]] && sid_after=""
    [[ -n "${sid_after//[[:space:]]/}" ]] || sid_after="$sid_before"
    sid="$sid_after"
  fi
  if [[ -z "${sid_before//[[:space:]]/}" ]]; then
    session_pointer_relation="missing"
  elif [[ "$sid_before" == "$sid_after" ]]; then
    session_pointer_relation="same"
  else
    session_pointer_relation="replaced"
  fi
  [[ "$process_started" == "true" ]] && process_start_outcome="started"
  if [[ "$process_start_outcome" == "started" && "$state" == "failed" && "$child_rc" != "0" && "$timed_out" != "true" && "$interrupted" != "true" ]]; then
    local provider_json=""
    provider_json="$(_planveyor_role_run_provider_error_json "$stdout_path" "$stderr_path")"
    provider_http_status="$(_planveyor_py_any - "$provider_json" <<'PY'
import json, sys
print(json.loads(sys.argv[1])["provider_http_status"])
PY
)"
    provider_error_code="$(_planveyor_py_any - "$provider_json" <<'PY'
import json, sys
print(json.loads(sys.argv[1])["provider_error_code"])
PY
)"
    provider_error_class="$(_planveyor_py_any - "$provider_json" <<'PY'
import json, sys
print(json.loads(sys.argv[1])["provider_error_class"])
PY
)"
    provider_retryability="$(_planveyor_py_any - "$provider_json" <<'PY'
import json, sys
print(json.loads(sys.argv[1])["provider_retryability"])
PY
)"
  fi
  status_post="$(planveyor_status_line "$plan_path" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] || status_post="$status_pre"
  [[ "$child_rc" == "0" && "$state" == "success" ]] && success="true"
  local duration_seconds=$(( SECONDS - started_seconds ))
  (( duration_seconds < 0 )) && duration_seconds=0

  local payload_json=""
  local receipt_configured_model_id=""
  receipt_configured_model_id="$(_planveyor_model_identity_value configured_model_id "${model_identity_args[@]}" 2>/dev/null || true)"
  if [[ "$runner_id" == "claude" && -z "${receipt_configured_model_id//[[:space:]]/}" ]]; then
    receipt_configured_model_id="N/A (why=consumer default)"
  fi
  local -a authority_receipt_arg
  authority_receipt_arg=()
  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    authority_receipt_arg=("authority_context=${PLANVEYOR_CTX_JSON}")
  fi
  payload_json="$(_planveyor_role_run_payload_json \
    "schema_version=role_execution_receipt.v1" \
    "run_id=${run_id}" \
    "role=${role}" \
    "session_key=${session_key}" \
    "wrapper=${wrapper}" \
    "runner_id=${runner_id}" \
    "runner_alias=$(_planveyor_model_identity_value runner_alias "${model_identity_args[@]}" 2>/dev/null || true)" \
    "profile=$(_planveyor_model_identity_value profile "${model_identity_args[@]}" 2>/dev/null || true)" \
    "model=${model}" \
    "configured_model_id=${receipt_configured_model_id}" \
    "observable_model_id=$(_planveyor_model_identity_value observable_model_id "${model_identity_args[@]}" 2>/dev/null || true)" \
    "model_id_state=$(_planveyor_model_identity_value model_id_state "${model_identity_args[@]}" 2>/dev/null || true)" \
    "sid=${sid:-N/A (why=.planveyor.session.${session_key} was not read)}" \
    "sid_before=${sid_before:-N/A (why=.planveyor.session.${session_key} was not read before wrapper)}" \
    "sid_after=${sid_after:-N/A (why=.planveyor.session.${session_key} was not read after wrapper)}" \
    "session_action_requested=resume" \
    "session_pointer_relation=${session_pointer_relation}" \
    "process_start_outcome=${process_start_outcome}" \
    "session_reset_performed=false" \
    "cli_process_mode=one_shot" \
    "process_persistent=false" \
    "provider_error_class=${provider_error_class}" \
    "provider_http_status=${provider_http_status}" \
    "provider_error_code=${provider_error_code}" \
    "provider_retryability=${provider_retryability}" \
    "child_session=${child_session}" \
    "target_plan=${plan_path}" \
    "pre_status=${status_pre}" \
    "post_status=${status_post}" \
    "exit_code=${child_rc}" \
    "started_at=${started_at}" \
    "finished_at=${finished_at}" \
    "receipt_written_at=${receipt_written_at}" \
    "result_artifact=${result_artifact}" \
    "state=${state}" \
    "success=${success}" \
    "timed_out=${timed_out}" \
    "terminated_by_timeout=${timed_out}" \
    "interrupted=${interrupted}" \
    "non_green_reason=${non_green_reason}" \
    "stdout_path=${stdout_path}" \
    "stderr_path=${stderr_path}" \
    "receipt_path=${receipt_path}" \
    "latest_receipt_path=${latest_path}" \
    "timeout_seconds=${timeout_seconds}" \
    "duration_seconds=${duration_seconds}" \
    "elapsed_seconds=${duration_seconds}" \
    "${authority_receipt_arg[@]}")" || {
      if [[ "$role_outcome_attempted" == "true" ]]; then
        role_outcome_state="blocked"
        role_outcome_reason_code="execution_receipt_invalid"
        role_outcome_readback_persisted="false"
      fi
      local close_json=""
      _planveyor_role_run_close_transaction "$transaction_done_path" "$lock_release_path" "$lock_pid" "$lock_holder_pid" "$lock_state" || true
      close_json="${_PLANVEYOR_ROLE_RUN_CLOSE_JSON:-}"
      if (( json )); then
        _planveyor_py_any - "$run_id" "$session_key" "$close_json" \
          "$role_outcome_attempted" "$role_outcome_state" "$role_outcome_reason_code" \
          "${role_outcome_readback_path#$root/}" "$role_outcome_readback_persisted" <<'PY'
import json, sys
try:
    close = json.loads(sys.argv[3])
except (TypeError, ValueError):
    close = {"ok": False, "reason": "invalid_close_result"}
payload = {"ok": False, "error": "receipt_payload_failed", "run_id": sys.argv[1], "session_key": sys.argv[2], "close": close}
if sys.argv[4] == "true":
    payload.update(role_outcome_state=sys.argv[5], role_outcome_reason_code=sys.argv[6], role_outcome_readback_path=sys.argv[7], role_outcome_readback_persisted=sys.argv[8] == "true")
print(json.dumps(payload, sort_keys=True))
PY
      fi
      popd >/dev/null || true
      return 126
    }

  local publish_json=""
  publish_json="$(_planveyor_role_run_atomic_publish primary "$receipt_path" "$payload_json")"
  if (( $? != 0 )); then
    if [[ "$role_outcome_attempted" == "true" ]]; then
      role_outcome_state="blocked"
      role_outcome_reason_code="execution_receipt_invalid"
      role_outcome_readback_persisted="false"
    fi
    local close_json=""
    _planveyor_role_run_close_transaction "$transaction_done_path" "$lock_release_path" "$lock_pid" "$lock_holder_pid" "$lock_state" || true
    close_json="${_PLANVEYOR_ROLE_RUN_CLOSE_JSON:-}"
    _planveyor_py_any - "$publish_json" "$run_id" "$session_key" "$receipt_path" "$close_json" \
      "$role_outcome_attempted" "$role_outcome_state" "$role_outcome_reason_code" \
      "${role_outcome_readback_path#$root/}" "$role_outcome_readback_persisted" <<'PY'
import json, sys
detail = json.loads(sys.argv[1])
try:
    close = json.loads(sys.argv[5])
except (TypeError, ValueError):
    close = {"ok": False, "reason": "invalid_close_result"}
payload = {"ok": False, "error": "primary_publication_failed", "run_id": sys.argv[2], "session_key": sys.argv[3], "receipt_path": sys.argv[4], "mutation_performed": bool(detail.get("mutation_performed")), "close": close}
if sys.argv[6] == "true":
    payload.update(role_outcome_state=sys.argv[7], role_outcome_reason_code=sys.argv[8], role_outcome_readback_path=sys.argv[9], role_outcome_readback_persisted=sys.argv[10] == "true")
print(json.dumps(payload, sort_keys=True))
PY
    popd >/dev/null || true
    return 126
  fi

  local primary_readback=""
  primary_readback="$(_planveyor_role_run_check_json "$receipt_path" "$run_id" "$session_key" "$plan_path" "$status_pre")"
  if (( $? != 0 )); then
    readback_state="blocked"
    readback_reason="receipt_readback_failed"
    final_rc=126
  elif [[ "$lock_state" == "contended" ]]; then
    final_rc=125
  else
    publish_json="$(_planveyor_role_run_atomic_publish latest "$latest_path" "$payload_json")"
    if (( $? != 0 )); then
      readback_state="blocked"
      readback_reason="latest_publication_failed"
      final_rc=126
    else
      local latest_readback=""
      latest_readback="$(_planveyor_role_run_check_latest_json "$latest_path" "$run_id" "$session_key" "$plan_path")"
      if (( $? != 0 )); then
        readback_state="blocked"
        readback_reason="receipt_readback_failed"
        final_rc=126
      else
        local role_outcome_final_rc=$child_rc
        if [[ "$role_outcome_attempted" == "true" ]]; then
          if [[ "$role_outcome_recovery_preflight_blocked" == "true" ]]; then
            role_outcome_final_rc=125
          elif [[ "$role_outcome_transport_failed" == "true" ]]; then
            role_outcome_final_rc=126
          else
            local outcome_finalize_json="" outcome_finalize_rc=0 outcome_finalize_kv=""
            outcome_finalize_json="$(_planveyor_role_outcome_helper_json finalize "$root" "$plan_path" "$role" "$run_id" "$output_dir" "$receipt_path" "$role_outcome_preflight_path")"
            outcome_finalize_rc=$?
            outcome_finalize_kv="$(_planveyor_role_outcome_result_kv "$outcome_finalize_json" readback "$role" "$run_id" "$plan_path" 2>/dev/null || true)"
            local outcome_finalize_state="" outcome_finalize_reason="" outcome_finalize_persisted="" outcome_row=""
            for outcome_row in ${(f)outcome_finalize_kv}; do
              case "$outcome_row" in
                state=*) outcome_finalize_state="${outcome_row#state=}" ;;
                reason_code=*) outcome_finalize_reason="${outcome_row#reason_code=}" ;;
                persisted=*) outcome_finalize_persisted="${outcome_row#persisted=}" ;;
              esac
            done
            if [[ -z "$outcome_finalize_state" || -z "$outcome_finalize_reason" || -z "$outcome_finalize_persisted" ]]; then
              role_outcome_state="blocked"
              if (( outcome_finalize_rc == 127 )); then
                role_outcome_reason_code="helper_invocation_failed"
              else
                role_outcome_reason_code="helper_output_invalid"
              fi
              role_outcome_readback_persisted="false"
              role_outcome_final_rc=126
            elif [[ "$outcome_finalize_persisted" == "true" ]]; then
              local outcome_readback_json="" outcome_readback_rc=0 outcome_readback_kv=""
              outcome_readback_json="$(_planveyor_role_outcome_helper_json readback "$root" "$plan_path" "$role" "$run_id" "$output_dir" "$receipt_path")"
              outcome_readback_rc=$?
              outcome_readback_kv="$(_planveyor_role_outcome_result_kv "$outcome_readback_json" readback "$role" "$run_id" "$plan_path" 2>/dev/null || true)"
              role_outcome_state=""
              role_outcome_reason_code=""
              role_outcome_readback_persisted=""
              for outcome_row in ${(f)outcome_readback_kv}; do
                case "$outcome_row" in
                  state=*) role_outcome_state="${outcome_row#state=}" ;;
                  reason_code=*) role_outcome_reason_code="${outcome_row#reason_code=}" ;;
                  persisted=*) role_outcome_readback_persisted="${outcome_row#persisted=}" ;;
                esac
              done
              if [[ -z "$role_outcome_state" || -z "$role_outcome_reason_code" || "$role_outcome_readback_persisted" != "true" ]]; then
                role_outcome_state="blocked"
                if (( outcome_readback_rc == 127 )); then
                  role_outcome_reason_code="helper_invocation_failed"
                else
                  role_outcome_reason_code="helper_output_invalid"
                fi
                role_outcome_readback_persisted="false"
                role_outcome_final_rc=126
              elif [[ "$role_outcome_state" == "finalized" && "$outcome_readback_rc" == "0" ]]; then
                role_outcome_final_rc=$child_rc
              elif [[ "$role_outcome_preflight_blocked" == "true" && "$role_outcome_state" == "blocked" ]]; then
                role_outcome_final_rc=125
              else
                role_outcome_final_rc=126
              fi
            else
              role_outcome_state="$outcome_finalize_state"
              role_outcome_reason_code="$outcome_finalize_reason"
              role_outcome_readback_persisted="false"
              role_outcome_final_rc=126
            fi
          fi
        fi
        if [[ -f "$role_outcome_diagnostic_path" ]]; then
          local outcome_diagnostic_kv="" outcome_diagnostic_row=""
          outcome_diagnostic_kv="$(_planveyor_role_outcome_diagnostic_kv "$role_outcome_diagnostic_path" "$role" "$run_id" "$plan_path" "$root" 2>/dev/null || true)"
          for outcome_diagnostic_row in ${(f)outcome_diagnostic_kv}; do
            case "$outcome_diagnostic_row" in
              state=*) role_outcome_diagnostic_state="${outcome_diagnostic_row#state=}" ;;
              reason_code=*) role_outcome_diagnostic_reason_code="${outcome_diagnostic_row#reason_code=}" ;;
              recovery_state=*) role_outcome_recovery_state="${outcome_diagnostic_row#recovery_state=}" ;;
              safe_action=*) role_outcome_safe_action="${outcome_diagnostic_row#safe_action=}" ;;
            esac
          done
          if [[ -z "$role_outcome_diagnostic_state" || -z "$role_outcome_diagnostic_reason_code" ]]; then
            role_outcome_state="blocked"
            role_outcome_reason_code="helper_output_invalid"
            role_outcome_readback_persisted="false"
            role_outcome_final_rc=126
          fi
        fi
        local prune_json="" prune_rc=0 prune_kv="" prune_row=""
        prune_json="$(_planveyor_role_run_prune "$receipt_root" "$output_root" "$session_key" "$run_id" "$latest_path")"
        prune_rc=$?
        prune_kv="$(_planveyor_role_run_prune_result_kv "$prune_json" "$prune_rc" 2>/dev/null || true)"
        retention_prune_state=""
        retention_prune_reason=""
        retention_prune_paths_json=""
        retention_prune_mutation_performed=""
        for prune_row in ${(f)prune_kv}; do
          case "$prune_row" in
            state=*) retention_prune_state="${prune_row#state=}" ;;
            reason=*) retention_prune_reason="${prune_row#reason=}" ;;
            paths_json=*) retention_prune_paths_json="${prune_row#paths_json=}" ;;
            mutation_performed=*) retention_prune_mutation_performed="${prune_row#mutation_performed=}" ;;
          esac
        done
        if [[ -z "$retention_prune_state" || -z "$retention_prune_reason" || -z "$retention_prune_paths_json" || -z "$retention_prune_mutation_performed" ]]; then
          readback_state="blocked"
          readback_reason="prune_output_invalid"
          retention_prune_state="blocked"
          retention_prune_reason="prune_output_invalid"
          retention_prune_paths_json="[]"
          retention_prune_mutation_performed="false"
          final_rc=126
        elif (( prune_rc != 0 )); then
          readback_state="blocked"
          readback_reason="$retention_prune_reason"
          final_rc=126
        else
          final_rc=$role_outcome_final_rc
        fi
      fi
    fi
  fi

  local close_json="" close_reason=""
  _planveyor_role_run_close_transaction "$transaction_done_path" "$lock_release_path" "$lock_pid" "$lock_holder_pid" "$lock_state"
  local close_rc=$?
  close_json="${_PLANVEYOR_ROLE_RUN_CLOSE_JSON:-}"
  if (( close_rc != 0 )); then
    close_reason="$(_planveyor_py_any - "$close_json" <<'PY'
import json, sys
try:
    print(json.loads(sys.argv[1]).get("reason", "control_marker_publication_failed"))
except (TypeError, ValueError):
    print("control_marker_publication_failed")
PY
)"
    readback_state="blocked"
    readback_reason="$close_reason"
    final_rc=126
  fi

  if [[ "$role_outcome_attempted" == "true" && -z "$role_outcome_state" ]]; then
    role_outcome_state="blocked"
    role_outcome_reason_code="execution_receipt_invalid"
    role_outcome_readback_persisted="false"
  fi

  if [[ "$retention_prune_state" == "not_run" ]]; then
    if [[ "$lock_state" == "contended" ]]; then
      retention_prune_reason="lock_contended"
    elif [[ "$readback_reason" != "ok" ]]; then
      retention_prune_reason="$readback_reason"
    else
      retention_prune_reason="upstream_not_reached"
    fi
  fi

  if (( json )); then
    _planveyor_py_any - "$receipt_path" "$readback_state" "$readback_reason" \
      "$role_outcome_attempted" "$role_outcome_state" "$role_outcome_reason_code" \
      "${role_outcome_readback_path#$root/}" "$role_outcome_readback_persisted" \
      "$role_outcome_diagnostic_state" "$role_outcome_diagnostic_reason_code" \
      "${role_outcome_diagnostic_path#$root/}" "$role_outcome_recovery_state" \
      "$role_outcome_safe_action" "$retention_prune_state" "$retention_prune_reason" \
      "$retention_prune_paths_json" "$retention_prune_mutation_performed" <<'PY'
from __future__ import annotations
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
payload["readback_state"] = sys.argv[2]
payload["readback_reason"] = sys.argv[3]
if sys.argv[4] == "true":
    payload["role_outcome_state"] = sys.argv[5]
    payload["role_outcome_reason_code"] = sys.argv[6]
    payload["role_outcome_readback_path"] = sys.argv[7]
    payload["role_outcome_readback_persisted"] = sys.argv[8] == "true"
if sys.argv[9]:
    payload["role_outcome_diagnostic_state"] = sys.argv[9]
    payload["role_outcome_diagnostic_reason_code"] = sys.argv[10]
    payload["role_outcome_diagnostic_path"] = sys.argv[11]
if sys.argv[12]:
    payload["role_outcome_recovery_state"] = sys.argv[12]
    payload["role_outcome_safe_action"] = sys.argv[13]
payload["retention_prune_state"] = sys.argv[14]
payload["retention_prune_reason"] = sys.argv[15]
payload["retention_prune_paths"] = json.loads(sys.argv[16])
payload["retention_prune_mutation_performed"] = sys.argv[17] == "true"
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
  else
    print -r -- "run_id=${run_id}"
    print -r -- "role=${role}"
    print -r -- "session_key=${session_key}"
    print -r -- "state=${state}"
    print -r -- "exit_code=${child_rc}"
    print -r -- "session_pointer_relation=${session_pointer_relation}"
    print -r -- "process_start_outcome=${process_start_outcome}"
    print -r -- "provider_error_class=${provider_error_class}"
    print -r -- "provider_retryability=${provider_retryability}"
    print -r -- "receipt_path=${receipt_path}"
    print -r -- "latest_receipt_path=${latest_path}"
    print -r -- "readback_state=${readback_state}"
    print -r -- "retention_prune_state=${retention_prune_state}"
    print -r -- "retention_prune_reason=${retention_prune_reason}"
    print -r -- "retention_prune_paths=${retention_prune_paths_json}"
    print -r -- "retention_prune_mutation_performed=${retention_prune_mutation_performed}"
    if [[ "$role_outcome_attempted" == "true" ]]; then
      print -r -- "role_outcome_state=${role_outcome_state}"
      print -r -- "role_outcome_reason_code=${role_outcome_reason_code}"
      print -r -- "role_outcome_readback_path=${role_outcome_readback_path#$root/}"
      print -r -- "role_outcome_readback_persisted=${role_outcome_readback_persisted}"
      if [[ -n "$role_outcome_diagnostic_state" ]]; then
        print -r -- "role_outcome_diagnostic_state=${role_outcome_diagnostic_state}"
        print -r -- "role_outcome_diagnostic_reason_code=${role_outcome_diagnostic_reason_code}"
        print -r -- "role_outcome_diagnostic_path=${role_outcome_diagnostic_path#$root/}"
      fi
      if [[ -n "$role_outcome_recovery_state" ]]; then
        print -r -- "role_outcome_recovery_state=${role_outcome_recovery_state}"
        print -r -- "role_outcome_safe_action=${role_outcome_safe_action}"
      fi
    fi
    print -r -- "semantic_truth=PLAN_PATH/review artifact (receipt is execution lineage only)"
  fi

  popd >/dev/null || return 1
  return $final_rc
}

_planveyor_custom_role_step_dirty_json() {
  local plan_path="${1:-}"
  local helper="$(_planveyor_script custom_pipeline_dirty_state.py)"
  [[ -f "$helper" ]] || return 127
  _planveyor_py_any "$helper" "$plan_path" --format json
}

_planveyor_custom_role_step_emit() {
  local state="${1:-blocked}"
  local reason_code="${2:-internal_error}"
  local role="${3:-}"
  local target_plan="${4:-}"
  local role_run_id="${5:-}"
  local execution_receipt_path="${6:-}"
  local execution_readback_state="${7:-not_attempted}"
  local semantic_gate_artifact="${8:-}"
  local semantic_gate_state="${9:-not_applicable}"
  local role_outcome_projection_json="${10:-}"
  _planveyor_py_any - "$state" "$reason_code" "$role" "$target_plan" "$role_run_id" \
    "$execution_receipt_path" "$execution_readback_state" "$semantic_gate_artifact" \
    "$semantic_gate_state" "$role_outcome_projection_json" <<'PY'
import json
import sys

state, reason, role, plan, run_id, receipt, readback, artifact, semantic_state, raw_projection = sys.argv[1:11]
projection = {}
if raw_projection:
    try:
        candidate = json.loads(raw_projection)
    except (TypeError, ValueError):
        candidate = None
    fields = {
        "role_outcome_state",
        "role_outcome_reason_code",
        "role_outcome_readback_path",
        "role_outcome_readback_persisted",
        "role_outcome_diagnostic_state",
        "role_outcome_diagnostic_reason_code",
        "role_outcome_diagnostic_path",
        "role_outcome_recovery_state",
        "role_outcome_safe_action",
    }
    groups = (
        (
            "role_outcome_state",
            "role_outcome_reason_code",
            "role_outcome_readback_path",
            "role_outcome_readback_persisted",
        ),
        (
            "role_outcome_diagnostic_state",
            "role_outcome_diagnostic_reason_code",
            "role_outcome_diagnostic_path",
        ),
        ("role_outcome_recovery_state", "role_outcome_safe_action"),
    )
    if isinstance(candidate, dict) and set(candidate).issubset(fields):
        valid = True
        for group in groups:
            present = [name in candidate for name in group]
            if any(present) and not all(present):
                valid = False
                break
            if all(present):
                for name in group:
                    value = candidate[name]
                    if name == "role_outcome_readback_persisted":
                        if not isinstance(value, bool):
                            valid = False
                            break
                    elif not isinstance(value, str) or not value.strip():
                        valid = False
                        break
                if not valid:
                    break
        if valid:
            projection = candidate
payload = {
    "schema": "custom_role_step.v1",
    "state": state,
    "reason_code": reason,
    "role": role or None,
    "target_plan": plan or None,
    "role_run_id": run_id or None,
    "execution_receipt_path": receipt or None,
    "execution_readback_state": readback,
    "semantic_gate_artifact": artifact or None,
    "semantic_gate_state": semantic_state,
}
payload.update(projection)
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
}

planveyor_custom_role_step() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_custom_role_step)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local role_arg="" plan_arg="" json=0 timeout_seconds=""
  local usage="Usage: planveyor_custom_role_step <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> --plan <PLAN_PATH> [--timeout SECONDS] --json"
  while (( $# > 0 )); do
    case "${1:-}" in
      --plan)
        shift
        plan_arg="${1:-}"
        ;;
      --timeout)
        shift
        timeout_seconds="${1:-}"
        ;;
      --json) json=1 ;;
      --help|-h)
        echo "$usage" >&2
        return 0
        ;;
      *)
        if [[ -z "${role_arg//[[:space:]]/}" ]]; then
          role_arg="${1:-}"
        else
          echo "$usage" >&2
          return 2
        fi
        ;;
    esac
    shift
  done
  [[ -n "${role_arg//[[:space:]]/}" && -n "${plan_arg//[[:space:]]/}" && "$json" == "1" ]] || {
    echo "$usage" >&2
    return 2
  }
  if [[ -n "$timeout_seconds" && ( "$timeout_seconds" != <-> || "$timeout_seconds" -le 0 ) ]]; then
    echo "Invalid --timeout: ${timeout_seconds}" >&2
    return 2
  fi

  local normalized="" role="" session_key="" row=""
  normalized="$(_planveyor_role_runner_preflight_normalize "$role_arg" 2>/dev/null || true)"
  [[ -n "${normalized//[[:space:]]/}" ]] || {
    _planveyor_custom_role_step_emit blocked internal_error "" "" "" "" not_attempted "" not_applicable
    return 2
  }
  for row in ${(s:;:)normalized}; do
    case "$row" in
      role=*) role="${row#role=}" ;;
      session_key=*) session_key="${row#session_key=}" ;;
      unsupported=*)
        _planveyor_custom_role_step_emit blocked internal_error "" "" "" "" not_attempted "" not_applicable
        return 2
        ;;
    esac
  done

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local plan_path=""
  plan_path="$(_planveyor_explicit_plan_normalize "$root" "$plan_arg" 2>/dev/null || true)"
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    _planveyor_custom_role_step_emit blocked internal_error "$role" "" "" "" not_attempted "" not_applicable
    return 2
  }

  local dirty_json="" dirty_rc=0 dirty_state=""
  dirty_json="$(_planveyor_custom_role_step_dirty_json "$plan_path" 2>/dev/null)"
  dirty_rc=$?
  if (( dirty_rc == 0 )); then
    dirty_state="$(_planveyor_py_any - "$dirty_json" <<'PY'
import json, sys
try:
    payload = json.loads(sys.argv[1])
except (TypeError, ValueError):
    raise SystemExit(1)
if payload.get("schema") != "custom_pipeline_dirty_state.v1":
    raise SystemExit(1)
print(payload.get("verdict", ""))
PY
)" || dirty_state=""
  fi
  if (( dirty_rc != 0 )) || [[ "$dirty_state" != "continue" ]]; then
    _planveyor_custom_role_step_emit blocked dirty_state_blocked "$role" "$plan_path" "" "" not_attempted "" not_applicable
    return 125
  fi

  local preflight_json=""
  preflight_json="$(planveyor_role_runner_preflight "$role_arg" --json 2>/dev/null)" || {
    _planveyor_custom_role_step_emit blocked runner_preflight_blocked "$role" "$plan_path" "" "" not_attempted "" not_applicable
    return 125
  }

  local -a execute_args
  execute_args=("$role_arg" "$plan_path")
  [[ -n "$timeout_seconds" ]] && execute_args+=(--timeout "$timeout_seconds")
  execute_args+=(--json)
  local execution_json="" execution_rc=0
  execution_json="$(_planveyor_role_run_execute_for_plan "${execute_args[@]}" --preflight-proof "$preflight_json")"
  execution_rc=$?

  local execution_kv=""
  execution_kv="$(_planveyor_py_any - "$execution_json" <<'PY'
import json, sys
try:
    payload = json.loads(sys.argv[1])
except (TypeError, ValueError):
    raise SystemExit(1)
if not isinstance(payload, dict):
    raise SystemExit(1)
for key in (
    "run_id", "session_key", "target_plan", "receipt_path", "state",
    "readback_state", "non_green_reason",
):
    value = payload.get(key)
    if isinstance(value, bool):
        value = "true" if value else "false"
    elif value is None:
        value = ""
    print(f"{key}={value}")
fields = {
    "role_outcome_state",
    "role_outcome_reason_code",
    "role_outcome_readback_path",
    "role_outcome_readback_persisted",
    "role_outcome_diagnostic_state",
    "role_outcome_diagnostic_reason_code",
    "role_outcome_diagnostic_path",
    "role_outcome_recovery_state",
    "role_outcome_safe_action",
}
groups = (
    (
        "role_outcome_state",
        "role_outcome_reason_code",
        "role_outcome_readback_path",
        "role_outcome_readback_persisted",
    ),
    (
        "role_outcome_diagnostic_state",
        "role_outcome_diagnostic_reason_code",
        "role_outcome_diagnostic_path",
    ),
    ("role_outcome_recovery_state", "role_outcome_safe_action"),
)
projection = {name: payload[name] for name in fields if name in payload}
unknown_projection_fields = {
    name for name in payload if name.startswith("role_outcome_") and name not in fields
}
valid = not unknown_projection_fields
for group in groups:
    present = [name in projection for name in group]
    if any(present) and not all(present):
        valid = False
        break
    if all(present):
        for name in group:
            value = projection[name]
            if name == "role_outcome_readback_persisted":
                if not isinstance(value, bool):
                    valid = False
                    break
            elif not isinstance(value, str) or not value.strip():
                valid = False
                break
        if not valid:
            break
if valid:
    if "role_outcome_readback_path" in projection:
        print(f"role_outcome_readback_path={projection['role_outcome_readback_path']}")
        print("role_outcome_readback_persisted=" + ("true" if projection["role_outcome_readback_persisted"] else "false"))
    print("role_outcome_projection_valid=true")
    print("role_outcome_projection_json=" + json.dumps(projection, ensure_ascii=False, sort_keys=True))
else:
    print("role_outcome_projection_valid=false")
    print("role_outcome_projection_json={}")
PY
)" || execution_kv=""

  local role_run_id="" returned_session_key="" returned_plan="" receipt_path=""
  local execution_state="" execution_readback_state="" non_green_reason=""
  local outcome_path="" outcome_persisted="" outcome_projection_valid="" outcome_projection_json=""
  for row in ${(f)execution_kv}; do
    case "$row" in
      run_id=*) role_run_id="${row#run_id=}" ;;
      session_key=*) returned_session_key="${row#session_key=}" ;;
      target_plan=*) returned_plan="${row#target_plan=}" ;;
      receipt_path=*) receipt_path="${row#receipt_path=}" ;;
      state=*) execution_state="${row#state=}" ;;
      readback_state=*) execution_readback_state="${row#readback_state=}" ;;
      non_green_reason=*) non_green_reason="${row#non_green_reason=}" ;;
      role_outcome_readback_path=*) outcome_path="${row#role_outcome_readback_path=}" ;;
      role_outcome_readback_persisted=*) outcome_persisted="${row#role_outcome_readback_persisted=}" ;;
      role_outcome_projection_valid=*) outcome_projection_valid="${row#role_outcome_projection_valid=}" ;;
      role_outcome_projection_json=*) outcome_projection_json="${row#role_outcome_projection_json=}" ;;
    esac
  done

  if [[ "$non_green_reason" == "role_run_lock_contended" ]]; then
    _planveyor_custom_role_step_emit blocked role_step_in_progress "$role" "$plan_path" "$role_run_id" "$receipt_path" "${execution_readback_state:-blocked}" "" not_applicable "$outcome_projection_json"
    return 125
  fi
  if (( execution_rc != 0 )) || [[ "$execution_state" != "success" || "$execution_readback_state" != "ok" ]]; then
    _planveyor_custom_role_step_emit blocked role_run_failed "$role" "$plan_path" "$role_run_id" "$receipt_path" "${execution_readback_state:-blocked}" "" not_applicable "$outcome_projection_json"
    return 125
  fi
  if [[ -z "${receipt_path//[[:space:]]/}" || ! -f "$receipt_path" ]]; then
    _planveyor_custom_role_step_emit blocked execution_receipt_missing "$role" "$plan_path" "$role_run_id" "$receipt_path" missing "" not_applicable "$outcome_projection_json"
    return 125
  fi
  if [[ "$returned_session_key" != "$session_key" || "$returned_plan" != "$plan_path" ]] || \
    ! planveyor_role_run_receipt_check "$receipt_path" --run-id "$role_run_id" --session-key "$session_key" --target-plan "$plan_path" --json >/dev/null 2>&1; then
    _planveyor_custom_role_step_emit blocked execution_receipt_invalid "$role" "$plan_path" "$role_run_id" "$receipt_path" blocked "" not_applicable "$outcome_projection_json"
    return 125
  fi
  if [[ "$outcome_projection_valid" != "true" ]]; then
    _planveyor_custom_role_step_emit blocked internal_error "$role" "$plan_path" "$role_run_id" "$receipt_path" ok "" not_applicable
    return 125
  fi

  local semantic_state="not_applicable" semantic_artifact=""
  if [[ "$outcome_persisted" == "true" ]]; then
    if [[ -z "${outcome_path//[[:space:]]/}" ]]; then
      _planveyor_custom_role_step_emit blocked semantic_gate_artifact_missing "$role" "$plan_path" "$role_run_id" "$receipt_path" ok "" not_applicable "$outcome_projection_json"
      return 125
    fi
    local outcome_fs="$outcome_path"
    [[ "$outcome_fs" == /* ]] || outcome_fs="${root}/${outcome_fs}"
    if [[ ! -f "$outcome_fs" ]]; then
      _planveyor_custom_role_step_emit blocked semantic_gate_artifact_missing "$role" "$plan_path" "$role_run_id" "$receipt_path" ok "" not_applicable "$outcome_projection_json"
      return 125
    fi
    semantic_artifact="$outcome_path"
    semantic_state="not_evaluated_by_helper"
  fi
  _planveyor_custom_role_step_emit completed execution_receipt_valid "$role" "$plan_path" "$role_run_id" "$receipt_path" ok "$semantic_artifact" "$semantic_state" "$outcome_projection_json"
  return 0
}

planveyor_arch() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect status_driven)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local sid; sid="$(planveyor_session architect)" || return 1
  _planveyor_session_authority_resume_validate architect "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role architect)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre
  local status_pre_value
  local owner_answers

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  status_pre_value="$(_planveyor_extract_status_value "$status_pre" 2>/dev/null || true)"
  echo "Plan status (pre): ${status_pre}" >&2

  owner_answers="$(_planveyor_consume_owner_answers_for architect "$plan_path")"
  local payload=""
  payload="$({ echo "ROLE=Architect"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; \
    if [[ -n "${owner_answers//[[:space:]]/}" ]]; then echo ""; echo "Owner answers (out-of-band):"; echo "${owner_answers}"; fi; })"
  printf '%s\n' "$payload" | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" resume "${sid}" -
  local rc=$?

  local status_post
  local status_post_value
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  status_post_value="$(_planveyor_extract_status_value "$status_post" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2

  popd >/dev/null || return 1
  return $rc
}

planveyor_arch_initial() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_initial)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect draft_discussion)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local sid; sid="$(planveyor_session architect)" || return 1
  _planveyor_session_authority_resume_validate architect "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role architect)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre
  local status_pre_value
  local owner_answers

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  status_pre_value="$(_planveyor_extract_status_value "$status_pre" 2>/dev/null || true)"
  echo "Plan status (pre): ${status_pre}" >&2

  owner_answers="$(_planveyor_consume_owner_answers_for architect "$plan_path")"
  local payload=""
  payload="$({ echo "ROLE=Architect"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; \
    if [[ -n "${owner_answers//[[:space:]]/}" ]]; then echo ""; echo "Owner answers (out-of-band):"; echo "${owner_answers}"; fi; })"
  printf '%s\n' "$payload" | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" resume "${sid}" -
  local rc=$?

  local status_post
  local status_post_value
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  status_post_value="$(_planveyor_extract_status_value "$status_post" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2

  popd >/dev/null || return 1
  return $rc
}

planveyor_arch_censor() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_censor)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect censor)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local sid; sid="$(planveyor_session architect)" || return 1
  _planveyor_session_authority_resume_validate architect "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role architect)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect censor)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre
  local status_pre_value
  local owner_answers

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  status_pre_value="$(_planveyor_extract_status_value "$status_pre" 2>/dev/null || true)"
  echo "Plan status (pre): ${status_pre}" >&2

  owner_answers="$(_planveyor_peek_owner_answers_for architect "$plan_path")"
  local payload=""
  payload="$({ echo "ROLE=Architect"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; \
    if [[ -n "${owner_answers//[[:space:]]/}" ]]; then echo ""; echo "Owner answers (out-of-band):"; echo "${owner_answers}"; fi; })"
  printf '%s\n' "$payload" | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" resume "${sid}" -
  local rc=$?

  local status_post
  local status_post_value
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  status_post_value="$(_planveyor_extract_status_value "$status_post" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2

  # Safety: Architect is allowed to set Done only during Architect arch review.
  # If censor caused a status jump to Done, flag it; but don't fail when plan was already Done.
  local status_pre_norm="${status_pre_value:l}"
  status_pre_norm="${status_pre_norm//$'\r'/}"
  status_pre_norm="${status_pre_norm//$'\t'/ }"
  while [[ "$status_pre_norm" == *"  "* ]]; do status_pre_norm="${status_pre_norm//  / }"; done
  status_pre_norm="${status_pre_norm#"${status_pre_norm%%[![:space:]]*}"}"
  status_pre_norm="${status_pre_norm%"${status_pre_norm##*[![:space:]]}"}"
  local status_post_norm="${status_post_value:l}"
  status_post_norm="${status_post_norm//$'\r'/}"
  status_post_norm="${status_post_norm//$'\t'/ }"
  while [[ "$status_post_norm" == *"  "* ]]; do status_post_norm="${status_post_norm//  / }"; done
  status_post_norm="${status_post_norm#"${status_post_norm%%[![:space:]]*}"}"
  status_post_norm="${status_post_norm%"${status_post_norm##*[![:space:]]}"}"
  if [[ "$status_pre_norm" != "done" && "$status_post_norm" == "done" ]]; then
    echo "❗ Process violation: Architect censor changed **Status:** to Done (unexpected). Fix plan status and rerun." >&2
    popd >/dev/null || return 1
    return 2
  fi

  if (( rc == 0 )); then
    local censor_handoff_status=""
    censor_handoff_status="$(_planveyor_censor_handoff_status_for_role architect "$status_pre_value" 2>/dev/null || true)"
    if [[ -n "${censor_handoff_status//[[:space:]]/}" ]]; then
      _planveyor_censor_receipt_gate_check Architect "$plan_path" "$censor_handoff_status" || {
        local gate_rc=$?
        popd >/dev/null || return 1
        return $gate_rc
      }
    fi
  fi

  popd >/dev/null || return 1
  return $rc
}

planveyor_coder() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_coder)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body coder status_driven)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local sid; sid="$(planveyor_session coder)" || return 1
  _planveyor_session_authority_resume_validate coder "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role coder)" || return 1
  local runner=""
  runner="$(planveyor_runner coder 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode coder main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre
  local status_pre_value
  local owner_answers

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  status_pre_value="$(_planveyor_extract_status_value "$status_pre" 2>/dev/null || true)"
  echo "Plan status (pre): ${status_pre}" >&2

  owner_answers="$(_planveyor_consume_owner_answers_for coder "$plan_path")"
  local payload=""
  payload="$({ echo "ROLE=Coder"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; \
    if [[ -n "${owner_answers//[[:space:]]/}" ]]; then echo ""; echo "Owner answers (out-of-band):"; echo "${owner_answers}"; fi; })"
  case "$runner" in
    codex)
      printf '%s\n' "$payload" | _planveyor_with_role_env coder "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" resume "${sid}" -
      ;;
    *)
      echo "Unsupported coder runner: ${runner} (use: planveyor_runner_set coder codex)" >&2
      popd >/dev/null || return 1
      return 1
      ;;
  esac
  local rc=$?

  local status_post
  local status_post_value
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  status_post_value="$(_planveyor_extract_status_value "$status_post" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2

  # Gate: prevent accidental handoff if plan_lint fails.
  local status_post_norm="${status_post_value:l}"
  status_post_norm="${status_post_norm//$'\r'/}"
  status_post_norm="${status_post_norm//$'\t'/ }"
  while [[ "$status_post_norm" == *"  "* ]]; do status_post_norm="${status_post_norm//  / }"; done
  status_post_norm="${status_post_norm#"${status_post_norm%%[![:space:]]*}"}"
  status_post_norm="${status_post_norm%"${status_post_norm##*[![:space:]]}"}"
  if [[ "$status_post_norm" == "ready for review" || "$status_post_norm" == "ready for arch review" ]]; then
    local lint_out=""
    lint_out="$(_planveyor_py_any "$(_planveyor_script plan_lint.py)" "$plan_path" 2>&1)"
    local lint_rc=$?
    if (( lint_rc != 0 )); then
      printf '%s\n' "$lint_out" >&2
      echo "❗ Coder handoff blocked: plan_lint failed; reverting **Status:** to In progress." >&2
      _planveyor_plan_set_header_status "$plan_path" "In progress" >/dev/null 2>&1 || true
      popd >/dev/null || return 1
      return 4
    fi
  fi

  if [[ "$status_post" == *"**Status:** Done"* ]]; then
    echo "❗ Process violation: Coder set **Status:** Done (Done = only Architect). Fix plan status and rerun." >&2
    popd >/dev/null || return 1
    return 2
  fi

  popd >/dev/null || return 1
  return $rc
}

planveyor_coder_censor() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_coder_censor)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body coder censor)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local sid; sid="$(planveyor_session coder)" || return 1
  _planveyor_session_authority_resume_validate coder "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role coder)" || return 1
  local runner=""
  runner="$(planveyor_runner coder 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode coder censor)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre
  local status_pre_value
  local owner_answers

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  status_pre_value="$(_planveyor_extract_status_value "$status_pre" 2>/dev/null || true)"
  echo "Plan status (pre): ${status_pre}" >&2

  owner_answers="$(_planveyor_peek_owner_answers_for coder "$plan_path")"
  local payload=""
  payload="$({ echo "ROLE=Coder"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; \
    if [[ -n "${owner_answers//[[:space:]]/}" ]]; then echo ""; echo "Owner answers (out-of-band):"; echo "${owner_answers}"; fi; })"
  case "$runner" in
    codex)
      printf '%s\n' "$payload" | _planveyor_with_role_env coder "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" resume "${sid}" -
      ;;
    *)
      echo "Unsupported coder runner: ${runner} (use: planveyor_runner_set coder codex)" >&2
      popd >/dev/null || return 1
      return 1
      ;;
  esac
  local rc=$?

  local status_post
  local status_post_value
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  status_post_value="$(_planveyor_extract_status_value "$status_post" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2

  # Process safety: Coder must never move plan to Done.
  local status_pre_norm="${status_pre_value:l}"
  status_pre_norm="${status_pre_norm//$'\r'/}"
  status_pre_norm="${status_pre_norm//$'\t'/ }"
  while [[ "$status_pre_norm" == *"  "* ]]; do status_pre_norm="${status_pre_norm//  / }"; done
  status_pre_norm="${status_pre_norm#"${status_pre_norm%%[![:space:]]*}"}"
  status_pre_norm="${status_pre_norm%"${status_pre_norm##*[![:space:]]}"}"
  local status_post_norm="${status_post_value:l}"
  status_post_norm="${status_post_norm//$'\r'/}"
  status_post_norm="${status_post_norm//$'\t'/ }"
  while [[ "$status_post_norm" == *"  "* ]]; do status_post_norm="${status_post_norm//  / }"; done
  status_post_norm="${status_post_norm#"${status_post_norm%%[![:space:]]*}"}"
  status_post_norm="${status_post_norm%"${status_post_norm##*[![:space:]]}"}"
  if [[ "$status_pre_norm" != "done" && "$status_post_norm" == "done" ]]; then
    echo "❗ Process violation: Coder censor changed **Status:** to Done (Done = only Architect). Fix plan status and rerun." >&2
    popd >/dev/null || return 1
    return 2
  fi

  if (( rc == 0 )); then
    local censor_handoff_status=""
    censor_handoff_status="$(_planveyor_censor_handoff_status_for_role coder "$status_pre_value" 2>/dev/null || true)"
    if [[ -n "${censor_handoff_status//[[:space:]]/}" ]]; then
      _planveyor_censor_receipt_gate_check Coder "$plan_path" "$censor_handoff_status" || {
        local gate_rc=$?
        popd >/dev/null || return 1
        return $gate_rc
      }
    fi
  fi

  popd >/dev/null || return 1
  return $rc
}

planveyor_planner() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_planner)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body planner status_driven)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local sid; sid="$(planveyor_session planner)" || return 1
  _planveyor_session_authority_resume_validate planner "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role planner)" || return 1
  local runner=""
  runner="$(planveyor_runner planner 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode planner main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre
  local status_pre_value
  local payload
  local owner_answers

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  status_pre_value="$(_planveyor_extract_status_value "$status_pre" 2>/dev/null || true)"
  echo "Plan status (pre): ${status_pre}" >&2

  owner_answers="$(_planveyor_consume_owner_answers_for planner "$plan_path")"
  payload="$({ echo "ROLE=Planner"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; \
    if [[ -n "${owner_answers//[[:space:]]/}" ]]; then echo ""; echo "Owner answers (out-of-band):"; echo "${owner_answers}"; fi; })"
  case "$runner" in
    codex)
      printf '%s\n' "$payload" | _planveyor_with_role_env planner "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" resume "${sid}" -
      ;;
    claude)
      _planveyor_authority_before_raw_claude_launch || {
        local guard_rc=$?
        popd >/dev/null || return 1
        return "$guard_rc"
      }
      _planveyor_with_role_env planner "$pybin" _planveyor_claude_direct_run -p --resume "${sid}" --permission-mode acceptEdits "${payload}"
      ;;
    *)
      echo "Unsupported planner runner: ${runner} (use: planveyor_runner_set planner codex|claude)" >&2
      popd >/dev/null || return 1
      return 1
      ;;
  esac
  local rc=$?

  local status_post
  local status_post_value
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  status_post_value="$(_planveyor_extract_status_value "$status_post" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2

  # Gate: prevent accidental handoff if plan_lint fails (especially code_draft requirement).
  local status_post_norm="${status_post_value:l}"
  status_post_norm="${status_post_norm//$'\r'/}"
  status_post_norm="${status_post_norm//$'\t'/ }"
  while [[ "$status_post_norm" == *"  "* ]]; do status_post_norm="${status_post_norm//  / }"; done
  status_post_norm="${status_post_norm#"${status_post_norm%%[![:space:]]*}"}"
  status_post_norm="${status_post_norm%"${status_post_norm##*[![:space:]]}"}"
  if [[ "$status_post_norm" == "ready for coder" ]]; then
    local lint_out=""
    lint_out="$(_planveyor_py "$(_planveyor_script plan_lint.py)" "$plan_path" 2>&1)"
    local lint_rc=$?
    if (( lint_rc != 0 )); then
      printf '%s\n' "$lint_out" >&2
      echo "❗ Planner handoff blocked: plan_lint failed; reverting **Status:** to Planner finalize." >&2
      _planveyor_plan_set_header_status "$plan_path" "Planner finalize" >/dev/null 2>&1 || true
      popd >/dev/null || return 1
      return 4
    fi
  fi

  if [[ "$status_post" == *"**Status:** Done"* ]]; then
    echo "❗ Process violation: Planner set **Status:** Done (Done = only Architect). Fix plan status and rerun." >&2
    popd >/dev/null || return 1
    return 2
  fi

  popd >/dev/null || return 1
  return $rc
}

planveyor_planner_censor() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_planner_censor)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body planner censor)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local sid; sid="$(planveyor_session planner)" || return 1
  _planveyor_session_authority_resume_validate planner "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role planner)" || return 1
  local runner=""
  runner="$(planveyor_runner planner 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode planner censor)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre
  local status_pre_value
  local payload
  local owner_answers

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  status_pre_value="$(_planveyor_extract_status_value "$status_pre" 2>/dev/null || true)"
  echo "Plan status (pre): ${status_pre}" >&2

  owner_answers="$(_planveyor_peek_owner_answers_for planner "$plan_path")"
  payload="$({ echo "ROLE=Planner"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; \
    if [[ -n "${owner_answers//[[:space:]]/}" ]]; then echo ""; echo "Owner answers (out-of-band):"; echo "${owner_answers}"; fi; })"
  case "$runner" in
    codex)
      printf '%s\n' "$payload" | _planveyor_with_role_env planner "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" resume "${sid}" -
      ;;
    claude)
      _planveyor_authority_before_raw_claude_launch || {
        local guard_rc=$?
        popd >/dev/null || return 1
        return "$guard_rc"
      }
      _planveyor_with_role_env planner "$pybin" _planveyor_claude_direct_run -p --resume "${sid}" --permission-mode acceptEdits "${payload}"
      ;;
    *)
      echo "Unsupported planner runner: ${runner} (use: planveyor_runner_set planner codex|claude)" >&2
      popd >/dev/null || return 1
      return 1
      ;;
  esac
  local rc=$?

  local status_post
  local status_post_value
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  status_post_value="$(_planveyor_extract_status_value "$status_post" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2

  # Process safety: Planner must never move plan to Done.
  local status_pre_norm="${status_pre_value:l}"
  status_pre_norm="${status_pre_norm//$'\r'/}"
  status_pre_norm="${status_pre_norm//$'\t'/ }"
  while [[ "$status_pre_norm" == *"  "* ]]; do status_pre_norm="${status_pre_norm//  / }"; done
  status_pre_norm="${status_pre_norm#"${status_pre_norm%%[![:space:]]*}"}"
  status_pre_norm="${status_pre_norm%"${status_pre_norm##*[![:space:]]}"}"
  local status_post_norm="${status_post_value:l}"
  status_post_norm="${status_post_norm//$'\r'/}"
  status_post_norm="${status_post_norm//$'\t'/ }"
  while [[ "$status_post_norm" == *"  "* ]]; do status_post_norm="${status_post_norm//  / }"; done
  status_post_norm="${status_post_norm#"${status_post_norm%%[![:space:]]*}"}"
  status_post_norm="${status_post_norm%"${status_post_norm##*[![:space:]]}"}"
  if [[ "$status_pre_norm" != "done" && "$status_post_norm" == "done" ]]; then
    echo "❗ Process violation: Planner censor changed **Status:** to Done (Done = only Architect). Fix plan status and rerun." >&2
    popd >/dev/null || return 1
    return 2
  fi

  if (( rc == 0 )); then
    local censor_handoff_status=""
    censor_handoff_status="$(_planveyor_censor_handoff_status_for_role planner "$status_pre_value" 2>/dev/null || true)"
    if [[ -n "${censor_handoff_status//[[:space:]]/}" ]]; then
      _planveyor_censor_receipt_gate_check Planner "$plan_path" "$censor_handoff_status" || {
        local gate_rc=$?
        popd >/dev/null || return 1
        return $gate_rc
      }
    fi
  fi

  popd >/dev/null || return 1
  return $rc
}

_planveyor_reviewer_run_for_session_key() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_reviewer_run_for_session_key)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local session_key="${1:-reviewer}"
  local lane_id="${2:-reviewer}"
  local runner="${3:-}"
  session_key="$(_planveyor_normalize_session_key "$session_key")" || return 1
  [[ -n "${lane_id//[[:space:]]/}" ]] || lane_id="$session_key"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body reviewer status_driven)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role reviewer)" || return 1
  [[ -n "${runner//[[:space:]]/}" ]] || runner="$(planveyor_runner reviewer 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  local codex_profile=""
  local -a codex_profile_args
  codex_profile_args=()
  if [[ "$runner" == "codex" ]]; then
    codex_profile="$(_planveyor_profile_for_role_mode reviewer main)" || return $?
    [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  fi
  local sid="" existing_sid=""
  existing_sid="$(planveyor_session "$session_key" 2>/dev/null || true)"
  [[ "$existing_sid" == "<SESSION_ID>" ]] && existing_sid=""
  if [[ -n "${existing_sid//[[:space:]]/}" ]]; then
    _planveyor_session_authority_resume_validate "$session_key" "$existing_sid" || return $?
  elif [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    _planveyor_session_missing_recovery "$session_key"
    return $?
  fi
  if [[ "$runner" == "codex" ]]; then
    sid="$(_planveyor_session_sid_ensure_in_effective_codex_home "$session_key" "$codex_profile")" || return 1
  else
    sid="$existing_sid"
    [[ -n "${sid//[[:space:]]/}" ]] || return 1
  fi
  _planveyor_session_authority_resume_validate "$session_key" "$sid" || return $?
  local status_pre
  local status_pre_value
  local payload
  local owner_answers
  local codex_home=""
  local codex_meta=""
  local run_receipt_surface=""
  local run_receipt_started_at=""
  local rc=0

  pushd "$root" >/dev/null || return 1

  # Safety: Reviewer is allowed to review on a "dirty" tree (staged/current), but must be read-only
  # for tracked files outside docs/** (no fixes/rollbacks during review).
  local -a pre_dirty_tracked_non_docs
  pre_dirty_tracked_non_docs=("${(@f)$( { git diff --name-only; git diff --name-only --cached; } | sort -u | rg -v '^docs/' || true)}")
  pre_dirty_tracked_non_docs=("${(@)pre_dirty_tracked_non_docs:#}")
  local pre_non_docs_hash=""
  pre_non_docs_hash="$({ git diff --no-color -- . ':(exclude)docs/**' || true; git diff --no-color --cached -- . ':(exclude)docs/**' || true; } \
    | _planveyor_py_any -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())' \
  )" || { popd >/dev/null || return 1; return 1; }

  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  status_pre_value="$(_planveyor_extract_status_value "$status_pre" 2>/dev/null || true)"
  echo "Plan status (pre): ${status_pre}" >&2

  run_receipt_started_at="$(_planveyor_now_utc_iso)"
  owner_answers="$(_planveyor_consume_owner_answers_for reviewer "$plan_path")"
  local profile=""
  local model=""
  case "$runner" in
    codex)
      profile="$codex_profile"
      if [[ -n "${profile//[[:space:]]/}" ]]; then
        model="$(_planveyor_codex_expected_model_for_profile "$profile")" || {
          local model_rc=$?
          popd >/dev/null || true
          return $model_rc
        }
      fi
      ;;
    claude)
      profile="direct_child"
      model="$(_planveyor_claude_configured_model 2>/dev/null || true)"
      ;;
  esac
  local -a model_identity_args
  model_identity_args=("${(@f)$(_planveyor_model_identity_payload_args "$runner" reviewer)}")
  local reviewer_runner_alias="$(_planveyor_model_identity_value runner_alias "${model_identity_args[@]}" 2>/dev/null || true)"
  local reviewer_configured_model_id="$(_planveyor_model_identity_value configured_model_id "${model_identity_args[@]}" 2>/dev/null || true)"
  local reviewer_observable_model_id="$(_planveyor_model_identity_value observable_model_id "${model_identity_args[@]}" 2>/dev/null || true)"
  local reviewer_model_id_state="$(_planveyor_model_identity_value model_id_state "${model_identity_args[@]}" 2>/dev/null || true)"
  payload="$({ echo "ROLE=Reviewer"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; echo "REVIEWER_LANE=${lane_id}"; echo "REVIEWER_SESSION_KEY=${session_key}"; echo "REVIEWER_RUNNER=${runner}"; [[ -n "${profile//[[:space:]]/}" ]] && echo "REVIEWER_PROFILE=${profile}"; [[ -n "${model//[[:space:]]/}" ]] && echo "REVIEWER_MODEL=${model}"; [[ -n "${reviewer_runner_alias//[[:space:]]/}" ]] && echo "REVIEWER_RUNNER_ALIAS=${reviewer_runner_alias}"; [[ -n "${reviewer_configured_model_id//[[:space:]]/}" ]] && echo "REVIEWER_CONFIGURED_MODEL_ID=${reviewer_configured_model_id}"; [[ -n "${reviewer_observable_model_id//[[:space:]]/}" ]] && echo "REVIEWER_OBSERVABLE_MODEL_ID=${reviewer_observable_model_id}"; [[ -n "${reviewer_model_id_state//[[:space:]]/}" ]] && echo "REVIEWER_MODEL_ID_STATE=${reviewer_model_id_state}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; \
    if [[ -n "${owner_answers//[[:space:]]/}" ]]; then echo ""; echo "Owner answers (out-of-band):"; echo "${owner_answers}"; fi; })"
  case "$runner" in
    codex)
      run_receipt_surface="codex_exec"
      codex_home="$(_planveyor_codex_home_effective)"
      local provider_home_state="$(_planveyor_init_run_provider_home_state codex)"
      codex_meta="runner=codex profile=${profile} model=${model} session_key=${session_key} lane_id=${lane_id} provider_home_state=${provider_home_state}"
      if [[ -z "${codex_profile//[[:space:]]/}" ]] || _planveyor_codex_session_model_matches_profile "$sid" "$codex_profile" "$codex_home"; then
        printf '%s\n' "$payload" | _planveyor_with_role_env reviewer "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" resume "${sid}" -
        rc=$?
      else
        local actual_model=""
        actual_model="$(_planveyor_codex_session_stat_value "$sid" model "$codex_home" 2>/dev/null || true)"
        local expected_model=""
        expected_model="$(_planveyor_codex_expected_model_for_profile "$codex_profile")" || {
          local model_rc=$?
          popd >/dev/null || true
          return $model_rc
        }
        echo "Stored reviewer session sid=${sid} uses stale model ${actual_model:-unknown}; starting a new reviewer session on ${expected_model}." >&2
        local replacement_capture_dir=""
        if [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
          replacement_capture_dir="$(_planveyor_init_run_capture_begin reviewer 2>/dev/null || true)"
          if [[ -z "${replacement_capture_dir//[[:space:]]/}" ]]; then
            echo "Unable to prepare engaged Reviewer replacement init receipt." >&2
            popd >/dev/null || true
            return 1
          fi
        fi
        local out=""
        out="$(printf '%s\n' "$payload" | _planveyor_with_role_env reviewer "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" - 2>&1)"
        rc=$?
        printf '%s\n' "$out"
        _planveyor_save_session_key_from_output "$session_key" "$out" "$codex_meta"
        local replacement_sid="${_PLANVEYOR_LAST_SAVED_SESSION_ID:-}"
        if [[ -n "${replacement_capture_dir//[[:space:]]/}" ]]; then
          _planveyor_init_run_capture_finalize "$replacement_capture_dir" reviewer "$session_key" codex "$profile" "$provider_home_state" "$out" "$rc" "$replacement_sid" "$model" "" "" "" "" "" "" "$codex_meta"
          local replacement_capture_rc=$?
          if [[ "$PLANVEYOR_CTX_STATE" == "engaged" && "$rc" == "0" && "$replacement_capture_rc" != "0" ]]; then
            rc=$replacement_capture_rc
          elif [[ "$rc" == "0" && "$replacement_capture_rc" == "0" && -n "${replacement_sid//[[:space:]]/}" ]]; then
            sid="$replacement_sid"
          fi
        fi
      fi
      ;;
    claude)
      _planveyor_authority_before_raw_claude_launch || {
        local guard_rc=$?
        popd >/dev/null || return 1
        return "$guard_rc"
      }
      _planveyor_with_role_env reviewer "$pybin" _planveyor_claude_direct_run -p --resume "${sid}" --permission-mode acceptEdits "${payload}"
      rc=$?
      ;;
    *)
      echo "Unsupported reviewer runner: ${runner} (use: planveyor_runner_set reviewer codex|claude)" >&2
      popd >/dev/null || return 1
      return 1
      ;;
  esac

  # Post-check: tracked diffs outside docs/** must remain unchanged.
  local post_non_docs_hash=""
  post_non_docs_hash="$({ git diff --no-color -- . ':(exclude)docs/**' || true; git diff --no-color --cached -- . ':(exclude)docs/**' || true; } \
    | _planveyor_py_any -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())' \
  )" || { popd >/dev/null || return 1; return 1; }
  if [[ "$post_non_docs_hash" != "$pre_non_docs_hash" ]]; then
    echo "❗ Process violation: Reviewer modified tracked non-doc changes during review (outside docs/**)." >&2
    echo "Fix: revert/stash non-doc changes back to the pre-review state, then rerun Reviewer." >&2

    local -a post_dirty_tracked_non_docs
    post_dirty_tracked_non_docs=("${(@f)$( { git diff --name-only; git diff --name-only --cached; } | sort -u | rg -v '^docs/' || true)}")
    post_dirty_tracked_non_docs=("${(@)post_dirty_tracked_non_docs:#}")

    echo "Non-doc dirty paths (pre-run):" >&2
    local p_pre
    for p_pre in "${pre_dirty_tracked_non_docs[@]}"; do
      echo "  - $p_pre" >&2
    done
    echo "Non-doc dirty paths (post-run):" >&2
    local p_post
    for p_post in "${post_dirty_tracked_non_docs[@]}"; do
      echo "  - $p_post" >&2
    done

    popd >/dev/null || return 1
    return 3
  fi

  local status_post
  local status_post_value
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  status_post_value="$(_planveyor_extract_status_value "$status_post" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2
  if [[ -n "${run_receipt_surface//[[:space:]]/}" ]]; then
    local -a authority_run_receipt_arg
    authority_run_receipt_arg=()
    if [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
      authority_run_receipt_arg=("$PLANVEYOR_CTX_JSON")
    fi
    _planveyor_run_receipt_emit \
      reviewer \
      "$sid" \
      "" \
      "$run_receipt_surface" \
      manual \
      "$plan_path" \
      "$status_pre" \
      "$run_receipt_started_at" \
      "$(_planveyor_now_utc_iso)" \
      "$(_planveyor_result_artifact_for_plan "$plan_path" "stdout receipt")" \
      "${authority_run_receipt_arg[@]}" >/dev/null 2>&1 || true
  fi
  _planveyor_review_receipt_emit "$plan_path"

  if [[ "$status_post" == *"**Status:** Done"* ]]; then
    echo "❗ Process violation: Reviewer set **Status:** Done (Done = only Architect). Fix plan status and rerun." >&2
    popd >/dev/null || return 1
    return 2
  fi

  popd >/dev/null || return 1
  return $rc
}

planveyor_reviewer() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  _planveyor_reviewer_run_for_session_key reviewer reviewer
}

planveyor_reviewer_code_risk() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_code_risk)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  _planveyor_reviewer_run_for_session_key reviewer_code_risk reviewer_code_risk
}

planveyor_reviewer_code_contracts() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_code_contracts)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  _planveyor_reviewer_run_for_session_key reviewer_code_contracts reviewer_code_contracts
}

# --- (Optional) Manager ---
_planveyor_manager_mode_admit() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_manager_mode_admit)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local actual_mode="$1"
  local plan_path="$2"
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local plan_fs="$plan_path"
  [[ "$plan_fs" == /* ]] || plan_fs="${root}/${plan_fs}"
  local oracle_py="$(_planveyor_script plan_status_oracle.py)"
  [[ -f "$oracle_py" ]] || {
    echo "Manager mode admission error: missing status oracle: $oracle_py" >&2
    return 3
  }
  local receipt=""
  receipt="$(mktemp "${TMPDIR:-/tmp}/planveyor.manager-mode.XXXXXX")" || return 3
  _planveyor_py_any "$oracle_py" "$plan_fs" --json --manager-mode "$actual_mode" >"$receipt"
  local rc=$?
  if (( rc == 0 )); then
    rm -f "$receipt"
    return 0
  fi
  if (( rc == 4 )); then
    local readback=""
    readback="$(_planveyor_py_any -c 'import json,sys; p=json.load(open(sys.argv[1], encoding="utf-8")); print("state=%s reason=%s required=%s actual=%s" % (p["manager_mode_state"], p["manager_mode_reason"], p["required_manager_mode"], p["actual_manager_mode"]))' "$receipt" 2>/dev/null || true)"
    echo "Manager mode admission rejected: ${readback:-state=unknown reason=oracle_readback_failed actual=${actual_mode}}" >&2
    echo "Remediation: use the compatible Manager wrapper or repair plan_meta.required_manager_mode in ${plan_path}, then rerun the same command; no automatic Manager switch was attempted." >&2
  else
    echo "Manager mode admission failed before Manager startup: plan=${plan_path} actual=${actual_mode} oracle_exit=${rc}" >&2
  fi
  rm -f "$receipt"
  return $rc
}

planveyor_manager() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body manager router)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local stored_sid=""
  stored_sid="$(planveyor_session manager 2>/dev/null || true)"
  [[ "$stored_sid" == "<SESSION_ID>" ]] && stored_sid=""
  if [[ -n "${stored_sid//[[:space:]]/}" ]]; then
    _planveyor_session_authority_resume_validate manager "$stored_sid" || return $?
  elif [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    _planveyor_session_missing_recovery manager
    return $?
  fi
  _planveyor_manager_mode_admit manager-collab "$plan_path" || return $?
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode manager main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local sid; sid="$(_planveyor_session_sid_ensure_in_effective_codex_home manager "$codex_profile")" || return 1
  _planveyor_session_authority_resume_validate manager "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role manager)" || return 1
  local status_pre

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  echo "Plan status (pre): ${status_pre}" >&2

  _planveyor_manager_prompt_body_still_current router "$prompt_body" || {
    local binding_rc=$?
    popd >/dev/null || return 1
    return $binding_rc
  }
  { echo "ROLE=Manager"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env manager "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?

  local status_post
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2

  if [[ "$status_post" == *"**Status:** Done"* ]]; then
    echo "❗ Process violation: Manager/agent set **Status:** Done (Done = only Architect). Fix plan status and rerun." >&2
    popd >/dev/null || return 1
    return 2
  fi
  popd >/dev/null || return 1
  return $rc
}

# --- (Optional) Manager (collab pipeline; subagents) ---
planveyor_manager_collab() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager_collab)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body manager collab_pipeline)" || return $?
  local plan_path; plan_path="$(planveyor_planpath)" || return 1
  local stored_sid=""
  stored_sid="$(planveyor_session manager 2>/dev/null || true)"
  [[ "$stored_sid" == "<SESSION_ID>" ]] && stored_sid=""
  if [[ -n "${stored_sid//[[:space:]]/}" ]]; then
    _planveyor_session_authority_resume_validate manager "$stored_sid" || return $?
  elif [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    _planveyor_session_missing_recovery manager
    return $?
  fi
  _planveyor_manager_mode_admit manager-collab "$plan_path" || return $?
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode manager main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local sid; sid="$(_planveyor_session_sid_ensure_in_effective_codex_home manager "$codex_profile")" || return 1
  _planveyor_session_authority_resume_validate manager "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role manager)" || return 1
  local status_pre
  local before_snapshot=""
  local after_snapshot=""

  pushd "$root" >/dev/null || return 1
  status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
  echo "Plan status (pre): ${status_pre}" >&2

  before_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.before.XXXXXX")"
  after_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.after.XXXXXX")"
  _planveyor_collab_snapshot_ids > "$before_snapshot"

  local payload=""
  payload="$({ echo "ROLE=Manager"; echo "PLAN_PATH=${plan_path}"; echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; echo ""; echo "MANAGER_CMD=run"; })"
  _planveyor_manager_prompt_body_still_current collab_pipeline "$prompt_body" || {
    local binding_rc=$?
    rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
    popd >/dev/null || return 1
    return $binding_rc
  }
  # Keep manager turns that may spawn/reset collab agents explicitly on-request + workspace-write
  # so later `/agents` chat stays available for those threads.
  _planveyor_with_role_env manager "$pybin" _planveyor_codex exec -c 'approval_policy="on-request"' -c 'sandbox_mode="workspace-write"' "${codex_profile_args[@]}" \
    resume "${sid}" "$payload"
  local rc=$?

  local status_post
  status_post="$(planveyor_status_line "$plan_path")" || status_post=""
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2

  _planveyor_collab_agent_sync_all
  _planveyor_collab_snapshot_ids > "$after_snapshot"
  _planveyor_collab_log_transitions "$before_snapshot" "$after_snapshot" "planveyor_manager_collab" >/dev/null 2>&1 || true
  rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
  popd >/dev/null || return 1
  return $rc
}

planveyor_manager_collab_tui() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager_collab_tui)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  # Runs Manager collab pipeline in Codex TUI (so you can watch /agent threads live).
  # Optional:
  #   planveyor_manager_collab_tui --q
  #   planveyor_manager_collab_tui --no-alt-screen
  #   planveyor_manager_collab_tui --merge [--range auto|<MERGE_SHA>|<BASE..HEAD>] [--no-alt-screen]
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local before_snapshot=""
  local after_snapshot=""

  local -a tui_flags merge_args
  tui_flags=()
  merge_args=()
  local merge_mode=0
  local queue_mode=0
  while (( $# > 0 )); do
    case "${1:-}" in
      --q) queue_mode=1 ;;
      --no-alt-screen) tui_flags+=(--no-alt-screen) ;;
      --merge) merge_mode=1 ;;
      --range)
        merge_mode=1
        shift
        [[ -n "${1:-}" ]] || { echo "Usage: planveyor_manager_collab_tui [--q] [--no-alt-screen] [--merge [--range auto|<MERGE_SHA>|<BASE..HEAD>]]" >&2; return 1; }
        merge_args+=("--range" "$1")
        ;;
      *)
        echo "Usage: planveyor_manager_collab_tui [--q] [--no-alt-screen] [--merge [--range auto|<MERGE_SHA>|<BASE..HEAD>]]" >&2
        return 1
        ;;
    esac
    shift
  done

  if (( merge_mode && queue_mode )); then
    echo "Queue mode (--q) and merge mode (--merge) are mutually exclusive." >&2
    return 1
  fi

  local prompt_phase="collab_pipeline"
  (( merge_mode )) && prompt_phase="collab_merge_pipeline"
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body manager "$prompt_phase")" || return $?
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode manager main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")

  local stored_sid=""
  stored_sid="$(planveyor_session manager 2>/dev/null || true)"
  [[ "$stored_sid" == "<SESSION_ID>" ]] && stored_sid=""
  if [[ -n "${stored_sid//[[:space:]]/}" ]]; then
    _planveyor_session_authority_resume_validate manager "$stored_sid" || return $?
  elif [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]] && (( ! merge_mode )); then
    _planveyor_session_missing_recovery manager
    return $?
  fi
  local sid=""
  if (( ! merge_mode && ! queue_mode )); then
    local admission_plan_path=""
    admission_plan_path="$(planveyor_planpath)" || return 1
    _planveyor_manager_mode_admit manager-collab "$admission_plan_path" || return $?
  fi
  if (( merge_mode )); then
    # Merge-mode quickstart must be cold-start safe: bootstrap a local Manager session
    # when the repo has no reusable sid yet.
    sid="$(_planveyor_manager_session_sid_ensure_local_or_init)" || return 1
  else
    sid="$(_planveyor_session_sid_ensure_in_effective_codex_home manager "$codex_profile")" || return 1
  fi
  _planveyor_session_authority_resume_validate manager "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role manager)" || return 1

  pushd "$root" >/dev/null || return 1
  before_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.before.XXXXXX")"
  after_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.after.XXXXXX")"
  _planveyor_collab_snapshot_ids > "$before_snapshot"
  local payload=""
  if (( merge_mode )); then
    local cmd_line="MANAGER_CMD=merge_run"
    if (( ${#merge_args[@]} > 0 )); then
      cmd_line="${cmd_line} ${merge_args[*]}"
    fi
    payload="$(_planveyor_manager_merge_payload "$pybin" "$cmd_line" "$prompt_body")" || { popd >/dev/null; return 1; }
  else
    local plan_path=""
    local status_pre=""
    local manager_cmd="MANAGER_CMD=run"
    if (( queue_mode )); then
      manager_cmd="MANAGER_CMD=run_q"
      plan_path="$(planveyor_planpath 2>/dev/null || true)"
      if [[ -n "${plan_path//[[:space:]]/}" ]]; then
        status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || true)"
      fi
    else
      plan_path="$(planveyor_planpath)" || { popd >/dev/null; return 1; }
      status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }
    fi
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
    payload="$({ echo "ROLE=Manager"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; echo ""; echo "${manager_cmd}"; })"
  fi
  _planveyor_manager_prompt_body_still_current "$prompt_phase" "$prompt_body" || {
    local binding_rc=$?
    rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
    popd >/dev/null || return 1
    return $binding_rc
  }
  # Keep the interactive TUI aligned with the configured profile so spawned collab threads can
  # inherit the active approval policy from the parent session.
  _planveyor_with_role_env manager "$pybin" _planveyor_codex resume "${tui_flags[@]}" "${codex_profile_args[@]}" -s workspace-write "${sid}" "$payload"
  local rc=$?

  if ! _planveyor_authority_validate_runtime_pin >/dev/null 2>&1; then
    print -u2 -r -- "planveyor: runtime_changed_after_resume; manager_rc=${rc}; posthooks=skipped"
    rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
    popd >/dev/null || true
    return "$rc"
  fi

  if (( ! merge_mode )); then
    local plan_path=""
    local status_post=""
    plan_path="$(planveyor_planpath 2>/dev/null || true)"
    if [[ -n "${plan_path//[[:space:]]/}" ]]; then
      status_post="$(planveyor_status_line "$plan_path" 2>/dev/null || true)"
      [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2
    fi
  fi

  _planveyor_collab_agent_sync_all
  _planveyor_collab_snapshot_ids > "$after_snapshot"
  _planveyor_collab_log_transitions "$before_snapshot" "$after_snapshot" "planveyor_manager_collab_tui" >/dev/null 2>&1 || true
  rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
  popd >/dev/null || return 1
  return $rc
}

planveyor_manager_collab_cmd() {
  emulate -L zsh
  # Validate the explicit continuation grammar before any authority/session or
  # plan/queue work. The selector is data, never part of MANAGER_CMD prose.
  local continuation_cycle_id="" continuation_arg="" continuation_requested=0
  for continuation_arg in "$@"; do
    [[ "$continuation_arg" == --followups-capture-cycle-id* ]] && continuation_requested=1
  done
  if (( continuation_requested )); then
    local continuation_uuid_re='^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    if (( $# != 4 )) || [[ "$1" != run || "$2" != docs/plans/*.md || "$2" == *[[:space:]]* || "$2" == */../* || "$2" == */./* || "$3" != --followups-capture-cycle-id || ! "$4" =~ "$continuation_uuid_re" ]]; then
      echo "Usage: planveyor_manager_collab_cmd run <docs/plans/PLAN.md> --followups-capture-cycle-id <UUIDv4>" >&2
      return 1
    fi
    continuation_cycle_id="$4"
    set -- run "$2"
  elif [[ "${1:-}" == run ]] && (( $# > 2 )); then
    echo "Usage: planveyor_manager_collab_cmd run [Q|PLAN_PATH]; continuation requires an explicit --followups-capture-cycle-id <UUIDv4>" >&2
    return 1
  fi
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager_collab_cmd)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  # One-shot commands for Manager collab prompt (including pipeline run via `run`).
  # Examples:
  #   planveyor_manager_collab_cmd status
  #   planveyor_manager_collab_cmd plan_set docs/plans/YYMMDD_HHMM_topic.md
  #   planveyor_manager_collab_cmd analysis docs/plans/YYMMDD_HHMM_analysis_wave.md
  #   planveyor_manager_collab_cmd decomposition docs/plans/YYMMDD_HHMM_decomposition.md
  #   planveyor_manager_collab_cmd run
  #   planveyor_manager_collab_cmd run Q
  #   planveyor_manager_collab_cmd run docs/plans/YYMMDD_HHMM_topic.md
  #   planveyor_manager_collab_cmd merge_apply --from feature/x --to main --then-review=1
  #   planveyor_manager_collab_cmd close role=all
  #   planveyor_manager_collab_cmd reset role=coder
  local cmd="${1:-}"
  (( $# > 0 )) && shift
  [[ -n "${cmd//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_manager_collab_cmd <status|plan_set|analysis [PLAN_PATH]|decomposition [PLAN_PATH]|run [Q]|merge_status|merge_run|merge_apply|close|reset ...>" >&2
    return 1
  }
  local queue_mode=0
  if [[ "$cmd" == "run" && "${1:-}" == "Q" ]]; then
    queue_mode=1
    shift || true
    if (( $# > 0 )); then
      echo "Usage: planveyor_manager_collab_cmd run Q" >&2
      return 1
    fi
    cmd="run_q"
  fi
  local cmd_line="$cmd"
  if [[ "$cmd_line" != MANAGER_CMD=* ]]; then
    cmd_line="MANAGER_CMD=${cmd_line}"
  fi
  if (( $# > 0 )); then
    cmd_line="${cmd_line} $*"
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local is_merge_cmd=0
  local cmd_name="${cmd_line#MANAGER_CMD=}"
  cmd_name="${cmd_name%%[[:space:]]*}"
  local needs_plan_path=1
  local before_snapshot=""
  local after_snapshot=""
  if [[ "$cmd_name" == merge_* ]]; then
    is_merge_cmd=1
  fi
  local prompt_phase="collab_pipeline"
  (( is_merge_cmd )) && prompt_phase="collab_merge_pipeline"
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body manager "$prompt_phase")" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role manager)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode manager main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  case "$cmd_name" in
    status|plan_set|reset|close|run_q) needs_plan_path=0 ;;
    run)
      if [[ "$cmd_line" != "MANAGER_CMD=run" ]]; then
        needs_plan_path=0
      fi
      ;;
    analysis)
      if [[ "$cmd_line" != "MANAGER_CMD=analysis" ]]; then
        needs_plan_path=0
      fi
      ;;
    decomposition)
      if [[ "$cmd_line" != "MANAGER_CMD=decomposition" ]]; then
        needs_plan_path=0
      fi
      ;;
  esac

  local stored_sid=""
  stored_sid="$(planveyor_session manager 2>/dev/null || true)"
  [[ "$stored_sid" == "<SESSION_ID>" ]] && stored_sid=""
  if [[ -n "${stored_sid//[[:space:]]/}" ]]; then
    _planveyor_session_authority_resume_validate manager "$stored_sid" || return $?
  elif [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]] && (( ! is_merge_cmd )); then
    _planveyor_session_missing_recovery manager
    return $?
  fi

  pushd "$root" >/dev/null || return 1
  before_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.before.XXXXXX")"
  after_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.after.XXXXXX")"
  _planveyor_collab_snapshot_ids > "$before_snapshot"
  local plan_path=""
  local status_pre=""
  local explicit_run_path=""
  if [[ "$cmd_name" == "run" && "$cmd_line" != "MANAGER_CMD=run" ]]; then
    explicit_run_path="${cmd_line#MANAGER_CMD=run }"
    explicit_run_path="${explicit_run_path%%[[:space:]]*}"
  fi
  if [[ -n "${explicit_run_path//[[:space:]]/}" ]]; then
    plan_path="$explicit_run_path"
    _planveyor_manager_mode_admit manager-collab "$plan_path"
    local admission_rc=$?
    if (( admission_rc != 0 )); then
      popd >/dev/null
      return $admission_rc
    fi
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  elif (( ! is_merge_cmd && needs_plan_path )); then
    plan_path="$(planveyor_planpath)" || { popd >/dev/null; return 1; }
    _planveyor_manager_mode_admit manager-collab "$plan_path"
    local admission_rc=$?
    if (( admission_rc != 0 )); then
      popd >/dev/null
      return $admission_rc
    fi
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  elif (( ! is_merge_cmd && queue_mode )); then
    plan_path="$(planveyor_planpath 2>/dev/null || true)"
    if [[ -n "${plan_path//[[:space:]]/}" ]]; then
      status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || true)"
      [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
    fi
  fi
  local sid=""
  if (( is_merge_cmd )); then
    sid="$(_planveyor_manager_session_sid_ensure_local_or_init)" || { popd >/dev/null; return 1; }
  else
    sid="$(planveyor_session manager)" || { popd >/dev/null; return 1; }
  fi
  _planveyor_session_authority_resume_validate manager "$sid" || { local validate_rc=$?; popd >/dev/null || true; return $validate_rc; }

  local payload=""
  if (( is_merge_cmd )); then
    payload="$(_planveyor_manager_merge_payload "$pybin" "$cmd_line" "$prompt_body")" || { popd >/dev/null; return 1; }
  else
    payload="$({ echo "ROLE=Manager"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${continuation_cycle_id}" ]] && echo "FOLLOWUPS_CAPTURE_CYCLE_ID=${continuation_cycle_id}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; echo ""; echo "${cmd_line}"; })"
  fi
  _planveyor_manager_prompt_body_still_current "$prompt_phase" "$prompt_body" || {
    local binding_rc=$?
    rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
    popd >/dev/null || return 1
    return $binding_rc
  }
  _planveyor_with_role_env manager "$pybin" _planveyor_codex exec -c 'approval_policy="on-request"' -c 'sandbox_mode="workspace-write"' "${codex_profile_args[@]}" \
    resume "${sid}" "$payload"
  local rc=$?

  _planveyor_collab_agent_sync_all
  _planveyor_collab_snapshot_ids > "$after_snapshot"
  _planveyor_collab_log_transitions "$before_snapshot" "$after_snapshot" "planveyor_manager_collab_cmd" >/dev/null 2>&1 || true
  rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
  popd >/dev/null || return 1
  return $rc
}

# --- Merge-mode (collab pipeline; post-merge checks) ---
planveyor_merge_collab_tui() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_collab_tui)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  # Thin alias for the merge-mode branch of `planveyor_manager_collab_tui`.
  # Usage:
  #   planveyor_merge_collab_tui [--no-alt-screen] [--range auto|<MERGE_SHA>|<BASE..HEAD>]
  planveyor_manager_collab_tui --merge "$@"
}

planveyor_merge_collab_cmd() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_collab_cmd)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  # Thin alias for `planveyor_manager_collab_cmd merge_run`.
  # Usage:
  #   planveyor_merge_collab_cmd [--range auto|<MERGE_SHA>|<BASE..HEAD>]
  planveyor_manager_collab_cmd merge_run "$@"
}

planveyor_merge_apply_collab_tui() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_apply_collab_tui)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  # Runs Manager collab in TUI and immediately starts merge-apply pipeline.
  # Usage:
  #   planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local before_snapshot=""
  local after_snapshot=""

  local -a tui_flags cmd_args
  tui_flags=()
  cmd_args=()
  local has_from=0
  while (( $# > 0 )); do
    case "${1:-}" in
      --no-alt-screen) tui_flags+=(--no-alt-screen) ;;
      --from=*|--to=*|--then-review=*)
        local opt="${1%%=*}"
        local val="${1#*=}"
        [[ -n "${val:-}" ]] || { echo "Usage: planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2; return 1; }
        if [[ "$opt" == "--then-review" && "$val" != "0" && "$val" != "1" ]]; then
          echo "Usage: planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2
          return 1
        fi
        cmd_args+=("${opt}" "$val")
        [[ "$opt" == "--from" ]] && has_from=1
        ;;
      --from|--to|--then-review)
        local opt="${1}"
        shift
        [[ -n "${1:-}" ]] || { echo "Usage: planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2; return 1; }
        if [[ "$opt" == "--then-review" && "$1" != "0" && "$1" != "1" ]]; then
          echo "Usage: planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2
          return 1
        fi
        cmd_args+=("${opt}" "$1")
        [[ "$opt" == "--from" ]] && has_from=1
        ;;
      *)
        echo "Usage: planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2
        return 1
        ;;
    esac
    shift
  done
  (( has_from == 1 )) || { echo "Usage: planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2; return 1; }

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body manager collab_merge_pipeline)" || return $?
  local sid; sid="$(planveyor_session manager)" || return 1
  _planveyor_session_authority_resume_validate manager "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role manager)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode manager main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")

  pushd "$root" >/dev/null || return 1
  before_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.before.XXXXXX")"
  after_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.after.XXXXXX")"
  _planveyor_collab_snapshot_ids > "$before_snapshot"
  local cmd_line="MANAGER_CMD=merge_apply ${cmd_args[*]}"
  local payload=""
  payload="$(_planveyor_manager_merge_payload "$pybin" "$cmd_line" "$prompt_body")" || { popd >/dev/null; return 1; }
  _planveyor_manager_prompt_body_still_current collab_merge_pipeline "$prompt_body" || {
    local binding_rc=$?
    rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
    popd >/dev/null || return 1
    return $binding_rc
  }
  _planveyor_with_role_env manager "$pybin" _planveyor_codex resume "${tui_flags[@]}" "${codex_profile_args[@]}" -s workspace-write "${sid}" "$payload"
  local rc=$?
  _planveyor_collab_agent_sync_all
  _planveyor_collab_snapshot_ids > "$after_snapshot"
  _planveyor_collab_log_transitions "$before_snapshot" "$after_snapshot" "planveyor_merge_apply_collab_tui" >/dev/null 2>&1 || true
  rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
  popd >/dev/null || return 1
  return $rc
}

planveyor_merge_apply_collab_cmd() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_apply_collab_cmd)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  # One-shot merge-apply pipeline via Manager collab prompt.
  # Usage:
  #   planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local before_snapshot=""
  local after_snapshot=""

  local -a cmd_args
  cmd_args=()
  local has_from=0
  while (( $# > 0 )); do
    case "${1:-}" in
      --from=*|--to=*|--then-review=*)
        local opt="${1%%=*}"
        local val="${1#*=}"
        [[ -n "${val:-}" ]] || { echo "Usage: planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2; return 1; }
        if [[ "$opt" == "--then-review" && "$val" != "0" && "$val" != "1" ]]; then
          echo "Usage: planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2
          return 1
        fi
        cmd_args+=("${opt}" "$val")
        [[ "$opt" == "--from" ]] && has_from=1
        ;;
      --from|--to|--then-review)
        local opt="${1}"
        shift
        [[ -n "${1:-}" ]] || { echo "Usage: planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2; return 1; }
        if [[ "$opt" == "--then-review" && "$1" != "0" && "$1" != "1" ]]; then
          echo "Usage: planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2
          return 1
        fi
        cmd_args+=("${opt}" "$1")
        [[ "$opt" == "--from" ]] && has_from=1
        ;;
      *)
        echo "Usage: planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2
        return 1
        ;;
    esac
    shift
  done
  (( has_from == 1 )) || { echo "Usage: planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" >&2; return 1; }

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body manager collab_merge_pipeline)" || return $?
  local sid; sid="$(planveyor_session manager)" || return 1
  _planveyor_session_authority_resume_validate manager "$sid" || return $?
  local pybin; pybin="$(_planveyor_resolve_pybin_for_role manager)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode manager main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")

  pushd "$root" >/dev/null || return 1
  before_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.before.XXXXXX")"
  after_snapshot="$(mktemp "${TMPDIR:-/tmp}/planveyor.collab.after.XXXXXX")"
  _planveyor_collab_snapshot_ids > "$before_snapshot"
  local cmd_line="MANAGER_CMD=merge_apply ${cmd_args[*]}"
  local payload=""
  payload="$(_planveyor_manager_merge_payload "$pybin" "$cmd_line" "$prompt_body")" || { popd >/dev/null; return 1; }
  _planveyor_manager_prompt_body_still_current collab_merge_pipeline "$prompt_body" || {
    local binding_rc=$?
    rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
    popd >/dev/null || return 1
    return $binding_rc
  }
  _planveyor_with_role_env manager "$pybin" _planveyor_codex exec -c 'approval_policy="on-request"' -c 'sandbox_mode="workspace-write"' "${codex_profile_args[@]}" \
    resume "${sid}" "$payload"
  local rc=$?
  _planveyor_collab_agent_sync_all
  _planveyor_collab_snapshot_ids > "$after_snapshot"
  _planveyor_collab_log_transitions "$before_snapshot" "$after_snapshot" "planveyor_merge_apply_collab_cmd" >/dev/null 2>&1 || true
  rm -f "$before_snapshot" "$after_snapshot" >/dev/null 2>&1 || true
  popd >/dev/null || return 1
  return $rc
}

# --- (Optional) Manager (custom pipeline; pre-initialized role sessions via wrappers) ---
# Custom stays serial terminal Done/Superseded -> Owner in this slice; collab/queue-only
# docs-closeout final_docs_commit auto-skip and queue stop-scope fields
# (latest_stop_reason_scope/historical_stop_reason) are not wired into these wrappers;
# custom prompt treats queue-only diagnostics as N/A.
planveyor_manager_invocation_checkpoint() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager_invocation_checkpoint)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local reason_code="" json=0
  local -a source_refs
  source_refs=()
  local usage="Usage: planveyor_manager_invocation_checkpoint --stop-reason-code <code> --source-ref <repo-ref> [--source-ref <repo-ref> ...] --json"
  while (( $# > 0 )); do
    case "${1:-}" in
      --stop-reason-code)
        shift
        reason_code="${1:-}"
        ;;
      --source-ref)
        shift
        source_refs+=("${1:-}")
        ;;
      --json) json=1 ;;
      --help|-h)
        echo "$usage" >&2
        return 0
        ;;
      *)
        echo "$usage" >&2
        return 2
        ;;
    esac
    shift
  done
  [[ -n "${MANAGER_INVOCATION_ID:-}" && -n "${MANAGER_INVOCATION_RECEIPT_PATH:-}" && \
     -n "$reason_code" && ${#source_refs[@]} -gt 0 ]] || {
    echo "$usage" >&2
    return 2
  }
  local out=""
  out="$(_planveyor_manager_invocation_receipt_checkpoint \
    "$MANAGER_INVOCATION_RECEIPT_PATH" "$MANAGER_INVOCATION_ID" \
    "$reason_code" "${source_refs[@]}")"
  local rc=$?
  if (( json )); then
    print -r -- "$out"
  elif (( rc == 0 )); then
    print -r -- "invocation_id=${MANAGER_INVOCATION_ID}"
    print -r -- "stop_checkpoint_state=recorded"
    print -r -- "stop_reason_code=${reason_code}"
  else
    print -r -- "$out"
  fi
  return $rc
}

_planveyor_manager_custom_pipeline_terminal() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_manager_custom_pipeline_terminal)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local receipt_path="${1:-}" invocation_id="${2:-}" sid="${3:-}" launch_surface="${4:-}"
  local plan_path="${5:-}" status_pre="${6:-}" started_at="${7:-}" result_artifact="${8:-}"
  local state="${9:-blocked}" reason_code="${10:-terminal_readback_failed}" manager_rc="${11:-}"
  local active_plan="${12:-}" final_plan="${13:-}" oracle_json="${14:-}"
  local queue_json="${15:-}" worktree_json="${16:-}" closeout_json="${17:-}"
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local last_commit=""
  last_commit="$(git -C "$root" rev-parse HEAD 2>/dev/null || true)"

  local finalized=""
  finalized="$(_planveyor_manager_invocation_receipt_finalize "$receipt_path" "$invocation_id" \
    "$state" "$reason_code" "$manager_rc" "$active_plan" "$final_plan" \
    "$oracle_json" "$queue_json" "$last_commit" "$worktree_json" "$closeout_json" \
    "$result_artifact")" || {
      [[ -n "${finalized//[[:space:]]/}" ]] && print -r -- "$finalized" >&2
      _planveyor_py_any - "$invocation_id" "$receipt_path" <<'PY'
import json, sys
print(json.dumps({
    "schema": "manager_invocation_wrapper_error.v1",
    "state": "blocked",
    "reason_code": "receipt_finalization_failed",
    "invocation_id": sys.argv[1],
    "receipt_path": sys.argv[2],
}, sort_keys=True))
PY
      return 126
    }

  local pointer_state="updated"
  local -a authority_run_receipt_arg
  authority_run_receipt_arg=()
  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    authority_run_receipt_arg=("$PLANVEYOR_CTX_JSON")
  fi
  if ! _planveyor_run_receipt_emit \
    manager_custom_pipeline "$sid" "" "$launch_surface" manager_custom_pipeline \
    "$plan_path" "$status_pre" "$started_at" "$(_planveyor_now_utc_iso)" \
    "$result_artifact" "${authority_run_receipt_arg[@]}" >/dev/null 2>&1; then
    pointer_state="write_failed"
  fi
  _planveyor_manager_invocation_receipt_pointer "$receipt_path" "$invocation_id" "$pointer_state" >/dev/null || {
    _planveyor_py_any - "$invocation_id" "$receipt_path" <<'PY'
import json, sys
print(json.dumps({
    "schema": "manager_invocation_wrapper_error.v1",
    "state": "blocked",
    "reason_code": "receipt_finalization_failed",
    "invocation_id": sys.argv[1],
    "receipt_path": sys.argv[2],
}, sort_keys=True))
PY
    return 126
  }
  local terminal_json=""
  terminal_json="$(_planveyor_manager_invocation_receipt_read "$receipt_path" "$invocation_id" terminal)" || {
    _planveyor_py_any - "$invocation_id" "$receipt_path" <<'PY'
import json, sys
print(json.dumps({
    "schema": "manager_invocation_wrapper_error.v1",
    "state": "blocked",
    "reason_code": "receipt_finalization_failed",
    "invocation_id": sys.argv[1],
    "receipt_path": sys.argv[2],
}, sort_keys=True))
PY
    return 126
  }
  print -r -- "$terminal_json"
  [[ "$pointer_state" == "updated" && "$state" != "blocked" ]] || return 125
  return 0
}

_planveyor_manager_queue_terminal_lineage() {
  local queue_json="${1:-}"
  local prelaunch_plan="${2:-}"
  _planveyor_py_any - "$queue_json" "$prelaunch_plan" <<'PY'
import json
import re
import sys

try:
    payload = json.loads(sys.argv[1])
except (TypeError, ValueError, json.JSONDecodeError):
    raise SystemExit(1)
prelaunch_plan = sys.argv[2]
if not isinstance(payload, dict):
    raise SystemExit(1)
if not isinstance(payload.get("exists"), bool) or not isinstance(
    payload.get("queue_empty"), bool
):
    raise SystemExit(1)


def optional_plan(key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
    ):
        raise SystemExit(1)
    return value


active_plan = optional_plan("active_plan")
resume_parent_plan = optional_plan("resume_parent_plan")
effective_plan = optional_plan("effective_plan")
if payload["exists"] is False:
    if (
        not payload["queue_empty"]
        or prelaunch_plan
        or active_plan is not None
        or resume_parent_plan is not None
        or effective_plan is not None
    ):
        raise SystemExit(1)
    print("active_plan=")
    print("final_plan=")
    print("readback_plan=")
    raise SystemExit(0)

if active_plan is not None and resume_parent_plan is not None:
    raise SystemExit(1)
if effective_plan != (active_plan or resume_parent_plan):
    raise SystemExit(1)
transition = payload.get("last_transition")
if transition is None:
    transition = {}
if not isinstance(transition, dict):
    raise SystemExit(1)

if effective_plan is not None:
    if payload["queue_empty"]:
        raise SystemExit(1)
    if effective_plan != prelaunch_plan:
        if not prelaunch_plan or transition.get("finalized_plan") != prelaunch_plan:
            raise SystemExit(1)
        next_plan = transition.get("next_plan")
        resume_plan = transition.get("resume_parent_plan")
        if bool(next_plan) == bool(resume_plan):
            raise SystemExit(1)
        if (next_plan or resume_plan) != effective_plan:
            raise SystemExit(1)
        if transition.get("queue_complete") is not False:
            raise SystemExit(1)
    print(f"active_plan={effective_plan}")
    print(f"final_plan={effective_plan}")
    print(f"readback_plan={effective_plan}")
    raise SystemExit(0)

if not payload["queue_empty"]:
    activation_blocker = transition.get("activation_blocker")
    if (
        not prelaunch_plan
        or transition.get("kind") != "advance_blocked"
        or transition.get("finalized_plan") != prelaunch_plan
        or transition.get("queue_complete") is not False
        or transition.get("next_plan") is not None
        or transition.get("resume_parent_plan") is not None
        or not isinstance(activation_blocker, str)
        or re.fullmatch(
            r"depends_on_skipped_incompatible: \S+ depends_on \S+ "
            r"state=skipped_manager_mode",
            activation_blocker,
        )
        is None
    ):
        raise SystemExit(1)
    print("active_plan=")
    print(f"final_plan={prelaunch_plan}")
    print(f"readback_plan={prelaunch_plan}")
    raise SystemExit(0)
if prelaunch_plan:
    if (
        transition.get("finalized_plan") != prelaunch_plan
        or transition.get("queue_complete") is not True
        or transition.get("next_plan") is not None
        or transition.get("resume_parent_plan") is not None
    ):
        raise SystemExit(1)
    print("active_plan=")
    print(f"final_plan={prelaunch_plan}")
    print(f"readback_plan={prelaunch_plan}")
else:
    print("active_plan=")
    print("final_plan=")
    print("readback_plan=")
PY
}

_planveyor_manager_custom_pipeline_supervise() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_manager_custom_pipeline_supervise)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local command="${1:-interactive}"
  local launch_surface="${2:-codex_exec}"
  local initial_plan="${3:-}"
  local cmd_line="${4:-}"
  local no_alt_screen="${5:-0}"
  local root=""
  root="$(_planveyor_project_root)" || return $?

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body manager custom_pipeline)" || return $?

  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode manager main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")

  local sid=""
  sid="$(planveyor_session manager)" || return 1
  _planveyor_session_authority_resume_validate manager "$sid" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  local started_at="$(_planveyor_now_utc_iso)"
  local invocation_id=""
  invocation_id="$(_planveyor_manager_invocation_id)"
  local receipt_path=""
  receipt_path="$(_planveyor_manager_invocation_receipt_path "$invocation_id")" || return 1
  local seeded=""
  local -a authority_manager_seed_arg
  authority_manager_seed_arg=()
  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    authority_manager_seed_arg=("$PLANVEYOR_CTX_JSON")
  fi
  seeded="$(_planveyor_manager_invocation_receipt_seed "$invocation_id" "$receipt_path" \
    "$sid" "$command" "$initial_plan" "$started_at" "${authority_manager_seed_arg[@]}")" || {
      _planveyor_py_any - "$invocation_id" "$receipt_path" <<'PY'
import json, sys
print(json.dumps({
    "schema": "manager_invocation_wrapper_error.v1",
    "state": "blocked",
    "reason_code": "receipt_seed_failed",
    "invocation_id": sys.argv[1],
    "receipt_path": sys.argv[2],
}, sort_keys=True))
PY
      return 125
    }

  pushd "$root" >/dev/null || return 1
  local active_plan="$initial_plan"
  local queue_json='{"state":"not_applicable","reason":"single_plan_or_interactive"}'
  local queue_discovery_rc=0
  local queue_prelaunch_empty="false"
  local queue_mode_rejected="false"
  local active_plan_supplied="false"
  if [[ "$command" == "run_q" ]]; then
    queue_json="$(planveyor_q_next_json --manager-mode manager-custom-pipeline 2>/dev/null)"
    queue_discovery_rc=$?
    if (( queue_discovery_rc == 0 )); then
      active_plan="$(_planveyor_py_any - "$queue_json" <<'PY'
import json, sys
try:
    payload = json.loads(sys.argv[1])
except (TypeError, ValueError):
    raise SystemExit(1)
print(
    payload.get("active_plan")
    or payload.get("resume_parent_plan")
    or payload.get("effective_plan")
    or payload.get("plan")
    or ""
)
PY
)" || active_plan=""
      [[ -n "${active_plan//[[:space:]]/}" ]] && active_plan_supplied="true"
      queue_prelaunch_empty="$(_planveyor_py_any - "$queue_json" <<'PY'
import json, sys
try:
    payload = json.loads(sys.argv[1])
except (TypeError, ValueError):
    print("false")
else:
    print("true" if payload.get("queue_empty") is True else "false")
PY
)"
    else
      local queue_failure_kv=""
      queue_failure_kv="$(_planveyor_py_any - "$queue_json" <<'PY'
import json, sys
try:
    payload = json.loads(sys.argv[1])
except (TypeError, ValueError):
    raise SystemExit(1)
else:
    print(f"kind={payload.get('closeout_kind') or ''}")
    print(f"plan={payload.get('candidate_plan') or ''}")
PY
)" || queue_failure_kv=""
      local queue_failure_kind="" queue_failure_plan="" queue_failure_row=""
      for queue_failure_row in ${(f)queue_failure_kv}; do
        case "$queue_failure_row" in
          kind=*) queue_failure_kind="${queue_failure_row#kind=}" ;;
          plan=*) queue_failure_plan="${queue_failure_row#plan=}" ;;
        esac
      done
      if [[ "$queue_failure_kind" == "manager_mode_mismatch" ]]; then
        queue_mode_rejected="true"
        active_plan="$queue_failure_plan"
        [[ -n "${active_plan//[[:space:]]/}" ]] && active_plan_supplied="true"
      else
        local queue_show_json=""
        queue_show_json="$(planveyor_q_show --json 2>/dev/null)" || queue_show_json=""
        local queue_missing=""
        queue_missing="$(_planveyor_py_any - "$queue_show_json" <<'PY'
import json, sys
try:
    payload = json.loads(sys.argv[1])
except (TypeError, ValueError):
    print("false")
else:
    print(
        "true"
        if payload.get("exists") is False and payload.get("queue_empty") is True
        else "false"
    )
PY
)"
        if [[ "$queue_missing" == "true" ]]; then
          queue_json="$queue_show_json"
          queue_discovery_rc=0
          queue_prelaunch_empty="true"
        fi
      fi
    fi
  fi

  [[ -n "${active_plan//[[:space:]]/}" ]] && active_plan_supplied="true"
  local active_plan_invalid="false"
  if [[ -n "${active_plan//[[:space:]]/}" ]]; then
    active_plan="$(_planveyor_explicit_plan_normalize "$root" "$active_plan" 2>/dev/null || true)"
    [[ -z "${active_plan//[[:space:]]/}" ]] && active_plan_invalid="true"
  fi
  if [[ "$queue_mode_rejected" == "true" ]]; then
    local worktree_json='{"state":"not_evaluated","reason":"manager_mode_rejected"}'
    local closeout_json='{"state":"blocked","reason":"manager_mode_rejected"}'
    local rejected_artifact="stdout receipt"
    [[ -n "$active_plan" ]] && \
      rejected_artifact="$(_planveyor_result_artifact_for_plan "$active_plan" "stdout receipt")"
    _planveyor_manager_custom_pipeline_terminal "$receipt_path" "$invocation_id" "$sid" \
      "$launch_surface" "$active_plan" "" "$started_at" \
      "$rejected_artifact" \
      blocked manager_mode_rejected "$queue_discovery_rc" "$active_plan" "$active_plan" \
      '{"state":"blocked","reason":"manager_mode_rejected"}' "$queue_json" \
      "$worktree_json" "$closeout_json"
    local terminal_rc=$?
    popd >/dev/null || true
    return $terminal_rc
  fi
  if [[ "$active_plan_invalid" == "true" && "$active_plan_supplied" == "true" ]]; then
    local worktree_json='{"state":"not_evaluated","reason":"invalid_active_plan"}'
    local closeout_json='{"state":"blocked","reason":"invalid_active_plan"}'
    _planveyor_manager_custom_pipeline_terminal "$receipt_path" "$invocation_id" "$sid" \
      "$launch_surface" "" "" "$started_at" "stdout receipt" blocked \
      terminal_readback_failed "$queue_discovery_rc" "" "" \
      '{"state":"blocked","reason":"invalid_active_plan"}' "$queue_json" \
      "$worktree_json" "$closeout_json"
    local terminal_rc=$?
    popd >/dev/null || true
    return $terminal_rc
  fi
  if [[ -z "${active_plan//[[:space:]]/}" && "$command" != "run_q" ]]; then
    local worktree_json='{"state":"not_evaluated","reason":"missing_plan"}'
    local closeout_json='{"state":"blocked","reason":"missing_plan"}'
    _planveyor_manager_custom_pipeline_terminal "$receipt_path" "$invocation_id" "$sid" \
      "$launch_surface" "" "" "$started_at" "stdout receipt" blocked \
      terminal_readback_failed "" "" "" \
      '{"state":"not_applicable","reason":"missing_plan"}' "$queue_json" \
      "$worktree_json" "$closeout_json"
    local terminal_rc=$?
    popd >/dev/null || true
    return $terminal_rc
  fi

  local admission_rc=0
  if [[ -n "${active_plan//[[:space:]]/}" ]]; then
    _planveyor_manager_mode_admit manager-custom-pipeline "$active_plan"
    admission_rc=$?
  fi
  if (( admission_rc != 0 )); then
    local worktree_json='{"state":"not_evaluated","reason":"manager_mode_rejected"}'
    local closeout_json='{"state":"blocked","reason":"manager_mode_rejected"}'
    _planveyor_manager_custom_pipeline_terminal "$receipt_path" "$invocation_id" "$sid" \
      "$launch_surface" "$active_plan" "" "$started_at" \
      "$(_planveyor_result_artifact_for_plan "$active_plan" "stdout receipt")" blocked \
      manager_mode_rejected "$admission_rc" "$active_plan" "$active_plan" \
      '{"state":"blocked","reason":"manager_mode_rejected"}' "$queue_json" \
      "$worktree_json" "$closeout_json"
    local terminal_rc=$?
    popd >/dev/null || true
    return $terminal_rc
  fi

  local status_pre=""
  [[ -n "${active_plan//[[:space:]]/}" ]] && \
    status_pre="$(planveyor_status_line "$active_plan" 2>/dev/null || true)"
  [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  local result_artifact=""
  if [[ -n "${active_plan//[[:space:]]/}" ]]; then
    result_artifact="$(_planveyor_result_artifact_for_plan "$active_plan" "stdout receipt")"
  else
    result_artifact="stdout receipt"
  fi
  local run_receipt_path=""
  run_receipt_path="$(_planveyor_run_receipt_path manager_custom_pipeline 2>/dev/null || true)"
  local payload=""
  payload="$({
    echo "ROLE=Manager"
    [[ -n "${active_plan//[[:space:]]/}" ]] && echo "PLAN_PATH=${active_plan}"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"
    echo "PYBIN=${pybin}"
    echo "MANAGER_INVOCATION_ID=${invocation_id}"
    echo "MANAGER_INVOCATION_RECEIPT_PATH=${receipt_path}"
    [[ -n "${run_receipt_path//[[:space:]]/}" ]] && echo "RUN_RECEIPT_PATH=${run_receipt_path}"
    echo "RESULT_ARTIFACT=${result_artifact}"
    [[ "$command" == "run_q" ]] && echo "MANAGER_QUEUE_DISCOVERY_JSON=${queue_json}"
    printf '%s\n' "$prompt_body"
    [[ -n "${cmd_line//[[:space:]]/}" ]] && { echo ""; echo "$cmd_line"; }
  })"

  _planveyor_manager_prompt_body_still_current custom_pipeline "$prompt_body" || {
    _planveyor_manager_custom_pipeline_terminal "$receipt_path" "$invocation_id" "$sid" \
      "$launch_surface" "$active_plan" "$status_pre" "$started_at" "$result_artifact" \
      blocked prompt_body_binding_changed "" "$active_plan" "$active_plan" \
      '{"state":"not_evaluated","reason":"prompt_body_binding_changed"}' \
      '{"state":"not_evaluated","reason":"prompt_body_binding_changed"}' \
      '{"state":"not_evaluated","reason":"prompt_body_binding_changed"}' \
      '{"state":"blocked","reason":"prompt_body_binding_changed"}'
    local terminal_rc=$?
    popd >/dev/null || return 1
    return $terminal_rc
  }

  local manager_rc=0
  if [[ "$launch_surface" == "codex_cli" ]]; then
    local -a tui_flags
    tui_flags=()
    (( no_alt_screen )) && tui_flags=(--no-alt-screen)
    MANAGER_INVOCATION_ID="$invocation_id" \
    MANAGER_INVOCATION_RECEIPT_PATH="$receipt_path" \
    _planveyor_with_role_env manager "$pybin" _planveyor_codex \
      resume "${tui_flags[@]}" "${codex_profile_args[@]}" -s workspace-write \
      "${sid}" "$payload"
    manager_rc=$?
  else
    MANAGER_INVOCATION_ID="$invocation_id" \
    MANAGER_INVOCATION_RECEIPT_PATH="$receipt_path" \
    _planveyor_with_role_env manager "$pybin" _planveyor_codex \
      exec -c 'approval_policy="on-request"' -c 'sandbox_mode="workspace-write"' \
      "${codex_profile_args[@]}" resume "${sid}" "$payload" >&2
    manager_rc=$?
  fi

  local exact_running=""
  exact_running="$(_planveyor_manager_invocation_receipt_read "$receipt_path" "$invocation_id")" || exact_running=""
  local checkpoint_state=""
  checkpoint_state="$(_planveyor_py_any - "$exact_running" <<'PY'
import json, sys
try:
    print(json.loads(sys.argv[1]).get("stop_checkpoint_state", ""))
except (TypeError, ValueError):
    print("")
PY
)"
  if [[ "$checkpoint_state" != "recorded" && "$queue_prelaunch_empty" == "true" && "$manager_rc" == "0" ]]; then
    MANAGER_INVOCATION_ID="$invocation_id" \
    MANAGER_INVOCATION_RECEIPT_PATH="$receipt_path" \
      planveyor_manager_invocation_checkpoint \
        --stop-reason-code queue_empty \
        --source-ref "scripts/plan_queue.py#queue-not-initialized-or-empty" \
        --json >/dev/null 2>&1 || true
    exact_running="$(_planveyor_manager_invocation_receipt_read "$receipt_path" "$invocation_id")" || exact_running=""
    checkpoint_state="$(_planveyor_py_any - "$exact_running" <<'PY'
import json, sys
try:
    print(json.loads(sys.argv[1]).get("stop_checkpoint_state", ""))
except (TypeError, ValueError):
    print("")
PY
)"
  fi

  local terminal_active_plan="$active_plan"
  local terminal_final_plan="$active_plan"
  local readback_plan="$active_plan"
  local queue_lineage_rc=0
  if [[ "$command" == "run_q" ]]; then
    queue_json="$(planveyor_q_show --json 2>/dev/null)"
    local queue_show_rc=$?
    if (( queue_show_rc != 0 )); then
      queue_discovery_rc=$queue_show_rc
      queue_lineage_rc=$queue_show_rc
    else
      local queue_lineage_kv=""
      queue_lineage_kv="$(_planveyor_manager_queue_terminal_lineage "$queue_json" "$active_plan")"
      queue_lineage_rc=$?
      if (( queue_lineage_rc == 0 )); then
        terminal_active_plan=""
        terminal_final_plan=""
        readback_plan=""
        local queue_lineage_row=""
        for queue_lineage_row in ${(f)queue_lineage_kv}; do
          case "$queue_lineage_row" in
            active_plan=*) terminal_active_plan="${queue_lineage_row#active_plan=}" ;;
            final_plan=*) terminal_final_plan="${queue_lineage_row#final_plan=}" ;;
            readback_plan=*) readback_plan="${queue_lineage_row#readback_plan=}" ;;
          esac
        done
        local normalized_lineage_plan=""
        if [[ -n "${terminal_active_plan//[[:space:]]/}" ]]; then
          normalized_lineage_plan="$(_planveyor_explicit_plan_normalize \
            "$root" "$terminal_active_plan" 2>/dev/null || true)"
          [[ "$normalized_lineage_plan" == "$terminal_active_plan" ]] || queue_lineage_rc=1
        fi
        if [[ -n "${terminal_final_plan//[[:space:]]/}" ]]; then
          normalized_lineage_plan="$(_planveyor_explicit_plan_normalize \
            "$root" "$terminal_final_plan" 2>/dev/null || true)"
          [[ "$normalized_lineage_plan" == "$terminal_final_plan" ]] || queue_lineage_rc=1
        fi
        if [[ -n "${readback_plan//[[:space:]]/}" ]]; then
          normalized_lineage_plan="$(_planveyor_explicit_plan_normalize \
            "$root" "$readback_plan" 2>/dev/null || true)"
          [[ "$normalized_lineage_plan" == "$readback_plan" ]] || queue_lineage_rc=1
        fi
      fi
    fi
  fi

  if [[ -n "${readback_plan//[[:space:]]/}" ]]; then
    result_artifact="$(_planveyor_result_artifact_for_plan "$readback_plan" "stdout receipt")"
  else
    result_artifact="stdout receipt"
  fi
  local status_post=""
  [[ -n "${readback_plan//[[:space:]]/}" ]] && \
    status_post="$(planveyor_status_line "$readback_plan" 2>/dev/null || true)"
  [[ -n "${status_post//[[:space:]]/}" ]] && echo "Plan status (post): ${status_post}" >&2
  local oracle_json=""
  local oracle_rc=0
  if [[ -n "${readback_plan//[[:space:]]/}" ]]; then
    oracle_json="$(_planveyor_py_any "$(_planveyor_script plan_status_oracle.py)" \
      "${root}/${readback_plan}" --json --manager-mode manager-custom-pipeline 2>/dev/null)"
    oracle_rc=$?
  else
    oracle_json='{"state":"not_applicable","reason":"no_active_plan"}'
  fi
  local worktree_json=""
  worktree_json="$(_planveyor_py_any - "$root" <<'PY'
import json, subprocess, sys
result = subprocess.run(
    ["git", "-C", sys.argv[1], "status", "--porcelain=v1"],
    text=True, capture_output=True, check=False,
)
print(json.dumps({
    "state": "clean" if result.returncode == 0 and not result.stdout.strip() else "dirty",
    "readback_ok": result.returncode == 0,
    "changed_path_count": len([line for line in result.stdout.splitlines() if line.strip()]),
}, sort_keys=True))
PY
)"
  local closeout_json=""
  closeout_json="$(_planveyor_py_any - "$status_post" <<'PY'
import json, sys
status = sys.argv[1]
terminal = "**Status:** Done" in status or "**Status:** Superseded" in status
print(json.dumps({
    "state": "terminal_status" if terminal else "non_terminal_status",
    "status_line": status or None,
}, ensure_ascii=False, sort_keys=True))
PY
)"

  local terminal_state="completed" terminal_reason="manager_process_exited"
  if (( manager_rc >= 128 )); then
    terminal_state="interrupted"
    terminal_reason="manager_process_interrupted"
  elif (( manager_rc != 0 )); then
    terminal_state="blocked"
    terminal_reason="manager_process_failed"
  elif [[ "$checkpoint_state" != "recorded" ]]; then
    terminal_state="blocked"
    terminal_reason="stop_checkpoint_missing"
  elif (( oracle_rc != 0 || queue_discovery_rc != 0 || queue_lineage_rc != 0 )) || [[ -z "${oracle_json//[[:space:]]/}" || -z "${queue_json//[[:space:]]/}" ]]; then
    terminal_state="blocked"
    terminal_reason="terminal_readback_failed"
  fi
  [[ -n "${oracle_json//[[:space:]]/}" ]] || oracle_json='{"state":"blocked","reason":"oracle_readback_failed"}'
  [[ -n "${queue_json//[[:space:]]/}" ]] || queue_json='{"state":"blocked","reason":"queue_readback_failed"}'

  _planveyor_manager_custom_pipeline_terminal "$receipt_path" "$invocation_id" "$sid" \
    "$launch_surface" "$readback_plan" "$status_pre" "$started_at" "$result_artifact" \
    "$terminal_state" "$terminal_reason" "$manager_rc" \
    "$terminal_active_plan" "$terminal_final_plan" \
    "$oracle_json" "$queue_json" \
    "$worktree_json" "$closeout_json"
  local terminal_rc=$?
  popd >/dev/null || return 1
  (( manager_rc != 0 )) && return $manager_rc
  return $terminal_rc
}

planveyor_manager_custom_pipeline() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager_custom_pipeline)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local plan_path=""
  plan_path="$(planveyor_planpath)" || return 1
  _planveyor_manager_custom_pipeline_supervise interactive codex_exec "$plan_path" ""
}

planveyor_manager_custom_pipeline_tui() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager_custom_pipeline_tui)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local no_alt_screen=0
  if [[ "${1:-}" == "--no-alt-screen" ]]; then
    no_alt_screen=1
    shift
  fi
  (( $# == 0 )) || {
    echo "Usage: planveyor_manager_custom_pipeline_tui [--no-alt-screen]" >&2
    return 2
  }
  local plan_path=""
  plan_path="$(planveyor_planpath)" || return 1
  _planveyor_manager_custom_pipeline_supervise interactive codex_cli "$plan_path" "" "$no_alt_screen"
}

_planveyor_manager_custom_pipeline_nonrun_cmd() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_manager_custom_pipeline_nonrun_cmd)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local cmd="${1:-}"
  shift || true
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body manager custom_pipeline)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode manager main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local sid=""
  sid="$(planveyor_session manager)" || return 1
  _planveyor_session_authority_resume_validate manager "$sid" || return $?
  local plan_path=""
  plan_path="$(planveyor_planpath 2>/dev/null || true)"
  local status_pre=""
  [[ -n "$plan_path" ]] && status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || true)"
  local payload=""
  payload="$({
    echo "ROLE=Manager"
    [[ -n "$plan_path" ]] && echo "PLAN_PATH=${plan_path}"
    [[ -n "$status_pre" ]] && echo "PRE_STATUS_LINE=${status_pre}"
    echo "PYBIN=${pybin}"
    printf '%s\n' "$prompt_body"
    echo ""
    echo "MANAGER_CMD=${cmd} $*"
  })"
  pushd "$root" >/dev/null || return 1
  _planveyor_manager_prompt_body_still_current custom_pipeline "$prompt_body" || {
    local binding_rc=$?
    popd >/dev/null || return 1
    return $binding_rc
  }
  _planveyor_with_role_env manager "$pybin" _planveyor_codex \
    exec -c 'approval_policy="on-request"' -c 'sandbox_mode="workspace-write"' \
    "${codex_profile_args[@]}" resume "${sid}" "$payload"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_manager_custom_pipeline_cmd() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager_custom_pipeline_cmd)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local cmd="${1:-}"
  (( $# > 0 )) && shift
  [[ -n "${cmd//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_manager_custom_pipeline_cmd <status|plan_set|run [PLAN_PATH|Q]|run_q>" >&2
    return 1
  }
  case "$cmd" in
    status|plan_set)
      _planveyor_manager_custom_pipeline_nonrun_cmd "$cmd" "$@"
      ;;
    run_q)
      (( $# == 0 )) || {
        echo "Usage: planveyor_manager_custom_pipeline_cmd run_q" >&2
        return 2
      }
      _planveyor_manager_custom_pipeline_supervise run_q codex_exec "" "MANAGER_CMD=run_q"
      ;;
    run)
      if (( $# == 1 )) && [[ "${1:-}" == "Q" ]]; then
        _planveyor_manager_custom_pipeline_supervise run_q codex_exec "" "MANAGER_CMD=run Q"
        return $?
      fi
      (( $# <= 1 )) || {
        echo "Usage: planveyor_manager_custom_pipeline_cmd run [PLAN_PATH|Q]" >&2
        return 2
      }
      local plan_path="${1:-}"
      [[ -n "$plan_path" ]] || plan_path="$(planveyor_planpath)" || return 1
      _planveyor_manager_custom_pipeline_supervise run codex_exec "$plan_path" \
        "MANAGER_CMD=run${1:+ ${1}}"
      ;;
    *)
      echo "Usage: planveyor_manager_custom_pipeline_cmd <status|plan_set|run [PLAN_PATH|Q]|run_q>" >&2
      return 1
      ;;
  esac
}
